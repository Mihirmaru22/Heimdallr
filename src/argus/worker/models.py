from typing import Any

from pydantic import BaseModel, Field

from argus.domain.claim import Claim
from argus.domain.entity import Entity
from argus.domain.evidence import Evidence


class RelevanceAssessment(BaseModel):
    """Initial assessment of whether a document contains information relevant to the task."""

    is_relevant: bool = Field(
        ..., description="True if document provides facts answering the task"
    )
    reasoning: str = Field(
        ..., description="Brief explanation of relevance determination"
    )
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Confidence in assessment"
    )


class ExtractedEntityItem(BaseModel):
    """Candidate entity identified in the text."""

    name: str = Field(..., min_length=1, description="Primary name of the entity")
    entity_type: str = Field(
        ..., min_length=1, description="Type (e.g. company, facility, person)"
    )
    aliases: list[str] = Field(
        default_factory=list, description="Alternative names or abbreviations"
    )
    attributes: dict[str, Any] = Field(
        default_factory=dict, description="Attributes discovered"
    )


class ExtractedClaimItem(BaseModel):
    """Candidate factual claim with supporting quotation."""

    subject_name: str = Field(
        ..., min_length=1, description="Name of the subject entity"
    )
    predicate: str = Field(
        ..., min_length=1, description="Relation (e.g. HAS_PLANT_MANAGER, LOCATED_IN)"
    )
    object_value: str = Field(
        ..., min_length=1, description="Value or target entity name"
    )
    verbatim_passage: str = Field(
        ...,
        min_length=1,
        description="Exact quotation from text directly supporting the claim",
    )
    confidence: float = Field(
        default=0.8, ge=0.0, le=1.0, description="Estimated confidence score"
    )


class ExtractionPayload(BaseModel):
    """Unified structured output returned by Worker LLM."""

    relevance: RelevanceAssessment
    entities: list[ExtractedEntityItem] = Field(default_factory=list)
    claims: list[ExtractedClaimItem] = Field(default_factory=list)
    suggested_followup_tasks: list[str] = Field(default_factory=list)


class WorkerResult(BaseModel):
    """Summary of operations performed by the Worker on a Document."""

    document_url: str
    is_relevant: bool
    entities_created: list[Entity] = Field(default_factory=list)
    entities_updated: list[Entity] = Field(default_factory=list)
    evidence_created: list[Evidence] = Field(default_factory=list)
    claims_created: list[Claim] = Field(default_factory=list)
    suggested_followup_tasks: list[str] = Field(default_factory=list)
