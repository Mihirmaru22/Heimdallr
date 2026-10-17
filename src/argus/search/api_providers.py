"""Search APIs with free tiers, used when the user has set a key.

These are the kind of index the big LLM tools search instead of scraping result pages: each
provider crawls the web itself and returns results through an official API, some with a page
extract. Free tiers (as checked 2026-10-17, see analysis/HEIMDALLR_free_sources_survey):
- Tavily: 1,000 credits per month, no card        (TAVILY_API_KEY)
- Exa: $10 of credit per month, no card           (EXA_API_KEY)
- Brave Search: $5 of credit per month, card needed (BRAVE_API_KEY)
A source without a key is simply not used.
"""

from __future__ import annotations

import time

from argus.search.models import SearchQuery, SearchResponse, SearchResult
from argus.search.pipeline import SearchPipeline, create_safe_async_client
from argus.search.provider import SearchProvider

MAX_EXTRACT_CHARS = 3000


def _response(query: SearchQuery, results: list[SearchResult], start: float) -> SearchResponse:
    return SearchResponse(query=query.query, results=results, total_results=len(results), execution_time_ms=(time.perf_counter() - start) * 1000.0)


def _result(url: str, title: str, text: str, engine: str, score: float = 0.0) -> SearchResult | None:
    if not url or not SearchPipeline.is_safe_url(url):
        return None
    return SearchResult(url=url, title=(title or url)[:300], snippet=" ".join((text or "").split())[:MAX_EXTRACT_CHARS], engine=engine, score=score)


class TavilySearchProvider(SearchProvider):
    def __init__(self, api_key: str, timeout: float = 15.0) -> None:
        self.api_key, self.timeout = api_key, timeout

    async def search(self, query: SearchQuery) -> SearchResponse:
        start = time.perf_counter()
        async with create_safe_async_client(timeout=self.timeout) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"query": query.query, "max_results": min(query.num_results, 20), "search_depth": "basic"},
            )
            resp.raise_for_status()
            data = resp.json()
        results = [_result(r.get("url", ""), r.get("title", ""), r.get("content", ""), "tavily", float(r.get("score") or 0)) for r in data.get("results", [])]
        return _response(query, [r for r in results if r], start)


class ExaSearchProvider(SearchProvider):
    def __init__(self, api_key: str, timeout: float = 15.0) -> None:
        self.api_key, self.timeout = api_key, timeout

    async def search(self, query: SearchQuery) -> SearchResponse:
        start = time.perf_counter()
        async with create_safe_async_client(timeout=self.timeout) as client:
            resp = await client.post(
                "https://api.exa.ai/search",
                headers={"x-api-key": self.api_key},
                json={"query": query.query, "numResults": min(query.num_results, 25), "contents": {"text": {"maxCharacters": MAX_EXTRACT_CHARS}}},
            )
            resp.raise_for_status()
            data = resp.json()
        results = [_result(r.get("url", ""), r.get("title") or "", r.get("text") or "", "exa", float(r.get("score") or 0)) for r in data.get("results", [])]
        return _response(query, [r for r in results if r], start)


class BraveSearchProvider(SearchProvider):
    def __init__(self, api_key: str, timeout: float = 15.0) -> None:
        self.api_key, self.timeout = api_key, timeout

    async def search(self, query: SearchQuery) -> SearchResponse:
        start = time.perf_counter()
        async with create_safe_async_client(timeout=self.timeout) as client:
            resp = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={"X-Subscription-Token": self.api_key, "Accept": "application/json"},
                params={"q": query.query, "count": min(query.num_results, 20)},
            )
            resp.raise_for_status()
            data = resp.json()
        items = (data.get("web") or {}).get("results", [])
        results = [_result(r.get("url", ""), r.get("title", ""), " ".join([r.get("description", "")] + list(r.get("extra_snippets") or [])), "brave") for r in items]
        return _response(query, [r for r in results if r], start)
