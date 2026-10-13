import pytest

from argus.brain.models import (
    PlannedTask,
    SynthesisPayload,
    TaskPlanningPayload,
)
from argus.brain.planner import ResearchBrain
from argus.core.controller import ArgusController
from argus.crawler.mock import MockFetcher
from argus.crawler.models import Document
from argus.domain.claim import Claim, ClaimStatus
from argus.domain.entity import Entity
from argus.domain.event import EventType
from argus.domain.evidence import Evidence
from argus.domain.objective import ResearchObjective
from argus.domain.stage import ResearchStage
from argus.domain.task import ResearchTask, TaskStatus
from argus.llm.mock import MockLLMProvider
from argus.search.mock import MockSearchProvider
from argus.search.models import SearchQuery, SearchResponse, SearchResult
from argus.search.pipeline import SearchPipeline
from argus.search.provider import SearchProvider
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


@pytest.mark.asyncio
async def test_research_brain_task_decomposition(repo, sample_objective):
    mock_payload = TaskPlanningPayload(
        planned_tasks=[
            PlannedTask(
                title="Identify Ford Assembly Facilities",
                description="Map all heavy truck and utility assembly plants in the US.",
                search_queries=[
                    "Ford Motor Company assembly plants USA",
                    "Ford heavy truck manufacturing facilities",
                ],
                priority=9,
            ),
            PlannedTask(
                title="Investigate Kentucky Truck Plant Leadership",
                description="Find current plant manager of KTP.",
                search_queries=["Kentucky Truck Plant plant manager official"],
                priority=8,
            ),
        ],
        strategic_rationale="Decompose by facility mapping first, then executive leadership second.",
    )

    llm = MockLLMProvider(responses=[mock_payload])
    brain = ResearchBrain(repo=repo, llm=llm)

    tasks = await brain.plan_initial_tasks(sample_objective)

    assert len(tasks) == 2
    assert tasks[0].status == TaskStatus.READY
    assert tasks[0].priority == 9
    assert tasks[1].priority == 8

    # Verify query extraction helper
    queries = brain.extract_search_queries(tasks[0])
    assert len(queries) == 2
    assert "Ford Motor Company assembly plants USA" in queries


def test_research_brain_stopping_evaluation(repo, sample_objective):
    llm = MockLLMProvider(responses=[])
    brain = ResearchBrain(repo=repo, llm=llm)

    # Case 1: Incomplete coverage, under budget
    eval1 = brain.evaluate_stopping_criteria(sample_objective, tasks_executed=1)
    assert eval1.should_stop is False
    assert len(eval1.missing_fields) == 2

    # Case 2: Budget exhausted
    eval2 = brain.evaluate_stopping_criteria(sample_objective, tasks_executed=5)
    assert eval2.should_stop is True
    assert "budget" in eval2.reason.lower()

    # Case 3: Required fields covered by supported claims
    ent = Entity(
        canonical_name="Ford KTP",
        entity_type="facility",
        objective_id=sample_objective.objective_id,
    )
    repo.save_entity(ent)

    ev = Evidence(source_id="h1", url="https://source.com", passage="Grounded evidence")
    repo.save_evidence(ev)

    repo.save_claim(
        Claim(
            subject_entity_id=ent.entity_id,
            predicate="OPERATES_FACILITY",
            object_value="Kentucky Truck Plant",
            status=ClaimStatus.SUPPORTED,
            evidence_ids=[ev.evidence_id],
            objective_id=sample_objective.objective_id,
        )
    )
    repo.save_claim(
        Claim(
            subject_entity_id=ent.entity_id,
            predicate="HAS_PLANT_MANAGER",
            object_value="Jane Smith",
            status=ClaimStatus.SUPPORTED,
            evidence_ids=[ev.evidence_id],
            objective_id=sample_objective.objective_id,
        )
    )

    eval3 = brain.evaluate_stopping_criteria(sample_objective, tasks_executed=2)
    assert eval3.should_stop is True
    assert eval3.coverage_score == 1.0
    assert len(eval3.missing_fields) == 0


