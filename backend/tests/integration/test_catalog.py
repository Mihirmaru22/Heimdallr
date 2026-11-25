from __future__ import annotations

import uuid

from sqlalchemy import inspect, select

from app.db import engine, session_scope
from app.models import CatalogClaim, CatalogCompany
from app.services.catalog_store import ingest_source_claim


def _claim(field: str, value, *, url: str, quote: str, direct: bool = False, group: str = "",
           relationship: str | None = None) -> dict:
    return {
        "field_key": field,
        "value": value,
        "raw_value": value,
        "status": "verified" if direct else "needs_review",
        "verified_direct": direct,
        "reputable": bool(group),
        "method": "test_source",
        "confidence": 1.0 if direct else None,
        "source_url": url,
        "source_origin": url.split("/")[2],
        "source_group": group,
        "source_record_id": "record-1",
        "source_license": "Test fixture source license",
        "quote": quote,
        "source_type": "test source",
        "source_date": "2026-11-05",
        "relationship": relationship or ("uses" if field == "uses_technology" else ""),
    }


def test_catalog_columns_migrated(database):
    columns = {column["name"] for column in inspect(engine).get_columns("catalog_claims")}
    assert {
        "raw_value", "source_origin", "source_group", "source_record_id", "source_license", "retrieved_at"
    } <= columns


def test_catalog_search_review_and_tenant_isolation(make_user):
    alice = make_user("catalog-alice@example.com", org="Alice Catalog")
    mallory = make_user("catalog-mallory@example.com", org="Mallory Catalog")
    org_id = uuid.UUID(alice.org_id)
    website = "https://acme-analytics.example.test/"
    with session_scope(org_id) as db:
        company_id = ingest_source_claim(db, org_id, company_name="Acme Analytics Ltd", website=website,
                                         country="GB", claim=_claim(
            "country", "United Kingdom", url="https://register.example.test/acme", quote="Registered in the UK.",
            direct=True))
        ingest_source_claim(db, org_id, company_name="Acme Analytics Ltd", website=website, country="GB",
                            claim=_claim("uses_technology", "SAP ERP", url="https://acme-analytics.example.test/it",
                                         quote="We use SAP ERP.", direct=True))
        ingest_source_claim(db, org_id, company_name="Acme Analytics Ltd", website=website, country="GB",
                                        claim=_claim("contact_email", "support@acme-analytics.example.test",
                                                     url="https://acme-analytics.example.test/contact",
                                                     quote="Contact support@acme-analytics.example.test."))
        # Re-importing the same source claim is idempotent.
        ingest_source_claim(db, org_id, company_name="Acme Analytics Ltd", website=website, country="GB",
                            claim=_claim("uses_technology", "SAP ERP", url="https://acme-analytics.example.test/it",
                                         quote="We use SAP ERP.", direct=True))

    base = alice.org("/catalog")
    by_company = alice.get(base, params={"q": "Acme Analytics"}).json()
    assert by_company["total"] == 1 and by_company["items"][0]["id"] == str(company_id)
    assert alice.get(base, params={"region": "United Kingdom"}).json()["total"] == 1
    assert alice.get(base, params={"technology": "SAP"}).json()["total"] == 1
    review_search = alice.get(base, params={"field": "contact_email", "value": "support@acme",
                                           "include_review": True})
    assert review_search.json()["total"] == 1
    assert alice.get(base, params={"field": "contact_email"}).json()["total"] == 0

    detail = alice.get(f"{base}/{company_id}").json()
    email_claim = next(claim for claim in detail["claims"] if claim["field_key"] == "contact_email")
    assert email_claim["raw_value"] == "support@acme-analytics.example.test"
    assert email_claim["source_license"] == "Test fixture source license"
    reviewed = alice.post(alice.org(f"/catalog/claims/{email_claim['id']}/review"), json={"decision": "verify"})
    assert reviewed.status_code == 200 and reviewed.json()["verification_status"] == "verified"
    assert alice.get(base, params={"field": "contact_email"}).json()["total"] == 1

    assert mallory.get(alice.org("/catalog")).status_code == 404
    assert mallory.get(mallory.org("/catalog"), params={"q": "Acme Analytics"}).json()["total"] == 0
    with session_scope(org_id) as db:
        assert len(db.execute(select(CatalogCompany)).scalars().all()) == 1
        assert len(db.execute(select(CatalogClaim)).scalars().all()) == 3


def test_corroboration_requires_distinct_sources_and_distinct_quotes(make_user):
    user = make_user("catalog-corroboration@example.com", org="Evidence Catalog")
    org_id = uuid.UUID(user.org_id)
    company = "Northwind Research"
    website = "https://northwind.example.test/"
    with session_scope(org_id) as db:
        ingest_source_claim(db, org_id, company_name=company, website=website, country="US", claim=_claim(
            "uses_technology", "SAP ERP", url="https://publisher-a.example/one", quote="Northwind uses SAP ERP.",
            group="publisher-a.example"))
        ingest_source_claim(db, org_id, company_name=company, website=website, country="US", claim=_claim(
            "uses_technology", "SAP ERP", url="https://publisher-b.example/copy", quote="Northwind uses SAP ERP.",
            group="publisher-b.example"))
        rows = db.execute(select(CatalogClaim).where(CatalogClaim.field_key == "uses_technology")).scalars().all()
        assert {row.verification_status for row in rows} == {"needs_review"}

        ingest_source_claim(db, org_id, company_name=company, website=website, country="US", claim=_claim(
            "uses_technology", "SAP ERP", url="https://publisher-c.example/story",
            quote="Northwind rolled out SAP ERP.",
            group="publisher-c.example"))
        rows = db.execute(select(CatalogClaim).where(CatalogClaim.field_key == "uses_technology")).scalars().all()
        assert {row.verification_status for row in rows} == {"verified"}
        assert {row.verification_method for row in rows} == {"corroborated_sources"}


def test_conflicting_reputable_relationship_blocks_corroboration(make_user):
    user = make_user("catalog-conflict@example.com", org="Conflict Catalog")
    org_id = uuid.UUID(user.org_id)
    with session_scope(org_id) as db:
        for source, value, quote, relationship in (
            ("one.example", "SAP ERP", "Company uses SAP ERP.", "uses"),
            ("two.example", "SAP ERP", "Company rolled out the SAP ERP system.", "rolling_out"),
            ("three.example", "SAP ERP", "Company is evaluating SAP ERP.", "evaluating"),
        ):
            ingest_source_claim(db, org_id, company_name="Conflict Co", website="https://conflict.example.test/",
                                country="US", claim=_claim("uses_technology", value,
                                url=f"https://{source}/story", quote=quote, group=source,
                                relationship=relationship))
        rows = db.execute(select(CatalogClaim).where(CatalogClaim.field_key == "uses_technology")).scalars().all()
        assert {row.verification_status for row in rows} == {"needs_review"}
