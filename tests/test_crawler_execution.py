import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from argus.brain.models import PlannedTask, SynthesisPayload, TaskPlanningPayload
from argus.brain.planner import ResearchBrain
from argus.brain.system1 import System1DecisionEngine
from argus.core.controller import ArgusController
from argus.crawler.engine import CrawlExecutionEngine
from argus.crawler.fetcher import TwoTierFetcher
from argus.crawler.mock import MockFetcher
from argus.crawler.models import CrawlRequest, Document
from argus.domain.claim import ClaimStatus
from argus.domain.event import EventType
from argus.domain.objective import ResearchObjective
from argus.domain.task import ResearchTask, TaskStatus
from argus.llm.mock import MockLLMProvider
from argus.search.mock import MockSearchProvider
from argus.search.models import SearchQuery, SearchResult
from argus.search.pipeline import SearchPipeline
from argus.storage.db import DatabaseManager
from argus.storage.repository import ArgusRepository
from argus.verifier.engine import ExpertVerifier
from argus.worker.engine import WorkerEngine
from argus.worker.models import (
    ExtractedClaimItem,
    ExtractedEntityItem,
    ExtractionPayload,
    RelevanceAssessment,
)


@pytest.fixture
def repo():
    db = DatabaseManager(":memory:")
    return ArgusRepository(db)


@pytest.fixture
def sample_objective(repo):
    obj = ResearchObjective(
        target="US Automobile Manufacturers",
        target_type="industry",
        intelligence_goal="Identify plants, locations, and key leadership.",
        required_fields=["facility", "manager"],
        success_criteria="At least 2 facilities identified",
        max_tasks=5,
    )
    repo.save_objective(obj)
    return obj


# ==============================================================================
# TEST 1 — CrawlRequest enqueue
# Selected URL -> CrawlRequest -> Crawlee queue
# ==============================================================================
@pytest.mark.asyncio
async def test_01_crawl_request_enqueue(repo, sample_objective):
    mock_fetcher = MockFetcher()
    engine = CrawlExecutionEngine(fetcher=mock_fetcher, repo=repo, memory_storage=True)

    url = "https://media.ford.com/plants/kentucky-truck"
    req = CrawlRequest(
        url=url,
        objective_id=sample_objective.objective_id,
        research_task_id="task_001",
        priority=8,
    )

    enqueued, reason = await engine.enqueue_request(req)
    assert enqueued is True
    assert reason == "enqueued"

    rq = await engine.get_or_create_queue(sample_objective.objective_id)
    crawlee_req = await rq.fetch_next_request()
    assert crawlee_req is not None
    assert crawlee_req.url == url
    assert crawlee_req.user_data.get("objective_id") == sample_objective.objective_id
    assert crawlee_req.user_data.get("research_task_id") == "task_001"

    # Verify audit events
    events = repo.list_events(objective_id=sample_objective.objective_id)
    event_types = [e.event_type for e in events]
    assert EventType.CRAWL_REQUEST_CREATED in event_types
    assert EventType.CRAWL_REQUEST_ENQUEUED in event_types


# ==============================================================================
# TEST 2 — Duplicate URL
# Same URL discovered multiple times -> Crawlee prevents duplicate acquisition
# ==============================================================================
@pytest.mark.asyncio
async def test_02_duplicate_url_deduplication(repo, sample_objective):
    mock_fetcher = MockFetcher()
    engine = CrawlExecutionEngine(fetcher=mock_fetcher, repo=repo, memory_storage=True)

    url1 = "https://media.ford.com/plants/ktp?utm_source=twitter"
    url2 = "https://media.ford.com/plants/ktp?utm_medium=social#details"

    req1 = CrawlRequest(url=url1, objective_id=sample_objective.objective_id)
    req2 = CrawlRequest(url=url2, objective_id=sample_objective.objective_id)

    enqueued1, reason1 = await engine.enqueue_request(req1)
    enqueued2, reason2 = await engine.enqueue_request(req2)

    assert enqueued1 is True
    assert reason1 == "enqueued"
    assert enqueued2 is False
    assert reason2 == "duplicate"

    stats = await engine.get_queue_stats(sample_objective.objective_id)
    assert stats["total_requests"] == 1

    events = repo.list_events(objective_id=sample_objective.objective_id)
    event_types = [e.event_type for e in events]
    assert EventType.CRAWL_REQUEST_SKIPPED in event_types


