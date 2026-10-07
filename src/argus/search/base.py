"""Base interface for discovery and crawling components."""

from abc import ABC, abstractmethod

from argus.search.models import SearchQuery, SearchResponse


class BaseDiscovery(ABC):
    """Abstract interface for discovery and search pipelines."""

    @abstractmethod
    async def search(self, query: SearchQuery) -> SearchResponse:
        """Execute discovery search query and return normalized results."""
        pass

    @abstractmethod
    def normalize_url(self, raw_url: str) -> str:
        """Normalize URL format and strip non-semantic query tracking parameters."""
        pass
