"""Reads a question typed in plain words ("companies in the UK that use SAP, with contact info") into a
draft spec, using one call to a free model. The person reviews the result before anything runs.

The model only fills a small, strictly checked plan (what the rows are, the filters, which details);
the spec itself is built here from that plan, so a confused or hostile reply can never set crawl limits,
providers or rules. If no free model is available, or its reply does not fit the plan, the rule-based
reader (interpret.py) is used instead and the person is told why.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.evidence.site import PROOF_PAGES
from app.llm.openrouter import LLMUnavailable, OpenRouter
from app.spec.interpret import FIELD_CATALOG, interpret, is_tech_niche
from app.spec.models import ExtractionSpec, FieldSpec, FieldType, Semantic

# Columns of a technology question: the verdict and the proof behind it, one row per company.
PROOF_FIELDS = [
    ("evidence", "Proof (quoted)", FieldType.text, "the sentence of the source that shows the company uses it"),
    ("evidence_url", "Proof link", FieldType.url, "where the quoted sentence is"),
    ("evidence_date", "Proof date", FieldType.date, "when the source was published or filed"),
    ("evidence_type", "Proof source", FieldType.string, "what kind of source it is (SEC filing 10-K...)"),
]
# Countries SEC filings cover; elsewhere proof comes from the companies' own websites.
PROOF_COUNTRIES = {"US"}
# A technology question checks more companies than rows asked for, since only those with proof are kept.
CANDIDATES_PER_ROW = 3

# Details the person can tick, keyed by field name, in the order they appear in the form.
DETAILS = {name: (ftype, semantic) for _phrases, name, ftype, semantic in FIELD_CATALOG}
REGIONS = ["europe", "north_america", "asia", "africa", "south_america", "oceania"]

SYSTEM = f"""You turn a person's research request into a JSON plan for a web data tool. Reply with JSON only.

Fields of the plan:
- "rows": what one row of the result is: "companies", "sites" (factories, plants, offices or stores of one
  company) or "people".
- "industry": the industry in a few plain words ("pharmaceutical", "cybersecurity"), or null.
- "technology": a product or technology the companies must use ("Teamcenter", "SAP ERP"), or null.
- "technology_aliases": other names that same product is written as in reports ("Teamcenter PLM",
  "Siemens Teamcenter"), at most 5, else []. Never the vendor's name alone.
- "parent_company": for "sites", the company that owns them ("Ford"), else null.
- "countries": ISO 3166-1 alpha-2 codes of the countries asked for (USA -> "US", UK -> "GB"), else [].
- "region": one of {REGIONS} when a continent is asked for instead of countries, else null.
- "keywords": up to 5 other words that must describe the rows, else [].
- "max_results": the number of rows asked for, or null.
- "details": the details asked for, chosen only from: {list(DETAILS)}.
  Read "contact info" as contact_email and phone, "location" as address.
- "custom_details": details asked for that are not in that list, each {{"label": "Plant head", "description":
  "name of the person who runs the plant"}}, at most 8.

