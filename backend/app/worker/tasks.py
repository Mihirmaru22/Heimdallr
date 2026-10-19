"""Celery tasks. Each one is idempotent: running it twice for the same id is harmless."""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from sqlalchemy import delete, select, update

from app.config import get_settings
from app.db import session_scope, utcnow
from app.models import CrawlJob, DiscoveredUrl, Export, Organization, UrlStatus
from app.models import JobState as S
from app.services import exports, pipeline
from app.worker.celery_app import celery

log = logging.getLogger("webdata.tasks")


@celery.task(name="app.worker.tasks.run_job", max_retries=0)
def run_job(job_id: str) -> str:
    return pipeline.run_job(uuid.UUID(job_id), redis="auto")


@celery.task(name="app.worker.tasks.build_export", autoretry_for=(OSError,), max_retries=2,
             retry_backoff=True)
def build_export(export_id: str) -> str:
    return exports.build(uuid.UUID(export_id))


@celery.task(name="app.worker.tasks.sweep_stuck_jobs")
def sweep_stuck_jobs() -> int:
    """Re-queue running jobs whose worker stopped sending heartbeats; release stale URL leases."""
    stale = utcnow() - timedelta(minutes=10)
    requeued = 0
    with session_scope(bypass=True) as db:
        db.execute(update(DiscoveredUrl).where(DiscoveredUrl.status == UrlStatus.in_progress,
                                               DiscoveredUrl.lease_until < utcnow())
                   .values(status=UrlStatus.queued))
        jobs = db.execute(select(CrawlJob.id).where(
            CrawlJob.state.in_([S.running.value, S.queued.value, S.planning.value, S.validating_results.value]),
            (CrawlJob.heartbeat_at < stale) | (CrawlJob.heartbeat_at.is_(None) & (CrawlJob.updated_at < stale)),
        )).scalars().all()
    for job_id in jobs:
        run_job.delay(str(job_id))
        requeued += 1
    return requeued


@celery.task(name="app.worker.tasks.retention_cleanup")
def retention_cleanup() -> dict[str, int]:
    s = get_settings()
    removed = {"exports": 0, "jobs": 0}
    with session_scope(bypass=True) as db:
        for exp in db.execute(select(Export).where(Export.expires_at < utcnow())).scalars():
            exports.delete_file(exp)
            db.delete(exp)
            removed["exports"] += 1
        for org in db.execute(select(Organization)).scalars():
            days = org.retention_days or s.retention_days
            old = select(CrawlJob.id).where(
                CrawlJob.org_id == org.id, CrawlJob.created_at < utcnow() - timedelta(days=days),
                CrawlJob.state.in_([S.completed.value, S.partially_completed.value, S.failed.value,
                                    S.cancelled.value]))
            # Export files are on disk, not in the database, so they are removed before the rows cascade.
            for exp in db.execute(select(Export).where(Export.job_id.in_(old))).scalars():
                exports.delete_file(exp)
            result = db.execute(delete(CrawlJob).where(CrawlJob.id.in_(old)))
            removed["jobs"] += result.rowcount or 0
    return removed
