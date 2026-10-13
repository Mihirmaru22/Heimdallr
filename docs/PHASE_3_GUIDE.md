# Phase 3 Implementation Guide: Web Acquisition & Crawler (Crawlee + Playwright)

Welcome to **Phase 3** of Argus!

In this phase, you are building the **web acquisition engine**. 
By the end of Phase 3, Argus will be able to take candidate URLs, fetch them through an intelligent **two-tier pipeline (fast HTTP first, Playwright browser fallback only when necessary)**, strip boilerplate noise, convert raw HTML into clean text documents, and store them with cryptographic content hashes for research provenance.

---

## 1. Architectural Principles (From the Brief)

1. **Two Separate Queues (Brief Sec 8):**
   * **Research Task Queue:** What information does Argus still need? (e.g., *"Find plant manager of KTP"*).
   * **Crawl Request Queue:** Which URL should be fetched? (e.g., `https://example.com/plant`).
   * *These are strictly separate concepts in the code.*
2. **Two-Tier Fetch Pipeline (Brief Sec 7):**
   ```text
   CrawlRequest (URL)
           │
           ▼
     HTTP Fetch (Fast, ~100ms)
           │
     Is substantive content available?
      ├── YES ──► Extract Clean Text ──► Document (fetch_method="http")
      └── NO  ──► Playwright Browser ──► Document (fetch_method="browser")
   ```
   *Do NOT launch a browser for every URL.* 85%+ of sites return substantive content via lightweight HTTP.
3. **Security & Guardrails (Brief Sec 16):**
   * Enforce response size limits (e.g., max 5 MB to prevent memory exhaustion).
   * Validate destination URLs against the SSRF shield before fetching and after redirects.
   * Graceful failure on timeouts, 404s, or blocking—never crash the orchestrator.
4. **Epistemic Provenance (Brief Sec 10):**
   * Every document computes a SHA-256 `content_hash` to guarantee evidence immutability.

---

## 2. Directory Structure for Phase 3

```text
Argus/
├── docs/
│   ├── PHASE_0_GUIDE.md
│   ├── PHASE_1_GUIDE.md
│   ├── PHASE_2_GUIDE.md
│   └── PHASE_3_GUIDE.md
├── src/
│   └── argus/
│       ├── core/
│       ├── domain/
│       ├── storage/
│       ├── search/
│       └── crawler/                  <-- NEW: Web Acquisition Layer
│           ├── __init__.py
│           ├── models.py             <-- CrawlRequest, Document
│           ├── extractor.py          <-- HTML boilerplate stripper & text cleaner
│           ├── fetcher.py            <-- TwoTierFetcher (HTTP + Playwright fallback)
│           └── mock.py               <-- MockFetcher (for fast offline tests)
└── tests/
    ├── test_objective.py
    ├── test_task.py
    ├── test_state_machine.py
    ├── test_knowledge_models.py
    ├── test_storage.py
    ├── test_search.py
    └── test_crawler.py              <-- NEW: Crawler & Document Tests
```

---

## 3. Step-by-Step Implementation

### Step 3.1: Dependencies (`pyproject.toml`)
We add `beautifulsoup4` (for bulletproof HTML parsing and boilerplate removal) and `playwright`:
```toml
dependencies = [
    "fastapi>=0.141.1",
    "httpx>=0.28.0",
    "pydantic>=2.10.0",
    "beautifulsoup4>=4.12.0",
    "playwright>=1.49.0",
]
```

---

### Step 3.2: `src/argus/crawler/models.py` (Crawl Contracts)

#### **Concept & Purpose**
Strict contracts representing a fetch request and the resulting normalized document.