@pytest.mark.asyncio
async def test_orchestrator_end_to_end_mock_loop(repo, sample_objective):
    # 1. Search setup
    search_provider = MockSearchProvider(
        predefined_results=[
            SearchResult(
                title="Ford Kentucky Truck Plant News",
                url="https://media.ford.com/plants/ktp",
                snippet="Official overview of Kentucky Truck Plant operations in Louisville.",
            )
        ]
    )
    search_pipeline = SearchPipeline(provider=search_provider)

    # 2. Crawler setup
    doc_text = (
        "Ford Motor Company operates Kentucky Truck Plant located in Louisville. "
        "Jane Smith is the plant manager overseeing F-Series Super Duty production."
    )
    fetcher = MockFetcher(
        predefined_documents={
            "https://media.ford.com/plants/ktp": Document(
                url="https://media.ford.com/plants/ktp",
                title="KTP Overview",
                text_content=doc_text,
                status_code=200,
            )
        }
    )

    # 3. LLM Setup (Planning, Extraction, Synthesis)
    plan_payload = TaskPlanningPayload(
        planned_tasks=[
            PlannedTask(
                title="Locate Ford Truck Facilities",
                description="Find Ford heavy vehicle manufacturing plants.",
                search_queries=["Ford truck plants USA"],
                priority=10,
            )
        ],
        strategic_rationale="Initial facility discovery task.",
    )

    extraction_payload = ExtractionPayload(
        relevance=RelevanceAssessment(
            is_relevant=True,
            reasoning="Directly covers manufacturing facility and management.",
        ),
        entities=[
            ExtractedEntityItem(
                name="Ford Motor Company",
                entity_type="company",
                aliases=["Ford"],
            ),
            ExtractedEntityItem(
                name="Kentucky Truck Plant",
                entity_type="facility",
                aliases=["KTP"],
            ),
        ],
        claims=[
            ExtractedClaimItem(
                subject_name="Ford Motor Company",
                predicate="OPERATES_FACILITY",
                object_value="Kentucky Truck Plant",
                verbatim_passage="Ford Motor Company operates Kentucky Truck Plant located in Louisville.",
                confidence=0.95,
            ),
            ExtractedClaimItem(
                subject_name="Kentucky Truck Plant",
                predicate="HAS_PLANT_MANAGER",
                object_value="Jane Smith",
                verbatim_passage="Jane Smith is the plant manager overseeing F-Series Super Duty production.",
                confidence=0.95,
            ),
        ],
    )

    synthesis_payload = SynthesisPayload(
        executive_summary="Investigation verified that Ford Motor Company operates the Kentucky Truck Plant under the leadership of plant manager Jane Smith."
    )

    llm = MockLLMProvider(
        responses=[plan_payload, extraction_payload, synthesis_payload]
    )

    # 4. Engine wiring
    worker = WorkerEngine(repo=repo, llm=llm)
    verifier = ExpertVerifier(repo=repo, llm=llm)
    brain = ResearchBrain(repo=repo, llm=llm)
    controller = ArgusController(
        repo=repo,
        search_pipeline=search_pipeline,
        fetcher=fetcher,
        worker=worker,
        verifier=verifier,
        brain=brain,
    )

    # 5. Execute autonomous loop
    dossier = await controller.run(sample_objective, max_crawl_pages_per_task=2)

    # 6. Verify dossier
    assert dossier.objective_id == sample_objective.objective_id
    assert dossier.total_tasks_executed >= 1
    assert dossier.total_documents_crawled >= 1
    assert len(dossier.entities) == 2
    assert "Kentucky Truck Plant" in dossier.executive_summary

    # 7. Verify task lifecycle transitions in repository
    all_tasks = repo.list_tasks(sample_objective.objective_id)
    assert len(all_tasks) >= 1
    assert all_tasks[0].status == TaskStatus.COMPLETED

    # 8. Verify audit event chain
    events = repo.list_events(sample_objective.objective_id)
    event_types = [e.event_type for e in events]
    assert EventType.RESEARCH_STARTED in event_types
    assert EventType.TASK_CREATED in event_types
    assert EventType.TASK_STARTED in event_types
    assert EventType.SEARCH_EXECUTED in event_types
    assert EventType.TASK_COMPLETED in event_types
    assert EventType.RESEARCH_STOPPED in event_types


