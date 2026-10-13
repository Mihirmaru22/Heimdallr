"""Real-time 4chan search provider for public discussion, rumors, and leaks.

Connects directly to the official zero-auth 4chan Read API:
- Boards: /o/ (Automotive) and /biz/ (Business & Finance)
- Real-time Catalog: https://a.4cdn.org/{board}/catalog.json
- Thread Details: https://a.4cdn.org/{board}/thread/{no}.json
"""

import asyncio
import html
import logging
import re
import time

import httpx

from argus.search.models import SearchQuery, SearchResponse, SearchResult
from argus.search.pipeline import create_safe_async_client
from argus.search.provider import SearchProvider

logger = logging.getLogger(__name__)

TAG_RE = re.compile(r"<[^>]+>")
SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)


def _clean_html(text: str) -> str:
    """Strip HTML formatting, embedded scripts/styles, and decode HTML entities from 4chan posts."""
    if not text or not isinstance(text, str):
        return ""
    # Strip script and style blocks along with inner content
    text = SCRIPT_STYLE_RE.sub(" ", text)
    # Replace <br> and <wbr> tags
    text = text.replace("<br>", " ").replace("<br/>", " ").replace("<br />", " ").replace("<wbr>", "")
    # Remove HTML tags
    cleaned = TAG_RE.sub(" ", text)
    # Unescape HTML entities (&gt;, &amp;, &#039;, etc.)
    cleaned = html.unescape(cleaned)
    # Collapse multiple whitespaces
    return " ".join(cleaned.split()).strip()


class FourChanSearchProvider(SearchProvider):
    """Real-time 4chan scraper and search provider querying official read APIs with in-memory caching."""

    def __init__(
        self,
        boards: list[str] | None = None,
        timeout: float = 8.0,
        max_threads_per_board: int = 150,
        cache_ttl_seconds: float = 30.0,
    ) -> None:
        self.boards = boards or ["o", "biz"]
        self.timeout = timeout
        self.max_threads_per_board = max_threads_per_board
        self.cache_ttl = cache_ttl_seconds
        self._catalog_cache: dict[str, tuple[float, list[dict]]] = {}
        self._client = create_safe_async_client(
            timeout=self.timeout,
            headers={
                "User-Agent": "ArgusIntelligence/1.0",
                "Accept": "application/json",
            },
        )

    async def search(self, query: SearchQuery) -> SearchResponse:
        """Search active 4chan catalog threads in real time across configured boards."""
        start_time = time.perf_counter()
        raw_query = query.query.strip().lower()
        if not raw_query:
            return SearchResponse(
                query=query.query,
                results=[],
                total_results=0,
                execution_time_ms=0.0,
            )

        # Extract search tokens (ignore single character or common stop words)
        stop_words = {"the", "a", "an", "and", "or", "for", "in", "of", "to", "at", "by", "from"}
        clean_tokens = [
            t.strip(".,;:?!'\"()[]{}")
            for t in raw_query.split()
            if len(t.strip(".,;:?!'\"()[]{}")) >= 3 and t.lower() not in stop_words
        ]

        if not clean_tokens:
            clean_tokens = [t.strip(".,;:?!'\"()[]{}") for t in raw_query.split() if t.strip(".,;:?!'\"()[]{}")]

        clean_tokens = [t for t in clean_tokens if t]
        if not clean_tokens:
            return SearchResponse(
                query=query.query,
                results=[],
                total_results=0,
                execution_time_ms=0.0,
            )

        matches: list[SearchResult] = []

        # Query boards concurrently
        board_tasks = [self._search_board(board, clean_tokens, query.num_results) for board in self.boards]
        board_results = await asyncio.gather(*board_tasks, return_exceptions=True)

        for res in board_results:
            if isinstance(res, list):
                matches.extend(res)
            elif isinstance(res, Exception):
                logger.debug("4chan board search error: %s", res)

        # Sort matches by score descending
        matches.sort(key=lambda x: x.score, reverse=True)
        final_results = matches[: query.num_results]

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return SearchResponse(
            query=query.query,
            results=final_results,
            total_results=len(final_results),
            execution_time_ms=elapsed_ms,
        )

    async def _fetch_catalog(self, board: str) -> list[dict]:
        """Fetch catalog from 4chan API or return cached copy if fresh."""
        now = time.time()
        if board in self._catalog_cache:
            timestamp, cached = self._catalog_cache[board]
            if now - timestamp < self.cache_ttl:
                return cached

        catalog_url = f"https://a.4cdn.org/{board}/catalog.json"
        try:
            resp = await self._client.get(catalog_url)
            if resp.status_code != 200:
                return []
            catalog = resp.json()
            if not isinstance(catalog, list):
                return []
            self._catalog_cache[board] = (now, catalog)
            return catalog
        except Exception as exc:
            logger.debug("Failed to fetch 4chan /%s/ catalog: %s", board, exc)
            return []

    async def _search_board(
        self, board: str, tokens: list[str], max_results: int
    ) -> list[SearchResult]:
        """Fetch and scan the catalog of a specific 4chan board."""
        catalog = await self._fetch_catalog(board)
        if not catalog:
            return []

        board_matches: list[SearchResult] = []

        for page in catalog:
            if not isinstance(page, dict):
                continue
            for thread in page.get("threads", []):
                if not isinstance(thread, dict):
                    continue
                thread_no = thread.get("no")
                if not thread_no:
                    continue

                sub = _clean_html(str(thread.get("sub") or ""))
                com = _clean_html(str(thread.get("com") or ""))
                full_text = f"{sub} {com}".lower()

                # Calculate match relevance
                match_count = sum(1 for tok in tokens if tok in full_text)
                if match_count == 0:
                    continue

                thread_url = f"https://boards.4channel.org/{board}/thread/{thread_no}"
                title = sub if sub else f"4chan /{board}/ Thread #{thread_no}"
                snippet = com[:300] if com else f"Discussion on 4chan /{board}/ matching {', '.join(tokens)}"

                score = min(0.95, 0.5 + (match_count / max(1, len(tokens))) * 0.45)

                board_matches.append(
                    SearchResult(
                        url=thread_url,
                        title=f"4chan /{board}/: {title}",
                        snippet=snippet,
                        engine="4chan",
                        score=round(score, 3),
                    )
                )

                if len(board_matches) >= max_results * 2:
                    break

        return board_matches

    async def close(self) -> None:
        """Close underlying HTTP client safely and idempotently."""
        if hasattr(self, "_client") and not self._client.is_closed:
            await self._client.aclose()
