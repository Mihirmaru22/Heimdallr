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
from app.extract.deterministic import PageDoc, _address_text, _orgs, _phones
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


# What the "only these countries" check concluded about a site.
IN_COUNTRY, OUTSIDE_COUNTRY, COUNTRY_UNKNOWN, NOT_CHECKED = "in_country", "outside_country", "unknown", "not_checked"


def country_status(doc: PageDoc, spec: ExtractionSpec, method: str, hint: dict | None) -> tuple[str, str]:
    """With "only these countries" on: (IN_COUNTRY, OUTSIDE_COUNTRY, COUNTRY_UNKNOWN or NOT_CHECKED, why).

    A registry entry or the site's own homepage decides. Registries have already matched the country and start
    URLs the user typed are always kept, so for them an unknown country is NOT_CHECKED, not COUNTRY_UNKNOWN.
    """
    d = spec.discovery
    if not d.countries or not d.strict_countries or method == "seed":
        return NOT_CHECKED, ""
    if country := country_iso((hint or {}).get("country")):
        how = f"{method} says {country}"
    else:
        country, how = site_country(doc), "the homepage"
    if country:
        if country in d.countries:
            return IN_COUNTRY, f"based in {country} ({how})"
        return OUTSIDE_COUNTRY, f"based in {country}, outside {', '.join(d.countries)} ({how})"
    if method not in REGISTRIES:
        return COUNTRY_UNKNOWN, f"could not confirm it is based in {', '.join(d.countries)}"
    return NOT_CHECKED, ""


def outside_countries_reason(doc: PageDoc, spec: ExtractionSpec, method: str, hint: dict | None) -> str | None:
    """With "only these countries" on, why a discovered site must be left out (None to keep it).

    A site is dropped when its registry entry or its own homepage puts it in another country. A web-search
    result whose country cannot be confirmed is dropped too; registries have already matched the country,
    and start URLs the user typed are always kept.
    """
    status, why = country_status(doc, spec, method, hint)
    return why if status in (OUTSIDE_COUNTRY, COUNTRY_UNKNOWN) else None


def pages_country(docs: list[PageDoc], wanted: list[str] | tuple[str, ...] = ()) -> tuple[str | None, str]:
    """(ISO country, where it was read) from a homepage plus the company's own contact or about pages.

    The same evidence as `site_country`, in the same order, over several pages: structured addresses when
    they all give one country, then a country-code domain, then the phone numbers of all pages together when
    they all belong to one country. Addresses or numbers in several countries settle nothing: a branch office
    looks like the headquarters, and a multinational's contact page lists its regional offices. Contact pages
    often write their numbers as plain text ("+44 (0) 845 838 2050"), so numbers written with their country
    code count too, not only tel: links. A page's words ("UK", "London") are never read as a location.
    """
    addresses: dict[str, list[str]] = {}  # country -> pages with a structured address there
    for doc in docs:
        for org in _orgs(doc):
            _full, _loc, country = _address_text(org.get("address"))
            if (iso := country_iso((country or "").strip())) and doc.url not in addresses.get(iso, []):
                addresses.setdefault(iso, []).append(doc.url)
    if len(addresses) == 1:
        ((iso, pages),) = addresses.items()
        return iso, f"structured address on {', '.join(pages)}"
    if addresses:  # a branch office and the headquarters look alike: several countries settle nothing
        return None, "structured addresses in several countries: " + "; ".join(
            f"{iso} on {', '.join(pages)}" for iso, pages in addresses.items())
    tld = (registered_domain(docs[0].url) or "").rsplit(".", 1)[-1].lower() if docs else ""
    if len(tld) == 2 and tld not in GENERIC_CCTLDS:
        return CCTLD_TO_ISO.get(tld, tld.upper()), "the country-code domain"
    numbers: dict[str, str] = {}
    where: dict[str, set[str]] = {}
    for doc in docs:
        for cand in _phones(doc):
            if not str(cand.value).startswith("+"):
                continue
            try:
                region = phonenumbers.region_code_for_number(phonenumbers.parse(cand.value, None))
            except phonenumbers.NumberParseException:
                continue
            if region and region != "ZZ":
                numbers[cand.value] = region
                where.setdefault(region, set()).add(doc.url)
    if len(set(numbers.values())) == 1:  # a contact page listing several countries is an office directory
        (iso,) = set(numbers.values())
        return iso, f"{len(numbers)} phone number(s) on {', '.join(sorted(where[iso]))}"
    if numbers:
        return None, ""
    return national_numbers_country(docs, wanted)


def national_numbers_country(docs: list[PageDoc], wanted: list[str] | tuple[str, ...]) -> tuple[str | None, str]:
    """A company's own pages often write their numbers the way callers inside the country dial them ("020 7946
    0000", "(800) 555-0199"): such a number says where it is when it is a valid number of one requested country
    and of no other requested country. Lick's and Emerald Technology's UK numbers were all written like that, so
    they were left out as "not confirmed" (measured 2026-10-26)."""
    found: dict[str, set[str]] = {}
    where: dict[str, set[str]] = {}
    for doc in docs:
        raws = [unquote(a.attributes.get("href") or "")[4:].split("/")[0].strip()
                for a in doc.tree.css('a[href^="tel:"]')]
        for region in wanted:
            if region not in phonenumbers.SUPPORTED_REGIONS:
                continue
            nums = []
            for raw in raws:
                if raw and not raw.startswith("+"):
                    try:
                        nums.append(phonenumbers.parse(raw, region))
                    except phonenumbers.NumberParseException:
                        continue
            nums += [m.number for m in phonenumbers.PhoneNumberMatcher(doc.text[:50_000], region,
                                                                        leniency=phonenumbers.Leniency.VALID)
                     if not m.raw_string.lstrip().startswith("+")]
            for num in nums:
                if phonenumbers.is_valid_number_for_region(num, region):
                    found.setdefault(region, set()).add(
                        phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164))
                    where.setdefault(region, set()).add(doc.url)
    if len(found) == 1:
        ((iso, nums),) = found.items()
        return iso, f"{len(nums)} phone number(s) written in {iso} national format on {', '.join(sorted(where[iso]))}"
    return None, ""


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


def off_topic_reason(doc: PageDoc, spec: ExtractionSpec, check_country: bool = True,
                     subject: str | None = None) -> str | None:
    """Why this search result's homepage is not a match, or None to keep it. `subject` overrides what the
    homepage must be about (the question's industry, then its keywords)."""
    d = spec.discovery
    subject = (d.industry or " ".join(d.keywords)) if subject is None else subject
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
