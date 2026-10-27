"""news: organisations that news and trade-press articles show using a technology.

"Ford rolls out SAP S/4HANA across its plants" is reported by the press long before (or instead of) the
company's own pages saying so. Articles are found in GDELT's DOC 2.0 index (free, no key: worldwide news,
updated every 15 minutes, back to 2017) by the product's names; no list of outlets is kept. GDELT lists at
most the latest 3 months of any search, so the years asked for are searched one 3-month window at a time,
newest first, one request every 5 seconds as GDELT asks. Every article is then read exactly like a case study
(app.discovery.case_studies): fetched like any crawled page (robots.txt respected), its sentences naming the
product cut out word for word, and one free model call says which organisations it shows using the product.
"""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime, timedelta

import httpx

from app.config import get_settings
from app.crawl.urlnorm import normalize_url, registered_domain
from app.discovery.case_studies import MAX_PAGES, CaseStudiesProvider
from app.discovery.providers import NOT_COMPANY_SITES, DiscoveryError
from app.evidence.products import Product
from app.search import Hit

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
WINDOW = timedelta(days=90)  # GDELT lists at most 3 months per search
PER_WINDOW = 75  # articles asked for per window
WANT = MAX_PAGES * 2  # candidates gathered before reading (some cannot be read or name nobody)
PAUSE = 5.0  # seconds between requests, as GDELT asks
# GDELT refuses a window with 429 / "limit requests" when another job on this address asked too recently (13 of
# set 1's 20 windows). Such a window is asked again after a longer pause instead of being skipped.
REFUSED_RETRIES = 2
REFUSED_PAUSE = 15.0


def gdelt_query(product: Product) -> str:
    """("SAP S/4HANA" OR "S4HANA"): GDELT rejects phrases under 3 characters and wants OR inside brackets."""
    names = list(dict.fromkeys(n for n in product.names if len(n) >= 4))[:3] or product.names[:1]
    quoted = [f'"{n}"' for n in names]
    return quoted[0] if len(quoted) == 1 else f"({' OR '.join(quoted)})"


def seen_date(value: str) -> str:
    """GDELT's "20250602T101500Z" -> "2025-06-02"."""
    m = re.match(r"(\d{4})(\d{2})(\d{2})", value or "")
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


class NewsProvider(CaseStudiesProvider):
    name = "news"
    what = "news articles"

    def __init__(self, *args, gdelt_url: str = GDELT_URL, years: int | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.gdelt_url = gdelt_url
        self.years = years
        self.now = lambda: datetime.now(UTC)

    async def search(self, client: httpx.AsyncClient, product: Product, places: list[str] | None = None,
                     countries: list[str] | None = None) -> list[str]:
        query = gdelt_query(product)
        years = self.years or 3
        test = get_settings().env == "test"
        pause = PAUSE if not test else 0
        hits: list[Hit] = []
        urls: set[str] = set()
        titles: set[str] = set()
        end = self.now()
        oldest = end - timedelta(days=365 * years)
        asked = 0
        refused = 0
        while end > oldest and len(hits) < WANT:
            start = max(oldest, end - WINDOW)
            if asked:
                await asyncio.sleep(pause)
            asked += 1
            try:
                resp = await client.get(self.gdelt_url, params={
                    "query": query, "mode": "artlist", "format": "json", "maxrecords": PER_WINDOW,
                    "sort": "hybridrel", "startdatetime": f"{start:%Y%m%d%H%M%S}",
                    "enddatetime": f"{end:%Y%m%d%H%M%S}"})
            except httpx.HTTPError as exc:
                if hits:
                    break
                raise DiscoveryError(f"GDELT is not reachable ({type(exc).__name__})") from None
            try:
                articles = resp.json().get("articles", []) if resp.status_code == 200 else None
            except ValueError:  # GDELT answers errors ("phrase too short", "limit requests") as plain text
                articles = None
            busy = resp.status_code == 429 or "limit requests" in resp.text[:300].lower()
            if articles is None and busy and refused < REFUSED_RETRIES:
                refused += 1
                await asyncio.sleep(REFUSED_PAUSE * refused if not test else 0)
                continue  # the same window again
            refused = 0
            end = start
            if articles is None:
                self.notes.append(f"news: GDELT refused one search window ({resp.status_code}: "
                                  f"{resp.text[:120].strip()})")
                continue
            for a in articles:
                url = normalize_url(a.get("url", ""))
                site = registered_domain(url) if url else ""
                title = " ".join((a.get("title") or "").lower().split())
                if not url or not site or site in NOT_COMPANY_SITES or url in urls or (title and title in titles):
                    continue  # syndicated copies carry the same title
                urls.add(url)
                titles.add(title)
                hits.append(Hit(url, a.get("title") or "", "", "gdelt"))
                self.dates[url] = seen_date(a.get("seendate", ""))
        return self._order(hits, places, countries)

    async def _context(self, product, d):
        return []  # GDELT is searched by the product's names alone

    async def discover(self, spec):
        self.years = self.years or spec.discovery.evidence_years
        return await super().discover(spec)
