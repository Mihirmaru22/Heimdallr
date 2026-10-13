"""Heimdallr V5: ONION_SPECIALIST_V1 Evaluation Models.

Defines benchmark task schema, 4-way evaluation metrics, and causal attribution types.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class OnionTaskCategory(str, Enum):
    """16 required benchmark categories for Vertical 5."""

    ONION_SERVICE_DISCOVERY = "ONION_SERVICE_DISCOVERY"
    ONION_SEARCH = "ONION_SEARCH"
    ONION_CRAWLING = "ONION_CRAWLING"
    ENTITY_DISCOVERY = "ENTITY_DISCOVERY"
    ENTITY_RESOLUTION = "ENTITY_RESOLUTION"
    TEMPORAL = "TEMPORAL"
    CONTRADICTION = "CONTRADICTION"
    MULTI_HOP = "MULTI_HOP"
    NOT_FOUND = "NOT_FOUND"
    UNKNOWN = "UNKNOWN"
    EVIDENCE_GROUNDING = "EVIDENCE_GROUNDING"
    SOURCE_QUALITY = "SOURCE_QUALITY"
    ADVERSARIAL = "ADVERSARIAL"
    ROUTING = "ROUTING"
    CROSS_SPECIALIST = "CROSS_SPECIALIST"
    SECURITY = "SECURITY"


class OnionTask(BaseModel):
    """A frozen task in the ONION_SPECIALIST_V1 benchmark suite."""

    task_id: str
    category: OnionTaskCategory
    title: str
    query: str
    target_entity: Optional[str] = None
    target_onion: Optional[str] = None
    expected_entities: List[str] = Field(default_factory=list)
    expected_claims: List[Dict[str, Any]] = Field(default_factory=list)
    required_evidence_desc: str = ""
    is_negative: bool = False
    is_temporal: bool = False
    is_multihop: bool = False
    is_contradiction: bool = False
    is_adversarial: bool = False
    expected_epistemic_status: str = "SUPPORTED"


class OnionTaskExecutionResult(BaseModel):
    """Execution output from a single configuration on an onion task."""

    task_id: str
    config_name: str
    passed: bool
    entity_precision: float
    entity_recall: float
    entity_f1: float
    claim_precision: float
    claim_recall: float
    claim_f1: float
    field_precision: float
    field_recall: float
    field_accuracy: float
    evidence_coverage: float
    evidence_correctness: float
    evidence_independence: float
    epistemic_accuracy: float
    temporal_accuracy: float
    contradiction_accuracy: float
    unsupported_claims: int
    hallucinated_evidence: int
    candidate_invoked: bool
    candidate_contribution: str
    final_epistemic_status: str
    runtime_sec: float
    searches_executed: int
    pages_crawled: int
    objective_completion: float
    information_gain: float


class FourWayOnionComparison(BaseModel):
    """Four-way counterfactual comparison for a single task."""

    task_id: str
    category: str
    argus_baseline_passed: bool
    candidate_standalone_passed: bool
    heimdallr_integrated_passed: bool
    candidate_disabled_passed: bool
    candidate_invoked: bool
    candidate_unique_contribution: str
    candidate_verified: bool
    causal_pattern: str
    attribution_class: str
