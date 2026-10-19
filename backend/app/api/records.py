"""Extracted records: browse, search, review, correct and exclude."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import String, cast, select, update
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import OrgContext, org_member
from app.errors import ApiError
from app.extract.normalize import InvalidValue, normalize_value
from app.models import CrawlJob, ExtractedRecord, ExtractionSchema, FieldValue
from app.schemas import ExcludeIn, FieldValueOut, Page, RecordDetail, RecordOut, RecordPatch
from app.services.common import audit
from app.spec.models import ExtractionSpec

from ._util import client_ip, get_in_org, paginate

router = APIRouter(prefix="/orgs/{org_id}", tags=["records"])

SORTS = {
    "quality": ExtractedRecord.quality_score.desc(),
    "-quality": ExtractedRecord.quality_score.asc(),
    "created": ExtractedRecord.created_at.asc(),
    "updated": ExtractedRecord.updated_at.desc(),
}


@router.get("/jobs/{job_id}/records", response_model=Page[RecordOut])
def list_records(job_id: uuid.UUID, ctx: OrgContext = Depends(org_member), db: Session = Depends(get_db),
                 status: list[Literal["valid", "partial", "invalid"]] = Query(default_factory=list),
                 excluded: bool | None = None, q: str | None = Query(None, max_length=200),
                 sort: Literal["quality", "-quality", "created", "updated"] = "quality",
                 limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)) -> Page[RecordOut]:
    get_in_org(db, CrawlJob, job_id, ctx.org.id, "job")
    query = select(ExtractedRecord).where(ExtractedRecord.job_id == job_id, ExtractedRecord.org_id == ctx.org.id)
    if status:
        query = query.where(ExtractedRecord.status.in_(status))
    if excluded is not None:
        query = query.where(ExtractedRecord.excluded.is_(excluded))
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(cast(ExtractedRecord.data, String).ilike(f"%{escaped}%", escape="\\"))
    items, total = paginate(db, query.order_by(SORTS[sort], ExtractedRecord.id), limit, offset)
    return Page(items=[RecordOut.model_validate(r) for r in items], total=total, limit=limit, offset=offset)


def _detail(db: Session, rec: ExtractedRecord) -> RecordDetail:
    fvs = db.execute(select(FieldValue).where(FieldValue.record_id == rec.id)
                     .order_by(FieldValue.field_name, FieldValue.selected.desc(),
                               FieldValue.confidence.desc().nulls_last())).scalars().all()
    out = RecordOut.model_validate(rec).model_dump()
    return RecordDetail(**out, fields=[FieldValueOut.model_validate(f) for f in fvs])


@router.get("/records/{record_id}", response_model=RecordDetail)
def get_record(record_id: uuid.UUID, ctx: OrgContext = Depends(org_member),
               db: Session = Depends(get_db)) -> RecordDetail:
    return _detail(db, get_in_org(db, ExtractedRecord, record_id, ctx.org.id, "record"))


def _spec_for(db: Session, rec: ExtractedRecord) -> ExtractionSpec:
    job = db.get(CrawlJob, rec.job_id)
    return ExtractionSpec.model_validate(db.get(ExtractionSchema, job.schema_id).spec)


@router.patch("/records/{record_id}", response_model=RecordDetail)
def patch_record(record_id: uuid.UUID, body: RecordPatch, request: Request, ctx: OrgContext = Depends(org_member),
                 db: Session = Depends(get_db)) -> RecordDetail:
    """Correct values by hand. Values are validated like extracted ones; re-finalizing keeps the edits."""
    rec = get_in_org(db, ExtractedRecord, record_id, ctx.org.id, "record")
    if body.data:
        spec = _spec_for(db, rec)
        fields = {f.name: f for f in spec.fields}
        unknown = sorted(set(body.data) - set(fields))
        if unknown:
            raise ApiError(422, "unknown_fields", f"Not fields of this schema: {', '.join(unknown)}")
        data = dict(rec.data)
        errors = []
        for name, raw in body.data.items():
            try:
                value = None if raw in (None, "", []) else normalize_value(fields[name], raw)
            except InvalidValue as exc:
                errors.append({"loc": ["data", name], "msg": str(exc)})
                continue
            data[name] = value
            db.execute(update(FieldValue).where(FieldValue.record_id == rec.id, FieldValue.field_name == name)
                       .values(selected=False))
            db.add(FieldValue(org_id=rec.org_id, record_id=rec.id, field_name=name, value=value,
                              value_status="found" if value is not None else "absent", method="user_edit",
                              confidence=1.0, selected=True))
        if errors:
            db.rollback()
            raise ApiError(422, "invalid_values", "Some values are not valid", errors=errors)
        rec.data = data
        required = [f.name for f in spec.fields if f.required]
        present = {k for k, v in data.items() if v not in (None, "", [])}
        if required and not any(n in present for n in required):
            rec.status = "invalid"
        else:
            rec.status = "valid" if all(n in present for n in required) else "partial"
        rec.quality_score = round(len(present & set(fields)) / max(len(fields), 1), 3)
        rec.user_edited = True
    if body.excluded is not None:
        rec.excluded = body.excluded
    audit(db, "record.update", org_id=ctx.org.id, actor_id=ctx.user.id, target_type="record", target_id=rec.id,
          ip=client_ip(request), data={"fields": sorted(body.data or {}), "excluded": body.excluded})
    db.commit()
    return _detail(db, rec)


@router.post("/jobs/{job_id}/records/exclude")
def exclude(job_id: uuid.UUID, body: ExcludeIn, ctx: OrgContext = Depends(org_member),
            db: Session = Depends(get_db)) -> dict[str, int]:
    get_in_org(db, CrawlJob, job_id, ctx.org.id, "job")
    result = db.execute(update(ExtractedRecord).where(ExtractedRecord.job_id == job_id,
                                                      ExtractedRecord.org_id == ctx.org.id,
                                                      ExtractedRecord.id.in_(body.record_ids))
                        .values(excluded=body.excluded))
    db.commit()
    return {"updated": result.rowcount or 0}
