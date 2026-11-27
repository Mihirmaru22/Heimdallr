"""Integration tests for catalog search, company details, claim review workflows, and rebuild API."""

from __future__ import annotations

import uuid

import pytest

from app.db import session_scope
from app.models import (
    CatalogClaim,
    CatalogCompany,
    CompanyFact,
    CrawlJob,
    Evidence,
    ExtractionSchema,
    JobCompany,
    Project,
)
from app.services.catalog_store import accumulate_job_catalog


@pytest.fixture
def catalog_api_fixture(make_user):
    alice = make_user("alice_api@example.com")
    org_id = uuid.UUID(alice.org_id)

    with session_scope(org_id) as db:
        project = Project(org_id=org_id, name="catalog test project")
        db.add(project)
        db.flush()

        schema = ExtractionSchema(
            org_id=org_id,
            project_id=project.id,
            version=1,
            nl_request="test",
            spec={"fields": [{"name": "company_name", "type": "string"}]},
            status="active",
            interpreter="test",
        )
        db.add(schema)
        db.flush()

        job = CrawlJob(
            org_id=org_id,
            project_id=project.id,
            schema_id=schema.id,
            state="finished",
            settings={},
            counters={},
        )
        db.add(job)
        db.flush()

        # Company 1: Acme (has verified software usage + needs_review country)
        ev1 = Evidence(
            org_id=org_id,
            job_id=job.id,
            company="Acme Corp",
            website="https://acme.com",
            product="Databricks",
            url="https://acme.com/case-study",
            quote="Acme runs Databricks for Lakehouse.",
            verdict="Confirmed",
            strength=0.9,
            source_type="Case study",
            relationship="uses",
            kept=True,
        )
        fact1 = CompanyFact(
            org_id=org_id,
            job_id=job.id,
            site="acme.com",
            company="Acme Corp",
            kind="country",
            value="US",
            by="registry: sec",
            source_url="https://sec.gov/edgar/acme",
        )
        jc1 = JobCompany(
            org_id=org_id,
            job_id=job.id,
            key="domain:acme.com",
            name="Acme Corp",
            website="https://acme.com",
            status="delivered",
            proof_verdict="Confirmed",
            proof_url="https://acme.com/case-study",
            proof_quote="Acme runs Databricks for Lakehouse.",
            country="US",
        )

        # Company 2: Beta GmbH (only has needs_review country)
        fact2 = CompanyFact(
            org_id=org_id,
            job_id=job.id,
            site="beta.de",
            company="Beta GmbH",
            kind="country",
            value="DE",
            by="registry: gleif",
            source_url="https://gleif.org/beta",
        )
        jc2 = JobCompany(
            org_id=org_id,
            job_id=job.id,
            key="domain:beta.de",
            name="Beta GmbH",
            website="https://beta.de",
            status="delivered",
            country="DE",
        )

        db.add_all([ev1, fact1, jc1, fact2, jc2])
        db.flush()

        accumulate_job_catalog(db, job.id, org_id)

    return alice, org_id


def test_search_catalog_default_verified_only(catalog_api_fixture):
    alice, _org_id = catalog_api_fixture
    r = alice.get(alice.org("/catalog"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["name"] == "Acme Corp"
    assert body["items"][0]["verified_claims"] == 1


def test_search_catalog_include_review(catalog_api_fixture):
    alice, _org_id = catalog_api_fixture
    r = alice.get(alice.org("/catalog?include_review=true"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    names = {item["name"] for item in body["items"]}
    assert "Acme Corp" in names
    assert "Beta GmbH" in names


def test_search_catalog_query_and_filters(catalog_api_fixture):
    alice, _org_id = catalog_api_fixture

    # Search by q matching company name
    r_q = alice.get(alice.org("/catalog?q=Acme"))
    assert r_q.status_code == 200
    assert r_q.json()["total"] == 1
    assert r_q.json()["items"][0]["domain"] == "acme.com"

    # Search by q matching quote
    r_quote = alice.get(alice.org("/catalog?q=Lakehouse"))
    assert r_quote.status_code == 200
    assert r_quote.json()["total"] == 1

    # Filter by technology
    r_tech = alice.get(alice.org("/catalog?technology=Databricks"))
    assert r_tech.status_code == 200
    assert r_tech.json()["total"] == 1

    # Filter by non-existent technology
    r_tech_none = alice.get(alice.org("/catalog?technology=Oracle"))
    assert r_tech_none.status_code == 200
    assert r_tech_none.json()["total"] == 0

    # Filter by region with include_review=true
    r_region = alice.get(alice.org("/catalog?region=DE&include_review=true"))
    assert r_region.status_code == 200
    assert r_region.json()["total"] == 1
    assert r_region.json()["items"][0]["name"] == "Beta GmbH"


def test_get_catalog_company_detail(catalog_api_fixture):
    alice, org_id = catalog_api_fixture
    with session_scope(org_id) as db:
        from sqlalchemy import select
        acme = db.execute(select(CatalogCompany).where(CatalogCompany.domain == "acme.com")).scalar_one()
        acme_id = acme.id

    r = alice.get(alice.org(f"/catalog/{acme_id}"))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["name"] == "Acme Corp"
    assert data["domain"] == "acme.com"
    assert len(data["claims"]) == 2

    # Verified claims come first
    assert data["claims"][0]["verification_status"] == "verified"
    assert data["claims"][0]["field_key"] == "uses_technology"
    assert data["claims"][1]["verification_status"] == "needs_review"
    assert data["claims"][1]["field_key"] == "country"


def test_review_claim_verify_reject_reopen(catalog_api_fixture):
    alice, org_id = catalog_api_fixture
    with session_scope(org_id) as db:
        from sqlalchemy import select
        claim = db.execute(
            select(CatalogClaim).where(
                CatalogClaim.org_id == org_id,
                CatalogClaim.field_key == "country",
                CatalogClaim.source_url == "https://sec.gov/edgar/acme",
                CatalogClaim.verification_status == "needs_review",
            )
        ).scalar_one()
        claim_id = claim.id

    # 1. Verify: needs_review -> verify
    r_verify = alice.post(alice.org(f"/catalog/claims/{claim_id}/review"), json={"decision": "verify"})
    assert r_verify.status_code == 200, r_verify.text
    assert r_verify.json()["verification_status"] == "verified"
    assert r_verify.json()["verified_by"] is not None

    # 2. Reject: verified -> reject
    r_reject = alice.post(alice.org(f"/catalog/claims/{claim_id}/review"), json={"decision": "reject"})
    assert r_reject.status_code == 200, r_reject.text
    assert r_reject.json()["verification_status"] == "rejected"

    # 3. Invalid direct transition: rejected -> verify must return 409
    r_invalid = alice.post(alice.org(f"/catalog/claims/{claim_id}/review"), json={"decision": "verify"})
    assert r_invalid.status_code == 409
    assert r_invalid.json()["code"] == "claim_already_reviewed"

    # 4. Reopen: rejected -> needs_review
    r_reopen = alice.post(alice.org(f"/catalog/claims/{claim_id}/review"), json={"decision": "reopen"})
    assert r_reopen.status_code == 200, r_reopen.text
    assert r_reopen.json()["verification_status"] == "needs_review"


def test_rebuild_catalog_endpoint(catalog_api_fixture):
    alice, _org_id = catalog_api_fixture
    r = alice.post(alice.org("/catalog/rebuild"))
    assert r.status_code == 200, r.text
    data = r.json()
    assert "jobs_scanned" in data
    assert "companies" in data
    assert "claims" in data
    assert data["jobs_scanned"] >= 1
