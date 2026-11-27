"""Accumulate source-backed, reviewable facts from completed company research jobs."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import case, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.crawl.urlnorm import registered_domain
from app.db import utcnow
from app.models import (
    CatalogClaim,
    CatalogCompany,
    CompanyFact,
    Evidence,
    FieldValue,
    JobCompany,
)

DELIVERED = "delivered"


def accumulate_job_catalog(db: Session, job_id: uuid.UUID, org_id: uuid.UUID) -> dict[str, int]:
    """Copy eligible claims into the durable catalog, keeping provenance independent of job retention."""
    companies = db.execute(select(JobCompany).where(
        JobCompany.org_id == org_id,
        JobCompany.job_id == job_id,
        JobCompany.status == DELIVERED,
    ).order_by(JobCompany.name)).scalars().all()
    if not companies:
        return {"companies": 0, "claims": 0}

    evidence_rows = db.execute(select(Evidence).where(
        Evidence.org_id == org_id, Evidence.job_id == job_id,
    )).scalars().all()
    facts = db.execute(select(CompanyFact).where(
        CompanyFact.org_id == org_id, CompanyFact.job_id == job_id,
    )).scalars().all()
    record_ids = [company.record_id for company in companies if company.record_id]
    field_values = db.execute(select(FieldValue).where(
        FieldValue.org_id == org_id,
        FieldValue.record_id.in_(record_ids),
        FieldValue.selected.is_(True),
        FieldValue.value_status == "found",
    )).scalars().all() if record_ids else []
    fields_by_record: dict[uuid.UUID, list[FieldValue]] = {}
    for field_value in field_values:
        fields_by_record.setdefault(field_value.record_id, []).append(field_value)

    now = utcnow()
    company_count = 0
    claim_count = 0
    for company in companies:
        source_evidence = _matching_confirmed_evidence(evidence_rows, company)
        website = company.website or (source_evidence.website if source_evidence else "")
        domain = registered_domain(website) or ""
        identity = _identity_key(company.name, domain, company.country)
        if not identity:
            continue

        claims: list[dict[str, Any]] = []
        if (company.proof_verdict == "Confirmed" and source_evidence is not None
                and source_evidence.product and source_evidence.url and source_evidence.quote):
            claims.append({
                "field_key": "uses_technology",
                "value": source_evidence.product,
                "status": "verified",
                "method": "confirmed_usage_evidence",
                "confidence": source_evidence.strength,
                "source_url": source_evidence.url,
                "quote": source_evidence.quote,
                "source_type": source_evidence.source_type or "",
                "source_date": source_evidence.evidence_date or "",
                "relationship": source_evidence.relationship or "uses",
                "evidence_id": source_evidence.id,
            })

        for fact in facts:
            if not _matching_country_fact(fact, company, domain):
                continue
            claims.append({
                "field_key": "country",
                "value": fact.value,
                "status": "needs_review",
                "method": "official_registry_review",
                "confidence": None,
                "source_url": fact.source_url,
                "quote": fact.quote,
                "source_type": fact.by,
                "source_date": "",
                "relationship": "",
                "evidence_id": None,
            })

        for field_value in fields_by_record.get(company.record_id, []):
            source_url = field_value.source_url or ""
            if (not field_value.field_name or not source_url or not field_value.evidence
                    or _value_is_empty(field_value.value)):
                continue
            if not domain or registered_domain(source_url) != domain:
                continue  # profile facts must come from the company's own site before human review
            if field_value.field_name == "uses_technology" and company.proof_verdict == "Confirmed":
                continue  # keep the confirmed proof claim as the canonical usage fact
            claims.append({
                "field_key": field_value.field_name,
                "value": field_value.value,
                "status": "needs_review",
                "method": "first_party_page_review",
                "confidence": field_value.confidence,
                "source_url": source_url,
                "quote": field_value.evidence,
                "source_type": field_value.method or "",
                "source_date": "",
                "relationship": "",
                "evidence_id": None,
            })

        if not claims:
            continue

        company_id = _upsert_company(db, org_id, identity, company.name, website, domain, now)
        company_count += 1
        for claim in claims:
            _upsert_claim(db, org_id, company_id, job_id, claim, now)
            claim_count += 1

    return {"companies": company_count, "claims": claim_count}


def rebuild_catalog(db: Session, org_id: uuid.UUID) -> dict[str, int]:
    """Idempotently import eligible outcomes from this organization's existing research history."""
    job_ids = db.execute(select(JobCompany.job_id).where(
        JobCompany.org_id == org_id, JobCompany.status == DELIVERED,
    ).distinct().order_by(JobCompany.job_id)).scalars().all()
    totals = {"jobs_scanned": len(job_ids), "companies": 0, "claims": 0}
    for job_id in job_ids:
        counts = accumulate_job_catalog(db, job_id, org_id)
        totals["companies"] += counts["companies"]
        totals["claims"] += counts["claims"]
    return totals


