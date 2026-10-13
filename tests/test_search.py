from unittest.mock import AsyncMock, patch

import pytest

from argus.brain.planner import ResearchBrain
from argus.brain.system1 import System1DecisionEngine
from argus.domain.task import ResearchTask, TaskStatus
from argus.llm.mock import MockLLMProvider
from argus.search.mock import MockSearchProvider
from argus.search.models import SearchQuery, SearchResponse, SearchResult
from argus.search.pipeline import SearchPipeline
from argus.search.searxng import SearXNGSearchProvider
from argus.storage.db import DatabaseManager
from argus.storage.repository import ArgusRepository


def test_search_models():
    query = SearchQuery(query="US automotive manufacturing plants", num_results=15)
    assert query.query == "US automotive manufacturing plants"
    assert query.num_results == 15
    assert query.categories == ["general"]

    result = SearchResult(
        url="https://media.ford.com/plants/ktp",
        title="Kentucky Truck Plant",
        snippet="Official plant details",
        engine="google",
        score=0.95,
    )
    assert result.engine == "google"
    assert result.score == 0.95


def test_url_normalization():
    # Test tracking params and fragment removal
    dirty_url = "HTTPS://MEDIA.FORD.COM/plants/ktp/?utm_source=twitter&utm_medium=social#overview"
    clean_url = SearchPipeline.normalize_url(dirty_url)
    assert clean_url == "https://media.ford.com/plants/ktp"

    # Test root path preservation
    root_url = "https://www.ford.com/"
    assert SearchPipeline.normalize_url(root_url) == "https://www.ford.com/"

    # Test fbclid and gclid removal
    ad_url = "https://example.com/article?fbclid=12345&gclid=67890&keep_param=true"
    assert (
        SearchPipeline.normalize_url(ad_url)
        == "https://example.com/article?keep_param=true"
    )

    # Test DuckDuckGo redirect unwrapping
    ddg_redirect = "https://duckduckgo.com/l/?uddg=https%3A%2F%2Fmedia.gm.com%2Fnews.html%3Futm_source%3Dddg&rut=123"
    assert SearchPipeline.normalize_url(ddg_redirect) == "https://media.gm.com/news.html"

    # Test Google redirect unwrapping
    google_redirect = "https://www.google.com/url?q=https%3A%2F%2Fwww.stellantis.com%2Fpress&sa=U&ved=0ahU"
    assert SearchPipeline.normalize_url(google_redirect) == "https://www.stellantis.com/press"


def test_ssrf_safety_checks():
    # Disallowed hosts
    assert not SearchPipeline.is_safe_url("http://localhost:8080/admin")
    assert not SearchPipeline.is_safe_url("http://127.0.0.1/test")
    assert not SearchPipeline.is_safe_url("http://[::1]/test")
    assert not SearchPipeline.is_safe_url("http://169.254.169.254/latest/meta-data")
    assert not SearchPipeline.is_safe_url(
        "http://metadata.google.internal/computeMetadata"
    )

    # Private IP ranges
    assert not SearchPipeline.is_safe_url("http://192.168.1.1/status")
    assert not SearchPipeline.is_safe_url("http://10.0.0.15/intranet")
    assert not SearchPipeline.is_safe_url("http://172.16.5.1/db")

    # Invalid schemes
    assert not SearchPipeline.is_safe_url("file:///etc/passwd")
    assert not SearchPipeline.is_safe_url("ftp://files.example.com")

    # Valid public URLs
    assert SearchPipeline.is_safe_url("https://media.ford.com/plants")
    assert SearchPipeline.is_safe_url("http://automotive-news.com/article")

    # DNS rebinding domains resolving to loopback or link-local
    assert not SearchPipeline.is_safe_url("http://localtest.me/admin")
    assert not SearchPipeline.is_safe_url("http://127.0.0.1.nip.io/shell")
    assert not SearchPipeline.is_safe_url("http://169.254.169.254.nip.io/meta")
    assert not SearchPipeline.is_safe_url("http://router.local/settings")
    assert not SearchPipeline.is_safe_url("http://internal-host.lan/secret")


