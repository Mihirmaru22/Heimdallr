"""Quotas, usage records and audit logging."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import utcnow
from app.errors import ApiError
from app.models import AuditLog, CrawlJob, Organization, UsageRecord, User
from app.services.state_machine import ACTIVE

LIMIT_KEYS = ("max_pages_per_job", "max_depth", "max_active_jobs_per_org", "max_pages_per_org_month",
              "max_records_per_job", "max_export_rows")


def org_limits(org: Organization) -> dict[str, int]:
    """Platform limits, lowered (never raised) by the organization's overrides."""
    s = get_settings()
    limits = {k: int(getattr(s, k)) for k in LIMIT_KEYS}
    for k, v in (org.limits or {}).items():
        if k in limits and isinstance(v, int) and v >= 0:
            limits[k] = min(limits[k], v)
    return limits


def month() -> str:
    return utcnow().strftime("%Y-%m")


def usage_this_month(db: Session, org_id: uuid.UUID, kind: str) -> int:
    return int(db.execute(select(func.coalesce(func.sum(UsageRecord.quantity), 0)).where(
        UsageRecord.org_id == org_id, UsageRecord.period_month == month(), UsageRecord.kind == kind)).scalar_one())


def record_usage(db: Session, org_id: uuid.UUID, kind: str, quantity: int, *, user_id=None, job_id=None,
                 detail: dict[str, Any] | None = None) -> None:
    db.add(UsageRecord(org_id=org_id, user_id=user_id, job_id=job_id, kind=kind, quantity=quantity,
                       detail=detail or {}, period_month=month()))


def active_jobs(db: Session, org_id: uuid.UUID, user_id: uuid.UUID | None = None) -> int:
    q = select(func.count()).select_from(CrawlJob).where(CrawlJob.org_id == org_id,
                                                         CrawlJob.state.in_([s.value for s in ACTIVE]))
    if user_id is not None:
        q = q.where(CrawlJob.created_by == user_id)
    return int(db.execute(q).scalar_one())


def check_job_quota(db: Session, org: Organization, user: User, pages: int) -> None:
    limits = org_limits(org)
    if active_jobs(db, org.id) >= limits["max_active_jobs_per_org"]:
        raise ApiError(429, "quota_active_jobs",
                       f"Your organization already has {limits['max_active_jobs_per_org']} active jobs")
    if user.max_active_jobs is not None and active_jobs(db, org.id, user.id) >= user.max_active_jobs:
        raise ApiError(429, "quota_user_jobs", "You have reached your personal active-job limit")
    used = usage_this_month(db, org.id, "pages")
    if used + pages > limits["max_pages_per_org_month"]:
        raise ApiError(429, "quota_pages",
                       f"This job could exceed the monthly page quota ({used} of "
                       f"{limits['max_pages_per_org_month']} used)")


def audit(db: Session, action: str, *, org_id=None, actor_id=None, target_type=None, target_id=None, ip=None,
          data: dict[str, Any] | None = None) -> None:
    db.add(AuditLog(org_id=org_id, actor_id=actor_id, action=action, target_type=target_type,
                    target_id=str(target_id) if target_id else None, ip=ip, data=data or {}))


def model_calls(job: CrawlJob) -> tuple[dict[str, dict[str, int]], dict[str, dict[str, int]]]:
    """(the job's model calls per step, its plan's), each step {"answered": n, "failed": n}: what the job stored
    when it ended, or while it runs, the live counts in Redis."""
    counters = job.counters or {}
    if counters.get("model_calls_kept"):
        out: dict[str, dict[str, dict[str, int]]] = {"model_calls": {}, "plan_model_calls": {}}
        for key, n in counters.items():
            scope, _, rest = key.partition(".")
            if scope in out and rest.count(".") == 1:
                step, outcome = rest.split(".")
                out[scope].setdefault(step, {"answered": 0, "failed": 0})[outcome] = int(n)
        return out["model_calls"], out["plan_model_calls"]
    try:
        from app.llm.openrouter import State

        state = State()
        return state.calls(str(job.id)), state.calls(f"schema:{job.schema_id}")
    except Exception:  # noqa: BLE001 - no Redis: no live counts
        return {}, {}


def model_call_lines(job: CrawlJob) -> list[tuple[str, str]]:
    """(label, "total N: answered A, failed F") for the whole job and each step, plan included."""
    calls, plan = model_calls(job)
    steps = {k: dict(v) for k, v in calls.items()}
    for counts in plan.values():  # whatever the planner's calls were tagged with, they planned the job
        merged = steps.setdefault("plan", {"answered": 0, "failed": 0})
        for outcome in ("answered", "failed"):
            merged[outcome] = merged.get(outcome, 0) + counts.get(outcome, 0)

    def line(c: dict[str, int]) -> str:
        a, f = c.get("answered", 0), c.get("failed", 0)
        return f"total {a + f}: answered {a}, failed {f}"

    total = {o: sum(c.get(o, 0) for c in steps.values()) for o in ("answered", "failed")}
    return [("model calls", line(total))] + [(f"model calls: {step}", line(c)) for step, c in sorted(
        steps.items(), key=lambda kv: -(kv[1].get("answered", 0) + kv[1].get("failed", 0)))]
