"""Checks a web-search (SearXNG) result's homepage before the site is crawled.

Search results are only links: "cybersecurity companies United States" also returns personal blogs,
unrelated firms and companies in other countries. Registries (Wikidata, SEC) already filter by
industry and country, so only search results go through this. A site is dropped when its homepage
never mentions the industry, or when it clearly belongs to another country (its structured address,
a country-code domain, or homepage phone numbers that all share one country). Anything unclear is kept.
"""

from __future__ import annotations

import re

import phonenumbers

from app.crawl.urlnorm import registered_domain
from app.extract.deterministic import PageDoc, _address_text, _orgs
from app.spec.models import ExtractionSpec

# Other ways sites write an industry ("cyber security", "financial technology").
INDUSTRY_WORDS = {
    "cybersecurity": ["cyber", "security"], "computer security": ["security", "cyber"],
    "fintech": ["fintech", "financial technology", "payments"], "edtech": ["edtech", "education", "learning"],
    "ai": ["artificial intelligence", " ai ", "machine learning", "ai-powered", "genai"],
    "saas": ["saas", "software", "platform"], "biotech": ["biotech", "biolog", "therapeut"],
    "pharma": ["pharma"], "healthtech": ["health"],
}
STOP = {"and", "the", "for", "companies", "company", "industry", "sector", "firms", "startups", "services"}
# Country-code domains that are used worldwide as generic names and say nothing about location.
GENERIC_CCTLDS = {"io", "ai", "co", "me", "tv", "ly", "fm", "gg", "sh", "so", "to", "cc", "ws", "app", "dev"}
CCTLD_TO_ISO = {"uk": "GB"}
COUNTRY_NAMES = {"united states": "US", "usa": "US", "us": "US", "united kingdom": "GB", "uk": "GB",
                 "great britain": "GB", "germany": "DE", "deutschland": "DE", "france": "FR", "italy": "IT",
                 "italia": "IT", "spain": "ES", "españa": "ES", "netherlands": "NL", "poland": "PL", "polska": "PL",
                 "canada": "CA", "india": "IN", "australia": "AU", "israel": "IL", "japan": "JP"}


def industry_terms(industry: str) -> list[str]:
    term = industry.lower().strip()
    if term in INDUSTRY_WORDS:
        return [term, *INDUSTRY_WORDS[term]]
    words = [w for w in re.findall(r"[a-z]+", term) if len(w) >= 3 and w not in STOP]
    # "pharmaceutical" also matches "pharma", "manufacturing" also "manufacturer".
    return [term] + [w[:6] if len(w) > 7 else w for w in words]


def off_topic_reason(doc: PageDoc, spec: ExtractionSpec) -> str | None:
    """Why this search result's homepage is not a match, or None to keep it."""
    d = spec.discovery
    subject = d.industry or " ".join(d.keywords)
    if subject.strip():
        text = f" {doc.title} {doc.meta.get('description', '')} {doc.meta.get('og:description', '')} " \
               f"{doc.text[:20_000]} ".lower()
        if not any(t in text for t in industry_terms(subject)):
            return f"homepage does not mention {subject!r}"
    if d.countries:
        country = site_country(doc)
        if country and country not in d.countries:
            return f"appears to be based in {country}, not {', '.join(d.countries)}"
    return None


def site_country(doc: PageDoc) -> str | None:
    """ISO country from the site's own structured address, a country-code domain, or its phone numbers."""
    for org in _orgs(doc):
        _full, _loc, country = _address_text(org.get("address"))
        if country:
            c = country.strip()
            iso = c.upper() if re.fullmatch(r"[A-Za-z]{2}", c) else COUNTRY_NAMES.get(c.lower())
            if iso:
                return CCTLD_TO_ISO.get(iso.lower(), iso)
    site = registered_domain(doc.url) or ""
    tld = site.rsplit(".", 1)[-1].lower()
    if len(tld) == 2 and tld not in GENERIC_CCTLDS:
        return CCTLD_TO_ISO.get(tld, tld.upper())
    # International phone numbers on the homepage, when they all point to one country.
    regions = set()
    for a in doc.tree.css('a[href^="tel:"]')[:10]:
        raw = (a.attributes.get("href") or "")[4:].strip()
        if raw.startswith("+"):
            try:
                region = phonenumbers.region_code_for_number(phonenumbers.parse(raw, None))
            except phonenumbers.NumberParseException:
                continue
            if region and region != "ZZ":
                regions.add(region)
    return regions.pop() if len(regions) == 1 else None
