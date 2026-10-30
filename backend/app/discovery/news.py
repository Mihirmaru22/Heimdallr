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
from app.discovery.case_studies import CaseStudiesProvider
from app.discovery.providers import NOT_COMPANY_SITES, DiscoveryError
from app.evidence.products import Product

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
WINDOW = timedelta(days=90)  # GDELT lists at most 3 months per search
PER_WINDOW = 75  # articles asked for per window
WANT = 60  # articles gathered before reading; reading then stops on coverage (case_studies.PLATEAU)
PAUSE = 5.0  # seconds between requests, as GDELT asks
WINDOW_TRIES = 3  # requests per 3-month window when GDELT says "limit requests to one every 5 seconds"
TURN_KEY = "webdata:gdelt:turn"


async def gdelt_turn(pause: float) -> None:
    """Wait until this process may send the next GDELT request. GDELT counts requests per address, and the jobs
    of every worker share one: a pause per job still had 13 of 20 requests refused with two jobs running. The
    turn is kept in Redis for all workers; without Redis, the pause alone applies."""
    if pause <= 0:
        return
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(get_settings().redis_url, socket_timeout=2)
        try:
            for _ in range(int(pause * 60)):  # gives up after about a minute of other jobs' turns
                if await r.set(TURN_KEY, "1", nx=True, px=int(pause * 1000)):
                    return
                await asyncio.sleep(0.5)
            return
        finally:
            await r.aclose()
    except Exception:  # noqa: BLE001 - Redis down: fall back to this job's own pause
        await asyncio.sleep(pause)


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
    publisher = "news"
    open_ended = False  # at most WANT articles are gathered: it needs a bounded share, then hands the rest on

    def __init__(self, *args, gdelt_url: str = GDELT_URL, years: int | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.gdelt_url = gdelt_url
        self.years = years
        self.now = lambda: datetime.now(UTC)

    async def search(self, client: httpx.AsyncClient, product: Product) -> list[str]:
        query = gdelt_query(product)
        years = self.years or 3
        pause = PAUSE if get_settings().env != "test" else 0
        urls: list[str] = []
        titles: set[str] = set()
        end = self.now()
        oldest = end - timedelta(days=365 * years)
        asked = 0
        while end > oldest and len(urls) < WANT:
            start = max(oldest, end - WINDOW)
            params = {"query": query, "mode": "artlist", "format": "json", "maxrecords": PER_WINDOW,
                      "sort": "hybridrel", "startdatetime": f"{start:%Y%m%d%H%M%S}",
                      "enddatetime": f"{end:%Y%m%d%H%M%S}"}
            try:
                for attempt in range(WINDOW_TRIES):
                    if asked:
                        await gdelt_turn(pause)
                    asked += 1
                    resp = await client.get(self.gdelt_url, params=params)
                    if resp.status_code != 429:
                        break
                    # Refused for asking too often (another job asked moments ago): wait and ask the same
                    # window again, instead of losing three months of articles.
                    if attempt + 1 < WINDOW_TRIES:
                        await asyncio.sleep(pause * 2)
            except httpx.HTTPError as exc:
                if urls:
                    break
                raise DiscoveryError(f"GDELT is not reachable ({type(exc).__name__})") from None
            end = start
            try:
                articles = resp.json().get("articles", []) if resp.status_code == 200 else None
            except ValueError:  # GDELT answers errors ("phrase too short", "limit requests") as plain text
                articles = None
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
                urls.append(url)
                titles.add(title)
                self.meta.setdefault(url, (a.get("title") or "", ""))
                self.dates[url] = seen_date(a.get("seendate", ""))
        return urls

    async def _context(self, product, d):
        return []  # GDELT is searched by the product's names alone

    async def discover(self, spec):
        self.years = self.years or spec.discovery.evidence_years
        return await super().discover(spec)
