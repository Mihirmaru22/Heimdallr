"""DuckDuckGo search provider for live web search without API keys.

Uses the `ddgs` package to query DuckDuckGo's organic results.
Supports multi-worker concurrency limiting and multi-backend fallback ('lite', 'api', 'html').
"""

import asyncio
import logging
import random
import time
from urllib.parse import parse_qs, unquote, urlparse

from ddgs import DDGS

from argus.search.models import SearchQuery, SearchResponse, SearchResult
from argus.search.provider import SearchProvider

logger = logging.getLogger(__name__)


class DuckDuckGoSearchProvider(SearchProvider):
    """Live web search via DuckDuckGo with pooled concurrency and multi-backend rotation."""

    def __init__(
        self,
        timeout: float = 15.0,
        max_concurrent: int = 2,
        min_interval_seconds: float = 0.5,
    ) -> None:
        self.timeout = timeout
        self.max_concurrent = max_concurrent
        self.min_interval = min_interval_seconds
        self._semaphore: asyncio.Semaphore | None = None
        self._last_call_time = 0.0

    def _get_semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.max_concurrent)
        return self._semaphore

    async def search(self, query: SearchQuery) -> SearchResponse:
        """Execute a DuckDuckGo text search with VCR caching support."""
        from argus.utils.vcr import VCRProxy
        
        async def _do_search():
            return await self._search_impl(query)
            
        return await VCRProxy.search(query.query, _do_search)

    async def _search_impl(self, query: SearchQuery) -> SearchResponse:
        """Execute a DuckDuckGo text search under concurrency guard."""
        start_time = time.perf_counter()
        query_text = query.query.strip()
        if not query_text:
            return SearchResponse(
                query=query.query,
                results=[],
                total_results=0,
                execution_time_ms=0.0,
            )

        sem = self._get_semaphore()
        async with sem:
            # Pacing delay between calls to preserve single-IP health
            now = time.time()
            elapsed_since_last = now - self._last_call_time
            if elapsed_since_last < self.min_interval:
                jitter = random.uniform(0.05, 0.2)
                await asyncio.sleep((self.min_interval - elapsed_since_last) + jitter)
            self._last_call_time = time.time()

            loop = asyncio.get_event_loop()
            raw_results = await loop.run_in_executor(
                None,
                self._sync_search,
                query_text,
                query.num_results,
            )

        parsed: list[SearchResult] = []
        for idx, r in enumerate(raw_results):
            url = r.get("href") or r.get("link", "")
            title = r.get("title", "")
            snippet = r.get("body", "")
            if not url or not title:
                continue

            # Unwrap DuckDuckGo redirect wrapper if present
            if "uddg=" in url:
                qs = parse_qs(urlparse(url).query)
                if "uddg" in qs and qs["uddg"]:
                    url = unquote(qs["uddg"][0])

            score = max(0.4, 0.95 - (idx * 0.05))
            parsed.append(
                SearchResult(
                    url=url,
                    title=title.strip(),
                    snippet=snippet.strip(),
                    engine="duckduckgo",
                    score=round(score, 3),
                )
            )

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return SearchResponse(
            query=query.query,
            results=parsed,
            total_results=len(parsed),
            execution_time_ms=elapsed_ms,
        )

    def _sync_search(self, query: str, max_results: int) -> list[dict]:
        """Synchronous DuckDuckGo search trying 'lite' first, then 'api' and 'html'."""
        # Prioritize 'lite' as it has the lowest rate-limiting profile
        backends = ("lite", "api", "html")
        for backend in backends:
            try:
                ddgs = DDGS(timeout=int(self.timeout))
                results = list(
                    ddgs.text(query, backend=backend, max_results=max_results)
                )
                if results:
                    return results
            except Exception as exc:
                logger.debug(
                    "DDG backend '%s' failed for '%s': %s",
                    backend,
                    query,
                    exc,
                )
                continue
        return []
