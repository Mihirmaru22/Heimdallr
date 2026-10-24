"""Tenant isolation: through the API (404s) and in the database itself (row-level security)."""

import uuid

import pytest
from sqlalchemy import select, text

from app.db import SessionLocal, session_scope, set_tenant
from app.models import CrawlJob, ExtractedRecord, Project


@pytest.fixture
def two_tenants(make_user, crawl_env):
    alice = make_user("alice@example.com")
    mallory = make_user("mallory@example.com")
    project = alice.post(alice.org("/projects"), json={"name": "secret project"}).json()
    spec = {"fields": [{"name": "company_name", "type": "string", "semantic": "company_name", "required": True}],
            "crawl": {"start_urls": [crawl_env["url"]("acme-security.test")], "max_pages": 3}}
    schema = alice.post(alice.org(f"/projects/{project['id']}/schemas"), json={"spec": spec}).json()
    job = alice.post(alice.org("/jobs"), json={"schema_id": schema["id"]}).json()
    rec = alice.get(alice.org(f"/jobs/{job['id']}/records")).json()["items"][0]
    exp = alice.post(alice.org(f"/jobs/{job['id']}/exports"), json={}).json()
    exp = alice.get(alice.org(f"/exports/{exp['id']}")).json()
    return alice, mallory, {"project": project, "schema": schema, "job": job, "record": rec, "export": exp}


def test_other_org_ids_are_not_found(two_tenants):
    alice, mallory, ids = two_tenants
    a = f"/api/v1/orgs/{alice.org_id}"
    # Mallory using Alice's organization id directly.
    for path in ["", "/projects", f"/projects/{ids['project']['id']}", f"/jobs/{ids['job']['id']}",
                 f"/records/{ids['record']['id']}", f"/exports/{ids['export']['id']}", "/members", "/usage"]:
        assert mallory.get(a + path).status_code == 404, path
    # Mallory using her own organization id with Alice's object ids.
    for path in [f"/projects/{ids['project']['id']}", f"/schemas/{ids['schema']['id']}",
                 f"/jobs/{ids['job']['id']}", f"/jobs/{ids['job']['id']}/records", f"/jobs/{ids['job']['id']}/urls",
                 f"/records/{ids['record']['id']}", f"/exports/{ids['export']['id']}"]:
        assert mallory.get(mallory.org(path)).status_code == 404, path
    assert mallory.post(mallory.org("/jobs"), json={"schema_id": ids["schema"]["id"]}).status_code == 404
    assert mallory.patch(mallory.org(f"/records/{ids['record']['id']}"), json={"excluded": True}).status_code == 404
    assert mallory.post(mallory.org(f"/jobs/{ids['job']['id']}/cancel")).status_code == 404
    r = mallory.post(mallory.org(f"/jobs/{ids['job']['id']}/records/exclude"),
                     json={"record_ids": [ids["record"]["id"]]})
    assert r.status_code == 404


def test_download_link_is_bound_to_user_and_org(two_tenants):
    alice, mallory, ids = two_tenants
    link = ids["export"]["download_url"]
    assert alice.get(link).status_code == 200
    assert mallory.get(link).status_code == 404  # not a member of that org
    swapped = link.replace(alice.org_id, mallory.org_id)
    assert mallory.get(swapped).status_code == 404
    tampered = link[:-4] + "0000"
    assert alice.get(tampered).status_code == 403
    from fastapi.testclient import TestClient

    anonymous = TestClient(alice.client.app)
    assert anonymous.get(link).status_code == 401


def test_rls_hides_other_tenants_rows_even_without_where_clauses(two_tenants):
    alice, mallory, ids = two_tenants
    with session_scope(uuid.UUID(mallory.org_id)) as db:
        assert db.execute(select(Project)).scalars().all() == []
        assert db.execute(select(CrawlJob)).scalars().all() == []
        assert db.execute(select(ExtractedRecord)).scalars().all() == []
    with session_scope(uuid.UUID(alice.org_id)) as db:
        assert len(db.execute(select(Project)).scalars().all()) == 1


def test_rls_blocks_writes_into_another_tenant(two_tenants):
    alice, mallory, ids = two_tenants
    db = SessionLocal()
    try:
        set_tenant(db, uuid.UUID(mallory.org_id))
        db.add(Project(org_id=uuid.UUID(alice.org_id), name="planted"))
        with pytest.raises(Exception, match="row-level security"):
            db.flush()
    finally:
        db.rollback()
        db.close()


def test_no_tenant_means_no_rows(two_tenants):
    db = SessionLocal()
    try:
        assert db.execute(text("SELECT count(*) FROM projects")).scalar_one() == 0
    finally:
        db.close()


def test_app_role_is_not_superuser(database):
    with session_scope() as db:
        row = db.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")).one()
    assert row == (False, False), "the application must not connect as a role that bypasses row-level security"


def test_member_roles(make_user):
    owner = make_user("owner@example.com")
    member = make_user("member@example.com")
    r = owner.post(owner.org("/members"), json={"email": "member@example.com", "role": "member"})
    assert r.status_code == 201
    member.org_id = owner.org_id
    assert member.get(member.org("/projects")).status_code == 200
    assert member.patch(member.org(), json={"name": "hijacked"}).status_code == 403
    assert member.post(member.org("/members"), json={"email": "owner@example.com"}).status_code == 403
    me = member.me["user"]["id"]
    assert owner.patch(owner.org(f"/members/{me}"), json={"role": "admin"}).status_code == 200
    # An admin cannot make themselves owner, and the last owner cannot be removed.
    assert member.patch(member.org(f"/members/{me}"), json={"role": "owner"}).status_code == 403
    owner_id = owner.me["user"]["id"]
    assert owner.delete(owner.org(f"/members/{owner_id}")).status_code == 409
