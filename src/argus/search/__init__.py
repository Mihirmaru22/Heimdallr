"""Search layer for Argus research engine."""

from argus.search.duckduckgo import DuckDuckGoSearchProvider
from argus.search.fourchan import FourChanSearchProvider
from argus.search.google_news import GoogleNewsRSSSearchProvider
from argus.search.hybrid import HybridSearchProvider
from argus.search.linkedin import LinkedInSearchProvider
from argus.search.mock import MockSearchProvider
from argus.search.models import SearchQuery, SearchResponse, SearchResult
from argus.search.pipeline import SearchPipeline
from argus.search.provider import SearchProvider
from argus.search.searxng import SearXNGSearchProvider

__all__ = [
    "DuckDuckGoSearchProvider",
    "FourChanSearchProvider",
    "GoogleNewsRSSSearchProvider",
    "HybridSearchProvider",
    "LinkedInSearchProvider",
    "MockSearchProvider",
    "SearXNGSearchProvider",
    "SearchPipeline",
    "SearchProvider",
    "SearchQuery",
    "SearchResponse",
    "SearchResult",
]