#### **Code Blueprint**
```python
from datetime import UTC, datetime
import hashlib
import uuid
from pydantic import BaseModel, Field


def generate_document_id() -> str:
    return f"doc_{uuid.uuid4().hex[:8]}"


class CrawlRequest(BaseModel):
    """A single web acquisition request."""

    url: str = Field(..., min_length=1, description="Target URL to fetch")
    task_id: str | None = Field(
        default=None, description="Originating ResearchTask ID if linked"
    )
    priority: int = Field(default=1, ge=1, le=100)
    max_retries: int = Field(default=2, ge=0)
    retry_count: int = Field(default=0, ge=0)
    force_browser: bool = Field(
        default=False, description="Bypass HTTP and force Playwright rendering"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Document(BaseModel):
    """A clean, processed text document ready for information extraction."""

    document_id: str = Field(default_factory=generate_document_id)
    url: str = Field(..., description="Final resolved URL after redirects")
    title: str = Field(default="", description="Extracted page title")
    text_content: str = Field(..., description="Cleaned, substantive text body")
    status_code: int = Field(default=200, description="HTTP response status code")
    content_hash: str = Field(default="", description="SHA-256 hash of cleaned text")
    fetch_method: str = Field(
        default="http", description="Acquisition method: 'http' or 'browser'"
    )
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def model_post_init(self, __context) -> None:
        """Compute content hash automatically if not set."""
        if not self.content_hash and self.text_content:
            self.content_hash = hashlib.sha256(
                self.text_content.encode("utf-8")
            ).hexdigest()
```

---

### Step 3.3: `src/argus/crawler/extractor.py` (Boilerplate Stripper)

#### **Concept & Purpose**
Raw HTML is filled with junk: `<script>`, `<style>`, `<nav>`, `<footer>`, `<header>`, cookie banners, and navigation menus.
The extractor strips this clutter, leaving only the substantive text, and checks whether the page is a blank JavaScript shell (e.g., *"Please enable JavaScript to view this page"*).

#### **Code Blueprint**
```python
import re
from bs4 import BeautifulSoup

STRIP_TAGS = {
    "script",
    "style",
    "nav",
    "footer",
    "header",
    "aside",
    "noscript",
    "iframe",
    "svg",
}
JS_SHELL_PATTERNS = [
    re.compile(r"enable javascript", re.I),
    re.compile(r"javascript is required", re.I),
    re.compile(r"you need to enable javascript to run this app", re.I),
]


class DocumentExtractor:
    """Extracts page title and clean text from raw HTML, stripping boilerplate."""

    @classmethod
    def extract(cls, raw_html: str) -> tuple[str, str, bool]:
        """
        Returns:
            title: str
            clean_text: str
            needs_browser: bool (True if content is an empty SPA shell requiring JS)
        """
        soup = BeautifulSoup(raw_html, "html.parser")

        # Extract title
        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        # Remove clutter tags
        for tag in soup.find_all(list(STRIP_TAGS)):
            tag.decompose()

        # Get body text or entire document text
        body = soup.body or soup
        text = body.get_text(separator="\n", strip=True)

        # Collapse excess whitespace and empty lines
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        clean_text = "\n".join(lines)

        # Check for empty client-rendered SPA shells
        needs_browser = False
        if len(clean_text) < 150:
            for pattern in JS_SHELL_PATTERNS:
                if pattern.search(clean_text) or pattern.search(raw_html):
                    needs_browser = True
                    break

        return title, clean_text, needs_browser
```

---

### Step 3.4: `src/argus/crawler/fetcher.py` (Two-Tier Fetcher)

#### **Concept & Purpose**
1. **Tier 1 (HTTP):** Fetches the page via `httpx` async client. Enforces max response size (5 MB) and verifies redirect safety against SSRF.
2. **Tier 2 (Playwright Browser):** If `force_browser=True` or HTTP content was flagged as an unrendered JS shell, launches headless browser, renders DOM, and extracts content.