# ==============================================================================
# TEST 3 — Security rejection
# Try localhost/private/metadata URLs -> Argus rejects before acquisition
# ==============================================================================
@pytest.mark.asyncio
async def test_03_security_rejection(repo, sample_objective):
    mock_fetcher = MockFetcher()
    engine = CrawlExecutionEngine(fetcher=mock_fetcher, repo=repo, memory_storage=True)

    disallowed_urls = [
        "http://localhost:8080/admin",
        "http://127.0.0.1/test",
        "http://169.254.169.254/latest/meta-data",
        "http://metadata.google.internal/computeMetadata",
        "http://192.168.1.1/status",
        "file:///etc/passwd",
    ]

    for bad_url in disallowed_urls:
        req = CrawlRequest(url=bad_url, objective_id=sample_objective.objective_id)
        enqueued, reason = await engine.enqueue_request(req)
        assert enqueued is False
        assert reason == "rejected_unsafe"

    stats = await engine.get_queue_stats(sample_objective.objective_id)
    assert stats["total_requests"] == 0

    events = repo.list_events(objective_id=sample_objective.objective_id)
    rejected_events = [e for e in events if e.event_type == EventType.CRAWL_REQUEST_REJECTED]
    assert len(rejected_events) == len(disallowed_urls)


# ==============================================================================
# TEST 4 — HTTP-first
# Static page: HTTP path is used, Playwright should not be launched
# ==============================================================================
@pytest.mark.asyncio
async def test_04_http_first_static_page(repo, sample_objective):
    fetcher = TwoTierFetcher()
    engine = CrawlExecutionEngine(fetcher=fetcher, repo=repo, memory_storage=True)

    static_html = (
        "<!DOCTYPE html><html><head><title>Kentucky Truck Plant</title></head>"
        "<body><h1>Kentucky Truck Plant</h1>"
        "<p>" + ("Ford builds F-Series Super Duty trucks in Louisville, Kentucky. " * 5) + "</p>"
        "</body></html>"
    )

    req = CrawlRequest(
        url="https://media.ford.com/plants/ktp",
        objective_id=sample_objective.objective_id,
    )
    await engine.enqueue_request(req)

    # Mock HTTP response via httpx and spy on _fetch_browser
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.url = "https://media.ford.com/plants/ktp"
    mock_response.content = static_html.encode("utf-8")
    mock_response.text = static_html

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        with patch.object(fetcher, "_fetch_browser", new_callable=AsyncMock) as mock_browser:
            docs = await engine.process_next_batch(sample_objective.objective_id, max_pages=1)

            assert len(docs) == 1
            doc = docs[0]
            assert doc.fetch_method == "http"
            assert "Kentucky Truck Plant" in doc.text_content
            # Verify Playwright was NOT called
            mock_browser.assert_not_called()


# ==============================================================================
# TEST 5 — Browser fallback
# Dynamic page: browser path is reached according to existing TwoTierFetcher behavior
# ==============================================================================
@pytest.mark.asyncio
async def test_05_browser_fallback_dynamic_page(repo, sample_objective):
    fetcher = TwoTierFetcher()
    engine = CrawlExecutionEngine(fetcher=fetcher, repo=repo, memory_storage=True)

    spa_shell = (
        "<!DOCTYPE html><html><head><title>App</title></head>"
        "<body><div id='root'></div>"
        "<noscript>You need JavaScript to view this application.</noscript>"
        "</body></html>"
    )

    req = CrawlRequest(
        url="https://media.ford.com/interactive-map",
        objective_id=sample_objective.objective_id,
    )
    await engine.enqueue_request(req)

    mock_http_response = AsyncMock()
    mock_http_response.status_code = 200
    mock_http_response.url = "https://media.ford.com/interactive-map"
    mock_http_response.content = spa_shell.encode("utf-8")
    mock_http_response.text = spa_shell

    browser_rendered_doc = Document(
        url="https://media.ford.com/interactive-map",
        title="Interactive Facility Map",
        text_content="Interactive map loaded: Kentucky Truck Plant, Michigan Assembly Plant.",
        status_code=200,
        fetch_method="playwright",
    )

    with patch("httpx.AsyncClient.get", return_value=mock_http_response):
        with patch.object(
            fetcher, "_fetch_browser", new_callable=AsyncMock, return_value=browser_rendered_doc
        ) as mock_browser:
            docs = await engine.process_next_batch(sample_objective.objective_id, max_pages=1)

            assert len(docs) == 1
            assert docs[0].fetch_method == "playwright"
            assert "Interactive map loaded" in docs[0].text_content
            mock_browser.assert_called_once()


