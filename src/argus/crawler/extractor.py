import json
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin, urldefrag

from bs4 import BeautifulSoup, Tag

from argus.crawler.models import ContentUnit, generate_unit_id

STRIP_TAGS = {
    "script",
    "style",
    "nav",
    "footer",
    "header",
    "aside",
    "noscript",
    "iframe",
    "svg",
    "form",
    "button",
    "input",
    "select",
    "option",
    "textarea",
    "dialog",
    "canvas",
    "audio",
    "video",
}

# Common boilerplate class/id patterns (cookie banners, modals, ads, tracking widgets)
BOILERPLATE_ATTR_PATTERN = re.compile(
    r"(cookie|consent|banner|onetrust|gdpr|advertisement|ad-container|sponsored|share-button|social-share|popup|modal)",
    re.IGNORECASE,
)

JS_SHELL_PATTERNS = [
    re.compile(r"enable javascript", re.IGNORECASE),
    re.compile(r"javascript is required", re.IGNORECASE),
    re.compile(r"you need to enable javascript to run this app", re.IGNORECASE),
    re.compile(r"please turn javascript on", re.IGNORECASE),
]


class StructuredDocumentResult(tuple):
    """Result object supporting 8-tuple unpacking, dictionary indexing, and attribute access."""

    def __new__(
        cls,
        title: str,
        clean_text: str,
        needs_browser: bool,
        published_at: datetime | None,
        content_units: list[ContentUnit],
        outgoing_links: list[dict[str, Any]],
        metadata: dict[str, Any],
        canonical_url: str | None,
    ):
        return super().__new__(
            cls,
            (
                title,
                clean_text,
                needs_browser,
                published_at,
                content_units,
                outgoing_links,
                metadata,
                canonical_url,
            ),
        )

    @property
    def title(self) -> str:
        return self[0]

    @property
    def clean_text(self) -> str:
        return self[1]

    @property
    def needs_browser(self) -> bool:
        return self[2]

    @property
    def published_at(self) -> datetime | None:
        return self[3]

    @property
    def content_units(self) -> list[ContentUnit]:
        return self[4]

    @property
    def outgoing_links(self) -> list[dict[str, Any]]:
        return self[5]

    @property
    def metadata(self) -> dict[str, Any]:
        return self[6]

    @property
    def canonical_url(self) -> str | None:
        return self[7]

    def __getitem__(self, item: Any) -> Any:
        if isinstance(item, str):
            mapping = {
                "title": self[0],
                "clean_text": self[1],
                "needs_browser": self[2],
                "published_at": self[3],
                "content_units": self[4],
                "outgoing_links": self[5],
                "metadata": self[6],
                "canonical_url": self[7],
            }
            if item in mapping:
                return mapping[item]
            raise KeyError(item)
        return super().__getitem__(item)


