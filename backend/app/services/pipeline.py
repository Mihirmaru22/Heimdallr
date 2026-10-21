"""Runs a job end to end: validating -> planning -> queued -> running -> validating_results -> done.

Safe to call again for the same job (after a crash or a redelivered task): each step checks
the persisted state and continues from there.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy import func, select

from app.config import get_settings
from app.crawl.runner import CrawlRunner, JobCancelled
from app.db import session_scope
from app.discovery.providers import DiscoveryError
from app.models import CrawlJob, DiscoveredUrl, ExtractionSchema, Organization, UrlStatus
from app.models import JobState as S
from app.services.common import org_limits, record_usage
from app.services.finalize import finalize_job
from app.services.state_machine import log_event, transition
from app.spec.models import validate_spec

log = logging.getLogger("webdata.pipeline")


def _load(job_id: uuid.UUID):
    with session_scope(bypass=True) as db:
        job = db.get(CrawlJob, job_id)
        if job is None:
            return None, None, None
        org = db.get(Organization, job.org_id)
        schema = db.get(ExtractionSchema, job.schema_id)
        return job, org, schema


def _move(job_id: uuid.UUID, org_id: uuid.UUID, dst: S, message: str = "", **fields) -> CrawlJob | None:
    with session_scope(org_id) as db:
        job = db.get(CrawlJob, job_id)
        if job is None:
            return None
        if job.state == dst.value:
            return job
        if not transition(db, job, dst, message, **fields):
            return None
        return job


def _cancelled(job_id: uuid.UUID, org_id: uuid.UUID) -> None:
    with session_scope(org_id) as db:
        job = db.get(CrawlJob, job_id)
        if job and job.state == S.cancel_requested:
            transition(db, job, S.cancelled, "Cancelled by user")


async def _seed(r: CrawlRunner) -> int:
    try:
        return await r.seed()
    finally:
        await r.client.aclose()


def _seed_if_empty(job_id: uuid.UUID, org_id: uuid.UUID, runner) -> bool:
    """Discover starting URLs unless the job already has some. False if nothing is eligible (job failed)."""
    with session_scope(org_id) as db:
        already = db.execute(select(func.count()).select_from(DiscoveredUrl).where(
            DiscoveredUrl.job_id == job_id)).scalar_one()
    if already:
        return True
    added = asyncio.run(_seed(runner()))
    with session_scope(org_id) as db:
        eligible = db.execute(select(func.count()).select_from(DiscoveredUrl).where(
            DiscoveredUrl.job_id == job_id, DiscoveredUrl.status == UrlStatus.queued)).scalar_one()
        reasons = db.execute(select(DiscoveredUrl.url, DiscoveredUrl.status_reason).where(
            DiscoveredUrl.job_id == job_id).limit(5)).all()
    if eligible == 0:
        detail = "; ".join(f"{u}: {why}" for u, why in reasons) or "no starting URLs"
        _move(job_id, org_id, S.failed, f"No eligible starting pages ({detail})",
              error=f"No eligible starting pages. {detail}"[:2000])
        return False
    log.info("job %s seeded %s urls", job_id, added)
    return True


def run_job(job_id: uuid.UUID, *, resolver=None, redis=None, client_factory=None) -> str:
    job, org, schema = _load(job_id)
    if job is None or org is None or schema is None:
        return "missing"
    org_id = org.id
    limits = org_limits(org)
    state = S(job.state)
    if state in (S.completed, S.partially_completed, S.failed, S.cancelled):
        return state.value
    if state == S.cancel_requested:
        _cancelled(job_id, org_id)
        return S.cancelled.value
    try:
        spec = validate_spec(schema.spec, limits)
    except Exception as exc:  # noqa: BLE001 - the stored spec is re-validated before every run
        _move(job_id, org_id, S.failed, f"Invalid specification: {exc}", error=str(exc)[:2000])
        return S.failed.value

    def runner() -> CrawlRunner:
        client = client_factory() if client_factory else None
        return CrawlRunner(job_id, org_id, spec, resolver=resolver, redis=redis, client=client,
                           max_records=limits["max_records_per_job"])

    try:
        if state == S.created:
            _move(job_id, org_id, S.validating, "Validating the specification and URLs")
            state = S.validating
        if state == S.validating:
            _move(job_id, org_id, S.planning, "Discovering starting pages")
            state = S.planning
        if state == S.planning:
            if not _seed_if_empty(job_id, org_id, runner):
                return S.failed.value
            _move(job_id, org_id, S.queued, "Waiting for a worker")
            state = S.queued
        if state == S.queued:
            # A retried job that failed before discovery has nothing to crawl yet.
            if not _seed_if_empty(job_id, org_id, runner):
                return S.failed.value
            _move(job_id, org_id, S.running, "Crawling")
            state = S.running
        if state in (S.running, S.waiting_quota):
            r = runner()
            counters = asyncio.run(r.run())
            with session_scope(org_id) as db:
                job = db.get(CrawlJob, job_id)
                # Bill only pages fetched since the last time this job was billed (resumes, retries).
                billed = (job.counters or {}).get("pages_billed", 0)
                new_pages = max(0, counters.get("fetched", 0) - billed)
                if new_pages:
                    record_usage(db, org_id, "pages", new_pages, job_id=job_id)
                counters = {**counters, "pages_billed": billed + new_pages}
            _move(job_id, org_id, S.validating_results, "Validating and deduplicating results",
                  counters=counters)
            state = S.validating_results
        if state == S.validating_results:
            stats = finalize_job(job_id, org_id, spec, limits["max_records_per_job"])
            with session_scope(org_id) as db:
                job = db.get(CrawlJob, job_id)
                counters = {**(job.counters or {}), **{f"records_{k}": v for k, v in stats.items() if k != "records"},
                            "extracted": stats["records"]}
                failed_pages = counters.get("failed", 0)
                complete = stats["records"] > 0 and failed_pages == 0 and stats["invalid"] == 0
                if stats["records"] == 0:
                    transition(db, job, S.failed, "No records could be extracted", counters=counters,
                               error="No records could be extracted from the fetched pages")
                    return S.failed.value
                dst = S.completed if complete else S.partially_completed
                msg = (f"{stats['records']} records ({stats['valid']} complete, {stats['partial']} partial, "
                       f"{stats['invalid']} missing required fields); {failed_pages} page(s) failed")
                transition(db, job, dst, msg, counters=counters)
                return dst.value
    except JobCancelled:
        _cancelled(job_id, org_id)
        return S.cancelled.value
    except DiscoveryError as exc:
        _move(job_id, org_id, S.failed, f"Discovery failed: {exc}", error=str(exc)[:2000])
        return S.failed.value
    except Exception as exc:
        log.exception("job %s crashed", job_id)
        with session_scope(org_id) as db:
            log_event(db, org_id, job_id, "error", f"Unexpected error: {type(exc).__name__}")
        _move(job_id, org_id, S.failed, "Unexpected error; see events", error=type(exc).__name__)
        return S.failed.value
    return state.value


def settings_snapshot() -> dict:
    s = get_settings()
    return {"respect_robots": s.respect_robots, "per_domain_delay_seconds": s.per_domain_delay_seconds,
            "per_domain_concurrency": s.per_domain_concurrency, "user_agent": s.user_agent,
            "max_page_bytes": s.max_page_bytes}
