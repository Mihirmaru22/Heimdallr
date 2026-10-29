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


MAX_LINES_BACK = 40
MIN_QUOTE_WORDS = 4


def _ends_block(line: str) -> bool:
    """True when a line of page text ends a block, so the next line starts a new one. Menus, headings and
    titles ("Careers", "Top Workplaces", "Komatsu America Selects PTC's Windchill") end on a capitalised word or
    a number; a sentence that a link or a bold word split across lines ("With both", "and") ends on a lower-case
    word or a comma and carries on."""
    line = line.strip()
    if not line or line[-1] in ".!?:;|•»›)":
        return True
    if line[-1] in ",-–(&/":
        return False
    last = line.split()[-1]
    return not last[0].islower()


def _carries_on(line: str) -> bool:
    """The line continues the one before it: it starts in lower case or with punctuation (", ING found",
    "and"), as when a link or a bold word split a sentence across lines."""
    line = line.lstrip()
    return bool(line) and (line[0].islower() or line[0] in ",.;:)!?%")


def _block_start(text: str, pos: int) -> int:
    """Where the block holding position `pos` starts on the page: after the nearest line break whose line above
    ends a block (0 when the text has no line breaks, as filings read with document_text())."""
    idx = text.rfind("\n", 0, pos)
    for _ in range(MAX_LINES_BACK):
        if idx == -1:
            return 0
        above = text[text.rfind("\n", 0, idx) + 1:idx]
        below = text[idx + 1:(text.find("\n", idx + 1) + 1 or len(text) + 1) - 1]
        if _ends_block(above) and not _carries_on(below):
            return idx + 1
        idx = text.rfind("\n", 0, idx)
    return idx + 1


def _block_end(text: str, pos: int) -> int:
    """Where the block holding position `pos` ends: at the first line break after it whose line ends a block
    and whose next line does not carry on (len(text) when there is none)."""
    idx = text.find("\n", pos)
    for _ in range(MAX_LINES_BACK):
        if idx == -1:
            return len(text)
        line = text[text.rfind("\n", 0, idx) + 1:idx]
        below = text[idx + 1:(text.find("\n", idx + 1) + 1 or len(text) + 1) - 1]
        if _ends_block(line) and not _carries_on(below):
            return idx
        idx = text.find("\n", idx + 1)
    return idx if idx != -1 else len(text)


def _sentence_break(text: str, i: int, width: int) -> bool:
    """A full stop, question or exclamation mark at i ends a sentence only when what follows is not lower case:
    "Komatsu America Corp. has chosen Windchill" is one sentence."""
    if text[i] not in ".?!":
        return True
    nxt = text[i + width:i + width + 1]
    return not nxt.islower()


def _last_break(text: str, pos: int) -> int:
    best = 0
    for b in BREAKS:
        i = text.rfind(b, 0, pos)
        while i != -1 and not _sentence_break(text, i, len(b)):
            i = text.rfind(b, 0, i)
        if i != -1:
            best = max(best, i + len(b))
    return best


def _next_end(text: str, pos: int) -> list[int]:
    ends = []
    for b in (". ", "? ", ".\n", "!\n", "?\n"):
        i = text.find(b, pos)
        while i != -1 and not _sentence_break(text, i, len(b)):
            i = text.find(b, i + 1)
        if i != -1:
            ends.append(i + 1)
    return ends


def find_mentions(text: str, product: Product, limit: int = 3) -> list[str]:
    """Up to `limit` distinct sentences that mention the product, in document order."""
    out: list[str] = []
    spans: list[tuple[int, int]] = []
    for pattern in product.patterns:
        for m in pattern.finditer(text):
            # The sentence around the mention: from the last sentence end, bullet or table rule before it to
            # the next sentence end. A sentence longer than MAX_QUOTE is cut at whole words around the mention,
            # never mid-word ("rgin 21.0 %" was the start of a quote).
            # A page's menus and headings are lines, not sentences: a quote never reaches back past the block the
            # mention is in (one quote was once a 30-line menu ending in the customer's announcement).
            start = max(_last_break(text, m.start()), _block_start(text, m.start()))
            if m.start() - start > MAX_QUOTE // 2:
                start = text.find(" ", m.start() - MAX_QUOTE // 2, m.start()) + 1 or m.start()
            ends = _next_end(text, m.end())
            end = min([*ends, _block_end(text, m.end())])
            if end - m.end() > MAX_QUOTE // 2:
                cut = text.rfind(" ", m.end(), m.end() + MAX_QUOTE // 2)
                end = cut if cut != -1 else m.end()
            quote = text[start:end].strip(" _•-–|")
            # One quote per sentence: "SAP S/4HANA" and "S/4HANA" inside it are the same mention.
            if quote and quote not in out and not any(start < e and s < end for s, e in spans):
                spans.append((start, end))
                out.append(quote)
            if len(out) >= limit * 6:
                break
    # Document order, then the first `limit`; a menu item or heading of a few words ("The NetSuite", "All NetSuite
    # Products") says nothing about anyone using it, so it comes last.
    out.sort(key=lambda q: (len(q.split()) < MIN_QUOTE_WORDS, text.find(q)))
    return sorted(out[:limit], key=text.find)


def verify_quote(quote: str, text: str) -> bool:
    return bool(quote) and quote in text