@pytest.mark.asyncio
async def test_cross_objective_data_isolation_and_no_premature_stopping(repo):
    """Bug 1.1 Regression Test: Verify multiple objectives in the same database do NOT

    contaminate each other's stopping evaluation or dossier synthesis.
    """
    llm = MockLLMProvider(
        responses=[
            SynthesisPayload(
                executive_summary="Objective 2 dossier with no leaked data."
            )
        ]
    )
    brain = ResearchBrain(repo=repo, llm=llm)

    # 1. Setup Objective A with satisfied required fields
    obj_a = ResearchObjective(
        target="Company A",
        target_type="company",
        intelligence_goal="Analyze Company A",
        required_fields=["revenue", "ceo"],
        success_criteria="Complete",
    )
    repo.save_objective(obj_a)

    ent_a = Entity(
        canonical_name="Company A",
        entity_type="company",
        objective_id=obj_a.objective_id,
    )
    repo.save_entity(ent_a)

    ev_a = Evidence(source_id="hA", url="https://a.com", passage="A info")
    repo.save_evidence(ev_a)

    repo.save_claim(
        Claim(
            subject_entity_id=ent_a.entity_id,
            predicate="HAS_REVENUE",
            object_value="$10B",
            status=ClaimStatus.SUPPORTED,
            evidence_ids=[ev_a.evidence_id],
            objective_id=obj_a.objective_id,
        )
    )
    repo.save_claim(
        Claim(
            subject_entity_id=ent_a.entity_id,
            predicate="HAS_CEO",
            object_value="Alice",
            status=ClaimStatus.SUPPORTED,
            evidence_ids=[ev_a.evidence_id],
            objective_id=obj_a.objective_id,
        )
    )

    # Objective A stopping criteria should be satisfied
    eval_a = brain.evaluate_stopping_criteria(obj_a, tasks_executed=1)
    assert eval_a.should_stop is True
    assert eval_a.coverage_score == 1.0

    # 2. Setup Objective B with same required fields in SAME database
    obj_b = ResearchObjective(
        target="Company B",
        target_type="company",
        intelligence_goal="Analyze Company B",
        required_fields=["revenue", "ceo"],
        success_criteria="Complete",
    )
    repo.save_objective(obj_b)

    # 3. Verify Objective B stopping criteria is NOT contaminated by Objective A
    eval_b = brain.evaluate_stopping_criteria(obj_b, tasks_executed=0)
    assert eval_b.should_stop is False, (
        "Objective B must NOT prematurely stop due to Objective A's claims"
    )
    assert eval_b.coverage_score == 0.0
    assert set(eval_b.missing_fields) == {"revenue", "ceo"}

    # 4. Verify entities and claims scoping
    assert len(repo.list_entities(objective_id=obj_b.objective_id)) == 0
    assert len(repo.list_claims(objective_id=obj_b.objective_id)) == 0

    # 5. Verify Objective B dossier synthesis contains 0 entities from Objective A
    dossier_b = await brain.synthesize_dossier(
        objective=obj_b,
        total_tasks=0,
        total_documents=0,
    )
    assert len(dossier_b.entities) == 0
    assert dossier_b.objective_id == obj_b.objective_id


