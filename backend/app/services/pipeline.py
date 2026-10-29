"""Runs a job end to end: validating -> planning -> queued -> running -> validating_results -> done.

Safe to call again for the same job (after a crash or a redelivered task): each step checks
the persisted state and continues from there.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import logging
import threading
import uuid
from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, select, update

from app.config import get_settings
from app.crawl.runner import CrawlRunner, JobCancelled
from app.db import session_scope, utcnow
from app.discovery.providers import DiscoveryError
from app.models import CrawlJob, DiscoveredUrl, ExtractionSchema, Organization, UrlStatus
from app.models import JobState as S
from app.services.common import org_limits, record_usage
from app.services.companies import build_companies
from app.services.finalize import finalize_job
from app.services.state_machine import log_event, transition
from app.spec.models import validate_spec

log = logging.getLogger("webdata.pipeline")


HEARTBEAT_EVERY = 20.0  # seconds between proofs of life while a worker holds a job
HEARTBEAT_FRESH = timedelta(seconds=90)  # a younger heartbeat means a worker still has the job


@contextlib.contextmanager
def _beating(job_id: uuid.UUID, org_id: uuid.UUID, every: float = HEARTBEAT_EVERY):
    """Writes the job's heartbeat for as long as this worker holds it, whichever step it is in. Discovery used
    to run for about fifteen minutes without one, so the stuck-job sweep re-queued the job and a second worker
    task ran it alongside the first."""
    stop = threading.Event()

    def beat() -> None:
        while True:
            try:
                with session_scope(org_id) as db:
                    db.execute(update(CrawlJob).where(CrawlJob.id == job_id).values(heartbeat_at=utcnow()))
            except Exception:  # noqa: BLE001 - a missed beat must never stop the job
                log.warning("could not write the heartbeat of job %s", job_id)
            if stop.wait(every):
                return

    thread = threading.Thread(target=beat, name=f"heartbeat-{job_id}", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=5)


def _held_elsewhere(job: CrawlJob) -> bool:
    """Another worker task is working on this job right now (it wrote a heartbeat moments ago)."""
    return (job.state in (S.validating.value, S.planning.value, S.queued.value, S.running.value,
                          S.waiting_quota.value, S.validating_results.value)
            and job.heartbeat_at is not None and utcnow() - job.heartbeat_at < HEARTBEAT_FRESH)


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
        if job.state == S.cancel_requested.value and dst != S.cancelled:
            # The person cancelled while this step ran: the job ends cancelled, whatever the step was moving to.
            if dst == S.failed:
                transition(db, job, S.cancelled, "Cancelled by user")
                return job
            raise JobCancelled()
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
    if _held_elsewhere(job):
        log.warning("job %s is already being worked on; this duplicate delivery does nothing", job_id)
        return "running_elsewhere"
    from app.llm.openrouter import JOB

    token = JOB.set(str(job_id))  # every model call made for this job is counted under it, by step
    try:
        with _beating(job_id, org.id):
            return _run(job_id, job, org, schema, resolver, redis, client_factory)
    finally:
        JOB.reset(token)
        _keep_model_calls(job_id, org.id, schema.id)


def _keep_model_calls(job_id: uuid.UUID, org_id: uuid.UUID, schema_id: uuid.UUID) -> None:
    """The job's model calls per step (answered and failed), stored with the job, and its plan's calls: the report
    reads them from the job, not from Redis, which keeps them only for a while."""
    from app.llm.openrouter import State

    try:
        state = State()
        calls, plan = state.calls(str(job_id)), state.calls(f"schema:{schema_id}")
    except Exception:  # noqa: BLE001 - counts are a report, never a reason to fail the job
        log.warning("could not read the model call counts of job %s", job_id)
        return
    with session_scope(org_id) as db:
        job = db.get(CrawlJob, job_id)
        if job is not None:
            # Flat integer counters ("model_calls.proof_read.answered"), like every other counter of a job.
            flat = {f"{scope}.{step}.{outcome}": n for scope, counts in (("model_calls", calls),
                                                                          ("plan_model_calls", plan))
                    for step, c in counts.items() for outcome, n in c.items()}
            job.counters = {**{k: v for k, v in (job.counters or {}).items() if not k.startswith(
                ("model_calls.", "plan_model_calls."))}, **flat, "model_calls_kept": 1}


def _run(job_id: uuid.UUID, job: CrawlJob, org: Organization, schema: ExtractionSchema, resolver, redis,
         client_factory) -> str:
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
            # Every company the job came across gets one decision, made here from all its facts.
            outcomes = build_companies(job_id, org_id, spec)
            with session_scope(org_id) as db:
                job = db.get(CrawlJob, job_id)
                counters = {**(job.counters or {}), **{f"records_{k}": v for k, v in stats.items() if k != "records"},
                            "extracted": stats["records"],
                            **{f"companies_{k.replace(' ', '_')}": v for k, v in outcomes.items()}}
                failed_pages = counters.get("failed", 0)
                complete = stats["records"] > 0 and failed_pages == 0 and stats["invalid"] == 0
                if stats["records"] == 0 and not outcomes:
                    transition(db, job, S.failed, "No records could be extracted", counters=counters,
                               error="No records could be extracted from the fetched pages")
                    return S.failed.value
                dst = S.completed if complete else S.partially_completed
                found = ", ".join(f"{n} {k}" for k, n in sorted(outcomes.items(), key=lambda kv: -kv[1]))
                msg = (f"{outcomes.get('delivered', 0) if spec.discovery.technology else stats['records']} "
                       f"delivered; companies: {found or 'none'}; {stats['records']} records "
                       f"({stats['valid']} complete, {stats['partial']} partial); {failed_pages} page(s) failed")
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


@functools.lru_cache(maxsize=1)
def code_version() -> str | None:
    """The commit this process runs, so every job records the code it was measured on."""
    import subprocess

    try:
        out = subprocess.run(["git", "rev-parse", "--short=7", "HEAD"],  # noqa: S607 - fixed arguments
                             cwd=Path(__file__).resolve().parent, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return (out.stdout.strip() or None) if out.returncode == 0 else None


def settings_snapshot() -> dict:
    s = get_settings()
    return {"code_version": code_version(),
            "respect_robots": s.respect_robots, "per_domain_delay_seconds": s.per_domain_delay_seconds,
            "per_domain_concurrency": s.per_domain_concurrency, "user_agent": s.user_agent,
            "max_page_bytes": s.max_page_bytes}
