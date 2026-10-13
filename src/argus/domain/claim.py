import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ClaimStatus(str, Enum):
    """Epistemic verification state of a factual claim."""

    PENDING = "pending"  # Extracted, awaiting evaluation wall verification
    SUPPORTED = "supported"  # Backed by direct verified evidence
    CORROBORATED = "corroborated"  # Backed by multiple independent sources confirming same fact
    INFERRED = "inferred"  # Derived by Argus via reasoning/patterns, not directly observed
    UNVERIFIED = "unverified"  # Insufficient or weak evidence to establish fact
    CONTRADICTED = "contradicted"  # Active conflicting evidence found between sources
    REFUTED = "refuted"  # Disproven by authoritative evidence or superseded
    UNKNOWN = "unknown"  # Argus has not established the answer / undetermined
    NOT_FOUND = "not_found"  # Argus investigated the field but found no adequate evidence

    @classmethod
    def _missing_(cls, value: object):
        if isinstance(value, str):
            v = value.strip().lower()
            for member in cls:
                if member.value == v or member.name.lower() == v:
                    return member
        return super()._missing_(value)


def generate_claim_id() -> str:
    return f"clm_{uuid.uuid4().hex[:8]}"


class Claim(BaseModel):
    """The fundamental epistemic unit in Argus: Subject -> Predicate -> Object."""

    claim_id: str = Field(default_factory=generate_claim_id)
    objective_id: str | None = Field(
        default=None, description="Parent research objective ID"
    )
    subject_entity_id: str = Field(
        ..., min_length=1, description="Entity ID of the claim subject"
    )
    predicate: str = Field(
        ...,
        min_length=1,
        description="Relationship or property, e.g. HAS_PLANT_MANAGER",
    )
    object_value: str = Field(
        ..., min_length=1, description="Literal value or target entity name"
    )
    object_entity_id: str | None = Field(
        default=None, description="FK to target Entity if object is an entity"
    )
    status: ClaimStatus = Field(
        default=ClaimStatus.PENDING, description="Current verification state"
    )
    evidence_ids: list[str] = Field(
        default_factory=list, description="List of Evidence IDs backing this claim"
    )
    confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Adjudicated confidence score"
    )
    # Provenance and Epistemic Derivation Fields
    derivation_method: str | None = Field(
        default=None, description="Derivation technique if inferred (e.g. corporate_email_pattern)"
    )
    derivation_inputs: list[str] = Field(
        default_factory=list, description="Input entity or claim IDs used in derivation"
    )
    inference_reason: str | None = Field(
        default=None, description="Explicit rationale explaining the inference derivation"
    )
    temporal_context: str | None = Field(
        default=None, description="Temporal qualification (e.g. historical, current, 2021-2025)"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="UTC creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC last updated timestamp",
    )

    @property
    def derivation(self) -> dict[str, Any] | None:
        """Structured derivation provenance describing how Argus inferred the value."""
        if self.derivation_method or self.inference_reason or self.derivation_inputs:
            return {
                "method": self.derivation_method,
                "supporting_observations": self.derivation_inputs,
                "reason": self.inference_reason,
            }
        return None

    def is_verified(self) -> bool:
        """True if the claim is established fact (SUPPORTED or CORROBORATED)."""
        return self.status in (ClaimStatus.SUPPORTED, ClaimStatus.CORROBORATED)

    def is_inferred(self) -> bool:
        """True if the claim is a derived inference rather than an observed fact."""
        return self.status == ClaimStatus.INFERRED

