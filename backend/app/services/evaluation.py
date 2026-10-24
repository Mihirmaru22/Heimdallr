"""The test questions as a benchmark: every run of each question scored against its answer key, and new runs
started without anyone retyping the questions.

- history: all finished runs of every key's question, oldest first, each with the code version it ran on,
  so whether the work improved is read from the runs themselves;
- start_runs: one new run per question with the plan of its latest run (the same plan, so only the code
  differs between the two), which `app.cli eval-run` waits for and scores next to the previous run.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from app.models import CrawlJob, CrawlJobEvent, ExtractionSchema
from app.models import JobState as S
from app.services.scorecard import score_job

KEYS_DIR = Path(__file__).resolve().parents[2] / "eval" / "keys"
API_LOG = Path(__file__).resolve().parents[2] / "var" / "logs" / "api.log"
# start.sh writes one line per start: "===== start.sh run 2026-10-22 16:56:06 +0530 <branch> <commit> - <subject> ====="
MARKER = re.compile(r"===== start\.sh run (\S+ \S+ [+-]\d{4}) \S+ ([0-9a-f]{6,40}) - ")
FINISHED = (S.completed, S.partially_completed)
COLUMNS = ("key: must-have companies found", "key: rows that must not be there", "key: website correct",
           "included: email or phone", "records included", "time (s)")


def load_keys(keys_dir: Path = KEYS_DIR) -> dict[str, dict[str, Any]]:
    import json

    return {p.stem: json.loads(p.read_text()) for p in sorted(keys_dir.glob("*.json"))}


def _same_question(a: str | None, b: str) -> bool:
    def norm(s: str) -> str:
        return " ".join(re.findall(r"[a-z0-9/]+", (s or "").lower()))

    return norm(a) == norm(b)


def runs_of(db, question: str) -> list[CrawlJob]:
    """Finished runs of this question, oldest first."""
    rows = db.execute(select(CrawlJob, ExtractionSchema.nl_request).join(
        ExtractionSchema, ExtractionSchema.id == CrawlJob.schema_id).where(CrawlJob.state.in_(FINISHED))
        .order_by(CrawlJob.created_at)).all()
    return [job for job, asked in rows if _same_question(asked, question)]


def code_starts(log: Path | None = None) -> list[tuple[datetime, str]]:
    """(when the stack started, commit) from start.sh's markers, oldest first."""
    log = log or API_LOG
    if not log.is_file():
        return []
    out = []
    for m in MARKER.finditer(log.read_text(errors="replace")):
        out.append((datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S %z").astimezone(UTC), m.group(2)[:7]))
    return sorted(out)


def code_of(job: CrawlJob, starts: list[tuple[datetime, str]]) -> str:
    recorded = (job.settings or {}).get("code_version")
    if recorded:
        return recorded
    created = job.created_at if job.created_at.tzinfo else job.created_at.replace(tzinfo=UTC)
    before = [commit for at, commit in starts if at <= created]
    return before[-1] if before else "?"


def history(db, keys: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    """One row per finished run of every key's question."""
    starts = code_starts()
    rows = []
    for name, key in keys.items():
        for job in runs_of(db, key["question"]):
            card = score_job(db, job.id, key)
            rows.append({"question": name, "job": str(job.id)[:8], "created": f"{job.created_at:%m-%d %H:%M}",
                         "code": code_of(job, starts), **{c: card.get(c, "") for c in COLUMNS}})
    return rows


def found(value: str) -> tuple[int, int]:
    """"12/15 (80%)" -> (12, 15)."""
    m = re.match(r"(\d+)/(\d+)", value or "")
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def with_current_sources(db, schema: ExtractionSchema) -> ExtractionSchema:
    """The same plan with the sources today's planner rules pick for its filters, so a new source is measured
    without the planner's model reading the question again (which can change the fields and filters too)."""
    from app.spec.models import ExtractionSpec
    from app.spec.planner import choose_providers

    spec = ExtractionSpec.model_validate(schema.spec)
    if spec.crawl.start_urls:
        return schema
    d = spec.discovery
    providers = choose_providers(d, bool(d.technology and spec.record_scope == "site"))
    if providers == d.providers:
        return schema
    d.providers = providers
    version = (db.execute(select(func.max(ExtractionSchema.version)).where(
        ExtractionSchema.project_id == schema.project_id)).scalar() or 0) + 1
    new = ExtractionSchema(org_id=schema.org_id, project_id=schema.project_id, version=version,
                           nl_request=schema.nl_request, spec=spec.model_dump(mode="json"), status="confirmed",
                           interpreter=f"benchmark: sources of v{schema.version} refreshed")
    db.add(new)
    db.flush()
    return new


def plan_run(db, runs: list[CrawlJob]) -> CrawlJob | None:
    """The run whose plan a new benchmark run copies: the latest run asking for the most companies. A small
    capped job run to check the system is up (10 companies instead of 50) must not become the benchmark plan,
    which it did once and made a whole question's score meaningless."""
    def asked(job: CrawlJob) -> int:
        schema = db.get(ExtractionSchema, job.schema_id)
        return int(((schema.spec or {}).get("discovery") or {}).get("max_results") or 0) if schema else 0

    most = max((asked(j) for j in runs), default=0)
    return next((j for j in reversed(runs) if asked(j) == most), None)


def start_runs(db, keys: dict[str, dict[str, Any]], refresh_sources: bool = False
               ) -> list[tuple[str, CrawlJob | None, CrawlJob]]:
    """A new run of each question with its latest run's plan: (key name, previous run, new run)."""
    from app.services.pipeline import settings_snapshot

    out = []
    for name, key in keys.items():
        previous = plan_run(db, runs_of(db, key["question"]))
        if previous is None:
            continue  # never asked yet: run it once from the app so it has a plan
        snap = settings_snapshot()
        schema = db.get(ExtractionSchema, previous.schema_id)
        if refresh_sources:
            schema = with_current_sources(db, schema)
        crawl = (schema.spec or {}).get("crawl") or {}
        job = CrawlJob(org_id=previous.org_id, project_id=previous.project_id, schema_id=schema.id,
                       created_by=previous.created_by, state=S.created, counters={},
                       settings={**snap, "max_pages": crawl.get("max_pages"), "max_depth": crawl.get("max_depth"),
                                 "eval_of": str(previous.id)})
        db.add(job)
        db.flush()
        db.add(CrawlJobEvent(org_id=job.org_id, job_id=job.id, type="transition", to_state=S.created,
                             message=f"Benchmark run of {name}, same plan as {str(previous.id)[:8]}"))
        out.append((name, previous, job))
    return out


def unfinished(db, job_ids: list[uuid.UUID]) -> int:
    return db.execute(select(func.count()).select_from(CrawlJob).where(
        CrawlJob.id.in_(job_ids), CrawlJob.state.not_in((*FINISHED, S.failed, S.cancelled)))).scalar_one()


def starts_of(db, job_id: uuid.UUID) -> int:
    """How many times a worker began this job's discovery. More than one means a duplicate task ran it, so the
    run's score measures the duplicate, not the code."""
    return db.execute(select(func.count()).select_from(CrawlJobEvent).where(
        CrawlJobEvent.job_id == job_id, CrawlJobEvent.type == "transition",
        CrawlJobEvent.to_state == S.planning.value)).scalar_one()
