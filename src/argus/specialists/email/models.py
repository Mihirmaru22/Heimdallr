"""Heimdallr Vertical 6: Email & Account Intelligence Domain Models.

Implements strict four-dimensional epistemic verification and bidirectional
discovery data structures:
1. ADDRESS_VALIDITY: INVALID_SYNTAX, DOMAIN_VALID, DOMAIN_UNVERIFIED, INCONCLUSIVE
2. MAILBOX_EVIDENCE: DELIVERABILITY_CONFIRMED, DELIVERABILITY_INDICATED, UNVERIFIED, INCONCLUSIVE
3. IDENTITY_ASSOCIATION: DIRECTLY_ASSOCIATED, CORROBORATED_ASSOCIATION, POSSIBLE_ASSOCIATION, CONTRADICTED, UNKNOWN
4. TEMPORAL_STATUS: CURRENT, HISTORICAL, STALE, UNKNOWN
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AddressValidity(str, Enum):
    """Syntax and DNS domain routing validity."""
    INVALID_SYNTAX = "INVALID_SYNTAX"
    DOMAIN_VALID = "DOMAIN_VALID"
    DOMAIN_UNVERIFIED = "DOMAIN_UNVERIFIED"
    INCONCLUSIVE = "INCONCLUSIVE"


class MailboxEvidence(str, Enum):
    """Authorized mailbox existence and deliverability signals."""
    DELIVERABILITY_CONFIRMED = "DELIVERABILITY_CONFIRMED"
    DELIVERABILITY_INDICATED = "DELIVERABILITY_INDICATED"
    UNVERIFIED = "UNVERIFIED"
    INCONCLUSIVE = "INCONCLUSIVE"


class IdentityAssociation(str, Enum):
    """Grounded linkage between an email address and a human or legal identity."""
    DIRECTLY_ASSOCIATED = "DIRECTLY_ASSOCIATED"
    CORROBORATED_ASSOCIATION = "CORROBORATED_ASSOCIATION"
    POSSIBLE_ASSOCIATION = "POSSIBLE_ASSOCIATION"
    CONTRADICTED = "CONTRADICTED"
    UNKNOWN = "UNKNOWN"


class TemporalStatus(str, Enum):
    """Temporal lifecycle status of the email association or mailbox."""
    CURRENT = "CURRENT"
    HISTORICAL = "HISTORICAL"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class AssociationNature(str, Enum):
    """Epistemic nature of account or email discovery observation."""
    PUBLIC_PAGE_MENTION = "PUBLIC_PAGE_MENTION"
    PROFILE_EXPLICIT_PUBLICATION = "PROFILE_EXPLICIT_PUBLICATION"
    AUTHORIZED_PRESENCE_SIGNAL = "AUTHORIZED_PRESENCE_SIGNAL"
    CONFIRMED_IDENTITY_ASSOCIATION = "CONFIRMED_IDENTITY_ASSOCIATION"
    INFERRED_PATTERN_CANDIDATE = "INFERRED_PATTERN_CANDIDATE"


class AccountObservation(BaseModel):
    """Discovered online account or profile association for an email address."""
    platform: str
    canonical_url: str
    observed_email: str
    observation_timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source_provenance: str
    evidence_passage: str
    association_nature: AssociationNature = AssociationNature.PUBLIC_PAGE_MENTION
    association_strength: float = 0.5  # 0.0 to 1.0
    verification_status: str = "UNVERIFIED"  # UNVERIFIED, CORROBORATED, DISPUTED
    account_identifier: Optional[str] = None
    profile_metadata: Dict[str, Any] = Field(default_factory=dict)


class EmailCandidate(BaseModel):
    """Discovered or generated candidate email address for an identity."""
    email: str
    source_identifier: str
    derivation_method: str  # DIRECT_OBSERVATION, PATTERN_GENERATION, PROFILE_METADATA, DIRECTORY_LOOKUP
    epistemic_status: str = "UNVERIFIED"  # SUPPORTED, INFERRED, UNVERIFIED, CONTRADICTED, NOT_FOUND
    association_nature: AssociationNature = AssociationNature.PUBLIC_PAGE_MENTION
    confidence: float = 0.5
    temporal_status: TemporalStatus = TemporalStatus.UNKNOWN
    source_provenance: str = ""
    evidence_passage: str = ""
    target_identity: Optional[str] = None


class EmailVerificationResult(BaseModel):
    """Four-dimensional epistemic verification evaluation for an email address."""
    email: str
    address_validity: AddressValidity
    mailbox_evidence: MailboxEvidence
    identity_association: IdentityAssociation
    temporal_status: TemporalStatus
    syntax_details: Dict[str, Any] = Field(default_factory=dict)
    domain_details: Dict[str, Any] = Field(default_factory=dict)
    mailbox_details: Dict[str, Any] = Field(default_factory=dict)
    identity_details: Dict[str, Any] = Field(default_factory=dict)
    temporal_details: Dict[str, Any] = Field(default_factory=dict)
    disposable_domain: bool = False
    verification_timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    inconclusive_reasons: List[str] = Field(default_factory=list)


class IdentityResolutionVerdict(BaseModel):
    """Epistemic identity resolution evaluation between an email and a target identity."""
    email: str
    target_identity: str
    association_verdict: IdentityAssociation
    temporal_status: TemporalStatus
    confidence: float
    is_merged: bool = False
    rejection_reason: Optional[str] = None  # SHARED_NAME, RECYCLED_PHONE, REUSED_USERNAME, STALE_PROFILE, IMPERSONATION, INSUFFICIENT_EVIDENCE
    corroborating_evidence: List[Dict[str, Any]] = Field(default_factory=list)
    conflicting_evidence: List[Dict[str, Any]] = Field(default_factory=list)
    distinct_identities_detected: List[str] = Field(default_factory=list)
    epistemic_rationale: str = ""
