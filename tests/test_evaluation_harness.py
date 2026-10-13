"""Tests for the Argus Evaluation Harness.

Covers the 22 mandatory evaluation harness test requirements:
1. benchmark task validation
2. ground-truth schema validation
3. benchmark version loading
4. deterministic entity grading
5. deterministic field grading
6. claim grading
7. evidence coverage grading
8. evidence passage validation
9. provenance grading
10. epistemic status grading
11. contradiction grading
12. unknown/not-found grading
13. completeness calculation
14. unsupported claim calculation
15. trajectory capture
16. efficiency metric calculation
17. failure classification
18. benchmark result persistence
19. baseline comparison
20. regression detection
21. benchmark leakage protection
22. report generation
+ multi-run repeatability/stability evaluation
"""

from datetime import UTC, datetime
from pathlib import Path
import pytest

from argus.crawler.extractor import DocumentExtractor
from argus.crawler.models import ContentUnit, Document
from argus.domain.claim import Claim, ClaimStatus
from argus.domain.entity import Entity
from argus.domain.event import EventType, ResearchEvent
from argus.domain.evidence import Evidence
from argus.domain.objective import ResearchObjective
from argus.evals.benchmark import BenchmarkSuite
from argus.evals.corpus import build_default_frozen_corpus
from argus.evals.graders import (
    ContradictionGrader,
    EntityGrader,
    EpistemicGrader,
    EvidenceGrader,
    FieldGrader,
    IndependentGrader,
    SecurityGrader,
    normalize_text,
)
from argus.evals.metrics import (
    MetricAggregator,
    RegressionComparator,
    StabilityEvaluator,
)
from argus.evals.models import (
    BenchmarkRunResult,
    BenchmarkSummaryMetrics,
    DifficultyLevel,
    EvaluationTask,
    ExpectedClaim,
    ExpectedContradiction,
    ExpectedEntity,
    ExpectedField,
    FailureCategory,
    GroundTruth,
    SecurityExpectation,
    TaskCategory,
    TaskGradeResult,
    TaskTrajectory,
    TrajectoryEvent,
)
from argus.evals.report import EvaluationReporter
from argus.evals.runner import ArgusEvalRunner, DeterministicEvalLLM
from argus.evals.trajectory import TrajectoryRecorder
from argus.storage.db import DatabaseManager
from argus.storage.repository import ArgusRepository


# ==============================================================================
# 1. Benchmark Task Validation
# ==============================================================================
def test_benchmark_task_validation():
    """Verify EvaluationTask model validates mandatory fields and structure."""
    task = EvaluationTask(
        task_id="test_01",
        version="1.0",
        category=TaskCategory.ENTITY_DISCOVERY,
        difficulty=DifficultyLevel.EASY,
        title="Discover Ford",
        objective_target="Ford Motor Company",
        target_type="company",
        intelligence_goal="Find core operations",
        required_fields=["company_name", "headquarters"],
        success_criteria="Ford found in Dearborn",
        ground_truth=GroundTruth(
            entities=[
                ExpectedEntity(canonical_name="Ford Motor Company", entity_type="company")
            ]
        ),
    )
    assert task.task_id == "test_01"
    assert task.category == TaskCategory.ENTITY_DISCOVERY
    assert task.difficulty == DifficultyLevel.EASY
    assert len(task.ground_truth.entities) == 1


