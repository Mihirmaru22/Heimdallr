"""Heimdallr V3.2: Specialist Competition & Recruitment Models.

Defines the candidate contract, lifecycle states, licensing classifications,
competition decisions, and normalized observation boundaries.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CandidateLifecycleState(str, Enum):
    """Lifecycle stages through which an open-source candidate must pass."""

    DISCOVERED = "DISCOVERED"
    AUDITED = "AUDITED"
    LICENSE_CHECKED = "LICENSE_CHECKED"
    CAPABILITY_MAPPED = "CAPABILITY_MAPPED"
    ISOLATED = "ISOLATED"
    BENCHMARKED = "BENCHMARKED"
    COMPARED = "COMPARED"
    DECISION = "DECISION"


class LicenseStatus(str, Enum):
    """Formal licensing compatibility tiers."""

    APPROVED = "APPROVED"                                # Permissive: MIT, Apache-2.0, BSD, CC0
    APPROVED_WITH_ATTRIBUTION = "APPROVED_WITH_ATTRIBUTION"  # CC-BY, ODbL with attribution
    RESTRICTED = "RESTRICTED"                            # Weak copyleft / non-commercial clauses
    INCOMPATIBLE = "INCOMPATIBLE"                        # AGPL, proprietary, commercial lock-in
    UNKNOWN = "UNKNOWN"                                  # Missing or undeclared license


class CompetitionDecisionType(str, Enum):
    """Formal outcome decisions produced by the Competition Engine."""

    RECRUIT_NEW_CAPABILITY = "RECRUIT_NEW_CAPABILITY"    # Candidate creates a genuinely new verified capability
    RECRUIT_IMPLEMENTATION = "RECRUIT_IMPLEMENTATION"    # Candidate joins existing capability as alternative implementation
    REPLACE_INCUMBENT = "REPLACE_INCUMBENT"              # Candidate strictly supersedes the incumbent across benchmark criteria
    COEXIST = "COEXIST"                                  # Candidate and incumbent excel on distinct question subsets
    REJECT = "REJECT"                                    # Candidate fails benchmark, licensing, or security gates
    QUARANTINE = "QUARANTINE"                            # Candidate exhibits security regressions or fatal operational flaws


class CandidateImplementation(BaseModel):
    """Formal contract for an open-source capability candidate entering Heimdallr."""

    candidate_id: str
    name: str
    version: str
    repository: str
    license: str
    license_status: LicenseStatus = LicenseStatus.UNKNOWN
    claimed_capabilities: List[str] = Field(default_factory=list)
    mapped_capabilities: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    runtime_requirements: Dict[str, Any] = Field(default_factory=dict)
    security_profile: Dict[str, Any] = Field(default_factory=dict)
    operational_constraints: Dict[str, Any] = Field(default_factory=dict)
    benchmark_profile: Optional[Dict[str, Any]] = None
    provenance: str = ""
    lifecycle_state: CandidateLifecycleState = CandidateLifecycleState.DISCOVERED


class NormalizedObservation(BaseModel):
    """Sanitized observation emitted by candidate adapters behind the isolation boundary."""

    observation_id: str
    source_candidate_id: str
    entity_name: str
    evidence_type: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = 1.0
    epistemic_status: str = "OBSERVED"
    is_authoritative: bool = False  # NEVER authoritative until verified by Heimdallr


class CompetitionDecision(BaseModel):
    """Formal, auditable decision produced by the Competition Engine."""

    candidate_id: str
    capability_id: str
    incumbent_id: Optional[str] = None
    decision: CompetitionDecisionType
    primary_reason: str
    marginal_value: Dict[str, float] = Field(default_factory=dict)
    regressions: List[str] = Field(default_factory=list)
    license_result: LicenseStatus = LicenseStatus.UNKNOWN
    security_result: str = "PASS"
    operational_result: str = "PASS"
    benchmark_version: str = "SPECIALIST_COMPETITION_V1"
