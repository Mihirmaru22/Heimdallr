# Phase 2 Implementation Guide: Search Provider & Normalization (SearXNG)

Welcome to **Phase 2** of Argus!

In this phase, you are building the **search acquisition layer**. 
By the end of Phase 2, Argus will be able to dispatch research queries through an abstract `SearchProvider`, query a SearXNG instance, normalize and deduplicate the results, and block dangerous URLs (SSRF protection).

---

## 1. Architectural Principles (From the Brief)

1. **Decoupled Search Infrastructure:**
   Argus must not hard-code SearXNG throughout the application. We use a `SearchProvider` interface so another engine (e.g., Bing, Brave, Google API) can be swapped in later without touching research logic:
   ```text
   Research Brain / Worker
             ↓
       SearchPipeline
             ↓
       SearchProvider (Interface)
             ↓
      SearXNG / MockProvider
   ```
2. **Argus Owns the Intelligence:**
   * Query normalization
   * Result deduplication
   * Security & SSRF filtering (blocking `localhost`, private IP ranges, cloud metadata)
   * Domain-level filtering
3. **Deterministic Testing:**
   We provide a `MockSearchProvider` so tests run offline in milliseconds without requiring a live SearXNG instance running in Docker.

---

## 2. Directory Structure for Phase 2

```text
Argus/
├── docs/
│   ├── PHASE_0_GUIDE.md
│   ├── PHASE_1_GUIDE.md
│   └── PHASE_2_GUIDE.md
├── src/
│   └── argus/
│       ├── core/
│       ├── domain/
│       ├── storage/
│       └── search/                   <-- NEW: Search Layer
│           ├── __init__.py
│           ├── models.py             <-- SearchResult, SearchQuery, SearchResponse
│           ├── provider.py           <-- SearchProvider (Abstract Base Class)
│           ├── searxng.py            <-- SearXNG HTTP Implementation
│           ├── mock.py               <-- MockSearchProvider (for testing)
│           └── pipeline.py           <-- URL Normalizer, Deduplicator, SSRF Shield
└── tests/
    ├── test_objective.py
    ├── test_task.py
    ├── test_state_machine.py
    ├── test_knowledge_models.py
    ├── test_storage.py
    └── test_search.py               <-- NEW: Search & Normalization Tests
```

---

## 3. Step-by-Step Implementation

### Step 2.1: Dependencies (`pyproject.toml`)
For robust, non-blocking asynchronous HTTP requests to SearXNG, add `httpx`:
```toml
dependencies = [
    "fastapi>=0.141.1",
    "pydantic>=2.10.0",
    "httpx>=0.28.0",
]
```

---

### Step 2.2: `src/argus/search/models.py` (Search Contracts)

#### **Concept & Purpose**
Strict Pydantic models for queries and normalized search engine outputs.

#### **Code Blueprint**
```python
from pydantic import BaseModel, Field, HttpUrl


class SearchQuery(BaseModel):
    """Parameters for executing a research search query."""

    query: str = Field(..., min_length=1, description="Search terms")
    num_results: int = Field(
        default=10, ge=1, le=50, description="Max results requested"
    )
    language: str = Field(default="en", description="Target language code")
    categories: list[str] = Field(
        default_factory=lambda: ["general"], description="SearXNG categories"
    )


class SearchResult(BaseModel):
    """A single normalized search result from an engine."""

    url: str = Field(..., description="Canonical result URL")
    title: str = Field(..., description="Page title")
    snippet: str = Field(default="", description="Search summary/snippet")
    engine: str = Field(
        default="unknown", description="Source search engine (e.g., google, bing)"
    )
    score: float = Field(default=0.0, description="Engine relevance score")


class SearchResponse(BaseModel):
    """Aggregated results from a search query."""

    query: str
    results: list[SearchResult] = Field(default_factory=list)
    total_results: int = 0
    execution_time_ms: float = 0.0
```

---

### Step 2.3: `src/argus/search/provider.py` & `mock.py`

#### **Concept & Purpose**
The `SearchProvider` defines the asynchronous contract that all search engines must fulfill. The `MockSearchProvider` lets tests simulate search responses deterministically.

#### **`src/argus/search/provider.py`**
```python
from abc import ABC, abstractmethod
from argus.search.models import SearchQuery, SearchResponse


class SearchProvider(ABC):
    """Abstract interface for external search providers."""

    @abstractmethod
    async def search(self, query: SearchQuery) -> SearchResponse:
        """Execute a search query asynchronously and return normalized results."""
        pass
```

#### **`src/argus/search/mock.py`**
```python
from argus.search.models import SearchQuery, SearchResponse, SearchResult
from argus.search.provider import SearchProvider


class MockSearchProvider(SearchProvider):
    """A deterministic mock search provider for unit testing."""

    def __init__(self, predefined_results: list[SearchResult] | None = None):
        self.predefined_results = predefined_results or []
        self.recorded_queries: list[SearchQuery] = []

    async def search(self, query: SearchQuery) -> SearchResponse:
        self.recorded_queries.append(query)
        results = self.predefined_results[: query.num_results]
        return SearchResponse(
            query=query.query,
            results=results,
            total_results=len(results),
            execution_time_ms=5.0,
        )
```

---

### Step 2.4: `src/argus/search/pipeline.py` (Normalization, Dedup & Security)