# ==============================================================================
# 2. Ground-Truth Schema Validation
# ==============================================================================
def test_ground_truth_schema_validation():
    """Verify GroundTruth schema accepts entities, fields, claims, contradictions, and security expectations."""
    gt = GroundTruth(
        version="1.0",
        last_verified_at="2026-02-01T00:00:00Z",
        entities=[
            ExpectedEntity(
                canonical_name="Dearborn Truck Plant",
                entity_type="facility",
                accepted_aliases=["DTP"],
                unacceptable_merges=["Kentucky Truck Plant"],
            )
        ],
        fields=[
            ExpectedField(field_name="location", accepted_values=["Dearborn, MI", "Dearborn, Michigan"])
        ],
        claims=[
            ExpectedClaim(
                subject_name="Dearborn Truck Plant",
                predicate="PRODUCES",
                object_value="Ford F-150",
                expected_status=ClaimStatus.SUPPORTED,
            )
        ],
        contradictions=[
            ExpectedContradiction(
                field_or_predicate="CAPEX",
                conflicting_values=["$1B", "$2B"],
                resolved_value="$1B",
            )
        ],
        expected_unknowns=["secret_code"],
        security=SecurityExpectation(
            expected_injection_resistant=True,
            forbidden_tokens_in_output=["HACKED"],
            disallowed_urls=["http://169.254.169.254/"],
        ),
    )
    assert len(gt.entities) == 1
    assert len(gt.fields) == 1
    assert len(gt.claims) == 1
    assert len(gt.contradictions) == 1
    assert "secret_code" in gt.expected_unknowns
    assert "HACKED" in gt.security.forbidden_tokens_in_output


# ==============================================================================
# 3. Benchmark Version Loading
# ==============================================================================
def test_benchmark_version_loading():
    """Verify loading default benchmark tasks v1.0 and filtering by core subset."""
    suite = BenchmarkSuite.load_from_file()
    assert suite.version == "1.0"
    assert len(suite.tasks) == 50

    # Verify category distribution
    cat_counts = {}
    for t in suite.tasks:
        cat_counts[t.category] = cat_counts.get(t.category, 0) + 1

    assert cat_counts[TaskCategory.ENTITY_DISCOVERY] == 8
    assert cat_counts[TaskCategory.STRUCTURED_EXTRACTION] == 8
    assert cat_counts[TaskCategory.PLANT_FACILITY_DISCOVERY] == 8
    assert cat_counts[TaskCategory.LEADERSHIP_RESEARCH] == 6
    assert cat_counts[TaskCategory.MULTI_HOP] == 6
    assert cat_counts[TaskCategory.TEMPORAL] == 5
    assert cat_counts[TaskCategory.CONTRADICTION] == 5
    assert cat_counts[TaskCategory.MISSING_INFORMATION] == 2
    assert cat_counts[TaskCategory.ADVERSARIAL_INJECTION] == 2

    # Check core subset
    core_tasks = suite.filter(is_core=True)
    assert len(core_tasks) >= 5
    assert all(t.is_core for t in core_tasks)


# ==============================================================================
# 4. Deterministic Entity Grading
# ==============================================================================
def test_deterministic_entity_grading():
    """Verify EntityGrader precision, recall, F1, alias matching, and false merge detection."""
    expected = [
        ExpectedEntity(
            canonical_name="Ford Motor Company",
            entity_type="company",
            accepted_aliases=["Ford", "FoMoCo"],
            unacceptable_merges=["Ford Credit"],
        ),
        ExpectedEntity(
            canonical_name="Dearborn Truck Plant",
            entity_type="facility",
            accepted_aliases=["DTP"],
        ),
    ]

    # Perfect extraction with alias
    extracted_good = [
        Entity(canonical_name="Ford", entity_type="company", aliases=[]),
        Entity(canonical_name="Dearborn Truck Plant", entity_type="facility", aliases=[]),
    ]
    p, r, f1, res_acc, f_merge, f_split = EntityGrader.grade(extracted_good, expected)
    assert p == 1.0
    assert r == 1.0
    assert f1 == 1.0
    assert f_merge == 0
    assert f_split == 0

    # Test false merge violation
    extracted_bad_merge = [
        Entity(canonical_name="Ford Motor Company", entity_type="company", aliases=["Ford Credit"]),
        Entity(canonical_name="Dearborn Truck Plant", entity_type="facility", aliases=[]),
    ]
    _, _, _, _, f_merge, _ = EntityGrader.grade(extracted_bad_merge, expected)
    assert f_merge > 0


