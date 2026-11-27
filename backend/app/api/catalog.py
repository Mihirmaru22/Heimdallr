"""Search and review the durable, organization-scoped company catalog."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import case, or_, select
from sqlalchemy.orm import Session

from app.db import get_db, utcnow
from app.deps import OrgContext, org_member
from app.errors import ApiError
from app.models import CatalogClaim, CatalogCompany
from app.schemas import (
    CatalogClaimOut,
    CatalogClaimReviewIn,
    CatalogCompanyDetail,
    CatalogCompanyOut,
    CatalogRebuildOut,
    Page,
)
from app.services.catalog_store import rebuild_catalog
from app.services.common import audit

from ._util import client_ip, get_in_org, paginate

router = APIRouter(prefix="/orgs/{org_id}/catalog", tags=["catalog"])


@router.get("", response_model=Page[CatalogCompanyOut])
def search_catalog(
    ctx: OrgContext = Depends(org_member),
    db: Session = Depends(get_db),
    q: str | None = Query(None, max_length=200),
    region: str | None = Query(None, max_length=120),
    technology: str | None = Query(None, max_length=200),
    field: str | None = Query(None, max_length=120),
    value: str | None = Query(None, max_length=200),
    include_review: bool = False,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Page[CatalogCompanyOut]:
    """Search verified claims by default; include_review also exposes facts awaiting a person."""
    statuses = ("verified", "needs_review") if include_review else ("verified",)
    query = select(CatalogCompany).where(CatalogCompany.org_id == ctx.org.id)
    query = query.where(_has_claim(ctx.org.id, statuses))

    if q:
        pattern = _pattern(q)
        matching_claim = select(CatalogClaim.id).where(
            CatalogClaim.org_id == ctx.org.id,
            CatalogClaim.company_id == CatalogCompany.id,
            CatalogClaim.verification_status.in_(statuses),
            or_(CatalogClaim.field_key.ilike(pattern, escape="\\"),
                CatalogClaim.display_value.ilike(pattern, escape="\\"),
                CatalogClaim.quote.ilike(pattern, escape="\\"),
                CatalogClaim.source_url.ilike(pattern, escape="\\")),
        ).exists()
        query = query.where(or_(
            CatalogCompany.name.ilike(pattern, escape="\\"),
            CatalogCompany.domain.ilike(pattern, escape="\\"),
            CatalogCompany.website.ilike(pattern, escape="\\"),
            matching_claim,
        ))

    if region:
        query = query.where(_claim_matches(ctx.org.id, statuses, display_value=region))
    if technology:
        query = query.where(_claim_matches(ctx.org.id, statuses, field_key="uses_technology", display_value=technology,
                                           relationships=("uses", "rolling_out")))
    if field or value:
        query = query.where(_claim_matches(ctx.org.id, statuses, field_key=field, display_value=value))

    items, total = paginate(db, query.order_by(CatalogCompany.name, CatalogCompany.domain), limit, offset)
    counts: dict[uuid.UUID, dict[str, int | str]] = {
        item.id: {"verified": 0, "needs_review": 0, "location": ""} for item in items
    }
    if counts:
        rows = db.execute(select(CatalogClaim.company_id, CatalogClaim.verification_status,
                                CatalogClaim.field_key, CatalogClaim.display_value)
                          .where(CatalogClaim.org_id == ctx.org.id,
                                 CatalogClaim.company_id.in_(counts),
                                 CatalogClaim.verification_status.in_(("verified", "needs_review")))
                          .order_by(CatalogClaim.company_id, CatalogClaim.verification_status,
                                    CatalogClaim.field_key)).all()
        for company_id, status, field_key, display_value in rows:
            if status in counts[company_id]:
                counts[company_id][status] = int(counts[company_id][status]) + 1
            if (status == "verified" and not counts[company_id]["location"]
                    and field_key in {"country", "region", "headquarters", "head_office", "address", "location",
                                      "city", "state", "state_province"}):
                counts[company_id]["location"] = display_value[:180]

    return Page(items=[_company_out(company, counts[company.id]) for company in items], total=total,
                limit=limit, offset=offset)


@router.get("/{company_id}", response_model=CatalogCompanyDetail)
def catalog_company(company_id: uuid.UUID, ctx: OrgContext = Depends(org_member),
                    db: Session = Depends(get_db)) -> CatalogCompanyDetail:
    company = get_in_org(db, CatalogCompany, company_id, ctx.org.id, "catalog company")
    claims = db.execute(select(CatalogClaim).where(
        CatalogClaim.org_id == ctx.org.id,
        CatalogClaim.company_id == company.id,
    ).order_by(
        case((CatalogClaim.verification_status == "verified", 0),
             (CatalogClaim.verification_status == "needs_review", 1), else_=2),
        CatalogClaim.field_key,
        CatalogClaim.display_value,
    )).scalars().all()
    counts = {
        "verified": sum(claim.verification_status == "verified" for claim in claims),
        "needs_review": sum(claim.verification_status == "needs_review" for claim in claims),
        "location": next((claim.display_value[:180] for claim in claims
                          if claim.verification_status == "verified" and claim.field_key in {
                              "country", "region", "headquarters", "head_office", "address", "location",
                              "city", "state", "state_province"}), ""),
    }
    return CatalogCompanyDetail(**_company_out(company, counts).model_dump(),
                                claims=[CatalogClaimOut.model_validate(claim) for claim in claims])


@router.post("/claims/{claim_id}/review", response_model=CatalogClaimOut)
def review_claim(claim_id: uuid.UUID, body: CatalogClaimReviewIn, request: Request,
                 ctx: OrgContext = Depends(org_member), db: Session = Depends(get_db)) -> CatalogClaimOut:
    claim = get_in_org(db, CatalogClaim, claim_id, ctx.org.id, "catalog claim")
    allowed = {
        "needs_review": {"verify", "reject"},
        "verified": {"reject", "reopen"},
        "rejected": {"reopen"},
    }
    if body.decision not in allowed.get(claim.verification_status, set()):
        raise ApiError(409, "claim_already_reviewed", "That review action is not valid for this claim state")

    if body.decision == "verify":
        claim.verification_status = "verified"
    elif body.decision == "reject":
        claim.verification_status = "rejected"
    else:
        claim.verification_status = "needs_review"
    claim.verification_method = "user_review"
    claim.verified_by = ctx.user.id if body.decision == "verify" else None
    claim.verified_at = utcnow() if body.decision == "verify" else None
    audit(db, f"catalog.claim.{body.decision}", org_id=ctx.org.id, actor_id=ctx.user.id,
          target_type="catalog_claim", target_id=claim.id, ip=client_ip(request),
          data={"field_key": claim.field_key, "source_url": claim.source_url})
    db.commit()
    db.refresh(claim)
    return CatalogClaimOut.model_validate(claim)


@router.post("/rebuild", response_model=CatalogRebuildOut)
def rebuild_existing_results(request: Request, ctx: OrgContext = Depends(org_member),
                             db: Session = Depends(get_db)) -> CatalogRebuildOut:
    """Idempotently pull eligible records from earlier runs into the catalog."""
    totals = rebuild_catalog(db, ctx.org.id)
    audit(db, "catalog.rebuild", org_id=ctx.org.id, actor_id=ctx.user.id,
          target_type="catalog", target_id=ctx.org.id, ip=client_ip(request), data=totals)
    db.commit()
    return CatalogRebuildOut(**totals)


def _has_claim(org_id: uuid.UUID, statuses: tuple[str, ...]):
    return select(CatalogClaim.id).where(
        CatalogClaim.org_id == org_id,
        CatalogClaim.company_id == CatalogCompany.id,
        CatalogClaim.verification_status.in_(statuses),
    ).exists()


def _claim_matches(org_id: uuid.UUID, statuses: tuple[str, ...], *, field_key: str | None = None,
                   display_value: str | None = None,
                   relationships: tuple[str, ...] | None = None):
    query = select(CatalogClaim.id).where(
        CatalogClaim.org_id == org_id,
        CatalogClaim.company_id == CatalogCompany.id,
        CatalogClaim.verification_status.in_(statuses),
    )
    if field_key:
        query = query.where(CatalogClaim.field_key.ilike(_pattern(field_key), escape="\\"))
    if display_value:
        query = query.where(CatalogClaim.display_value.ilike(_pattern(display_value), escape="\\"))
    if relationships:
        query = query.where(CatalogClaim.relationship.in_(relationships))
    return query.exists()


def _pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _company_out(company: CatalogCompany, counts: dict[str, int | str]) -> CatalogCompanyOut:
    return CatalogCompanyOut(id=company.id, name=company.name, website=company.website, domain=company.domain,
                             location=str(counts.get("location", "")),
                             verified_claims=int(counts.get("verified", 0)),
                             review_claims=int(counts.get("needs_review", 0)),
                             last_seen_at=company.last_seen_at, updated_at=company.updated_at)
