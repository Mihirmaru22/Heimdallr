"""Read retrieved pages with a language model running on the user's own machine.

The pattern extractors only find evidence phrased the way they expect. A language model reads a
page the way a person does: the employer of a job post, the customer named in a case study's
title, a fact stated in a table. This reader asks a local model (free: Ollama, or any
OpenAI-compatible local server such as llama.cpp or LM Studio) for findings that answer the
research question, each with a quote copied from the page.

The model never decides what is true. Each quote is matched back to the page text (``snap_quote``);
a quote that is not on the page is dropped. Every finding then goes through the same evidence gate
as any other claim, which checks that the passage is in the cited evidence and names both sides.

Configuration (environment):
    HEIMDALLR_LLM        "ollama:<model>" (e.g. ollama:qwen2.5:7b-instruct) or "openai:<model>"
    HEIMDALLR_LLM_URL    server base URL (default http://localhost:11434 for ollama,
                         http://localhost:8080/v1 for openai-compatible)
    HEIMDALLR_LLM_MAX_PAGES  pages read per run (default 80)
Unset HEIMDALLR_LLM means no model is used and runs behave as before.
"""

from __future__ import annotations

from dataclasses import dataclass
import difflib
import json
import logging
import os
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

CHUNK_CHARS = 6000
CHUNK_OVERLAP = 300
MAX_CHUNKS_PER_PAGE = 3
MAX_QUOTE_CHARS = 500


@dataclass
class ReadFinding:
    subject: str
    relation: str
    value: str
    quote: str
    country: str = ""


_SYSTEM = (
    "You extract facts from ONE web page to answer a research question. Use only the page text; "
    "never use outside knowledge. Reply with JSON only: "
    '{"findings": [{"subject": "...", "relation": "...", "value": "...", "country": "...", "quote": "..."}]}. '
    "quote must be copied exactly from the page: one contiguous passage of at most 400 characters "
    "that names both the subject and the value. country is the country the page states for the subject, "
    "or an empty string. Do not include findings the page only hints at, denies, or presents as a guess. "
    'If the page does not answer the question, reply {"findings": []}.'
)


def _list_instruction(answer_noun: str, object_name: str, geography: str) -> str:
    where = f" in {geography}" if geography else ""
    return (
        f"The question asks for {answer_noun}{where} that use {object_name}. "
        f"Report each organization the page shows using, deploying, implementing or hiring staff for {object_name}: "
        f'subject = the organization\'s name, relation = "uses", value = "{object_name}" '
        "(or the exact product name the page uses). A job post counts: the employer is the subject. "
        "Vendors, consultancies and resellers that only sell or implement it for others are not users; "
        "lists of unnamed 'companies' are not findings."
    )


