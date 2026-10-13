from argus.search.models import SearchQuery, SearchResponse, SearchResult
from argus.search.provider import SearchProvider


class MockSearchProvider(SearchProvider):
    """A deterministic mock search provider for unit testing without network dependencies."""

    def __init__(self, predefined_results: list[SearchResult] | None = None) -> None:
        self.predefined_results = predefined_results or []
        self.recorded_queries: list[SearchQuery] = []

    async def search(self, query: SearchQuery) -> SearchResponse:
        self.recorded_queries.append(query)
        # Return slice up to requested num_results
        results = self.predefined_results[: query.num_results]
        return SearchResponse(
            query=query.query,
            results=results,
            total_results=len(results),
            execution_time_ms=5.0,
        )
