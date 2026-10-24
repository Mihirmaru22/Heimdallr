"""Small helpers shared by the routers."""

from __future__ import annotations

import uuid
from typing import TypeVar

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import not_found

T = TypeVar("T")


def client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


def get_in_org(db: Session, model: type[T], obj_id: uuid.UUID, org_id: uuid.UUID, what: str) -> T:
    """Load an object only if it belongs to the organization; otherwise 404 (never 403)."""
    obj = db.get(model, obj_id)
    if obj is None or getattr(obj, "org_id", None) != org_id:
        raise not_found(what)
    return obj


def paginate(db: Session, query, limit: int, offset: int) -> tuple[list, int]:
    total = db.execute(select(func.count()).select_from(query.order_by(None).subquery())).scalar_one()
    items = db.execute(query.limit(limit).offset(offset)).scalars().all()
    return list(items), int(total)
