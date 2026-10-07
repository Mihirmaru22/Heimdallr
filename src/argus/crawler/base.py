"""Base interface for acquisition and document extraction."""

from abc import ABC, abstractmethod

from argus.crawler.fetcher import BaseFetcher
from argus.crawler.models import CrawlRequest, Document


class BaseAcquisition(ABC):
    """Abstract interface for web acquisition and document extraction."""

    @abstractmethod
    async def fetch_and_extract(self, request: CrawlRequest) -> Document:
        """Fetch raw content and extract structured Document with metadata and content units."""
        pass


class ArgusAcquisition(BaseAcquisition):
    """Default Argus acquisition engine combining BaseFetcher and DocumentExtractor."""

    def __init__(self, fetcher: BaseFetcher) -> None:
        self.fetcher = fetcher

    async def fetch_and_extract(self, request: CrawlRequest) -> Document:
        return await self.fetcher.fetch(request)
