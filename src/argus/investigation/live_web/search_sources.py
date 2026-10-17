"""Free search sources the live retriever can query, and merging of their results.

Every source here is free and reached through its public interface:
- duckduckgo: the ddgs library (already the V3 default)
- google_news: Google News RSS feeds
- wikipedia: the official MediaWiki search API
- searxng: a SearXNG instance the user runs (set HEIMDALLR_SEARXNG_URL)
- tavily, exa, brave: search APIs with free tiers, used only when their key is set
  (TAVILY_API_KEY, EXA_API_KEY, BRAVE_API_KEY); see argus.search.api_providers

Each source counts against the retriever's per-host and per-task budgets like any fetch.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Callable
from urllib.parse import urlparse

from argus.search.models import SearchResult
from argus.search.provider import SearchProvider

FREE_SEARCH_SOURCES = ("duckduckgo", "google_news", "wikipedia", "searxng", "tavily", "exa", "brave")

_API_SOURCES = {
    # name: (host, key variable, provider class name in argus.search.api_providers)
    "tavily": ("api.tavily.com", "TAVILY_API_KEY", "TavilySearchProvider"),
    "exa": ("api.exa.ai", "EXA_API_KEY", "ExaSearchProvider"),
    "brave": ("api.search.brave.com", "BRAVE_API_KEY", "BraveSearchProvider"),
}


@dataclass
class SearchSource:
    name: str
    host: str
    make: Callable[[float], SearchProvider]


def _duckduckgo(timeout: float) -> SearchProvider:
    # Looked up at call time so tests can substitute the provider class.
    import argus.search.duckduckgo as ddg

    return ddg.DuckDuckGoSearchProvider(timeout=timeout)


def _google_news(timeout: float) -> SearchProvider:
    from argus.search.google_news import GoogleNewsRSSSearchProvider

    return GoogleNewsRSSSearchProvider(timeout=timeout)


def _wikipedia(timeout: float) -> SearchProvider:
    from argus.search.wikipedia import WikipediaSearchProvider

    return WikipediaSearchProvider(timeout=timeout)


def get_search_source(name: str) -> SearchSource | None:
    """The named source, or None when it is unknown or not configured on this machine."""
    if name == "duckduckgo":
        return SearchSource(name, "duckduckgo.com", _duckduckgo)
    if name == "google_news":
        return SearchSource(name, "news.google.com", _google_news)
    if name == "wikipedia":
        return SearchSource(name, "en.wikipedia.org", _wikipedia)
    if name == "searxng":
        base = os.environ.get("HEIMDALLR_SEARXNG_URL", "").strip()
        if not base:
            return None
        from argus.search.searxng import SearXNGSearchProvider

        return SearchSource(name, urlparse(base).netloc or base, lambda t: SearXNGSearchProvider(base_url=base, timeout=t))
    if name in _API_SOURCES:
        host, key_var, cls_name = _API_SOURCES[name]
        key = os.environ.get(key_var, "").strip()
        if not key:
            return None
        import argus.search.api_providers as api

        cls = getattr(api, cls_name)
        return SearchSource(name, host, lambda t: cls(api_key=key, timeout=t))
    return None


def _url_key(url: str) -> str:
    p = urlparse(url.strip())
    host = p.netloc.lower().removeprefix("www.")
    return f"{host}{p.path.rstrip('/')}".lower() + (f"?{p.query}" if p.query else "")


@dataclass
class MergedResult:
    result: SearchResult
    engines: list[str]
    best_rank: int


def merge_results(per_source: list[tuple[str, list[SearchResult]]], limit: int) -> list[MergedResult]:
    """Dedupe by URL across sources; results found by more sources rank first, then by rank."""
    merged: dict[str, MergedResult] = {}
    for name, results in per_source:
        for rank, r in enumerate(results):
            key = _url_key(r.url)
            if key in merged:
                m = merged[key]
                if name not in m.engines:
                    m.engines.append(name)
                m.best_rank = min(m.best_rank, rank)
                if len(r.snippet or "") > len(m.result.snippet or ""):
                    m.result = r  # keep the most informative snippet
            else:
                merged[key] = MergedResult(result=r, engines=[name], best_rank=rank)
    # Sorting by rank interleaves sources at equal agreement, so one engine cannot fill every slot.
    ordered = sorted(merged.values(), key=lambda m: (-len(m.engines), m.best_rank))
    return ordered[:limit]
