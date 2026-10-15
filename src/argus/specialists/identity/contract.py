"""Clean-Room Identity Specialist Contract.

Defines the formal capability contract for identity discovery, candidate account
harvesting, and evidence provenance under Heimdallr.

Crucial Architectural Invariants:
1. The specialist discovers candidate accounts and provides raw observations and provenance.
   It NEVER asserts verified identity equivalence without independent corroborating evidence.
2. Account existence, identity equivalence, and access to private content are strictly
   separate claims.
3. Private profile content (e.g. private Instagram) is NEVER claimed to be retrieved
   without authorized access.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid
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


class AccountClaimType(str, Enum):
    """Specific claim type distinguishing existence, identity equivalence, and privacy boundaries."""

    ACCOUNT_EXISTENCE = "ACCOUNT_EXISTENCE"
    IDENTITY_EQUIVALENCE = "IDENTITY_EQUIVALENCE"
    PRIVATE_CONTENT_ACCESS = "PRIVATE_CONTENT_ACCESS"


class IdentityClaim(BaseModel):
    """Fine-grained identity claim maintaining strict epistemic boundaries."""

    claim_type: AccountClaimType
    subject: str
    platform: str
    status: str
    statement: str
    is_private: bool = False
    authorized_access: bool = False
    content_retrieved: bool = True
    source_url: str = ""
    retrieval_mode: str = "FIXTURE_SIMULATION"
    is_live: bool = False
    response_content_sha256: str | None = None
    observation_record_sha256: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)


class InvestigationConstraints(BaseModel):
    """Optional operational and epistemic constraints for identity probing."""

    allowed_platforms: list[str] | None = None
    blocked_platforms: list[str] | None = None
    permit_delimiter_permutations: bool = True  # e.g., 'foo_bar' -> 'foo-bar'
    max_candidates: int = 50
    timeout_per_probe_sec: float = 5.0
    require_biographical_data: bool = False
    strict_provenance: bool = True
    starting_platform: str | None = None


class IdentityProbeRequest(BaseModel):
    """Input payload for the IdentityProbeSpecialist."""

    identifier: str = Field(..., description="Target handle, username, or email string")
    identifier_type: IdentifierType = Field(
        default=IdentifierType.USERNAME,
        description="Type of the provided identifier",
    )
    starting_platform: str | None = Field(
        default=None,
        description="Starting platform where the username originated (e.g. github, instagram, twitter)",
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
        ..., description="Name of the platform (e.g. GitHub, Twitter, LinkedIn, Instagram)"
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
    is_starting_account: bool = Field(
        default=False,
        description="True if this record corresponds to the resolved starting account on starting platform",
    )
    is_private: bool = Field(
        default=False,
        description="True if the discovered remote account is marked private",
    )
    private_content_accessed: bool = Field(
        default=False,
        description="ALWAYS False for private accounts unless explicitly authorized credentials were provided",
    )
    retrieval_mode: str = Field(
        default="FIXTURE_SIMULATION",
        description="Explicit retrieval mode: LIVE vs FIXTURE_SIMULATION",
    )
    is_live: bool = Field(
        default=False,
        description="True ONLY if record was acquired through live outbound network retrieval",
    )
    response_content_sha256: str | None = Field(
        default=None,
        description="Cryptographic SHA-256 hash of actual raw response bytes captured from source",
    )
    observation_record_sha256: str | None = Field(
        default=None,
        description="Cryptographic SHA-256 hash of structured observation payload",
    )


class IdentityProbeResult(BaseModel):
    """Output contract returned by the IdentityProbeSpecialist."""

    target_identifier: str
    identifier_type: IdentifierType
    starting_platform: str | None = None
    starting_account: CandidateIdentityRelationship | None = None
    candidates: list[CandidateIdentityRelationship] = Field(default_factory=list)
    sources_queried: list[str] = Field(default_factory=list)
    claims: list[IdentityClaim] = Field(default_factory=list)
    platforms_queried: int = 0
    platforms_skipped: int = 0
    platforms_available: int = 0
    total_platforms_probed: int = 0
    total_candidates_found: int = 0
    execution_time_ms: float = 0.0
    epistemic_notice: str = (
        "CANDIDATES ONLY: The specialist makes no assertion of entity identity equivalence. "
        "All candidate relationships require authoritative verification by the Argus Verifier."
    )
    outcome: SpecialistOutcome = Field(
        default=SpecialistOutcome.SUCCESS_EMPTY,
        description="Outcome status: SUCCESS_WITH_RESULTS, SUCCESS_EMPTY, SOURCE_UNAVAILABLE, SOURCE_ERROR, PARTIAL_SUCCESS, TIMEOUT",
    )
    errors: list[str] = Field(default_factory=list)


class IdentityInvestigationReport(BaseModel):
    """Structured, evidence-backed report for an identity investigation vertical slice."""

    investigation_id: str = Field(default_factory=lambda: f"id_rep_{uuid.uuid4().hex[:10]}")
    starting_identifier: str
    starting_platform: str
    starting_account_resolved: bool = False
    starting_account_profile: dict[str, Any] | None = None

    sources_queried: list[str] = Field(default_factory=list)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    supporting_evidence: list[dict[str, Any]] = Field(default_factory=list)
    candidate_identity_links: list[dict[str, Any]] = Field(default_factory=list)
    contradictory_evidence: list[dict[str, Any]] = Field(default_factory=list)
    source_failures: list[dict[str, Any]] = Field(default_factory=list)
    coverage_gaps: list[str] = Field(default_factory=list)
    unresolved_questions: list[dict[str, Any]] = Field(default_factory=list)

    outcome: SpecialistOutcome = SpecialistOutcome.SUCCESS_EMPTY
    platforms_queried: int = 0
    platforms_skipped: int = 0
    platforms_available: int = 0
    account_existence_claims: list[dict[str, Any]] = Field(default_factory=list)
    identity_equivalence_claims: list[dict[str, Any]] = Field(default_factory=list)
    private_content_access_claims: list[dict[str, Any]] = Field(default_factory=list)
    epistemic_status: str = "UNKNOWN"
    stopping_rationale: str = ""
    steps_taken: int = 0
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
