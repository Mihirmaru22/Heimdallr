"""Excel exports: request, poll, and download through a short-lived signed link."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db, utcnow
from app.deps import OrgContext, org_member
from app.errors import ApiError, not_found
from app.models import CrawlJob, Export, Project
from app.models import JobState as S
from app.schemas import ExportIn, ExportOut
from app.security import sign_download, verify_download
from app.services.common import audit
from app.worker import tasks

from ._util import client_ip, get_in_org

router = APIRouter(prefix="/orgs/{org_id}", tags=["exports"])
EXPORTABLE = {S.completed, S.partially_completed}


def _out(org_id: uuid.UUID, exp: Export, user_id: uuid.UUID) -> ExportOut:
    out = ExportOut.model_validate(exp)
    if exp.status == "ready":
        out.download_url = (f"/api/v1/orgs/{org_id}/exports/{exp.id}/download"
                            f"?token={sign_download(exp.id, user_id)}")
    return out


@router.post("/jobs/{job_id}/exports", response_model=ExportOut, status_code=202)
def create_export(job_id: uuid.UUID, body: ExportIn, request: Request, ctx: OrgContext = Depends(org_member),
                  db: Session = Depends(get_db)) -> ExportOut:
    job = get_in_org(db, CrawlJob, job_id, ctx.org.id, "job")
    if S(job.state) not in EXPORTABLE:
        raise ApiError(409, "job_not_finished", "Export is available once the job has completed")
    exp = Export(org_id=ctx.org.id, job_id=job.id, requested_by=ctx.user.id, status="pending",
                 options=body.model_dump(mode="json"))
    db.add(exp)
    audit(db, "export.create", org_id=ctx.org.id, actor_id=ctx.user.id, target_type="job", target_id=job.id,
          ip=client_ip(request))
    db.commit()
    tasks.build_export.delay(str(exp.id))
    db.refresh(exp)
    return _out(ctx.org.id, exp, ctx.user.id)


@router.get("/jobs/{job_id}/exports", response_model=list[ExportOut])
def list_exports(job_id: uuid.UUID, ctx: OrgContext = Depends(org_member),
                 db: Session = Depends(get_db)) -> list[ExportOut]:
    get_in_org(db, CrawlJob, job_id, ctx.org.id, "job")
    rows = db.execute(select(Export).where(Export.job_id == job_id, Export.org_id == ctx.org.id)
                      .order_by(Export.created_at.desc())).scalars().all()
    return [_out(ctx.org.id, e, ctx.user.id) for e in rows]


@router.get("/exports/{export_id}", response_model=ExportOut)
def get_export(export_id: uuid.UUID, ctx: OrgContext = Depends(org_member),
               db: Session = Depends(get_db)) -> ExportOut:
    return _out(ctx.org.id, get_in_org(db, Export, export_id, ctx.org.id, "export"), ctx.user.id)


@router.get("/exports/{export_id}/download")
def download(export_id: uuid.UUID, token: str = Query(..., max_length=200), ctx: OrgContext = Depends(org_member),
             db: Session = Depends(get_db)) -> FileResponse:
    """Needs the session cookie AND a link signed for this user and export, so a leaked link alone is useless."""
    exp = get_in_org(db, Export, export_id, ctx.org.id, "export")
    if not verify_download(token, exp.id, ctx.user.id):
        raise ApiError(403, "link_expired", "This download link is invalid or has expired; request a new one")
    if exp.status != "ready" or not exp.file_path:
        raise not_found("export file")
    if exp.expires_at and exp.expires_at < utcnow():
        raise ApiError(410, "export_expired", "This export has expired; create a new one")
    path = Path(exp.file_path)
    if not path.is_file():
        raise not_found("export file")
    project = db.get(Project, db.get(CrawlJob, exp.job_id).project_id)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", project.name if project else "export").strip("_")[:60] or "export"
    audit(db, "export.download", org_id=ctx.org.id, actor_id=ctx.user.id, target_type="export", target_id=exp.id)
    db.commit()
    return FileResponse(path, filename=f"{stem}-{exp.created_at:%Y%m%d-%H%M}.xlsx",
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
