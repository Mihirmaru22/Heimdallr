"""Hybrid Search Provider for Argus.

Combines DuckDuckGo (for directory, company, and Wikipedia specs) and
Google News RSS (for high-speed local press, executive appointments, and breaking news)
into a unified, resilient, zero-key search architecture.
"""

import asyncio
import logging
import time
from typing import Any
from urllib.parse import urlparse

from argus.search.duckduckgo import DuckDuckGoSearchProvider
from argus.search.fourchan import FourChanSearchProvider
from argus.search.google_news import GoogleNewsRSSSearchProvider
from argus.search.linkedin import LinkedInSearchProvider
from argus.search.models import SearchQuery, SearchResponse, SearchResult
from argus.search.provider import SearchProvider

logger = logging.getLogger(__name__)

# Keywords indicating personnel, leadership, or recent operational changes
NEWS_INTENT_KEYWORDS = {
    "director",
    "manager",
    "lead",
    "head",
    "chief",
    "executive",
    "appointed",
    "named",
    "retired",
    "fired",
    "hire",
    "hired",
    "layoff",
    "layoffs",
    "idled",
    "strike",
    "invest",
    "investment",
    "expansion",
    "retool",
    "retooling",
    "transition",
    "status",
    "restart",
}

LEADERSHIP_KEYWORDS = {
    "director",
    "manager",
    "lead",
    "head",
    "chief",
    "engineer",
    "superintendent",
    "plant_head",
    "tech_lead",
}

FORUM_KEYWORDS = {
    "rumor",
    "leak",
    "discussion",
    "layoff",
    "strike",
    "workers",
    "insider",
    "forum",
}


