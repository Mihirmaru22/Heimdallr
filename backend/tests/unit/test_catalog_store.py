"""Unit tests for catalog accumulation, claim state transitions, and provenance."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.db import session_scope
from app.models import (
    CatalogClaim,
    CatalogCompany,
    CompanyFact,
    CrawlJob,
    Evidence,
    ExtractedRecord,
    ExtractionSchema,
    FieldValue,
    JobCompany,
    Project,
)
from app.services.catalog_store import (
    _matching_country_fact,
    accumulate_job_catalog,
    rebuild_catalog,
)


@pytest.fixture
def catalog_job_env(make_user):
    alice = make_user("alice_catalog@example.com")
    org_id = uuid.UUID(alice.org_id)
    with session_scope(org_id) as db:
        project = Project(org_id=org_id, name="catalog test")
        db.add(project)
        db.flush()

        schema = ExtractionSchema(
            org_id=org_id,
            project_id=project.id,
            version=1,
            nl_request="companies using tech",
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
        db.commit()
        job_id = job.id

    return alice, org_id, job_id


def test_matching_country_fact_logic():
    company = JobCompany(name="Acme Inc", website="https://acme.com")
    fact_valid = CompanyFact(
        site="acme.com",
        company="Acme Inc",
        kind="country",
        value="US",
        by="registry: sec",
        source_url="https://sec.gov/edgar/123",
    )
    assert _matching_country_fact(fact_valid, company, "acme.com") is True

    # Non-country kind
    fact_other = CompanyFact(
        site="acme.com", company="Acme Inc", kind="phone", value="123", by="registry", source_url="https://sec.gov"
    )
    assert _matching_country_fact(fact_other, company, "acme.com") is False

    # Non-registry
    fact_news = CompanyFact(
        site="acme.com", company="Acme Inc", kind="country", value="US", by="news article", source_url="https://news.com"
    )
    assert _matching_country_fact(fact_news, company, "acme.com") is False

    # Name match fallback when domain/site is empty
    comp_no_domain = JobCompany(name="Acme Technologies", website="")
    fact_no_site = CompanyFact(
        site="",
        company="Acme Technologies",
        kind="country",
        value="UK",
        by="registry: companies house",
        source_url="https://find-and-update.company-information.service.gov.uk/123",
    )
    assert _matching_country_fact(fact_no_site, comp_no_domain, "") is True

    # Mismatched name
    comp_other = JobCompany(name="Globex Corp", website="")
    assert _matching_country_fact(fact_no_site, comp_other, "") is False


def test_accumulate_confirmed_software_usage(catalog_job_env):
    _alice, org_id, job_id = catalog_job_env
    with session_scope(org_id) as db:
        ev = Evidence(
            org_id=org_id,
            job_id=job_id,
            company="Acme Corp",
            website="https://acme.com",
            product="Snowflake",
            url="https://acme.com/case-study",
            quote="Acme deploys Snowflake on AWS.",
            verdict="Confirmed",
            strength=0.95,
            source_type="Case study",
            relationship="uses",
            kept=True,
        )
        db.add(ev)
        db.flush()

        jc = JobCompany(
            org_id=org_id,
            job_id=job_id,
            key="domain:acme.com",
            name="Acme Corp",
            website="https://acme.com",
            status="delivered",
            proof_verdict="Confirmed",
            proof_url="https://acme.com/case-study",
            proof_quote="Acme deploys Snowflake on AWS.",
            country="US",
        )
        db.add(jc)
        db.flush()

        counts = accumulate_job_catalog(db, job_id, org_id)
        assert counts["companies"] == 1
        assert counts["claims"] == 1

        company = db.execute(select(CatalogCompany).where(CatalogCompany.org_id == org_id)).scalar_one()
        assert company.name == "Acme Corp"
        assert company.domain == "acme.com"

        claim = db.execute(select(CatalogClaim).where(CatalogClaim.company_id == company.id)).scalar_one()
        assert claim.field_key == "uses_technology"
        assert claim.value == "Snowflake"
        assert claim.verification_status == "verified"
        assert claim.verification_method == "confirmed_usage_evidence"
        assert claim.source_url == "https://acme.com/case-study"
        assert claim.quote == "Acme deploys Snowflake on AWS."


def test_accumulate_registry_country_claim(catalog_job_env):
    _alice, org_id, job_id = catalog_job_env
    with session_scope(org_id) as db:
        fact = CompanyFact(
            org_id=org_id,
            job_id=job_id,
            site="initech.com",
            company="Initech LLC",
            kind="country",
            value="US",
            by="registry: sec",
            source_url="https://www.sec.gov/edgar/initech",
            quote="Initech state of incorporation: DE",
        )
        db.add(fact)

        jc = JobCompany(
            org_id=org_id,
            job_id=job_id,
            key="domain:initech.com",
            name="Initech LLC",
            website="https://initech.com",
            status="delivered",
            proof_verdict="",
            country="US",
            country_by="registry: sec",
        )
        db.add(jc)
        db.flush()

        counts = accumulate_job_catalog(db, job_id, org_id)
        assert counts["companies"] == 1
        assert counts["claims"] == 1

        claim = db.execute(select(CatalogClaim).where(CatalogClaim.org_id == org_id)).scalar_one()
        assert claim.field_key == "country"
        assert claim.value == "US"
        assert claim.verification_status == "needs_review"
        assert claim.verification_method == "official_registry_review"
        assert claim.source_url == "https://www.sec.gov/edgar/initech"


def test_accumulate_first_party_profile_fields(catalog_job_env):
    _alice, org_id, job_id = catalog_job_env
    with session_scope(org_id) as db:
        rec = ExtractedRecord(
            org_id=org_id,
            job_id=job_id,
            dedupe_key="hooli:profile",
            data={"company_name": "Hooli"},
            source_urls=["https://hooli.com/about"],
        )
        db.add(rec)
        db.flush()

        # First party field: matches hooli.com domain
        fv_valid = FieldValue(
            org_id=org_id,
            record_id=rec.id,
            field_name="employee_count",
            value="1500",
            value_status="found",
            method="llm_extraction",
            source_url="https://hooli.com/about",
            evidence="Over 1,500 employees worldwide",
            confidence=0.9,
            selected=True,
        )
        # Third party field: should be filtered out
        fv_third_party = FieldValue(
            org_id=org_id,
            record_id=rec.id,
            field_name="competitor",
            value="Acme",
            value_status="found",
            method="llm_extraction",
            source_url="https://external-blog.test/post",
            evidence="Main rival is Acme",
            confidence=0.8,
            selected=True,
        )
        db.add_all([fv_valid, fv_third_party])

        jc = JobCompany(
            org_id=org_id,
            job_id=job_id,
            key="domain:hooli.com",
            name="Hooli",
            website="https://hooli.com",
            status="delivered",
            record_id=rec.id,
        )
        db.add(jc)
        db.flush()

        counts = accumulate_job_catalog(db, job_id, org_id)
        assert counts["companies"] == 1
        assert counts["claims"] == 1

        claims = db.execute(select(CatalogClaim).where(CatalogClaim.org_id == org_id)).scalars().all()
        assert len(claims) == 1
        assert claims[0].field_key == "employee_count"
        assert claims[0].verification_status == "needs_review"
        assert claims[0].verification_method == "first_party_page_review"


def test_catalog_claim_conflict_review_preservation(catalog_job_env):
    _alice, org_id, job_id = catalog_job_env
    with session_scope(org_id) as db:
        fact = CompanyFact(
            org_id=org_id,
            job_id=job_id,
            site="globex.com",
            company="Globex",
            kind="country",
            value="DE",
            by="registry: gleif",
            source_url="https://gleif.org/globex",
        )
        db.add(fact)
        jc = JobCompany(
            org_id=org_id,
            job_id=job_id,
            key="domain:globex.com",
            name="Globex",
            website="https://globex.com",
            status="delivered",
        )
        db.add(jc)
        db.flush()

        accumulate_job_catalog(db, job_id, org_id)
        claim = db.execute(select(CatalogClaim).where(CatalogClaim.org_id == org_id)).scalar_one()
        assert claim.verification_status == "needs_review"

        # User reviews and rejects the claim
        claim.verification_status = "rejected"
        claim.verification_method = "user_review"
        db.commit()

        # Re-running accumulation on the job should preserve the rejection
        accumulate_job_catalog(db, job_id, org_id)
        refreshed = db.execute(select(CatalogClaim).where(CatalogClaim.org_id == org_id)).scalar_one()
        assert refreshed.verification_status == "rejected"


def test_rebuild_catalog_idempotent(catalog_job_env):
    _alice, org_id, job_id = catalog_job_env
    with session_scope(org_id) as db:
        fact = CompanyFact(
            org_id=org_id,
            job_id=job_id,
            site="northwind.com",
            company="Northwind",
            kind="country",
            value="GB",
            by="registry: ch",
            source_url="https://find-and-update.company-information.service.gov.uk/northwind",
        )
        db.add(fact)
        jc = JobCompany(
            org_id=org_id,
            job_id=job_id,
            key="domain:northwind.com",
            name="Northwind",
            website="https://northwind.com",
            status="delivered",
        )
        db.add(jc)
        db.flush()

        totals1 = rebuild_catalog(db, org_id)
        assert totals1["jobs_scanned"] == 1
        assert totals1["companies"] == 1
        assert totals1["claims"] == 1

        # Second rebuild should not duplicate
        totals2 = rebuild_catalog(db, org_id)
        assert totals2["jobs_scanned"] == 1
        assert totals2["companies"] == 1
        assert totals2["claims"] == 1

        company_count = len(db.execute(select(CatalogCompany).where(CatalogCompany.org_id == org_id)).scalars().all())
        claim_count = len(db.execute(select(CatalogClaim).where(CatalogClaim.org_id == org_id)).scalars().all())
        assert company_count == 1
        assert claim_count == 1