# ==============================================================================
# 5. Deterministic Field Grading
# ==============================================================================
def test_deterministic_field_grading():
    """Verify FieldGrader accepted values and variation tolerance."""
    expected_fields = [
        ExpectedField(field_name="location", accepted_values=["Louisville, Kentucky", "Louisville, KY"]),
        ExpectedField(field_name="ceo", accepted_values=["Jim Farley", "James Farley"]),
    ]
    extracted_claims = [
        Claim(
            subject_entity_id="e1",
            predicate="LOCATED_IN",
            object_value="Louisville, KY",
            status=ClaimStatus.SUPPORTED,
        ),
        Claim(
            subject_entity_id="e1",
            predicate="HAS_CEO",
            object_value="James Farley",
            status=ClaimStatus.SUPPORTED,
        ),
    ]
    entities = [Entity(entity_id="e1", canonical_name="Ford", entity_type="company")]

    acc, prec, rec = FieldGrader.grade(extracted_claims, expected_fields, entities)
    assert acc == 1.0
    assert prec == 1.0
    assert rec == 1.0


# ==============================================================================
# 6. Claim Grading
# ==============================================================================
def test_claim_grading():
    """Verify claim evaluation handles matches and omissions properly."""
    expected = [
        ExpectedClaim(subject_name="Tesla", predicate="HAS_CEO", object_value="Elon Musk")
    ]
    claims = [
        Claim(
            subject_entity_id="e_tesla",
            predicate="HAS_CEO",
            object_value="Elon Musk",
            status=ClaimStatus.SUPPORTED,
        )
    ]
    ep_acc, escalations = EpistemicGrader.grade(claims, expected)
    assert ep_acc == 1.0
    assert escalations == 0


# ==============================================================================
# 7. Evidence Coverage Grading
# ==============================================================================
def test_evidence_coverage_grading():
    """Verify evidence coverage metric calculates proportion of grounded claims."""
    doc = Document(
        document_id="d1",
        url="https://example.com/test",
        title="Test",
        text_content="Tesla is located in Austin, Texas. It produces electric vehicles.",
    )
    ev = Evidence(
        evidence_id="ev1",
        document_id="d1",
        source_id="d1",
        url="https://example.com/test",
        passage="Tesla is located in Austin, Texas.",
    )
    # Claim 1 has evidence, Claim 2 has none
    c1 = Claim(
        subject_entity_id="e1",
        predicate="LOCATED_IN",
        object_value="Austin, Texas",
        evidence_ids=["ev1"],
    )
    c2 = Claim(
        subject_entity_id="e1",
        predicate="PRODUCES",
        object_value="Electric Vehicles",
        evidence_ids=[],
    )

    ev_cov, ev_corr, unsupp, hall_ev, hall_qt = EvidenceGrader.grade(
        claims=[c1, c2],
        evidences=[ev],
        documents=[doc],
    )
    assert ev_cov == 0.50
    assert unsupp == 0.50


# ==============================================================================
# 8. Evidence Passage Validation
# ==============================================================================
def test_evidence_passage_validation():
    """Verify evidence grader detects hallucinated passages not present in source document."""
    doc = Document(
        document_id="d1",
        url="https://example.com/test",
        title="Doc",
        text_content="The facility produces batteries.",
    )
    # Fabricated quote
    fake_ev = Evidence(
        evidence_id="ev_fake",
        document_id="d1",
        source_id="d1",
        url="https://example.com/test",
        passage="FABRICATED PASSAGE NEVER WRITTEN IN DOCUMENT",
    )
    c = Claim(
        subject_entity_id="e1",
        predicate="PRODUCES",
        object_value="batteries",
        evidence_ids=["ev_fake"],
    )

    _, _, unsupp, _, hall_qt = EvidenceGrader.grade(
        claims=[c],
        evidences=[fake_ev],
        documents=[doc],
    )
    assert hall_qt > 0.0
    assert unsupp == 1.0


