from abc import ABC, abstractmethod

from argus.search.models import SearchQuery, SearchResponse


class SearchProvider(ABC):
    """Abstract interface defining the contract for search providers."""

    @abstractmethod
    async def search(self, query: SearchQuery) -> SearchResponse:
        """Execute a search query asynchronously and return normalized results."""
