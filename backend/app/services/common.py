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
