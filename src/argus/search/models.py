from pydantic import BaseModel, Field


class SearchQuery(BaseModel):
    """Parameters for executing a research search query."""

    query: str = Field(..., min_length=1, description="Search query string")
    num_results: int = Field(
        default=10, ge=1, le=50, description="Max results requested"
    )
    language: str = Field(default="en", description="Target language code")
    categories: list[str] = Field(
        default_factory=lambda: ["general"], description="SearXNG categories to query"
    )


class SearchResult(BaseModel):
    """A single normalized search result from an engine."""

    url: str = Field(..., min_length=1, description="Result destination URL")
    title: str = Field(..., min_length=1, description="Webpage or document title")
    snippet: str = Field(default="", description="Search snippet or summary")
    engine: str = Field(
        default="unknown", description="Source search engine, e.g. google, bing"
    )
    score: float = Field(default=0.0, description="Engine relevance score")


class SearchResponse(BaseModel):
    """Aggregated response from a search provider."""

    query: str = Field(..., description="Original search query executed")
    results: list[SearchResult] = Field(
        default_factory=list, description="List of search results"
    )
    total_results: int = Field(default=0, description="Total results count")
    execution_time_ms: float = Field(
        default=0.0, description="Execution time in milliseconds"
    )
