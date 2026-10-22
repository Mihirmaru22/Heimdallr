"""Projects, extraction schemas (generate, edit, confirm) and the plan preview."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.crawl import netguard
from app.crawl.netguard import BlockedDestination
from app.crawl.urlnorm import normalize_url
from app.db import get_db
from app.deps import OrgContext, org_member
from app.errors import ApiError
from app.models import ExtractionSchema, Project, Role
from app.schemas import GenerateSchemaIn, Page, PlanPreview, ProjectIn, ProjectOut, SchemaOut, SchemaUpdate, UrlCheck
from app.services.common import audit, org_limits, record_usage
from app.spec.models import validate_spec

from ._util import client_ip, get_in_org, paginate

router = APIRouter(prefix="/orgs/{org_id}", tags=["projects"])
PREVIEW_URL_CHECKS = 50


@router.get("/projects", response_model=Page[ProjectOut])
def list_projects(ctx: OrgContext = Depends(org_member), db: Session = Depends(get_db),
                  limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                  q: str | None = Query(None, max_length=200)) -> Page[ProjectOut]:
    query = select(Project).where(Project.org_id == ctx.org.id)
    if q:
        query = query.where(Project.name.ilike(f"%{q}%"))
    items, total = paginate(db, query.order_by(Project.created_at.desc()), limit, offset)
    return Page(items=[ProjectOut.model_validate(p) for p in items], total=total, limit=limit, offset=offset)


@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectIn, request: Request, ctx: OrgContext = Depends(org_member),
                   db: Session = Depends(get_db)) -> ProjectOut:
    p = Project(org_id=ctx.org.id, name=body.name, description=body.description, created_by=ctx.user.id)
    db.add(p)
    db.flush()
    audit(db, "project.create", org_id=ctx.org.id, actor_id=ctx.user.id, target_type="project", target_id=p.id,
          ip=client_ip(request))
    db.commit()
    return ProjectOut.model_validate(p)


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: uuid.UUID, ctx: OrgContext = Depends(org_member),
                db: Session = Depends(get_db)) -> ProjectOut:
    return ProjectOut.model_validate(get_in_org(db, Project, project_id, ctx.org.id, "project"))


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(project_id: uuid.UUID, body: ProjectIn, ctx: OrgContext = Depends(org_member),
                   db: Session = Depends(get_db)) -> ProjectOut:
    p = get_in_org(db, Project, project_id, ctx.org.id, "project")
    p.name, p.description = body.name, body.description
    db.commit()
    return ProjectOut.model_validate(p)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: uuid.UUID, request: Request, ctx: OrgContext = Depends(org_member),
                   db: Session = Depends(get_db)) -> None:
    ctx.require(Role.admin)
    p = get_in_org(db, Project, project_id, ctx.org.id, "project")
    db.delete(p)
    audit(db, "project.delete", org_id=ctx.org.id, actor_id=ctx.user.id, target_type="project",
          target_id=project_id, ip=client_ip(request))
    db.commit()


# --- schemas ----------------------------------------------------------------------------------


def _next_version(db: Session, project_id: uuid.UUID) -> int:
    return (db.execute(select(func.max(ExtractionSchema.version)).where(
        ExtractionSchema.project_id == project_id)).scalar_one() or 0) + 1


def _spec_error(exc: ValidationError | ValueError) -> ApiError:
    if isinstance(exc, ValidationError):
        errors = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()][:20]
    else:
        errors = [{"loc": [], "msg": str(exc)}]
    return ApiError(422, "invalid_spec", "The extraction specification is not valid", errors=errors)


@router.get("/projects/{project_id}/schemas", response_model=list[SchemaOut])
def list_schemas(project_id: uuid.UUID, ctx: OrgContext = Depends(org_member),
                 db: Session = Depends(get_db)) -> list[SchemaOut]:
    get_in_org(db, Project, project_id, ctx.org.id, "project")
    rows = db.execute(select(ExtractionSchema).where(ExtractionSchema.project_id == project_id,
                                                     ExtractionSchema.org_id == ctx.org.id)
                      .order_by(ExtractionSchema.version.desc())).scalars().all()
    return [SchemaOut.model_validate(s) for s in rows]


@router.post("/projects/{project_id}/schemas/generate", response_model=SchemaOut, status_code=201)
def generate_schema(project_id: uuid.UUID, body: GenerateSchemaIn, ctx: OrgContext = Depends(org_member),
                    db: Session = Depends(get_db)) -> SchemaOut:
    """Turn a plain-language question into a draft spec: one free-model call, or the rules when none answers."""
    import asyncio

    from app.spec.planner import plan_spec

    get_in_org(db, Project, project_id, ctx.org.id, "project")
    # Sync endpoints run in a worker thread with no event loop, so the async planner gets its own.
    draft, interpreter, notes = asyncio.run(plan_spec(body.request, body.start_urls))
    try:
        spec = validate_spec(draft.model_dump(mode="json"), org_limits(ctx.org))
    except (ValidationError, ValueError) as exc:
        raise _spec_error(exc) from None
    s = ExtractionSchema(org_id=ctx.org.id, project_id=project_id, version=_next_version(db, project_id),
                         nl_request=body.request, spec=spec.model_dump(mode="json"), status="draft",
                         interpreter=interpreter[:64])
    db.add(s)
    if interpreter.startswith("model:"):
        record_usage(db, ctx.org.id, "llm_request", 1, user_id=ctx.user.id,
                     detail={"model": interpreter[6:], "purpose": "plan"})
    db.commit()
    out = SchemaOut.model_validate(s)
    out.notes = notes
    return out


@router.post("/projects/{project_id}/schemas", response_model=SchemaOut, status_code=201)
def create_schema(project_id: uuid.UUID, body: SchemaUpdate, ctx: OrgContext = Depends(org_member),
                  db: Session = Depends(get_db)) -> SchemaOut:
    get_in_org(db, Project, project_id, ctx.org.id, "project")
    try:
        spec = validate_spec(body.spec, org_limits(ctx.org))
    except (ValidationError, ValueError) as exc:
        raise _spec_error(exc) from None
    s = ExtractionSchema(org_id=ctx.org.id, project_id=project_id, version=_next_version(db, project_id),
                         spec=spec.model_dump(mode="json"), status="draft", interpreter="manual")
    db.add(s)
    db.commit()
    return SchemaOut.model_validate(s)


@router.get("/schemas/{schema_id}", response_model=SchemaOut)
def get_schema(schema_id: uuid.UUID, ctx: OrgContext = Depends(org_member),
               db: Session = Depends(get_db)) -> SchemaOut:
    return SchemaOut.model_validate(get_in_org(db, ExtractionSchema, schema_id, ctx.org.id, "schema"))


@router.put("/schemas/{schema_id}", response_model=SchemaOut)
def update_schema(schema_id: uuid.UUID, body: SchemaUpdate, ctx: OrgContext = Depends(org_member),
                  db: Session = Depends(get_db)) -> SchemaOut:
    """Edit a draft. A confirmed schema is immutable (jobs point at it); editing it creates a new version."""
    s = get_in_org(db, ExtractionSchema, schema_id, ctx.org.id, "schema")
    try:
        spec = validate_spec(body.spec, org_limits(ctx.org))
    except (ValidationError, ValueError) as exc:
        raise _spec_error(exc) from None
    if s.status == "confirmed":
        s = ExtractionSchema(org_id=ctx.org.id, project_id=s.project_id, version=_next_version(db, s.project_id),
                             nl_request=s.nl_request, spec={}, status="draft", interpreter="manual")
        db.add(s)
    s.spec = spec.model_dump(mode="json")
    db.commit()
    return SchemaOut.model_validate(s)


@router.post("/schemas/{schema_id}/confirm", response_model=SchemaOut)
def confirm_schema(schema_id: uuid.UUID, ctx: OrgContext = Depends(org_member),
                   db: Session = Depends(get_db)) -> SchemaOut:
    s = get_in_org(db, ExtractionSchema, schema_id, ctx.org.id, "schema")
    try:
        validate_spec(s.spec, org_limits(ctx.org))
    except (ValidationError, ValueError) as exc:
        raise _spec_error(exc) from None
    s.status = "confirmed"
    db.commit()
    return SchemaOut.model_validate(s)


@router.get("/schemas/{schema_id}/preview", response_model=PlanPreview)
def preview(schema_id: uuid.UUID, ctx: OrgContext = Depends(org_member), db: Session = Depends(get_db)) -> PlanPreview:
    """What a job would do: which start URLs pass the safety checks, which discovery sources run, page caps."""
    s = get_in_org(db, ExtractionSchema, schema_id, ctx.org.id, "schema")
    try:
        spec = validate_spec(s.spec, org_limits(ctx.org))
    except (ValidationError, ValueError) as exc:
        raise _spec_error(exc) from None
    checks: list[UrlCheck] = []
    for raw in spec.crawl.start_urls[:PREVIEW_URL_CHECKS]:
        norm = normalize_url(raw)
        if norm is None:
            checks.append(UrlCheck(url=raw, normalized=None, allowed=False, reason="not a valid http(s) URL"))
            continue
        try:
            netguard.check_url(norm, resolver=netguard.resolve)  # looked up per call so tests can swap DNS
            checks.append(UrlCheck(url=raw, normalized=norm, allowed=True, reason="ok"))
        except BlockedDestination as exc:
            checks.append(UrlCheck(url=raw, normalized=norm, allowed=False, reason=str(exc)))
        except OSError as exc:
            checks.append(UrlCheck(url=raw, normalized=norm, allowed=False, reason=f"DNS lookup failed: {exc}"))
    warnings: list[str] = []
    if len(spec.crawl.start_urls) > PREVIEW_URL_CHECKS:
        warnings.append(f"Only the first {PREVIEW_URL_CHECKS} start URLs were checked here; "
                        "all are checked at run time.")
    if "searxng" in spec.discovery.providers and not get_settings().searxng_url:
        warnings.append("Web search (SearXNG) is not configured on this server, so it will be skipped.")
    if "sec_edgar" in spec.discovery.providers:
        from app.discovery.sec_edgar import SecEdgarProvider, index_ready

        if not SecEdgarProvider.covers(spec):
            warnings.append("SEC EDGAR only lists US-listed companies, so it will be skipped for this region.")
        elif not index_ready():
            warnings.append("The SEC company list has not been downloaded on this server yet "
                            "(run `python -m app.cli refresh-sec`), so SEC EDGAR will be skipped.")
    if not spec.crawl.start_urls and not set(spec.discovery.providers) - {"seeds"}:
        warnings.append("There are no start URLs and no discovery source, so the job would find nothing.")
    if "gleif" in spec.discovery.providers and not spec.discovery.industry:
        warnings.append("GLEIF searches company names for the industry, so it is skipped without one.")
    if spec.discovery.parent_company:
        warnings.append(f"Finding the sites of {spec.discovery.parent_company!r} is not built yet; add its "
                        "website as a start URL meanwhile.")
    if any(f.semantic.value == "none" and not (f.rules.css or f.rules.meta or f.rules.jsonld or f.rules.regex)
           for f in spec.fields):
        warnings.append("Custom details are only filled where a page labels them (\"Plant head: ...\") until "
                        "model reading arrives in a later step.")
    if "wikidata" in spec.discovery.providers:
        warnings.append("Wikidata returns companies that list an official website; coverage varies by industry.")
    searching = set(spec.discovery.providers) - {"seeds"}
    sites = len(spec.crawl.start_urls) + (spec.discovery.max_results if searching else 0)
    est_pages = min(spec.crawl.max_pages, max(1, sites) * spec.crawl.max_pages_per_site)
    return PlanPreview(spec=spec.model_dump(mode="json"), urls=checks, discovery_providers=spec.discovery.providers,
                       estimated_max_pages=est_pages, estimated_llm_calls=estimated_llm_calls(spec, sites),
                       warnings=warnings)


def estimated_llm_calls(spec, sites: int) -> int:
    """At most this many free-model requests: one per web-search homepage check, and for a technology question
    about two per company judged (proof check, plus a second reading of a use verdict)."""
    d = spec.discovery
    calls = d.max_results if "searxng" in d.providers else 0
    if d.technology:
        calls += 2 * max(sites, d.max_results)
    return calls
