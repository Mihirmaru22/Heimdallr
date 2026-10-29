"""One web-search layer for the whole project.

Discovery, case studies, news and website lookups all ask a `SearchHub` instead of calling a search engine
themselves. The hub asks every backend that is configured, in parallel, and merges the answers so one engine's
gaps do not become ours: the free search APIs (Keenable, Tavily, Linkup, Exa) and the self-hosted SearXNG.

Rules kept here, not scattered in callers:
- Free only. Only the cheapest plain-search mode of each API is used, and a monthly counter (counts, never
  results) stops each paid-credit API before its free allowance runs out.
- A backend that fails over and over, or runs out of credit, is switched off for the rest of the process and
  says so in `hub.problems`; the others carry on. Nothing is cached: every search is a live request.
- Search results are leads only. Nothing here decides whether a page is true.
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.config import get_settings
from app.crawl.urlnorm import normalize_url

log = logging.getLogger(__name__)

# Which kinds of question a backend is asked. "lookup" (one company's website) stays on free, uncapped engines.
GENERAL, EVIDENCE, LOOKUP = "general", "evidence", "lookup"
# Proof searches for one named company ("Farmers Insurance" "Guidewire"): many per job, so only the engines
# without a monthly cap are asked.
TARGETED = "targeted"
FAILS_BEFORE_OFF = 5
COOLDOWN_SECONDS = 60.0
MAX_HITS = 30
TOP_UP_BELOW = 10  # the fallback engine is asked only when the others gave fewer distinct results than this


# One job's searches, reused within that job only (never across jobs): a query asked twice in a run gets the
# same answer, so which pages are read does not change mid-run. Set by the crawler for the length of a job.
JOB_CACHE: contextvars.ContextVar[dict | None] = contextvars.ContextVar("search_job_cache", default=None)


class SearchError(Exception):
    """No configured backend could answer."""


@dataclass(frozen=True)
class Hit:
    url: str
    title: str = ""
    snippet: str = ""
    provider: str = ""


class BackendOff(Exception):
    """This backend must stop being used (bad key, no credit left)."""


class Backend:
    name = ""
    kinds: tuple[str, ...] = (GENERAL, EVIDENCE)
    pages = 1  # result pages it can give; more pages only where this is above 1
    fallback = False  # asked only to top up what the others gave
    monthly_cap: int | None = None  # calls per month we allow ourselves (None = no counter)

    async def search(self, client: httpx.AsyncClient, query: str, page: int) -> list[Hit]:
        raise NotImplementedError

    @staticmethod
    def check(resp: httpx.Response, quota_codes: tuple[int, ...] = ()) -> None:
        if resp.status_code in (401, 403):
            raise BackendOff("the key was refused")
        if resp.status_code in quota_codes:
            raise BackendOff("the free allowance is used up")
        resp.raise_for_status()


class SearxngBackend(Backend):
    """Self-hosted, so free, but it scrapes engines that block it after a busy day: it only tops up."""

    name = "searxng"
    kinds = (GENERAL, EVIDENCE, LOOKUP, TARGETED)
    pages = 5
    fallback = True

    def __init__(self, url: str) -> None:
        self.url = url.rstrip("/")

    async def search(self, client, query, page):
        resp = await client.get(f"{self.url}/search", params={
            "q": query, "format": "json", "pageno": page, "language": "en", "safesearch": 1})
        if resp.status_code == 403:
            raise BackendOff("SearXNG refused JSON output; enable `json` under search.formats")
        resp.raise_for_status()
        return [Hit(r.get("url", ""), r.get("title", ""), r.get("content", ""), self.name)
                for r in resp.json().get("results", []) if r.get("url")]


class KeenableBackend(Backend):
    """The keyless public endpoint (no credits; the shared pool allows 1,000 calls an hour per address)."""

    name = "keenable"
    kinds = (GENERAL, EVIDENCE, LOOKUP, TARGETED)

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key

    async def search(self, client, query, page):
        if self.api_key:
            resp = await client.post("https://api.keenable.ai/v1/search", json={"query": query},
                                     headers={"X-API-Key": self.api_key})
        else:
            resp = await client.post("https://api.keenable.ai/v1/search/public", json={"query": query},
                                     headers={"X-Keenable-Title": "webdata-ai"})
        self.check(resp, quota_codes=(402,))
        return [Hit(r.get("url", ""), r.get("title", ""), r.get("snippet") or r.get("description") or "", self.name)
                for r in resp.json().get("results", []) if r.get("url")]


class TavilyBackend(Backend):
    name = "tavily"
    monthly_cap = 950  # of 1,000 free credits; a basic search costs 1

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def search(self, client, query, page):
        resp = await client.post("https://api.tavily.com/search", headers={"Authorization": f"Bearer {self.api_key}"},
                                 json={"query": query, "search_depth": "basic", "max_results": 10})
        self.check(resp, quota_codes=(432, 433))
        return [Hit(r.get("url", ""), r.get("title", ""), r.get("content", ""), self.name)
                for r in resp.json().get("results", []) if r.get("url")]


class LinkupBackend(Backend):
    name = "linkup"
    monthly_cap = 3800  # of about 4,000 searches in the $20 credit; a standard search costs $0.005

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def search(self, client, query, page):
        resp = await client.post("https://api.linkup.so/v1/search", headers={"Authorization": f"Bearer {self.api_key}"},
                                 json={"q": query, "depth": "standard", "outputType": "searchResults"}, timeout=60)
        self.check(resp)
        return [Hit(r.get("url", ""), r.get("name", ""), (r.get("content") or "")[:400], self.name)
                for r in resp.json().get("results", []) if r.get("type") == "text" and r.get("url")][:10]


class ExaBackend(Backend):
    """Best at finding the pages about a product (case studies, news), not at company lists."""

    name = "exa"
    kinds = (EVIDENCE,)
    monthly_cap = 2300  # of about 2,500 calls in the $10 credit; the cheap `lite` mode costs $0.004

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def search(self, client, query, page):
        resp = await client.post("https://api.exa.ai/search", headers={"x-api-key": self.api_key},
                                 json={"query": query, "type": "lite", "numResults": 10})
        self.check(resp, quota_codes=(402,))
        return [Hit(r.get("url", ""), r.get("title", ""), "", self.name)
                for r in resp.json().get("results", []) if r.get("url")]


class Usage:
    """How many calls each capped API has had this month. Counts only, in a small file; never search results."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path if path is not None else Path(get_settings().data_dir) / "search_usage.json"
        self.counts: dict[str, int] = {}
        self.month = ""
        self._load()

    def _load(self) -> None:
        self.month = datetime.now(UTC).strftime("%Y-%m")
        try:
            data = json.loads(self.path.read_text())
            self.counts = {k: int(v) for k, v in data.get(self.month, {}).items()}
        except (OSError, ValueError, AttributeError):
            self.counts = {}

    def used(self, name: str) -> int:
        if datetime.now(UTC).strftime("%Y-%m") != self.month:
            self._load()
        return self.counts.get(name, 0)

    def add(self, name: str) -> None:
        self.counts[name] = self.used(name) + 1
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({self.month: self.counts}))
        except OSError:
            log.warning("could not write the search usage counter")


