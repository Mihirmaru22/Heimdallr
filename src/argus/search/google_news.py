"""Google News RSS Search Provider for Argus.

Provides real-time, zero-key, high-concurrency search across corporate newsrooms,
local newspapers, and industry publications without bot blocking or rate limits.
"""

import html
import logging
import re
import time
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET

import httpx

from argus.search.models import SearchQuery, SearchResponse, SearchResult
from argus.search.pipeline import SearchPipeline, create_safe_async_client
from argus.search.provider import SearchProvider

logger = logging.getLogger(__name__)

# Standard browser User-Agent
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class GoogleNewsRSSSearchProvider(SearchProvider):
    """Zero-key, high-speed news and press search via Google News RSS syndication."""

    def __init__(
        self,
        timeout: float = 8.0,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self.timeout = timeout
        self.headers = {"User-Agent": user_agent}

    async def search(self, query: SearchQuery) -> SearchResponse:
        """Query Google News RSS feed and return normalized search results."""
        start_time = time.perf_counter()
        query_text = query.query.strip()
        if not query_text:
            return SearchResponse(
                query=query.query,
                results=[],
                total_results=0,
                execution_time_ms=0.0,
            )

        encoded_q = quote_plus(query_text)
        rss_url = (
            f"https://news.google.com/rss/search?q={encoded_q}&hl=en-US&gl=US&ceid=US:en"
        )

        try:
            async with create_safe_async_client(
                timeout=self.timeout,
                follow_redirects=False,
                headers=self.headers,
            ) as client:
                response = await client.get(rss_url)
                response.raise_for_status()
                xml_content = response.text

            results = self._parse_rss(xml_content, max_results=query.num_results)

        except Exception as exc:
            logger.warning(
                "GoogleNewsRSS search failed for query '%s': %s",
                query.query,
                exc,
            )
            results = []

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return SearchResponse(
            query=query.query,
            results=results,
            total_results=len(results),
            execution_time_ms=elapsed_ms,
        )

    def _parse_rss(self, xml_content: str, max_results: int) -> list[SearchResult]:
        """Parse Google News RSS XML into normalized SearchResult models with XXE defense."""
        parsed_results: list[SearchResult] = []

        # Defuse XML entity expansion & XXE attacks
        if "<!ENTITY" in xml_content or "<!DOCTYPE" in xml_content:
            logger.warning("Rejected RSS feed containing potentially malicious DTD or ENTITY declarations")
            return []

        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as err:
            logger.warning("Failed to parse Google News RSS XML: %s", err)
            return []

        channel = root.find("channel")
        if channel is None:
            return []

        for item in channel.findall("item"):
            title_elem = item.find("title")
            link_elem = item.find("link")
            pub_date_elem = item.find("pubDate")
            desc_elem = item.find("description")
            source_elem = item.find("source")

            raw_title = title_elem.text if title_elem is not None and title_elem.text else ""
            raw_link = link_elem.text if link_elem is not None and link_elem.text else ""

            if not raw_title or not raw_link:
                continue

            # Epistemic & network defense: discard links to private or disallowed targets
            if not SearchPipeline.is_safe_url(raw_link):
                continue

            source_name = (
                source_elem.text
                if source_elem is not None and source_elem.text
                else ""
            )
            pub_date = (
                pub_date_elem.text
                if pub_date_elem is not None and pub_date_elem.text
                else ""
            )

            # Build clean snippet from source, publication date, and description
            snippet_parts = []
            if source_name:
                snippet_parts.append(f"Source: {source_name}")
            if pub_date:
                snippet_parts.append(f"Date: {pub_date}")

            if desc_elem is not None and desc_elem.text:
                clean_desc = re.sub(r"<[^>]+>", " ", desc_elem.text)
                clean_desc = html.unescape(clean_desc).strip()
                clean_desc = " ".join(clean_desc.split())
                if clean_desc and clean_desc not in raw_title:
                    snippet_parts.append(clean_desc[:250])

            snippet = " | ".join(snippet_parts) if snippet_parts else raw_title

            # Calculate rank-decay score
            rank_idx = len(parsed_results)
            score = max(0.4, 0.95 - (rank_idx * 0.05))

            parsed_results.append(
                SearchResult(
                    url=raw_link,
                    title=html.unescape(raw_title).strip(),
                    snippet=snippet,
                    engine="google_news",
                    score=round(score, 3),
                )
            )

            if len(parsed_results) >= max_results:
                break

        return parsed_results