# ==============================================================================
# 9. Provenance Grading
# ==============================================================================
def test_provenance_grading():
    """Verify ContentUnit character offsets and unit IDs are validated."""
    html = "<html><body><h1>Overview</h1><p>Dearborn Truck Plant produces the F-150.</p></body></html>"
    res = DocumentExtractor.extract_structured(raw_html=html, url="https://example.com/prov", document_id="doc_prov")
    doc = Document(
        document_id="doc_prov",
        url="https://example.com/prov",
        title="Prov",
        text_content=res.clean_text,
        content_units=res.content_units,
    )
    target_passage = "Dearborn Truck Plant produces the F-150."
    assert target_passage in doc.text_content
    start = doc.text_content.index(target_passage)
    end = start + len(target_passage)

    matched_unit = doc.find_unit_for_offset(start)
    assert matched_unit is not None
    assert target_passage in matched_unit.text

    ev = Evidence(
        evidence_id="ev_prov",
        document_id=doc.document_id,
        source_id=doc.document_id,
        url=doc.url,
        passage=target_passage,
        char_start=start,
        char_end=end,
        unit_id=matched_unit.unit_id,
    )
    c = Claim(
        subject_entity_id="e1",
        predicate="PRODUCES",
        object_value="F-150",
        evidence_ids=[ev.evidence_id],
    )

    ev_cov, ev_corr, unsupp, hall_ev, hall_qt = EvidenceGrader.grade(
        claims=[c],
        evidences=[ev],
        documents=[doc],
    )
    assert ev_corr == 1.0
    assert hall_qt == 0.0
    assert unsupp == 0.0


# ==============================================================================
# 10. Epistemic Status Grading
# ==============================================================================
def test_epistemic_status_grading():
    """Verify EpistemicGrader penalizes status escalation (e.g. UNKNOWN claimed as SUPPORTED)."""
    expected = [
        ExpectedClaim(
            subject_name="Secret Lab",
            predicate="HAS_MANAGER",
            object_value="Unknown",
            expected_status=ClaimStatus.UNKNOWN,
        )
    ]
    # Escalated claim
    escalated_claim = Claim(
        subject_entity_id="e_sec",
        predicate="HAS_MANAGER",
        object_value="Jane Doe",
        status=ClaimStatus.SUPPORTED,  # VIOLATION: ground truth is UNKNOWN
    )
    accuracy, escalations = EpistemicGrader.grade([escalated_claim], expected)
    assert accuracy == 0.0
    assert escalations == 1


# ==============================================================================
# 11. Contradiction Grading
# ==============================================================================
def test_contradiction_grading():
    """Verify ContradictionGrader detects marked contradictions."""
    expected_contra = [
        ExpectedContradiction(
            field_or_predicate="CAPEX",
            conflicting_values=["$5.6B", "$11.4B"],
        )
    ]
    # Argus marked this claim as CONTRADICTED
    c = Claim(
        subject_entity_id="e1",
        predicate="CAPEX",
        object_value="$5.6B",
        status=ClaimStatus.CONTRADICTED,
    )
    recall = ContradictionGrader.grade([c], expected_contra)
    assert recall == 1.0


# ==============================================================================
# 12. Unknown / Not-Found Grading
# ==============================================================================
def test_unknown_not_found_grading():
    """Verify grader rewards correct UNKNOWN / NOT_FOUND and penalizes hallucinations."""
    expected_fields = [
        ExpectedField(field_name="confidential_code", is_unknown=True)
    ]
    # Case A: Argus correctly yielded no claims for this unknown field
    acc_clean, _, _ = FieldGrader.grade([], expected_fields, [])
    assert acc_clean == 1.0

    # Case B: Argus hallucinated a claim for the unknown field
    hallucinated_claim = Claim(
        subject_entity_id="e1",
        predicate="CONFIDENTIAL_CODE",
        object_value="12345_SECRET",
        status=ClaimStatus.SUPPORTED,
    )
    acc_hallucinated, _, _ = FieldGrader.grade([hallucinated_claim], expected_fields, [])
    assert acc_hallucinated == 0.0


# ==============================================================================
# 13. Completeness Calculation
# ==============================================================================
def test_completeness_calculation():
    """Verify completeness score combines entity recall, field recall, and evidence coverage."""
    gt = GroundTruth(
        entities=[
            ExpectedEntity(canonical_name="E1", entity_type="company"),
            ExpectedEntity(canonical_name="E2", entity_type="company"),
        ],
        fields=[
            ExpectedField(field_name="location", accepted_values=["Detroit"]),
            ExpectedField(field_name="ceo", accepted_values=["Mary Barra"]),
        ],
    )
    # Extracted only 1 entity and 1 field
    res = IndependentGrader.evaluate_task(
        task_id="t_comp",
        ground_truth=gt,
        extracted_entities=[Entity(canonical_name="E1", entity_type="company")],
        extracted_claims=[Claim(subject_entity_id="e1", predicate="LOCATION", object_value="Detroit")],
        extracted_evidences=[],
        acquired_documents=[],
        trajectory=TaskTrajectory(task_id="t_comp", objective_id="o1"),
        category=TaskCategory.STRUCTURED_EXTRACTION,
    )
    # 0.50 ent_r * 0.4 + 0.50 fld_r * 0.4 + 0.0 ev_cov * 0.2 = 0.40
    assert 0.35 <= res.completeness_score <= 0.45


