"""One polite, bounded, SSRF-checked page fetch, with redirects followed hop by hop."""

from __future__ import annotations

import asyncio
import hashlib
import html
import io
import logging
import random
import time
from dataclasses import dataclass, field

import httpx

from app.config import get_settings
from app.crawl.netguard import BlockedDestination, check_url
from app.crawl.urlnorm import normalize_url

log = logging.getLogger("webdata.fetch")

HTML_TYPES = ("text/html", "application/xhtml+xml")
TEXT_TYPES = HTML_TYPES + ("text/plain", "application/xml", "text/xml")
PDF_TYPES = ("application/pdf",)
# Documents a discovery source reads for proof: many case studies and customer stories are published as PDFs.
DOCUMENT_TYPES = HTML_TYPES + PDF_TYPES
MAX_PDF_PAGES = 40
RETRY_STATUSES = {408, 425, 429, 500, 502, 503, 504}


class FetchError(Exception):
    def __init__(self, kind: str, message: str, retryable: bool) -> None:
        super().__init__(message)
        self.kind, self.retryable = kind, retryable


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int
    content_type: str
    body: bytes
    redirects: list[str] = field(default_factory=list)
    elapsed: float = 0.0
    # Response headers, lower-cased names, kept in memory only (they can carry cookies): never logged or stored.
    headers: list[tuple[str, str]] = field(default_factory=list)

    @property
    def text(self) -> str:
        charset = "utf-8"
        if "charset=" in self.content_type:
            charset = self.content_type.split("charset=")[-1].split(";")[0].strip() or "utf-8"
        try:
            return self.body.decode(charset, errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()

    @property
    def is_html(self) -> bool:
        return self.content_type.split(";")[0].strip().lower() in HTML_TYPES

    @property
    def is_pdf(self) -> bool:
        return self.content_type.split(";")[0].strip().lower() in PDF_TYPES or self.body[:5] == b"%PDF-"

    def html(self) -> str:
        """The page as HTML: a PDF's text becomes one paragraph per line, so it is read like any page."""
        return pdf_html(self.body) if self.is_pdf else self.text


def pdf_html(body: bytes) -> str:
    """A PDF's text as a minimal HTML page ("" when it has no extractable text, e.g. a scanned image)."""
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(body))
        title = str((reader.metadata or {}).get("/Title") or "")
        lines = [line.strip() for page in reader.pages[:MAX_PDF_PAGES]
                 for line in (page.extract_text() or "").splitlines()]
    except Exception as exc:  # noqa: BLE001 - a broken PDF is a page without text, not a crash
        log.info("PDF could not be read: %s", type(exc).__name__)
        return ""
    body_html = "".join(f"<p>{html.escape(line)}</p>" for line in lines if line)
    return f"<html><head><title>{html.escape(title)}</title></head><body>{body_html}</body></html>" if body_html else ""


class Fetcher:
    def __init__(self, client: httpx.AsyncClient, politeness=None, resolver=None,
                 allowed_types: tuple[str, ...] = HTML_TYPES) -> None:
        self.client = client
        self.politeness = politeness
        self.resolver = resolver
        self.allowed_types = allowed_types
        self.settings = get_settings()

    def _check(self, url: str) -> None:
        if self.resolver is not None:
            check_url(url, resolver=self.resolver)
        else:
            check_url(url)

    async def _once(self, url: str) -> FetchResult:
        s = self.settings
        start = time.monotonic()
        redirects: list[str] = []
        current = url
        for _hop in range(s.max_redirects + 1):
            try:
                self._check(current)
            except BlockedDestination as exc:
                raise FetchError("blocked", str(exc), retryable=False) from None
            if self.politeness is not None:
                await self.politeness.wait(current)
            try:
                async with self.client.stream("GET", current) as resp:
                    if resp.status_code in (301, 302, 303, 307, 308):
                        location = resp.headers.get("location")
                        nxt = normalize_url(location, base=current) if location else None
                        if not nxt:
                            raise FetchError("redirect", "redirect without a usable Location", retryable=False)
                        redirects.append(current)
                        current = nxt
                        continue
                    ctype = resp.headers.get("content-type", "")
                    if resp.status_code in RETRY_STATUSES:
                        retry_after = resp.headers.get("retry-after", "")
                        raise FetchError(f"http_{resp.status_code}", retry_after, retryable=True)
                    if resp.status_code >= 400:
                        raise FetchError(f"http_{resp.status_code}", f"HTTP {resp.status_code}", retryable=False)
                    base_type = ctype.split(";")[0].strip().lower()
                    if base_type and base_type not in self.allowed_types:
                        raise FetchError("content_type", f"skipped content type {base_type}", retryable=False)
                    declared = resp.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > s.max_page_bytes:
                        raise FetchError("too_large", f"page is {declared} bytes", retryable=False)
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in resp.aiter_bytes():
                        size += len(chunk)
                        if size > s.max_page_bytes:
                            raise FetchError("too_large", f"page exceeds {s.max_page_bytes} bytes",
                                             retryable=False)
                        chunks.append(chunk)
                    return FetchResult(url, current, resp.status_code, ctype, b"".join(chunks), redirects,
                                       time.monotonic() - start,
                                       [(k.lower(), v) for k, v in resp.headers.multi_items()])
            except httpx.TimeoutException:
                log.info("fetch timed out: %s", current)
                raise FetchError("timeout", "timed out", retryable=True) from None
            except httpx.TransportError as exc:
                if isinstance(exc.__cause__, BlockedDestination) or "non-public" in str(exc):
                    raise FetchError("blocked", str(exc), retryable=False) from None
                # No HTTP response means no "HTTP Request" log line either: without this, a site that drops
                # the connection leaves no trace at all.
                log.info("fetch failed (%s: %s): %s", type(exc).__name__, str(exc)[:200], current)
                raise FetchError("network", type(exc).__name__, retryable=True) from None
            except FetchError:
                raise
            except Exception as exc:  # noqa: BLE001 - one page's failure is that page's, never the job's
                # Anything else the request could not survive (a header the HTTP library will not encode, a
                # malformed answer) makes this page unreadable; a UnicodeEncodeError on one news page once failed
                # a whole job (2026-10-30).
                log.warning("fetch failed (%s: %s): %s", type(exc).__name__, str(exc)[:200], current)
                raise FetchError("request", type(exc).__name__, retryable=False) from None
        raise FetchError("redirect", "too many redirects", retryable=False)

    async def fetch(self, url: str, attempts: int | None = None) -> FetchResult:
        """Fetch with bounded retries, exponential backoff and jitter."""
        attempts = attempts or self.settings.url_retry_limit
        for attempt in range(1, attempts + 1):
            try:
                return await self._once(url)
            except FetchError as exc:
                if not exc.retryable or attempt == attempts:
                    raise
                delay = min(2 ** attempt, 30) * (0.5 + random.random())
                if exc.kind == "http_429" and str(exc).isdigit():
                    delay = max(delay, min(int(str(exc)), 60))
                await asyncio.sleep(delay if self.settings.env != "test" else 0)
        raise AssertionError("unreachable")
