"""Corporate Financial & Registry Intelligence Specialist Contract.

Defines the formal capability contract for corporate legal entity discovery,
SEC EDGAR filings, Companies House records, officer/director verification,
subsidiary/ownership relationships, and temporal reasoning under Heimdallr.

Core Architectural Invariants:
1. SPECIALIST DISCOVERS. ARGUS VERIFIES.
2. The specialist returns candidate corporate facts and relationships with provenance.
3. The specialist NEVER asserts definitive legal ownership or beneficial control
   unless authoritatively corroborated by the Argus Verifier.
4. Preserves temporal validity (appointment date, resignation date, acquisition date,
   filing date, effective date) without assuming 'latest record = timeless truth'.
5. Strictly enforces Entity Type Safety:
   - BRAND != LEGAL ENTITY
   - REGISTERED AGENT != OWNER / OFFICER
   - DIRECTOR != BENEFICIAL OWNER
   - SUBSIDIARY != PARENT
"""

from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field

from argus.specialists.outcome import SpecialistOutcome


class CorporateIdentifierType(str, Enum):
    """Officially recognized regulatory corporate identifier formats."""

    CIK = "CIK"  # SEC Central Index Key (10 digits)
    COMPANY_NUMBER_UK = "COMPANY_NUMBER_UK"  # Companies House UK (8 alphanumeric)
    LEI = "LEI"  # Legal Entity Identifier (20 alphanumeric)
    STATE_CORP_ID = "STATE_CORP_ID"  # Delaware / State Division of Corporations ID
    TICKER = "TICKER"  # Stock Exchange Ticker Symbol


class CorporateRelationshipType(str, Enum):
    """Categorization of corporate structural and legal relationships."""

    PARENT_COMPANY = "parent_company"
    SUBSIDIARY = "subsidiary"
    ACQUIRED_SUBSIDIARY = "acquired_subsidiary"
    DIVESTED_SUBSIDIARY = "divested_subsidiary"
    OFFICER = "officer"
    DIRECTOR = "director"
    BENEFICIAL_OWNER = "beneficial_owner"
    REGISTERED_AGENT = "registered_agent"
    BRAND_NAME = "brand_name"
    FILING_ENTITY = "filing_entity"


class OfficerRole(str, Enum):
    """Corporate titles and officer designations."""

    CEO = "Chief Executive Officer"
    CFO = "Chief Financial Officer"
    COO = "Chief Operating Officer"
    DIRECTOR = "Director"
    SECRETARY = "Company Secretary"
    CHAIRMAN = "Chairman of the Board"
    REGISTERED_AGENT = "Registered Agent"


class TemporalCorporateStatus(str, Enum):
    """Temporal validity state of corporate relationships."""

    CURRENT_ACTIVE = "CURRENT_ACTIVE"
    HISTORICAL_RESIGNED = "HISTORICAL_RESIGNED"
    HISTORICAL_DIVESTED = "HISTORICAL_DIVESTED"
    AMENDED_SUPERSEDED = "AMENDED_SUPERSEDED"
    UNKNOWN_TEMPORAL = "UNKNOWN_TEMPORAL"


class EpistemicCorporateStatus(str, Enum):
    """Candidate-level epistemic statuses emitted by corporate registry probes."""

    CANDIDATE_FACT = "CANDIDATE_FACT"
    UNVERIFIED_RELATIONSHIP = "UNVERIFIED_RELATIONSHIP"
    REGISTERED_AGENT_ONLY = "REGISTERED_AGENT_ONLY"
    AMENDED_SUPERSEDED = "AMENDED_SUPERSEDED"
    CONTRADICTED_RECORD = "CONTRADICTED_RECORD"
    NO_MATCH = "NO_MATCH"


class CorporateInvestigationConstraints(BaseModel):
    """Operational and jurisdictional scope constraints."""

    allowed_jurisdictions: list[str] | None = None
    target_relationship: CorporateRelationshipType | None = None
    as_of_date: str | None = None  # ISO-8601 YYYY-MM-DD
    include_historical: bool = True
    max_candidates: int = 50
    strict_provenance: bool = True