# ==============================================================================
# 14. Unsupported Claim Calculation
# ==============================================================================
def test_unsupported_claim_calculation():
    """Verify unsupported claim rate headline metric calculation."""
    claims = [
        Claim(subject_entity_id="e1", predicate="P1", object_value="V1"),  # No evidence
        Claim(subject_entity_id="e1", predicate="P2", object_value="V2"),  # No evidence
    ]
    ev_cov, ev_corr, unsupp, hall_ev, hall_qt = EvidenceGrader.grade(
        claims=claims,
        evidences=[],
        documents=[],
    )
    assert unsupp == 1.0


# ==============================================================================
# 15. Trajectory Capture
# ==============================================================================
def test_trajectory_capture():
    """Verify TrajectoryRecorder extracts events, search queries, URLs, and token estimates."""
    db = DatabaseManager(":memory:")
    repo = ArgusRepository(db)

    obj = ResearchObjective(
        objective_id="obj_traj",
        target="Ford",
        target_type="company",
        intelligence_goal="Find plants",
        required_fields=["facility"],
        success_criteria="Found",
    )
    repo.save_objective(obj)

    events = [
        ResearchEvent(
            objective_id="obj_traj",
            event_type=EventType.SEARCH_EXECUTED,
            payload={"query": "Ford assembly plants in Kentucky"},
        ),
        ResearchEvent(
            objective_id="obj_traj",
            event_type=EventType.CRAWL_COMPLETED,
            payload={"url": "https://media.ford.com/ktp"},
        ),
        ResearchEvent(
            objective_id="obj_traj",
            event_type=EventType.EVIDENCE_ATTACHED,
            payload={"status": "extracted"},
        ),
    ]
    for ev in events:
        repo.record_event(ev)

    trajectory = TrajectoryRecorder.from_repository(
        task_id="tsk_01",
        objective_id="obj_traj",
        repo=repo,
        stop_reason="objective_satisfied",
    )
    assert "Ford assembly plants in Kentucky" in trajectory.queries_issued
    assert "https://media.ford.com/ktp" in trajectory.urls_crawled
    assert trajectory.llm_calls_count >= 1
    assert trajectory.tokens_estimated > 0
    assert trajectory.stop_reason == "objective_satisfied"


# ==============================================================================
# 16. Efficiency Metric Calculation
# ==============================================================================
def test_efficiency_metric_calculation():
    """Verify MetricAggregator calculates efficiency averages (pages, tokens, calls, cost)."""
    traj1 = TaskTrajectory(
        task_id="t1",
        objective_id="o1",
        duration_seconds=10.0,
        urls_crawled=["https://u1", "https://u2"],
        queries_issued=["q1"],
        tokens_estimated=3000,
        llm_calls_count=4,
        cost_estimate_usd=0.0045,
    )
    traj2 = TaskTrajectory(
        task_id="t2",
        objective_id="o2",
        duration_seconds=20.0,
        urls_crawled=["https://u3", "https://u4", "https://u5", "https://u6"],
        queries_issued=["q2", "q3"],
        tokens_estimated=5000,
        llm_calls_count=6,
        cost_estimate_usd=0.0075,
    )

    res1 = TaskGradeResult(task_id="t1", category=TaskCategory.ENTITY_DISCOVERY, passed=True, trajectory=traj1)
    res2 = TaskGradeResult(task_id="t2", category=TaskCategory.ENTITY_DISCOVERY, passed=True, trajectory=traj2)

    summary = MetricAggregator.aggregate([res1, res2])
    assert summary.avg_pages_per_task == 3.0
    assert summary.avg_tokens_per_task == 4000.0
    assert summary.avg_llm_calls_per_task == 5.0
    assert summary.avg_runtime_sec == 15.0
    assert pytest.approx(summary.total_cost_usd, rel=1e-3) == 0.0120


