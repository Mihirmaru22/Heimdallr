from unittest.mock import AsyncMock, patch

import pytest

from argus.crawler.extractor import DocumentExtractor
from argus.crawler.fetcher import TwoTierFetcher
from argus.crawler.mock import MockFetcher
from argus.crawler.models import CrawlRequest, Document
from argus.storage.db import DatabaseManager
from argus.storage.repository import ArgusRepository


def test_document_model_hash_computation():
    doc = Document(
        url="https://media.ford.com/plants/ktp",
        title="Kentucky Truck Plant",
        text_content="Kentucky Truck Plant builds F-Series Super Duty trucks in Louisville.",
    )
    assert doc.document_id.startswith("doc_")
    assert len(doc.content_hash) == 64  # SHA-256 hex string length
    assert doc.fetch_method == "http"


def test_document_extractor_strips_boilerplate():
    raw_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Ford Manufacturing Facilities | Official News</title>
        <script>var tracker = 'analytics';</script>
        <style>body { background: #000; }</style>
    </head>
    <body>
        <header>
            <nav><a href="/home">Home</a><a href="/about">About</a></nav>
        </header>
        <main>
            <h1>Kentucky Truck Plant</h1>
            <p>The facility covers 6 million square feet and employs 9,000 workers.</p>
            <p>Plant Manager: Jane Smith.</p>
        </main>
        <footer>
            <p>Copyright 2026 Ford Motor Company. All rights reserved.</p>
        </footer>
    </body>
    </html>
    """

    title, clean_text, needs_browser, published_at = DocumentExtractor.extract(raw_html)
    assert title == "Ford Manufacturing Facilities | Official News"
    assert "The facility covers 6 million square feet" in clean_text
    assert "Plant Manager: Jane Smith." in clean_text
    assert "var tracker" not in clean_text
    assert "Copyright 2026" not in clean_text
def test_document_extractor_strips_cookie_banners_and_forms():
    raw_html = """
    <html>
    <head><title>Plant News</title></head>
    <body>
        <div class="cookie-consent-banner">
            <p>We value your privacy. Accept all cookies.</p>
            <button>Accept</button>
        </div>
        <form action="/search">
            <input type="text" name="q" placeholder="Search site" />
            <button type="submit">Search</button>
        </form>
        <article>
            <h1>Flint Assembly Plant</h1>
            <p>Flint Assembly builds heavy-duty Chevrolet Silverado trucks.</p>
        </article>
        <div class="social-share-buttons">
            <button>Share on X</button>
        </div>
    </body>
    </html>
    """
    title, clean_text, _, _ = DocumentExtractor.extract(raw_html)
    assert title == "Plant News"
    assert "Flint Assembly builds heavy-duty Chevrolet Silverado trucks." in clean_text
    assert "Accept all cookies" not in clean_text
    assert "Search site" not in clean_text
    assert "Share on X" not in clean_text


def test_document_extractor_detects_js_shell():
    spa_html = """
    <html>
    <head><title>Loading React App</title></head>
    <body>
        <noscript>You need to enable JavaScript to run this app.</noscript>
        <div id="root"></div>
    </body>
    </html>
    """
    _, _, needs_browser, _ = DocumentExtractor.extract(spa_html)
    assert needs_browser is True


@pytest.mark.asyncio
async def test_two_tier_fetcher_ssrf_blocking():
    fetcher = TwoTierFetcher()

    # Test SSRF target
    req = CrawlRequest(url="http://127.0.0.1:8000/internal")
    doc = await fetcher.fetch(req)

    assert doc.status_code == 403
    assert doc.fetch_method == "blocked"
    assert doc.text_content == ""


@pytest.mark.asyncio
async def test_two_tier_fetcher_browser_post_redirect_ssrf_blocking():
    """Bug 2.1 Regression Test:

    Verify that when Playwright browser encounters a post-redirect to internal metadata
    or loopback endpoints (e.g. 169.254.169.254), route interception aborts the request
    and returns a blocked document with status 403.
    """
    fetcher = TwoTierFetcher()
    req = CrawlRequest(
        url="https://external-redirector.com/forward", force_browser=True
    )

    mock_route = AsyncMock()
    mock_route.request.url = "http://169.254.169.254/latest/meta-data/"

    mock_page = AsyncMock()
    mock_page.url = "http://169.254.169.254/latest/meta-data/"
    mock_page.goto.side_effect = Exception("net::ERR_BLOCKED_BY_CLIENT")

    mock_context = AsyncMock()
    mock_context.new_page.return_value = mock_page

    async def fake_route(pattern, handler):
        await handler(mock_route)

    mock_context.route = fake_route

    mock_browser = AsyncMock()
    mock_browser.new_context.return_value = mock_context

    mock_playwright = AsyncMock()
    mock_playwright.chromium.launch.return_value = mock_browser

    mock_p_ctx = AsyncMock()
    mock_p_ctx.__aenter__.return_value = mock_playwright
    mock_p_ctx.__aexit__.return_value = None

    with patch("playwright.async_api.async_playwright", return_value=mock_p_ctx):
        doc = await fetcher.fetch(req)

        assert doc.status_code == 403
        assert doc.fetch_method == "blocked"
        assert "Redirect Blocked" in doc.title
        mock_route.abort.assert_awaited_once_with("blockedbyclient")


@pytest.mark.asyncio
async def test_two_tier_fetcher_browser_unsafe_final_url_blocked():
    """Bug 2.1 Regression Test:

    Verify that if the browser lands on an unsafe final URL, it is blocked with status 403.
    """
    fetcher = TwoTierFetcher()
    req = CrawlRequest(url="https://safe-url.com", force_browser=True)

    mock_page = AsyncMock()
    mock_page.url = "http://127.0.0.1:8000/internal"
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_page.goto.return_value = mock_response

    mock_context = AsyncMock()
    mock_context.new_page.return_value = mock_page

    mock_browser = AsyncMock()
    mock_browser.new_context.return_value = mock_context

    mock_playwright = AsyncMock()
    mock_playwright.chromium.launch.return_value = mock_browser

    mock_p_ctx = AsyncMock()
    mock_p_ctx.__aenter__.return_value = mock_playwright
    mock_p_ctx.__aexit__.return_value = None

    with patch("playwright.async_api.async_playwright", return_value=mock_p_ctx):
        doc = await fetcher.fetch(req)
        assert doc.status_code == 403
        assert doc.fetch_method == "blocked"


@pytest.mark.asyncio
async def test_two_tier_fetcher_http_happy_path():
    fetcher = TwoTierFetcher()
    req = CrawlRequest(url="https://media.ford.com/plants/ktp")

    fake_html = """
    <html>
    <head><title>KTP News</title></head>
    <body>
        <p>This is a long substantive article about Kentucky Truck Plant manufacturing operations in Louisville, Kentucky.</p>
        <p>It contains multiple paragraphs of useful research text detailing production numbers and leadership.</p>
    </body>
    </html>
    """

    from unittest.mock import MagicMock

    mock_response = MagicMock()
    mock_response.url = "https://media.ford.com/plants/ktp"
    mock_response.status_code = 200
    mock_response.text = fake_html
    mock_response.content = fake_html.encode("utf-8")

    with patch(
        "httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response
    ):
        doc = await fetcher.fetch(req)
        assert doc.status_code == 200
        assert doc.fetch_method == "http"
        assert doc.title == "KTP News"
        assert "Kentucky Truck Plant manufacturing operations" in doc.text_content


@pytest.mark.asyncio
async def test_two_tier_fetcher_escalates_to_browser():
    fetcher = TwoTierFetcher()
    req = CrawlRequest(url="https://spa-example.com/plant")

    # Mock HTTP returning a JavaScript shell that needs browser
    spa_doc = Document(
        url="https://spa-example.com/plant",
        title="Loading",
        text_content="Please enable JavaScript",
        status_code=200,
        fetch_method="http",
    )

    rendered_browser_doc = Document(
        url="https://spa-example.com/plant",
        title="Rendered Plant Page",
        text_content="Full client-rendered content with leadership and plant data.",
        status_code=200,
        fetch_method="browser",
    )

    with (
        patch.object(
            fetcher, "_fetch_http", new_callable=AsyncMock, return_value=(spa_doc, True)
        ),
        patch.object(
            fetcher,
            "_fetch_browser",
            new_callable=AsyncMock,
            return_value=rendered_browser_doc,
        ),
    ):
        doc = await fetcher.fetch(req)
        assert doc.fetch_method == "browser"
        assert doc.title == "Rendered Plant Page"
        assert "Full client-rendered content" in doc.text_content


@pytest.mark.asyncio
async def test_mock_fetcher():
    predefined = {
        "https://example.com/doc1": Document(
            url="https://example.com/doc1",
            title="Doc 1",
            text_content="Content 1",
        )
    }
    fetcher = MockFetcher(predefined_documents=predefined)

    req = CrawlRequest(url="https://example.com/doc1")
    doc = await fetcher.fetch(req)

    assert doc.title == "Doc 1"
    assert len(fetcher.recorded_requests) == 1
    assert fetcher.recorded_requests[0].url == "https://example.com/doc1"


def test_document_storage_in_repo():
    db = DatabaseManager(":memory:")
    repo = ArgusRepository(db)

    doc = Document(
        url="https://media.ford.com/plants/ktp",
        title="Ford KTP",
        text_content="Kentucky Truck Plant builds Super Duty trucks.",
        status_code=200,
        fetch_method="http",
    )
    repo.save_document(doc)

    retrieved = repo.get_document(doc.document_id)
    assert retrieved is not None
    assert retrieved.document_id == doc.document_id
    assert retrieved.url == doc.url
    assert retrieved.content_hash == doc.content_hash

    # Test retrieval by content hash (dedup verification)
    by_hash = repo.get_document_by_hash(doc.content_hash)
    assert by_hash is not None
    assert by_hash.document_id == doc.document_id


@pytest.mark.asyncio
async def test_two_tier_fetcher_http_oversized_content_length_rejected():
    fetcher = TwoTierFetcher()
    req = CrawlRequest(url="https://media.ford.com/oversized-pdf")

    class MockStreamResponse:
        def __init__(self):
            self.url = "https://media.ford.com/oversized-pdf"
            self.headers = {"Content-Length": "10000000"}  # 10 MB > 5 MB
            self.status_code = 200
            self.encoding = "utf-8"
            self.stream_called = False

        async def aiter_bytes(self, chunk_size=65536):
            self.stream_called = True
            yield b"x" * 65536

    class MockStreamContext:
        def __init__(self, resp):
            self.resp = resp

        async def __aenter__(self):
            return self.resp

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_resp = MockStreamResponse()
    with patch("httpx.AsyncClient.stream", return_value=MockStreamContext(mock_resp)):
        doc = await fetcher.fetch(req)
        assert doc.status_code == 413
        assert doc.title == "Oversized Document"
        assert doc.text_content == ""
        assert not mock_resp.stream_called


@pytest.mark.asyncio
async def test_two_tier_fetcher_http_streaming_oversized_abort():
    fetcher = TwoTierFetcher()
    req = CrawlRequest(url="https://media.ford.com/large-stream")

    chunks_yielded = 0

    class MockStreamResponse:
        def __init__(self):
            self.url = "https://media.ford.com/large-stream"
            self.headers = {}  # No Content-Length provided
            self.status_code = 200
            self.encoding = "utf-8"

        async def aiter_bytes(self, chunk_size=65536):
            nonlocal chunks_yielded
            for _ in range(5):
                chunks_yielded += 1
                yield b"A" * (3 * 1024 * 1024)

    class MockStreamContext:
        def __init__(self, resp):
            self.resp = resp

        async def __aenter__(self):
            return self.resp

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_resp = MockStreamResponse()
    with patch("httpx.AsyncClient.stream", return_value=MockStreamContext(mock_resp)):
        doc = await fetcher.fetch(req)
        assert doc.status_code == 413
        assert doc.title == "Oversized Document"
        assert doc.text_content == ""
        assert chunks_yielded == 2


@pytest.mark.asyncio
async def test_two_tier_fetcher_browser_oversized_content_rejected():
    fetcher = TwoTierFetcher()
    req = CrawlRequest(url="https://media.ford.com/huge-page", force_browser=True)

    mock_page = AsyncMock()
    mock_page.url = "https://media.ford.com/huge-page"
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_page.goto.return_value = mock_response
    mock_page.content.return_value = (
        "<html><body>" + ("x" * 6_000_000) + "</body></html>"
    )

    mock_context = AsyncMock()
    mock_context.new_page.return_value = mock_page

    mock_browser = AsyncMock()
    mock_browser.new_context.return_value = mock_context

    mock_playwright = AsyncMock()
    mock_playwright.chromium.launch.return_value = mock_browser

    mock_p_ctx = AsyncMock()
    mock_p_ctx.__aenter__.return_value = mock_playwright
    mock_p_ctx.__aexit__.return_value = None

    with patch("playwright.async_api.async_playwright", return_value=mock_p_ctx):
        doc = await fetcher.fetch(req)
        assert doc.status_code == 413
        assert doc.title == "Oversized Document"
        assert doc.fetch_method == "browser"
        assert doc.text_content == ""


@pytest.mark.asyncio
async def test_two_tier_fetcher_browser_aborts_heavy_media():
    fetcher = TwoTierFetcher()
    req = CrawlRequest(url="https://media.ford.com/article", force_browser=True)

    mock_media_route = AsyncMock()
    mock_media_route.request.url = "https://media.ford.com/video.mp4"
    mock_media_route.request.resource_type = "media"

    mock_page = AsyncMock()
    mock_page.url = "https://media.ford.com/article"
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_page.goto.return_value = mock_response
    mock_page.content.return_value = "<html><body>Article content</body></html>"

    mock_context = AsyncMock()
    mock_context.new_page.return_value = mock_page

    async def fake_route(pattern, handler):
        await handler(mock_media_route)

    mock_context.route = fake_route

    mock_browser = AsyncMock()
    mock_browser.new_context.return_value = mock_context

    mock_playwright = AsyncMock()
    mock_playwright.chromium.launch.return_value = mock_browser

    mock_p_ctx = AsyncMock()
    mock_p_ctx.__aenter__.return_value = mock_playwright
    mock_p_ctx.__aexit__.return_value = None

    with patch("playwright.async_api.async_playwright", return_value=mock_p_ctx):
        doc = await fetcher.fetch(req)
        assert doc.status_code == 200
        mock_media_route.abort.assert_awaited_once_with("blockedbyclient")
