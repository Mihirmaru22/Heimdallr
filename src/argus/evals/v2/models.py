"""Heimdallr Eval V2: Domain & Task Specification Models.

Defines the architecture-aware schema for 10x harder investigations,
multi-hop chains, temporal reasoning, contradiction handling,
evidence independence, security injection resistance, and stopping decisions.
"""

from __future__ import annotations

from contextlib import contextmanager
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, PrivateAttr


class EvaluatorGroundTruthAccessError(RuntimeError):
    """Raised when research execution attempts to access evaluator ground truth during execution."""
    pass



class DifficultyTier(str, Enum):
    """Evaluation difficulty tier."""

    TIER_1_HARD = "TIER_1_HARD"  # ~25%
    TIER_2_VERY_HARD = "TIER_2_VERY_HARD"  # ~35%
    TIER_3_EXTREME = "TIER_3_EXTREME"  # ~25%
    TIER_4_ADVERSARIAL = "TIER_4_ADVERSARIAL"  # ~15%


class BenchmarkCategory(str, Enum):
    """The 25 mandatory benchmark categories of Eval V2."""

    GENERAL_ENTITY_DISCOVERY = "GENERAL_ENTITY_DISCOVERY"
    STRUCTURED_EXTRACTION = "STRUCTURED_EXTRACTION"
    DEEP_ENTITY_RESOLUTION = "DEEP_ENTITY_RESOLUTION"
    IDENTITY_INTELLIGENCE = "IDENTITY_INTELLIGENCE"
    INFRASTRUCTURE_INTELLIGENCE = "INFRASTRUCTURE_INTELLIGENCE"
    CORPORATE_REGISTRY_INTELLIGENCE = "CORPORATE_REGISTRY_INTELLIGENCE"
    LEADERSHIP_INTELLIGENCE = "LEADERSHIP_INTELLIGENCE"
    MULTI_HOP_INVESTIGATION = "MULTI_HOP_INVESTIGATION"
    TEMPORAL_INTELLIGENCE = "TEMPORAL_INTELLIGENCE"
    CONTRADICTION_RESOLUTION = "CONTRADICTION_RESOLUTION"
    MISSING_INFORMATION_NOT_FOUND = "MISSING_INFORMATION_NOT_FOUND"
    UNKNOWN_HANDLING = "UNKNOWN_HANDLING"
    NEGATIVE_INTELLIGENCE = "NEGATIVE_INTELLIGENCE"
    ADVERSARIAL_ENTITY_CONFUSION = "ADVERSARIAL_ENTITY_CONFUSION"
    CROSS_SPECIALIST_INVESTIGATION = "CROSS_SPECIALIST_INVESTIGATION"
    SPECIALIST_ROUTING = "SPECIALIST_ROUTING"
    SPECIALIST_NON_INVOCATION = "SPECIALIST_NON_INVOCATION"
    RESEARCH_STOPPING = "RESEARCH_STOPPING"
    EVIDENCE_GROUNDING = "EVIDENCE_GROUNDING"
    EPISTEMIC_CLASSIFICATION = "EPISTEMIC_CLASSIFICATION"
    LONG_HORIZON_INVESTIGATION = "LONG_HORIZON_INVESTIGATION"
    SECURITY_PROMPT_INJECTION = "SECURITY_PROMPT_INJECTION"
    SOURCE_QUALITY_AUTHORITY = "SOURCE_QUALITY_AUTHORITY"
    EFFICIENCY = "EFFICIENCY"
    REGRESSION_HISTORICAL_CAPABILITY = "REGRESSION_HISTORICAL_CAPABILITY"


class BenchmarkSplit(str, Enum):
    """Evaluation partition split."""

    DEVELOPMENT = "DEVELOPMENT"
    FROZEN_REGRESSION = "FROZEN_REGRESSION"
    HIDDEN_ADVERSARIAL = "HIDDEN_ADVERSARIAL"
    LIVE_HOLDOUT = "LIVE_HOLDOUT"


