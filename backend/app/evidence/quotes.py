"""Exact sentences from a fetched document that mention a product. A quote shown to the person is always a
verbatim substring of the document's text; verify_quote() is the check."""

from __future__ import annotations

import re

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from app.evidence.products import Product

SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"“])")
MAX_QUOTE = 400


def document_text(html_or_text: str) -> str:
    """Readable text of an HTML filing or page: scripts and styles out, whitespace collapsed."""
    if "<" in html_or_text[:2000]:
        tree = HTMLParser(html_or_text)
        for n in tree.css("script, style, noscript"):
            n.decompose()
        text = tree.body.text(separator=" ") if tree.body else tree.text(separator=" ")
    else:
        text = html_or_text
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def find_mentions(text: str, product: Product, limit: int = 3) -> list[str]:
    """Up to `limit` distinct sentences that mention the product, in document order."""
    out: list[str] = []
    for pattern in product.patterns:
        for m in pattern.finditer(text):
            start = max(text.rfind(". ", 0, m.start()) + 2, m.start() - MAX_QUOTE // 2, 0)
            ends = [i for i in (text.find(". ", m.end()), text.find("? ", m.end())) if i != -1]
            end = min([*ends, m.end() + MAX_QUOTE // 2, len(text)])
            quote = text[start:end + 1].strip()
            if quote and quote not in out:
                out.append(quote)
            if len(out) >= limit * 3:
                break
    # Document order, then the first `limit`.
    out.sort(key=text.find)
    return out[:limit]


def verify_quote(quote: str, text: str) -> bool:
    return bool(quote) and quote in text