# ==============================================================================
# TEST 6 — Dynamic URL discovery
# Document produces additional URLs -> discover -> normalize -> security -> queue
# ==============================================================================
@pytest.mark.asyncio
async def test_06_dynamic_url_discovery(repo, sample_objective):
    html_with_links = """
    <html><body>
        <p>Parent plant directory.</p>
        <a href="/plants/michigan-assembly">Michigan Assembly Plant</a>
        <a href="https://media.ford.com/plants/chicago-assembly">Chicago Assembly</a>
        <a href="http://127.0.0.1/evil">SSRF Target</a>
        <a href="javascript:void(0)">Ignored JS Link</a>
    </body></html>
    """
    mock_fetcher = MockFetcher({
        "https://media.ford.com/plants": Document(
            url="https://media.ford.com/plants",
            title="Plants Directory",
            text_content=html_with_links,
            status_code=200,
            fetch_method="mock",
        )
    })
    engine = CrawlExecutionEngine(fetcher=mock_fetcher, repo=repo, memory_storage=True)

    parent_req = CrawlRequest(
        url="https://media.ford.com/plants",
        objective_id=sample_objective.objective_id,
        depth=0,
    )
    await engine.enqueue_request(parent_req)

    # Process parent batch with dynamic link discovery enabled
    docs = await engine.process_next_batch(
        objective_id=sample_objective.objective_id,
        max_pages=1,
        discover_links=True,
        max_depth=2,
    )
    assert len(docs) == 1

    # Verify newly enqueued child links in Crawlee queue
    rq = await engine.get_or_create_queue(sample_objective.objective_id)
    child_req1 = await rq.fetch_next_request()
    assert child_req1 is not None
    assert child_req1.url in (
        "https://media.ford.com/plants/michigan-assembly",
        "https://media.ford.com/plants/chicago-assembly",
    )
    assert child_req1.user_data.get("depth") == 1

    child_req2 = await rq.fetch_next_request()
    assert child_req2 is not None
    assert child_req2.user_data.get("depth") == 1

    # SSRF link must have been rejected
    child_req3 = await rq.fetch_next_request()
    assert child_req3 is None


# ==============================================================================
# TEST 7 — Retry
# Transient failure -> crawl request retries/reclaims, NO duplicate ResearchTasks
# ==============================================================================
@pytest.mark.asyncio
async def test_07_retry_transient_failure(repo, sample_objective):
    attempts = 0

    class FlakyFetcher(MockFetcher):
        async def fetch(self, request: CrawlRequest) -> Document:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return Document(
                    url=request.url,
                    title="503 Service Unavailable",
                    text_content="",
                    status_code=503,
                    fetch_method="http",
                    error_message="Gateway Unavailable",
                )
            return Document(
                url=request.url,
                title="Recovered Page",
                text_content="Successfully acquired after transient 503 recovery.",
                status_code=200,
                fetch_method="http",
            )

    engine = CrawlExecutionEngine(fetcher=FlakyFetcher(), repo=repo, memory_storage=True)

    req = CrawlRequest(
        url="https://media.ford.com/flaky-service",
        objective_id=sample_objective.objective_id,
        research_task_id="task_flaky_1",
        max_retries=2,
    )
    await engine.enqueue_request(req)

    # First attempt: 503 triggers reclaim
    docs_first_try = await engine.process_next_batch(sample_objective.objective_id, max_pages=1)
    assert len(docs_first_try) == 0
    assert attempts == 1

    events = repo.list_events(objective_id=sample_objective.objective_id)
    reclaimed = [e for e in events if e.event_type == EventType.CRAWL_REQUEST_RECLAIMED]
    assert len(reclaimed) == 1

    # Second attempt: succeeds
    docs_second_try = await engine.process_next_batch(sample_objective.objective_id, max_pages=1)
    assert len(docs_second_try) == 1
    assert attempts == 2
    assert docs_second_try[0].status_code == 200

    # Ensure no duplicate ResearchTasks were created in repo
    tasks = repo.list_tasks(sample_objective.objective_id)
    assert len(tasks) == 0  # No tasks injected or duplicated by crawl layer


