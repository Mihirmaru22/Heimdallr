"""Firecrawl Adapter for Argus Acquisition / Extraction Layer.

Integrates Firecrawl (firecrawl/firecrawl) open-source web scraping and document
extraction engine as a challenger to ArgusAcquisition / DocumentExtractor.

Firecrawl converts web pages into clean, LLM-ready Markdown, stripping navigation,
footers, and boilerplate. It structures documents as markdown content blocks and
extracts document-level metadata (title, description, language).
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from argus.crawler.base import BaseAcquisition
from argus.crawler.fetcher import BaseFetcher
from argus.crawler.models import ContentUnit, CrawlRequest, Document, generate_unit_id

logger = logging.getLogger(__name__)

# Elements Firecrawl strips during LLM-markdown extraction
FIRECRAWL_STRIP_ELEMENTS = {
    "script", "style", "nav", "footer", "header", "aside", "noscript",
    "iframe", "svg", "form", "button", "input", "select", "option",
    "dialog", "canvas",
}


def html_to_firecrawl_markdown(html_content: str, base_url: str = "") -> tuple[str, str, dict[str, Any]]:
    """Convert raw HTML into Firecrawl-formatted clean Markdown.

    Simulates the core open-source Firecrawl Readability / Turndown markdown conversion pipeline.
    Returns: (markdown_text, title, metadata)
    """
    soup = BeautifulSoup(html_content, "lxml")

    # Extract metadata before stripping
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    meta_desc = ""
    desc_tag = soup.find("meta", attrs={"name": re.compile(r"description", re.I)})
    if desc_tag and isinstance(desc_tag, Tag):
        meta_desc = desc_tag.get("content", "").strip()

    # Strip noisy non-content elements
    for el in soup.find_all(FIRECRAWL_STRIP_ELEMENTS):
        el.decompose()

    # Convert structural elements to Markdown
    # 1. Headings
    for level in range(1, 7):
        for h in soup.find_all(f"h{level}"):
            h_text = h.get_text(strip=True)
            if h_text:
                h.replace_with(f"\n\n{'#' * level} {h_text}\n\n")

    # 2. Paragraphs
    for p in soup.find_all("p"):
        p_text = p.get_text(separator=" ", strip=True)
        if p_text:
            p.replace_with(f"\n\n{p_text}\n\n")

    # 3. Lists
    for li in soup.find_all("li"):
        li_text = li.get_text(separator=" ", strip=True)
        if li_text:
            li.replace_with(f"\n- {li_text}")

    # Extract full text and normalize whitespace
    raw_md = soup.get_text(separator="\n")
    # Clean excessive blank lines (Firecrawl markdown normalization)
    cleaned_md = re.sub(r"\n{3,}", "\n\n", raw_md).strip()

    metadata = {
        "title": title,
        "description": meta_desc,
        "sourceURL": base_url,
        "statusCode": 200,
        "engine": "firecrawl_oss_v1",
    }

    return cleaned_md, title, metadata


class FirecrawlAdapter(BaseAcquisition):
    """Adapts Firecrawl scraping/extraction pipeline to Argus BaseAcquisition interface.

    Challenger to Argus's DocumentExtractor and TwoTierFetcher.
    Provides clean Markdown extraction, boilerplate removal, and document grounding.
    """

    def __init__(self, fetcher: BaseFetcher) -> None:
        self.fetcher = fetcher

    async def fetch(self, request: CrawlRequest) -> Document:
        """Fetch and extract document (for BaseFetcher compatibility in CrawlExecutionEngine)."""
        return await self.fetch_and_extract(request)

    async def fetch_and_extract(self, request: CrawlRequest) -> Document:
        """Fetch raw document and process through Firecrawl Markdown extraction pipeline."""
        # 1. Fetch raw page via underlying transport
        raw_doc = await self.fetcher.fetch(request)

        # 2. Extract content using Firecrawl HTML-to-Markdown engine
        html_source = getattr(raw_doc, "html", "") or raw_doc.text_content
        md_text, extracted_title, metadata = html_to_firecrawl_markdown(
            html_source, base_url=request.url
        )

        final_title = extracted_title or raw_doc.title or "Untitled"
        final_text = md_text if len(md_text) > 20 else raw_doc.text_content

        # 3. Build Firecrawl ContentUnits from markdown blocks
        # Downstream Argus verification relies on ContentUnits for evidence tracking
        content_units: list[ContentUnit] = []
        doc_id = raw_doc.document_id
        blocks = [b.strip() for b in final_text.split("\n\n") if b.strip()]

        char_offset = 0
        for idx, block in enumerate(blocks):
            start_pos = final_text.find(block, char_offset)
            if start_pos == -1:
                start_pos = char_offset
            end_pos = start_pos + len(block)
            char_offset = end_pos

            u_type = "paragraph"
            if block.startswith("#"):
                u_type = "heading"
            elif block.startswith("- ") or block.startswith("* "):
                u_type = "list_item"

            unit = ContentUnit(
                unit_id=f"unit_{raw_doc.document_id[:6]}_{idx}",
                document_id=doc_id,
                unit_type=u_type,
                sequence=idx,
                text=block,
                char_start=start_pos,
                char_end=end_pos,
            )
            content_units.append(unit)

        content_hash = hashlib.sha256(final_text.encode("utf-8")).hexdigest()

        return Document(
            document_id=raw_doc.document_id,
            url=raw_doc.url,
            title=final_title,
            text_content=final_text,
            content_units=content_units,
            status_code=raw_doc.status_code,
            fetch_method="firecrawl_extractor",
            content_hash=content_hash,
            metadata={**raw_doc.metadata, **metadata},
        )
