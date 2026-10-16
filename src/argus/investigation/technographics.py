"""Enterprise Technographic Extraction and Deployment Intelligence Engine.

Extracts, attributes, and verifies company technology deployments from retrieved
open-source intelligence and technographic source material (e.g., vendor customer
announcements, case studies, TheirStack telemetry, and enterprise job postings).

Enforces the three-tier epistemic provenance model:
1. VENDOR_CONFIRMED: Official vendor customer disclosures or case studies.
2. TECHNOGRAPHIC_PROVIDER_ASSERTION: Third-party technographic telemetry (e.g., TheirStack, Enlyft).
3. CORROBORATED: Independently verified across multiple distinct publisher domains.

This module only *proposes* statuses from the publisher's source class. The final
status (and any corroboration) is decided by the shared verification gate in
``argus.investigation.claim_verification``; no numeric confidence is assigned here.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from argus.investigation.objective_parser import (
    COUNTRY_ALIASES,
    normalize_geography,
    parse_enumeration_objective,
)
from argus.investigation.claim_verification import (
    SOURCE_TECHNOGRAPHIC,
    SOURCE_VENDOR,
    TECHNOGRAPHIC_PROVIDER_DOMAINS,  # noqa: F401  (re-exported for existing importers)
    classify_source,
)


# Generic page/table words that are never organization names. Product and vendor
# words are rejected dynamically from the objective, not listed here.
COMMON_NON_COMPANIES = {
    "api export",
    "export",
    "technologies",
    "technology",
    "company",
    "companies",
    "industry",
    "employees",
    "revenue",
    "country",
    "domain",
    "high confidence",
    "search companies",
    "unknown",
    "who",
    "explore who",
    "explore",
    "search",
    "download",
    "pricing",
    "customers",
    "contact",
}

# Column-header vocabulary of technographic tables (generic, not vendor specific).
_HEADER_WORDS = {
    "api", "export", "company", "companies", "name", "country", "location", "hq", "headquarters",
    "industry", "sector", "employees", "employee", "size", "revenue", "technologies", "technology",
    "tech", "domain", "website", "confidence", "founded", "first", "seen", "last", "jobs",
}
_ROW_STOP_WORDS = {"employees", "employee", "revenue", "industry", "country", "domain", "hq", "headquarters", "founded", "confidence"}
_NAME_CONNECTORS = {"&", "and", "of", "de", "der", "la", "the", "y"}
_USE_VERB_PHRASE = (
    r"(?:(?:has|have|had|is|are|was|were)\s+)?(?:been\s+|now\s+|also\s+|recently\s+)?"
    r"(?:uses|use|used|using|deploys|deployed|deploying|runs|ran|running|implemented|implements|implementing|"
    r"adopted|adopts|adopting|selected|selects|chose|chosen|standardi[sz]ed\s+on|standardi[sz]es\s+on|"
    r"migrated\s+to|moved\s+to|rolled\s+out|relies\s+on|relied\s+on|licensed|licenses|upgraded\s+to)"
)


@dataclass
class TechnographicFinding:
    company: str
    software: str
    country: str = ""
    industry: str = ""
    employees: str = ""
    revenue: str = ""
    use_case: str = ""
    evidence_quote: str = ""
    source_url: str = ""
    status: str = "TECHNOGRAPHIC_PROVIDER_ASSERTION"
    confidence: float | None = None
    source_type: str = "technographic_provider"
    qualifier: str = "Third-Party Technographic Provider Assertion"
    matched_alias: str = ""


def classify_technographic_source(doc_url: str, software: str = "") -> tuple[str, float | None, str, str]:
    """Propose a provenance tier from the publisher's source class.

    Returns ``(proposed_status, confidence, source_type, qualifier)``. Confidence is
    always ``None``: a publisher's class says who asserts a deployment, not how
    likely the assertion is to be true.
    """
    source_class = classify_source(doc_url, software)
    if source_class == SOURCE_TECHNOGRAPHIC:
        return (
            "TECHNOGRAPHIC_PROVIDER_ASSERTION",
            None,
            "technographic_provider",
            "Third-Party Technographic Provider Assertion (Job Postings & Telemetry)",
        )
    if source_class == SOURCE_VENDOR:
        return (
            "VENDOR_CONFIRMED",
            None,
            "vendor_official_disclosure",
            "Vendor Customer Case Study / Official Disclosure",
        )
    return (
        "SUPPORTED",
        None,
        "independent_industry_press",
        "Independent Trade Press / Industry Report",
    )


def _provenance(doc_url: str, software: str) -> dict[str, Any]:
    status, confidence, source_type, qualifier = classify_technographic_source(doc_url, software)
    return {"status": status, "confidence": confidence, "source_type": source_type, "qualifier": qualifier}


_GEO_KEYS = sorted(COUNTRY_ALIASES, key=len, reverse=True)
_GEO_TOKEN_RE = re.compile(r"(?:" + "|".join(re.escape(k) for k in _GEO_KEYS) + r")(?![A-Za-z])", re.IGNORECASE)
_DOMAIN_RE = re.compile(r"[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)*\.[a-z]{2,}(?![A-Za-z0-9])")
_NUMBER_RE = re.compile(r"\d[\d,.]*\s*[kKmMbB]?\+?(?![A-Za-z0-9])")
_MONEY_RE = re.compile(r"\$\s?\d[\d,.]*\s*[kKmMbBtT]?\+?")
_NAME_TOKEN_RE = re.compile(r"(?:[A-Z0-9][\w&'.\-]*|[a-z]{1,3}[A-Z][\w&'.\-]*)")
_WORD_RE = re.compile(r"\$?[\w&'.\-]+|[·|,;:]")


def clean_company_name(raw_name: str, excluded_words: set[str] | None = None) -> str:
    """Return a plausible organization name, or "" for page furniture and product words."""
    if not raw_name:
        return ""
    clean = re.sub(r"\s+", " ", raw_name).strip(" ,;:-·|")
    words = clean.split(" ")
    while words and words[-1].lower() in _NAME_CONNECTORS:
        words.pop()
    clean = " ".join(words)
    low = clean.lower()
    if not clean or low in COMMON_NON_COMPANIES or normalize_geography(clean):
        return ""
    if excluded_words and all(w.lower() in excluded_words for w in words):
        return ""
    if len(clean) < 2 or len(clean) > 60:
        return ""
    if clean.startswith(("http", "www.", "{", "[", "curl")) or _DOMAIN_RE.fullmatch(clean):
        return ""
    if all(w.lower() in _HEADER_WORDS for w in words):
        return ""
    if not _NAME_TOKEN_RE.match(words[0]):
        return ""
    return clean


def detect_software_in_query(query: str) -> str:
    """The object named by an enumeration objective (no fixed product list)."""
    enum = parse_enumeration_objective(query or "")
    return enum.object_name if enum else "Enterprise Software"


def detect_country_in_query(query: str) -> str:
    """The geography constraint named by an enumeration objective, or ""."""
    enum = parse_enumeration_objective(query or "")
    return enum.geography if enum else ""


def _strip_header(prefix: str) -> str:
    """Drop a run of table column headers ("Company Country Industry ...") and anything before it."""
    words = list(re.finditer(r"\S+", prefix))
    cut = None
    run = 0
    for i, w in enumerate(words):
        if w.group(0).strip(",;:").lower() in _HEADER_WORDS:
            run += 1
            if run >= 2:
                cut = w.end()
        else:
            run = 0
    return prefix[cut:] if cut is not None else prefix


def _parse_row(prefix: str, excluded_words: set[str]) -> dict[str, Any] | None:
    """Parse '<Company> [domain] [country] [industry] [employees] [$revenue] ...' preceding a product mention.

    Requires a structural delimiter after the company name (domain, country, number,
    money or a field label). Without one the text is not treated as a table row.
    """
    pos = len(prefix) - len(prefix.lstrip(" ,;·|"))
    name_tokens: list[str] = []
    name_start = None
    delimiter = None
    while pos < len(prefix):
        while pos < len(prefix) and prefix[pos] == " ":
            pos += 1
        if pos >= len(prefix):
            break
        rest = prefix[pos:]
        prev = name_tokens[-1].lower() if name_tokens else ""
        geo_m = _GEO_TOKEN_RE.match(rest)
        if name_tokens and geo_m and prev not in _NAME_CONNECTORS and geo_m.group(0)[:1].isupper():
            delimiter = ("country", geo_m)
            break
        dom_m = _DOMAIN_RE.match(rest)
        if name_tokens and dom_m:
            delimiter = ("domain", dom_m)
            break
        money_m = _MONEY_RE.match(rest)
        num_m = _NUMBER_RE.match(rest)
        if name_tokens and (money_m or num_m):
            delimiter = ("number", None)
            break
        tok_m = re.match(r"\S+", rest)
        tok = tok_m.group(0)
        if name_tokens and (tok.lower() in _ROW_STOP_WORDS or tok in ("·", "|")):
            delimiter = ("label", None)
            break
        bare = tok.strip(",;:")
        if _NAME_TOKEN_RE.fullmatch(bare) or (name_tokens and bare.lower() in _NAME_CONNECTORS):
            if name_start is None:
                name_start = pos
            name_tokens.append(bare)
            pos += len(tok)
            if tok.endswith((",", ";", ":")):
                delimiter = ("punct", None)
                break
            continue
        return None
    if not name_tokens or delimiter is None or len(name_tokens) > 7:
        return None
    company = clean_company_name(" ".join(name_tokens), excluded_words)
    if not company:
        return None

    after = prefix[pos:]
    country = ""
    if delimiter[0] == "domain":
        after = after[delimiter[1].end():].lstrip()
    geo_m = _GEO_TOKEN_RE.match(after)
    if geo_m and geo_m.group(0)[:1].isupper():
        country = normalize_geography(geo_m.group(0)) or geo_m.group(0)
        after = after[geo_m.end():]
    money = _MONEY_RE.search(after)
    num = None
    for nm in _NUMBER_RE.finditer(after):
        if money and money.start() <= nm.start() < money.end():
            continue
        num = nm
        break
    first_num_pos = min([m.start() for m in (money, num) if m] or [len(after)])
    industry_words = [w for w in re.findall(r"[A-Za-z&,\-]+", after[:first_num_pos])]
    while industry_words and industry_words[-1].strip(",").lower() in excluded_words:
        industry_words.pop()
    industry = " ".join(industry_words).strip(" ,·|")
    if industry and industry.split()[0].lower() in _ROW_STOP_WORDS:
        industry = ""
    return {
        "company": company,
        "name_start": name_start,
        "country": country,
        "industry": industry[:80],
        "employees": num.group(0).strip() if num else "",
        "revenue": money.group(0).replace(" ", "") if money else "",
    }


def _parse_prose(prefix: str, excluded_words: set[str]) -> dict[str, Any] | None:
    """Parse '<Company> [has] <usage verb> [the] [Vendor] ' immediately preceding a product mention."""
    name_run = r"(?:[A-Z0-9][\w&'.\-]*|[a-z]{1,3}[A-Z][\w&'.\-]*)(?:\s+(?:(?:&|and|of|de)\s+)?(?:[A-Z0-9][\w&'.\-]*|[a-z]{1,3}[A-Z][\w&'.\-]*)){0,5}"
    m = re.search(
        rf"(?:^|(?<=[\s,(]))(?P<name>{name_run})\s+{_USE_VERB_PHRASE}\s+(?:the\s+|its\s+|their\s+)?(?:[A-Z][\w&\-]*\s+){{0,2}}$",
        prefix,
    )
    if not m:
        return None
    name = m.group("name")
    # Drop sentence-initial filler ("In 2024 Acme ...", "Today Acme ...") conservatively.
    words = name.split()
    while len(words) > 1 and (words[0].lower() in {"in", "today", "now", "recently", "also", "the"} or words[0].isdigit()):
        words.pop(0)
    company = clean_company_name(" ".join(words), excluded_words)
    if not company:
        return None
    return {"company": company, "name_start": m.start("name") + name.find(words[0]), "country": "", "industry": "", "employees": "", "revenue": ""}


def extract_technographic_deployments(
    text: str,
    doc_url: str = "",
    target_query: str = "",
    products: list[str] | None = None,
    geography: str | None = None,
) -> list[TechnographicFinding]:
    """Extract '(organization, uses, product)' assertions for the objective's product.

    ``products`` are the names of the objective's object (e.g. the user's
    "Teamcenter" and the evidence-qualified "Siemens Teamcenter"); when omitted
    they are parsed from ``target_query``. No fixed vendor or product list is used.

    Rows are recognised by structure rather than by one provider's layout: the text
    between consecutive product mentions is parsed as a row (company name followed by
    a domain, country, number or field label) or as a usage sentence. Rows whose
    stated country conflicts with the objective's geography are dropped; a country is
    never assumed from the query.
    """
    if products is None:
        enum = parse_enumeration_objective(target_query or "")
        products = [enum.object_name] if enum else []
        if geography is None and enum:
            geography = enum.geography
    names = sorted({p.strip() for p in products if p and p.strip()}, key=len, reverse=True)
    if not text or len(text) < 20 or not names:
        return []
    canonical = names[0]
    excluded_words = {w.lower() for n in names for w in re.findall(r"[\w&\-]+", n)}
    product_re = re.compile(r"(?<![\w-])(?:" + "|".join(re.escape(n) for n in names) + r")(?![\w-])", re.IGNORECASE)

    extracted: dict[str, TechnographicFinding] = {}
    prev_end = 0
    for m in product_re.finditer(text):
        seg_start = prev_end
        prev_end = m.end()
        prefix_full = text[seg_start:m.start()]
        # Rows and sentences do not span sentence breaks, line breaks or "|" separators.
        boundary = 0
        for b in re.finditer(r"[.!?](?=\s)|\n|\|", prefix_full):
            boundary = b.end()
        offset = seg_start + boundary
        prefix = prefix_full[boundary:]
        if len(prefix) > 400:
            offset += len(prefix) - 400
            prefix = prefix[-400:]
        stripped = _strip_header(prefix)
        offset += len(prefix) - len(stripped)
        prefix = stripped

        parsed = _parse_prose(prefix, excluded_words) or _parse_row(prefix, excluded_words)
        if not parsed:
            continue
        if geography and parsed["country"] and parsed["country"] != geography:
            continue
        company = parsed["company"]
        if company in extracted:
            continue
        quote = text[offset + parsed["name_start"]:m.end()].strip()
        matched = m.group(0)
        extracted[company] = TechnographicFinding(
            company=company,
            software=canonical,
            country=parsed["country"],
            industry=parsed["industry"],
            employees=parsed["employees"],
            revenue=parsed["revenue"],
            evidence_quote=quote,
            source_url=doc_url,
            matched_alias=matched,
            **_provenance(doc_url, canonical),
        )
    return list(extracted.values())
