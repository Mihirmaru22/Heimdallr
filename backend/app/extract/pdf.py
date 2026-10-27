"""Text of a PDF as a plain HTML page, so a discovery source can read a PDF case study like any other page.

Customer stories and partner write-ups are often published only as PDFs (set 1 baseline: 7 of the case-study
pages picked were PDFs, and one of them was the only copy of a real user's story). Only the text is taken, at most
MAX_PAGES pages; nothing in the file is run. A PDF that can't be read gives None, like an unreadable page.
"""

from __future__ import annotations

import html
import io
import logging

log = logging.getLogger(__name__)

MAX_PAGES = 30
PDF_TYPES = ("application/pdf", "application/x-pdf")


def pdf_html(body: bytes) -> str | None:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(body))
        title = str((reader.metadata or {}).get("/Title") or "").strip() if reader.metadata else ""
        lines: list[str] = []
        for page in reader.pages[:MAX_PAGES]:
            lines += [ln.strip() for ln in (page.extract_text() or "").splitlines() if ln.strip()]
    except Exception as exc:  # noqa: BLE001 - a broken or encrypted PDF is just an unreadable page
        log.info("PDF could not be read: %s", type(exc).__name__)
        return None
    if not lines:
        return None
    title = title or lines[0][:200]
    body_html = "\n".join(f"<p>{html.escape(ln)}</p>" for ln in lines)
    return f"<html><head><title>{html.escape(title)}</title></head><body>{body_html}</body></html>"
