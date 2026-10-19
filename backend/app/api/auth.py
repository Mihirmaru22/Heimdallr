"""Registration, sign-in, sign-out and the current user."""

from __future__ import annotations

import re
import secrets

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db, set_bypass
from app.deps import Auth, current_auth
from app.errors import ApiError
from app.models import Membership, Organization, Role, User
from app.schemas import LoginIn, MeOut, OrgOut, RegisterIn, UserOut
from app.security import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    create_session,
    destroy_session,
    dummy_verify,
    hash_password,
    record_attempt,
    too_many_attempts,
    verify_password,
)
from app.services.common import audit

from ._util import client_ip

router = APIRouter(prefix="/auth", tags=["auth"])


def slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:48] or "org"
    return f"{base}-{secrets.token_hex(3)}"


def _set_cookies(response: Response, token: str, csrf: str) -> None:
    s = get_settings()
    age = s.session_ttl_hours * 3600
    response.set_cookie(SESSION_COOKIE, token, max_age=age, httponly=True, secure=s.cookie_secure,
                        samesite="lax", path="/")
    # Readable by the SPA so it can echo it in the X-CSRF-Token header (double-submit).
    response.set_cookie(CSRF_COOKIE, csrf, max_age=age, httponly=False, secure=s.cookie_secure,
                        samesite="lax", path="/")


def me_payload(db: Session, user: User, csrf: str) -> MeOut:
    set_bypass(db, False)
    rows = db.execute(select(Organization, Membership.role).join(Membership, Membership.org_id == Organization.id)
                      .where(Membership.user_id == user.id, Organization.disabled_at.is_(None))
                      .order_by(Organization.created_at)).all()
    orgs = [OrgOut(id=o.id, name=o.name, slug=o.slug, role=role) for o, role in rows]
    return MeOut(user=UserOut.model_validate(user), organizations=orgs, csrf_token=csrf)


@router.post("/register", response_model=MeOut, status_code=201)
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)) -> MeOut:
    ip = client_ip(request)
    if too_many_attempts(db, f"register:{ip}"):
        raise ApiError(429, "rate_limited", "Too many attempts; try again later")
    record_attempt(db, f"register:{ip}")
    user = User(email=str(body.email), password_hash=hash_password(body.password),
                display_name=body.display_name or str(body.email).split("@")[0])
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "email_taken", "An account with this email already exists") from None
    org = Organization(name=body.organization_name or f"{user.display_name}'s workspace",
                       slug=slugify(body.organization_name or user.display_name))
    db.add(org)
    db.flush()
    db.add(Membership(org_id=org.id, user_id=user.id, role=Role.owner))
    audit(db, "user.register", org_id=org.id, actor_id=user.id, target_type="user", target_id=user.id, ip=ip)
    db.commit()
    token, csrf = create_session(db, user, ip)
    _set_cookies(response, token, csrf)
    return me_payload(db, user, csrf)


@router.post("/login", response_model=MeOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> MeOut:
    ip = client_ip(request)
    email = str(body.email).lower()
    if too_many_attempts(db, f"login:{email}") or too_many_attempts(db, f"login-ip:{ip}"):
        raise ApiError(429, "rate_limited", "Too many sign-in attempts; try again in 15 minutes")
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        dummy_verify(body.password)
    ok = user is not None and user.disabled_at is None and verify_password(user.password_hash, body.password)
    if not ok:
        record_attempt(db, f"login:{email}")
        record_attempt(db, f"login-ip:{ip}")
        raise ApiError(401, "invalid_credentials", "Email or password is incorrect")
    audit(db, "user.login", actor_id=user.id, target_type="user", target_id=user.id, ip=ip)
    db.commit()
    token, csrf = create_session(db, user, ip)
    _set_cookies(response, token, csrf)
    return me_payload(db, user, csrf)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, auth: Auth = Depends(current_auth),
           db: Session = Depends(get_db)) -> Response:
    destroy_session(db, request.cookies.get(SESSION_COOKIE))
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return response


@router.get("/me", response_model=MeOut)
def me(auth: Auth = Depends(current_auth), db: Session = Depends(get_db)) -> MeOut:
    return me_payload(db, auth.user, auth.session.csrf_token)