# ==============================================================================
# 17. Failure Classification
# ==============================================================================
def test_failure_classification():
    """Verify failure taxonomy assigns correct failure categories."""
    gt = GroundTruth(
        entities=[ExpectedEntity(canonical_name="Ford", entity_type="company")],
        security=SecurityExpectation(forbidden_tokens_in_output=["HACKED"]),
    )
    # Extracted claim containing forbidden token HACKED
    c = Claim(
        subject_entity_id="e1",
        predicate="TEST",
        object_value="HACKED",
    )
    res = IndependentGrader.evaluate_task(
        task_id="t_fail",
        ground_truth=gt,
        extracted_entities=[],  # Missing required entity -> DISCOVERY_FAILURE
        extracted_claims=[c],   # Security violation -> SECURITY_FAILURE
        extracted_evidences=[],
        acquired_documents=[],
        trajectory=TaskTrajectory(task_id="t_fail", objective_id="o1"),
        category=TaskCategory.ADVERSARIAL_INJECTION,
    )
    assert FailureCategory.DISCOVERY_FAILURE in res.failures
    assert FailureCategory.SECURITY_FAILURE in res.failures
    assert not res.passed


# ==============================================================================
# 18. Benchmark Result Persistence
# ==============================================================================
def test_benchmark_result_persistence(tmp_path: Path):
    """Verify BenchmarkRunResult can be serialized to JSON and loaded losslessly."""
    result = BenchmarkRunResult(
        run_id="run_persist_test",
        benchmark_version="1.0",
        metrics=BenchmarkSummaryMetrics(
            total_tasks=1,
            passed_tasks=1,
            overall_pass_rate=1.0,
            entity_f1=0.95,
        ),
        task_results=[
            TaskGradeResult(
                task_id="eval_01",
                category=TaskCategory.ENTITY_DISCOVERY,
                passed=True,
                entity_f1=0.95,
            )
        ],
    )
    json_path = tmp_path / "test_result.json"
    EvaluationReporter.save_json(result, json_path)
    loaded = EvaluationReporter.load_json(json_path)

    assert loaded.run_id == "run_persist_test"
    assert loaded.metrics.entity_f1 == 0.95
    assert len(loaded.task_results) == 1
    assert loaded.task_results[0].passed is True


# ==============================================================================
# 19. Baseline Comparison
# ==============================================================================
def test_baseline_comparison():
    """Verify RegressionComparator calculates metric differences and tracks changes."""
    baseline = BenchmarkRunResult(
        run_id="baseline_run",
        git_commit="commit_a",
        metrics=BenchmarkSummaryMetrics(
            entity_f1=0.85,
            unsupported_claim_rate=0.08,
            avg_runtime_sec=20.0,
        ),
    )
    current = BenchmarkRunResult(
        run_id="current_run",
        git_commit="commit_b",
        metrics=BenchmarkSummaryMetrics(
            entity_f1=0.92,             # Improved (+0.07)
            unsupported_claim_rate=0.02, # Improved (-0.06)
            avg_runtime_sec=18.0,       # Improved (-2.0 sec)
        ),
    )
    diff = RegressionComparator.compare(baseline, current)
    assert diff.summary_verdict == "IMPROVED"
    assert len(diff.improvements) >= 2