class StopReason(str, Enum):
    """Explicit taxonomy of investigation termination reasons."""

    OBJECTIVE_SATISFIED = "OBJECTIVE_SATISFIED"
    BUDGET_EXHAUSTED_WITH_ACCEPTABLE_COVERAGE = "BUDGET_EXHAUSTED_WITH_ACCEPTABLE_COVERAGE"
    BUDGET_EXHAUSTED_WITH_CRITICAL_MISSING_FIELDS = "BUDGET_EXHAUSTED_WITH_CRITICAL_MISSING_FIELDS"
    NO_INFORMATION_GAIN = "NO_INFORMATION_GAIN"
    NO_RELIABLE_PUBLIC_EVIDENCE = "NO_RELIABLE_PUBLIC_EVIDENCE"
    CONTRADICTION_REQUIRES_UNRESOLVED_RESEARCH = "CONTRADICTION_REQUIRES_UNRESOLVED_RESEARCH"
    ERROR = "ERROR"
    SECURITY_STOP = "SECURITY_STOP"


class FailureSeverity(str, Enum):
    """Graded severity for benchmark discrepancies."""

    CRITICAL = "CRITICAL"  # False merge, fabricated entity/edge, prompt injection breach
    MAJOR = "MAJOR"  # Missing critical hop, temporal misclassification, unhandled contradiction
    MINOR = "MINOR"  # Non-critical attribute omission, peripheral formatting mismatch


class SpecialistType(str, Enum):
    """Specialists available within the Heimdallr architecture."""

    IDENTITY = "identity"
    INFRASTRUCTURE = "infrastructure"
    CORPORATE = "corporate"
    NONE = "none"


class InvestigationHop(BaseModel):
    """Individual edge in a multi-hop investigation chain."""

    hop_index: int
    source_entity: str
    predicate: str
    target_entity: str
    required_evidence_snippet: str
    acceptable_alternative_snippets: list[str] = Field(default_factory=list)
    specialist_type: SpecialistType = SpecialistType.NONE
    is_critical: bool = True
    hop_metadata: dict[str, Any] = Field(default_factory=dict)


class TemporalSpec(BaseModel):
    """Temporal constraints and historical validity requirements."""

    as_of_date: str | None = None  # YYYY-MM-DD
    effective_date: str | None = None
    resignation_or_divestiture_date: str | None = None
    is_historical: bool = False
    expected_temporal_status: str = "CURRENT_ACTIVE"  # CURRENT_ACTIVE, HISTORICAL_RESIGNED, HISTORICAL_DIVESTED, AMENDED_SUPERSEDED


class ContradictionSpec(BaseModel):
    """Specification for conflicting sources and resolution policy."""

    has_contradiction: bool = True
    competing_claims: list[dict[str, Any]] = Field(default_factory=list)
    authoritative_source_url: str | None = None
    superseded_source_url: str | None = None
    resolution_type: str = "AMENDED_SUPERSEDES"  # AMENDED_SUPERSEDES, TEMPORAL_PRECEDENCE, JURISDICTION_SCOPE, PRESERVE_UNCERTAINTY
    expected_resolution_text: str = ""


class SecuritySpec(BaseModel):
    """Specification for adversarial prompt injection / untrusted payload."""

    contains_injection: bool = False
    injection_payload: str | None = None
    expected_defense_action: str = "IGNORE_PAYLOAD"  # IGNORE_PAYLOAD, SECURITY_STOP, SANITIZE
    forbidden_leak_token: str | None = None


class EvidenceIndependenceSpec(BaseModel):
    """Evidence syndication and independent corroboration constraints."""

    syndicated_cluster_id: str | None = None
    is_wire_service_copy: bool = False
    primary_source_origin: str = ""
    min_independent_sources_required: int = 1


class TaskExecutionInput(BaseModel):
    """Execution-safe task payload supplied to the system under test, containing no expected outputs."""

    task_id: str
    title: str
    query: str
    category: BenchmarkCategory
    difficulty_tier: DifficultyTier
    split: BenchmarkSplit = BenchmarkSplit.FROZEN_REGRESSION
    known_context: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


TaskExecutionDTO = TaskExecutionInput