class CorporateProbeRequest(BaseModel):
    """Input payload for corporate registry and regulatory filing queries."""

    entity_name: str = Field(..., description="Target company legal name or commercial brand")
    corporate_identifier: str | None = Field(default=None, description="Regulatory CIK, Company Number, or LEI")
    identifier_type: CorporateIdentifierType | None = Field(default=None, description="Identifier classification")
    jurisdiction: str | None = Field(default=None, description="Incorporation state or country (e.g. US-DE, GB)")
    target_relationship: CorporateRelationshipType | None = Field(
        default=None, description="Target relationship filter (officer, subsidiary, beneficial_owner, etc.)"
    )
    as_of_date: str | None = Field(default=None, description="Historical temporal filter anchor (YYYY-MM-DD)")
    constraints: CorporateInvestigationConstraints = Field(
        default_factory=CorporateInvestigationConstraints, description="Investigation boundaries"
    )


class CandidateCorporateRelationship(BaseModel):
    """An unverified candidate corporate fact or relationship extracted from registry filings."""

    relationship_id: str = Field(..., description="Unique deterministic identifier for relationship")
    subject_entity: str = Field(..., description="Primary subject entity legal name")
    predicate: CorporateRelationshipType = Field(..., description="Nature of corporate relationship")
    object_entity: str = Field(..., description="Target related entity, officer, or subsidiary name")
    jurisdiction: str = Field(..., description="Regulatory jurisdiction (e.g., US-DE, UK, Global)")
    source_registry: str = Field(..., description="Registry origin (SEC_EDGAR, COMPANIES_HOUSE, GLEIF)")
    filing_id: str | None = Field(default=None, description="Accession number or official filing ID")
    source_url: str = Field(..., description="Direct URL or canonical reference to source filing")
    filing_date: str | None = Field(default=None, description="Filing submission date (YYYY-MM-DD)")
    effective_date: str | None = Field(default=None, description="Date relationship took legal effect")
    resignation_date: str | None = Field(default=None, description="Date officer resigned or subsidiary sold")
    observation: str = Field(..., description="Raw text snippet or structured field extracted from filing")
    provenance: dict[str, Any] = Field(
        default_factory=dict, description="Cryptographic SHA-256 fingerprint, endpoint, timestamp"
    )
    extraction_method: str = Field(
        ..., description="Extraction path (edgar_submissions_api, ch_officers_endpoint, gleif_records)"
    )
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="Registry factual extraction confidence")
    temporal_status: TemporalCorporateStatus = Field(
        default=TemporalCorporateStatus.CURRENT_ACTIVE,
        description="Temporal validity state (CURRENT_ACTIVE, HISTORICAL_RESIGNED, etc.)",
    )
    epistemic_status: EpistemicCorporateStatus = Field(
        default=EpistemicCorporateStatus.CANDIDATE_FACT,
        description="Epistemic status. Never asserts verified legal ownership without Argus verification.",
    )
    raw_filing_metadata: dict[str, Any] = Field(
        default_factory=dict, description="Raw structured filing payload"
    )


class CorporateProbeResult(BaseModel):
    """Output contract returned by the CorporateProbeSpecialist."""

    target_entity: str
    target_identifier: str | None = None
    relationships: list[CandidateCorporateRelationship] = Field(default_factory=list)
    total_registries_queried: int = 0
    total_relationships_found: int = 0
    execution_time_ms: float = 0.0
    epistemic_notice: str = (
        "CANDIDATES ONLY: The specialist makes no assertion of beneficial ownership or legal liability. "
        "All candidate relationships require authoritative verification by the Argus Verifier."
    )
    outcome: SpecialistOutcome = Field(
        default=SpecialistOutcome.SUCCESS_EMPTY,
        description="Outcome status: SUCCESS_WITH_RESULTS, SUCCESS_EMPTY, SOURCE_UNAVAILABLE, SOURCE_ERROR, PARTIAL_SUCCESS",
    )
    errors: list[str] = Field(default_factory=list)
