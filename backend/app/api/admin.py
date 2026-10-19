"""Platform administration. Every route 404s for non-admins so the surface is not discoverable."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db, set_bypass, utcnow
from app.deps import platform_admin
from app.errors import ApiError, not_found
from app.models import AuditLog, CrawlJob, DomainPolicy, Organization, User
from app.services.common import LIMIT_KEYS, audit, org_limits

from ._util import client_ip

router = APIRouter(prefix="/admin", tags=["admin"])


class AdminOrg(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    disabled: bool
    limits: dict[str, int]
    overrides: dict[str, Any]
    jobs: int


class OrgAdminUpdate(BaseModel):
    disabled: bool | None = None
    limits: dict[str, int] | None = None
    retention_days: int | None = Field(default=None, ge=1, le=3650)


class AdminUser(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    is_platform_admin: bool
    disabled: bool
    max_active_jobs: int | None


class UserAdminUpdate(BaseModel):
    disabled: bool | None = None
    max_active_jobs: int | None = Field(default=None, ge=0, le=1000)


class PolicyIn(BaseModel):
    domain: str = Field(min_length=3, max_length=255, pattern=r"^[a-z0-9.-]+$")
    org_id: uuid.UUID | None = None
    reason: str = Field(default="", max_length=500)


class PolicyOut(BaseModel):
    id: uuid.UUID
    domain: str
    org_id: uuid.UUID | None
    rule: str
    reason: str


def _admin_db(db: Session = Depends(get_db), _: User = Depends(platform_admin)) -> Session:
    set_bypass(db, True)
    return db


@router.get("/orgs", response_model=list[AdminOrg])
def orgs(db: Session = Depends(_admin_db), limit: int = Query(100, le=500), offset: int = 0) -> list[AdminOrg]:
    jobs = dict(db.execute(select(CrawlJob.org_id, func.count()).group_by(CrawlJob.org_id)).all())
    rows = db.execute(select(Organization).order_by(Organization.created_at).limit(limit).offset(offset)).scalars()
    return [AdminOrg(id=o.id, name=o.name, slug=o.slug, disabled=o.disabled_at is not None, limits=org_limits(o),
                     overrides=o.limits or {}, jobs=jobs.get(o.id, 0)) for o in rows]


@router.patch("/orgs/{org_id}", response_model=AdminOrg)
def update_org(org_id: uuid.UUID, body: OrgAdminUpdate, request: Request, db: Session = Depends(_admin_db),
               admin: User = Depends(platform_admin)) -> AdminOrg:
    org = db.get(Organization, org_id)
    if org is None:
        raise not_found("organization")
    if body.limits is not None:
        bad = sorted(set(body.limits) - set(LIMIT_KEYS))
        if bad or any(v < 0 for v in body.limits.values()):
            raise ApiError(422, "invalid_limits", f"Unknown or negative limits: {bad}")
        org.limits = body.limits
    if body.disabled is not None:
        org.disabled_at = utcnow() if body.disabled else None
    if body.retention_days is not None:
        org.retention_days = body.retention_days
    audit(db, "admin.org.update", org_id=org.id, actor_id=admin.id, target_type="org", target_id=org.id,
          ip=client_ip(request), data=body.model_dump(exclude_unset=True))
    db.commit()
    jobs = db.execute(select(func.count()).select_from(CrawlJob).where(CrawlJob.org_id == org.id)).scalar_one()
    return AdminOrg(id=org.id, name=org.name, slug=org.slug, disabled=org.disabled_at is not None,
                    limits=org_limits(org), overrides=org.limits or {}, jobs=jobs)


def _user_out(u: User) -> AdminUser:
    return AdminUser(id=u.id, email=u.email, display_name=u.display_name, is_platform_admin=u.is_platform_admin,
                     disabled=u.disabled_at is not None, max_active_jobs=u.max_active_jobs)


@router.get("/users", response_model=list[AdminUser])
def users(db: Session = Depends(_admin_db), q: str | None = Query(None, max_length=200),
          limit: int = Query(100, le=500), offset: int = 0) -> list[AdminUser]:
    query = select(User).order_by(User.created_at)
    if q:
        query = query.where(User.email.ilike(f"%{q}%"))
    return [_user_out(u) for u in db.execute(query.limit(limit).offset(offset)).scalars()]


@router.patch("/users/{user_id}", response_model=AdminUser)
def update_user(user_id: uuid.UUID, body: UserAdminUpdate, request: Request, db: Session = Depends(_admin_db),
                admin: User = Depends(platform_admin)) -> AdminUser:
    user = db.get(User, user_id)
    if user is None:
        raise not_found("user")
    if body.disabled is not None:
        if user.id == admin.id and body.disabled:
            raise ApiError(409, "self_disable", "You cannot disable your own account")
        user.disabled_at = utcnow() if body.disabled else None
    if "max_active_jobs" in body.model_fields_set:
        user.max_active_jobs = body.max_active_jobs
    audit(db, "admin.user.update", actor_id=admin.id, target_type="user", target_id=user.id,
          ip=client_ip(request), data=body.model_dump(exclude_unset=True))
    db.commit()
    return _user_out(user)


@router.get("/domain-policies", response_model=list[PolicyOut])
def policies(db: Session = Depends(_admin_db)) -> list[PolicyOut]:
    rows = db.execute(select(DomainPolicy).order_by(DomainPolicy.domain)).scalars()
    return [PolicyOut(id=p.id, domain=p.domain, org_id=p.org_id, rule=p.rule, reason=p.reason) for p in rows]


@router.post("/domain-policies", response_model=PolicyOut, status_code=201)
def add_policy(body: PolicyIn, request: Request, db: Session = Depends(_admin_db),
               admin: User = Depends(platform_admin)) -> PolicyOut:
    p = DomainPolicy(domain=body.domain.lower().strip("."), org_id=body.org_id, rule="deny", reason=body.reason)
    db.add(p)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "duplicate_policy", "That domain is already blocked") from None
    audit(db, "admin.policy.add", org_id=body.org_id, actor_id=admin.id, target_type="domain", target_id=p.id,
          ip=client_ip(request), data={"domain": p.domain})
    db.commit()
    return PolicyOut(id=p.id, domain=p.domain, org_id=p.org_id, rule=p.rule, reason=p.reason)


@router.delete("/domain-policies/{policy_id}", status_code=204)
def delete_policy(policy_id: uuid.UUID, db: Session = Depends(_admin_db),
                  admin: User = Depends(platform_admin)) -> None:
    p = db.get(DomainPolicy, policy_id)
    if p is None:
        raise not_found("policy")
    db.delete(p)
    audit(db, "admin.policy.delete", actor_id=admin.id, target_type="domain", target_id=policy_id,
          data={"domain": p.domain})
    db.commit()


@router.get("/audit")
def audit_log(db: Session = Depends(_admin_db), org_id: uuid.UUID | None = None,
              limit: int = Query(100, le=500), offset: int = 0) -> list[dict[str, Any]]:
    q = select(AuditLog).order_by(AuditLog.created_at.desc())
    if org_id:
        q = q.where(AuditLog.org_id == org_id)
    return [{"id": a.id, "org_id": a.org_id, "actor_id": a.actor_id, "action": a.action,
             "target_type": a.target_type, "target_id": a.target_id, "ip": a.ip, "data": a.data,
             "created_at": a.created_at} for a in db.execute(q.limit(limit).offset(offset)).scalars()]
