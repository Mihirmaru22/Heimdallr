"""Tests for Challenger Recruitment Adapters (OpenPlanter, Photon, Firecrawl)."""

import pytest
from unittest.mock import MagicMock

from argus.brain.openplanter_adapter import OpenPlanterAdapter, OpenPlanterSubtask
from argus.crawler.firecrawl_adapter import FirecrawlAdapter, html_to_firecrawl_markdown
from argus.crawler.mock import MockFetcher
from argus.crawler.models import CrawlRequest, Document
from argus.domain.objective import ResearchObjective
from argus.domain.task import ResearchTask
from argus.evals.runner import DeterministicEvalLLM
from argus.search.models import SearchQuery
from argus.search.photon_adapter import PhotonAdapter
from argus.storage.db import DatabaseManager
from argus.storage.repository import ArgusRepository


@pytest.fixture
def repo():
    db = DatabaseManager(":memory:")
    return ArgusRepository(db)


@pytest.fixture
def deterministic_llm():
    return DeterministicEvalLLM()


# ==============================================================================
# 1. OpenPlanter Adapter Tests
# ==============================================================================
@pytest.mark.asyncio
async def test_openplanter_initial_task_planning(repo, deterministic_llm):
    adapter = OpenPlanterAdapter(repo=repo, llm=deterministic_llm)
    objective = ResearchObjective(
        objective_id="obj_openplanter_test",
        target="Ford Motor Company",
        target_type="company",
        intelligence_goal="Map global operations and facilities",
        required_fields=["headquarters", "facilities"],
        success_criteria="Headquarters and facilities discovered",
    )
    repo.save_objective(objective)

    tasks = await adapter.plan_initial_tasks(objective)
    assert len(tasks) >= 1
    assert any("facilities" in t.title.lower() or "operations" in t.title.lower() for t in tasks)
    assert "Acceptance Criteria:" in tasks[0].description
    assert tasks[0].depth == 1


def test_openplanter_query_extraction(repo, deterministic_llm):
    adapter = OpenPlanterAdapter(repo=repo, llm=deterministic_llm)
    task = ResearchTask(
        objective_id="obj_test",
        title="Probe Dearborn facility",
        description="Search Queries:\n- Dearborn facility operations\n- Ford truck plant",
    )
    queries = adapter.extract_search_queries(task, objective_target="Ford")
    assert "Dearborn facility operations" in queries
    assert "Ford truck plant" in queries


def test_openplanter_stopping_criteria(repo, deterministic_llm):
    adapter = OpenPlanterAdapter(repo=repo, llm=deterministic_llm)
    objective = ResearchObjective(
        objective_id="obj_test",
        target="Ford",
        target_type="company",
        intelligence_goal="General intelligence",
        required_fields=["headquarters"],
        success_criteria="Headquarters identified",
        max_tasks=5,
    )
    # At start, should not stop
    eval_res = adapter.evaluate_stopping_criteria(objective, tasks_executed=0)
    assert eval_res.should_stop is False
    assert "headquarters" in eval_res.missing_fields

    # At max tasks, budget boundary stops
    eval_max = adapter.evaluate_stopping_criteria(objective, tasks_executed=5)
    assert eval_max.should_stop is True


# ==============================================================================
# 2. Photon Adapter Tests
# ==============================================================================
def test_photon_regex_link_extraction():
    html_sample = """
    <html>
        <body>
            <a href="/about-us">About Us</a>
            <a href="https://example.com/facilities?id=42&view=full">Facilities</a>
            <a href="javascript:void(0)">Ignore</a>
            <script src="/static/app.js"></script>
        </body>
    </html>
    """
    adapter = PhotonAdapter()
    links = adapter.extract_photon_links(html_sample, base_url="https://example.com")
    assert "https://example.com/about-us" in links
    assert "https://example.com/facilities?id=42&view=full" in links
    assert "https://example.com/static/app.js" in links
    assert not any("javascript:" in link for link in links)


@pytest.mark.asyncio
async def test_photon_search_discovery():
    mock_doc = Document(
        document_id="doc_1",
        url="https://example.com",
        title="Example Home",
        text_content="<a href='https://example.com/plant'>Plant</a>",
    )
    mock_provider = MagicMock()
    mock_provider.search = MagicMock()

    adapter = PhotonAdapter(corpus_documents=[mock_doc])
    res = await adapter.search(SearchQuery(query="operations", num_results=5))
    assert res.query == "operations"
    assert res.execution_time_ms >= 0


# ==============================================================================
# 3. Firecrawl Adapter Tests
# ==============================================================================
def test_html_to_firecrawl_markdown():
    html_sample = """
    <html>
        <head><title>Apex Manufacturing</title></head>
        <body>
            <header><nav>Navigation links to drop</nav></header>
            <h1>Plant Overview</h1>
            <p>Apex Automotive operates in Detroit, Michigan.</p>
            <ul>
                <li>Powertrain components</li>
                <li>Electric drivetrains</li>
            </ul>
            <footer>Footer boilerplate to drop</footer>
        </body>
    </html>
    """
    md, title, meta = html_to_firecrawl_markdown(html_sample, base_url="https://apex.com")
    assert title == "Apex Manufacturing"
    assert "# Plant Overview" in md
    assert "Apex Automotive operates in Detroit, Michigan." in md
    assert "- Powertrain components" in md
    assert "Navigation links to drop" not in md
    assert "Footer boilerplate to drop" not in md
    assert meta["engine"] == "firecrawl_oss_v1"


@pytest.mark.asyncio
async def test_firecrawl_adapter_fetch_and_extract():
    raw_doc = Document(
        document_id="doc_raw_1",
        url="https://apex.com/info",
        title="Apex Info",
        text_content="<p>Paragraph text here.</p>",
    )
    mock_fetcher = MockFetcher(predefined_documents={raw_doc.url: raw_doc})
    adapter = FirecrawlAdapter(fetcher=mock_fetcher)

    req = CrawlRequest(url="https://apex.com/info")
    extracted_doc = await adapter.fetch(req)
    assert extracted_doc.status_code == 200
    assert extracted_doc.fetch_method == "firecrawl_extractor"
    assert len(extracted_doc.content_units) >= 1
    assert extracted_doc.content_units[0].char_start is not None
    assert extracted_doc.content_units[0].char_end is not None
