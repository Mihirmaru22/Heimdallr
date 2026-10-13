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
    """A concrete condition an observation must satisfy to substantiate a question or claim."""

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
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    satisfied_at: str | None = None

    def add_satisfying_evidence(
        self,
        evidence_id: str,
        source_type: str = "generic",
        is_independent: bool = True,
    ) -> None:
        """Register an evidentiary item against this requirement."""
        if evidence_id not in self.satisfied_by_evidence_ids:
            self.satisfied_by_evidence_ids.append(evidence_id)
        if source_type not in self.discovered_source_types:
            self.discovered_source_types.append(source_type)

        # Check satisfaction
        sources_count = len(self.satisfied_by_evidence_ids) if is_independent else 1
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
