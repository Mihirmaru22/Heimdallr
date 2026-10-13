"""Heimdallr V2: Investigation Hypothesis Model.

Models testable propositions with symmetrical support and refutation requirements:
- Active testing of both evidence FOR and evidence AGAINST
- Prevents confirmation-bias research
- Tracks evolving confidence based on validated evidentiary weight
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid

from pydantic import BaseModel, Field


class HypothesisStatus(str, Enum):
    """Epistemic evaluation statuses for a testable hypothesis."""

    UNTESTED = "UNTESTED"
    SUPPORTED = "SUPPORTED"
    WEAKLY_SUPPORTED = "WEAKLY_SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    SUPERSEDED = "SUPERSEDED"


class InvestigationHypothesis(BaseModel):
    """A testable proposition with explicit evidence requirements for and against."""

    hypothesis_id: str = Field(default_factory=lambda: f"hyp_{uuid.uuid4().hex[:8]}")
    proposition: str
    related_question_id: str | None = None
    related_entities: list[str] = Field(default_factory=list)

    supporting_evidence_requirements: list[str] = Field(default_factory=list)
    refuting_evidence_requirements: list[str] = Field(default_factory=list)

    current_status: HypothesisStatus = HypothesisStatus.UNTESTED
    confidence: float = 0.0  # 0.0 to 1.0

    supporting_claim_ids: list[str] = Field(default_factory=list)
    contradicting_claim_ids: list[str] = Field(default_factory=list)
    next_test_actions: list[str] = Field(default_factory=list)
    temporal_context: dict[str, Any] | None = None

    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolution_notes: str = ""

    def add_supporting_claim(self, claim_id: str, confidence_delta: float = 0.25) -> None:
        """Record evidence supporting the proposition and update confidence."""
        if claim_id not in self.supporting_claim_ids:
            self.supporting_claim_ids.append(claim_id)
        self.confidence = min(1.0, self.confidence + confidence_delta)
        self.recalculate_status()

    def add_contradicting_claim(self, claim_id: str, confidence_penalty: float = 0.35) -> None:
        """Record evidence contradicting the proposition and update status."""
        if claim_id not in self.contradicting_claim_ids:
            self.contradicting_claim_ids.append(claim_id)
        self.confidence = max(0.0, self.confidence - confidence_penalty)
        self.recalculate_status()

    def recalculate_status(self) -> HypothesisStatus:
        """Update status based on supporting vs contradicting claim counts."""
        n_sup = len(self.supporting_claim_ids)
        n_con = len(self.contradicting_claim_ids)

        if n_con > 0 and n_sup == 0:
            self.current_status = HypothesisStatus.CONTRADICTED
        elif n_con > 0 and n_sup > 0:
            if n_con >= n_sup:
                self.current_status = HypothesisStatus.CONTRADICTED
            else:
                self.current_status = HypothesisStatus.INCONCLUSIVE
        elif n_sup >= 2 and self.confidence >= 0.70:
            self.current_status = HypothesisStatus.SUPPORTED
        elif n_sup >= 1:
            self.current_status = HypothesisStatus.WEAKLY_SUPPORTED
        else:
            self.current_status = HypothesisStatus.UNTESTED

        self.updated_at = datetime.now(timezone.utc).isoformat()
        return self.current_status

    def supersede(self, superseded_by_id: str, reason: str) -> None:
        """Mark hypothesis superseded by a restated or more specific hypothesis."""
        self.current_status = HypothesisStatus.SUPERSEDED
        self.resolution_notes = f"Superseded by {superseded_by_id}: {reason}"
        self.updated_at = datetime.now(timezone.utc).isoformat()
