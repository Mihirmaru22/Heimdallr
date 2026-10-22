"""Export generation and storage. Files live under data_dir/exports/<org_id>/ and expire."""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from app.config import get_settings
from app.db import session_scope, utcnow
from app.export.xlsx import ExportOptions, ExportRecord, build_workbook
from app.models import CrawlJob, CrawlJobEvent, Evidence, Export, ExtractedRecord, ExtractionSchema, FieldValue, Project
from app.services.common import org_limits, record_usage
from app.spec.models import ExtractionSpec

log = logging.getLogger("webdata.exports")


def export_path(org_id: uuid.UUID, export_id: uuid.UUID) -> Path:
    base = Path(get_settings().data_dir).resolve() / "exports" / str(org_id)
    return base / f"{export_id}.xlsx"


def delete_file(export: Export) -> None:
    if export.file_path:
        path = Path(export.file_path)
        base = (Path(get_settings().data_dir).resolve() / "exports").resolve()
        if path.resolve().is_relative_to(base):
            path.unlink(missing_ok=True)


def _records(db, export: Export, spec: ExtractionSpec, max_rows: int) -> list[ExportRecord]:
    opts = export.options
    q = select(ExtractedRecord).where(ExtractedRecord.job_id == export.job_id)
    if not opts.get("include_excluded"):
        q = q.where(ExtractedRecord.excluded.is_(False))
    if opts.get("statuses"):
        q = q.where(ExtractedRecord.status.in_(opts["statuses"]))
    if opts.get("record_ids"):
        q = q.where(ExtractedRecord.id.in_([uuid.UUID(r) for r in opts["record_ids"]]))
    rows = db.execute(q.order_by(ExtractedRecord.created_at).limit(max_rows)).scalars().all()
    ids = [r.id for r in rows]
    fvs: dict[uuid.UUID, list[dict]] = {i: [] for i in ids}
    if ids:
        for fv in db.execute(select(FieldValue).where(FieldValue.record_id.in_(ids),
                                                      FieldValue.selected.is_(True))).scalars():
            fvs[fv.record_id].append({"field_name": fv.field_name, "value": fv.value,
                                      "value_status": fv.value_status, "method": fv.method,
                                      "source_url": fv.source_url, "evidence": fv.evidence,
                                      "confidence": fv.confidence, "error": fv.error})
    return [ExportRecord(str(r.id), r.data, r.status, r.quality_score, r.source_urls, fvs[r.id]) for r in rows]


def _evidence(db, job_id: uuid.UUID) -> list[dict]:
    rows = db.execute(select(Evidence).where(Evidence.job_id == job_id)
                      .order_by(Evidence.kept.desc(), Evidence.strength.desc(), Evidence.company)).scalars().all()
    return [{c.name: getattr(e, c.name) for c in Evidence.__table__.columns} for e in rows]


def build(export_id: uuid.UUID) -> str:
    with session_scope(bypass=True) as db:
        export = db.get(Export, export_id)
        if export is None:
            return "missing"
        org_id = export.org_id
    if export.status == "ready":
        return "ready"
    try:
        with session_scope(org_id) as db:
            export = db.get(Export, export_id)
            job = db.get(CrawlJob, export.job_id)
            schema = db.get(ExtractionSchema, job.schema_id)
            project = db.get(Project, job.project_id)
            from app.models import Organization

            org = db.get(Organization, org_id)
            spec = ExtractionSpec.model_validate(schema.spec)
            max_rows = org_limits(org)["max_export_rows"]
            records = _records(db, export, spec, max_rows)
            evidence = _evidence(db, export.job_id)
            problems = db.execute(select(CrawlJobEvent.message).where(
                CrawlJobEvent.job_id == export.job_id, CrawlJobEvent.type == "warning",
                CrawlJobEvent.message.startswith("Discovery problem: "),
            ).order_by(CrawlJobEvent.created_at)).scalars().all()
            summary = {
                "Project": project.name,
                "Request": schema.nl_request or spec.title,
                "Job ID": str(job.id),
                "Job state": job.state,
                "Created": job.created_at,
                "Started": job.started_at,
                "Finished": job.finished_at,
                "Exported at": utcnow(),
                "Rows exported": len(records),
                "Records valid / partial / invalid": " / ".join(
                    str(job.counters.get(f"records_{k}", 0)) for k in ("valid", "partial", "invalid")),
                "Duplicates removed": job.counters.get("records_duplicates", 0),
                "Pages discovered": job.counters.get("discovered", 0),
                "Pages fetched": job.counters.get("fetched", 0),
                "Pages skipped": job.counters.get("skipped", 0),
                "Pages blocked (robots or policy)": job.counters.get("blocked", 0),
                "Pages failed": job.counters.get("failed", 0),
                "Fields": ", ".join(f.name for f in spec.fields),
                "Deduplication keys": ", ".join(spec.deduplication_keys) or "(per site)",
                "Max pages / depth": f"{spec.crawl.max_pages} / {spec.crawl.max_depth}",
                "Extraction": "deterministic (no LLM)",
                **({"Proof": f"{sum(e['kept'] for e in evidence)} kept (Evidence sheet), "
                             f"{sum(not e['kept'] for e in evidence)} rejected with the reason (Rejected sheet). "
                             "Quotes are copied word for word from the linked document."}
                   if evidence else {}),
                **{f"Source problem {i}": m.removeprefix("Discovery problem: ") for i, m in enumerate(problems, 1)},
                "Note": "robots.txt was respected; that alone does not make reuse of this data lawful.",
            }
            options = ExportOptions(
                include_metadata=export.options.get("include_metadata", True),
                include_sources=export.options.get("include_sources", True),
                include_issues=export.options.get("include_issues", True),
                columns=export.options.get("columns"),
                data_sheet_name=export.options.get("data_sheet_name") or "Data",
            )
        path = export_path(org_id, export_id)
        result = build_workbook(path, spec, records, summary, options, evidence)
        with session_scope(org_id) as db:
            export = db.get(Export, export_id)
            export.status = "ready"
            export.row_count = result.rows
            export.file_bytes = result.bytes
            export.sha256 = result.sha256
            export.file_path = str(result.path)
            export.expires_at = utcnow() + timedelta(hours=get_settings().export_ttl_hours)
            record_usage(db, org_id, "export_rows", result.rows, user_id=export.requested_by, job_id=export.job_id)
        return "ready"
    except Exception as exc:
        log.exception("export %s failed", export_id)
        with session_scope(org_id) as db:
            export = db.get(Export, export_id)
            export.status = "failed"
            export.error = f"{type(exc).__name__}: {str(exc)[:500]}"
        return "failed"
