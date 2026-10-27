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


SENTENCE_STOP = (".", "!", "?", ":")


def _short(line: str) -> bool:
    """A line of at most three words: a menu entry, a heading, a button, never a sentence on its own."""
    return len(line.split()) <= 3


def _block_bounds(text: str, start: int, end: int, at: int, at_end: int) -> tuple[int, int]:
    """Narrow [start, end) around the mention at [at, at_end) to the lines of its own sentence.

    Page text keeps one line per text node, so an inline link or bold word breaks a sentence over lines and a
    menu is a run of short lines. A neighbouring line joins the quote unless a sentence ended before it, or it
    is part of a run of short lines (a menu, a list of links). Set 1's quotes were menus ("Products Solutions
    Customers ... uses Windchill") and the model then read them as naming nobody."""
    if "\n" not in text[start:end]:
        return start, end
    line_start = text.rfind("\n", start, at) + 1 or start
    line_start = max(line_start, start)
    cur = line_start
    while cur > start:
        prev_start = max(text.rfind("\n", start, cur - 1) + 1, start)
        prev = text[prev_start:cur - 1].strip()
        before = text[max(text.rfind("\n", start, prev_start - 1) + 1, start):prev_start - 1].strip() \
            if prev_start > start else ""
        if not prev or prev.endswith(SENTENCE_STOP) or (_short(prev) and (not before or _short(before))):
            break
        cur = prev_start
    new_start = cur
    nl = text.find("\n", at_end, end)
    new_end = end
    while nl != -1:
        line_end = text.find("\n", nl + 1, end)
        line = text[nl + 1:line_end if line_end != -1 else end].strip()
        after_end = text.find("\n", line_end + 1, end) if line_end != -1 else -1
        after = text[line_end + 1:after_end if after_end != -1 else end].strip() if line_end != -1 else ""
        if text[:nl].rstrip().endswith(SENTENCE_STOP) or not line or (_short(line) and (not after or _short(after))):
            new_end = nl
            break
        nl = line_end
    return new_start, new_end


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
            start, end = _block_bounds(text, start, end, m.start(), m.end())
            quote = text[start:end].strip(" _•-–|\n")
            # One quote per sentence: "SAP S/4HANA" and "S/4HANA" inside it are the same mention.
            if _short(quote) and not quote.endswith(SENTENCE_STOP):
                continue  # the product's name in a menu or a heading shows nobody using it
            if quote and quote not in out and not any(start < e and s < end for s, e in spans):
                spans.append((start, end))
                out.append(quote)
            if len(out) >= limit * 3:
                break
    # Document order, then the first `limit`.
    out.sort(key=text.find)
    return out[:limit]


def verify_quote(quote: str, text: str) -> bool:
    return bool(quote) and quote in text
