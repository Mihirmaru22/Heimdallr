"""Clean-Room Identity Specialist Contract.

Defines the formal capability contract for identity discovery, candidate account
harvesting, and evidence provenance under Heimdallr.

Crucial Architectural Invariant:
The specialist discovers candidate accounts and provides raw observations and provenance.
It NEVER asserts verified identity equivalence ("these accounts belong to the same person").
All identity resolution and epistemic state assertions are reserved strictly for the
Argus Verification Layer.
"""

from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field

from argus.specialists.outcome import SpecialistOutcome


class IdentifierType(str, Enum):
    """Explicitly supported input identifier types for candidate probing."""

    USERNAME = "username"
    EMAIL = "email"
    PHONE = "phone"
    DOMAIN_HANDLE = "domain_handle"


class EpistemicCandidateStatus(str, Enum):
    """Candidate-level epistemic statuses emitted by discovery probes.
    
    The specialist NEVER emits 'VERIFIED_SAME_PERSON'. It only emits candidate states.
    """

    UNVERIFIED_CANDIDATE = "UNVERIFIED_CANDIDATE"
    POTENTIAL_MATCH = "POTENTIAL_MATCH"
    AMBIGUOUS_COLLISION = "AMBIGUOUS_COLLISION"
    NO_MATCH = "NO_MATCH"


class InvestigationConstraints(BaseModel):
    """Optional operational and epistemic constraints for identity probing."""

    allowed_platforms: list[str] | None = None
    blocked_platforms: list[str] | None = None
    permit_delimiter_permutations: bool = True  # e.g., 'foo_bar' -> 'foo-bar'
    max_candidates: int = 50
    timeout_per_probe_sec: float = 5.0
    require_biographical_data: bool = False
    strict_provenance: bool = True


class IdentityProbeRequest(BaseModel):
    """Input payload for the IdentityProbeSpecialist."""

    identifier: str = Field(..., description="Target handle, username, or email string")
    identifier_type: IdentifierType = Field(
        default=IdentifierType.USERNAME,
        description="Type of the provided identifier",
    )
    target_entity_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Known biographical/organizational context of the target entity",
    )
    constraints: InvestigationConstraints = Field(
        default_factory=InvestigationConstraints,
        description="Investigation boundaries and search options",
    )


class CandidateIdentityRelationship(BaseModel):
    """An unverified candidate identity relationship discovered on an external platform.
    
    In accordance with Heimdallr epistemic integrity rules, this represents a candidate
    correlation hypothesis with attached raw observations, NOT an assertion of identity.
    """

    candidate_entity: str = Field(
        ..., description="Identifier or synthetic handle representing the remote account"
    )
    identifier: str = Field(
        ..., description="The queried identifier that led to discovery"
    )
    source_platform: str = Field(
        ..., description="Name of the platform (e.g. GitHub, Twitter, LinkedIn)"
    )
    source_url: str = Field(
        ..., description="Canonical URL of the candidate profile"
    )
    supporting_observation: str = Field(
        ..., description="Raw observed data snippet (display name, bio, tags)"
    )
    provenance: dict[str, Any] = Field(
        default_factory=dict,
        description="Technical provenance (HTTP status, timestamp, matched signatures, hash)",
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Preliminary probe confidence score (probe existence match strength)",
    )
    discovery_method: str = Field(
        default="http_probe",
        description="Method utilized (e.g. exact_handle_probe, delimiter_permutation_probe)",
    )
    timestamp: str = Field(
        ..., description="ISO-8601 timestamp of probe observation"
    )
    epistemic_status: EpistemicCandidateStatus = Field(
        default=EpistemicCandidateStatus.UNVERIFIED_CANDIDATE,
        description="Epistemic candidate status. NEVER asserts definitive identity truth.",
    )
    raw_profile_data: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured profile attributes discovered (display_name, bio, location)",
    )


class IdentityProbeResult(BaseModel):
    """Output contract returned by the IdentityProbeSpecialist."""

    target_identifier: str
    identifier_type: IdentifierType
    candidates: list[CandidateIdentityRelationship] = Field(default_factory=list)
    total_platforms_probed: int = 0
    total_candidates_found: int = 0
    execution_time_ms: float = 0.0
    epistemic_notice: str = (
        "CANDIDATES ONLY: The specialist makes no assertion of entity identity equivalence. "
        "All candidate relationships require authoritative verification by the Argus Verifier."
    )
    outcome: SpecialistOutcome = Field(
        default=SpecialistOutcome.SUCCESS_EMPTY,
        description="Outcome status: SUCCESS_WITH_RESULTS, SUCCESS_EMPTY, SOURCE_UNAVAILABLE, SOURCE_ERROR, PARTIAL_SUCCESS",
    )
    errors: list[str] = Field(default_factory=list)
