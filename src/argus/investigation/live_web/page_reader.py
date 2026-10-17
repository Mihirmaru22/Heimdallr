"""Turn a fetched page into readable evidence text: main content, structured job posts, PDFs.

V3 stripped every tag with a regex, so menus, cookie banners and footers were mixed
into the evidence and structured data (JSON-LD) was lost. This reader:
- keeps the page's main content (``<main>``/``<article>``/role=main when present) and
  drops navigation, headers, footers, forms and scripts, one block per line;
- reads schema.org JobPosting data embedded as JSON-LD (used by most job boards and
  company career pages) into labelled lines, so the employer, location, date and
  description of a job post are evidence in their own right;
- extracts text from PDFs when the optional ``pypdf`` library is installed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import html as html_lib
import io
import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_DROP_TAGS = ("script", "style", "noscript", "template", "svg", "nav", "footer", "aside", "form", "iframe", "button")
_BLOCK_TAGS = ("p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "td", "th", "dd", "dt", "blockquote", "pre", "div", "section", "br", "tr")


@dataclass
class ReadPage:
    title: str
    text: str
    method: str  # html_main_content | html_body | pdf_text | pdf_unreadable | plain_text
    job_postings: list[dict[str, str]] = field(default_factory=list)
    note: str | None = None


def _clean_lines(text: str) -> str:
    out: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        line = " ".join(line.split())
        if len(line) < 3 or line in seen:
            continue
        seen.add(line)
        out.append(line)
    return "\n".join(out)


def _strip_html(fragment: str) -> str:
    text = re.sub(r"<\s*(?:br|/p|/li|/div|/h\d)\s*/?>", "\n", fragment or "", flags=re.I)
    return html_lib.unescape(re.sub(r"<[^>]+>", " ", text))


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _place(loc: Any) -> str:
    parts: list[str] = []
    for item in _as_list(loc):
        if isinstance(item, str):
            parts.append(item)
            continue
        if not isinstance(item, dict):
            continue
        addr = item.get("address", item)
        if isinstance(addr, str):
            parts.append(addr)
        elif isinstance(addr, dict):
            bits = [addr.get(k) for k in ("addressLocality", "addressRegion", "addressCountry")]
            bits = [b.get("name") if isinstance(b, dict) else b for b in bits]
            parts.append(", ".join(str(b) for b in bits if b))
    return "; ".join(p for p in parts if p)


def job_postings_from_jsonld(raw_html: str) -> list[dict[str, str]]:
    """schema.org JobPosting objects embedded in the page, as flat fields."""
    postings: list[dict[str, str]] = []
    for block in re.findall(r"<script[^>]+application/ld\+json[^>]*>(.*?)</script>", raw_html or "", flags=re.I | re.S):
        try:
            data = json.loads(block.strip())
        except (ValueError, TypeError):
            continue
        stack = _as_list(data)
        while stack:
            node = stack.pop(0)
            if not isinstance(node, dict):
                continue
            stack.extend(_as_list(node.get("@graph")))
            kinds = {str(k) for k in _as_list(node.get("@type"))}
            if "JobPosting" not in kinds:
                continue
            org = node.get("hiringOrganization")
            org_name = org.get("name") if isinstance(org, dict) else org
            postings.append({
                "title": str(node.get("title") or "").strip(),
                "employer": str(org_name or "").strip(),
                "location": _place(node.get("jobLocation")) or str(node.get("jobLocationType") or ""),
                "date_posted": str(node.get("datePosted") or "").strip(),
                "description": _clean_lines(_strip_html(str(node.get("description") or ""))),
            })
    return postings


def _posting_text(p: dict[str, str]) -> str:
    lines = [f"Job posting: {p['title']}" if p.get("title") else "Job posting"]
    if p.get("employer"):
        lines.append(f"Employer: {p['employer']}")
    if p.get("location"):
        lines.append(f"Location: {p['location']}")
    if p.get("date_posted"):
        lines.append(f"Date posted: {p['date_posted']}")
    if p.get("description"):
        lines.append(p["description"])
    return "\n".join(lines)


def read_html(raw_html: str, fallback_title: str = "") -> ReadPage:
    from bs4 import BeautifulSoup

    postings = job_postings_from_jsonld(raw_html)
    soup = BeautifulSoup(raw_html or "", "html.parser")
    title = (soup.title.get_text(" ", strip=True) if soup.title else "") or fallback_title
    for tag in soup(_DROP_TAGS):
        tag.decompose()
    root = soup.find("main") or soup.find(attrs={"role": "main"}) or soup.find("article")
    method = "html_main_content" if root else "html_body"
    root = root or soup.body or soup
    # Site banners go; a headline <header> inside the article stays.
    for tag in root.find_all("header"):
        if not tag.find_parent(("article", "main")):
            tag.decompose()
    for tag in root.find_all(_BLOCK_TAGS):
        tag.insert_before("\n")
        tag.insert_after("\n")
    body = _clean_lines(root.get_text(" "))
    text = "\n\n".join([*(_posting_text(p) for p in postings), body]).strip()
    return ReadPage(title=title, text=text, method=method, job_postings=postings)


def read_pdf(data: bytes, fallback_title: str = "") -> ReadPage:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ReadPage(title=fallback_title, text="", method="pdf_unreadable", note="PDF text extraction needs the optional pypdf library (pip install pypdf)")
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [(page.extract_text() or "") for page in reader.pages[:50]]
        meta_title = str((reader.metadata or {}).get("/Title") or "").strip()
    except Exception as exc:
        return ReadPage(title=fallback_title, text="", method="pdf_unreadable", note=f"PDF could not be read: {exc}")
    return ReadPage(title=meta_title or fallback_title, text=_clean_lines("\n".join(pages)), method="pdf_text")


def read_page(content: bytes, content_type: str = "", fallback_title: str = "") -> ReadPage:
    """Readable text of a fetched resource, chosen by content type (or PDF signature)."""
    ctype = (content_type or "").lower()
    if "pdf" in ctype or content[:5] == b"%PDF-":
        return read_pdf(content, fallback_title)
    text = content.decode("utf-8", errors="replace")
    if "html" in ctype or "xml" in ctype or re.search(r"<\s*(?:html|body|div|p)\b", text[:5000], re.I):
        return read_html(text, fallback_title)
    return ReadPage(title=fallback_title, text=_clean_lines(text), method="plain_text")
