"""Database engine, sessions and the tenant context used by Postgres row-level security.

Every tenant table has a policy `org_id = current_setting('app.org_id')`. The app sets that value
for the connection once it knows which organization a request or task belongs to; the repository
layer also filters by org_id, so RLS is a second line of defence, not the only one.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy import DateTime, create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.config import get_settings


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


def new_id() -> uuid.UUID:
    return uuid.uuid4()


engine = create_engine(get_settings().database_url, pool_pre_ping=True, future=True)


@event.listens_for(engine, "checkin")
def _reset_tenant(dbapi_conn, _record):  # pragma: no cover - exercised implicitly
    # A pooled connection must never carry one request's tenant into the next request.
    try:
        cur = dbapi_conn.cursor()
        cur.execute("RESET app.org_id; RESET app.bypass_rls")
        cur.close()
        dbapi_conn.commit()
    except Exception:  # noqa: S110 - a broken connection is discarded by the pool anyway
        pass


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


@event.listens_for(Session, "after_begin")
def _apply_tenant(session: Session, _transaction, connection) -> None:
    # A session may get a different pooled connection after each commit, so the tenant is
    # re-applied at the start of every transaction from what the session was told.
    connection.exec_driver_sql(
        "SELECT set_config('app.org_id', %(org)s, false), set_config('app.bypass_rls', %(bypass)s, false)",
        {"org": session.info.get("org_id", ""), "bypass": "on" if session.info.get("bypass") else ""},
    )


def _reapply(db: Session) -> None:
    db.execute(
        text("SELECT set_config('app.org_id', :o, false), set_config('app.bypass_rls', :b, false)"),
        {"o": db.info.get("org_id", ""), "b": "on" if db.info.get("bypass") else ""},
    )


def set_tenant(db: Session, org_id: uuid.UUID | None) -> None:
    """Scope this session to one organization (or to none)."""
    db.info["org_id"] = str(org_id) if org_id else ""
    _reapply(db)


def set_bypass(db: Session, on: bool) -> None:
    """Platform-admin and maintenance code only: see rows of every organization."""
    db.info["bypass"] = on
    _reapply(db)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        set_tenant(db, None)
        yield db
    finally:
        db.close()


@contextmanager
def session_scope(org_id: uuid.UUID | None = None, bypass: bool = False) -> Iterator[Session]:
    """Short-lived session for worker tasks; commits on success."""
    db = SessionLocal()
    try:
        set_tenant(db, org_id)
        if bypass:
            set_bypass(db, True)
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
