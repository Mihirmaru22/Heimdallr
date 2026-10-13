"""Heimdallr V2: Investigation Question Model & Lifecycle.

Decomposes broad objectives into structured, prioritizable, dependent questions:
- Tracks resolution status (OPEN, INVESTIGATING, SUPPORTED, etc.)
- Manages question hierarchies (parent/child branching)
- Explicitly models dependencies and specialist requirements
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid

from pydantic import BaseModel, Field


class QuestionStatus(str, Enum):
    """Lifecycle statuses for an investigation question."""

    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    SUPPORTED = "SUPPORTED"
    PARTIALLY_RESOLVED = "PARTIALLY_RESOLVED"
    CONTRADICTED = "CONTRADICTED"
    NOT_FOUND = "NOT_FOUND"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    UNKNOWN = "UNKNOWN"
    ABANDONED = "ABANDONED"


class QuestionType(str, Enum):
    """Categorical question taxonomy."""

    ENTITY_DISCOVERY = "ENTITY_DISCOVERY"
    RELATIONSHIP_VERIFICATION = "RELATIONSHIP_VERIFICATION"
    OFFICER_TENURE = "OFFICER_TENURE"
    INFRASTRUCTURE_ATTRIBUTION = "INFRASTRUCTURE_ATTRIBUTION"
    PLATFORM_ACCOUNT = "PLATFORM_ACCOUNT"
    IDENTITY_CORRELATION = "IDENTITY_CORRELATION"
    CONTRADICTION_RESOLUTION = "CONTRADICTION_RESOLUTION"
    TEMPORAL_STATE = "TEMPORAL_STATE"
    CONTACT_CHANNEL = "CONTACT_CHANNEL"
    NEGATIVE_VERIFICATION = "NEGATIVE_VERIFICATION"
    GENERAL = "GENERAL"


class InvestigationQuestion(BaseModel):
    """A single testable investigation question with dependencies and evidence bounds."""

    question_id: str = Field(default_factory=lambda: f"q_{uuid.uuid4().hex[:8]}")
    parent_question_id: str | None = None
    child_question_ids: list[str] = Field(default_factory=list)

    question_text: str
    question_type: QuestionType = QuestionType.GENERAL
    priority: float = 0.5  # 0.0 (low) to 1.0 (critical)
    is_critical: bool = False
    status: QuestionStatus = QuestionStatus.OPEN

    required_evidence: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)  # prerequisite question_ids
    related_entities: list[str] = Field(default_factory=list)
    related_claims: list[str] = Field(default_factory=list)
    temporal_context: dict[str, Any] | None = None
    specialist_requirements: list[str] = Field(default_factory=list)

    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved_at: str | None = None
    resolution_reason: str | None = None
    resolved_by_claim_ids: list[str] = Field(default_factory=list)
    resolved_by_evidence_ids: list[str] = Field(default_factory=list)

    def is_blocked(self, resolved_question_ids: set[str]) -> bool:
        """Return True if any prerequisite question is not yet resolved."""
        return any(dep not in resolved_question_ids for dep in self.dependencies)

    def mark_investigating(self) -> None:
        """Mark question as actively under research."""
        if self.status == QuestionStatus.OPEN:
            self.status = QuestionStatus.INVESTIGATING

    def resolve(
        self,
        status: QuestionStatus,
        reason: str,
        claim_ids: list[str] | None = None,
        evidence_ids: list[str] | None = None,
    ) -> None:
        """Resolve question with explicit status, rationale, and grounding."""
        self.status = status
        self.resolution_reason = reason
        self.resolved_at = datetime.now(timezone.utc).isoformat()
        if claim_ids:
            self.resolved_by_claim_ids.extend(claim_ids)
        if evidence_ids:
            self.resolved_by_evidence_ids.extend(evidence_ids)

    def abandon(self, reason: str) -> None:
        """Mark question abandoned (e.g. branch prune, irrelevance, zero gain)."""
        self.status = QuestionStatus.ABANDONED
        self.resolution_reason = reason
        self.resolved_at = datetime.now(timezone.utc).isoformat()

    def spawn_child(
        self,
        question_text: str,
        question_type: QuestionType | None = None,
        priority: float | None = None,
        required_evidence: list[str] | None = None,
        related_entities: list[str] | None = None,
        specialist_requirements: list[str] | None = None,
    ) -> InvestigationQuestion:
        """Spawn a child question linked to this parent."""
        child = InvestigationQuestion(
            parent_question_id=self.question_id,
            question_text=question_text,
            question_type=question_type or self.question_type,
            priority=priority if priority is not None else self.priority,
            required_evidence=required_evidence or [],
            related_entities=related_entities or list(self.related_entities),
            specialist_requirements=specialist_requirements or list(self.specialist_requirements),
            temporal_context=self.temporal_context.copy() if self.temporal_context else None,
        )
        self.child_question_ids.append(child.question_id)
        return child