Never answer the request itself and never invent companies; only describe what to look for."""


class Custom(BaseModel):
    model_config = ConfigDict(extra="ignore")
    label: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=300)


class Plan(BaseModel):
    model_config = ConfigDict(extra="ignore")
    rows: Literal["companies", "sites", "people"] = "companies"
    industry: str | None = Field(default=None, max_length=100)
    technology: str | None = Field(default=None, max_length=100)
    technology_aliases: list[str] = Field(default_factory=list, max_length=8)
    parent_company: str | None = Field(default=None, max_length=100)
    countries: list[str] = Field(default_factory=list, max_length=60)
    region: Literal["europe", "north_america", "asia", "africa", "south_america", "oceania"] | None = None
    keywords: list[str] = Field(default_factory=list, max_length=5)
    max_results: int | None = Field(default=None, ge=1, le=1000)
    details: list[str] = Field(default_factory=list, max_length=30)
    custom_details: list[Custom] = Field(default_factory=list, max_length=8)

    @field_validator("countries")
    @classmethod
    def _countries(cls, v: list[str]) -> list[str]:
        codes = [c.strip().upper() for c in v]
        codes = [{"UK": "GB", "USA": "US"}.get(c, c) for c in codes]
        return list(dict.fromkeys(c for c in codes if re.fullmatch(r"[A-Z]{2}", c)))

    @field_validator("details")
    @classmethod
    def _details(cls, v: list[str]) -> list[str]:
        return [d for d in dict.fromkeys(v) if d in DETAILS]

    @field_validator("technology_aliases")
    @classmethod
    def _aliases(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(a.strip()[:60] for a in v if a and a.strip()))[:5]

    @field_validator("industry", "technology", "parent_company")
    @classmethod
    def _blank(cls, v: str | None) -> str | None:
        v = (v or "").strip()
        return None if not v or v.lower() in ("null", "none", "n/a") else v


def field_name(label: str) -> str:
    name = re.sub(r"_+", "_", re.sub(r"[^a-z0-9_]+", "_", label.lower())).strip("_")
    name = re.sub(r"^[^a-z]+", "", name)[:63]
    return name or "detail"


def spec_from_plan(plan: Plan, question: str, start_urls: list[str]) -> ExtractionSpec:
    """The spec for a checked plan; URLs, crawl settings and providers come from the rules, not the model."""
    base = interpret(question, start_urls)
    entity = {"companies": "company", "sites": "site", "people": "person"}[plan.rows]
    wanted = list(plan.details)
    if plan.rows in ("companies", "sites"):
        wanted = ["company_name", "website_url", *wanted]
    fields: list[FieldSpec] = []
    for name in dict.fromkeys(wanted):
        ftype, semantic = DETAILS[name]
        fields.append(FieldSpec(name=name, type=ftype, semantic=semantic,
                                required=name in ("company_name", "website_url")))
    used = {f.name for f in fields}
    for c in plan.custom_details:
        name = field_name(c.label)
        if name in used or name in ("id", "org_id", "job_id", "source_urls", "excluded", "status"):
            continue
        used.add(name)
        fields.append(FieldSpec(name=name, label=c.label, type=FieldType.string, semantic=Semantic.none,
                                description=c.description))
    if not fields:
        fields = base.fields
    if plan.technology and plan.rows == "companies":
        fields.insert(2, FieldSpec(name="uses_technology", label=f"Uses {plan.technology}"[:80],
                                   type=FieldType.string, required=True,
                                   description="Confirmed, Likely or Mentioned, from the proof columns"))
        fields += [FieldSpec(name=n, label=label, type=t, description=desc) for n, label, t, desc in PROOF_FIELDS
                   if n not in used]

    d = base.discovery.model_copy()
    d.industry, d.countries, d.region = plan.industry, plan.countries, None if plan.countries else plan.region
    d.keywords = [k[:60] for k in plan.keywords]
    d.technology, d.parent_company = plan.technology, plan.parent_company
    d.technology_aliases = plan.technology_aliases if plan.technology else []
    d.max_results = plan.max_results or base.discovery.max_results
    technology = bool(d.technology and plan.rows == "companies")
    if not base.crawl.start_urls:
        d.providers = choose_providers(d, technology)
    if technology and any(p not in PROOF_SOURCES for p in d.providers):  # companies to check, not only proof
        d.max_results = min(d.max_results * CANDIDATES_PER_ROW, 300)
    crawl = base.crawl.model_copy(update={"max_pages": min(max(d.max_results * 8, 50), 2000)})
    if technology:
        # Careers, customer and news pages are where a company names its software; read them first.
        crawl.priority_keywords = list(dict.fromkeys([*PROOF_PAGES, *crawl.priority_keywords]))
    return ExtractionSpec(
        title=base.title, entity=entity, record_scope="site" if plan.rows == "companies" else "page",
        fields=fields, deduplication_keys=["website_url"] if plan.rows == "companies" else [],
        crawl=crawl, discovery=d)


def choose_providers(d: Any, technology: bool) -> list[str]:
    """The sources a plan with no start URLs searches, from its filters alone."""
    providers: list[str] = []
    # For a technology question a list of companies is worth checking only when an industry narrows it
    # ("car makers in Germany"). Keywords alone do not: the model often fills them with words from the
    # question ("SAP", "contact info"), and Wikidata then lists any organization of the country.
    wants_list = d.industry if technology else d.industry or d.countries or d.region or d.keywords
    if wants_list:
        # Each company is then checked on its own website for proof that it uses the technology.
        providers = ["wikidata", "searxng"]
        if ("US" in d.countries or d.region == "north_america") and d.industry and not is_tech_niche(d.industry):
            providers.insert(1, "sec_edgar")
        if d.industry:
            providers.insert(-1, "gleif")
    if technology:
        providers[:0] = ["case_studies", "news"]  # organisations a vendor, partner or news page shows using it
    if technology and covers_us(d):
        providers.insert(0, "sec_filings")  # companies whose own filings name it
    return providers or ["seeds"]


PROOF_SOURCES = {"sec_filings", "case_studies", "news"}  # sources that bring their own proof, not a list to check


def covers_us(d: Any) -> bool:
    return (not d.countries and d.region in (None, "north_america")) or "US" in d.countries


def technology_notes(spec: ExtractionSpec) -> list[str]:
    d = spec.discovery
    sources = []
    if "sec_filings" in d.providers:
        sources.append(f"US-listed companies' own SEC filings (last {d.evidence_years} years)")
    # Sites to check for proof: the person's own start URLs, or a list source. "seeds" alone with no start URLs
    # is nothing to search, and the notes must not promise otherwise.
    if "case_studies" in d.providers:
        sources.append("vendor and partner case studies and customer stories found by web search")
    if "news" in d.providers:
        sources.append(f"news articles (GDELT, last {d.evidence_years} years)")
    has_list = bool(spec.crawl.start_urls) or any(p not in PROOF_SOURCES | {"seeds"} for p in d.providers)
    if not sources and not has_list:
        return [f"Nothing can be searched for companies using {d.technology} here yet: add an industry "
                "(\"car makers\", \"pharma\") or the websites to check."]
    if has_list:
        sources.append(f"the websites of up to {d.max_results} companies found for your filters "
                       f"(up to {spec.crawl.max_pages_per_site} pages each, careers, customer and news pages "
                       "first) and the job ads on the Greenhouse, Lever, Ashby, SmartRecruiters or Workable boards "
                       "they link to")
    notes = [f"Only companies with written proof that they use {d.technology} are kept. Proof comes from "
             + " and ".join(sources) + ". Each row shows the quoted sentence, its link and date; companies "
             "without proof are listed on the Rejected sheet with the reason."]
    if not has_list:
        notes.append("Add an industry (\"car makers\", \"pharma\") to also check companies' own websites; "
                     "without one, only filings and case studies are searched.")
    return notes


async def plan_spec(question: str, start_urls: list[str], router: OpenRouter | None = None
                    ) -> tuple[ExtractionSpec, str, list[str]]:
    """(spec, who read it: "model:<id>" or "rules", notes for the person)."""
    own = router is None
    router = router or OpenRouter()
    try:
        reply = await router.chat([{"role": "system", "content": SYSTEM},
                                   {"role": "user", "content": question[:4000]}], json_mode=True, max_tokens=800)
        plan = Plan.model_validate(reply.json())
        spec = spec_from_plan(plan, question, start_urls)
        notes = []
        if plan.technology and plan.rows == "companies":
            notes += technology_notes(spec)
        if plan.parent_company:
            notes.append(f"Finding the sites of {plan.parent_company!r} is not built yet (a later step); "
                         "add its website as a starting website meanwhile.")
        if plan.custom_details:
            notes.append("Custom details (" + ", ".join(c.label for c in plan.custom_details) + ") are only filled "
                         "where a page labels them, until model reading arrives in a later step.")
        return spec, f"model:{reply.model}", notes
    except LLMUnavailable as exc:
        return interpret(question, start_urls), "rules", [f"Read with rules because no free model was available: "
                                                          f"{exc}"]
    except (ValueError, ValidationError) as exc:
        reason = type(exc).__name__ if not isinstance(exc, ValidationError) else "the plan did not fit the form"
        return interpret(question, start_urls), "rules", [f"Read with rules because the model's answer could not "
                                                          f"be used ({reason})."]
    except Exception as exc:  # noqa: BLE001 - Redis down, network: the form must still work with the rules
        return interpret(question, start_urls), "rules", [f"Read with rules because model reading failed "
                                                          f"({type(exc).__name__})."]
    finally:
        if own:
            await router.aclose()