@pytest.mark.asyncio
async def test_controller_avoids_duplicate_url_crawls_across_tasks(repo):
    """Bug 4.1 Regression Test:

    Verify that URLs crawled in earlier tasks are not re-crawled in subsequent tasks,
    avoiding crawler latency, redundant storage, and wasted LLM extraction calls.
    """

    class QuerySearchProvider(SearchProvider):
        async def search(self, query: SearchQuery) -> SearchResponse:
            if "query 1" in query.query:
                results = [
                    SearchResult(
                        title="Shared Plant Overview",
                        url="https://media.ford.com/shared",
                        snippet="Shared overview.",
                    ),
                    SearchResult(
                        title="Facility 1",
                        url="https://media.ford.com/facility_1",
                        snippet="Facility 1 info.",
                    ),
                ]
            else:
                results = [
                    SearchResult(
                        title="Shared Plant Overview",
                        url="https://media.ford.com/shared",
                        snippet="Shared overview.",
                    ),
                    SearchResult(
                        title="Facility 2",
                        url="https://media.ford.com/facility_2",
                        snippet="Facility 2 info.",
                    ),
                ]
            return SearchResponse(
                query=query.query,
                results=results,
                total_results=len(results),
                execution_time_ms=5.0,
            )

    search_provider = QuerySearchProvider()
    search_pipeline = SearchPipeline(provider=search_provider)

    fetcher = MockFetcher(
        predefined_documents={
            "https://media.ford.com/shared": Document(
                url="https://media.ford.com/shared",
                title="Shared Overview",
                text_content="Shared overview details about automotive manufacturing plant.",
                status_code=200,
            ),
            "https://media.ford.com/facility_1": Document(
                url="https://media.ford.com/facility_1",
                title="Facility 1",
                text_content="Plant 1 details and specifications.",
                status_code=200,
            ),
            "https://media.ford.com/facility_2": Document(
                url="https://media.ford.com/facility_2",
                title="Facility 2",
                text_content="Plant 2 details and specifications.",
                status_code=200,
            ),
        }
    )

    plan_payload = TaskPlanningPayload(
        planned_tasks=[
            PlannedTask(
                title="Task 1",
                description="First search task",
                search_queries=["query 1"],
                priority=10,
            ),
            PlannedTask(
                title="Task 2",
                description="Second search task",
                search_queries=["query 2"],
                priority=9,
            ),
        ],
        strategic_rationale="Two tasks planned.",
    )

    extraction_payload = ExtractionPayload(
        relevance=RelevanceAssessment(is_relevant=True, reasoning="Relevant content."),
        entities=[
            ExtractedEntityItem(
                name="Ford Motor Company",
                entity_type="company",
                aliases=["Ford"],
            )
        ],
        claims=[
            ExtractedClaimItem(
                subject_name="Ford Motor Company",
                predicate="HAS_FACILITY",
                object_value="Plant",
                verbatim_passage="Shared overview details about automotive manufacturing plant.",
                confidence=0.9,
            )
        ],
    )

    synthesis_payload = SynthesisPayload(executive_summary="Summary of findings.")

    # Responses: plan initial, extraction for doc 1, doc 2, doc 3, synthesis
    llm = MockLLMProvider(
        responses=[
            plan_payload,
            extraction_payload,
            extraction_payload,
            extraction_payload,
            synthesis_payload,
        ]
    )

    obj = ResearchObjective(
        target="Ford Plants",
        target_type="company",
        intelligence_goal="Find plants",
        required_fields=["plants"],
        success_criteria="Done",
        max_tasks=5,
    )
    repo.save_objective(obj)

    worker = WorkerEngine(repo=repo, llm=llm)
    verifier = ExpertVerifier(repo=repo, llm=llm)
    brain = ResearchBrain(repo=repo, llm=llm)
    controller = ArgusController(
        repo=repo,
        search_pipeline=search_pipeline,
        fetcher=fetcher,
        worker=worker,
        verifier=verifier,
        brain=brain,
    )

    dossier = await controller.run(obj, max_crawl_pages_per_task=2)

    # Verify requests recorded by fetcher
    fetched_urls = [req.url for req in fetcher.recorded_requests]
    # In Task 1: crawled shared and facility_1
    # In Task 2: shared and facility_1 were skipped because already crawled; crawled facility_2
    assert fetched_urls.count("https://media.ford.com/shared") == 1
    assert fetched_urls.count("https://media.ford.com/facility_1") == 1
    assert fetched_urls.count("https://media.ford.com/facility_2") == 1
    assert len(fetched_urls) == 3
    assert dossier.total_documents_crawled == 3


@pytest.mark.asyncio
async def test_brain_prevents_repetitive_task_spam_on_unresolvable_fields(repo):
    """Bug 4.2 Regression Test:

    Verify that follow-up tasks are not repeatedly generated for unresolvable missing fields,
    preventing infinite loops and wasted budget on duplicate searches.
    """
    llm = MockLLMProvider(responses=[])
    brain = ResearchBrain(repo=repo, llm=llm)

    obj = ResearchObjective(
        target="Secret Corp",
        target_type="company",
        intelligence_goal="Find hidden codes",
        required_fields=["unobtainable_secret"],
        success_criteria="Done",
        max_tasks=5,
    )
    repo.save_objective(obj)

    # First attempt: plans initial investigation for unobtainable_secret
    first_followups = await brain.plan_followup_tasks(
        objective=obj,
        missing_fields=["unobtainable_secret"],
        disambiguation_tasks=[],
    )
    assert len(first_followups) == 1
    assert first_followups[0].title == "Investigate unobtainable_secret for Secret Corp"

    # Second attempt: field was already attempted, should return empty to allow controller to break
    second_followups = await brain.plan_followup_tasks(
        objective=obj,
        missing_fields=["unobtainable_secret"],
        disambiguation_tasks=[],
    )
    assert len(second_followups) == 0