def _upsert_company(
    db: Session,
    org_id: uuid.UUID,
    identity_key: str,
    name: str,
    website: str,
    domain: str,
    now,
) -> uuid.UUID:
    statement = pg_insert(CatalogCompany).values(
        org_id=org_id,
        identity_key=identity_key,
        name=(name or "")[:300],
        website=website or "",
        domain=domain,
        last_seen_at=now,
        created_at=now,
        updated_at=now,
    )
    statement = statement.on_conflict_do_update(
        index_elements=[CatalogCompany.org_id, CatalogCompany.identity_key],
        set_={
            "name": case((CatalogCompany.name == "", (name or "")[:300]), else_=CatalogCompany.name),
            "website": case((CatalogCompany.website == "", website or ""), else_=CatalogCompany.website),
            "last_seen_at": now,
            "updated_at": now,
        },
    ).returning(CatalogCompany.id)
    return db.execute(statement).scalar_one()


def _upsert_claim(
    db: Session,
    org_id: uuid.UUID,
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    claim: dict[str, Any],
    now,
) -> None:
    value = claim["value"]
    value_json = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    source_url = claim["source_url"]
    field_key = claim["field_key"][:120]
    claim_key = hashlib.sha256(f"{field_key}\0{value_json}\0{source_url}".encode()).hexdigest()
    statement = pg_insert(CatalogClaim).values(
        org_id=org_id,
        company_id=company_id,
        claim_key=claim_key,
        field_key=field_key,
        value=value,
        display_value=_display_value(value),
        verification_status=claim["status"],
        verification_method=claim["method"],
        confidence=claim["confidence"],
        source_url=source_url,
        quote=claim["quote"][:8000],
        source_type=claim["source_type"][:100],
        source_date=claim["source_date"][:10],
        relationship=claim["relationship"][:40],
        source_job_id=job_id,
        source_evidence_id=claim["evidence_id"],
        verified_at=now if claim["status"] == "verified" else None,
        first_seen_at=now,
        last_seen_at=now,
        created_at=now,
        updated_at=now,
    )
    existing_status = CatalogClaim.verification_status
    incoming = statement.excluded
    statement = statement.on_conflict_do_update(
        index_elements=[CatalogClaim.company_id, CatalogClaim.claim_key],
        set_={
            "last_seen_at": now,
            "updated_at": now,
            "verification_status": case(
                (existing_status == "rejected", "rejected"),
                (incoming.verification_status == "verified", "verified"),
                else_=existing_status,
            ),
            "verification_method": case(
                (existing_status == "needs_review", incoming.verification_method),
                else_=CatalogClaim.verification_method,
            ),
            "verified_at": case(
                (existing_status == "needs_review", incoming.verified_at),
                else_=CatalogClaim.verified_at,
            ),
        },
    )
    db.execute(statement)


def _identity_key(name: str, domain: str, country: str) -> str:
    if domain:
        return f"domain:{domain}"[:512]
    normalized = _normalized_name(name)
    if not normalized:
        return ""
    suffix = f":{country.casefold()}" if country else ""
    return f"name:{normalized}{suffix}"[:512]


def _matching_country_fact(fact: CompanyFact, company: JobCompany, domain: str) -> bool:
    if fact.kind != "country" or not fact.by.casefold().startswith("registry") or not fact.source_url or not fact.value:
        return False
    comp_name = _normalized_name(company.name)
    fact_name = _normalized_name(fact.company)
    if domain and fact.site:
        return fact.site == domain and (not comp_name or not fact_name or comp_name == fact_name)
    return bool(comp_name and fact_name and comp_name == fact_name)


def _matching_confirmed_evidence(evidence_rows: list[Evidence], company: JobCompany) -> Evidence | None:
    company_domain = registered_domain(company.website) or ""
    company_name = _normalized_name(company.name)
    return next((item for item in evidence_rows
                 if item.url == company.proof_url and item.kept and item.verdict == "Confirmed"
                 and (registered_domain(item.website) == company_domain if company_domain
                      else company_name and _normalized_name(item.company) == company_name)), None)


def _normalized_name(name: str) -> str:
    return "".join(character for character in (name or "").casefold() if character.isalnum())


def _value_is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _display_value(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "; ".join(_display_value(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)
