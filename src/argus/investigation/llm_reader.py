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
    HEIMDALLR_LLM        one model or a comma-separated chain, tried in order; a model that is
                         rate-limited or unreachable hands over to the next for the rest of the run:
                           "ollama:<model>"      local Ollama (e.g. ollama:qwen2.5:7b)
                           "openrouter:<model>"  OpenRouter, e.g. a free model whose id ends in
                                                 ":free" (key: OPENROUTER_API_KEY or .env)
                           "openai:<model>"      any OpenAI-compatible local server
                         e.g. "openrouter:qwen/qwen-2.5-72b-instruct:free,ollama:qwen2.5:7b"
    HEIMDALLR_LLM_URL    base URL for ollama/openai backends (defaults http://localhost:11434,
                         http://localhost:8080/v1)
    HEIMDALLR_LLM_MAX_PAGES  pages read per run (default 80)
Unset HEIMDALLR_LLM means no model is used and runs behave as before.

OpenRouter free models allow 20 requests a minute and 50 a day (1,000 a day once 10 credits
have been bought); the reader spaces its calls and falls back to the next model when refused.
"""

from __future__ import annotations

from dataclasses import dataclass
import difflib
import json
import logging
import os
import re
import time
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


class ModelUnavailable(Exception):
    """The model refused (rate limit, quota) or could not be reached; the next model takes over."""


OPENROUTER_URL = "https://openrouter.ai/api/v1"
# OpenRouter free models: 20 requests per minute.
OPENROUTER_MIN_INTERVAL = 3.1


def _openrouter_key() -> str:
    from argus.llm.openrouter import OpenRouterLLMProvider  # reads OPENROUTER_API_KEY / OPEN_ROUTER_API / .env

    return OpenRouterLLMProvider().api_key


class LLMReader:
    """Client for one chat model; ``read`` returns findings grounded in the page text."""

    def __init__(self, backend: str, model: str, base_url: str, timeout: float = 180.0, max_pages: int = 80, api_key: str = "", service: Any = None) -> None:
        self.service = service  # the shared FreeModelService, when reading goes through it
        self.backend, self.model, self.base_url = backend, model, base_url.rstrip("/")
        self.timeout, self.max_pages = timeout, max_pages
        self.api_key = api_key
        self.pages_read = 0
        self.failures = 0
        self._last_call = 0.0
        self.in_chain = False  # inside a ReaderChain, refusals are passed up so the next model reads
        self.disabled = False

    @property
    def label(self) -> str:
        return self.model if self.service is not None else f"{self.backend}:{self.model}"

    @classmethod
    def from_spec(cls, spec: str, max_pages: int = 80) -> "LLMReader | None":
        backend, _, model = spec.strip().partition(":")
        backend = backend.lower()
        if not model:
            return None
        if backend == "ollama":
            return cls(backend, model, os.environ.get("HEIMDALLR_LLM_URL", "http://localhost:11434"), max_pages=max_pages)
        if backend == "openai":
            return cls(backend, model, os.environ.get("HEIMDALLR_LLM_URL", "http://localhost:8080/v1"), max_pages=max_pages)
        if backend == "openrouter":
            from argus.llm.free_models import require_free

            model = require_free(model)
            key = _openrouter_key()
            if not key:
                logger.warning("openrouter:%s skipped: no OPENROUTER_API_KEY", model)
                return None
            return cls(backend, model, OPENROUTER_URL, timeout=90.0, max_pages=max_pages, api_key=key)
        logger.warning("HEIMDALLR_LLM backend %r not supported (use ollama:, openrouter: or openai:)", backend)
        return None

    @staticmethod
    def from_env() -> "LLMReader | ReaderChain | None":
        specs = [p for p in os.environ.get("HEIMDALLR_LLM", "").split(",") if p.strip()]
        max_pages = int(os.environ.get("HEIMDALLR_LLM_MAX_PAGES", "80") or 80)
        if not specs:
            # Default: the project-wide free-model service (OpenRouter free models, then local qwen).
            from argus.llm.free_models import get_free_model_service

            service = get_free_model_service()
            return LLMReader("service", service.label, "", max_pages=max_pages, service=service) if service else None
        readers = [r for r in (LLMReader.from_spec(p, max_pages) for p in specs) if r is not None]
        if not readers:
            return None
        return readers[0] if len(readers) == 1 else ReaderChain(readers, max_pages=max_pages)

    def _chat(self, system: str, user: str) -> str:
        if self.service is not None:
            from argus.llm.free_models import ModelUnavailable as ServiceUnavailable

            try:
                return self.service.chat(system, user, json_mode=True)
            except ServiceUnavailable as exc:
                raise ModelUnavailable(str(exc)) from exc
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        try:
            if self.backend == "ollama":
                resp = httpx.post(
                    f"{self.base_url}/api/chat",
                    json={"model": self.model, "stream": False, "format": "json", "options": {"temperature": 0}, "messages": messages},
                    timeout=self.timeout,
                )
            else:
                headers = {}
                if self.backend == "openrouter":
                    wait = OPENROUTER_MIN_INTERVAL - (time.monotonic() - self._last_call)
                    if wait > 0:
                        time.sleep(wait)
                    self._last_call = time.monotonic()
                    headers = {"Authorization": f"Bearer {self.api_key}", "X-Title": "Heimdallr Research"}
                resp = httpx.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json={"model": self.model, "temperature": 0, "messages": messages},
                    timeout=self.timeout,
                )
        except httpx.HTTPError as exc:
            raise ModelUnavailable(f"{self.label} unreachable: {exc}") from exc
        if resp.status_code in (401, 402, 403, 404, 429) or resp.status_code >= 500:
            raise ModelUnavailable(f"{self.label} refused: HTTP {resp.status_code} {resp.text[:200]}")
        resp.raise_for_status()
        data = resp.json()
        if self.backend == "ollama":
            return str(data.get("message", {}).get("content", ""))
        if data.get("error"):
            raise ModelUnavailable(f"{self.label} error: {data['error']}")
        return str(data["choices"][0]["message"]["content"])

    def read(
        self,
        question: str,
        title: str,
        text: str,
        list_target: tuple[str, str, str] | None = None,
    ) -> list[ReadFinding]:
        """Findings on this page that answer ``question``; ``list_target`` = (noun, object, geography)."""
        if not text or self.disabled or self.pages_read >= self.max_pages:
            return []
        self.pages_read += 1
        instruction = _list_instruction(*list_target) if list_target else ""
        findings: list[ReadFinding] = []
        seen: set[tuple[str, str]] = set()
        for chunk in _chunks(text):
            user = f"Research question: {question}\n{instruction}\n\nPage title: {title}\nPage text:\n{chunk}"
            try:
                raw = self._chat(_SYSTEM, user)
            except ModelUnavailable as exc:
                self.failures += 1
                if self.in_chain:
                    raise
                logger.warning("%s; page reading is off for the rest of this run", exc)
                self.disabled = True
                return findings
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


class ReaderChain:
    """Several models in order of preference. A model that is rate-limited or unreachable is
    dropped for the rest of the run and the page is read by the next one."""

    def __init__(self, readers: list[LLMReader], max_pages: int = 80) -> None:
        self.readers, self.max_pages = readers, max_pages
        for r in readers:
            r.in_chain = True
        self.pages_read = 0
        self.exhausted: list[str] = []

    @property
    def failures(self) -> int:
        return sum(r.failures for r in self.readers)

    @property
    def label(self) -> str:
        return " > ".join(r.label for r in self.readers)

    def read(self, question: str, title: str, text: str, list_target: tuple[str, str, str] | None = None) -> list[ReadFinding]:
        if not text or self.pages_read >= self.max_pages:
            return []
        self.pages_read += 1
        for reader in self.readers:
            if reader.label in self.exhausted:
                continue
            try:
                reader.pages_read = 0  # the chain enforces the page budget
                return reader.read(question, title, text, list_target=list_target)
            except ModelUnavailable as exc:
                logger.warning("%s; switching to the next model", exc)
                self.exhausted.append(reader.label)
        return []


def relation_predicate(relation: str) -> str:
    """A claim predicate from the model's relation phrase ("is headquartered in" -> "is_headquartered_in")."""
    slug = re.sub(r"[^a-z0-9]+", "_", relation.lower()).strip("_")
    return slug[:40] or "related_to"
