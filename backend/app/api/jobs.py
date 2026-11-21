"""Crawl jobs: create (idempotent, quota-checked), list, progress, events, URLs, cancel and retry."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db import get_db, utcnow
from app.deps import OrgContext, org_member
from app.errors import ApiError
from app.models import CrawlJob, CrawlJobEvent, DiscoveredUrl, ExtractedRecord, ExtractionSchema, JobCompany, UrlStatus
from app.models import JobState as S
from app.schemas import CompanyOut, EventOut, JobIn, JobOut, JobProgress, Page, UrlOut
from app.services.common import audit, check_job_quota, org_limits
from app.services.pipeline import settings_snapshot
from app.services.state_machine import TERMINAL, transition
from app.spec.models import validate_spec
from app.worker import tasks

from ._util import client_ip, get_in_org, paginate

router = APIRouter(prefix="/orgs/{org_id}", tags=["jobs"])


def _enqueue(job_id: uuid.UUID) -> None:
    tasks.run_job.delay(str(job_id))


@router.post("/jobs", response_model=JobOut, status_code=201)
def create_job(body: JobIn, request: Request, response: Response, ctx: OrgContext = Depends(org_member),
               db: Session = Depends(get_db),
               idempotency_key: str | None = Header(None, alias="Idempotency-Key", max_length=128)) -> JobOut:
    if idempotency_key:
        existing = db.execute(select(CrawlJob).where(CrawlJob.org_id == ctx.org.id,
                                                     CrawlJob.idempotency_key == idempotency_key)).scalar_one_or_none()
        if existing is not None:
            if existing.schema_id != body.schema_id:
                raise ApiError(409, "idempotency_conflict", "This Idempotency-Key was used for a different job")
            response.status_code = 200
            return JobOut.model_validate(existing)
    schema = get_in_org(db, ExtractionSchema, body.schema_id, ctx.org.id, "schema")
    try:
        spec = validate_spec(schema.spec, org_limits(ctx.org))
    except (ValidationError, ValueError) as exc:
        raise ApiError(422, "invalid_spec", f"The extraction specification is not valid: {exc}") from None
    check_job_quota(db, ctx.org, ctx.user, spec.crawl.max_pages)
    schema.status = "confirmed"  # starting a job confirms the schema; later edits create a new version
    job = CrawlJob(org_id=ctx.org.id, project_id=schema.project_id, schema_id=schema.id, created_by=ctx.user.id,
                   state=S.created, idempotency_key=idempotency_key, counters={},
                   settings={**settings_snapshot(), "max_pages": spec.crawl.max_pages,
                             "max_depth": spec.crawl.max_depth})
    db.add(job)
    db.flush()
    db.add(CrawlJobEvent(org_id=ctx.org.id, job_id=job.id, type="transition", to_state=S.created,
                         message="Job created"))
    audit(db, "job.create", org_id=ctx.org.id, actor_id=ctx.user.id, target_type="job", target_id=job.id,
          ip=client_ip(request))
    db.commit()
    _enqueue(job.id)
    db.refresh(job)
    return JobOut.model_validate(job)


@router.get("/jobs", response_model=Page[JobOut])
def list_jobs(ctx: OrgContext = Depends(org_member), db: Session = Depends(get_db),
              project_id: uuid.UUID | None = None, state: str | None = Query(None, max_length=32),
              limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)) -> Page[JobOut]:
    q = select(CrawlJob).where(CrawlJob.org_id == ctx.org.id)
    if project_id:
        q = q.where(CrawlJob.project_id == project_id)
    if state:
        q = q.where(CrawlJob.state == state)
    items, total = paginate(db, q.order_by(CrawlJob.created_at.desc()), limit, offset)
    return Page(items=[JobOut.model_validate(j) for j in items], total=total, limit=limit, offset=offset)


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: uuid.UUID, ctx: OrgContext = Depends(org_member), db: Session = Depends(get_db)) -> JobOut:
    return JobOut.model_validate(get_in_org(db, CrawlJob, job_id, ctx.org.id, "job"))


@router.get("/jobs/{job_id}/progress", response_model=JobProgress)
def progress(job_id: uuid.UUID, ctx: OrgContext = Depends(org_member), db: Session = Depends(get_db)) -> JobProgress:
    job = get_in_org(db, CrawlJob, job_id, ctx.org.id, "job")
    counts = dict(db.execute(select(ExtractedRecord.status, func.count()).where(
        ExtractedRecord.job_id == job.id).group_by(ExtractedRecord.status)).all())
    # Counted from when the run was created, so planning time is included and the clock never restarts
    # when crawling begins (started_at is only set then).
    start = job.created_at or job.started_at
    elapsed = None
    if start:
        end = job.finished_at if S(job.state) in TERMINAL and job.finished_at else utcnow()
        elapsed = max(0.0, (end - start).total_seconds())
    return JobProgress(id=job.id, state=job.state, counters=job.counters, records=sum(counts.values()),
                       valid_records=counts.get("valid", 0), elapsed_seconds=elapsed, error=job.error,
                       terminal=S(job.state) in TERMINAL)


@router.get("/jobs/{job_id}/events", response_model=list[EventOut])
def events(job_id: uuid.UUID, ctx: OrgContext = Depends(org_member), db: Session = Depends(get_db),
           after_id: int = Query(0, ge=0), limit: int = Query(200, ge=1, le=1000)) -> list[EventOut]:
    get_in_org(db, CrawlJob, job_id, ctx.org.id, "job")
    rows = db.execute(select(CrawlJobEvent).where(CrawlJobEvent.job_id == job_id, CrawlJobEvent.id > after_id,
                                                  CrawlJobEvent.type != "activity")
                      .order_by(CrawlJobEvent.id).limit(limit)).scalars().all()
    return [EventOut.model_validate(e) for e in rows]


@router.get("/jobs/{job_id}/activity", response_model=list[EventOut])
def activity(job_id: uuid.UUID, ctx: OrgContext = Depends(org_member), db: Session = Depends(get_db),
             after_id: int = Query(0, ge=0), limit: int = Query(300, ge=1, le=1000)) -> list[EventOut]:
    """The live feed: each thing the worker did, oldest first. With after_id=0, the latest `limit` lines;
    then poll with the last id seen to get only what is new."""
    get_in_org(db, CrawlJob, job_id, ctx.org.id, "job")
    q = select(CrawlJobEvent).where(CrawlJobEvent.job_id == job_id, CrawlJobEvent.type == "activity")
    if after_id:
        rows = db.execute(q.where(CrawlJobEvent.id > after_id).order_by(CrawlJobEvent.id).limit(limit)).scalars().all()
    else:
        rows = list(reversed(db.execute(q.order_by(CrawlJobEvent.id.desc()).limit(limit)).scalars().all()))
    return [EventOut.model_validate(e) for e in rows]


@router.get("/jobs/{job_id}/companies", response_model=Page[CompanyOut])
def companies(job_id: uuid.UUID, ctx: OrgContext = Depends(org_member), db: Session = Depends(get_db),
              status: str | None = Query(None, max_length=40), limit: int = Query(200, ge=1, le=1000),
              offset: int = Query(0, ge=0)) -> Page[CompanyOut]:
    """Every company the job came across, with its outcome and the reasons for it (filled when the job ends)."""
    get_in_org(db, CrawlJob, job_id, ctx.org.id, "job")
    q = select(JobCompany).where(JobCompany.job_id == job_id)
    if status:
        q = q.where(JobCompany.status == status)
    items, total = paginate(db, q.order_by(JobCompany.status, JobCompany.name), limit, offset)
    return Page(items=[CompanyOut.model_validate(c) for c in items], total=total, limit=limit, offset=offset)


@router.get("/jobs/{job_id}/urls", response_model=Page[UrlOut])
def urls(job_id: uuid.UUID, ctx: OrgContext = Depends(org_member), db: Session = Depends(get_db),
         status: str | None = Query(None, max_length=32), limit: int = Query(100, ge=1, le=500),
         offset: int = Query(0, ge=0)) -> Page[UrlOut]:
    get_in_org(db, CrawlJob, job_id, ctx.org.id, "job")
    q = select(DiscoveredUrl).where(DiscoveredUrl.job_id == job_id)
    if status:
        q = q.where(DiscoveredUrl.status == status)
    items, total = paginate(db, q.order_by(DiscoveredUrl.discovered_at, DiscoveredUrl.url), limit, offset)
    return Page(items=[UrlOut.model_validate(u) for u in items], total=total, limit=limit, offset=offset)


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
def cancel(job_id: uuid.UUID, request: Request, ctx: OrgContext = Depends(org_member),
           db: Session = Depends(get_db)) -> JobOut:
    job = get_in_org(db, CrawlJob, job_id, ctx.org.id, "job")
    state = S(job.state)
    if state in TERMINAL:
        raise ApiError(409, "job_finished", f"The job has already finished ({state.value})")
    if state != S.cancel_requested:
        # Not picked up by a worker yet: cancel at once. Otherwise the worker stops at its next check.
        dst = S.cancelled if state == S.created else S.cancel_requested
        if not transition(db, job, dst, "Cancellation requested by user"):
            raise ApiError(409, "job_changed", "The job changed state; try again")
    audit(db, "job.cancel", org_id=ctx.org.id, actor_id=ctx.user.id, target_type="job", target_id=job.id,
          ip=client_ip(request))
    db.commit()
    return JobOut.model_validate(job)


@router.post("/jobs/{job_id}/retry", response_model=JobOut)
def retry(job_id: uuid.UUID, request: Request, ctx: OrgContext = Depends(org_member),
          db: Session = Depends(get_db)) -> JobOut:
    """Resume a failed or cancelled job. Pages already fetched are kept; failed URLs get another try."""
    job = get_in_org(db, CrawlJob, job_id, ctx.org.id, "job")
    if S(job.state) not in (S.failed, S.cancelled):
        raise ApiError(409, "not_retryable", "Only failed or cancelled jobs can be retried")
    check_job_quota(db, ctx.org, ctx.user, int(job.settings.get("max_pages", 0)))
    db.execute(update(DiscoveredUrl).where(DiscoveredUrl.job_id == job.id,
                                           DiscoveredUrl.status.in_([UrlStatus.failed, UrlStatus.dead,
                                                                     UrlStatus.in_progress]))
               .values(status=UrlStatus.queued, attempts=0, lease_until=None))
    # A retried job is running again: its old finish time would make the elapsed time negative.
    if not transition(db, job, S.queued, "Retry requested by user", error=None, finished_at=None):
        raise ApiError(409, "job_changed", "The job changed state; try again")
    audit(db, "job.retry", org_id=ctx.org.id, actor_id=ctx.user.id, target_type="job", target_id=job.id,
          ip=client_ip(request))
    db.commit()
    _enqueue(job.id)
    db.refresh(job)
    return JobOut.model_validate(job)