@pytest.mark.asyncio
async def test_controller_retries_transient_task_failures(repo):
    """Bug 4.3 Regression Test:

    Verify that transient task execution failures transition to FAILED and are requeued
    to READY for retry when retry_count < max_retries, rather than dying permanently.
    """
    attempt = 0

    class TransientSearchProvider(SearchProvider):
        async def search(self, query: SearchQuery) -> SearchResponse:
            nonlocal attempt
            attempt += 1
            if attempt == 1:
                raise ConnectionResetError("Transient network glitch")
            return SearchResponse(
                query=query.query,
                results=[],
                total_results=0,
                execution_time_ms=5.0,
            )

    search_provider = TransientSearchProvider()
    search_pipeline = SearchPipeline(provider=search_provider)
    fetcher = MockFetcher()

    plan_payload = TaskPlanningPayload(
        planned_tasks=[
            PlannedTask(
                title="Transient Task",
                description="Task that fails once then succeeds",
                search_queries=["search query"],
                priority=10,
            )
        ],
        strategic_rationale="Test retry mechanism.",
    )
    synthesis_payload = SynthesisPayload(
        executive_summary="Completed despite transient failure."
    )
    llm = MockLLMProvider(responses=[plan_payload, synthesis_payload])

    obj = ResearchObjective(
        target="Retry Target",
        target_type="company",
        intelligence_goal="Test retries",
        required_fields=["facility"],
        success_criteria="Done",
        max_tasks=5,
    )
    repo.save_objective(obj)

    worker = WorkerEngine(repo=repo, llm=llm)
    verifier = ExpertVerifier(repo=repo, llm=llm)
    brain = ResearchBrain(repo=repo, llm=llm)
    controller = ArgusController(
        repo=repo,
        search_pipeline=search_pipeline,
        fetcher=fetcher,
        worker=worker,
        verifier=verifier,
        brain=brain,
    )

    dossier = await controller.run(obj)
    assert dossier is not None

    tasks = repo.list_tasks(obj.objective_id)
    transient_task = next(t for t in tasks if t.title == "Transient Task")
    # Task should have retried and completed successfully
    assert transient_task.status == TaskStatus.COMPLETED
    assert transient_task.retry_count == 1
    assert attempt >= 2


@pytest.mark.asyncio
async def test_brain_enforces_max_depth_on_subtasks(repo):
    """Bug 4.4 Regression Test:

    Verify that task recursion depth limits (max_depth) are strictly enforced
    when spawning follow-up or disambiguation subtasks.
    """
    llm = MockLLMProvider(responses=[])
    brain = ResearchBrain(repo=repo, llm=llm)

    obj = ResearchObjective(
        target="Depth Target",
        target_type="company",
        intelligence_goal="Test depth limits",
        required_fields=["field_a"],
        success_criteria="Done",
        max_depth=2,
    )
    repo.save_objective(obj)

    # Root task at depth 0
    root_task = ResearchTask(
        objective_id=obj.objective_id,
        title="Root Task",
        description="Root",
        depth=0,
    )
    repo.save_task(root_task)

    # Child task spawned at depth 1 (depth 1 <= max_depth 2) -> Allowed
    subtasks_1 = await brain.plan_followup_tasks(
        objective=obj,
        missing_fields=[],
        disambiguation_tasks=["Contradiction 1"],
        parent_task=root_task,
    )
    assert len(subtasks_1) == 1
    assert subtasks_1[0].depth == 1
    assert subtasks_1[0].parent_task_id == root_task.task_id

    # Child task spawned at depth 2 (depth 2 <= max_depth 2) -> Allowed
    subtasks_2 = await brain.plan_followup_tasks(
        objective=obj,
        missing_fields=[],
        disambiguation_tasks=["Contradiction 2"],
        parent_task=subtasks_1[0],
    )
    assert len(subtasks_2) == 1
    assert subtasks_2[0].depth == 2
    assert subtasks_2[0].parent_task_id == subtasks_1[0].task_id

    # Attempt to spawn child task at depth 3 (depth 3 > max_depth 2) -> Prohibited
    subtasks_3 = await brain.plan_followup_tasks(
        objective=obj,
        missing_fields=[],
        disambiguation_tasks=["Contradiction 3"],
        parent_task=subtasks_2[0],
    )
    assert len(subtasks_3) == 0  # Bounded by max_depth!


