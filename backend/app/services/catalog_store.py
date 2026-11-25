"""Accumulate source-backed, reviewable facts from completed company research jobs."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
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
    reputable_hosts = {"reuters.com", "bloomberg.com", "wsj.com", "ft.com", "cnbc.com", "bbc.com", "bbc.co.uk",
                       "apnews.com", "theguardian.com"}
    company_count = 0
    claim_count = 0
    for company in companies:
        source_evidence_rows = _matching_usage_evidence(evidence_rows, company)
        source_evidence = next((item for item in source_evidence_rows if item.url == company.proof_url), None)
        website = company.website or (source_evidence.website if source_evidence else "")
        domain = registered_domain(website) or ""
        identity = _identity_key(company.name, domain, company.country)
        if not identity:
            continue

        claims: list[dict[str, Any]] = []
        for evidence in source_evidence_rows:
            if not evidence.product or not evidence.url or not evidence.quote:
                continue
            source_host = _source_host(evidence.url)
            direct = (evidence.verdict == "Confirmed" and (
                evidence.source_type in {"Company website", "Vendor case study", "Customer's own page"}
                or evidence.source_type.startswith("SEC filing")
            ))
            reputable_news = evidence.source_type == "News article" and any(
                source_host == host or source_host.endswith("." + host) for host in reputable_hosts)
            claims.append({
                "field_key": "uses_technology",
                "value": evidence.product,
                "raw_value": evidence.product,
                "status": "verified" if direct else "needs_review",
                "verified_direct": direct,
                "reputable": reputable_news or evidence.source_type == "Partner case study",
                "method": "direct_first_party_or_filing" if direct else "usage_evidence_review",
                "confidence": evidence.strength,
                "source_url": evidence.url,
                "source_origin": source_host,
                "source_group": source_host if (
                    direct or reputable_news or evidence.source_type == "Partner case study"
                ) else "",
                "source_record_id": str(evidence.id),
                "source_license": "Source page; reuse terms are set by the publisher.",
                "retrieved_at": evidence.created_at,
                "quote": evidence.quote,
                "source_type": evidence.source_type or "",
                "source_date": evidence.evidence_date or "",
                "relationship": evidence.relationship or "uses",
                "evidence_id": evidence.id,
            })

        for fact in facts:
            if (fact.site != domain or fact.kind != "country" or not fact.by.casefold().startswith("registry")
                    or not fact.source_url or not fact.value):
                continue
            claims.append({
                "field_key": "country",
                "value": fact.value,
                "status": "needs_review",
                "method": "official_registry_review",
                "verified_direct": True,
                "confidence": None,
                "source_url": fact.source_url,
                "source_origin": _source_host(fact.source_url),
                "source_record_id": "",
                "source_license": "Official registry source; reuse terms not recorded by the research result.",
                "retrieved_at": now,
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
                "source_origin": _source_host(source_url),
                "source_record_id": "",
                "source_license": "Company website; reuse terms are set by the publisher.",
                "retrieved_at": now,
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


def ingest_source_claim(db: Session, org_id: uuid.UUID, *, company_name: str, website: str = "",
                        country: str = "", claim: dict[str, Any]) -> uuid.UUID:
    """Add one normalized, provenance-rich claim from a public source to the tenant catalog.

    Callers may set ``verified_direct`` only when the source directly and authoritatively supports
    this specific field. Claims from eligible independent sources can corroborate one another; a
    conflicting value in the same field keeps the claim in review.
    """
    domain = registered_domain(website) or ""
    identity = _identity_key(company_name, domain, country)
    if not identity:
        raise ValueError("A company name or website is required to store a catalog claim")
    now = utcnow()
    exact_matches = db.execute(select(CatalogCompany).where(
        CatalogCompany.org_id == org_id,
    )).scalars().all() if not domain else []
    matching = [company for company in exact_matches if _normalized_name(company.name) == _normalized_name(company_name)
                and (not company.domain or not domain or company.domain.casefold() == domain.casefold())]
    if len(matching) == 1:
        company_id = matching[0].id
    else:
        company_id = _upsert_company(db, org_id, identity, company_name, website, domain, now)
    _upsert_claim(db, org_id, company_id, claim.get("source_job_id"), claim, now)
    return company_id


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
        set_={"last_seen_at": now, "updated_at": now},
    ).returning(CatalogCompany.id)
    return db.execute(statement).scalar_one()


def _upsert_claim(
    db: Session,
    org_id: uuid.UUID,
    company_id: uuid.UUID,
    job_id: uuid.UUID | None,
    claim: dict[str, Any],
    now,
) -> None:
    value = claim["value"]
    source_group = str(claim.get("source_group") or "")[:300]
    status = str(claim.get("status") or "needs_review")
    method = str(claim.get("method") or "source_review")
    if claim.get("verified_direct"):
        if claim.get("field_key") == "uses_technology":
            _corroboration_status(db, org_id, company_id, claim)  # keep earlier corroborated claims honest
        status, method = "verified", "direct_official_source"
    elif source_group and claim.get("reputable"):
        status, method = _corroboration_status(db, org_id, company_id, claim), "corroborated_sources"
    value_json = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    source_url = claim["source_url"]
    field_key = claim["field_key"][:120]
    relationship = str(claim.get("relationship") or "")[:40]
    claim_key = hashlib.sha256(
        f"{field_key}\0{value_json}\0{relationship}\0{source_url}".encode()
    ).hexdigest()
    statement = pg_insert(CatalogClaim).values(
        org_id=org_id,
        company_id=company_id,
        claim_key=claim_key,
        field_key=field_key,
        value=value,
        display_value=_display_value(value),
        verification_status=status,
        verification_method=method,
        confidence=claim["confidence"],
        source_url=source_url,
        raw_value=claim.get("raw_value", value),
        source_origin=str(claim.get("source_origin") or _source_host(source_url))[:300],
        source_group=source_group,
        source_record_id=str(claim.get("source_record_id") or "")[:300],
        source_license=str(claim.get("source_license") or "")[:4000],
        retrieved_at=claim.get("retrieved_at") or datetime.now(UTC),
        quote=claim["quote"][:8000],
        source_type=claim["source_type"][:100],
        source_date=claim["source_date"][:10],
        relationship=relationship,
        source_job_id=job_id,
        source_evidence_id=claim.get("evidence_id"),
        verified_at=now if status == "verified" else None,
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


def _corroboration_status(db: Session, org_id: uuid.UUID, company_id: uuid.UUID,
                          claim: dict[str, Any]) -> str:
    """Auto-verify only two independent reputable origins with the same value and no conflict."""
    field_key = str(claim.get("field_key") or "")[:120]
    normalized = _normalized_value(claim["value"])
    if not field_key or not normalized:
        return "needs_review"
    peers = db.execute(select(CatalogClaim).where(
        CatalogClaim.org_id == org_id,
        CatalogClaim.company_id == company_id,
        CatalogClaim.field_key == field_key,
        CatalogClaim.verification_status != "rejected",
    )).scalars().all()
    matching = [peer for peer in peers if _normalized_value(peer.value) == normalized]
    # A company may use multiple products, so different values are not inherently contradictory.
    # For technology claims, however, a source saying "evaluating" or "moved away" contradicts "uses".
    if field_key == "uses_technology":
        positive = {"uses", "rolling_out"}
        incoming_relationship = str(claim.get("relationship") or "").casefold()
        if incoming_relationship not in positive or any(
            peer.relationship.casefold() not in positive for peer in matching
        ):
            for peer in matching:
                if peer.verification_method == "corroborated_sources":
                    peer.verification_status = "needs_review"
                    peer.verification_method = "corroboration_conflict_review"
                    peer.verified_at = None
            return "needs_review"
    groups = {str(claim.get("source_group") or "")} - {""}
    quotes = {_quote_fingerprint(str(claim.get("quote") or ""))}
    for peer in matching:
        if peer.source_group:
            groups.add(peer.source_group)
        quotes.add(_quote_fingerprint(peer.quote))
    # An identical excerpt copied to several domains remains one source signal.
    if len(groups) >= 2 and len(quotes - {""}) >= 2:
        # Promote matching pending claims together so either ingestion order yields the same state.
        for peer in matching:
            if peer.source_group and _normalized_value(peer.value) == normalized:
                peer.verification_status = "verified"
                peer.verification_method = "corroborated_sources"
                peer.verified_at = utcnow()
        return "verified"
    return "needs_review"


def _normalized_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).casefold()


def _quote_fingerprint(quote: str) -> str:
    normalized = " ".join(quote.casefold().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else ""


def _identity_key(name: str, domain: str, country: str) -> str:
    if domain:
        return f"domain:{domain}"[:512]
    normalized = _normalized_name(name)
    if not normalized:
        return ""
    suffix = f":{country.casefold()}" if country else ""
    return f"name:{normalized}{suffix}"[:512]


def _matching_usage_evidence(evidence_rows: list[Evidence], company: JobCompany) -> list[Evidence]:
    company_domain = registered_domain(company.website) or ""
    company_name = _normalized_name(company.name)
    return [item for item in evidence_rows
            if item.kept and item.verdict in {"Confirmed", "Likely"}
            and item.relationship in {"uses", "rolling_out", "evaluating", "moved_away"}
            and (registered_domain(item.website) == company_domain if company_domain
                 else company_name and _normalized_name(item.company) == company_name)]


def _normalized_name(name: str) -> str:
    return "".join(character for character in (name or "").casefold() if character.isalnum())


def _source_host(url: str) -> str:
    from urllib.parse import urlsplit

    return (urlsplit(url).hostname or "").casefold()[:300]


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