#### **Concept & Purpose**
This is where **Argus research intelligence** lives.
1. **URL Normalization:** Strips query tracking junk (`utm_source`, `utm_medium`, `fbclid`), trailing slashes, fragments (`#section`), and normalizes lowercase domains.
2. **Deduplication:** Different search engines often return the same page with slight URL differences. The pipeline merges duplicate results and preserves the best snippet/score.
3. **SSRF & Security Shield:** Rejects malicious or dangerous URLs before they ever enter Argus:
   * `localhost`, `127.0.0.1`, `::1`
   * Private network IPs (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`)
   * Cloud metadata services (`169.254.169.254`)
   * Non-HTTP(S) schemes (`file://`, `ftp://`)

#### **Code Blueprint**
```python
import ipaddress
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from argus.search.models import SearchResult

DISALLOWED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "::1",
    "169.254.169.254",  # AWS/GCP metadata endpoint
    "metadata.google.internal",
}

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "ref",
}


class SearchPipeline:
    """Cleans, normalizes, deduplicates, and validates search results."""

    @staticmethod
    def normalize_url(raw_url: str) -> str:
        """Strip tracking parameters, fragments, and normalize domain casing."""
        parsed = urlparse(raw_url.strip())
        if not parsed.scheme or not parsed.netloc:
            return raw_url

        # Filter out tracking query params
        query_pairs = [
            (k, v)
            for k, v in parse_qsl(parsed.query)
            if k.lower() not in TRACKING_PARAMS
        ]
        clean_query = urlencode(query_pairs)

        # Normalize path
        clean_path = parsed.path.rstrip("/") if parsed.path != "/" else "/"

        clean_parts = (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            clean_path,
            parsed.params,
            clean_query,
            "",  # Strip fragment (#section)
        )
        return urlunparse(clean_parts)

    @staticmethod
    def is_safe_url(url: str) -> bool:
        """Check against SSRF, internal networks, and forbidden IP addresses."""
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False

        hostname = parsed.hostname
        if not hostname or hostname in DISALLOWED_HOSTS:
            return False

        # Check for private IP address ranges
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return False
        except ValueError:
            pass  # Normal domain name

        return True

    @classmethod
    def process_results(
        cls, results: list[SearchResult], max_results: int = 20
    ) -> list[SearchResult]:
        """Normalize, filter unsafe URLs, and deduplicate results."""
        seen_urls: set[str] = set()
        clean_results: list[SearchResult] = []

        for item in results:
            clean_url = cls.normalize_url(item.url)
            if not cls.is_safe_url(clean_url):
                continue
            if clean_url in seen_urls:
                continue

            seen_urls.add(clean_url)
            clean_results.append(
                SearchResult(
                    url=clean_url,
                    title=item.title.strip(),
                    snippet=item.snippet.strip(),
                    engine=item.engine,
                    score=item.score,
                )
            )
            if len(clean_results) >= max_results:
                break

        return clean_results
```

---

### Step 2.5: `src/argus/search/searxng.py` (SearXNG Client)

#### **Concept & Purpose**
Sends an async HTTP request to a SearXNG instance using JSON output (`/search?q=...&format=json`).

#### **Code Blueprint**
```python
import time
import httpx
from argus.search.models import SearchQuery, SearchResponse, SearchResult
from argus.search.provider import SearchProvider


class SearXNGSearchProvider(SearchProvider):
    """SearXNG meta-search engine provider."""

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def search(self, query: SearchQuery) -> SearchResponse:
        start_time = time.perf_counter()
        params = {
            "q": query.query,
            "format": "json",
            "language": query.language,
            "categories": ",".join(query.categories),
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/search", params=params)
            response.raise_for_status()
            data = response.json()

        raw_results = data.get("results", [])
        parsed_results = [
            SearchResult(
                url=r.get("url", ""),
                title=r.get("title", ""),
                snippet=r.get("content", ""),
                engine=r.get("engine", "searxng"),
                score=float(r.get("score", 0.0) or 0.0),
            )
            for r in raw_results
            if r.get("url")
        ]

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return SearchResponse(
            query=query.query,
            results=parsed_results,
            total_results=len(parsed_results),
            execution_time_ms=elapsed_ms,
        )
```

---

## 4. Writing Unit Tests (`tests/test_search.py`)

### Test Scenarios to Cover:
1. **URL Normalization:**
   - Strips `utm_source=twitter&utm_medium=social`.
   - Strips `#header-link`.
   - Canonicalizes domain to lowercase.
2. **SSRF & Security Shield:**
   - Blocks `http://localhost:8080/admin`.
   - Blocks `http://127.0.0.1/secret`.
   - Blocks AWS metadata `http://169.254.169.254/latest/meta-data`.
   - Blocks private IP ranges like `http://192.168.1.1/router`.
   - Allows public HTTPS URLs like `https://media.ford.com/plants`.
3. **Deduplication:**
   - Passing `https://example.com/page?utm_source=a` and `https://example.com/page/` results in a single deduplicated result.
4. **Mock Provider Execution:**
   - Search execution returns expected `SearchResponse` asynchronously.
5. **SearXNG Provider Unit Test:**
   - Mocking HTTP responses to verify JSON parsing into `SearchResult` models.

---

## 5. Verification Command

Run:
```bash
uv run pytest -v tests/test_search.py
```

When all tests pass, **Phase 2 is certified!** Argus has a decoupled, secure search engine ready for web investigations.
