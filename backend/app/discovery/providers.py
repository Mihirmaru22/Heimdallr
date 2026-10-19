"""Discovery providers: where the first URLs of a job come from.

- seeds: URLs and domains the user typed (always available).
- wikidata: organizations from Wikidata (CC0) with an official website (P856), filtered by
  industry (P452) and country (P17 / P30 continent). Free, no key; please keep queries small.
Each result is a URL plus optional hints (name, headquarters...) that become candidate values
with method "wikidata", so the record shows where they came from.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.config import get_settings
from app.crawl.urlnorm import normalize_url
from app.spec.models import ExtractionSpec

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
CONTINENTS = {"europe": "Q46", "north_america": "Q49", "asia": "Q48", "africa": "Q15", "south_america": "Q18",
              "oceania": "Q55643"}
ISO2_RE = re.compile(r"^[A-Z]{2}$")
QID_RE = re.compile(r"^Q\d{1,12}$")


@dataclass
class DiscoveryResult:
    url: str
    method: str
    hint: dict[str, Any] = field(default_factory=dict)
    referrer: str | None = None


class DiscoveryError(Exception):
    pass


class DiscoveryProvider(Protocol):
    name: str

    async def discover(self, spec: ExtractionSpec) -> list[DiscoveryResult]: ...


class SeedProvider:
    name = "seeds"

    async def discover(self, spec: ExtractionSpec) -> list[DiscoveryResult]:
        out: list[DiscoveryResult] = []
        for raw in spec.crawl.start_urls + [f"https://{d}/" for d in spec.crawl.allowed_domains]:
            url = normalize_url(raw if "://" in raw else f"https://{raw}")
            if url and all(r.url != url for r in out):
                out.append(DiscoveryResult(url, "seed"))
        return out


class WikidataProvider:
    name = "wikidata"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self.client = client

    def _client(self) -> httpx.AsyncClient:
        return self.client or httpx.AsyncClient(
            timeout=30, headers={"User-Agent": get_settings().user_agent}, follow_redirects=False
        )

    async def industry_ids(self, client: httpx.AsyncClient, industry: str) -> list[str]:
        resp = await client.get(WIKIDATA_API, params={
            "action": "wbsearchentities", "search": industry[:100], "language": "en", "type": "item",
            "limit": 5, "format": "json",
        })
        resp.raise_for_status()
        return [r["id"] for r in resp.json().get("search", []) if QID_RE.match(r.get("id", ""))][:3]

    @staticmethod
    def build_query(industry_ids: list[str], countries: list[str], region: str | None, limit: int) -> str:
        lines = ["SELECT DISTINCT ?org ?orgLabel ?website ?hqLabel ?countryLabel WHERE {"]
        if industry_ids:
            values = " ".join(f"wd:{q}" for q in industry_ids if QID_RE.match(q))
            lines.append(f"  VALUES ?industry {{ {values} }}")
            lines.append("  ?org wdt:P452 ?industry .")
        lines.append("  ?org wdt:P856 ?website .")
        lines.append("  ?org wdt:P17 ?country .")
        isos = [c for c in countries if ISO2_RE.match(c)]
        if isos:
            lines.append("  ?country wdt:P297 ?iso .")
            lines.append("  VALUES ?iso { " + " ".join(f'"{c}"' for c in isos) + " }")
        elif region in CONTINENTS:
            lines.append(f"  ?country wdt:P30 wd:{CONTINENTS[region]} .")
        lines.append("  OPTIONAL { ?org wdt:P159 ?hq . }")
        lines.append("  FILTER NOT EXISTS { ?org wdt:P576 ?dissolved . }")
        lines.append('  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }')
        lines.append(f"}} LIMIT {int(limit)}")
        return "\n".join(lines)

    async def discover(self, spec: ExtractionSpec) -> list[DiscoveryResult]:
        d = spec.discovery
        if not (d.industry or d.countries or d.region):
            raise DiscoveryError("Wikidata discovery needs an industry, countries or a region")
        client = self._client()
        try:
            ids = await self.industry_ids(client, d.industry) if d.industry else []
            if d.industry and not ids:
                raise DiscoveryError(f"Wikidata has no item matching industry {d.industry!r}")
            query = self.build_query(ids, d.countries, d.region, d.max_results * 2)
            resp = await client.get(WIKIDATA_SPARQL, params={"query": query, "format": "json"},
                                    headers={"Accept": "application/sparql-results+json"})
            if resp.status_code == 429:
                raise DiscoveryError("Wikidata rate limit reached; try again later")
            resp.raise_for_status()
            rows = resp.json()["results"]["bindings"]
        except httpx.HTTPError as exc:
            raise DiscoveryError(f"Wikidata request failed: {type(exc).__name__}") from None
        finally:
            if self.client is None:
                await client.aclose()
        out: list[DiscoveryResult] = []
        seen: set[str] = set()
        for row in rows:
            url = normalize_url(row.get("website", {}).get("value", ""))
            if not url or url in seen:
                continue
            seen.add(url)
            org = row.get("org", {}).get("value", "")
            hint = {
                "company_name": row.get("orgLabel", {}).get("value"),
                "headquarters": row.get("hqLabel", {}).get("value"),
                "country": row.get("countryLabel", {}).get("value"),
                "website_url": url,
                "_source": org,
            }
            out.append(DiscoveryResult(url, "wikidata", {k: v for k, v in hint.items() if v}, referrer=org))
            if len(out) >= d.max_results:
                break
        return out


def providers_for(spec: ExtractionSpec) -> list[DiscoveryProvider]:
    registry: dict[str, DiscoveryProvider] = {"seeds": SeedProvider(), "wikidata": WikidataProvider()}
    return [registry[name] for name in spec.discovery.providers if name in registry]
