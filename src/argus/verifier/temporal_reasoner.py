"""Temporal State Reasoner for Historical and Restatement Corporate OSINT.

Explicitly models the regulatory lifecycle:
Observed -> Filed -> Effective -> Amended -> Restated -> Superseded

Answers: "What was true at time T?" rather than "What does the latest document say?"
"""

from __future__ import annotations

from enum import Enum
import logging
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class LifecycleState(str, Enum):
    OBSERVED = "OBSERVED"
    FILED = "FILED"
    EFFECTIVE = "EFFECTIVE"
    AMENDED = "AMENDED"
    RESTATED = "RESTATED"
    SUPERSEDED = "SUPERSEDED"


class TemporalRecord(BaseModel):
    """An observation or regulatory disclosure with explicit filing and effective intervals."""

    record_id: str
    lifecycle_state: LifecycleState
    subject: str
    predicate: str
    object: str
    filing_date: str | None = Field(default=None, description="Date document was officially lodged/published")
    effective_start: str | None = Field(default=None, description="Start date of effective legal validity")
    effective_end: str | None = Field(default=None, description="End date / resignation / termination date")
    supersedes_record_id: str | None = Field(default=None, description="ID of superseded prior disclosure")
    is_restatement: bool = False
    source_url: str | None = None


class TemporalResolutionVerdict(BaseModel):
    """Verdict resolving what was true at time T."""

    as_of_date: str
    subject: str
    predicate: str
    active_object: str | None
    is_active_at_time_t: bool
    status: str  # "ACTIVE", "HISTORICAL_FORMER", "FUTURE_NOT_YET_APPOINTED", "SUPERSEDED"
    authoritative_record_id: str | None
    superseded_records: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    rationale: str


class TemporalStateReasoner:
    """Evaluates the legal and factual state of entities at an arbitrary historical date T."""

    def resolve_at_date(
        self,
        as_of_date: str,
        subject: str,
        predicate: str,
        records: list[TemporalRecord],
    ) -> TemporalResolutionVerdict:
        """Determines what claim held true on `as_of_date`."""
        relevant = [r for r in records if r.subject.lower() == subject.lower() and r.predicate.lower() == predicate.lower()]

        if not relevant:
            return TemporalResolutionVerdict(
                as_of_date=as_of_date,
                subject=subject,
                predicate=predicate,
                active_object=None,
                is_active_at_time_t=False,
                status="NO_RECORDS",
                authoritative_record_id=None,
                rationale="No temporal records matching subject and predicate found.",
            )

        # 1. Identify superseded records (e.g. 10-K superseded by 10-K/A restatement)
        superseded_ids = set()
        for r in relevant:
            if r.supersedes_record_id:
                superseded_ids.add(r.supersedes_record_id)

        active_candidates: list[TemporalRecord] = []
        for r in relevant:
            if r.record_id in superseded_ids:
                continue

            # Check effective window
            start_ok = True
            end_ok = True
            if r.effective_start and r.effective_start > as_of_date:
                start_ok = False
            if r.effective_end and r.effective_end < as_of_date:
                end_ok = False

            if start_ok and end_ok:
                active_candidates.append(r)

        if active_candidates:
            # Sort by restatement priority and filing date
            active_candidates.sort(
                key=lambda x: (1 if x.is_restatement else 0, x.filing_date or ""),
                reverse=True,
            )
            top = active_candidates[0]
            return TemporalResolutionVerdict(
                as_of_date=as_of_date,
                subject=subject,
                predicate=predicate,
                active_object=top.object,
                is_active_at_time_t=True,
                status="ACTIVE",
                authoritative_record_id=top.record_id,
                superseded_records=list(superseded_ids),
                rationale=f"Active at {as_of_date} per authoritative filing {top.record_id} (effective {top.effective_start} to {top.effective_end or 'present'}).",
            )

        # Check if record was historical (ended before as_of_date)
        former = [r for r in relevant if r.effective_end and r.effective_end < as_of_date]
        if former:
            former.sort(key=lambda x: x.effective_end or "", reverse=True)
            top_former = former[0]
            return TemporalResolutionVerdict(
                as_of_date=as_of_date,
                subject=subject,
                predicate=predicate,
                active_object=top_former.object,
                is_active_at_time_t=False,
                status="HISTORICAL_FORMER",
                authoritative_record_id=top_former.record_id,
                superseded_records=list(superseded_ids),
                rationale=f"Former / resigned prior to {as_of_date} (ended on {top_former.effective_end}).",
            )

        # Otherwise future or ungrounded
        return TemporalResolutionVerdict(
            as_of_date=as_of_date,
            subject=subject,
            predicate=predicate,
            active_object=None,
            is_active_at_time_t=False,
            status="INACTIVE_OR_UNCONFIRMED",
            authoritative_record_id=None,
            superseded_records=list(superseded_ids),
            rationale=f"No record was legally effective on date {as_of_date}.",
        )
