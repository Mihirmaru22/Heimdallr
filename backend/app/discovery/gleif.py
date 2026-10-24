"""GLEIF discovery: legal entities worldwide from the Global Legal Entity Identifier register.

GLEIF's API is free, needs no key and allows 60 requests a minute. Every company that trades in regulated
markets has an LEI, in every country, with its registered legal name, headquarters address and status.
It does not record industries or websites, so this source searches legal names for the industry word
("pharmaceutical" finds "Sun Pharmaceutical Industries Ltd") within the requested countries, keeps active
operating companies (not funds or branches), and takes each one's website from the Wikidata item that
carries its LEI (P1278). Its own contribution to a record is the verified legal name and address.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx

from app.config import get_settings
from app.crawl.urlnorm import normalize_url, registered_domain
from app.discovery.providers import (
    COUNTRY_QIDS,
    REGION_COUNTRIES,
    WIKIDATA_API,
    DiscoveryError,
    DiscoveryResult,
    WikidataProvider,
    wd_founded,
    wd_label,
)
from app.spec.models import ExtractionSpec
from app.spec.spelling import spellings, to_us

API = "https://api.gleif.org/api/v1/lei-records"
PAGE_SIZE = 200  # GLEIF's maximum
PAGES_PER_WORD = 3
REQUEST_GAP = 1.1  # seconds; GLEIF allows 60 requests a minute
# Words companies put in their legal names for an industry ("Pfizer Pharmaceuticals LLC", "Acme Bank AG").
NAME_WORDS = {
    "pharmaceutical": ["pharmaceutical", "pharmaceuticals", "pharma"], "pharma": ["pharma", "pharmaceuticals"],
    "biotech": ["biotech", "biotechnology", "biosciences", "therapeutics"],
    "biotechnology": ["biotechnology", "biotech", "biosciences"],
    "software": ["software", "technologies"], "tech": ["technologies", "technology", "software"],
    "technology": ["technologies", "technology", "software"], "banking": ["bank"], "bank": ["bank"],
    "insurance": ["insurance", "assurance"], "logistics": ["logistics"], "automotive": ["automotive", "motors"],
    "cybersecurity": ["cybersecurity", "cyber"], "semiconductors": ["semiconductor", "semiconductors"],
    "defense": ["defense", "defence", "aerospace"],
}
SKIP_CATEGORIES = {"FUND", "BRANCH", "SOLE_PROPRIETOR"}
FUND_NAME_RE = re.compile(r"\b(fund|funds|fonds|sicav|trust|etf|portfolio|pension|spv|securiti[sz]ation)\b", re.I)
WIKIDATA_BATCH = 10  # LEIs per Wikidata search; search queries are limited to about 300 characters


def name_words(industry: str) -> list[str]:
    term = to_us(industry.lower().strip())
    if term in NAME_WORDS:
        return NAME_WORDS[term]
    words = [v for w in re.findall(r"[a-z]+", term) if len(w) >= 3 for v in spellings(w)]
    return list(dict.fromkeys(words + [w + "s" for w in words if not w.endswith("s")]))[:4]


def _address(addr: dict[str, Any] | None) -> tuple[str, str]:
    """(full address, "City, Region") from a GLEIF address block."""
    addr = addr or {}
    city = (addr.get("city") or "").strip()
    region = (addr.get("region") or "").split("-")[-1].strip()  # "US-NY" -> "NY"
    lines = [ln.strip() for ln in addr.get("addressLines") or [] if ln and ln.strip()]
    full = ", ".join([*lines, *(x for x in (city, region, addr.get("postalCode"), addr.get("country")) if x)])
    return full, ", ".join(x for x in (city.title() if city.isupper() else city, region) if x)


def _entity(record: dict[str, Any]) -> dict[str, Any] | None:
    attrs = record.get("attributes") or {}
    ent = attrs.get("entity") or {}
    if ent.get("status") != "ACTIVE" or ent.get("category") in SKIP_CATEGORIES:
        return None
    name = ((ent.get("legalName") or {}).get("name") or "").strip()
    if not name or FUND_NAME_RE.search(name):
        return None
    hq = ent.get("headquartersAddress") or ent.get("legalAddress") or {}
    full, locality = _address(hq)
    return {"lei": attrs.get("lei") or record.get("id"), "name": name, "country": (hq.get("country") or "").upper(),
            "address": full, "headquarters": locality}


class GleifProvider:
    name = "gleif"

    def __init__(self, client: httpx.AsyncClient | None = None, gap: float = REQUEST_GAP) -> None:
        self.client = client
        self.gap = gap
        self.notes: list[str] = []

    async def _search(self, client: httpx.AsyncClient, word: str, countries: list[str]) -> list[dict[str, Any]]:
        out = []
        for page in range(1, PAGES_PER_WORD + 1):
            params = {"filter[fulltext]": word, "filter[entity.status]": "ACTIVE",
                      "page[size]": PAGE_SIZE, "page[number]": page}
            if countries:
                params["filter[entity.legalAddress.country]"] = ",".join(countries)
            resp = await client.get(API, params=params, headers={"Accept": "application/vnd.api+json"})
            if resp.status_code == 429:
                await asyncio.sleep(60)
                resp = await client.get(API, params=params, headers={"Accept": "application/vnd.api+json"})
            resp.raise_for_status()
            body = resp.json()
            out += [e for e in (_entity(r) for r in body.get("data") or []) if e]
            last = ((body.get("meta") or {}).get("pagination") or {}).get("lastPage") or page
            if page >= last:
                break
            await asyncio.sleep(self.gap)
        return out

    async def from_wikidata(self, client: httpx.AsyncClient, leis: list[str]) -> dict[str, dict[str, Any]]:
        """LEI -> website and label of the Wikidata item carrying that LEI (P1278)."""
        wd = WikidataProvider(client)
        found: dict[str, dict[str, Any]] = {}
        for i in range(0, len(leis), WIKIDATA_BATCH):
            query = "haswbstatement:" + "|".join(f"P1278={lei}" for lei in leis[i:i + WIKIDATA_BATCH])
            resp = await client.get(WIKIDATA_API, params={
                "action": "query", "list": "search", "srsearch": query, "srnamespace": 0, "srlimit": 50,
                "srprop": "", "format": "json"})
            resp.raise_for_status()
            qids = [h["title"] for h in resp.json().get("query", {}).get("search", [])]
            if not qids:
                continue
            for e in (await wd._entities(client, qids, "labels|claims")).values():
                info = {"website": next((u for u in (normalize_url(w) for w in wd._claim_ids(e, "P856")) if u), ""),
                        "label": wd_label(e) or "", "founded_year": wd_founded(e)}
                for lei in wd._claim_ids(e, "P1278"):
                    found.setdefault(lei.upper(), info)
        return found

    async def discover(self, spec: ExtractionSpec) -> list[DiscoveryResult]:
        d = spec.discovery
        if not d.industry:
            raise DiscoveryError("GLEIF discovery needs an industry (it searches company names for it)")
        countries = d.countries or REGION_COUNTRIES.get(d.region or "", [])
        client = self.client or httpx.AsyncClient(timeout=30, headers={"User-Agent": get_settings().user_agent})
        try:
            entities: dict[str, dict[str, Any]] = {}
            try:
                for word in name_words(d.industry):
                    for e in await self._search(client, word, countries):
                        entities.setdefault(e["lei"], e)
                    if len(entities) >= d.max_results * 6:
                        break
                    await asyncio.sleep(self.gap)
            except httpx.HTTPStatusError as exc:
                if not entities:
                    raise DiscoveryError(f"GLEIF search failed (HTTP {exc.response.status_code})") from exc
                self.notes.append(f"gleif: search stopped early (HTTP {exc.response.status_code})")
            except httpx.HTTPError as exc:
                if not entities:
                    raise DiscoveryError(f"GLEIF could not be reached ({type(exc).__name__})") from exc
            if not entities:
                raise DiscoveryError(f"GLEIF has no active companies with {d.industry!r} in their name here")
            try:
                wiki = await self.from_wikidata(client, list(entities))
            except httpx.HTTPError as exc:
                raise DiscoveryError(f"Wikidata website lookup for GLEIF companies failed "
                                     f"({type(exc).__name__})") from exc
        finally:
            if self.client is None:
                await client.aclose()
        out: list[DiscoveryResult] = []
        seen: set[str] = set()
        for lei, e in entities.items():
            info = wiki.get(lei.upper())
            if not info or not info["website"]:
                continue
            domain = registered_domain(info["website"]) or info["website"]
            if domain in seen:  # subsidiaries of one group often share the group's website
                continue
            seen.add(domain)
            source = f"https://search.gleif.org/#/record/{lei}"
            country = COUNTRY_QIDS.get(e["country"], ("", e["country"]))[1]
            hint = {"company_name": info["label"] or e["name"], "legal_name": e["name"], "lei": lei,
                    "headquarters": e["headquarters"], "address": e["address"], "country": country,
                    "website_url": info["website"], "founded_year": info.get("founded_year"), "_source": source}
            out.append(DiscoveryResult(info["website"], "gleif", {k: v for k, v in hint.items() if v},
                                       referrer=source))
            if len(out) >= d.max_results:
                break
        missing = len(entities) - len(wiki)
        if missing > 0:
            self.notes.append(f"gleif: {missing} matching companies have no known website and were left out")
        if not out:
            raise DiscoveryError("none of the matching GLEIF companies has a known website")
        return out