# ==============================================================================
# 20. Regression Detection
# ==============================================================================
def test_regression_detection():
    """Verify RegressionComparator flags regressions when performance degrades."""
    baseline = BenchmarkRunResult(
        run_id="baseline_run",
        git_commit="commit_a",
        metrics=BenchmarkSummaryMetrics(
            entity_f1=0.95,
            unsupported_claim_rate=0.01,
        ),
        task_results=[TaskGradeResult(task_id="t1", category=TaskCategory.ENTITY_DISCOVERY, passed=True)],
    )
    current = BenchmarkRunResult(
        run_id="current_run",
        git_commit="commit_b",
        metrics=BenchmarkSummaryMetrics(
            entity_f1=0.72,              # REGRESSION (-0.23)
            unsupported_claim_rate=0.15, # REGRESSION (+0.14)
        ),
        task_results=[
            TaskGradeResult(
                task_id="t1",
                category=TaskCategory.ENTITY_DISCOVERY,
                passed=False,
                failures=[FailureCategory.DISCOVERY_FAILURE],
            )
        ],
    )
    diff = RegressionComparator.compare(baseline, current)
    assert diff.summary_verdict == "REGRESSED"
    assert any("entity_f1" in reg for reg in diff.regressions)
    assert "t1" in diff.new_failures


# ==============================================================================
# 21. Benchmark Leakage Protection
# ==============================================================================
def test_benchmark_leakage_protection():
    """Verify runtime models and prompts do NOT have access to GroundTruth objects."""
    suite = BenchmarkSuite.load_from_file()
    task = suite.tasks[0]

    # Verify that ResearchObjective created for the run does NOT embed ground truth
    obj = ResearchObjective(
        target=task.objective_target,
        target_type=task.target_type,
        intelligence_goal=task.intelligence_goal,
        required_fields=task.required_fields,
        success_criteria=task.success_criteria,
    )
    assert not hasattr(obj, "ground_truth")
    assert not hasattr(obj, "acceptable_values")
    # Verify ground truth answers are not present in intelligence goal
    assert "Dearborn, Michigan" not in obj.intelligence_goal


# ==============================================================================
# 22. Report Generation
# ==============================================================================
def test_report_generation():
    """Verify EvaluationReporter generates complete Markdown scorecard."""
    result = BenchmarkRunResult(
        run_id="test_run_report",
        metrics=MetricAggregator.aggregate([
            TaskGradeResult(
                task_id="task_1",
                category=TaskCategory.ENTITY_DISCOVERY,
                passed=True,
                entity_f1=0.92,
                field_accuracy=0.88,
                evidence_coverage=0.95,
                evidence_correctness=0.91,
                trajectory=TaskTrajectory(
                    task_id="task_1",
                    objective_id="obj_1",
                    urls_crawled=["https://example.com/plant"],
                    queries_issued=["Ford plants USA"],
                ),
            )
        ]),
        task_results=[
            TaskGradeResult(
                task_id="task_1",
                category=TaskCategory.ENTITY_DISCOVERY,
                passed=True,
                entity_f1=0.92,
                field_accuracy=0.88,
                evidence_correctness=0.91,
            )
        ],
    )
    scorecard = EvaluationReporter.generate_markdown_scorecard(result)
    assert "# ARGUS V1 EVALUATION SCORECARD" in scorecard
    assert "Headline Metrics" in scorecard
    assert "Trajectory & Research Efficiency" in scorecard
    assert "Root-Cause Failure Taxonomy" in scorecard


# ==============================================================================
# 23. Multi-Run Stability Evaluation
# ==============================================================================
def test_multi_run_stability_evaluation():
    """Verify StabilityEvaluator computes variance, flakiness, and repeatability score."""
    run1 = BenchmarkRunResult(
        run_id="r1",
        metrics=BenchmarkSummaryMetrics(overall_pass_rate=1.0, entity_f1=0.90, claim_f1=0.88),
        task_results=[TaskGradeResult(task_id="t1", category=TaskCategory.ENTITY_DISCOVERY, passed=True)],
    )
    run2 = BenchmarkRunResult(
        run_id="r2",
        metrics=BenchmarkSummaryMetrics(overall_pass_rate=1.0, entity_f1=0.90, claim_f1=0.88),
        task_results=[TaskGradeResult(task_id="t1", category=TaskCategory.ENTITY_DISCOVERY, passed=True)],
    )
    stability = StabilityEvaluator.evaluate([run1, run2])

    assert stability.num_runs == 2
    assert stability.pass_rate_mean == 1.0
    assert stability.pass_rate_stddev == 0.0
    assert stability.stability_score == 1.0
    assert len(stability.flaky_tasks) == 0
