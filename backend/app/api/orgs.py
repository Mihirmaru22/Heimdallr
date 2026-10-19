"""Organizations and their members."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import OrgContext, current_user, org_member
from app.errors import ApiError, forbidden, not_found
from app.models import ROLE_RANK, Membership, Organization, Role, User
from app.schemas import MemberIn, MemberOut, MemberUpdate, OrgIn, OrgOut, OrgUpdate, UsageOut
from app.services.common import active_jobs, audit, org_limits, usage_this_month

from ._util import client_ip
from .auth import slugify

router = APIRouter(prefix="/orgs", tags=["organizations"])


@router.get("", response_model=list[OrgOut])
def list_orgs(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[OrgOut]:
    rows = db.execute(select(Organization, Membership.role).join(Membership, Membership.org_id == Organization.id)
                      .where(Membership.user_id == user.id, Organization.disabled_at.is_(None))
                      .order_by(Organization.created_at)).all()
    return [OrgOut(id=o.id, name=o.name, slug=o.slug, role=r) for o, r in rows]


@router.post("", response_model=OrgOut, status_code=201)
def create_org(body: OrgIn, request: Request, user: User = Depends(current_user),
               db: Session = Depends(get_db)) -> OrgOut:
    org = Organization(name=body.name, slug=slugify(body.name))
    db.add(org)
    db.flush()
    db.add(Membership(org_id=org.id, user_id=user.id, role=Role.owner))
    audit(db, "org.create", org_id=org.id, actor_id=user.id, target_type="org", target_id=org.id,
          ip=client_ip(request))
    db.commit()
    return OrgOut(id=org.id, name=org.name, slug=org.slug, role=Role.owner)


@router.get("/{org_id}", response_model=OrgOut)
def get_org(ctx: OrgContext = Depends(org_member)) -> OrgOut:
    return OrgOut(id=ctx.org.id, name=ctx.org.name, slug=ctx.org.slug, role=ctx.role)


@router.patch("/{org_id}", response_model=OrgOut)
def update_org(body: OrgUpdate, request: Request, ctx: OrgContext = Depends(org_member),
               db: Session = Depends(get_db)) -> OrgOut:
    ctx.require(Role.admin)
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(ctx.org, k, v)
    audit(db, "org.update", org_id=ctx.org.id, actor_id=ctx.user.id, target_type="org", target_id=ctx.org.id,
          ip=client_ip(request), data=changes)
    db.commit()
    return OrgOut(id=ctx.org.id, name=ctx.org.name, slug=ctx.org.slug, role=ctx.role)


@router.get("/{org_id}/usage", response_model=UsageOut)
def usage(ctx: OrgContext = Depends(org_member), db: Session = Depends(get_db)) -> UsageOut:
    from app.services.common import month

    oid = ctx.org.id
    return UsageOut(period=month(), pages=usage_this_month(db, oid, "pages"),
                    llm_requests=usage_this_month(db, oid, "llm_request"),
                    export_rows=usage_this_month(db, oid, "export_rows"),
                    active_jobs=active_jobs(db, oid), limits=org_limits(ctx.org))


# --- members ----------------------------------------------------------------------------------


def _member_out(m: Membership, u: User) -> MemberOut:
    return MemberOut(user_id=u.id, email=u.email, display_name=u.display_name, role=m.role, created_at=m.created_at)


@router.get("/{org_id}/members", response_model=list[MemberOut])
def list_members(ctx: OrgContext = Depends(org_member), db: Session = Depends(get_db)) -> list[MemberOut]:
    rows = db.execute(select(Membership, User).join(User, User.id == Membership.user_id)
                      .where(Membership.org_id == ctx.org.id).order_by(Membership.created_at)).all()
    return [_member_out(m, u) for m, u in rows]


@router.post("/{org_id}/members", response_model=MemberOut, status_code=201)
def add_member(body: MemberIn, request: Request, ctx: OrgContext = Depends(org_member),
               db: Session = Depends(get_db)) -> MemberOut:
    """Adds an existing account by email. (Invitations by email are out of scope for the local MVP.)"""
    ctx.require(Role.admin)
    user = db.execute(select(User).where(User.email == str(body.email))).scalar_one_or_none()
    if user is None or user.disabled_at is not None:
        raise not_found("user")
    if db.execute(select(Membership).where(Membership.org_id == ctx.org.id,
                                           Membership.user_id == user.id)).first():
        raise ApiError(409, "already_member", "That user is already a member")
    m = Membership(org_id=ctx.org.id, user_id=user.id, role=body.role)
    db.add(m)
    audit(db, "member.add", org_id=ctx.org.id, actor_id=ctx.user.id, target_type="user", target_id=user.id,
          ip=client_ip(request), data={"role": body.role})
    db.commit()
    return _member_out(m, user)


def _membership(db: Session, org_id: uuid.UUID, user_id: uuid.UUID) -> Membership:
    m = db.execute(select(Membership).where(Membership.org_id == org_id,
                                            Membership.user_id == user_id)).scalar_one_or_none()
    if m is None:
        raise not_found("member")
    return m


def _owners(db: Session, org_id: uuid.UUID) -> int:
    return db.execute(select(func.count()).select_from(Membership).where(
        Membership.org_id == org_id, Membership.role == Role.owner)).scalar_one()


@router.patch("/{org_id}/members/{user_id}", response_model=MemberOut)
def update_member(user_id: uuid.UUID, body: MemberUpdate, request: Request, ctx: OrgContext = Depends(org_member),
                  db: Session = Depends(get_db)) -> MemberOut:
    ctx.require(Role.admin)
    m = _membership(db, ctx.org.id, user_id)
    # Only owners can grant or take away ownership; admins can't promote past themselves.
    if (m.role == Role.owner or body.role == Role.owner) and ctx.role != Role.owner:
        raise forbidden("Only an owner can change ownership")
    if m.role == Role.owner and body.role != Role.owner and _owners(db, ctx.org.id) <= 1:
        raise ApiError(409, "last_owner", "An organization needs at least one owner")
    if ROLE_RANK[Role(body.role)] > ROLE_RANK[ctx.role]:
        raise forbidden()
    m.role = body.role
    audit(db, "member.role", org_id=ctx.org.id, actor_id=ctx.user.id, target_type="user", target_id=user_id,
          ip=client_ip(request), data={"role": body.role})
    db.commit()
    return _member_out(m, db.get(User, user_id))


@router.delete("/{org_id}/members/{user_id}", status_code=204)
def remove_member(user_id: uuid.UUID, request: Request, ctx: OrgContext = Depends(org_member),
                  db: Session = Depends(get_db)) -> None:
    if user_id != ctx.user.id:
        ctx.require(Role.admin)
    m = _membership(db, ctx.org.id, user_id)
    if m.role == Role.owner and ctx.role != Role.owner:
        raise forbidden("Only an owner can remove an owner")
    if m.role == Role.owner and _owners(db, ctx.org.id) <= 1:
        raise ApiError(409, "last_owner", "An organization needs at least one owner")
    db.delete(m)
    audit(db, "member.remove", org_id=ctx.org.id, actor_id=ctx.user.id, target_type="user", target_id=user_id,
          ip=client_ip(request))
    db.commit()
