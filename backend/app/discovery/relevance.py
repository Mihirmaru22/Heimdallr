"""Checks a web-search (SearXNG) result's homepage before the site is crawled.

Search results are only links: "cybersecurity companies United States" also returns personal blogs,
unrelated firms and companies in other countries. Registries (Wikidata, SEC) already filter by
industry and country, so only search results go through this. A site is dropped when its homepage
never mentions the industry, or when it clearly belongs to another country (its structured address,
a country-code domain, or homepage phone numbers that all share one country). Anything unclear is kept.
"""

from __future__ import annotations

import re
from collections import Counter
from urllib.parse import unquote

import phonenumbers

from app.crawl.urlnorm import registered_domain
from app.discovery.providers import COUNTRY_QIDS
from app.extract.deterministic import PageDoc, _address_text, _orgs
from app.spec.models import ExtractionSpec
from app.spec.spelling import spellings, to_us

# Other ways sites write an industry ("cyber security", "financial technology").
INDUSTRY_WORDS = {
    "cybersecurity": ["cyber", "security"], "computer security": ["security", "cyber"],
    "fintech": ["fintech", "financial technology", "payments"], "edtech": ["edtech", "education", "learning"],
    "ai": ["artificial intelligence", " ai ", "machine learning", "ai-powered", "genai"],
    "saas": ["saas", "software", "platform"], "biotech": ["biotech", "biolog", "therapeut"],
    "pharma": ["pharma"], "healthtech": ["health"],
    "defense": ["defense", "military", "armed forces"], "aerospace": ["aerospace", "aircraft", "aviation"],
}
STOP = {"and", "the", "for", "companies", "company", "industry", "sector", "firms", "startups", "services"}
# Country-code domains that are used worldwide as generic names and say nothing about location.
GENERIC_CCTLDS = {"io", "ai", "co", "me", "tv", "ly", "fm", "gg", "sh", "so", "to", "cc", "ws", "app", "dev"}
CCTLD_TO_ISO = {"uk": "GB"}
COUNTRY_NAMES = {"united states": "US", "usa": "US", "us": "US", "united kingdom": "GB", "uk": "GB",
                 "great britain": "GB", "germany": "DE", "deutschland": "DE", "france": "FR", "italy": "IT",
                 "italia": "IT", "spain": "ES", "españa": "ES", "netherlands": "NL", "poland": "PL", "polska": "PL",
                 "canada": "CA", "india": "IN", "australia": "AU", "israel": "IL", "japan": "JP"}

COUNTRY_NAMES.update({name.lower(): iso for iso, (_qid, name) in COUNTRY_QIDS.items()})
COUNTRY_NAMES.update({"united states of america": "US", "people's republic of china": "CN"})
REGISTRIES = {"wikidata", "sec_edgar", "gleif"}  # sources that already filter by country themselves


def country_iso(value: str | None) -> str | None:
    """"United States", "us", "USA" -> "US"; None when the name is not one we know."""
    v = (value or "").strip()
    if re.fullmatch(r"[A-Za-z]{2}", v):
        return CCTLD_TO_ISO.get(v.lower(), v.upper())
    return COUNTRY_NAMES.get(v.lower())


def outside_countries_reason(doc: PageDoc, spec: ExtractionSpec, method: str, hint: dict | None) -> str | None:
    """With "only these countries" on, why a discovered site must be left out (None to keep it).

    A site is dropped when its registry entry or its own homepage puts it in another country. A web-search
    result whose country cannot be confirmed is dropped too; registries have already matched the country,
    and start URLs the user typed are always kept.
    """
    d = spec.discovery
    if not d.countries or not d.strict_countries or method == "seed":
        return None
    country = country_iso((hint or {}).get("country")) or site_country(doc)
    if country:
        return None if country in d.countries else f"based in {country}, outside {', '.join(d.countries)}"
    if method not in REGISTRIES:
        return f"could not confirm it is based in {', '.join(d.countries)}"
    return None


def industry_terms(industry: str) -> list[str]:
    term = industry.lower().strip()
    us = to_us(term)
    if us in INDUSTRY_WORDS:
        terms = [term, us, *INDUSTRY_WORDS[us]]
    else:
        words = [w for w in re.findall(r"[a-z]+", term) if len(w) >= 3 and w not in STOP]
        # "pharmaceutical" also matches "pharma", "manufacturing" also "manufacturer".
        terms = [term] + [w[:6] if len(w) > 7 else w for w in words]
    # A UK "defence" company and a US "defense" company are both a match, whichever way it was typed.
    return list(dict.fromkeys(v for t in terms for v in spellings(t)))


# Below this many words of visible text, with no description either, a homepage is a loader, a cookie wall
# or a bot-challenge stub: nothing was read, so nothing about the site can be judged from it.
MIN_READABLE_WORDS = 5


def unreadable(doc: PageDoc) -> bool:
    """True when the fetched homepage has too little text to judge (an empty shell, not the site itself)."""
    described = doc.meta.get("description") or doc.meta.get("og:description")
    return len(doc.text.split()) < MIN_READABLE_WORDS and not described


def off_topic_reason(doc: PageDoc, spec: ExtractionSpec, check_country: bool = True) -> str | None:
    """Why this search result's homepage is not a match, or None to keep it."""
    d = spec.discovery
    subject = d.industry or " ".join(d.keywords)
    if subject.strip():
        text = f" {doc.title} {doc.meta.get('description', '')} {doc.meta.get('og:description', '')} " \
               f"{doc.text[:20_000]} ".lower()
        if not any(t in text for t in industry_terms(subject)):
            return f"homepage does not mention {subject!r}"
    if d.countries and check_country:
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
            iso = country_iso(c)
            if iso:
                return iso
    site = registered_domain(doc.url) or ""
    tld = site.rsplit(".", 1)[-1].lower()
    if len(tld) == 2 and tld not in GENERIC_CCTLDS:
        return CCTLD_TO_ISO.get(tld, tld.upper())
    # International phone numbers on the homepage: a multinational lists its regional offices, so the country
    # with the most distinct numbers wins when no other country has as many.
    numbers: dict[str, str] = {}
    for a in doc.tree.css('a[href^="tel:"]')[:10]:
        raw = unquote(a.attributes.get("href") or "")[4:].strip()
        if raw.startswith("+"):
            try:
                num = phonenumbers.parse(raw, None)
            except phonenumbers.NumberParseException:
                continue
            region = phonenumbers.region_code_for_number(num)
            if region and region != "ZZ":
                numbers[phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)] = region
    ranked = Counter(numbers.values()).most_common(2)
    if ranked and (len(ranked) == 1 or ranked[0][1] > ranked[1][1]):
        return ranked[0][0]
    return None
