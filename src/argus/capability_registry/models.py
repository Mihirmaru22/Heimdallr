"""Heimdallr V3.1: Capability Contract & Type Models.

Defines first-class, strongly typed models that separate CAPABILITIES from IMPLEMENTATIONS:
- Extensible CapabilityCategory and QuestionType taxonomies
- Concrete Input/Output schemas and Epistemic declarations
- Performance Profiles, Cost Models, and Security Profiles
- License and Recruitment Metadata for clean-room verification
- Dynamic Health & Availability states
- Ranked CapabilityCandidate contract for InvestigationMatcher
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, Field, field_validator


class CapabilityCategory(str, Enum):
    """Extensible capability categories for Heimdallr intelligence ecosystem."""

    GENERAL_RESEARCH = "GENERAL_RESEARCH"
    IDENTITY = "IDENTITY"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    CORPORATE = "CORPORATE"
    DOCUMENT_INTELLIGENCE = "DOCUMENT_INTELLIGENCE"
    VERIFICATION = "VERIFICATION"
    ENTITY_RESOLUTION = "ENTITY_RESOLUTION"
    TEMPORAL_REASONING = "TEMPORAL_REASONING"
    CONTRADICTION_ANALYSIS = "CONTRADICTION_ANALYSIS"
    SANCTIONS_AND_OFFSHORE = "SANCTIONS_AND_OFFSHORE"
    ONION_AND_DARKWEB = "ONION_AND_DARKWEB"
    EMAIL_AND_ACCOUNT = "EMAIL_AND_ACCOUNT"


class HealthStatus(str, Enum):
    """Runtime availability and operational health of a capability implementation."""

    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    DISABLED = "DISABLED"
    QUARANTINED = "QUARANTINED"


class LicenseStatus(str, Enum):
    """License compatibility and clean-room recruitment status."""

    APPROVED = "APPROVED"
    RESTRICTED = "RESTRICTED"
    REFERENCE_ONLY = "REFERENCE_ONLY"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


class EpistemicNature(str, Enum):
    """Explicit epistemic guarantee of the produced outputs."""

    CANDIDATE = "CANDIDATE"             # Provisional hypothesis (requires verification)
    OBSERVATION = "OBSERVATION"         # Uninterpreted raw extraction
    CLAIM = "CLAIM"                     # Grounded proposition
    VERIFIED_FACT = "VERIFIED_FACT"     # Authoritatively corroborated fact


class LicenseMetadata(BaseModel):
    """Legal and architectural recruitment metadata."""

    license: str
    license_status: LicenseStatus = LicenseStatus.APPROVED
    source_type: str = "IN_TREE"  # IN_TREE, CLEAN_ROOM_CHALLENGER, EXTERNAL_API
    repository: str = "argus-core"
    version: str = "1.0.0"
    commit: str = "HEAD"
    clean_room_status: str = "VERIFIED_CLEAN_ROOM"
    commercial_compatibility: bool = True
    restrictions: List[str] = Field(default_factory=list)


class CostModel(BaseModel):
    """Quantitative computational and token cost model for a capability."""

    cost_per_query_usd: float = 0.0015
    avg_tokens_per_call: int = 1200
    avg_runtime_ms: float = 250.0
    requires_external_network: bool = False
    rate_limit_qps: Optional[float] = None


class PerformanceProfile(BaseModel):
    """Empirically measured benchmark performance observation."""

    accuracy: float = 1.0
    precision: float = 1.0
    recall: float = 1.0
    f1: float = 1.0
    evidence_correctness: float = 1.0
    epistemic_accuracy: float = 1.0
    temporal_accuracy: float = 1.0
    cost_usd: float = 0.0015
    runtime_sec: float = 0.25
    failure_rate: float = 0.0
    benchmark_id: str = "EVAL_V2"
    benchmark_version: str = "2.1.0"
    measurement_date: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    scope: str = "BENCHMARK_OBSERVED"


class SecurityProfile(BaseModel):
    """Security guarantees, sandboxing, and data isolation characteristics."""

    sandboxed: bool = True
    evaluator_isolated: bool = True
    prompt_injection_sanitized: bool = True
    air_gapped_compatible: bool = True
    allowed_domains: List[str] = Field(default_factory=list)
    prohibited_operations: List[str] = Field(default_factory=list)


class BenchmarkMetadata(BaseModel):
    """Benchmark certification history and compliance record."""

    certified_benchmarks: List[str] = Field(default_factory=lambda: ["EVAL_V2", "EVAL_INVESTIGATION_V1"])
    last_eval_pass_rate: float = 1.0
    last_certified_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CapabilityInputSchema(BaseModel):
    """Declared schema definition for inputs expected by the capability."""

    schema_type: str = "OBJECT"
    required_fields: List[str] = Field(default_factory=list)
    optional_fields: List[str] = Field(default_factory=list)
    field_descriptions: Dict[str, str] = Field(default_factory=dict)


class CapabilityOutputSchema(BaseModel):
    """Declared schema definition for outputs emitted by the capability."""

    schema_type: str = "OBJECT"
    output_fields: List[str] = Field(default_factory=list)
    epistemic_nature: EpistemicNature = EpistemicNature.CANDIDATE
    authoritative: bool = False
    field_descriptions: Dict[str, str] = Field(default_factory=dict)


class CapabilityDefinition(BaseModel):
    """First-class formal contract for an intelligence capability in Heimdallr."""

    capability_id: str = Field(..., description="Unique capability identifier, e.g. 'identity_resolution'")
    name: str = Field(..., description="Human-readable capability name")
    description: str = Field(..., description="Detailed description of capability scope and mechanics")
    version: str = Field(default="1.0.0", description="Semver version string")
    category: CapabilityCategory = Field(..., description="High-level category")
    status: HealthStatus = Field(default=HealthStatus.AVAILABLE, description="Current operational status")
    provider: str = Field(default="argus", description="Provider namespace or organization")
    implementation_id: str = Field(..., description="Specific implementation class or service ID")

    # Schemas
    input_schema: CapabilityInputSchema
    output_schema: CapabilityOutputSchema

    # Operational contracts
    question_types: List[str] = Field(default_factory=list, description="Question taxonomy codes this capability can resolve")
    supported_operations: List[str] = Field(default_factory=list, description="Action operations supported, e.g. ['DNS_QUERY', 'REGISTRY_SEARCH']")
    evidence_types: List[str] = Field(default_factory=list, description="Types of evidence produced, e.g. ['CT_LOG', 'SEC_FILING']")
    epistemic_behavior: str = Field(default="CANDIDATE_ONLY_VERIFIER_AUTHORITATIVE", description="Epistemic guarantee description")
    temporal_behavior: str = Field(default="POINT_IN_TIME_AWARE", description="Temporal handling capability")
    jurisdictions: List[str] = Field(default_factory=lambda: ["GLOBAL"], description="Supported legal jurisdictions")
    entity_types: List[str] = Field(default_factory=list, description="Entity classes processed, e.g. ['PERSON', 'ORGANIZATION', 'DOMAIN']")

    # Limitations & Failure modes
    dependencies: List[str] = Field(default_factory=list, description="Prerequisite capability IDs")
    limitations: List[str] = Field(default_factory=list, description="Declared scope limitations")
    failure_modes: List[str] = Field(default_factory=list, description="Known failure scenarios")

    # Profiles
    cost_model: CostModel = Field(default_factory=CostModel)
    performance_profile: PerformanceProfile = Field(default_factory=PerformanceProfile)
    security_profile: SecurityProfile = Field(default_factory=SecurityProfile)
    license_metadata: LicenseMetadata = Field(default_factory=lambda: LicenseMetadata(license="MIT"))
    benchmark_metadata: BenchmarkMetadata = Field(default_factory=BenchmarkMetadata)
    health_status: HealthStatus = Field(default=HealthStatus.AVAILABLE)

    @field_validator("version")
    @classmethod
    def validate_semver(cls, v: str) -> str:
        parts = v.split(".")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            raise ValueError(f"Invalid semver version: '{v}'. Must be X.Y.Z.")
        return v

    @field_validator("capability_id", "implementation_id", "provider", "name")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field cannot be empty or whitespace.")
        return v.strip()


class CapabilityCandidate(BaseModel):
    """Ranked capability recommendation returned by the CapabilityMatcher."""

    candidate_id: str = Field(default_factory=lambda: f"cand_{uuid.uuid4().hex[:8]}")
    capability_id: str
    implementation_id: str
    category: CapabilityCategory
    match_score: float = Field(..., ge=0.0, le=1.0, description="Overall matching confidence score (0.0 to 1.0)")
    matched_requirements: List[str] = Field(default_factory=list)
    unmet_requirements: List[str] = Field(default_factory=list)
    expected_information_gain: float = Field(default=0.8, ge=0.0, le=1.0)
    estimated_cost: float = Field(default=0.0015)
    evidence_strength: float = Field(default=0.9, ge=0.0, le=1.0)
    scope_fit: float = Field(default=1.0, ge=0.0, le=1.0)
    temporal_fit: float = Field(default=1.0, ge=0.0, le=1.0)
    jurisdiction_fit: float = Field(default=1.0, ge=0.0, le=1.0)
    health_status: HealthStatus = HealthStatus.AVAILABLE
    risk_flags: List[str] = Field(default_factory=list)
    rationale: str = ""
