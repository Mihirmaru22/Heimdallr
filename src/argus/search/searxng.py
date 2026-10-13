import time

import httpx

from argus.search.models import SearchQuery, SearchResponse, SearchResult
from argus.search.pipeline import SearchPipeline, create_safe_async_client
from argus.search.provider import SearchProvider


class SearXNGSearchProvider(SearchProvider):
    """SearXNG meta-search engine provider over async HTTP."""

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def search(self, query: SearchQuery) -> SearchResponse:
        """Query SearXNG JSON API and return normalized SearchResponse."""
        start_time = time.perf_counter()
        params = {
            "q": query.query,
            "format": "json",
            "language": query.language,
            "categories": ",".join(query.categories),
        }

        async with create_safe_async_client(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/search", params=params)
            response.raise_for_status()
            data = response.json()

        raw_results = data.get("results", [])
        parsed_results: list[SearchResult] = []

        for r in raw_results:
            raw_url = r.get("url")
            raw_title = r.get("title")
            if not raw_url or not raw_title:
                continue

            # SSRF defense: filter internal or metadata destinations
            if not SearchPipeline.is_safe_url(raw_url):
                continue

            parsed_results.append(
                SearchResult(
                    url=raw_url,
                    title=raw_title,
                    snippet=r.get("content", "") or "",
                    engine=r.get("engine", "searxng"),
                    score=float(r.get("score", 0.0) or 0.0),
                )
            )

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return SearchResponse(
            query=query.query,
            results=parsed_results,
            total_results=len(parsed_results),
            execution_time_ms=elapsed_ms,
        )
