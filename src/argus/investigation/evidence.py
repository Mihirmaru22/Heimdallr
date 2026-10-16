"""Heimdallr V2: Evidence Requirement Specification & Enforcement.

Enforces explicit evidentiary conditions BEFORE actions are planned and executed:
- Prevents irrelevant research sprawl
- Demands source type authority (SEC EDGAR, Companies House, DNS, CT Logs)
- Enforces independent corroboration standards
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid

from pydantic import BaseModel, Field


class EvidenceStatus(str, Enum):
    """Satisfaction level for a structured evidence requirement."""

    UNSATISFIED = "UNSATISFIED"
    PARTIALLY_SATISFIED = "PARTIALLY_SATISFIED"
    SATISFIED = "SATISFIED"


class EvidenceRequirement(BaseModel):
    """A concrete condition an observation must satisfy to substantiate a question or claim.

    Architectural Integration Notice:
    EvidenceRequirement and add_satisfying_evidence() provide evidentiary condition modeling.
    This mechanism is currently disconnected from the production investigation engine loops
    (InvestigationState, InvestigationPlanner, and InvestigationEngine), which rely on
    InvestigationQuestion, InvestigationHypothesis, InformationGap, and claims/evidence graphs.
    Broader integration into planner loops is reserved for a future architectural milestone.
    """

    requirement_id: str = Field(default_factory=lambda: f"evr_{uuid.uuid4().hex[:8]}")
    description: str
    target_entity: str | None = None
    predicate: str | None = None

    min_independent_sources: int = 1
    required_source_types: list[str] = Field(default_factory=list)
    temporal_bound: dict[str, Any] | None = None

    is_mandatory: bool = True
    status: EvidenceStatus = EvidenceStatus.UNSATISFIED

    satisfied_by_evidence_ids: list[str] = Field(default_factory=list)
    discovered_source_types: list[str] = Field(default_factory=list)
    independent_sources: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    satisfied_at: str | None = None

    def add_satisfying_evidence(
        self,
        evidence_id: str,
        source_type: str = "generic",
        source_id: str | None = None,
        is_independent: bool = True,
    ) -> None:
        """Register an evidentiary item against this requirement.
        
        Correct source-independence counting:
        Tracks unique independent sources. Non-independent items contribute to evidence
        records but do not inflate the independent source tally.
        """
        if evidence_id not in self.satisfied_by_evidence_ids:
            self.satisfied_by_evidence_ids.append(evidence_id)
        if source_type not in self.discovered_source_types:
            self.discovered_source_types.append(source_type)

        # Track independent sources uniquely
        if is_independent:
            src_key = source_id or f"{source_type}:{evidence_id}"
            if src_key not in self.independent_sources:
                self.independent_sources.append(src_key)

        # Sources count is the number of distinct independent sources registered, or 1 if non-independent evidence exists
        sources_count = len(self.independent_sources)
        meets_sources = sources_count >= self.min_independent_sources

        if self.required_source_types:
            meets_types = any(st in self.discovered_source_types for st in self.required_source_types)
        else:
            meets_types = True

        if meets_sources and meets_types:
            self.status = EvidenceStatus.SATISFIED
            self.satisfied_at = datetime.now(timezone.utc).isoformat()
        elif sources_count > 0:
            self.status = EvidenceStatus.PARTIALLY_SATISFIED

    def is_satisfied(self) -> bool:
        """Return True if requirement is fully met."""
        return self.status == EvidenceStatus.SATISFIED
