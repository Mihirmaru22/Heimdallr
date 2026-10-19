"""Job state machine. Transitions are atomic compare-and-set updates that also log an event."""

from __future__ import annotations

import uuid

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import CrawlJob, CrawlJobEvent
from app.models import JobState as S

TRANSITIONS: dict[S, set[S]] = {
    S.created: {S.validating, S.cancelled, S.failed},
    S.validating: {S.planning, S.failed, S.cancel_requested, S.cancelled},
    S.planning: {S.queued, S.failed, S.cancel_requested, S.cancelled},
    S.queued: {S.running, S.failed, S.cancel_requested, S.cancelled},
    S.running: {S.validating_results, S.waiting_quota, S.failed, S.cancel_requested},
    S.waiting_quota: {S.running, S.validating_results, S.failed, S.cancel_requested},
    S.validating_results: {S.exporting, S.completed, S.partially_completed, S.failed, S.cancel_requested},
    S.exporting: {S.completed, S.partially_completed, S.failed},
    S.cancel_requested: {S.cancelled, S.failed},
    S.completed: set(),
    S.partially_completed: set(),
    S.failed: {S.queued},  # retry
    S.cancelled: {S.queued},  # retry
}
TERMINAL = {S.completed, S.partially_completed, S.failed, S.cancelled}
ACTIVE = {S.created, S.validating, S.planning, S.queued, S.running, S.waiting_quota, S.validating_results,
          S.exporting, S.cancel_requested}


class IllegalTransition(Exception):
    pass


def can_transition(src: str, dst: str) -> bool:
    return S(dst) in TRANSITIONS.get(S(src), set())


def transition(db: Session, job: CrawlJob, dst: S, message: str = "", **fields) -> bool:
    """Move job to dst if it is still in the state we read. Returns False if someone else moved it."""
    src = S(job.state)
    if not can_transition(src, dst):
        raise IllegalTransition(f"{src} -> {dst}")
    values = {"state": dst.value, "lock_version": job.lock_version + 1, "updated_at": utcnow(), **fields}
    if dst == S.running and job.started_at is None:
        values["started_at"] = utcnow()
    if dst in TERMINAL:
        values["finished_at"] = utcnow()
    result = db.execute(
        update(CrawlJob)
        .where(CrawlJob.id == job.id, CrawlJob.state == src.value, CrawlJob.lock_version == job.lock_version)
        .values(**values)
    )
    if result.rowcount != 1:
        db.rollback()
        return False
    db.add(CrawlJobEvent(org_id=job.org_id, job_id=job.id, type="transition", from_state=src.value,
                         to_state=dst.value, message=message[:2000]))
    db.commit()
    db.refresh(job)
    return True


def log_event(db: Session, org_id: uuid.UUID, job_id: uuid.UUID, type_: str, message: str,
              data: dict | None = None) -> None:
    db.add(CrawlJobEvent(org_id=org_id, job_id=job_id, type=type_, message=message[:2000], data=data or {}))