class HybridSearchProvider(SearchProvider):
    """Orchestrates DuckDuckGo, Google News RSS, LinkedIn, and 4chan in parallel with cross-engine deduplication."""

    def __init__(
        self,
        ddg_provider: SearchProvider | None = None,
        google_news_provider: SearchProvider | None = None,
        linkedin_provider: SearchProvider | None = None,
        fourchan_provider: SearchProvider | None = None,
        parallel_leadership_search: bool = True,
        enable_social_intelligence: bool = True,
        ddg_max_concurrent: int = 2,
        timeout: float = 15.0,
    ) -> None:
        self.ddg = ddg_provider or DuckDuckGoSearchProvider(max_concurrent=ddg_max_concurrent, timeout=timeout)
        self.news = google_news_provider or GoogleNewsRSSSearchProvider()
        self.enable_social = enable_social_intelligence
        self.linkedin = linkedin_provider or (LinkedInSearchProvider(search_backend=self.ddg, timeout=timeout) if self.enable_social else None)
        self.fourchan = fourchan_provider or (FourChanSearchProvider(timeout=min(timeout, 8.0)) if self.enable_social else None)
        self.parallel_leadership_search = parallel_leadership_search

    async def search(self, query: SearchQuery) -> SearchResponse:
        """Execute hybrid search fusing DuckDuckGo, Google News RSS, LinkedIn, and 4chan."""
        start_time = time.perf_counter()
        query_text = query.query.strip()
        if not query_text:
            return SearchResponse(
                query=query.query,
                results=[],
                total_results=0,
                execution_time_ms=0.0,
            )

        # Check intent
        words = {w.lower().strip(".,;:?!'\"()[]{}") for w in query_text.split()}
        has_news_intent = bool(words & NEWS_INTENT_KEYWORDS)
        has_leadership_intent = bool(words & LEADERSHIP_KEYWORDS)
        has_forum_intent = bool(words & FORUM_KEYWORDS)

        # Determine strategy
        if self.parallel_leadership_search or has_news_intent or has_leadership_intent:
            tasks: list[asyncio.Task | Any] = [
                self.ddg.search(
                    SearchQuery(query=query_text, num_results=max(3, query.num_results // 2))
                ),
                self.news.search(
                    SearchQuery(query=query_text, num_results=max(3, query.num_results // 2))
                ),
            ]

            # If leadership intent detected, trigger real-time LinkedIn targeted scraper
            query_linkedin = has_leadership_intent and self.linkedin is not None
            if query_linkedin and self.linkedin is not None:
                tasks.append(
                    self.linkedin.search(
                        SearchQuery(query=query_text, num_results=max(2, query.num_results // 3))
                    )
                )

            # If forum/leak intent detected, trigger real-time 4chan scraper
            query_4chan = has_forum_intent and self.fourchan is not None
            if query_4chan and self.fourchan is not None:
                tasks.append(
                    self.fourchan.search(
                        SearchQuery(query=query_text, num_results=max(2, query.num_results // 3))
                    )
                )

            responses = await asyncio.gather(*tasks, return_exceptions=True)

            ddg_resp = responses[0] if isinstance(responses[0], SearchResponse) else None
            news_resp = responses[1] if isinstance(responses[1], SearchResponse) else None
            
            li_idx = 2 if query_linkedin else None
            li_resp = responses[li_idx] if (li_idx is not None and isinstance(responses[li_idx], SearchResponse)) else None

            fc_idx = (3 if query_linkedin else 2) if query_4chan else None
            fc_resp = responses[fc_idx] if (fc_idx is not None and isinstance(responses[fc_idx], SearchResponse)) else None

            primary: list[SearchResult] = []
            secondary: list[SearchResult] = []

            # Prioritize LinkedIn for leadership roles, News for recent events, DDG for broad directories
            if li_resp and li_resp.results:
                primary.extend(li_resp.results)
            if news_resp and news_resp.results:
                if has_news_intent:
                    primary.extend(news_resp.results)
                else:
                    secondary.extend(news_resp.results)
            if ddg_resp and ddg_resp.results:
                if not has_news_intent:
                    primary.extend(ddg_resp.results)
                else:
                    secondary.extend(ddg_resp.results)
            if fc_resp and fc_resp.results:
                secondary.extend(fc_resp.results)

            merged_results = self._merge_and_deduplicate(
                primary=primary,
                secondary=secondary,
                max_results=query.num_results,
            )

        else:
            # Default to DuckDuckGo with Google News as fallback if DDG returns 0
            ddg_resp = await self.ddg.search(query)
            if ddg_resp.results:
                merged_results = ddg_resp.results[: query.num_results]
            else:
                logger.info("DDG yielded 0 results; falling back to Google News RSS for '%s'", query_text)
                news_resp = await self.news.search(query)
                merged_results = news_resp.results[: query.num_results]

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return SearchResponse(
            query=query.query,
            results=merged_results,
            total_results=len(merged_results),
            execution_time_ms=elapsed_ms,
        )

    def _merge_and_deduplicate(
        self,
        primary: list[SearchResult],
        secondary: list[SearchResult],
        max_results: int,
    ) -> list[SearchResult]:
        """Interleave and deduplicate results from both providers."""
        merged: list[SearchResult] = []
        seen_urls: set[str] = set()
        seen_titles: set[str] = set()

        def _normalize_title(t: str) -> str:
            return "".join(c.lower() for c in t if c.isalnum())[:30]

        def _normalize_url(u: str) -> str:
            p = urlparse(u.strip().lower())
            return f"{p.netloc}{p.path}".rstrip("/")

        # Interleave primary and secondary
        max_len = max(len(primary), len(secondary))
        for i in range(max_len):
            for group in (primary, secondary):
                if i < len(group):
                    item = group[i]
                    norm_url = _normalize_url(item.url)
                    norm_title = _normalize_title(item.title)

                    if norm_url in seen_urls or (norm_title and norm_title in seen_titles):
                        continue

                    seen_urls.add(norm_url)
                    if norm_title:
                        seen_titles.add(norm_title)
                    merged.append(item)

                    if len(merged) >= max_results:
                        return merged
        return merged[:max_results]

    async def close(self) -> None:
        """Close child providers safely and idempotently."""
        for provider in (self.fourchan, self.linkedin, self.news, self.ddg):
            if provider is not None and hasattr(provider, "close") and callable(provider.close):
                try:
                    res = provider.close()
                    if asyncio.iscoroutine(res):
                        await res
                except Exception as exc:
                    logger.debug("Error closing provider %s: %s", provider, exc)

