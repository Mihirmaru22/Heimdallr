"""Rule-based request interpretation: turns a plain-English request into a draft spec, no LLM.

It recognises common field names ("email", "headquarters", "pricing"...), URLs and domains,
a target count ("up to 500"), an industry phrase and countries or regions. Anything it cannot
map becomes a plain string field the user can configure. The person always reviews the result.
"""

from __future__ import annotations

import re

from app.spec.models import (
    CrawlSettings,
    DiscoverySettings,
    ExtractionSpec,
    FieldSpec,
    FieldType,
    Semantic,
)

# phrase -> (field name, type, semantic)
FIELD_CATALOG: list[tuple[tuple[str, ...], str, FieldType, Semantic]] = [
    (("company name", "organization name", "organisation name", "business name", "name of the company"),
     "company_name", FieldType.string, Semantic.company_name),
    (("website", "official site", "homepage", "web site", "website url"), "website_url", FieldType.url,
     Semantic.website_url),
    (("contact email", "email", "e-mail"), "contact_email", FieldType.email, Semantic.contact_email),
    (("phone", "telephone", "phone number"), "phone", FieldType.phone, Semantic.phone),
    (("headquarters", "hq", "head office", "headquartered"), "headquarters", FieldType.string, Semantic.headquarters),
    (("address", "postal address", "location"), "address", FieldType.string, Semantic.address),
    (("country",), "country", FieldType.string, Semantic.country),
    (("description", "summary", "about"), "description", FieldType.text, Semantic.description),
    (("pricing", "price", "prices", "plans"), "pricing", FieldType.string, Semantic.pricing),
    (("product categories", "products", "product category", "services", "offerings"),
     "product_categories", FieldType.list, Semantic.product_categories),
    (("industry", "sector"), "industry", FieldType.string, Semantic.industry),
    (("founded", "year founded", "founding year"), "founded_year", FieldType.integer, Semantic.founded_year),
    (("social", "linkedin", "twitter", "social media"), "social_links", FieldType.list, Semantic.social_links),
    (("title", "page title"), "page_title", FieldType.string, Semantic.page_title),
    (("source url", "source urls", "sources", "source"), "source_url", FieldType.url, Semantic.source_url),
]

ENTITY_WORDS = {
    "compan": "company", "business": "company", "startup": "company", "vendor": "company",
    "firm": "company", "organi": "company", "product": "product", "store": "store", "shop": "store",
    "school": "school", "universit": "university", "hospital": "hospital", "restaurant": "restaurant",
}

REGIONS = {
    "europe": "europe", "european": "europe", "eu": "europe", "north america": "north_america",
    "asia": "asia", "africa": "africa", "south america": "south_america", "latin america": "south_america",
    "oceania": "oceania",
}

COUNTRIES = {
    "united kingdom": "GB", "uk": "GB", "britain": "GB", "germany": "DE", "france": "FR", "spain": "ES",
    "italy": "IT", "netherlands": "NL", "belgium": "BE", "sweden": "SE", "norway": "NO", "denmark": "DK",
    "finland": "FI", "poland": "PL", "ireland": "IE", "switzerland": "CH", "austria": "AT", "portugal": "PT",
    "estonia": "EE", "israel": "IL", "united states": "US", "usa": "US", "canada": "CA", "india": "IN",
    "japan": "JP", "australia": "AU", "singapore": "SG", "brazil": "BR",
}

URL_RE = re.compile(r"https?://[^\s,;'\")<>]+", re.I)
DOMAIN_RE = re.compile(r"(?<![@\w.-])((?:[a-z0-9-]+\.)+[a-z]{2,24})(?![\w-])", re.I)
COUNT_RE = re.compile(r"\b(?:up to|at most|max(?:imum)?|top|find|list)\s+(\d{1,5})\b", re.I)
INDUSTRY_RE = re.compile(r"\b(?:find|list|collect|get)\s+(?:up to\s+\d+\s+|\d+\s+)?([a-z][a-z \-]{2,40}?)\s+"
                         r"(?:companies|company|firms|vendors|startups|businesses)", re.I)


def _has(text: str, phrase: str) -> bool:
    return re.search(rf"(?<![a-z]){re.escape(phrase)}(?![a-z])", text) is not None


def interpret(request: str, start_urls: list[str] | None = None) -> ExtractionSpec:
    text = request.lower()
    fields: list[FieldSpec] = []
    used: set[str] = set()
    for phrases, name, ftype, semantic in FIELD_CATALOG:
        if name in used:
            continue
        if any(_has(text, p) for p in phrases):
            fields.append(FieldSpec(name=name, type=ftype, semantic=semantic))
            used.add(name)

    entity = next((v for k, v in ENTITY_WORDS.items() if k in text), "record")
    if entity == "company" and "company_name" not in used:
        fields.insert(0, FieldSpec(name="company_name", type=FieldType.string, semantic=Semantic.company_name,
                                   required=True))
        used.add("company_name")
    if "website_url" not in used and entity in ("company", "store", "school", "university", "hospital"):
        fields.append(FieldSpec(name="website_url", type=FieldType.url, semantic=Semantic.website_url))
        used.add("website_url")
    if not fields:
        fields = [FieldSpec(name="page_title", type=FieldType.string, semantic=Semantic.page_title),
                  FieldSpec(name="description", type=FieldType.text, semantic=Semantic.description)]
    for f in fields:
        if f.name in ("company_name", "website_url"):
            f.required = True

    urls = list(dict.fromkeys((start_urls or []) + URL_RE.findall(request)))
    url_text = " ".join(urls)
    for d in DOMAIN_RE.findall(request):
        if d.lower() not in url_text.lower() and "@" not in d:
            urls.append(f"https://{d.lower()}/")

    count_match = COUNT_RE.search(request)
    max_results = int(count_match.group(1)) if count_match else 50
    region = next((v for k, v in REGIONS.items() if _has(text, k)), None)
    countries = sorted({v for k, v in COUNTRIES.items() if _has(text, k)})
    industry_match = INDUSTRY_RE.search(request)
    industry = industry_match.group(1).strip() if industry_match else None

    providers: list = ["seeds"] if urls else []
    if not urls and (industry or region or countries):
        # Wikidata gives name + website for well-known firms; SearXNG (when configured) finds the rest.
        providers = ["wikidata", "searxng"]
        if "US" in countries or region == "north_america":
            providers.append("sec_edgar")  # SEC lists every US-listed company by industry code
    dedupe = ["website_url"] if "website_url" in used else ([fields[0].name] if fields else [])
    record_scope = "site" if entity in ("company", "store", "school", "university", "hospital") else "page"
    title = request.strip().split("\n")[0][:120] or "Extraction"
    return ExtractionSpec(
        title=title,
        entity=entity,
        record_scope=record_scope,
        fields=fields,
        deduplication_keys=dedupe,
        crawl=CrawlSettings(start_urls=urls, max_pages=min(max(max_results * 8, 50), 2000)),
        discovery=DiscoverySettings(providers=providers or ["seeds"], industry=industry, countries=countries,
                                    region=region, max_results=max_results),
    )