def test_dns_rebinding_mocked_resolution():
    """Bug 2.2 Regression Test:

    Verify that when a seemingly benign hostname resolves to a private, loopback,
    or cloud metadata IP address, is_safe_url catches and rejects it.
    """
    # Simulate an external domain resolving to an internal 10.0.0.1 IP
    fake_addrinfo_private = [
        (2, 1, 6, "", ("10.0.0.1", 80)),
    ]
    with patch("socket.getaddrinfo", return_value=fake_addrinfo_private):
        assert not SearchPipeline.is_safe_url("https://attacker-rebinding.com/steal")

    # Simulate an external domain resolving to AWS metadata endpoint
    fake_addrinfo_metadata = [
        (2, 1, 6, "", ("169.254.169.254", 80)),
    ]
    with patch("socket.getaddrinfo", return_value=fake_addrinfo_metadata):
        assert not SearchPipeline.is_safe_url("https://metadata-proxy.com/latest")

    # Simulate an external domain resolving to a valid public IP
    fake_addrinfo_public = [
        (2, 1, 6, "", ("93.184.216.34", 80)),
    ]
    with patch("socket.getaddrinfo", return_value=fake_addrinfo_public):
        assert SearchPipeline.is_safe_url("https://legit-domain.com/index")


def test_pipeline_deduplication_and_filtering():
    raw_results = [
        SearchResult(
            url="https://media.ford.com/plants/?utm_source=google",
            title="Ford Plants",
            snippet="List of plants",
        ),
        SearchResult(
            url="https://media.ford.com/plants#leadership",
            title="Ford Plants Duplicate",
            snippet="Same page with fragment",
        ),
        SearchResult(
            url="http://127.0.0.1/malicious",
            title="Localhost Attack",
            snippet="Should be blocked",
        ),
        SearchResult(
            url="https://gm.com/facilities",
            title="GM Facilities",
            snippet="General Motors manufacturing sites",
        ),
    ]

    processed = SearchPipeline.process_results(raw_results, max_results=10)
    assert len(processed) == 2
    assert processed[0].url == "https://media.ford.com/plants"
    assert processed[1].url == "https://gm.com/facilities"


@pytest.mark.asyncio
async def test_mock_search_provider():
    predefined = [
        SearchResult(url="https://ford.com", title="Ford Home"),
        SearchResult(url="https://gm.com", title="GM Home"),
        SearchResult(url="https://tesla.com", title="Tesla Home"),
    ]
    provider = MockSearchProvider(predefined_results=predefined)

    query = SearchQuery(query="auto manufacturers", num_results=2)
    response = await provider.search(query)

    assert isinstance(response, SearchResponse)
    assert len(response.results) == 2
    assert response.results[0].title == "Ford Home"
    assert response.results[1].title == "GM Home"
    assert len(provider.recorded_queries) == 1
    assert provider.recorded_queries[0].query == "auto manufacturers"


@pytest.mark.asyncio
async def test_searxng_provider_mocked_http():
    fake_searxng_json = {
        "results": [
            {
                "url": "https://media.ford.com/ktp",
                "title": "Ford Kentucky Truck Plant",
                "content": "Produces F-Series trucks in Louisville.",
                "engine": "google",
                "score": 0.98,
            }
        ]
    }

    from unittest.mock import MagicMock

    mock_response = MagicMock()
    mock_response.json.return_value = fake_searxng_json
    mock_response.raise_for_status.return_value = None

    with patch(
        "httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response
    ):
        provider = SearXNGSearchProvider(base_url="http://test-searxng:8080")
        query = SearchQuery(query="Ford KTP")
        response = await provider.search(query)

        assert response.total_results == 1
        assert response.results[0].url == "https://media.ford.com/ktp"
        assert response.results[0].title == "Ford Kentucky Truck Plant"
        assert response.results[0].snippet == "Produces F-Series trucks in Louisville."


def test_archetype_dorking_manufacturing(tmp_path):
    """Exit Criterion 1: Leadership/personnel queries generate LinkedIn and appointment dorks."""
    repo = ArgusRepository(DatabaseManager(":memory:"))
    brain = ResearchBrain(repo=repo, llm=MockLLMProvider())

    task = ResearchTask(
        objective_id="obj_mfg",
        title="Investigate plant manager and technical leads for Louisville Assembly Plant",
        description="Find verified leadership.\n\nSearch Queries:\n- Louisville Assembly Plant plant manager official",
        status=TaskStatus.READY,
    )

    queries = brain.extract_search_queries(
        task, objective_target="Ford Motor Company", dork=True
    )

    # Must preserve base query
    assert "Louisville Assembly Plant plant manager official" in queries
    # Must generate LinkedIn professional profile dork
    assert any("site:linkedin.com/in" in q for q in queries)
    # Must generate executive announcement/press release dork
    assert any("appointed" in q or "named" in q or "executive appointment" in q for q in queries)