def snap_quote(quote: str, text: str, min_ratio: float = 0.9) -> str:
    """The passage of ``text`` the model's quote corresponds to, copied from ``text``; else "".

    Small models change whitespace, quotes or punctuation when copying. The returned passage is
    always taken from the page itself, so the evidence gate checks the page's words.
    """
    quote = " ".join((quote or "").split())
    if len(quote) < 12 or not text:
        return ""
    flat = " ".join(text.split())
    idx = flat.lower().find(quote.lower())
    if idx >= 0:
        return flat[idx: idx + len(quote)]
    # Fuzzy: best window of the same length around candidate anchors (the quote's first words).
    anchor = " ".join(quote.split()[:3]).lower()
    starts = [m.start() for m in re.finditer(re.escape(anchor), flat.lower())] or list(range(0, max(1, len(flat) - len(quote) + 1), max(1, len(quote) // 4)))
    best, best_ratio = "", 0.0
    for s in starts[:400]:
        window = flat[s: s + len(quote)]
        ratio = difflib.SequenceMatcher(None, window.lower(), quote.lower()).ratio()
        if ratio > best_ratio:
            best, best_ratio = window, ratio
    return best if best_ratio >= min_ratio else ""


def _chunks(text: str) -> list[str]:
    out, i = [], 0
    while i < len(text) and len(out) < MAX_CHUNKS_PER_PAGE:
        out.append(text[i: i + CHUNK_CHARS])
        i += CHUNK_CHARS - CHUNK_OVERLAP
    return out


def _parse_findings(raw: str) -> list[dict[str, Any]]:
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return []
    items = data.get("findings") if isinstance(data, dict) else None
    return [f for f in items if isinstance(f, dict)] if isinstance(items, list) else []


class LLMReader:
    """Client for a local chat model; ``read`` returns findings grounded in the page text."""

    def __init__(self, backend: str, model: str, base_url: str, timeout: float = 180.0, max_pages: int = 80) -> None:
        self.backend, self.model, self.base_url = backend, model, base_url.rstrip("/")
        self.timeout, self.max_pages = timeout, max_pages
        self.pages_read = 0
        self.failures = 0

    @property
    def label(self) -> str:
        return f"{self.backend}:{self.model}"

    @classmethod
    def from_env(cls) -> "LLMReader | None":
        spec = os.environ.get("HEIMDALLR_LLM", "").strip()
        if not spec or ":" not in spec:
            return None
        backend, model = spec.split(":", 1)
        backend = backend.lower()
        if backend not in ("ollama", "openai"):
            logger.warning("HEIMDALLR_LLM backend %r not supported (use ollama: or openai:)", backend)
            return None
        default_url = "http://localhost:11434" if backend == "ollama" else "http://localhost:8080/v1"
        max_pages = int(os.environ.get("HEIMDALLR_LLM_MAX_PAGES", "80") or 80)
        return cls(backend, model, os.environ.get("HEIMDALLR_LLM_URL", default_url), max_pages=max_pages)

    def _chat(self, system: str, user: str) -> str:
        if self.backend == "ollama":
            resp = httpx.post(
                f"{self.base_url}/api/chat",
                json={"model": self.model, "stream": False, "format": "json", "options": {"temperature": 0},
                      "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return str(resp.json().get("message", {}).get("content", ""))
        resp = httpx.post(
            f"{self.base_url}/chat/completions",
            json={"model": self.model, "temperature": 0,
                  "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return str(resp.json()["choices"][0]["message"]["content"])

    def read(
        self,
        question: str,
        title: str,
        text: str,
        list_target: tuple[str, str, str] | None = None,
    ) -> list[ReadFinding]:
        """Findings on this page that answer ``question``; ``list_target`` = (noun, object, geography)."""
        if not text or self.pages_read >= self.max_pages:
            return []
        self.pages_read += 1
        instruction = _list_instruction(*list_target) if list_target else ""
        findings: list[ReadFinding] = []
        seen: set[tuple[str, str]] = set()
        for chunk in _chunks(text):
            user = f"Research question: {question}\n{instruction}\n\nPage title: {title}\nPage text:\n{chunk}"
            try:
                raw = self._chat(_SYSTEM, user)
            except Exception as exc:
                self.failures += 1
                logger.warning("LLM reader (%s) failed: %s", self.label, exc)
                return findings
            for item in _parse_findings(raw):
                subject = " ".join(str(item.get("subject") or "").split())
                value = " ".join(str(item.get("value") or "").split())
                quote = snap_quote(str(item.get("quote") or "")[:MAX_QUOTE_CHARS], text)
                if not subject or not value or not quote or (subject.lower(), value.lower()) in seen:
                    continue
                seen.add((subject.lower(), value.lower()))
                findings.append(ReadFinding(
                    subject=subject,
                    relation=" ".join(str(item.get("relation") or "").split()) or "related to",
                    value=value,
                    quote=quote,
                    country=" ".join(str(item.get("country") or "").split()),
                ))
        return findings


def relation_predicate(relation: str) -> str:
    """A claim predicate from the model's relation phrase ("is headquartered in" -> "is_headquartered_in")."""
    slug = re.sub(r"[^a-z0-9]+", "_", relation.lower()).strip("_")
    return slug[:40] or "related_to"