class TaskExpectedOutput(BaseModel):
    """Ground truth expectations for an Eval V2 investigation task."""

    _execution_locked: bool = PrivateAttr(default=False)

    expected_entities: list[str] = Field(default_factory=list)
    expected_relationships: list[dict[str, Any]] = Field(default_factory=list)
    multi_hop_chain: list[InvestigationHop] = Field(default_factory=list)
    temporal_spec: TemporalSpec | None = None
    contradiction_spec: ContradictionSpec | None = None
    security_spec: SecuritySpec | None = None
    evidence_independence: EvidenceIndependenceSpec | None = None
    expected_epistemic_status: str = "SUPPORTED"  # SUPPORTED, CORROBORATED, INFERRED, UNVERIFIED, CONTRADICTED, UNKNOWN, NOT_FOUND
    expected_stop_reason: StopReason = StopReason.OBJECTIVE_SATISFIED
    required_specialists: list[SpecialistType] = Field(default_factory=list)
    prohibited_specialists: list[SpecialistType] = Field(default_factory=list)
    unacceptable_merges: list[str] = Field(default_factory=list)
    adversarial_traps: list[str] = Field(default_factory=list)

    def lock_for_execution(self) -> None:
        self._execution_locked = True

    def unlock_for_grading(self) -> None:
        self._execution_locked = False

    def __repr__(self) -> str:
        locked = False
        try:
            priv = super().__getattribute__("__pydantic_private__")
            if priv and priv.get("_execution_locked"):
                locked = True
        except (AttributeError, KeyError):
            pass
        if locked:
            return "<TaskExpectedOutput: LOCKED_FOR_EXECUTION>"
        return super().__repr__()

    def __str__(self) -> str:
        locked = False
        try:
            priv = super().__getattribute__("__pydantic_private__")
            if priv and priv.get("_execution_locked"):
                locked = True
        except (AttributeError, KeyError):
            pass
        if locked:
            return "<TaskExpectedOutput: LOCKED_FOR_EXECUTION>"
        return super().__str__()

    def __getattribute__(self, name: str) -> Any:
        locked = False
        try:
            priv = super().__getattribute__("__pydantic_private__")
            if priv and priv.get("_execution_locked"):
                locked = True
        except (AttributeError, KeyError):
            pass

        if locked:
            if name.startswith("__pydantic_") or name in (
                "_execution_locked",
                "__class__",
                "unlock_for_grading",
                "lock_for_execution",
                "__repr__",
                "__str__",
            ):
                return super().__getattribute__(name)
            raise EvaluatorGroundTruthAccessError(
                f"EvaluatorGroundTruthAccessError: Illegal access to '{name}' during research execution! "
                f"Ground truth is strictly isolated to the evaluator/grader."
            )
        return super().__getattribute__(name)


@contextmanager
def guard_ground_truth(target: Any):
    """Context manager locking EvalV2Task or TaskExpectedOutput against execution-time leakage."""
    if hasattr(target, "lock_for_execution"):
        target.lock_for_execution()
    try:
        yield
    finally:
        if hasattr(target, "unlock_for_grading"):
            target.unlock_for_grading()



class EvalV2Task(BaseModel):
    """Primary benchmark task specification in Heimdallr Eval V2."""

    _execution_locked: bool = PrivateAttr(default=False)

    task_id: str
    title: str
    query: str
    category: BenchmarkCategory
    difficulty_tier: DifficultyTier
    split: BenchmarkSplit = BenchmarkSplit.FROZEN_REGRESSION
    known_context: dict[str, Any] = Field(default_factory=dict)
    expected_output: TaskExpectedOutput
    metadata: dict[str, Any] = Field(default_factory=dict)

    def lock_for_execution(self) -> None:
        try:
            exp = super().__getattribute__("expected_output")
            if exp is not None and hasattr(exp, "lock_for_execution"):
                exp.lock_for_execution()
        except AttributeError:
            pass
        self._execution_locked = True

    def unlock_for_grading(self) -> None:
        self._execution_locked = False
        try:
            exp = super().__getattribute__("expected_output")
            if exp is not None and hasattr(exp, "unlock_for_grading"):
                exp.unlock_for_grading()
        except AttributeError:
            pass

    def to_execution_input(self) -> TaskExecutionInput:
        """Create execution-safe view with expected_output completely omitted."""
        return TaskExecutionInput(
            task_id=self.task_id,
            title=self.title,
            query=self.query,
            category=self.category,
            difficulty_tier=self.difficulty_tier,
            split=self.split,
            known_context=self.known_context.copy(),
            metadata=self.metadata.copy(),
        )

    to_execution_dto = to_execution_input

    def __repr__(self) -> str:
        locked = False
        try:
            priv = super().__getattribute__("__pydantic_private__")
            if priv and priv.get("_execution_locked"):
                locked = True
        except (AttributeError, KeyError):
            pass
        if locked:
            return f"EvalV2Task(task_id={self.task_id!r}, query={self.query!r}, expected_output=<LOCKED_FOR_EXECUTION>)"
        return super().__repr__()

    def __str__(self) -> str:
        locked = False
        try:
            priv = super().__getattribute__("__pydantic_private__")
            if priv and priv.get("_execution_locked"):
                locked = True
        except (AttributeError, KeyError):
            pass
        if locked:
            return f"EvalV2Task(task_id={self.task_id!r}, query={self.query!r}, expected_output=<LOCKED_FOR_EXECUTION>)"
        return super().__str__()

    def __getattribute__(self, name: str) -> Any:
        locked = False
        try:
            priv = super().__getattribute__("__pydantic_private__")
            if priv and priv.get("_execution_locked"):
                locked = True
        except (AttributeError, KeyError):
            pass

        if locked:
            if name == "expected_output":
                raise EvaluatorGroundTruthAccessError(
                    "EvaluatorGroundTruthAccessError: Illegal access to 'expected_output' on EvalV2Task during research execution! "
                    "Ground truth is strictly isolated to the evaluator/grader."
                )
        return super().__getattribute__(name)


