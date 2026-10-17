"""Wikipedia search through the official MediaWiki API (free, no key).

Wikipedia asks API clients to send a descriptive User-Agent with contact details
(https://meta.wikimedia.org/wiki/User-Agent_policy); set HEIMDALLR_CONTACT to an email
or URL to include one.
"""

from __future__ import annotations

import html
import logging
import os
import re
import time
from urllib.parse import quote

from argus.search.models import SearchQuery, SearchResponse, SearchResult
from argus.search.pipeline import create_safe_async_client
from argus.search.provider import SearchProvider

logger = logging.getLogger(__name__)


def research_user_agent() -> str:
    contact = os.environ.get("HEIMDALLR_CONTACT", "").strip()
    return f"Heimdallr-Research/4.0 ({contact})" if contact else "Heimdallr-Research/4.0"


class WikipediaSearchProvider(SearchProvider):
    """Full-text article search on one Wikipedia language edition."""

    def __init__(self, language: str = "en", timeout: float = 10.0) -> None:
        self.language = language
        self.timeout = timeout
        self.endpoint = f"https://{language}.wikipedia.org/w/api.php"

    async def search(self, query: SearchQuery) -> SearchResponse:
        start = time.perf_counter()
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query.query,
            "srlimit": str(min(query.num_results, 20)),
            "format": "json",
            "utf8": "1",
        }
        results: list[SearchResult] = []
        try:
            async with create_safe_async_client(timeout=self.timeout, headers={"User-Agent": research_user_agent()}) as client:
                resp = await client.get(self.endpoint, params=params)
                resp.raise_for_status()
                data = resp.json()
            results = self.parse(data)
        except Exception as exc:
            logger.warning("Wikipedia search failed for '%s': %s", query.query, exc)
        return SearchResponse(
            query=query.query,
            results=results,
            total_results=len(results),
            execution_time_ms=(time.perf_counter() - start) * 1000.0,
        )

    def parse(self, data: dict) -> list[SearchResult]:
        out: list[SearchResult] = []
        for idx, item in enumerate(((data or {}).get("query") or {}).get("search") or []):
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            snippet = html.unescape(re.sub(r"<[^>]+>", "", str(item.get("snippet") or "")))
            out.append(SearchResult(
                url=f"https://{self.language}.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}",
                title=title,
                snippet=" ".join(snippet.split()),
                engine="wikipedia",
                score=round(max(0.4, 0.9 - idx * 0.05), 3),
            ))
        return out