def test_archetype_dorking_pharma_clinical_trials(tmp_path):
    """Exit Criteria 1 & 2: Pharma personnel generates professional dorks, regulatory generates gov compliance."""
    repo = ArgusRepository(DatabaseManager(":memory:"))
    brain = ResearchBrain(repo=repo, llm=MockLLMProvider())

    # Case A: Personnel / Principal Investigator
    task_lead = ResearchTask(
        objective_id="obj_pharma",
        title="Identify principal investigator and study directors for Oncology Trial NCT098234",
        description="Find clinical trial leadership.\n\nSearch Queries:\n- NCT098234 clinical trial principal investigator",
        status=TaskStatus.READY,
    )
    queries_lead = brain.extract_search_queries(
        task_lead, objective_target="Pfizer", dork=True
    )
    assert any("site:linkedin.com/in" in q for q in queries_lead)
    assert any("appointed" in q or "named" in q or "executive appointment" in q for q in queries_lead)

    # Case B: Regulatory Compliance & FDA Audit
    task_reg = ResearchTask(
        objective_id="obj_pharma",
        title="Inspect FDA compliance records and cGMP audit findings for Kalamazoo Sterile Injectables",
        description="Extract regulatory inspection history.\n\nSearch Queries:\n- Pfizer Kalamazoo sterile facility FDA inspection",
        status=TaskStatus.READY,
    )
    queries_reg = brain.extract_search_queries(
        task_reg, objective_target="Pfizer", dork=True
    )
    assert any("site:gov" in q for q in queries_reg)
    assert any("regulatory filing" in q or "inspection" in q for q in queries_reg)


def test_archetype_dorking_mining_extraction(tmp_path):
    """Exit Criterion 3: Facility/directory queries generate directory and supplier registry dorks."""
    repo = ArgusRepository(DatabaseManager(":memory:"))
    brain = ResearchBrain(repo=repo, llm=MockLLMProvider())

    task_dir = ResearchTask(
        objective_id="obj_mining",
        title="Locate active copper extraction sites and smelter facilities directory in Atacama",
        description="Map mining operational footprint.\n\nSearch Queries:\n- Atacama copper mining smelter operations",
        status=TaskStatus.READY,
    )
    queries_dir = brain.extract_search_queries(
        task_dir, objective_target="BHP Group", dork=True
    )
    assert "Atacama copper mining smelter operations" in queries_dir
    assert any("facility directory" in q or "locations" in q for q in queries_dir)
    assert any("supplier registry" in q or "operations directory" in q for q in queries_dir)


def test_archetype_dorking_with_system1_engine(tmp_path):
    """Exit Criterion 4: System1DecisionEngine seamlessly integrates with ResearchBrain for dorking."""
    from unittest.mock import MagicMock

    repo = ArgusRepository(DatabaseManager(":memory:"))
    system1 = System1DecisionEngine(preload=False)
    mock_router = MagicMock()
    mock_router.predict.return_value = {
        "model": "laya-rl-agent",
        "answers": {"archetype": {"type": "choice", "choice": "newsroom"}},
    }
    system1._router = mock_router
    system1._is_available = True

    brain = ResearchBrain(repo=repo, llm=MockLLMProvider(), system1=system1)

    task = ResearchTask(
        objective_id="obj_test",
        title="Who is the plant manager at Louisville Assembly",
        description="Search Queries:\n- Louisville Assembly plant manager",
        status=TaskStatus.READY,
    )

    queries = brain.extract_search_queries(task, objective_target="Ford")
    assert len(queries) > 1
    assert any("site:linkedin.com/in" in q for q in queries)
    assert any("appointed" in q or "named" in q or "executive appointment" in q for q in queries)


MOCK_GOOGLE_NEWS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Google News - Search</title>
    <item>
      <title>GM Names New Plant Director for Arlington Assembly - Dallas Business News</title>
      <link>https://news.google.com/articles/test-arlington-director</link>
      <pubDate>Mon, 15 Jun 2026 10:00:00 GMT</pubDate>
      <description>&lt;a href="..."&gt;General Motors announced a leadership change at Arlington Assembly.&lt;/a&gt;</description>
      <source url="https://bizjournals.com">Dallas Business News</source>
    </item>
    <item>
      <title>Arlington Assembly Reaches Production Milestone - Fort Worth Report</title>
      <link>https://news.google.com/articles/test-arlington-milestone</link>
      <pubDate>Tue, 16 Jun 2026 12:00:00 GMT</pubDate>
      <description>Milestone reached at GM plant.</description>
      <source url="https://fortworthreport.org">Fort Worth Report</source>
    </item>
  </channel>