class HopEvaluationResult(BaseModel):
    """Evaluation result for an individual hop in a multi-hop investigation chain."""

    hop_index: int
    discovered: bool = False
    source_matched: bool = False
    predicate_matched: bool = False
    target_matched: bool = False
    evidence_grounded: bool = False
    specialist_invoked_correctly: bool = True
    passed: bool = False
    failure_reason: str | None = None


class RoutingEvaluationResult(BaseModel):
    """Diagnostic routing performance evaluation."""

    task_id: str
    required_specialists: list[SpecialistType]
    prohibited_specialists: list[SpecialistType]
    invoked_specialists: list[SpecialistType]
    is_correct: bool = True
    unnecessary_invocations: list[SpecialistType] = Field(default_factory=list)
    missed_invocations: list[SpecialistType] = Field(default_factory=list)
    wrong_specialist_invoked: bool = False


class EvalV2TaskResult(BaseModel):
    """Comprehensive diagnostic result for a single task execution in Eval V2."""

    task_id: str
    title: str
    category: BenchmarkCategory
    difficulty_tier: DifficultyTier
    split: BenchmarkSplit
    configuration: str  # e.g. "argus_baseline", "specialist_standalone", "argus_specialist_integrated", "cumulative_milestone_3"

    passed: bool = False
    severity: FailureSeverity | None = None
    failure_mode: str | None = None

    # Research Quality Metrics
    entity_precision: float = 0.0
    entity_recall: float = 0.0
    entity_f1: float = 0.0
    relationship_precision: float = 0.0
    relationship_recall: float = 0.0
    relationship_f1: float = 0.0
    field_accuracy: float = 0.0

    # Multi-hop & Chain Metrics
    chain_completion_rate: float = 0.0
    hop_results: list[HopEvaluationResult] = Field(default_factory=list)
    broken_chain_detected: bool = False

    # Evidence & Independence
    evidence_coverage: float = 0.0
    evidence_correctness: float = 0.0
    evidence_completeness: float = 0.0
    evidence_independence_score: float = 1.0
    hallucinated_evidence_detected: bool = False

    # Epistemics & Contradiction
    epistemic_accuracy: float = 0.0
    epistemic_assigned_status: str = "UNKNOWN"
    contradiction_detected: bool = True
    contradiction_resolved_correctly: bool = True

    # Temporal
    temporal_accuracy: float = 0.0
    effective_date_accurate: bool = True
    historical_status_accurate: bool = True

    # Entity Safety
    false_positive_merges: int = 0
    false_negative_misses: int = 0
    identity_collision_detected: bool = False

    # Routing
    routing_result: RoutingEvaluationResult | None = None

    # Stopping Behavior
    assigned_stop_reason: StopReason = StopReason.OBJECTIVE_SATISFIED
    expected_stop_reason: StopReason = StopReason.OBJECTIVE_SATISFIED
    stopping_correct: bool = True
    premature_stopping: bool = False

    # Security
    security_violation_detected: bool = False
    prompt_injection_neutralized: bool = True

    # Investigation Efficiency
    searches_count: int = 0
    pages_extracted: int = 0
    llm_calls_count: int = 0
    tokens_count: int = 0
    cost_usd: float = 0.0
    runtime_sec: float = 0.0

    discovered_entities: list[str] = Field(default_factory=list)
    discovered_relationships: list[dict[str, Any]] = Field(default_factory=list)
    extracted_evidence: list[dict[str, Any]] = Field(default_factory=list)
