"""The crawl pipeline against the local test websites, without the HTTP API."""

import uuid

from sqlalchemy import select

from app.db import session_scope
from app.models import (
    CrawlJob,
    DiscoveredUrl,
    ExtractedRecord,
    ExtractionSchema,
    FetchedPage,
    Membership,
    Organization,
    Project,
    User,
)
from app.services import pipeline
from app.spec.models import ExtractionSpec

FIELDS = [
    {"name": "company_name", "type": "string", "semantic": "company_name", "required": True},
    {"name": "website_url", "type": "url", "semantic": "website_url"},
    {"name": "contact_email", "type": "email", "semantic": "contact_email"},
    {"name": "phone", "type": "phone", "semantic": "phone"},
    {"name": "description", "type": "text", "semantic": "description"},
]


def make_job(start_urls, **spec_extra):
    spec = ExtractionSpec.model_validate({"entity": "company", "fields": FIELDS,
                                          "crawl": {"start_urls": start_urls, "max_pages": 30, "max_depth": 2},
                                          **spec_extra}).model_dump(mode="json")
    with session_scope(bypass=True) as db:
        user = User(email=f"{uuid.uuid4().hex[:8]}@example.test", password_hash="x")
        org = Organization(name="T", slug=uuid.uuid4().hex[:10])
        db.add_all([user, org])
        db.flush()
        db.add(Membership(org_id=org.id, user_id=user.id, role="owner"))
        project = Project(org_id=org.id, name="P")
        db.add(project)
        db.flush()
        schema = ExtractionSchema(org_id=org.id, project_id=project.id, version=1, spec=spec, status="confirmed")
        db.add(schema)
        db.flush()
        job = CrawlJob(org_id=org.id, project_id=project.id, schema_id=schema.id, settings={}, counters={})
        db.add(job)
        db.flush()
        return job.id, org.id


def urls_by_status(job_id, org_id):
    with session_scope(org_id) as db:
        return {u.url: (u.status, u.status_reason) for u in
                db.execute(select(DiscoveredUrl).where(DiscoveredUrl.job_id == job_id)).scalars()}


def records(job_id, org_id):
    with session_scope(org_id) as db:
        return db.execute(select(ExtractedRecord).where(ExtractedRecord.job_id == job_id)).scalars().all()


def test_full_crawl_respects_robots_and_extracts(db_clean, crawl_env):
    url = crawl_env["url"]
    job_id, org_id = make_job([url("acme-security.test"), url("globex.test"), url("blocked.test"),
                               url("flaky.test")])
    state = pipeline.run_job(job_id, resolver=crawl_env["resolver"])
    assert state == "completed"  # blocked and missing pages are reported, not failures

    statuses = urls_by_status(job_id, org_id)
    assert statuses[url("acme-security.test", "/private/secret.html")][0] == "blocked_robots"
    assert statuses[url("blocked.test")][0] == "blocked_robots"
    assert statuses[url("flaky.test")] == ("blocked_robots", "robots.txt unreachable; treated as disallow")
    assert ("acme-security.test", "/private/secret.html") not in crawl_env["requests"]
    assert ("blocked.test", "/") not in crawl_env["requests"]
    # A broken link is skipped, not counted as a failed page.
    assert statuses[url("acme-security.test", "/products/detect/")] == ("skipped", "page not found (HTTP 404)")

    # The redirect to the cloud metadata address and to a loopback port were refused, not followed.
    internal = statuses[url("globex.test", "/go-internal")]
    loopback = statuses[url("globex.test", "/go-loopback")]
    assert internal[0] == "blocked_policy" and "169.254.169.254" in internal[1]
    assert loopback[0] == "blocked_policy"

    recs = {r.data["company_name"]: r for r in records(job_id, org_id)}
    acme = recs["Acme Security Ltd"]
    assert acme.data["contact_email"] in ("hello@acme-security.test", "sales@acme-security.test")
    assert acme.data["phone"] == "+442079460958"
    assert acme.status == "valid"
    assert "Globex Cyber Defense" in recs
    # Prompt-injection text on a page is just data: nothing about the job changed because of it.
    assert all("attacker@evil.example" != r.data.get("contact_email") for r in recs.values())


def test_rerunning_a_finished_job_is_a_no_op(db_clean, crawl_env):
    job_id, org_id = make_job([crawl_env["url"]("acme-security.test")])
    assert pipeline.run_job(job_id, resolver=crawl_env["resolver"]) in ("completed", "partially_completed")
    seen = len(crawl_env["requests"])
    with session_scope(org_id) as db:
        pages = db.execute(select(FetchedPage.id).where(FetchedPage.job_id == job_id)).all()
    assert pipeline.run_job(job_id, resolver=crawl_env["resolver"]) in ("completed", "partially_completed")
    assert len(crawl_env["requests"]) == seen
    with session_scope(org_id) as db:
        assert len(db.execute(select(FetchedPage.id).where(FetchedPage.job_id == job_id)).all()) == len(pages)


def test_duplicates_are_merged_by_dedupe_key(db_clean, crawl_env):
    url = crawl_env["url"]
    job_id, org_id = make_job([url("acme-security.test"), url("acme-mirror.test")],
                              deduplication_keys=["company_name"])
    pipeline.run_job(job_id, resolver=crawl_env["resolver"])
    names = [r.data["company_name"] for r in records(job_id, org_id)]
    assert names.count("Acme Security Ltd") == 1
    with session_scope(org_id) as db:
        job = db.get(CrawlJob, job_id)
        assert job.counters.get("records_duplicates", 0) >= 1


def test_job_with_only_blocked_start_urls_fails_clearly(db_clean, crawl_env):
    job_id, org_id = make_job(["http://169.254.169.254/latest/meta-data/", "http://localhost:8080/"])
    assert pipeline.run_job(job_id, resolver=crawl_env["resolver"]) == "failed"
    with session_scope(org_id) as db:
        job = db.get(CrawlJob, job_id)
        assert "No eligible starting pages" in job.error


def test_page_budget_is_enforced(db_clean, crawl_env):
    job_id, org_id = make_job([crawl_env["url"]("acme-security.test")])
    with session_scope(org_id) as db:
        schema = db.get(ExtractionSchema, db.get(CrawlJob, job_id).schema_id)
        schema.spec = {**schema.spec, "crawl": {**schema.spec["crawl"], "max_pages": 2}}
    pipeline.run_job(job_id, resolver=crawl_env["resolver"])
    with session_scope(org_id) as db:
        assert len(db.execute(select(FetchedPage.id).where(FetchedPage.job_id == job_id)).all()) <= 2


def test_discovery_hints_fill_fields_by_extractor(db_clean, crawl_env, monkeypatch):
    from app.crawl import runner
    from app.discovery.providers import DiscoveryResult

    url = crawl_env["url"]

    class FakeRegistry:
        name = "sec_edgar"

        async def discover(self, spec):
            return [DiscoveryResult(url("acme-security.test"), "sec_edgar",
                                    {"industry": "Services-Prepackaged Software", "_source": "test"})]

    monkeypatch.setattr(runner, "providers_for", lambda spec: [FakeRegistry()])
    fields = [*FIELDS, {"name": "company_industry", "type": "string", "semantic": "industry"}]
    job_id, org_id = make_job([], fields=fields, discovery={"providers": ["sec_edgar"], "industry": "software"})
    assert pipeline.run_job(job_id, resolver=crawl_env["resolver"]) == "completed"
    (record,) = records(job_id, org_id)
    assert record.data["company_industry"] == "Services-Prepackaged Software"
