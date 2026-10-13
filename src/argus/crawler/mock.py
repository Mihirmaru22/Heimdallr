from argus.crawler.fetcher import BaseFetcher
from argus.crawler.models import CrawlRequest, Document


class MockFetcher(BaseFetcher):
    """Deterministic mock crawler for offline testing."""

    def __init__(self, predefined_documents: dict[str, Document] | None = None) -> None:
        self.predefined_documents = predefined_documents or {}
        self.recorded_requests: list[CrawlRequest] = []

    async def fetch(self, request: CrawlRequest) -> Document:
        self.recorded_requests.append(request)
        if request.url in self.predefined_documents:
            return self.predefined_documents[request.url]

        return Document(
            url=request.url,
            title="Mock Title",
            text_content=f"Mock content for {request.url}",
            status_code=200,
            fetch_method="mock",
        )