#### **Code Blueprint**
```python
from abc import ABC, abstractmethod
import httpx
from argus.crawler.extractor import DocumentExtractor
from argus.crawler.models import CrawlRequest, Document
from argus.search.pipeline import SearchPipeline

MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB


class BaseFetcher(ABC):
    @abstractmethod
    async def fetch(self, request: CrawlRequest) -> Document:
        pass


class TwoTierFetcher(BaseFetcher):
    """Orchestrates fast HTTP fetch with automatic Playwright escalation."""

    def __init__(
        self,
        timeout: float = 12.0,
        user_agent: str = "ArgusResearchEngine/1.0",
    ) -> None:
        self.timeout = timeout
        self.user_agent = user_agent

    async def fetch(self, request: CrawlRequest) -> Document:
        # SSRF Security check before outbound call
        if not SearchPipeline.is_safe_url(request.url):
            return Document(
                url=request.url,
                title="Blocked",
                text_content="",
                status_code=403,
                fetch_method="blocked",
            )

        # Tier 2: Forced browser
        if request.force_browser:
            return await self._fetch_browser(request)

        # Tier 1: Fast HTTP attempt
        try:
            doc, needs_browser = await self._fetch_http(request)
            if not needs_browser and len(doc.text_content) > 100:
                return doc
        except Exception:
            # If HTTP connection fails, escalate to browser
            pass

        # Escalate to browser rendering
        return await self._fetch_browser(request)

    async def _fetch_http(self, request: CrawlRequest) -> tuple[Document, bool]:
        headers = {"User-Agent": self.user_agent}
        async with httpx.AsyncClient(
            timeout=self.timeout, follow_redirects=True, headers=headers
        ) as client:
            response = await client.get(request.url)
            final_url = str(response.url)

            # Security check on final redirected URL
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

            # Enforce size ceiling
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

            title, clean_text, needs_browser = DocumentExtractor.extract(response.text)
            doc = Document(
                url=final_url,
                title=title,
                text_content=clean_text,
                status_code=response.status_code,
                fetch_method="http",
            )
            return doc, needs_browser

    async def _fetch_browser(self, request: CrawlRequest) -> Document:
        """Render using Playwright headless browser."""
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=self.user_agent)
            page = await context.new_page()
            try:
                response = await page.goto(
                    request.url, timeout=int(self.timeout * 1000)
                )
                status_code = response.status if response else 200
                html = await page.content()
                final_url = page.url
            finally:
                await browser.close()

        title, clean_text, _ = DocumentExtractor.extract(html)
        return Document(
            url=final_url,
            title=title,
            text_content=clean_text,
            status_code=status_code,
            fetch_method="browser",
        )
```

---

### Step 3.5: `src/argus/crawler/mock.py` (Testing Mock)

#### **Concept & Purpose**
Allows all unit and integration tests to run offline in milliseconds without launching headless Chromium or making live web calls.

#### **Code Blueprint**
```python
from argus.crawler.fetcher import BaseFetcher
from argus.crawler.models import CrawlRequest, Document


class MockFetcher(BaseFetcher):
    """Deterministic mock crawler for offline testing."""

    def __init__(self, predefined_documents: dict[str, Document] | None = None):
        self.predefined_documents = predefined_documents or {}
        self.recorded_requests: list[CrawlRequest] = []

    async def fetch(self, request: CrawlRequest) -> Document:
        self.recorded_requests.append(request)
        if request.url in self.predefined_documents:
            return self.predefined_documents[request.url]

        return Document(
            url=request.url,
            title="Mock Title",
            text_content=f"Mock content for {request.url}",
            status_code=200,
            fetch_method="mock",
        )
```

---

### Step 3.6: Update SQLite Database (`documents` Table)
In `src/argus/storage/db.py` and `repository.py`, add persistence for `Document`:
```sql
CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    text_content TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    fetch_method TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_documents_url ON documents(url);
CREATE INDEX IF NOT EXISTS idx_documents_hash ON documents(content_hash);
```
Add `save_document(doc)` and `get_document(doc_id)` to `ArgusRepository`.

---

## 4. Writing Unit Tests (`tests/test_crawler.py`)

### Test Scenarios to Cover:
1. **HTML Extraction & Boilerplate Removal:**
   - Strips `<script>`, `<style>`, `<nav>`, `<footer>`.
   - Extracts correct title.
   - Detects JS SPA empty shell (`Please enable JavaScript`).
2. **Document Model:**
   - Computes SHA-256 `content_hash` automatically.
3. **SSRF Pre-Fetch Block:**
   - Passing `http://localhost:8080` or `http://169.254.169.254` returns `status_code=403` with `fetch_method="blocked"`.
4. **Two-Tier Escalation Logic:**
   - Tests HTTP path using mocked `httpx` response.
   - Tests escalation to browser when HTTP returns JS shell.
5. **Mock Fetcher:**
   - Asynchronous fetch execution and request recording.
6. **Storage Integration:**
   - `repo.save_document(doc)` and `repo.get_document(doc_id)`.

---

## 5. Verification Command

Run:
```bash
uv run pytest -v tests/test_crawler.py
```

When all tests pass, **Phase 3 is certified!** Argus has an intelligent, secure crawler and document processor ready to feed the intelligence workers.
