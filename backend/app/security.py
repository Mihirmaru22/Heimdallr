"""Password hashing (Argon2id), server-side sessions, CSRF tokens and signed download links."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
import uuid
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import utcnow
from app.models import AuthSession, LoginAttempt, User

SESSION_COOKIE = "wd_session"
CSRF_COOKIE = "wd_csrf"
CSRF_HEADER = "X-CSRF-Token"

_hasher = PasswordHasher()
# Used to keep login timing the same whether or not the email exists.
_DUMMY_HASH = _hasher.hash("not-a-real-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored: str, password: str) -> bool:
    try:
        return _hasher.verify(stored, password)
    except (VerificationError, InvalidHashError):
        return False


def dummy_verify(password: str) -> None:
    verify_password(_DUMMY_HASH, password)


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user: User, ip: str) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    db.add(AuthSession(token_hash=_digest(token), user_id=user.id, csrf_token=csrf, ip=ip[:64],
                       expires_at=utcnow() + timedelta(hours=get_settings().session_ttl_hours)))
    db.execute(delete(AuthSession).where(AuthSession.expires_at < utcnow()))
    db.commit()
    return token, csrf


def load_session(db: Session, token: str | None) -> AuthSession | None:
    if not token or len(token) > 100:
        return None
    sess = db.get(AuthSession, _digest(token))
    if sess is None or sess.expires_at < utcnow():
        return None
    return sess


def destroy_session(db: Session, token: str | None) -> None:
    if token:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == _digest(token)))
        db.commit()


def csrf_ok(sess: AuthSession, header_value: str | None) -> bool:
    return bool(header_value) and hmac.compare_digest(sess.csrf_token, header_value or "")


def too_many_attempts(db: Session, key: str) -> bool:
    since = utcnow() - timedelta(minutes=15)
    count = db.execute(select(func.count()).select_from(LoginAttempt).where(
        LoginAttempt.key == key, LoginAttempt.created_at > since)).scalar_one()
    return count >= get_settings().login_attempts_per_15min


def record_attempt(db: Session, key: str) -> None:
    db.add(LoginAttempt(key=key[:320]))
    db.commit()


def sign_download(export_id: uuid.UUID, user_id: uuid.UUID, ttl_seconds: int = 300) -> str:
    expires = int(time.time()) + ttl_seconds
    msg = f"{export_id}:{user_id}:{expires}".encode()
    sig = hmac.new(get_settings().secret_key.encode(), msg, hashlib.sha256).hexdigest()
    return f"{expires}.{sig}"


def verify_download(token: str, export_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    try:
        expires_s, sig = token.split(".", 1)
        expires = int(expires_s)
    except ValueError:
        return False
    if expires < time.time():
        return False
    msg = f"{export_id}:{user_id}:{expires}".encode()
    good = hmac.new(get_settings().secret_key.encode(), msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(good, sig)
