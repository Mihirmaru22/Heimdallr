"""Request dependencies: the signed-in user, CSRF on unsafe methods, and org membership checks."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db, set_tenant
from app.errors import ApiError, forbidden, not_found
from app.models import ROLE_RANK, AuthSession, Membership, Organization, Role, User
from app.security import CSRF_HEADER, SESSION_COOKIE, csrf_ok, load_session

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


@dataclass
class Auth:
    user: User
    session: AuthSession


def current_auth(request: Request, db: Session = Depends(get_db)) -> Auth:
    sess = load_session(db, request.cookies.get(SESSION_COOKIE))
    if sess is None:
        raise ApiError(401, "unauthenticated", "Sign in to continue")
    user = db.get(User, sess.user_id)
    if user is None or user.disabled_at is not None:
        raise ApiError(401, "unauthenticated", "This account is not active")
    if request.method in UNSAFE and not csrf_ok(sess, request.headers.get(CSRF_HEADER)):
        raise ApiError(403, "csrf_failed", "Missing or invalid CSRF token")
    return Auth(user, sess)


def current_user(auth: Auth = Depends(current_auth)) -> User:
    return auth.user


@dataclass
class OrgContext:
    user: User
    org: Organization
    role: Role

    def require(self, minimum: Role) -> None:
        if ROLE_RANK[self.role] < ROLE_RANK[minimum]:
            raise forbidden(f"This needs the {minimum.value} role")


def org_context(org_id: uuid.UUID, db: Session, user: User) -> OrgContext:
    row = db.execute(select(Membership, Organization).join(Organization, Organization.id == Membership.org_id)
                     .where(Membership.org_id == org_id, Membership.user_id == user.id)).first()
    if row is None or row[1].disabled_at is not None:
        raise not_found("organization")
    set_tenant(db, org_id)
    return OrgContext(user, row[1], Role(row[0].role))


def org_member(org_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)) -> OrgContext:
    return org_context(org_id, db, user)


def platform_admin(user: User = Depends(current_user)) -> User:
    if not user.is_platform_admin:
        raise not_found("page")
    return user
