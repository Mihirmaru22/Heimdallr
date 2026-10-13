"""Real-time LinkedIn scraping and search provider.

Performs live search dorking across indexed LinkedIn profiles and company directories,
bypassing the LinkedIn authwall by extracting rich structured profile metadata
directly from organic search snippets and SERP caches without requiring user credentials.
"""

import asyncio
import logging
import re
import time
from urllib.parse import parse_qs, unquote, urlparse

from argus.search.duckduckgo import DuckDuckGoSearchProvider
from argus.search.models import SearchQuery, SearchResponse, SearchResult
from argus.search.provider import SearchProvider

logger = logging.getLogger(__name__)

# Regex to extract person name and role from standard LinkedIn page titles:
# e.g. "Amy Carrier - Plant Director at General Motors | LinkedIn"
# or "Ray Theriault - Corvette Plant Director - General Motors | LinkedIn"
LI_TITLE_PATTERN = re.compile(
    r"^([A-Z][a-zA-Z\.\'\- ]+?)\s*[\-\|\–]\s*(.+?)(?:\s*[\-\|\–]\s*LinkedIn)?$",
    re.IGNORECASE,
)


def _clean_linkedin_url(raw_url: str) -> str:
    """Normalize LinkedIn URL by unwrapping redirects and stripping query tracking parameters."""
    if not raw_url:
        return ""
    if "uddg=" in raw_url:
        p_wrap = urlparse(raw_url)
        qs = parse_qs(p_wrap.query)
        if "uddg" in qs and qs["uddg"]:
            raw_url = unquote(qs["uddg"][0])
    p = urlparse(raw_url)
    clean_path = p.path.rstrip("/")
    return f"https://www.linkedin.com{clean_path}"


def parse_linkedin_title(title: str) -> tuple[str, str]:
    """Parse name and role from LinkedIn title. Returns (name, role)."""
    if not title:
        return "", ""
    # Remove trailing "| LinkedIn" or "- LinkedIn"
    cleaned = re.sub(r"\s*[\-\|\–]\s*LinkedIn.*$", "", title, flags=re.IGNORECASE).strip()
    match = LI_TITLE_PATTERN.match(cleaned)
    if match:
        name = match.group(1).strip()
        role = match.group(2).strip()
        return name, role
    return cleaned, ""


class LinkedInSearchProvider(SearchProvider):
    """Real-time LinkedIn scraper and search provider using live SERP index extraction."""

    def __init__(
        self,
        search_backend: SearchProvider | None = None,
        timeout: float = 12.0,
    ) -> None:
        self.backend = search_backend or DuckDuckGoSearchProvider(timeout=timeout, max_concurrent=2)

    async def search(self, query: SearchQuery) -> SearchResponse:
        """Execute real-time LinkedIn targeted search and return parsed profiles."""
        start_time = time.perf_counter()
        raw_query = query.query.strip()
        if not raw_query:
            return SearchResponse(
                query=query.query,
                results=[],
                total_results=0,
                execution_time_ms=0.0,
            )

        # Build precision LinkedIn dork query if not already scoped
        if "site:linkedin.com" not in raw_query.lower():
            # Add role-seeking keywords if not present
            role_terms = ""
            if not any(k in raw_query.lower() for k in ("director", "manager", "lead", "head", "engineer")):
                role_terms = ' ("Plant Director" OR "Plant Manager" OR "Site Director" OR "Engineering Lead")'
            dork_query = f'site:linkedin.com/in {raw_query}{role_terms}'
        else:
            dork_query = raw_query

        # Execute live search
        backend_resp = await self.backend.search(
            SearchQuery(query=dork_query, num_results=query.num_results * 2)
        )

        parsed_results: list[SearchResult] = []
        seen_urls: set[str] = set()

        for item in backend_resp.results:
            url_lower = item.url.lower()
            if "linkedin.com/in/" not in url_lower and "linkedin.com/company/" not in url_lower:
                continue

            # Filter out authwall/login/signup redirect endpoints
            if any(junk in url_lower for junk in ("/login", "/signup", "/uas/login", "/authwall", "/checkpoint")):
                continue
            if any(junk in item.title.lower() for junk in ("log in", "sign up", "sign in", "join linkedin")):
                continue

            clean_url = _clean_linkedin_url(item.url)
            if clean_url in seen_urls:
                continue
            seen_urls.add(clean_url)

            name, role = parse_linkedin_title(item.title)
            formatted_title = f"{name} - {role}" if role else item.title

            parsed_results.append(
                SearchResult(
                    url=clean_url,
                    title=f"LinkedIn: {formatted_title}",
                    snippet=item.snippet,
                    engine="linkedin",
                    score=0.92,
                )
            )

            if len(parsed_results) >= query.num_results:
                break

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return SearchResponse(
            query=query.query,
            results=parsed_results,
            total_results=len(parsed_results),
            execution_time_ms=elapsed_ms,
        )

    async def close(self) -> None:
        """Close backend search provider if supported."""
        if hasattr(self.backend, "close") and callable(self.backend.close):
            res = self.backend.close()
            if asyncio.iscoroutine(res):
                await res
