"""Domain Infrastructure & Passive DNS Specialist Contract.

Defines the formal capability contract for infrastructure enumeration, subdomain
discovery, certificate-associated domain mapping, and network provenance under Heimdallr.

Core Architectural Invariants:
1. SPECIALIST DISCOVERS. ARGUS VERIFIES.
2. The specialist returns candidate infrastructure relationships, NOT verified corporate assets.
3. Every asset retains technical and cryptographic provenance (source endpoint, timestamp, payload hash).
4. The specialist NEVER asserts corporate ownership ("Target Company owns this domain/IP")
   unless authoritatively verified by the Argus Verifier against corporate biographical/legal evidence.
"""

from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field

from argus.specialists.outcome import SpecialistOutcome


class AssetType(str, Enum):
    """Categorization of discovered network assets."""

    SUBDOMAIN = "subdomain"
    DNS_RECORD = "dns_record"
    CERTIFICATE_SAN = "certificate_san"
    IP_ASSOCIATION = "ip_association"
    RELATED_DOMAIN = "related_domain"


class RelationshipType(str, Enum):
    """Structural relationship between parent domain/entity and discovered asset."""

    DIRECT_SUBDOMAIN = "direct_subdomain"
    CERT_SAN_CO_OCCURRENCE = "cert_san_co_occurrence"
    CNAME_TARGET = "cname_target"
    SHARED_HOSTING_NEIGHBOR = "shared_hosting_neighbor"
    THIRD_PARTY_SAAS = "third_party_saas"
    LOOKALIKE_SUSPECT = "lookalike_suspect"
    PARENT_REGISTRANT = "parent_registrant"


class TemporalStatus(str, Enum):
    """Temporal validity of the infrastructure observation."""

    CURRENT_ACTIVE = "CURRENT_ACTIVE"
    HISTORICAL_EXPIRED = "HISTORICAL_EXPIRED"
    UNKNOWN_TEMPORAL = "UNKNOWN_TEMPORAL"


class EpistemicAssetStatus(str, Enum):
    """Candidate-level epistemic statuses emitted by infrastructure discovery probes.
    
    The specialist NEVER asserts 'VERIFIED_OWNED_ASSET'. It only emits candidate states.
    """

    CANDIDATE_ASSET = "CANDIDATE_ASSET"
    UNVERIFIED_INFRASTRUCTURE = "UNVERIFIED_INFRASTRUCTURE"
    THIRD_PARTY_SERVICE = "THIRD_PARTY_SERVICE"
    AMBIGUOUS_SHARED_HOST = "AMBIGUOUS_SHARED_HOST"
    EXPIRED_HISTORICAL = "EXPIRED_HISTORICAL"
    ADVERSARIAL_LOOKALIKE = "ADVERSARIAL_LOOKALIKE"
    NO_MATCH = "NO_MATCH"


class InfrastructureInvestigationConstraints(BaseModel):
    """Operational and investigative boundary constraints."""

    allowed_domains: list[str] | None = None
    disallowed_domains: list[str] | None = None
    max_depth: int = 3
    include_expired_certificates: bool = True
    classify_third_party_saas: bool = True
    max_assets: int = 100
    timeout_sec: float = 10.0
    strict_provenance: bool = True


class InfrastructureProbeRequest(BaseModel):
    """Input payload for infrastructure enumeration and passive DNS discovery."""

    domain: str = Field(..., description="Target apex domain or FQDN to expand")
    entity_name: str | None = Field(default=None, description="Known corporate entity name")
    known_entity_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Known corporate affiliations, subsidiaries, brands, and facilities",
    )
    constraints: InfrastructureInvestigationConstraints = Field(
        default_factory=InfrastructureInvestigationConstraints,
        description="Operational and scope boundaries",
    )


class CandidateInfrastructureAsset(BaseModel):
    """An unverified candidate network asset discovered via passive or active enumeration."""

    asset_id: str = Field(..., description="Unique canonical identifier (e.g. hostname or IP)")
    hostname: str = Field(..., description="Fully qualified domain name of the asset")
    parent_domain: str = Field(..., description="Queried apex domain")
    asset_type: AssetType = Field(..., description="Type of asset (subdomain, cert SAN, etc.)")
    relationship_type: RelationshipType = Field(
        ..., description="Observed structural relationship to parent domain"
    )
    ip_addresses: list[str] = Field(default_factory=list, description="Resolved IP addresses")
    cname_target: str | None = Field(default=None, description="CNAME destination if applicable")
    certificate_sans: list[str] = Field(
        default_factory=list, description="Subject Alternative Names on TLS certificate"
    )
    supporting_observation: str = Field(
        ..., description="Raw text snippet or record observed (DNS line, CT log record)"
    )
    provenance: dict[str, Any] = Field(
        default_factory=dict,
        description="Technical provenance (source endpoint, HTTP status, timestamp, SHA-256)",
    )
    confidence: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Preliminary probe confidence"
    )
    discovery_method: str = Field(
        ..., description="Discovery source (ct_log_enumeration, dns_zone, cert_san_expansion)"
    )
    timestamp: str = Field(..., description="ISO-8601 timestamp of discovery observation")
    temporal_status: TemporalStatus = Field(
        default=TemporalStatus.CURRENT_ACTIVE,
        description="Temporal validity status (CURRENT_ACTIVE vs HISTORICAL_EXPIRED)",
    )
    epistemic_status: EpistemicAssetStatus = Field(
        default=EpistemicAssetStatus.CANDIDATE_ASSET,
        description="Candidate epistemic status. NEVER asserts definitive ownership truth.",
    )
    raw_record_data: dict[str, Any] = Field(
        default_factory=dict,
        description="Raw structured attributes (cert validity dates, DNS TTL, ASN)",
    )


class InfrastructureProbeResult(BaseModel):
    """Output contract returned by the InfrastructureProbeSpecialist."""

    target_domain: str
    assets: list[CandidateInfrastructureAsset] = Field(default_factory=list)
    total_sources_queried: int = 0
    total_assets_found: int = 0
    execution_time_ms: float = 0.0
    epistemic_notice: str = (
        "CANDIDATES ONLY: The specialist makes no assertion of corporate entity ownership. "
        "All infrastructure assets require authoritative verification by the Argus Verifier."
    )
    outcome: SpecialistOutcome = Field(
        default=SpecialistOutcome.SUCCESS_EMPTY,
        description="Outcome status: SUCCESS_WITH_RESULTS, SUCCESS_EMPTY, SOURCE_UNAVAILABLE, SOURCE_ERROR, PARTIAL_SUCCESS",
    )
    errors: list[str] = Field(default_factory=list)
