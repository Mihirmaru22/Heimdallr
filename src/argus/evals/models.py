"""Domain models and schemas for the Argus Evaluation Harness.

This module defines independent data structures for:
- Benchmark evaluation tasks and ground truth
- Task trajectories and execution audit events
- Deterministic grading results and 16-class failure taxonomy
- Benchmark run reports, reproducibility metadata, and regression comparisons
"""

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from argus.domain.claim import ClaimStatus


class FailureCategory(str, Enum):
    """The 16-class root-cause failure taxonomy for Argus research."""

    SEARCH_FAILURE = "SEARCH_FAILURE"
    DISCOVERY_FAILURE = "DISCOVERY_FAILURE"
    ACQUISITION_FAILURE = "ACQUISITION_FAILURE"
    DOCUMENT_EXTRACTION_FAILURE = "DOCUMENT_EXTRACTION_FAILURE"
    CONTEXT_SELECTION_FAILURE = "CONTEXT_SELECTION_FAILURE"
    ENTITY_RESOLUTION_FAILURE = "ENTITY_RESOLUTION_FAILURE"
    CLAIM_EXTRACTION_FAILURE = "CLAIM_EXTRACTION_FAILURE"
    EVIDENCE_ALIGNMENT_FAILURE = "EVIDENCE_ALIGNMENT_FAILURE"
    VERIFICATION_FAILURE = "VERIFICATION_FAILURE"
    CONTRADICTION_FAILURE = "CONTRADICTION_FAILURE"
    TEMPORAL_FAILURE = "TEMPORAL_FAILURE"
    COMPLETENESS_FAILURE = "COMPLETENESS_FAILURE"
    STOPPING_FAILURE = "STOPPING_FAILURE"
    SYNTHESIS_FAILURE = "SYNTHESIS_FAILURE"
    SECURITY_FAILURE = "SECURITY_FAILURE"
    INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"


class TaskCategory(str, Enum):
    """Benchmark task categories for research evaluation."""

    ENTITY_DISCOVERY = "entity_discovery"
    STRUCTURED_EXTRACTION = "structured_extraction"
    PLANT_FACILITY_DISCOVERY = "plant_facility_discovery"
    LEADERSHIP_RESEARCH = "leadership_research"
    MULTI_HOP = "multi_hop"
    TEMPORAL = "temporal"
    CONTRADICTION = "contradiction"
    MISSING_INFORMATION = "missing_information"
    ADVERSARIAL_INJECTION = "adversarial_injection"


