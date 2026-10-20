from celery import Celery

from app.config import get_settings

settings = get_settings()
celery = Celery("webdata", broker=settings.redis_url, backend=None, include=["app.worker.tasks"])
celery.conf.update(
    task_acks_late=True,  # a task lost with its worker is redelivered; tasks are idempotent
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_always_eager=settings.celery_eager,
    task_eager_propagates=False,
    broker_connection_retry_on_startup=True,
    task_default_queue="webdata",
    beat_schedule={
        "sweep-stuck-jobs": {"task": "app.worker.tasks.sweep_stuck_jobs", "schedule": 120.0},
        "retention-cleanup": {"task": "app.worker.tasks.retention_cleanup", "schedule": 6 * 3600.0},
        "refresh-sec-index": {"task": "app.worker.tasks.refresh_sec_index", "schedule": 24 * 3600.0},
    },
)