@pytest.mark.asyncio
async def test_controller_five_stage_lifecycle(repo):
    """Exit Criterion 1 & 3: Controller executes all 5 stages in order."""
    search_provider = MockSearchProvider(
        predefined_results=[
            SearchResult(
                title="Ford Operations",
                url="https://media.ford.com/operations",
                snippet="Overview of facilities and management.",
            ),
        ]
    )
    search_pipeline = SearchPipeline(provider=search_provider)
    fetcher = MockFetcher(
        predefined_documents={
            "https://media.ford.com/operations": Document(
                url="https://media.ford.com/operations",
                title="Ford Operations",
                text_content="Kentucky Truck Plant operates under John Doe, Plant Manager.",
                status_code=200,
            ),
        }
    )

    plan_payload = TaskPlanningPayload(
        planned_tasks=[
            PlannedTask(
                title="Reconnaissance & Facilities",
                description="Discover plants and leaders",
                search_queries=["Ford operations"],
                priority=10,
            ),
        ],
        strategic_rationale="Initial recon.",
    )
    extraction_payload = ExtractionPayload(
        relevance=RelevanceAssessment(is_relevant=True, reasoning="Direct match"),
        entities=[
            ExtractedEntityItem(name="Ford Motor Company", entity_type="company"),
            ExtractedEntityItem(name="Kentucky Truck Plant", entity_type="facility"),
        ],
        claims=[
            ExtractedClaimItem(
                subject_name="Kentucky Truck Plant",
                predicate="HAS_PLANT_MANAGER",
                object_value="John Doe",
                verbatim_passage="Kentucky Truck Plant operates under John Doe, Plant Manager.",
                confidence=0.95,
            ),
        ],
    )
    synthesis_payload = SynthesisPayload(executive_summary="Summary of findings.")
    llm = MockLLMProvider(responses=[plan_payload, extraction_payload, synthesis_payload])

    obj = ResearchObjective(
        target="Ford",
        target_type="company",
        intelligence_goal="Map facilities and leadership",
        required_fields=["plant_manager"],
        success_criteria="Done",
        max_tasks=5,
    )
    repo.save_objective(obj)

    controller = ArgusController(
        repo=repo,
        search_pipeline=search_pipeline,
        fetcher=fetcher,
        worker=WorkerEngine(repo=repo, llm=llm),
        verifier=ExpertVerifier(repo=repo, llm=llm),
        brain=ResearchBrain(repo=repo, llm=llm),
    )

    dossier = await controller.run(obj)
    assert dossier is not None

    events = repo.list_events(obj.objective_id)
    stages_started = [
        e.payload["stage"] for e in events if e.event_type == EventType.STAGE_STARTED
    ]
    stages_completed = [
        e.payload["stage"] for e in events if e.event_type == EventType.STAGE_COMPLETED
    ]

    expected_stages = [
        ResearchStage.RECONNAISSANCE.value,
        ResearchStage.OPERATIONAL_MAPPING.value,
        ResearchStage.PERSONNEL_LEADERSHIP.value,
        ResearchStage.CONTACT_RESOLUTION.value,
        ResearchStage.SYNTHESIS.value,
    ]
    assert stages_started == expected_stages
    assert stages_completed == expected_stages


@pytest.mark.asyncio
async def test_controller_diminishing_returns_stopping(repo):
    """Exit Criterion 2: Controller halts when 3 consecutive tasks produce 0 new supported claims."""
    search_provider = MockSearchProvider(predefined_results=[])
    search_pipeline = SearchPipeline(provider=search_provider)
    fetcher = MockFetcher()

    plan_payload = TaskPlanningPayload(
        planned_tasks=[
            PlannedTask(
                title=f"Fruitless Task {i}",
                description="Looking for unindexed data",
                search_queries=[f"query {i}"],
                priority=10 - i,
            )
            for i in range(1, 6)
        ],
        strategic_rationale="5 tasks planned.",
    )
    synthesis_payload = SynthesisPayload(executive_summary="Premature stop on diminishing returns.")
    llm = MockLLMProvider(responses=[plan_payload, synthesis_payload])

    obj = ResearchObjective(
        target="Phantom Corp",
        target_type="company",
        intelligence_goal="Find ghost records",
        required_fields=["unobtainable_secret"],
        success_criteria="Done",
        max_tasks=10,
    )
    repo.save_objective(obj)

    controller = ArgusController(
        repo=repo,
        search_pipeline=search_pipeline,
        fetcher=fetcher,
        worker=WorkerEngine(repo=repo, llm=llm),
        verifier=ExpertVerifier(repo=repo, llm=llm),
        brain=ResearchBrain(repo=repo, llm=llm),
    )

    dossier = await controller.run(obj)
    assert dossier is not None
    # Must have stopped after exactly 3 tasks due to diminishing returns, NOT running all 5 or 10
    assert dossier.total_tasks_executed == 3

    events = repo.list_events(obj.objective_id)
    stopped_event = next(e for e in events if e.event_type == EventType.RESEARCH_STOPPED)
    assert "diminishing_returns" in stopped_event.payload["stop_reason"]