</rss>
"""


@pytest.mark.asyncio
async def test_google_news_rss_provider_parsing():
    from argus.search.google_news import GoogleNewsRSSSearchProvider

    provider = GoogleNewsRSSSearchProvider(timeout=5.0)

    # Test XML parser directly
    results = provider._parse_rss(MOCK_GOOGLE_NEWS_XML, max_results=5)
    assert len(results) == 2

    first = results[0]
    assert "GM Names New Plant Director" in first.title
    assert first.url == "https://news.google.com/articles/test-arlington-director"
    assert "Dallas Business News" in first.snippet
    assert "2026" in first.snippet
    assert first.engine == "google_news"
    assert first.score > 0.8

    # Test max_results capping
    capped = provider._parse_rss(MOCK_GOOGLE_NEWS_XML, max_results=1)
    assert len(capped) == 1


@pytest.mark.asyncio
async def test_google_news_rss_search_network_mock():
    from argus.search.google_news import GoogleNewsRSSSearchProvider
    import httpx

    provider = GoogleNewsRSSSearchProvider()

    mock_resp = httpx.Response(
        status_code=200,
        text=MOCK_GOOGLE_NEWS_XML,
        request=httpx.Request("GET", "https://news.google.com/rss"),
    )

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        resp = await provider.search(
            SearchQuery(query="General Motors Arlington Assembly plant director", num_results=5)
        )
        assert resp.total_results == 2
        assert len(resp.results) == 2
        assert resp.results[0].engine == "google_news"


@pytest.mark.asyncio
async def test_duckduckgo_provider_concurrency_guard():
    from argus.search.duckduckgo import DuckDuckGoSearchProvider

    provider = DuckDuckGoSearchProvider(max_concurrent=2, min_interval_seconds=0.01)

    mock_raw = [
        {"href": "https://en.wikipedia.org/wiki/Arlington_Assembly", "title": "Arlington Assembly", "body": "Plant specs"}
    ]

    with patch.object(provider, "_sync_search", return_value=mock_raw):
        resp = await provider.search(SearchQuery(query="Arlington Assembly", num_results=2))
        assert resp.total_results == 1
        assert resp.results[0].url == "https://en.wikipedia.org/wiki/Arlington_Assembly"
        assert resp.results[0].engine == "duckduckgo"


@pytest.mark.asyncio
async def test_hybrid_search_provider_parallel_interleaving():
    from argus.search.hybrid import HybridSearchProvider

    mock_ddg = AsyncMock()
    mock_ddg.search.return_value = SearchResponse(
        query="Arlington Assembly director",
        results=[
            SearchResult(
                url="https://en.wikipedia.org/wiki/Arlington_Assembly",
                title="Arlington Assembly - Wikipedia",
                snippet="General Motors assembly plant",
                engine="duckduckgo",
            ),
            SearchResult(
                url="https://linkedin.com/in/plant-director",
                title="John Urbanic - Plant Executive Director",
                snippet="Plant Director at Arlington",
                engine="duckduckgo",
            ),
        ],
        total_results=2,
        execution_time_ms=50.0,
    )

    mock_news = AsyncMock()
    mock_news.search.return_value = SearchResponse(
        query="Arlington Assembly director",
        results=[
            SearchResult(
                url="https://news.google.com/articles/news-1",
                title="GM Names New Director for Arlington",
                snippet="Source: Dallas Business | Date: 2026",
                engine="google_news",
            ),
            SearchResult(
                url="https://news.google.com/articles/news-2",
                title="Arlington Plant Production Update",
                snippet="Source: Fort Worth Star | Date: 2026",
                engine="google_news",
            ),
        ],
        total_results=2,
        execution_time_ms=40.0,
    )

    hybrid = HybridSearchProvider(ddg_provider=mock_ddg, google_news_provider=mock_news)
    resp = await hybrid.search(SearchQuery(query="Arlington Assembly director", num_results=4))

    assert resp.total_results == 4
    engines = [r.engine for r in resp.results]
    assert "google_news" in engines
    assert "duckduckgo" in engines


@pytest.mark.asyncio
async def test_hybrid_search_provider_deduplication():
    from argus.search.hybrid import HybridSearchProvider

    mock_ddg = AsyncMock()
    mock_ddg.search.return_value = SearchResponse(
        query="test",
        results=[
            SearchResult(
                url="https://example.com/same-article/",
                title="Identical Article Headline",
                snippet="snippet 1",
                engine="duckduckgo",
            )
        ],
        total_results=1,
        execution_time_ms=10.0,
    )

    mock_news = AsyncMock()
    mock_news.search.return_value = SearchResponse(
        query="test",
        results=[
            SearchResult(
                url="https://example.com/same-article",
                title="Identical Article Headline",
                snippet="snippet 2",
                engine="google_news",
            )
        ],
        total_results=1,
        execution_time_ms=10.0,
    )

    hybrid = HybridSearchProvider(ddg_provider=mock_ddg, google_news_provider=mock_news)
    resp = await hybrid.search(SearchQuery(query="test manager", num_results=5))

    # Should deduplicate into a single result
    assert resp.total_results == 1


@pytest.mark.asyncio
async def test_hybrid_search_provider_fallback_on_failure():
    from argus.search.hybrid import HybridSearchProvider

    mock_ddg = AsyncMock()
    mock_ddg.search.side_effect = Exception("DDG 429 Too Many Requests")

    mock_news = AsyncMock()
    mock_news.search.return_value = SearchResponse(
        query="test",
        results=[
            SearchResult(
                url="https://news.google.com/article",
                title="News Backup Article",
                snippet="Valid result",
                engine="google_news",
            )
        ],
        total_results=1,
        execution_time_ms=10.0,
    )

    hybrid = HybridSearchProvider(ddg_provider=mock_ddg, google_news_provider=mock_news)
    # Even if DDG explodes, hybrid must gracefully return news results
    resp = await hybrid.search(SearchQuery(query="GM plant director", num_results=3))

    assert resp.total_results == 1
    assert resp.results[0].engine == "google_news"


@pytest.mark.asyncio
async def test_fourchan_search_provider_catalog_filtering():
    """Test 4chan real-time catalog fetching, token matching, and HTML cleaning."""
    from unittest.mock import MagicMock
    from argus.search.fourchan import FourChanSearchProvider

    mock_catalog = [
        {
            "page": 1,
            "threads": [
                {
                    "no": 12345,
                    "sub": "Tonawanda Engine plant leak",
                    "com": "Heard from a line worker at &gt;&gt;12344 that the new V8 line is launching next quarter.<br>Thoughts?",
                },
                {
                    "no": 67890,
                    "sub": "Which miata is best?",
                    "com": "NA vs NB debate for the hundredth time.",
                },
            ],
        }
    ]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_catalog

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        fc = FourChanSearchProvider(boards=["o"])
        resp = await fc.search(SearchQuery(query="Tonawanda engine", num_results=5))

        assert resp.total_results == 1
        r0 = resp.results[0]
        assert r0.engine == "4chan"
        assert "12345" in r0.url
        assert "Tonawanda Engine plant leak" in r0.title
        assert "new V8 line is launching" in r0.snippet
        assert "<br>" not in r0.snippet
        assert "&gt;" not in r0.snippet
        await fc.close()


@pytest.mark.asyncio
async def test_linkedin_search_provider_dorking_and_parsing():
    """Test LinkedIn real-time search dorking, URL cleaning, and title parsing."""
    from argus.search.linkedin import LinkedInSearchProvider

    mock_backend = AsyncMock()
    mock_backend.search.return_value = SearchResponse(
        query="test",
        results=[
            SearchResult(
                url="https://www.linkedin.com/in/amy-carrier-ba171b22?trk=public_profile_browsemap",
                title="Amy Carrier - Plant Director at General Motors | LinkedIn",
                snippet="Experienced Plant Director at General Motors Tonawanda Engine Plant.",
                engine="duckduckgo",
            ),
            SearchResult(
                url="https://other-news.com/article",
                title="Non-LinkedIn Result",
                snippet="Should be filtered out",
                engine="duckduckgo",
            ),
        ],
        total_results=2,
        execution_time_ms=5.0,
    )

    li = LinkedInSearchProvider(search_backend=mock_backend)
    resp = await li.search(SearchQuery(query="Tonawanda Engine plant director", num_results=5))

    # Must filter to only LinkedIn results
    assert resp.total_results == 1
    r0 = resp.results[0]
    assert r0.engine == "linkedin"
    # Query tracking params stripped
    assert r0.url == "https://www.linkedin.com/in/amy-carrier-ba171b22"
    # Cleaned title with name and role
    assert "Amy Carrier" in r0.title
    assert "Plant Director" in r0.title
    assert "| LinkedIn" not in r0.title


