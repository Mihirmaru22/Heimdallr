"""Exact sentences from a fetched document that mention a product. A quote shown to the person is always a
verbatim substring of the document's text; verify_quote() is the check."""

from __future__ import annotations

import re

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from app.evidence.products import Product

SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"“])")
MAX_QUOTE = 400
# Where a quote can start: after a sentence end, a bullet, or a table rule ("____ 1 Costs attributable to").
BREAKS = (". ", "? ", "! ", "• ", "_ ", "| ")


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
    spans: list[tuple[int, int]] = []
    for pattern in product.patterns:
        for m in pattern.finditer(text):
            # The sentence around the mention: from the last sentence end, bullet or table rule before it to
            # the next sentence end. A sentence longer than MAX_QUOTE is cut at whole words around the mention,
            # never mid-word ("rgin 21.0 %" was the start of a quote).
            start = max([i + len(b) for b in BREAKS if (i := text.rfind(b, 0, m.start())) != -1], default=0)
            if m.start() - start > MAX_QUOTE // 2:
                start = text.find(" ", m.start() - MAX_QUOTE // 2, m.start()) + 1 or m.start()
            ends = [i + 1 for i in (text.find(". ", m.end()), text.find("? ", m.end())) if i != -1]
            end = min([*ends, len(text)])
            if end - m.end() > MAX_QUOTE // 2:
                cut = text.rfind(" ", m.end(), m.end() + MAX_QUOTE // 2)
                end = cut if cut != -1 else m.end()
            quote = text[start:end].strip(" _•-–|")
            # One quote per sentence: "SAP S/4HANA" and "S/4HANA" inside it are the same mention.
            if quote and not any(start < e and s < end for s, e in spans):
                spans.append((start, end))
                out.append(quote)
            if len(out) >= limit * 3:
                break
    # Document order, then the first `limit`.
    out.sort(key=text.find)
    return out[:limit]


def verify_quote(quote: str, text: str) -> bool:
    return bool(quote) and quote in text