@pytest.mark.asyncio
async def test_brain_dynamic_branch_depth_halts_trivia_allows_personnel(repo):
    """Planner with System1 decision engine should halt municipal trivia at depth >= 2 while allowing personnel."""
    from argus.brain.system1 import System1DecisionEngine

    llm = MockLLMProvider(responses=[])
    system1 = System1DecisionEngine()
    system1._router = None
    system1._is_available = False  # Test heuristic gating

    brain = ResearchBrain(repo=repo, llm=llm, system1=system1)

    obj = ResearchObjective(
        target="US Auto Plants",
        target_type="industry",
        intelligence_goal="Find plant heads and verify operations",
        required_fields=["manufacturing_plant", "plant_head"],
        success_criteria="Done",
        max_depth=5,
    )
    repo.save_objective(obj)

    root_task = ResearchTask(
        objective_id=obj.objective_id,
        title="Initial Plant Discovery",
        description="Discover factories",
        depth=1,
    )
    repo.save_task(root_task)

    # Disambiguation tasks at depth 2 (root.depth=1 -> new_depth=2)
    # Task A: municipal boundary trivia -> Should be halted
    # Task B: personnel succession -> Should be allowed and prioritized
    followups = await brain.plan_followup_tasks(
        objective=obj,
        missing_fields=["plant_head"],
        disambiguation_tasks=[
            "Delta Township municipal boundary and tax parcel coordinates",
            "Tonawanda Engine Plant Director 2025 appointment",
        ],
        parent_task=root_task,
    )

    followup_titles = [t.title for t in followups]
    # Municipal trivia must be blocked by should_branch_deeper!
    assert not any("municipal boundary" in t.lower() for t in followup_titles)
    # Personnel succession must be allowed!
    assert any("tonawanda engine" in t.lower() for t in followup_titles)
    assert any("plant_head" in t.lower() for t in followup_titles)

    # Check priority: personnel task should have priority 10
    personnel_task = next(t for t in followups if "tonawanda engine" in t.title.lower())
    assert personnel_task.priority == 10
    assert personnel_task.depth == 2


@pytest.mark.asyncio
async def test_controller_dynamic_budget_calibration(repo):
    """ArgusController should dynamically calibrate (max_tasks, max_depth) when dynamic_budget is True."""
    from unittest.mock import MagicMock
    from argus.brain.system1 import System1DecisionEngine

    # Mock System 1 engine that returns (50, 5) for exhaustive multi-facility
    mock_system1 = MagicMock(spec=System1DecisionEngine)
    mock_system1.calibrate_budget_and_depth.return_value = (50, 5)

    search_pipeline = SearchPipeline(provider=MockSearchProvider(predefined_results=[]))
    fetcher = MockFetcher(predefined_documents={})
    llm = MockLLMProvider(
        responses=[
            TaskPlanningPayload(
                strategic_rationale="Initial plan for auto manufacturing",
                planned_tasks=[],
            ),
            SynthesisPayload(executive_summary="Summary of findings."),
        ]
    )
    worker = WorkerEngine(repo=repo, llm=llm)
    verifier = ExpertVerifier(repo=repo, llm=llm)
    brain = ResearchBrain(repo=repo, llm=llm)

    controller = ArgusController(
        repo=repo,
        search_pipeline=search_pipeline,
        fetcher=fetcher,
        worker=worker,
        verifier=verifier,
        brain=brain,
        system1=mock_system1,
    )

    # Initialize with default 15 tasks and depth 3
    obj = ResearchObjective(
        target="US Automobile Manufacturing Industry",
        target_type="industry",
        intelligence_goal="Investigate 30+ manufacturing plants and find plant heads",
        required_fields=["manufacturing_plant", "plant_head", "contact_info"],
        success_criteria="Done",
        max_tasks=15,
        max_depth=3,
        dynamic_budget=True,
    )

    dossier = await controller.run(obj)

    # Verify that calibrate_budget_and_depth was called
    mock_system1.calibrate_budget_and_depth.assert_called_once_with(
        objective_target=obj.target,
        intelligence_goal=obj.intelligence_goal,
        required_fields=obj.required_fields,
    )

    # Verify that objective in repo was updated to 50 tasks and depth 5
    saved_obj = repo.get_objective(obj.objective_id)
    assert saved_obj.max_tasks == 50
    assert saved_obj.max_depth == 5