class DifficultyLevel(str, Enum):
    """Evaluation task difficulty tier."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    ADVERSARIAL = "adversarial"


# ---------------------------------------------------------------------------
# Ground Truth Models (Isolated outside Argus runtime)
# ---------------------------------------------------------------------------


class ExpectedEntity(BaseModel):
    """Ground-truth expected entity definition."""

    canonical_name: str
    entity_type: str
    accepted_aliases: list[str] = Field(default_factory=list)
    unacceptable_merges: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)


class ExpectedField(BaseModel):
    """Ground-truth expected structured field value."""

    field_name: str
    entity_name: str | None = None
    accepted_values: list[str] = Field(default_factory=list)
    is_unknown: bool = False
    valid_from: str | None = None
    valid_to: str | None = None


class ExpectedClaim(BaseModel):
    """Ground-truth expected factual claim."""

    subject_name: str
    predicate: str
    object_value: str
    accepted_object_values: list[str] = Field(default_factory=list)
    expected_status: ClaimStatus = ClaimStatus.SUPPORTED
    required_evidence_keywords: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    is_inferred: bool = False


class ExpectedContradiction(BaseModel):
    """Ground-truth specification of contradictory sources."""

    field_or_predicate: str
    conflicting_values: list[str]
    resolved_value: str | None = None
    resolution_rationale: str | None = None


class SecurityExpectation(BaseModel):
    """Security boundaries and expected adversarial defense behavior."""

    expected_injection_resistant: bool = True
    forbidden_tokens_in_output: list[str] = Field(default_factory=list)
    disallowed_urls: list[str] = Field(default_factory=list)
    disallowed_actions: list[str] = Field(default_factory=list)


class GroundTruth(BaseModel):
    """Authoritative ground truth for an evaluation task."""

    version: str = "1.0"
    last_verified_at: str | None = None
    entities: list[ExpectedEntity] = Field(default_factory=list)
    fields: list[ExpectedField] = Field(default_factory=list)
    claims: list[ExpectedClaim] = Field(default_factory=list)
    contradictions: list[ExpectedContradiction] = Field(default_factory=list)
    expected_unknowns: list[str] = Field(default_factory=list)
    security: SecurityExpectation = Field(default_factory=SecurityExpectation)


class EvaluationTask(BaseModel):
    """A single benchmark research task with ground truth."""

    task_id: str
    version: str = "1.0"
    category: TaskCategory
    difficulty: DifficultyLevel = DifficultyLevel.MEDIUM
    title: str
    objective_target: str
    target_type: str = "industry"
    intelligence_goal: str
    required_fields: list[str]
    success_criteria: str
    max_tasks: int = 5
    max_depth: int = 2
    tags: list[str] = Field(default_factory=list)
    is_core: bool = False
    ground_truth: GroundTruth


# ---------------------------------------------------------------------------
# Trajectory Models
# ---------------------------------------------------------------------------


class TrajectoryEvent(BaseModel):
    """A discrete recorded action along the execution path."""

    event_id: str = Field(default_factory=lambda: f"tev_{uuid.uuid4().hex[:8]}")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    event_type: str
    stage: str | None = None
    task_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class TaskTrajectory(BaseModel):
    """Full execution trajectory capturing the complete reasoning and tool path."""

    task_id: str
    objective_id: str
    start_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    end_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    duration_seconds: float = 0.0
    events: list[TrajectoryEvent] = Field(default_factory=list)
    queries_issued: list[str] = Field(default_factory=list)
    urls_crawled: list[str] = Field(default_factory=list)
    documents_acquired_count: int = 0
    claims_extracted_count: int = 0
    claims_verified_count: int = 0
    llm_calls_count: int = 0
    tokens_estimated: int = 0
    stop_reason: str = ""
    premature_stop: bool = False
    wasteful_continuation: bool = False
    security_violations: list[str] = Field(default_factory=list)
    cost_estimate_usd: float = 0.0


# ---------------------------------------------------------------------------
# Grading & Scorecard Models
# ---------------------------------------------------------------------------


class TaskGradeResult(BaseModel):
    """Independent grading assessment of a single evaluation task run."""

    task_id: str
    category: TaskCategory
    passed: bool = False

    # Entity metrics
    entity_precision: float = 0.0
    entity_recall: float = 0.0
    entity_f1: float = 0.0
    entity_resolution_accuracy: float = 1.0
    false_merge_count: int = 0
    false_split_count: int = 0

    # Field metrics
    field_accuracy: float = 0.0
    field_precision: float = 0.0
    field_recall: float = 0.0

    # Claim metrics
    claim_precision: float = 0.0
    claim_recall: float = 0.0
    claim_f1: float = 0.0

    # Evidence & grounding metrics
    evidence_coverage: float = 0.0
    evidence_correctness: float = 0.0
    unsupported_claim_rate: float = 0.0
    hallucinated_evidence_rate: float = 0.0
    hallucinated_quote_rate: float = 0.0

    # Epistemic metrics
    epistemic_accuracy: float = 0.0
    status_escalation_errors: int = 0

    # Contradiction & uncertainty
    contradiction_detection_recall: float = 1.0
    unknown_accuracy: float = 1.0

    # Completeness & multi-hop
    completeness_score: float = 0.0
    multi_hop_completion: bool = True

    # Security
    security_violation_count: int = 0

    # Diagnostics
    failures: list[FailureCategory] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)
    trajectory: TaskTrajectory | None = None


class CategoryMetricSummary(BaseModel):
    """Aggregated score for a specific benchmark category."""

    category: TaskCategory
    task_count: int
    passed_count: int
    pass_rate: float
    avg_entity_f1: float
    avg_field_accuracy: float
    avg_claim_f1: float
    avg_evidence_correctness: float
    avg_unsupported_claim_rate: float
    avg_duration_sec: float


class CompositeScoreWeights(BaseModel):
    """Transparent weights for composite score calculation."""

    research_quality: float = 0.30
    evidence_quality: float = 0.25
    safety: float = 0.20
    completeness: float = 0.15
    efficiency: float = 0.10


class CompositeScoreBreakdown(BaseModel):
    """Separately visible sub-scores powering the composite metric."""

    research_quality: float
    evidence_quality: float
    safety: float
    completeness: float
    efficiency: float
    composite_score: float
    weights: CompositeScoreWeights = Field(default_factory=CompositeScoreWeights)


class BenchmarkSummaryMetrics(BaseModel):
    """Aggregate metric results across an entire evaluation run."""

    total_tasks: int = 0
    passed_tasks: int = 0
    overall_pass_rate: float = 0.0

    # Headline metrics
    entity_precision: float = 0.0
    entity_recall: float = 0.0
    entity_f1: float = 0.0
    entity_resolution_accuracy: float = 0.0

    field_accuracy: float = 0.0
    claim_precision: float = 0.0
    claim_recall: float = 0.0
    claim_f1: float = 0.0

    evidence_coverage: float = 0.0
    evidence_correctness: float = 0.0
    unsupported_claim_rate: float = 0.0
    hallucinated_evidence_rate: float = 0.0
    hallucinated_quote_rate: float = 0.0

    epistemic_accuracy: float = 0.0
    status_escalation_error_count: int = 0

    contradiction_detection_recall: float = 0.0
    unknown_accuracy: float = 0.0
    completeness_score: float = 0.0

    # Security
    total_security_violations: int = 0
    prompt_injection_success_rate: float = 0.0
    ssrf_violation_rate: float = 0.0
    security_policy_violation_rate: float = 0.0

    # Efficiency
    avg_pages_per_task: float = 0.0
    avg_searches_per_task: float = 0.0
    avg_queries_per_task: float = 0.0
    avg_claims_per_page: float = 0.0
    avg_tokens_per_task: float = 0.0
    avg_llm_calls_per_task: float = 0.0
    avg_runtime_sec: float = 0.0
    total_cost_usd: float = 0.0
    premature_stop_rate: float = 0.0
    wasteful_continuation_rate: float = 0.0

    # Composite
    composite: CompositeScoreBreakdown | None = None

    # Breakdowns
    category_summaries: dict[str, CategoryMetricSummary] = Field(default_factory=dict)
    failure_taxonomy_counts: dict[str, int] = Field(default_factory=dict)


class BenchmarkRunResult(BaseModel):
    """Complete, self-contained, reproducible evaluation run report."""

    run_id: str = Field(default_factory=lambda: f"run_{uuid.uuid4().hex[:8]}")
    benchmark_version: str = "1.0"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    git_commit: str = "unknown"
    python_version: str = "3.12"
    model_name: str = "argus_v1"
    evaluation_mode: str = "frozen"  # "frozen" or "live"
    is_core_subset: bool = False
    configuration: dict[str, Any] = Field(default_factory=dict)
    metrics: BenchmarkSummaryMetrics
    task_results: list[TaskGradeResult] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Multi-Run Stability & Regression Models
# ---------------------------------------------------------------------------


class RunStabilityResult(BaseModel):
    """Repeatability and stability assessment across multiple identical runs."""

    num_runs: int
    task_ids: list[str]
    pass_rate_mean: float
    pass_rate_stddev: float
    entity_f1_variance: float
    claim_f1_variance: float
    unsupported_claim_rate_variance: float
    flaky_tasks: list[str] = Field(default_factory=list)
    stability_score: float = 1.0  # 1.0 = 100% deterministic, 0.0 = total chaos


class RegressionDiff(BaseModel):
    """Comparative diff between two evaluation runs (Baseline vs Current)."""

    baseline_run_id: str
    current_run_id: str
    baseline_commit: str
    current_commit: str
    improvements: list[str] = Field(default_factory=list)
    regressions: list[str] = Field(default_factory=list)
    unchanged: list[str] = Field(default_factory=list)
    new_failures: dict[str, list[str]] = Field(default_factory=dict)
    resolved_failures: dict[str, list[str]] = Field(default_factory=dict)
    metric_deltas: dict[str, float] = Field(default_factory=dict)
    cost_delta_pct: float = 0.0
    latency_delta_pct: float = 0.0
    summary_verdict: str = "NEUTRAL"
