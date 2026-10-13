from enum import Enum

from pydantic import BaseModel, Field

from argus.domain.claim import ClaimStatus


class VerdictType(str, Enum):
    """Adjudicated epistemic verdict category."""

    CORROBORATED = "corroborated"  # Multiple sources confirm same fact
    DIRECT_SUPPORT = "direct_support"  # Single authoritative source confirms exact claim
    SUPERSEDED = "superseded"  # Newer authoritative source overrides older claim
    CONTRADICTION = "contradiction"  # Unresolved dispute between sources
    INSUFFICIENT = "insufficient"  # Weak or isolated single-source claim
    INFERRED = "inferred"  # Derived value rather than directly observed text


class ClaimEvaluation(BaseModel):
    """Adjudicated evaluation for an individual claim."""

    claim_id: str = Field(..., description="ID of the claim being evaluated")
    status: ClaimStatus = Field(
        ..., description="Resulting epistemic verification status"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Calibrated confidence score"
    )
    verdict: VerdictType = Field(..., description="Epistemic verdict category")
    reasoning: str = Field(..., description="Logical rationale justifying the verdict")


class AdjudicationPayload(BaseModel):
    """Structured output returned by the Expert Verifier LLM."""

    evaluations: list[ClaimEvaluation] = Field(
        ..., description="Evaluations for each presented claim"
    )
    has_conflict: bool = Field(
        ..., description="True if irreconcilable contradiction exists"
    )
    summary_reasoning: str = Field(
        ..., description="Overall synthesis of evidence and conflicts"
    )
    suggested_disambiguation_tasks: list[str] = Field(
        default_factory=list,
        description="Suggested targeted research tasks to resolve disputes",
    )


class AdjudicationResult(BaseModel):
    """Summary of adjudication run across a group of claims."""

    subject_entity_id: str
    predicate: str
    claims_evaluated: int
    claims_supported: int = 0
    claims_corroborated: int = 0
    claims_contradicted: int = 0
    claims_refuted: int = 0
    claims_unverified: int = 0
    claims_inferred: int = 0
    suggested_tasks: list[str] = Field(default_factory=list)
