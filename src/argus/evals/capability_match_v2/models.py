"""Heimdallr V3.1: CAPABILITY_MATCH_V2 Data Models and Contracts.

Defines schemas for:
- 11 benchmark categories across ~125 tasks
- Benchmark splits: dev, frozen_regression, hidden_adversarial
- Task definition with strict evaluator-only ground truth isolation
- Per-task evaluation results with precision, recall, F1, Capability Tax, and Regret
- Aggregate benchmark metrics matching Section 19, 20, 21, and 29
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field

from argus.capability_registry.models import HealthStatus
from argus.investigation.question import QuestionType


class MatchCategoryV2(str, Enum):
    """The 11 categories of CAPABILITY_MATCH_V2."""

    OBVIOUS_SINGLE = "OBVIOUS_SINGLE"
    AMBIGUOUS_SINGLE = "AMBIGUOUS_SINGLE"
    CAPABILITY_OVERLAP = "CAPABILITY_OVERLAP"
    MULTI_CAPABILITY = "MULTI_CAPABILITY"
    MINIMUM_SET_CHALLENGE = "MINIMUM_SET_CHALLENGE"
    FALSE_SPECIALIST_TRAP = "FALSE_SPECIALIST_TRAP"
    NEGATIVE_NON_APPLICABLE = "NEGATIVE_NON_APPLICABLE"
    TEMPORAL_JURISDICTIONAL = "TEMPORAL_JURISDICTIONAL"
    CAPABILITY_HEALTH = "CAPABILITY_HEALTH"
    MULTIPLE_IMPLEMENTATIONS = "MULTIPLE_IMPLEMENTATIONS"
    CROSS_SPECIALIST_CHAIN = "CROSS_SPECIALIST_CHAIN"


class BenchmarkSplit(str, Enum):
    """Evaluation splits for CAPABILITY_MATCH_V2."""

    DEV = "dev"
    FROZEN_REGRESSION = "frozen_regression"
    HIDDEN_ADVERSARIAL = "hidden_adversarial"


class RegretType(str, Enum):
    """Classification of routing regret penalties."""

    NONE = "NONE"
    UNNECESSARY = "UNNECESSARY"
    WRONG = "WRONG"
    UNAVAILABLE = "UNAVAILABLE"
    LOWER_RANKED_VALID_ALTERNATIVE = "LOWER_RANKED_VALID_ALTERNATIVE"
    MISSED_REQUIRED = "MISSED_REQUIRED"


class FailureClassification(str, Enum):
    """Root cause classification for benchmark failures."""

    NONE = "NONE"
    LEXICAL_ROUTING_FAILURE = "LEXICAL_ROUTING_FAILURE"
    SEMANTIC_ROUTING_FAILURE = "SEMANTIC_ROUTING_FAILURE"
    REQUIREMENT_EXTRACTION_FAILURE = "REQUIREMENT_EXTRACTION_FAILURE"
    CAPABILITY_MODEL_FAILURE = "CAPABILITY_MODEL_FAILURE"
    RANKING_FAILURE = "RANKING_FAILURE"
    HEALTH_STATE_FAILURE = "HEALTH_STATE_FAILURE"
    IMPLEMENTATION_SELECTION_FAILURE = "IMPLEMENTATION_SELECTION_FAILURE"
    BENCHMARK_FAILURE = "BENCHMARK_FAILURE"


class CapabilityMatchTaskV2(BaseModel):
    """A benchmark task in CAPABILITY_MATCH_V2."""

    task_id: str
    category: MatchCategoryV2
    split: BenchmarkSplit = BenchmarkSplit.FROZEN_REGRESSION
    question_text: str
    question_type: QuestionType = QuestionType.ENTITY_DISCOVERY
    required_evidence: List[str] = Field(default_factory=list)
    related_entities: List[str] = Field(default_factory=list)
    temporal_context: Optional[Dict[str, Any]] = None
    jurisdiction: str = "GLOBAL"
    specialist_requirements: List[str] = Field(default_factory=list)

    # Evaluator-Only Ground Truth (Quarantined from runtime matcher and planner)
    required_capabilities: List[str] = Field(default_factory=list)
    forbidden_capabilities: List[str] = Field(default_factory=list)
    minimum_sufficient_set: List[str] = Field(default_factory=list)
    acceptable_alternative_sets: List[List[str]] = Field(default_factory=list)
    expected_implementation_id: Optional[str] = None
    simulate_health_states: Dict[str, HealthStatus] = Field(default_factory=dict)
    chain_steps: Optional[List[Dict[str, Any]]] = None
    notes: str = ""

    def get_public_view(self) -> Dict[str, Any]:
        """Return public task dictionary without evaluator ground truth."""
        return {
            "task_id": self.task_id,
            "category": self.category.value,
            "split": self.split.value,
            "question_text": self.question_text,
            "question_type": self.question_type.value if hasattr(self.question_type, "value") else str(self.question_type),
            "required_evidence": self.required_evidence,
            "related_entities": self.related_entities,
            "temporal_context": self.temporal_context,
            "jurisdiction": self.jurisdiction,
            "specialist_requirements": self.specialist_requirements,
        }


class TaskEvaluationResult(BaseModel):
    """Individual task evaluation result in CAPABILITY_MATCH_V2."""

    task_id: str
    category: MatchCategoryV2
    split: BenchmarkSplit
    passed_minimum_set: bool
    passed_recall: bool
    precision: float
    recall: float
    f1: float
    capability_tax: int
    unnecessary_capabilities: int
    missed_capabilities: int
    forbidden_invoked: bool
    selected_capabilities: List[str]
    selected_implementations: List[str]
    expected_minimum_set: List[str]
    implementation_selection_passed: bool
    regret_type: RegretType
    failure_classification: FailureClassification
    runtime_sec: float
    rationale: str


class CapabilityMatchV2Summary(BaseModel):
    """Comprehensive benchmark aggregate metrics for CAPABILITY_MATCH_V2."""

    benchmark: str = "CAPABILITY_MATCH_V2"
    version: str = "2.0"
    total_tasks: int
    passed_minimum_set_tasks: int
    passed_recall_tasks: int

    # Core Capability Selection Metrics
    capability_precision: float
    capability_recall: float
    capability_f1: float
    minimum_capability_set_accuracy: float
    unnecessary_invocation_rate: float
    missed_capability_rate: float
    forbidden_invocation_rate: float

    # Capability Tax Metrics
    capability_tax_mean: float
    capability_tax_median: float
    capability_tax_p95: float
    capability_tax_max: int

    # Implementation Selection
    implementation_selection_accuracy: float

    # Ranking Metrics
    top_1_accuracy: float
    top_3_recall: float
    mean_reciprocal_rank: float
    ranking_stability: float

    # Multi-Capability Metrics
    exact_set_accuracy: float
    partial_set_accuracy: float
    cross_capability_completion: float

    # Health Handling Metrics
    unavailable_capability_avoidance: float
    degraded_capability_handling: float
    quarantined_capability_avoidance: float
    fallback_accuracy: float

    # Category Breakdown
    category_metrics: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    split_metrics: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

    # Audit & Decision
    leakage_audit: str = "PASS"
    decision: str = "GO"
