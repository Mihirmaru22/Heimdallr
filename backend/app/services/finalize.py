"""Build validated, deduplicated records from the candidates stored on fetched pages."""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import delete, select

from app.crawl.urlnorm import registered_domain
from app.db import session_scope, utcnow
from app.extract.deterministic import Candidate
from app.extract.records import PageCandidates, assemble_record, dedupe_key
from app.models import ExtractedRecord, FetchedPage, FieldValue
from app.spec.models import ExtractionSpec

# A technology question keeps only companies whose proof says they use it; a mere mention stays visible in the
# table, marked excluded, so the person can include it by hand.
USES = {"Confirmed", "Likely"}


def _page_candidates(page: FetchedPage) -> PageCandidates:
    cands = {
        name: [Candidate(c.get("value"), c.get("method", "?"), float(c.get("confidence", 0.5)), c.get("evidence", ""))
               for c in items]
        for name, items in (page.candidates or {}).items()
    }
    return PageCandidates(page.id, page.final_url, cands)


def finalize_job(job_id: uuid.UUID, org_id: uuid.UUID, spec: ExtractionSpec, max_records: int) -> dict[str, int]:
    """Idempotent: re-running replaces records the user has not edited."""
    with session_scope(org_id) as db:
        pages = db.execute(select(FetchedPage).where(FetchedPage.job_id == job_id)
                           .order_by(FetchedPage.fetched_at)).scalars().all()
        groups: dict[str, list[FetchedPage]] = defaultdict(list)
        for p in pages:
            key = registered_domain(p.final_url) if spec.record_scope == "site" else p.final_url
            groups[key].append(p)

        existing = {r.dedupe_key: r for r in db.execute(
            select(ExtractedRecord).where(ExtractedRecord.job_id == job_id)).scalars().all()}
        seen_keys: set[str] = set()
        stats = {"records": 0, "valid": 0, "partial": 0, "invalid": 0, "duplicates": 0}
        for group_key, group_pages in groups.items():
            if stats["records"] >= max_records:
                break
            assembled = assemble_record(spec, [_page_candidates(p) for p in group_pages])
            key = dedupe_key(spec, assembled.data, group_key)
            if key in seen_keys:
                stats["duplicates"] += 1
                continue
            seen_keys.add(key)
            record = existing.get(key)
            if record is not None and record.user_edited:
                stats["records"] += 1
                stats[record.status] = stats.get(record.status, 0) + 1
                continue
            if record is None:
                record = ExtractedRecord(org_id=org_id, job_id=job_id, dedupe_key=key)
                db.add(record)
            record.data = assembled.data
            record.status = assembled.status
            if spec.discovery.technology and "uses_technology" in {f.name for f in spec.fields}:
                record.excluded = assembled.data.get("uses_technology") not in USES
            record.quality_score = assembled.quality
            record.source_urls = assembled.source_urls or [p.final_url for p in group_pages[:5]]
            record.updated_at = utcnow()
            db.flush()
            db.execute(delete(FieldValue).where(FieldValue.record_id == record.id))
            for fr in assembled.fields:
                db.add(FieldValue(org_id=org_id, record_id=record.id, field_name=fr.name, value=fr.value,
                                  value_status=fr.value_status, method=fr.method,
                                  source_page_id=fr.source_page_id, source_url=fr.source_url,
                                  evidence=fr.evidence, confidence=fr.confidence, error=fr.error, selected=True))
                for alt in fr.alternatives:
                    db.add(FieldValue(org_id=org_id, record_id=record.id, field_name=fr.name,
                                      value=alt["value"], value_status="found", method=alt["method"],
                                      source_url=alt["source_url"], selected=False))
            stats["records"] += 1
            stats[assembled.status] += 1
        # Records whose source disappeared on a re-run (and were not edited) are removed.
        for key, record in existing.items():
            if key not in seen_keys and not record.user_edited:
                db.delete(record)
        return stats
