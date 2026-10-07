"""Photon Adapter for Argus Discovery / Crawling Layer.

Integrates Photon (s0md3v/Photon) open-source OSINT crawling and link discovery
engine as a challenger to ArgusDiscovery.

Photon utilizes fast regular-expression link parsing across HTML/JavaScript to
harvest in-scope and out-of-scope URLs, query-parameter endpoints, and subdomains,
crawling breadth-first without semantic query ranking or snippet triage.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any
from urllib.parse import urljoin, urlparse

from argus.search.base import BaseDiscovery
from argus.search.models import SearchQuery, SearchResponse, SearchResult
from argus.search.pipeline import SearchPipeline
from argus.search.provider import SearchProvider

logger = logging.getLogger(__name__)

# Photon standard regex patterns for OSINT link and endpoint harvesting
PHOTON_HREF_REGEX = re.compile(r"""(?:href|src)=['"]?([^'"\s>]+)""", re.IGNORECASE)
PHOTON_PARAM_REGEX = re.compile(r"""['"]([^'"\s]+\?[^'"\s]+)['"]""")
PHOTON_SCRIPT_REGEX = re.compile(r"""<script[^>]+src=['"]([^'"]+)['"]""", re.IGNORECASE)


class PhotonAdapter(BaseDiscovery):
    """Adapts Photon OSINT link-extraction crawler to the Argus BaseDiscovery interface.

    Challenger to Argus's SearchPipeline and Laya System 1 triage.
    Discovers URLs by parsing all internal/external hyperlinks via regex exploration.
    """

    def __init__(
        self,
        provider: SearchProvider | None = None,
        corpus_documents: list[Any] | None = None,
        max_depth: int = 2,
    ) -> None:
        self.provider = provider
        self.corpus_documents = corpus_documents or []
        self.max_depth = max_depth
        self._doc_by_url: dict[str, Any] = {
            getattr(d, "url", ""): d for d in self.corpus_documents if getattr(d, "url", "")
        }

    def normalize_url(self, raw_url: str) -> str:
        """Photon standard URL normalizer (delegates to canonical URL normalization)."""
        return SearchPipeline.normalize_url(raw_url)

    def extract_photon_links(self, html_or_text: str, base_url: str) -> list[str]:
        """Extract links using Photon's signature regex extraction logic."""
        found_links: list[str] = []
        raw_matches = PHOTON_HREF_REGEX.findall(html_or_text)
        param_matches = PHOTON_PARAM_REGEX.findall(html_or_text)

        parsed_base = urlparse(base_url)
        base_domain = parsed_base.netloc.lower()

        for match in raw_matches + param_matches:
            match = match.strip()
            if not match or match.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue

            full_url = urljoin(base_url, match)
            norm = self.normalize_url(full_url)
            parsed_full = urlparse(norm)

            if parsed_full.scheme in ("http", "https"):
                found_links.append(norm)

        # Deduplicate while preserving discovery order
        seen = set()
        deduped = []
        for link in found_links:
            if link not in seen:
                seen.add(link)
                deduped.append(link)

        return deduped

    async def search(self, query: SearchQuery) -> SearchResponse:
        """Execute discovery using Photon crawl spidering logic.

        Instead of semantic search ranking, Photon identifies seed URLs matching
        the domain/target and spider-crawls links using regex extraction.
        """
        start_time = time.perf_counter()

        # 1. Base provider seed discovery (analogous to Photon seeds / search query)
        seed_results: list[SearchResult] = []
        if self.provider is not None:
            raw_resp = await self.provider.search(query)
            seed_results = raw_resp.results

        # 2. Photon Spider: Crawl links out of discovered seeds
        discovered_urls: list[str] = []
        discovered_results: list[SearchResult] = []
        seen_urls: set[str] = set()

        # Add initial seeds
        for item in seed_results:
            norm_url = self.normalize_url(item.url)
            if norm_url not in seen_urls:
                seen_urls.add(norm_url)
                discovered_urls.append(norm_url)
                discovered_results.append(
                    SearchResult(
                        url=norm_url,
                        title=f"[Photon Seed] {item.title}",
                        snippet=item.snippet,
                        engine="photon_crawler",
                        score=0.9,
                    )
                )

        # 3. Spidering Phase: Regex extract links from document bodies in corpus
        for seed_url in list(discovered_urls):
            doc = self._doc_by_url.get(seed_url)
            if not doc:
                continue

            body = getattr(doc, "html", "") or getattr(doc, "text_content", "")
            child_links = self.extract_photon_links(body, base_url=seed_url)

            for child_url in child_links:
                if child_url not in seen_urls:
                    seen_urls.add(child_url)
                    discovered_urls.append(child_url)

                    child_doc = self._doc_by_url.get(child_url)
                    title = getattr(child_doc, "title", "Photon Discovered Page") if child_doc else "Photon Discovered Page"
                    snippet = getattr(child_doc, "text_content", "")[:200] if child_doc else ""

                    discovered_results.append(
                        SearchResult(
                            url=child_url,
                            title=f"[Photon Crawl] {title}",
                            snippet=snippet,
                            engine="photon_crawler",
                            score=0.7,
                        )
                    )

        # Photon returns URLs in BFS crawl order, capped at query request
        final_results = discovered_results[:query.num_results]
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        return SearchResponse(
            query=query.query,
            results=final_results,
            total_results=len(final_results),
            execution_time_ms=elapsed_ms,
        )