class DocumentExtractor:
    """Extracts webpage title, clean substantive text, and structural units from raw HTML."""

    @classmethod
    def format_table_as_markdown(
        cls, table_tag: Tag
    ) -> tuple[str, list[str], list[list[str]]]:
        """Convert an HTML table into a clean Markdown table with extracted headers and rows."""
        rows: list[list[str]] = []
        headers: list[str] = []

        # 1. Search for headers in thead or th elements
        thead = table_tag.find("thead")
        if thead:
            th_cells = thead.find_all(["th", "td"])
            if th_cells:
                headers = [th.get_text(" ", strip=True) for th in th_cells]

        all_trs = table_tag.find_all("tr")
        for tr in all_trs:
            cells = tr.find_all(["td", "th"])
            if not cells:
                continue
            row_vals = [c.get_text(" ", strip=True) for c in cells]

            # If headers not yet found, check if this tr contains th or is first row
            if not headers:
                if any(c.name == "th" for c in cells) or not rows:
                    headers = row_vals
                    continue

            # Skip duplicate header rows if repeated inside table body
            if row_vals == headers:
                continue

            rows.append(row_vals)

        if not headers and rows:
            headers = [f"Column {i + 1}" for i in range(len(rows[0]))]

        if not headers and not rows:
            return "", [], []

        # Standardize column width
        col_count = max(len(headers), max((len(r) for r in rows), default=0))
        if col_count == 0:
            return "", [], []

        while len(headers) < col_count:
            headers.append(f"Column {len(headers) + 1}")
        for r in rows:
            while len(r) < col_count:
                r.append("")

        # Construct Markdown table representation
        clean_headers = [h.replace("|", "/").replace("\n", " ").strip() for h in headers]
        header_line = "| " + " | ".join(clean_headers) + " |"
        sep_line = "| " + " | ".join("---" for _ in clean_headers) + " |"
        row_lines = [
            "| " + " | ".join(c.replace("|", "/").replace("\n", " ").strip() for c in r) + " |"
            for r in rows
        ]
        md_table = "\n".join([header_line, sep_line] + row_lines)
        return md_table, headers, rows

    @classmethod
    def extract_structured(
        cls,
        raw_html: str,
        base_url: str = "",
        document_id: str = "",
        url: str = "",
    ) -> StructuredDocumentResult:
        """Parse raw HTML and return structured document representation with exact offset alignment."""
        effective_url = url or base_url
        if not raw_html or not raw_html.strip():
            return StructuredDocumentResult("", "", False, None, [], [], {}, None)

        try:
            soup = BeautifulSoup(raw_html, "html.parser")
        except (RecursionError, Exception):
            clean_fallback = re.sub(r"<[^>]+>", " ", raw_html)
            clean_fallback = " ".join(clean_fallback.split())
            return StructuredDocumentResult("", clean_fallback, False, None, [], [], {}, None)

        doc_id = document_id or "doc_temp"
        metadata: dict[str, Any] = {}

        # 1. Title Extraction
        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        if not title:
            og_title = soup.find("meta", property="og:title")
            if og_title and getattr(og_title, "get", None):
                title = str(og_title.get("content", "")).strip()

        # 2. Canonical URL Extraction
        canonical_url: str | None = None
        canonical_tag = soup.find("link", rel=lambda val: val and "canonical" in str(val).lower())
        if canonical_tag and getattr(canonical_tag, "get", None):
            raw_canonical = str(canonical_tag.get("href", "")).strip()
            if raw_canonical:
                canonical_url = urljoin(effective_url, raw_canonical) if effective_url else raw_canonical
                canonical_url, _ = urldefrag(canonical_url)

        # 3. Publication Date & JSON-LD Metadata
        published_at: str | None = None
        meta_pub = (
            soup.find("meta", attrs={"property": re.compile(r"published_time", re.I)})
            or soup.find("meta", attrs={"name": re.compile(r"date|pubdate|published_time", re.I)})
            or soup.find("meta", property=re.compile(r"published_time", re.I))
        )
        if meta_pub and getattr(meta_pub, "get", None):
            published_at = str(meta_pub.get("content", "")).strip()

        if not published_at:
            time_tag = soup.find("time", attrs={"datetime": True}) or soup.find("time")
            if time_tag and getattr(time_tag, "get", None):
                published_at = str(time_tag.get("datetime") or time_tag.get_text(" ", strip=True)).strip()

        # JSON-LD Schema.org parsing
        for ld_script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            try:
                raw_ld = ld_script.get_text().strip()
                if raw_ld:
                    ld_data = json.loads(raw_ld)
                    if isinstance(ld_data, dict):
                        metadata["json_ld"] = ld_data
                        if not published_at:
                            published_at = ld_data.get("datePublished") or ld_data.get("dateModified")
                    elif isinstance(ld_data, list) and ld_data:
                        metadata["json_ld"] = ld_data[0]
                        if not published_at and isinstance(ld_data[0], dict):
                            published_at = ld_data[0].get("datePublished") or ld_data[0].get("dateModified")
            except Exception:
                pass

        if published_at:
            published_at = str(published_at).strip()

        # 4. Outgoing Links
        outgoing_links: list[dict[str, Any]] = []
        seen_links: set[str] = set()
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()
            if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue
            full_link = urljoin(base_url, href) if base_url else href
            clean_link, _ = urldefrag(full_link)
            if clean_link and clean_link not in seen_links:
                seen_links.add(clean_link)
                link_text = a_tag.get_text(" ", strip=True)
                outgoing_links.append({"url": clean_link, "anchor_text": link_text})

        # 5. Clutter Removal
        for tag in soup.find_all(list(STRIP_TAGS)):
            tag.decompose()

        for el in list(soup.find_all(True)):
            if not isinstance(el, Tag) or getattr(el, "attrs", None) is None:
                continue
            if el.name in ("body", "html", "main", "article", "section"):
                continue
            class_val = el.attrs.get("class", [])
            class_str = " ".join(class_val) if isinstance(class_val, list) else str(class_val)
            id_val = str(el.attrs.get("id", ""))
            role_val = str(el.attrs.get("role", ""))
            attr_text = f"{class_str} {id_val} {role_val}".strip()
            if BOILERPLATE_ATTR_PATTERN.search(attr_text):
                el.decompose()

        # 6. Structural Content Units Extraction
        content_units: list[ContentUnit] = []
        current_section: str | None = None
        processed_elements: set[int] = set()

        container = soup.body or soup

        # Find block elements in DOM order
        target_tags = ["h1", "h2", "h3", "h4", "h5", "h6", "p", "table", "ul", "ol", "blockquote", "pre"]
        block_elements = container.find_all(target_tags)

        for el in block_elements:
            if id(el) in processed_elements:
                continue

            tag_name = el.name.lower()

            # Headings
            if tag_name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                h_text = el.get_text(" ", strip=True)
                if h_text and (len(re.sub(r"[^a-zA-Z0-9]", "", h_text)) > 1 or h_text.isalnum()):
                    level = int(tag_name[1])
                    current_section = h_text
                    unit = ContentUnit(
                        document_id=doc_id,
                        unit_type="heading",
                        sequence=len(content_units),
                        heading_level=level,
                        section_title=current_section,
                        text=h_text,
                    )
                    content_units.append(unit)
                processed_elements.add(id(el))

            # Tables
            elif tag_name == "table":
                md_table, headers, rows = cls.format_table_as_markdown(el)
                if md_table:
                    unit = ContentUnit(
                        document_id=doc_id,
                        unit_type="table",
                        sequence=len(content_units),
                        section_title=current_section,
                        text=md_table,
                        metadata={
                            "headers": headers,
                            "row_count": len(rows),
                            "num_rows": len(rows),
                            "col_count": len(headers),
                            "num_cols": len(headers),
                        },
                    )
                    content_units.append(unit)
                # Mark table and all child tags as processed so cells aren't duplicated
                for child in el.find_all(True):
                    processed_elements.add(id(child))
                processed_elements.add(id(el))

            # Lists
            elif tag_name in ("ul", "ol"):
                is_ordered = (tag_name == "ol")
                items = el.find_all("li", recursive=False)
                for idx, li in enumerate(items, start=1):
                    li_text = li.get_text(" ", strip=True)
                    if li_text and (len(re.sub(r"[^a-zA-Z0-9]", "", li_text)) > 1 or li_text.isalnum()):
                        bullet = f"{idx}. " if is_ordered else "- "
                        unit = ContentUnit(
                            document_id=doc_id,
                            unit_type="list_item",
                            sequence=len(content_units),
                            section_title=current_section,
                            text=f"{bullet}{li_text}",
                        )
                        content_units.append(unit)
                for child in el.find_all(True):
                    processed_elements.add(id(child))
                processed_elements.add(id(el))

            # Paragraphs and pre/blockquote
            elif tag_name in ("p", "blockquote", "pre"):
                # Avoid nested paragraph double processing
                if any(parent.name == "p" for parent in el.parents):
                    continue
                p_text = el.get_text(" ", strip=True)
                if p_text and (len(re.sub(r"[^a-zA-Z0-9]", "", p_text)) > 1 or p_text.isalnum()):
                    unit = ContentUnit(
                        document_id=doc_id,
                        unit_type="paragraph",
                        sequence=len(content_units),
                        section_title=current_section,
                        text=p_text,
                    )
                    content_units.append(unit)
                processed_elements.add(id(el))

        # Fallback if no block elements were identified (e.g. flat text or loose divs)
        if not content_units:
            raw_text = container.get_text(separator="\n", strip=True)
            lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
            for line in lines:
                if len(re.sub(r"[^a-zA-Z0-9]", "", line)) > 1 or line.isalnum():
                    unit = ContentUnit(
                        document_id=doc_id,
                        unit_type="paragraph",
                        sequence=len(content_units),
                        section_title=current_section,
                        text=line,
                    )
                    content_units.append(unit)

        # 7. Exact Bounded Coordinate Alignment
        clean_text_parts: list[str] = []
        current_offset = 0

        for seq, unit in enumerate(content_units):
            unit.sequence = seq
            t = unit.text.strip()
            if not t:
                continue

            if clean_text_parts:
                current_offset += 1  # newline separator

            unit.char_start = current_offset
            unit.char_end = current_offset + len(t)
            current_offset += len(t)
            clean_text_parts.append(t)

        clean_text = "\n".join(clean_text_parts)

        # 8. Check for JavaScript SPA shell
        needs_browser = False
        if len(clean_text) < 200:
            for pattern in JS_SHELL_PATTERNS:
                if pattern.search(clean_text) or pattern.search(raw_html):
                    needs_browser = True
                    break
            if not needs_browser and len(clean_text) < 50:
                if re.search(r'id=["\'](root|app|__next)["\']', raw_html, re.I) and ("<script" in raw_html.lower()):
                    needs_browser = True

        # 9. Normalize publication date to UTC datetime
        parsed_published_at: datetime | None = None
        if published_at:
            v_clean = str(published_at).strip()
            if v_clean.endswith("Z"):
                v_clean = v_clean[:-1] + "+00:00"
            try:
                parsed_dt = datetime.fromisoformat(v_clean)
                if parsed_dt.tzinfo is None:
                    parsed_dt = parsed_dt.replace(tzinfo=UTC)
                parsed_published_at = parsed_dt
            except Exception:
                try:
                    parts = v_clean.split("T")[0].split("-")
                    if len(parts) == 3:
                        parsed_published_at = datetime(
                            int(parts[0]), int(parts[1]), int(parts[2]), tzinfo=UTC
                        )
                except Exception:
                    parsed_published_at = None

        return StructuredDocumentResult(
            title,
            clean_text,
            needs_browser,
            parsed_published_at,
            content_units,
            outgoing_links,
            metadata,
            canonical_url,
        )

    @classmethod
    def extract(cls, raw_html: str) -> tuple[str, str, bool, datetime | None]:
        """Backward-compatible extraction interface returning (title, clean_text, needs_browser, published_at)."""
        res = cls.extract_structured(raw_html)
        return res.title, res.clean_text, res.needs_browser, res.published_at
