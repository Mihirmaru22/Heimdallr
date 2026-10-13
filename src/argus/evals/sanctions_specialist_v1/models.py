"""Heimdallr V3.2.1: SANCTIONS_SPECIALIST_V1 Models.

Defines the 30 evaluation categories, task schemas, and four-way benchmark result models
for the independent sanctions, PEP, and beneficial ownership specialist holdout.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SanctionsCategory(str, Enum):
    SANCTIONS_SCREENING = "SANCTIONS_SCREENING"
    SANCTIONED_ENTITY_IDENTIFICATION = "SANCTIONED_ENTITY_IDENTIFICATION"
    ALIAS_RESOLUTION = "ALIAS_RESOLUTION"
    BENEFICIAL_OWNERSHIP = "BENEFICIAL_OWNERSHIP"
    OWNERSHIP_CHAIN_TRAVERSAL = "OWNERSHIP_CHAIN_TRAVERSAL"
    PEP_IDENTIFICATION = "PEP_IDENTIFICATION"
    OFFSHORE_ENTITIES = "OFFSHORE_ENTITIES"
    JURISDICTION_CONFLICTS = "JURISDICTION_CONFLICTS"
    HISTORICAL_SANCTIONS = "HISTORICAL_SANCTIONS"
    DELISTING_STATUS_CHANGES = "DELISTING_STATUS_CHANGES"
    TEMPORAL_REASONING = "TEMPORAL_REASONING"
    NEGATIVE_CASES = "NEGATIVE_CASES"
    AMBIGUOUS_NAMES = "AMBIGUOUS_NAMES"
    COMMON_NAME_COLLISIONS = "COMMON_NAME_COLLISIONS"
    CORPORATE_TO_SANCTIONS = "CORPORATE_TO_SANCTIONS"
    SANCTIONS_TO_CORPORATE = "SANCTIONS_TO_CORPORATE"
    CORP_TO_SANCTIONS_TO_IDENTITY = "CORP_TO_SANCTIONS_TO_IDENTITY"
    CORP_TO_SANCTIONS_TO_INFRA = "CORP_TO_SANCTIONS_TO_INFRA"
    MULTI_HOP_OWNERSHIP = "MULTI_HOP_OWNERSHIP"
    CONTRADICTION = "CONTRADICTION"
    MISSING_INFORMATION = "MISSING_INFORMATION"
    NOT_FOUND = "NOT_FOUND"
    UNKNOWN = "UNKNOWN"
    ADVERSARIAL_SOURCE_MATERIAL = "ADVERSARIAL_SOURCE_MATERIAL"
    SYNDICATED_EVIDENCE = "SYNDICATED_EVIDENCE"
    STALE_EVIDENCE = "STALE_EVIDENCE"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    CROSS_JURISDICTION_RESOLUTION = "CROSS_JURISDICTION_RESOLUTION"
    BENEFICIAL_OWNER_CHAIN_DEPTH = "BENEFICIAL_OWNER_CHAIN_DEPTH"
    FALSE_POSITIVE_SANCTIONS_MATCHING = "FALSE_POSITIVE_SANCTIONS_MATCHING"


class SanctionsTask(BaseModel):
    task_id: str
    category: SanctionsCategory
    title: str
    query: str
    target_entity: str
    expected_entities: List[str] = Field(default_factory=list)
    expected_claims: List[Dict[str, str]] = Field(default_factory=list)
    expected_epistemic_status: str = "SUPPORTED"
    is_negative: bool = False
    is_multihop: bool = False
    is_temporal: bool = False
    is_ambiguous: bool = False
    required_evidence_desc: str = ""
    adversarial_traps: List[str] = Field(default_factory=list)


class TaskExecutionResult(BaseModel):
    task_id: str
    config_name: str
    passed: bool
    entity_precision: float
    entity_recall: float
    entity_f1: float
    claim_precision: float
    claim_recall: float
    claim_f1: float
    evidence_coverage: float
    evidence_correctness: float
    evidence_independence: float
    epistemic_accuracy: float
    temporal_accuracy: float
    completeness: float
    unsupported_claims: int
    hallucinated_evidence: int
    candidate_invoked: bool
    candidate_contribution: str
    final_epistemic_status: str
    runtime_sec: float
    research_actions: int


class FourWayTaskComparison(BaseModel):
    task_id: str
    category: str
    argus_baseline_passed: bool
    opensanctions_standalone_passed: bool
    heimdallr_integrated_passed: bool
    candidate_disabled_passed: bool
    candidate_invoked: bool
    candidate_unique_contribution: str
    candidate_verified: bool
    causal_pattern: str  # e.g., "BASELINE_FAIL_INTEGRATED_PASS_DISABLED_FAIL"
    attribution_class: str  # FIXED_BY_CANDIDATE, COEXISTENCE_WIN, CANDIDATE_INVOLVED_NO_EFFECT, UNCHANGED