@pytest.mark.asyncio
async def test_brain_fans_out_to_individual_plants_not_one_lump(repo):
    """Planner must fan out to each discovered plant individually rather than probing as 1 generic lump."""
    from argus.domain.entity import Entity

    llm = MockLLMProvider(responses=[])
    brain = ResearchBrain(repo=repo, llm=llm)

    obj = ResearchObjective(
        target="US Automobile Manufacturing Industry",
        target_type="industry",
        intelligence_goal="Find all plants and their plant directors",
        required_fields=["manufacturing_plant", "plant_head", "tech_lead", "contact_info"],
        success_criteria="Done",
        max_tasks=50,
        max_depth=5,
    )
    repo.save_objective(obj)

    # Simulate discovery of 3 distinct plants in reconnaissance
    plants = [
        Entity(objective_id=obj.objective_id, entity_type="manufacturing_plant", canonical_name="Tonawanda Engine Plant"),
        Entity(objective_id=obj.objective_id, entity_type="assembly_plant", canonical_name="Bowling Green Assembly"),
        Entity(objective_id=obj.objective_id, entity_type="plant", canonical_name="Kentucky Truck Plant"),
    ]
    for p in plants:
        repo.save_entity(p)

    # When missing_fields has plant_head and tech_lead:
    followup_tasks = await brain.plan_followup_tasks(
        objective=obj,
        missing_fields=["plant_head", "tech_lead"],
        disambiguation_tasks=[],
    )

    # Must NOT create generic lump "Investigate plant_head for US Automobile Manufacturing Industry"
    titles = [t.title for t in followup_tasks]
    assert not any("Investigate plant_head for US Automobile" in t for t in titles)

    # Must create exactly 3 individual, targeted plant probing tasks
    assert len(followup_tasks) == 3
    assert any("Tonawanda Engine Plant" in t.title for t in followup_tasks)
    assert any("Bowling Green Assembly" in t.title for t in followup_tasks)
    assert any("Kentucky Truck Plant" in t.title for t in followup_tasks)

    # Each task must have priority 10 (urgent)
    for t in followup_tasks:
        assert t.priority == 10
        assert "Search Queries:" in t.description
        assert "plant manager OR director" in t.description
        assert "site:linkedin.com/in" in t.description


@pytest.mark.asyncio
async def test_controller_proactive_plant_fanout_and_diminishing_returns_rescue(repo):
    """When facilities are discovered, controller must fan-out to probe plant leadership and avoid premature diminishing returns halt."""
    search_provider = MockSearchProvider(predefined_results=[])
    search_pipeline = SearchPipeline(provider=search_provider)
    fetcher = MockFetcher()

    plan_payload = TaskPlanningPayload(
        planned_tasks=[
            PlannedTask(
                title="Broad Task 1: Macro Auto Landscape",
                description="Macro survey",
                search_queries=["macro queries"],
                priority=10,
            ),
            PlannedTask(
                title="Broad Task 2: Supply Chain Overview",
                description="Supply chain survey",
                search_queries=["supply chain"],
                priority=8,
            ),
            PlannedTask(
                title="Broad Task 3: Regulatory Compliance",
                description="Compliance survey",
                search_queries=["compliance"],
                priority=6,
            ),
            PlannedTask(
                title="Broad Task 4: Future Technology",
                description="Future EV tech",
                search_queries=["tech"],
                priority=4,
            ),
        ],
        strategic_rationale="Initial survey tasks",
    )
    synthesis_payload = SynthesisPayload(executive_summary="Completed investigation with plant probing.")
    llm = MockLLMProvider(responses=[plan_payload, synthesis_payload])

    obj = ResearchObjective(
        target="US Automobile Manufacturing Industry",
        target_type="industry",
        intelligence_goal="Map assembly plants and plant heads",
        required_fields=["manufacturing_plant", "plant_head"],
        success_criteria="Done",
        max_tasks=10,
        max_depth=4,
    )
    repo.save_objective(obj)

    # Pre-seed a discovered manufacturing facility entity
    plant = Entity(
        objective_id=obj.objective_id,
        entity_type="assembly_plant",
        canonical_name="Flint Assembly Complex",
    )
    repo.save_entity(plant)

    controller = ArgusController(
        repo=repo,
        search_pipeline=search_pipeline,
        fetcher=fetcher,
        worker=WorkerEngine(repo=repo, llm=llm),
        verifier=ExpertVerifier(repo=repo, llm=llm),
        brain=ResearchBrain(repo=repo, llm=llm),
    )

    dossier = await controller.run(obj)
    assert dossier is not None

    tasks = repo.list_tasks(obj.objective_id)
    task_titles = [t.title for t in tasks]

    # Verify that controller scheduled plant fan-out task for Flint Assembly Complex
    assert any("Investigate leadership and contacts for Flint Assembly Complex" in title for title in task_titles)