# ==============================================================================
# TEST 8 — Research/crawl separation
# Completing CrawlRequest does NOT automatically mark ResearchTask completed
# ==============================================================================
@pytest.mark.asyncio
async def test_08_research_crawl_separation(repo, sample_objective):
    research_task = ResearchTask(
        objective_id=sample_objective.objective_id,
        title="Find Louisville Facility Leadership",
        description="Official plant manager investigation",
        status=TaskStatus.RUNNING,
    )
    repo.save_task(research_task)

    mock_fetcher = MockFetcher()
    engine = CrawlExecutionEngine(fetcher=mock_fetcher, repo=repo, memory_storage=True)

    req = CrawlRequest(
        url="https://media.ford.com/plants/louisville",
        objective_id=sample_objective.objective_id,
        research_task_id=research_task.task_id,
    )
    await engine.enqueue_request(req)

    # Execute crawl batch
    docs = await engine.process_next_batch(sample_objective.objective_id, max_pages=1)
    assert len(docs) == 1

    # Verify ResearchTask remains in its current state (RUNNING), NOT auto-completed
    refreshed_task = repo.get_task(research_task.task_id)
    assert refreshed_task is not None
    assert refreshed_task.status == TaskStatus.RUNNING


# ==============================================================================
# TEST 9 — Persistence / resume
# Pending crawl requests remain recoverable after crawler interruption
# ==============================================================================
@pytest.mark.asyncio
async def test_09_persistence_and_resume(repo, sample_objective):
    temp_dir = tempfile.mkdtemp(prefix="argus_crawlee_test_")
    try:
        mock_fetcher = MockFetcher()

        # Engine 1: Enqueue two requests, process one, leave one pending
        engine1 = CrawlExecutionEngine(
            fetcher=mock_fetcher,
            repo=repo,
            storage_dir=temp_dir,
            memory_storage=False,
        )

        req1 = CrawlRequest(
            url="https://media.ford.com/page-1",
            objective_id=sample_objective.objective_id,
            research_task_id="task_pers_1",
        )
        req2 = CrawlRequest(
            url="https://media.ford.com/page-2",
            objective_id=sample_objective.objective_id,
            research_task_id="task_pers_2",
        )

        await engine1.enqueue_request(req1)
        await engine1.enqueue_request(req2)

        # Process first page
        docs1 = await engine1.process_next_batch(sample_objective.objective_id, max_pages=1)
        assert len(docs1) == 1
        assert docs1[0].url == "https://media.ford.com/page-1"

        # Simulate crawler/process interruption and resume with Engine 2 pointing to same storage
        engine2 = CrawlExecutionEngine(
            fetcher=mock_fetcher,
            repo=repo,
            storage_dir=temp_dir,
            memory_storage=False,
        )

        # Engine 2 should pick up pending page 2
        docs2 = await engine2.process_next_batch(sample_objective.objective_id, max_pages=1)
        assert len(docs2) == 1
        assert docs2[0].url == "https://media.ford.com/page-2"

        # Queue is now finished
        is_done = await engine2.is_queue_finished(sample_objective.objective_id)
        assert is_done is True
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ==============================================================================
# TEST 10 — Provenance
# Acquired Document retains relationship to URL, crawl_request_id, task_id, objective_id
# ==============================================================================
@pytest.mark.asyncio
async def test_10_provenance_retention(repo, sample_objective):
    mock_fetcher = MockFetcher()
    engine = CrawlExecutionEngine(fetcher=mock_fetcher, repo=repo, memory_storage=True)

    target_url = "https://media.ford.com/provenance-check"
    req = CrawlRequest(
        url=target_url,
        objective_id=sample_objective.objective_id,
        research_task_id="task_prov_99",
    )
    await engine.enqueue_request(req)

    docs = await engine.process_next_batch(sample_objective.objective_id, max_pages=1)
    assert len(docs) == 1
    doc = docs[0]

    assert doc.url == target_url
    assert doc.crawl_request_id == req.request_id
    assert doc.task_id == "task_prov_99"
    assert doc.research_task_id == "task_prov_99"
    assert doc.objective_id == sample_objective.objective_id


