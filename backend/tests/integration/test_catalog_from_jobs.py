"""A finished job adds its delivered companies, with their sources, to the catalog without a manual rebuild."""

import uuid

from sqlalchemy import select

from app.db import session_scope
from app.models import CatalogClaim, CatalogCompany, CompanyFact, Evidence
from app.services.companies import build_companies
from app.spec.models import ExtractionSpec
from tests.integration.test_pipeline import make_job


def test_a_delivered_company_reaches_the_catalog_when_the_job_is_decided(db_clean):
    discovery = {"providers": ["case_studies"], "technology": "NetSuite", "countries": ["GB"]}
    job_id, org_id = make_job(["https://acme.example.test/"], discovery=discovery)
    spec = ExtractionSpec.model_validate({"entity": "company", "fields": [
        {"name": "company_name", "type": "string", "semantic": "company_name", "required": True}],
        "discovery": discovery})
    proof_url = "https://www.netsuite.com/customers/acme"
    registry_url = "https://api.gleif.org/api/v1/lei-records/529900ABCDEFGHIJ1234"
    with session_scope(org_id) as db:
        db.add(Evidence(org_id=org_id, job_id=job_id, company="Acme Widgets", website="https://acme.example.test/",
                        product="NetSuite", quote="Acme Widgets runs its finance on NetSuite.", url=proof_url,
                        source_type="Vendor case study", relationship="uses", judged_by="rules", strength=0.9,
                        verdict="Confirmed", kept=True))
        db.add(CompanyFact(org_id=org_id, job_id=job_id, site="acme.example.test", company="Acme Widgets",
                           kind="country", value="GB", by="registry: gleif", detail="matched by website",
                           source_url=registry_url))

    outcomes = build_companies(job_id, org_id, spec)

    assert outcomes.get("delivered") == 1
    with session_scope(org_id) as db:
        company = db.execute(select(CatalogCompany).where(CatalogCompany.org_id == org_id)).scalar_one()
        claims = {c.field_key: c for c in db.execute(
            select(CatalogClaim).where(CatalogClaim.company_id == company.id)).scalars()}
    assert company.domain == "acme.example.test"
    assert claims["uses_technology"].source_url == proof_url
    assert claims["uses_technology"].verification_status == "verified"
    assert claims["uses_technology"].source_job_id == uuid.UUID(str(job_id))
    assert claims["country"].source_url == registry_url