def _key(url: str) -> str:
    norm = normalize_url(url) or url
    scheme_less = norm.split("://", 1)[-1].lower()
    return scheme_less.removeprefix("www.").rstrip("/").split("#", 1)[0]


class SearchHub:
    def __init__(self, client: httpx.AsyncClient, backends: list[Backend], usage: Usage | None = None) -> None:
        self.client = client
        self.backends = backends
        self.usage = usage if usage is not None else Usage()
        self.problems: dict[str, str] = {}  # backend name -> why it is off
        self.calls: dict[str, int] = {}  # backend name -> calls this process made
        self._fails: dict[str, int] = {}
        self._cool: dict[str, float] = {}

    @classmethod
    def from_settings(cls, client: httpx.AsyncClient, searxng_url: str | None = None) -> SearchHub:
        s = get_settings()
        url = (searxng_url if searxng_url is not None else s.searxng_url).strip()
        backends: list[Backend] = []
        if s.keenable_enabled:
            backends.append(KeenableBackend(s.keenable_api_key.get_secret_value() if s.keenable_use_key else ""))
        if key := s.tavily_api_key.get_secret_value():
            backends.append(TavilyBackend(key))
        if key := s.linkup_api_key.get_secret_value():
            backends.append(LinkupBackend(key))
        if key := s.exa_api_key.get_secret_value():
            backends.append(ExaBackend(key))
        if url:
            backends.append(SearxngBackend(url))
        return cls(client, backends)

    @property
    def configured(self) -> bool:
        return bool(self.backends)

    def _usable(self, backend: Backend, kind: str, page: int) -> bool:
        if kind not in backend.kinds or page > backend.pages or backend.name in self.problems:
            return False
        if self._cool.get(backend.name, 0) > time.monotonic():
            return False
        return backend.monthly_cap is None or self.usage.used(backend.name) < backend.monthly_cap

    async def _ask(self, backend: Backend, query: str, page: int) -> list[Hit]:
        self.calls[backend.name] = self.calls.get(backend.name, 0) + 1
        if backend.monthly_cap is not None:
            self.usage.add(backend.name)
        try:
            hits = await backend.search(self.client, query, page)
        except BackendOff as exc:
            self.problems[backend.name] = str(exc)
            log.warning("search backend %s switched off: %s", backend.name, exc)
            return []
        except (httpx.HTTPError, ValueError) as exc:
            status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else 0
            self._fails[backend.name] = self._fails.get(backend.name, 0) + 1
            if status == 429:
                self._cool[backend.name] = time.monotonic() + COOLDOWN_SECONDS
            if self._fails[backend.name] >= FAILS_BEFORE_OFF:
                self.problems[backend.name] = f"failed {FAILS_BEFORE_OFF} times in a row ({type(exc).__name__})"
            return []
        self._fails[backend.name] = 0
        return hits

    async def search(self, query: str, *, page: int = 1, kind: str = GENERAL) -> list[Hit]:
        """Hits from the search APIs, merged; SearXNG only tops up when they give too little. Within a job, a
        query asked before is answered from that job's own record of it."""
        cache = JOB_CACHE.get()
        key = (kind, " ".join(query.split()).casefold(), page)
        if cache is not None and key in cache:
            return list(cache[key])
        hits = await self._search(query, page=page, kind=kind)
        if cache is not None:
            cache[key] = list(hits)
        return hits

    async def _search(self, query: str, *, page: int = 1, kind: str = GENERAL) -> list[Hit]:
        active = [b for b in self.backends if self._usable(b, kind, page)]
        if not active:
            if page == 1:
                raise SearchError(self.explain(kind))
            return []
        asked = [b for b in active if not b.fallback] or active
        answers = list(await asyncio.gather(*(self._ask(b, query, page) for b in asked)))
        merged = self._merge(answers, kind)
        rest = [b for b in active if b not in asked]
        if rest and len(merged) < TOP_UP_BELOW:
            asked += rest
            extra = self._merge(list(await asyncio.gather(*(self._ask(b, query, page) for b in rest))), kind)
            have = {_key(h.url) for h in merged}
            merged += [h for h in extra if kind == LOOKUP or _key(h.url) not in have]
        if page == 1 and not merged and all(b.name in self.problems for b in asked):
            raise SearchError(self.explain(kind))
        return merged[:MAX_HITS]

    @staticmethod
    def _merge(answers: list[list[Hit]], kind: str) -> list[Hit]:
        """One hit from each engine in turn, so no engine crowds out the rest; repeats dropped except for a
        website lookup, where several engines giving the same address is the agreement the caller counts."""
        merged: list[Hit] = []
        seen: set[str] = set()
        for rank in range(max((len(a) for a in answers), default=0)):
            for hits in answers:
                if rank >= len(hits):
                    continue
                key = _key(hits[rank].url)
                if kind != LOOKUP and key in seen:
                    continue
                seen.add(key)
                merged.append(hits[rank])
        return merged

    def explain(self, kind: str = GENERAL) -> str:
        if not self.backends:
            return "web search is not configured (set a search API key or WEBDATA_SEARXNG_URL)"
        reasons = []
        for b in self.backends:
            if kind not in b.kinds:
                continue
            if b.name in self.problems:
                reasons.append(f"{b.name}: {self.problems[b.name]}")
            elif b.monthly_cap is not None and self.usage.used(b.name) >= b.monthly_cap:
                reasons.append(f"{b.name}: this month's free allowance is used")
            elif self._cool.get(b.name, 0) > time.monotonic():
                reasons.append(f"{b.name}: rate limited, retrying shortly")
        return f"web search is unavailable ({'; '.join(reasons) or 'no search backend for this kind of query'})"


def search_configured(searxng_url: str | None = None) -> bool:
    """True when at least one search backend could be used (so callers can skip early with a clear note)."""
    s = get_settings()
    return bool((searxng_url if searxng_url is not None else s.searxng_url).strip() or s.keenable_enabled
                or s.tavily_api_key.get_secret_value() or s.linkup_api_key.get_secret_value()
                or s.exa_api_key.get_secret_value())