# ==============================================================================
# TEST 11 — End-to-end
# Research Objective -> Research Task -> SearchPipeline -> Laya triage ->
# CrawlRequest -> Crawlee -> TwoTierFetcher -> Document -> Extraction
# ==============================================================================
@pytest.mark.asyncio
async def test_11_end_to_end_research_pipeline(repo, sample_objective):
    # 1. Search provider setup (upstream)
    search_provider = MockSearchProvider(
        predefined_results=[
            SearchResult(
                url="https://media.ford.com/plants/ktp",
                title="Kentucky Truck Plant",
                snippet="Official plant details and leadership for KTP in Louisville.",
            ),
            SearchResult(
                url="http://127.0.0.1/malicious",
                title="SSRF Attack Link",
                snippet="Internal IP to be blocked.",
            ),
        ]
    )
    search_pipeline = SearchPipeline(provider=search_provider)

    ktp_text = (
        "The Ford Kentucky Truck Plant is a major automobile manufacturing facility "
        "located in Louisville, Kentucky. It produces Ford Super Duty trucks, Ford Expedition, "
        "and Lincoln Navigator. The current Plant Manager is Jane Smith. Operations include stamping, "
        "body assembly, paint, and final vehicle testing."
    )
    mock_fetcher = MockFetcher({
        "https://media.ford.com/plants/ktp": Document(
            url="https://media.ford.com/plants/ktp",
            title="Kentucky Truck Plant",
            text_content=ktp_text,
            status_code=200,
            fetch_method="mock",
        )
    })

    # 3. LLM payloads for planner, worker, and synthesis
    plan_payload = TaskPlanningPayload(
        planned_tasks=[
            PlannedTask(
                title="Identify Ford Plants",
                description="Map major facilities",
                search_queries=["Ford Motor Company plants USA"],
                priority=10,
            )
        ],
        strategic_rationale="Initial facility reconnaissance.",
    )

    extraction_payload = ExtractionPayload(
        relevance=RelevanceAssessment(
            is_relevant=True,
            reasoning="Document contains details about Kentucky Truck Plant and leadership.",
        ),
        entities=[
            ExtractedEntityItem(
                name="Kentucky Truck Plant",
                entity_type="facility",
                attributes={"location": "Louisville, Kentucky", "plant_head": "Jane Smith"},
            )
        ],
        claims=[
            ExtractedClaimItem(
                subject_name="Kentucky Truck Plant",
                predicate="located_in",
                object_value="Louisville, Kentucky",
                confidence=0.95,
                verbatim_passage="Located in Louisville, Kentucky.",
            ),
            ExtractedClaimItem(
                subject_name="Kentucky Truck Plant",
                predicate="plant_head",
                object_value="Jane Smith",
                confidence=0.92,
                verbatim_passage="Plant Manager: Jane Smith.",
            ),
        ],
    )

    synthesis_payload = SynthesisPayload(
        executive_summary="Identified Kentucky Truck Plant led by Jane Smith.",
        confidence_assessment="High confidence based on official media sources.",
        gaps_and_limitations=[],
    )

    llm = MockLLMProvider(responses=[plan_payload, extraction_payload, synthesis_payload])

    # 4. Engine components
    system1 = System1DecisionEngine()
    system1._router = None
    system1._is_available = False  # Deterministic test mode
    brain = ResearchBrain(repo=repo, llm=llm, system1=system1)
    worker = WorkerEngine(repo=repo, llm=llm)
    verifier = ExpertVerifier(repo=repo, llm=llm)

    # CrawlExecutionEngine managing crawl requests via Crawlee
    crawl_engine = CrawlExecutionEngine(fetcher=mock_fetcher, repo=repo, memory_storage=True)

    controller = ArgusController(
        repo=repo,
        search_pipeline=search_pipeline,
        fetcher=mock_fetcher,
        worker=worker,
        verifier=verifier,
        brain=brain,
        system1=system1,
        crawl_engine=crawl_engine,
    )

    # 5. Run end-to-end research loop
    dossier = await controller.run(sample_objective, max_crawl_pages_per_task=2)

    # 6. Verify dossier and downstream extraction
    assert dossier.objective_id == sample_objective.objective_id
    assert dossier.total_tasks_executed >= 1
    assert dossier.total_documents_crawled >= 1
    assert "Kentucky Truck Plant" in dossier.executive_summary

    # 7. Verify crawl lifecycle audit trail recorded through Crawlee
    events = repo.list_events(objective_id=sample_objective.objective_id)
    event_types = [e.event_type for e in events]

    assert EventType.SEARCH_EXECUTED in event_types
    assert EventType.CRAWL_REQUEST_ENQUEUED in event_types
    assert EventType.CRAWL_REQUEST_STARTED in event_types
    assert EventType.CRAWL_REQUEST_SUCCEEDED in event_types

    # Malicious URL was rejected before entering queue
    assert "http://127.0.0.1/malicious" not in repo.get_crawled_urls()
