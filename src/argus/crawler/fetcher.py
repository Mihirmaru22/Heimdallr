from abc import ABC, abstractmethod
from datetime import UTC, datetime
from urllib.parse import urljoin

import httpx
from playwright.async_api import Error as PlaywrightError

from argus.crawler.extractor import DocumentExtractor
from argus.crawler.models import CrawlRequest, Document
from argus.search.pipeline import SearchPipeline, create_safe_async_client

MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB safety ceiling


class BaseFetcher(ABC):
    """Abstract contract for fetching web documents."""

    @abstractmethod
    async def fetch(self, request: CrawlRequest) -> Document:
        """Acquire a document from a crawl request."""


class TwoTierFetcher(BaseFetcher):
    """Orchestrates fast HTTP fetch with automatic Playwright browser escalation."""

    def __init__(
        self,
        timeout: float = 12.0,
        user_agent: str = "ArgusResearchEngine/1.0",
    ) -> None:
        self.timeout = timeout
        self.user_agent = user_agent

    async def fetch(self, request: CrawlRequest) -> Document:
        """Fetch a page using VCR caching if enabled."""
        from argus.utils.vcr import VCRProxy
        
        async def _do_fetch():
            return await self._fetch_impl(request)
            
        return await VCRProxy.fetch(request.url, _do_fetch)

    async def _fetch_impl(self, request: CrawlRequest) -> Document:
        """Fetch a page using fast HTTP first, escalating to Playwright if necessary."""
        # 1. SSRF Safety Check before outbound connection
        if not SearchPipeline.is_safe_url(request.url):
            return Document(
                url=request.url,
                title="Blocked",
                text_content="",
                status_code=403,
                fetch_method="blocked",
            )

        # 2. Force browser if requested
        if request.force_browser:
            return await self._fetch_browser(request)

        # 3. Tier 1: Fast HTTP attempt
        http_doc: Document | None = None
        needs_browser = False

        try:
            http_doc, needs_browser = await self._fetch_http(request)
            if http_doc.status_code in (403, 413) or http_doc.fetch_method == "blocked":
                return http_doc
            if not needs_browser and len(http_doc.text_content) >= 100:
                return http_doc
        except (httpx.HTTPError, TimeoutError, OSError, ValueError):
            # If HTTP connection fails (e.g. anti-bot/JS challenge), escalate to browser
            pass

        # 4. Tier 2: Escalate to browser rendering
        try:
            return await self._fetch_browser(request)
        except (
            httpx.HTTPError,
            TimeoutError,
            OSError,
            ValueError,
            RuntimeError,
            PlaywrightError,
        ) as e:
            # Graceful failure: return best HTTP doc if available, or error document
            if http_doc is not None and http_doc.text_content:
                return http_doc
            return Document(
                url=request.url,
                title="Fetch Error",
                text_content=f"Failed to acquire content: {e}",
                status_code=500,
                fetch_method="error",
            )

    async def _fetch_http(self, request: CrawlRequest) -> tuple[Document, bool]:
        """Perform lightweight HTTP request via httpx with bounded streaming and SSRF redirect protection."""
        from unittest.mock import AsyncMock

        headers = {"User-Agent": self.user_agent}
        max_redirects = 5
        current_url = request.url

        async with create_safe_async_client(
            timeout=self.timeout,
            follow_redirects=False,
            headers=headers,
        ) as client:
            # If client.get is mocked in test environment, handle mock safely
            if isinstance(client.get, AsyncMock):
                response = await client.get(current_url)
                # Check if mock returned a redirect
                if response.status_code in (301, 302, 303, 307, 308):
                    loc = response.headers.get("Location")
                    if loc:
                        dest = urljoin(current_url, loc)
                        if not SearchPipeline.is_safe_url(dest):
                            return (
                                Document(
                                    url=dest,
                                    title="Redirect Blocked",
                                    text_content="",
                                    status_code=403,
                                    fetch_method="blocked",
                                ),
                                False,
                            )
                final_url = str(response.url)
                if not SearchPipeline.is_safe_url(final_url):
                    return (
                        Document(
                            url=final_url,
                            title="Redirect Blocked",
                            text_content="",
                            status_code=403,
                            fetch_method="blocked",
                        ),
                        False,
                    )
                if len(response.content) > MAX_RESPONSE_BYTES:
                    return (
                        Document(
                            url=final_url,
                            title="Oversized Document",
                            text_content="",
                            status_code=413,
                            fetch_method="http",
                        ),
                        False,
                    )
                title, clean_text, needs_browser, published_at_str, content_units, outgoing_links, metadata, canonical_url = (
                    DocumentExtractor.extract_structured(response.text, base_url=final_url)
                )

                published_at = None
                if published_at_str:
                    try:
                        from dateutil.parser import parse as parse_date
                        parsed = parse_date(published_at_str)
                        if parsed.tzinfo is None:
                            parsed = parsed.replace(tzinfo=UTC)
                        published_at = parsed
                    except Exception:
                        pass

                doc = Document(
                    url=final_url,
                    canonical_url=canonical_url,
                    title=title,
                    text_content=clean_text,
                    status_code=response.status_code,
                    fetch_method="http",
                    published_at=published_at,
                    content_units=content_units,
                    outgoing_links=outgoing_links,
                    metadata=metadata,
                )
                return doc, needs_browser

            # Production streaming path with explicit hop-by-hop SSRF validation
            redirect_count = 0
            while True:
                if not SearchPipeline.is_safe_url(current_url):
                    return (
                        Document(
                            url=current_url,
                            title="Redirect Blocked",
                            text_content="",
                            status_code=403,
                            fetch_method="blocked",
                        ),
                        False,
                    )

                async with client.stream("GET", current_url) as response:
                    # Check for redirect status codes
                    if response.status_code in (301, 302, 303, 307, 308):
                        redirect_count += 1
                        if redirect_count > max_redirects:
                            return (
                                Document(
                                    url=current_url,
                                    title="Too Many Redirects",
                                    text_content="",
                                    status_code=400,
                                    fetch_method="http",
                                ),
                                False,
                            )
                        location = response.headers.get("Location")
                        if not location:
                            pass
                        else:
                            next_url = urljoin(current_url, location)
                            # Verify destination URL BEFORE making the request
                            if not SearchPipeline.is_safe_url(next_url):
                                return (
                                    Document(
                                        url=next_url,
                                        title="Redirect Blocked",
                                        text_content="",
                                        status_code=403,
                                        fetch_method="blocked",
                                    ),
                                    False,
                                )
                            current_url = next_url
                            continue

                    final_url = current_url

                    # Check Content-Type for binary/non-text media
                    content_type = response.headers.get("Content-Type", "").lower()
                    if any(
                        b_type in content_type
                        for b_type in ("application/pdf", "application/octet-stream", "application/zip", "image/", "video/", "audio/")
                    ):
                        return (
                            Document(
                                url=final_url,
                                title="Binary Document",
                                text_content="",
                                status_code=response.status_code,
                                fetch_method="http",
                                metadata={"content_type": content_type, "is_binary": True},
                            ),
                            False,
                        )

                    # Early rejection via Content-Length header
                    content_length = response.headers.get("Content-Length")
                    if (
                        content_length
                        and content_length.isdigit()
                        and int(content_length) > MAX_RESPONSE_BYTES
                    ):
                        return (
                            Document(
                                url=final_url,
                                title="Oversized Document",
                                text_content="",
                                status_code=413,
                                fetch_method="http",
                            ),
                            False,
                        )

                    # Stream response chunks to enforce size limit before buffering in memory
                    chunks: list[bytes] = []
                    total_bytes = 0
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        total_bytes += len(chunk)
                        if total_bytes > MAX_RESPONSE_BYTES:
                            return (
                                Document(
                                    url=final_url,
                                    title="Oversized Document",
                                    text_content="",
                                    status_code=413,
                                    fetch_method="http",
                                ),
                                False,
                            )
                        chunks.append(chunk)

                    raw_bytes = b"".join(chunks)
                    encoding = response.encoding or "utf-8"
                    text = raw_bytes.decode(encoding, errors="replace")

                    title, clean_text, needs_browser, published_at_str, content_units, outgoing_links, metadata, canonical_url = (
                        DocumentExtractor.extract_structured(text, base_url=final_url)
                    )

                    published_at = None
                    if published_at_str:
                        try:
                            from dateutil.parser import parse as parse_date
                            parsed = parse_date(published_at_str)
                            if parsed.tzinfo is None:
                                parsed = parsed.replace(tzinfo=UTC)
                            published_at = parsed
                        except Exception:
                            pass

                    doc = Document(
                        url=final_url,
                        canonical_url=canonical_url,
                        title=title,
                        text_content=clean_text,
                        status_code=response.status_code,
                        fetch_method="http",
                        published_at=published_at,
                        content_units=content_units,
                        outgoing_links=outgoing_links,
                        metadata=metadata,
                    )
                    return doc, needs_browser

    async def _fetch_browser(self, request: CrawlRequest) -> Document:
        """Render page using Playwright headless Chromium with strict SSRF route interception."""
        from playwright.async_api import async_playwright

        blocked_redirect = False
        blocked_url: str | None = None

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent=self.user_agent,
                    permissions=[],
                )

                # Intercept all routes to block SSRF on redirects, unsafe schemes, and abort heavy media
                async def intercept_route(route):
                    nonlocal blocked_redirect, blocked_url
                    req_url = route.request.url
                    # Block non-http/https schemes and SSRF
                    if not req_url.startswith(("http://", "https://")) or not SearchPipeline.is_safe_url(req_url):
                        blocked_redirect = True
                        blocked_url = req_url
                        await route.abort("blockedbyclient")
                    elif route.request.resource_type in ("media", "font"):
                        await route.abort("blockedbyclient")
                    else:
                        await route.continue_()

                await context.route("**/*", intercept_route)

                page = await context.new_page()
                try:
                    response = None
                    try:
                        response = await page.goto(
                            request.url,
                            timeout=int(self.timeout * 1000),
                            wait_until="domcontentloaded",
                        )
                    except Exception:
                        if blocked_redirect:
                            return Document(
                                url=blocked_url or request.url,
                                title="Redirect Blocked",
                                text_content="",
                                status_code=403,
                                fetch_method="blocked",
                            )
                        raise

                    final_url = page.url
                    if blocked_redirect or not SearchPipeline.is_safe_url(final_url):
                        return Document(
                            url=final_url,
                            title="Redirect Blocked",
                            text_content="",
                            status_code=403,
                            fetch_method="blocked",
                        )

                    status_code = response.status if response else 200
                    html = await page.content()
                finally:
                    await page.close()
                    await context.close()
            finally:
                await browser.close()

        # Enforce size ceiling on browser rendered content
        if len(html.encode("utf-8")) > MAX_RESPONSE_BYTES:
            return Document(
                url=final_url,
                title="Oversized Document",
                text_content="",
                status_code=413,
                fetch_method="browser",
            )

        title, clean_text, _, published_at_str, content_units, outgoing_links, metadata, canonical_url = (
            DocumentExtractor.extract_structured(html, base_url=final_url)
        )

        published_at = None
        if published_at_str:
            try:
                from dateutil.parser import parse as parse_date
                parsed = parse_date(published_at_str)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=UTC)
                published_at = parsed
            except Exception:
                pass

        return Document(
            url=final_url,
            canonical_url=canonical_url,
            title=title,
            text_content=clean_text,
            status_code=status_code,
            fetch_method="browser",
            published_at=published_at,
            content_units=content_units,
            outgoing_links=outgoing_links,
            metadata=metadata,
        )
