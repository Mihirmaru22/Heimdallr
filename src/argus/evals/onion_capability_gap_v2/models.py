"""Heimdallr V5.2: ONION_CAPABILITY_GAP_V2 Domain and Benchmark Models."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class GapV2TaskGroup(str, Enum):
    """The 6 controlled benchmark groups for ONION_CAPABILITY_GAP_V2."""

    GROUP_A_DISCOVERY = "GROUP_A_DISCOVERY"          # 20 tasks: Source discovery from search indexes, seeds, decoys
    GROUP_B_ACQUISITION = "GROUP_B_ACQUISITION"      # 20 tasks: Content retrieval from known .onion URLs
    GROUP_C_CRAWLING = "GROUP_C_CRAWLING"            # 15 tasks: Recursive link traversal, cycles, depth, budgets
    GROUP_D_HANDED_REASONING = "GROUP_D_HANDED_REASONING"  # 15 tasks: Downstream reasoning with handed documents
    GROUP_E_INVESTIGATION = "GROUP_E_INVESTIGATION"  # 15 tasks: End-to-end multi-specialist investigations
    GROUP_F_NEGATIVE_EPISTEMIC = "GROUP_F_NEGATIVE_EPISTEMIC"  # 15 tasks: Calibrated negative, budget, epistemic states


class GapV2Task(BaseModel):
    """A single independently graded task in ONION_CAPABILITY_GAP_V2."""

    task_id: str
    group: GapV2TaskGroup
    title: str
    query: str
    target_entity: Optional[str] = None
    target_onion: Optional[str] = None
    seed_urls: List[str] = Field(default_factory=list)
    expected_sources: List[str] = Field(default_factory=list)
    expected_entities: List[str] = Field(default_factory=list)
    expected_claims: List[Dict[str, Any]] = Field(default_factory=list)
    required_evidence_desc: str = ""
    handed_document_text: Optional[str] = None  # Normalized document provided for Configuration B
    handed_document_metadata: Dict[str, Any] = Field(default_factory=dict)
    required_specialists: List[str] = Field(default_factory=list)
    is_negative: bool = False
    is_multihop: bool = False
    is_decoy: bool = False
    is_malformed: bool = False
    is_redirect: bool = False
    is_cycle: bool = False
    is_timeout: bool = False
    is_large_document: bool = False
    expected_epistemic_status: str = "SUPPORTED"  # SUPPORTED, NOT_FOUND, UNKNOWN, CONTRADICTED, UNVERIFIED


class GapV2TaskExecutionResult(BaseModel):
    """Evaluation result for a single configuration executing a GapV2Task."""

    task_id: str
    config_name: str
    group: str
    passed: bool

    # Discovery metrics
    discovery_precision: float = 1.0
    discovery_recall: float = 1.0
    discovery_f1: float = 1.0
    duplicate_discovery_count: int = 0
    irrelevant_sources_retrieved: int = 0

    # Acquisition metrics
    acquisition_success: bool = True
    failure_classification_correct: bool = True
    retry_success: bool = True
    timeout_handled: bool = True
    provenance_preserved: bool = True

    # Crawling metrics
    crawl_page_recall: float = 1.0
    crawl_irrelevant_ratio: float = 0.0
    crawl_duplicate_rate: float = 0.0
    crawl_budget_compliant: bool = True
    crawl_stopped_correctly: bool = True

    # Reasoning metrics
    entity_precision: float = 1.0
    entity_recall: float = 1.0
    entity_f1: float = 1.0
    claim_precision: float = 1.0
    claim_recall: float = 1.0
    claim_f1: float = 1.0
    field_accuracy: float = 1.0
    evidence_correctness: float = 1.0
    evidence_coverage: float = 1.0
    unsupported_claims_count: int = 0
    hallucinated_evidence_count: int = 0
    contradiction_detected: bool = True
    temporal_correctness: bool = True
    epistemic_accuracy: float = 1.0

    # Investigation & System metrics
    objective_completion: float = 1.0
    critical_fields_complete: bool = True
    specialist_invoked: bool = False
    specialist_consumed: bool = False
    cross_specialist_correct: bool = True
    unnecessary_specialist_invocations: int = 0
    runtime_sec: float = 0.0
    cost_usd: float = 0.0
    final_epistemic_status: str = "SUPPORTED"
    error_message: Optional[str] = None


class FiveWayComparisonResult(BaseModel):
    """Comparative outcome across all 5 configurations for a single task."""

    task_id: str
    group: str
    config_a_passed: bool  # Argus from Scratch
    config_b_passed: bool  # Argus with Handed Documents
    config_c_passed: bool  # Proposed Onion Specialist Standalone
    config_d_passed: bool  # Heimdallr with Onion Capability Integrated
    config_e_passed: bool  # Heimdallr without Onion (Candidate Disabled)
    causal_attribution: str  # ACQUISITION_ATTRIBUTABLE, CRAWLING_ATTRIBUTABLE, REASONING_UNCHANGED, SHARED_COMPETENCE, UNRESOLVED
    attribution_justification: str
