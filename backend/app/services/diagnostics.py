"""What a run planned and what really happened, for the export's Diagnostics sheet and `app.cli job-report`.

Everything here is read back from what the run stored (its plan, events, live feed, pages and proof), so a run
can be measured after the fact on any machine: the plan, each source's answer or failure, where pages went,
and why pages were skipped.
"""

from __future__ import annotations

import uuid
from collections import Counter
from typing import Any

from sqlalchemy import func, select

from app.models import CrawlJob, CrawlJobEvent, DiscoveredUrl, Evidence, ExtractionSchema

PLAN_KEYS = ("providers", "technology", "technology_aliases", "industry", "keywords", "countries", "region",
             "max_results", "evidence_years")
SOURCE_KINDS = ("search", "kept", "dropped", "failed")
TOP_SITES = 40


def run_diagnostics(db, job_id: uuid.UUID) -> list[tuple[str, str, str]]:
    """(section, item, value) rows, in reading order."""
    job = db.get(CrawlJob, job_id)
    schema = db.get(ExtractionSchema, job.schema_id)
    spec: dict[str, Any] = schema.spec or {}
    d = spec.get("discovery") or {}
    crawl = spec.get("crawl") or {}
    rows: list[tuple[str, str, str]] = [("Plan", "Question", schema.nl_request or spec.get("title") or "")]
    rows += [("Plan", k, _show(d.get(k))) for k in PLAN_KEYS]
    rows += [("Plan", k, _show(crawl.get(k))) for k in ("max_pages", "max_pages_per_site", "max_depth")]
    rows += [("Plan", "record_scope", _show(spec.get("record_scope"))),
             ("Plan", "fields", ", ".join(f["name"] for f in spec.get("fields", [])))]

    events = db.execute(select(CrawlJobEvent).where(CrawlJobEvent.job_id == job_id)
                        .order_by(CrawlJobEvent.created_at, CrawlJobEvent.id)).scalars().all()
    start = next((e.created_at for e in events), None)

    def at(e: CrawlJobEvent) -> str:
        return f"+{(e.created_at - start).total_seconds():.0f}s" if start else ""

    for e in events:
        if e.type == "transition":
            rows.append(("Timeline", at(e), f"{e.from_state or ''} -> {e.to_state or ''} {e.message}".strip()))
        elif e.type in ("warning", "error", "info"):
            rows.append(("Notes", f"{at(e)} {e.type}", e.message))
    for e in events:
        data = e.data or {}
        source = data.get("source")
        if e.type == "activity" and source and data.get("kind") in SOURCE_KINDS:
            rows.append((f"Source: {source}", f"{at(e)} {data.get('kind')}", e.message))

    proof = db.execute(select(Evidence.source_type, Evidence.kept, func.count()).where(Evidence.job_id == job_id)
                       .group_by(Evidence.source_type, Evidence.kept)).all()
    for source_type, kept, n in sorted(proof, key=lambda r: (str(r[0]), not r[1])):
        rows.append(("Proof", f"{source_type or 'unknown'} {'kept' if kept else 'rejected'}", str(n)))

    urls = db.execute(select(DiscoveredUrl.host, DiscoveredUrl.method, DiscoveredUrl.status,
                             DiscoveredUrl.status_reason).where(DiscoveredUrl.job_id == job_id)).all()
    by_method = Counter(m for _h, m, _s, _r in urls)
    rows += [("Pages", f"found by {m}", str(n)) for m, n in by_method.most_common()]
    rows += [("Pages", f"status {s}", str(n)) for s, n in Counter(s for _h, _m, s, _r in urls).most_common()]
    reasons = Counter(_reason(r) for _h, _m, s, r in urls if r and s != "fetched")
    rows += [("Why not read", reason, str(n)) for reason, n in reasons.most_common(15)]
    per_site: dict[str, Counter] = {}
    for host, _m, status, _r in urls:
        per_site.setdefault(host, Counter())[status] += 1
    ranked = sorted(per_site.items(), key=lambda kv: -sum(kv[1].values()))[:TOP_SITES]
    rows += [("Pages per site", host, ", ".join(f"{s} {n}" for s, n in c.most_common())) for host, c in ranked]
    return rows


def _show(value: Any) -> str:
    if value is None or value == [] or value == "":
        return "(none)"
    return ", ".join(map(str, value)) if isinstance(value, list) else str(value)


def _reason(reason: str) -> str:
    """Reasons grouped by kind: "robots.txt disallows https://x/y" -> "robots.txt disallows"."""
    return reason.split(" http")[0].split(": ")[0][:120]
