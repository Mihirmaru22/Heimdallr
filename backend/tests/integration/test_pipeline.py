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
    # A detail no test page has, so these crawls read every page instead of stopping once all are found.
    {"name": "never_found", "type": "string", "rules": {"css": ["#no-such-element"]}},
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
    assert statuses[url("flaky.test")] == ("blocked_robots", "robots.txt unreachable (http 503); treated as disallow")
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


def test_a_later_source_fills_hints_for_a_site_found_earlier(db_clean, crawl_env, monkeypatch):
    from app.crawl import runner
    from app.discovery.providers import DiscoveryResult

    url = crawl_env["url"]

    class Source:
        def __init__(self, name, hint):
            self.name, self.hint = name, hint

        async def discover(self, spec):
            return [DiscoveryResult(url("acme-security.test"), self.name, self.hint)]

    monkeypatch.setattr(runner, "providers_for", lambda spec: [
        Source("wikidata", {"company_name": "Acme Security", "_source": "wd"}),
        Source("sec_edgar", {"company_name": "ACME SECURITY INC", "industry": "Software", "_source": "sec"})])
    fields = [*FIELDS, {"name": "company_industry", "type": "string", "semantic": "industry"}]
    job_id, org_id = make_job([], fields=fields,
                              discovery={"providers": ["wikidata", "sec_edgar"], "industry": "security"})
    assert pipeline.run_job(job_id, resolver=crawl_env["resolver"]) == "completed"
    with session_scope(org_id) as db:
        seeds = db.execute(select(DiscoveredUrl).where(DiscoveredUrl.job_id == job_id,
                                                       DiscoveredUrl.depth == 0)).scalars().all()
    assert len(seeds) == 1 and seeds[0].method == "wikidata"
    assert seeds[0].hint == {"company_name": "Acme Security", "industry": "Software", "_source": "wd"}


def test_off_topic_search_results_are_dropped_before_crawling(db_clean, crawl_env, monkeypatch):
    from app.crawl import runner
    from app.discovery.providers import DiscoveryResult

    url = crawl_env["url"]

    class Search:
        name = "searxng"

        async def discover(self, spec):
            return [DiscoveryResult(url("acme-security.test"), "searxng", {})]

    monkeypatch.setattr(runner, "providers_for", lambda spec: [Search()])
    job_id, org_id = make_job([], discovery={"providers": ["searxng"], "industry": "pharmaceutical"})
    pipeline.run_job(job_id, resolver=crawl_env["resolver"])
    status, reason = urls_by_status(job_id, org_id)[url("acme-security.test")]
    assert status == "skipped" and "does not mention 'pharmaceutical'" in reason
    assert records(job_id, org_id) == []


def test_every_source_gets_a_share_of_the_budget(db_clean, crawl_env, monkeypatch):
    from app.crawl import runner
    from app.discovery.providers import DiscoveryResult

    url = crawl_env["url"]

    class Source:
        def __init__(self, name, hosts):
            self.name, self.hosts = name, hosts

        async def discover(self, spec):
            return [DiscoveryResult(url(h), self.name, {}) for h in self.hosts]

    # Wikidata alone could fill the budget of 3; the others must still contribute.
    monkeypatch.setattr(runner, "providers_for", lambda spec: [
        Source("wikidata", ["w1.test", "w2.test", "w3.test"]), Source("sec_edgar", ["s1.test", "s2.test"]),
        Source("searxng", ["x1.test"])])
    job_id, org_id = make_job([], discovery={"providers": ["wikidata", "sec_edgar", "searxng"], "industry": "x",
                                             "max_results": 3})
    pipeline.run_job(job_id, resolver=crawl_env["resolver"])
    with session_scope(org_id) as db:
        methods = sorted(db.execute(select(DiscoveredUrl.method).where(
            DiscoveredUrl.job_id == job_id, DiscoveredUrl.depth == 0)).scalars().all())
    assert methods == ["searxng", "sec_edgar", "wikidata"]


def activity(job_id, org_id):
    from app.models import CrawlJobEvent

    with session_scope(org_id) as db:
        rows = db.execute(select(CrawlJobEvent).where(CrawlJobEvent.job_id == job_id,
                                                      CrawlJobEvent.type == "activity")
                          .order_by(CrawlJobEvent.id)).scalars().all()
        return [(r.data["kind"], r.message) for r in rows]


def test_the_activity_feed_shows_each_real_step(db_clean, crawl_env, monkeypatch):
    from app.crawl import runner
    from app.discovery.providers import DiscoveryResult

    url = crawl_env["url"]

    class Search:
        name = "searxng"

        async def discover(self, spec):
            return [DiscoveryResult(url("acme-security.test"), "searxng", {"company_name": "Acme"}),
                    DiscoveryResult(url("globex.test"), "searxng", {})]

    monkeypatch.setattr(runner, "providers_for", lambda spec: [Search()])
    monkeypatch.setattr(runner, "RECORDS_EVERY", 0)  # refresh the records after every batch
    job_id, org_id = make_job([], discovery={"providers": ["searxng"], "industry": "security"})
    pipeline.run_job(job_id, resolver=crawl_env["resolver"])
    lines = activity(job_id, org_id)
    kinds = [k for k, _ in lines]
    assert lines[0] == ("search", "Searching web search for security companies")
    assert ("search", "Web search returned 2 website(s)") in lines
    assert any(k == "queued" and "Acme (acme-security.test)" in m for k, m in lines)
    assert any(k == "read" and m.startswith("Reading http://acme-security.test") for k, m in lines)
    assert any(k == "kept" and "acme-security.test" in m for k, m in lines)
    assert any(k == "found" and "+442079460958" in m for k, m in lines)
    assert any(k == "blocked" and "/private/secret.html" in m for k, m in lines)
    assert kinds.count("records") == 1  # assembled while the crawl ran, and noted only when the count changed

    # The Events tab keeps its short list; the feed has its own endpoint.
    from app.api.jobs import events
    from app.deps import OrgContext

    with session_scope(org_id) as db:
        ctx = OrgContext.__new__(OrgContext)
        ctx.org = db.get(Organization, org_id)
        assert all(e.type != "activity" for e in events(job_id, ctx, db, 0, 1000))


def test_a_busy_site_does_not_get_every_worker(db_clean, crawl_env):
    from app.crawl.runner import CrawlRunner
    from app.models import UrlStatus

    url = crawl_env["url"]
    job_id, org_id = make_job([])
    with session_scope(org_id) as db:
        spec = ExtractionSpec.model_validate(db.get(ExtractionSchema, db.get(CrawlJob, job_id).schema_id).spec)
    r = CrawlRunner(job_id, org_id, spec, resolver=crawl_env["resolver"])
    r.add_urls([{"url": url("acme-security.test", f"/p{i}"), "method": "seed"} for i in range(5)]
               + [{"url": url("globex.test", "/"), "method": "seed", "depth": 1}])  # lower priority
    r.busy_hosts = {"acme-security.test": r.settings.per_domain_concurrency}
    row = r.claim_fair()
    assert row.host == "globex.test" and row.status == UrlStatus.in_progress
    assert r.claim_fair() is None  # acme is at its share and globex has nothing more


def test_a_site_queues_only_about_twice_its_page_budget(db_clean, crawl_env):
    job_id, org_id = make_job([crawl_env["url"]("acme-security.test")],
                              crawl={"start_urls": [crawl_env["url"]("acme-security.test")], "max_pages": 30,
                                     "max_depth": 2, "max_pages_per_site": 1})
    pipeline.run_job(job_id, resolver=crawl_env["resolver"])
    assert len(urls_by_status(job_id, org_id)) <= 1 + 2  # the start page, then at most 2 x 1 more


def test_a_site_is_left_once_every_detail_is_found(db_clean, crawl_env):
    url = crawl_env["url"]
    fields = [f for f in FIELDS if f["name"] != "never_found"]
    job_id, org_id = make_job([url("acme-security.test")], fields=fields)
    assert pipeline.run_job(job_id, resolver=crawl_env["resolver"]) == "completed"
    statuses = urls_by_status(job_id, org_id)
    fetched = [u for u, (st, _r) in statuses.items() if st == "fetched"]
    # The homepage had every detail, so none of the site's other pages were even queued.
    assert fetched == [url("acme-security.test")] and len(statuses) == 1
    assert ("kept", "Every detail found for acme-security.test after 1 page(s); moving on") \
        in activity(job_id, org_id)
    (acme,) = records(job_id, org_id)
    assert acme.data["phone"] == "+442079460958" and acme.status == "valid"


def test_a_company_whose_listed_homepage_moved_is_read_on_its_new_domain(db_clean, crawl_env):
    url = crawl_env["url"]
    fields = [f for f in FIELDS if f["name"] != "never_found"]
    job_id, org_id = make_job([url("acme-old.test")], fields=fields)
    assert pipeline.run_job(job_id, resolver=crawl_env["resolver"]) == "completed"
    (acme,) = records(job_id, org_id)
    assert acme.data["phone"] == "+442079460958"
    assert any(m.startswith("acme-old.test moved to acme-security.test") for _k, m in activity(job_id, org_id))


def _wikidata(url, hint, monkeypatch):
    from app.crawl import runner
    from app.discovery.providers import DiscoveryResult

    class Source:
        name = "wikidata"

        async def discover(self, spec):
            return [DiscoveryResult(url, "wikidata", hint)]

    async def unchecked(self, doc, spec):
        return None, "unchecked: no model in tests"

    monkeypatch.setattr(runner, "providers_for", lambda spec: [Source()])
    monkeypatch.setattr(runner.SiteChecker, "check", unchecked)


def test_a_registry_industry_is_not_undone_by_a_missing_word_on_the_homepage(db_clean, crawl_env, monkeypatch):
    # Wikidata matched the company on its industry; its homepage never uses that word (it says "medicines").
    url = crawl_env["url"]
    _wikidata(url("acme-security.test"), {"company_name": "Acme", "industry": "pharmaceutical industry"},
              monkeypatch)
    job_id, org_id = make_job([], discovery={"providers": ["wikidata"], "industry": "pharmaceutical"})
    pipeline.run_job(job_id, resolver=crawl_env["resolver"])
    assert urls_by_status(job_id, org_id)[url("acme-security.test")][0] == "fetched"

    # Without the registry's industry, the homepage's own words still decide.
    _wikidata(url("acme-security.test"), {"company_name": "Acme"}, monkeypatch)
    job_id, org_id = make_job([], discovery={"providers": ["wikidata"], "industry": "pharmaceutical"})
    pipeline.run_job(job_id, resolver=crawl_env["resolver"])
    status, reason = urls_by_status(job_id, org_id)[url("acme-security.test")]
    assert status == "skipped" and "does not mention" in reason


def test_a_homepage_with_no_text_is_not_judged_on_its_content(db_clean, crawl_env, monkeypatch):
    url = crawl_env["url"]
    _wikidata(url("loader.test"), {"company_name": "Loader"}, monkeypatch)
    job_id, org_id = make_job([], discovery={"providers": ["wikidata"], "industry": "pharmaceutical"})
    pipeline.run_job(job_id, resolver=crawl_env["resolver"])
    assert urls_by_status(job_id, org_id)[url("loader.test")][0] == "fetched"
    assert any("could not be read" in m for _k, m in activity(job_id, org_id))


def test_a_second_delivery_of_a_job_a_worker_is_busy_with_does_nothing(db_clean, crawl_env):
    from app.db import utcnow

    job_id, org_id = make_job([crawl_env["url"]("acme-security.test")])
    with session_scope(org_id) as db:
        job = db.get(CrawlJob, job_id)
        job.state, job.heartbeat_at = "planning", utcnow()
    assert pipeline.run_job(job_id, resolver=crawl_env["resolver"]) == "running_elsewhere"
    with session_scope(org_id) as db:
        assert db.get(CrawlJob, job_id).state == "planning"  # untouched


def test_the_heartbeat_is_written_while_a_worker_holds_the_job(db_clean):
    import time

    job_id, org_id = make_job([])
    with pipeline._beating(job_id, org_id, every=0.05):
        time.sleep(0.3)
    with session_scope(org_id) as db:
        assert db.get(CrawlJob, job_id).heartbeat_at is not None


def _hit(url, provider="tavily", title="", snippet=""):
    return {"provider": provider, "query": "cybersecurity companies United Kingdom", "url": url, "title": title,
            "snippet": snippet}


def test_only_these_countries_reads_company_pages_when_the_homepage_does_not_say(db_clean, crawl_env, monkeypatch):
    """Confirmed in the country (from its contact page), confirmed outside it, and not confirmed: each is told
    apart, the first is kept and the other two stay out, with the reason and what search said about them."""
    from app.crawl import runner
    from app.discovery.providers import DiscoveryResult
    from app.models import CrawlJobEvent

    url = crawl_env["url"]

    class Search:
        name = "searxng"

        async def discover(self, spec):
            return [DiscoveryResult(url(h), "searxng", {"_source": url(h), "_search": [_hit(url(h), **kw)]})
                    for h, kw in (("northwind.test", {}), ("southwind.test", {"provider": "linkup"}),
                                  ("eastwind.test", {"title": "Eastwind", "snippet": "A UK cyber security firm"}))]

    monkeypatch.setattr(runner, "providers_for", lambda spec: [Search()])
    job_id, org_id = make_job([], discovery={"providers": ["searxng"], "industry": "cybersecurity",
                                             "countries": ["GB"]})
    pipeline.run_job(job_id, resolver=crawl_env["resolver"])
    seen = urls_by_status(job_id, org_id)

    status, reason = seen[url("southwind.test")]
    assert status == "skipped" and reason.startswith("outside the requested countries: based in US")
    assert "structured address on " + url("southwind.test", "/contact.html") in reason
    status, reason = seen[url("eastwind.test")]
    # "London" and "UK" in its text, and the snippet's "A UK cyber security firm", are not proof of where it is.
    assert status == "skipped" and reason.startswith("country not confirmed: could not confirm it is based in GB")
    assert url("eastwind.test", "/about.html") in reason
    assert "found by tavily for 'cybersecurity companies United Kingdom'" in reason and "A UK cyber" in reason
    assert seen[url("northwind.test")][0] == "fetched"
    with session_scope(org_id) as db:
        seed = db.execute(select(DiscoveredUrl).where(DiscoveredUrl.url == url("northwind.test"),
                                                      DiscoveredUrl.job_id == job_id)).scalar_one()
        assert seed.hint["_country"].startswith("based in GB (2 phone number(s) on ")
        assert seed.hint["_search"][0]["provider"] == "tavily"  # the hit stays with the site it found
        notes = db.execute(select(CrawlJobEvent.message).where(CrawlJobEvent.job_id == job_id,
                                                               CrawlJobEvent.type == "info")).scalars().all()
    assert ("Country check (only GB): 1 site(s) confirmed in the country, 1 confirmed outside it, "
            "1 not confirmed either way (left out)") in notes
    assert [r.data["company_name"] for r in records(job_id, org_id)] == ["Northwind Cyber"]


def test_a_value_from_a_source_is_traced_to_that_source(db_clean, crawl_env, monkeypatch):
    """A registry's name is selected over the page's own, and is traced to the registry, not to the homepage it
    was stored with; the page's own name stays as an alternative traced to the page."""
    from app.crawl import runner
    from app.discovery.providers import DiscoveryResult
    from app.models import FieldValue

    url = crawl_env["url"]
    item = "http://www.wikidata.org/entity/Q1"

    class Registry:
        name = "wikidata"

        async def discover(self, spec):
            return [DiscoveryResult(url("acme-security.test"), "wikidata",
                                    {"company_name": "Acme Security Group", "_source": item}, referrer=item)]

    monkeypatch.setattr(runner, "providers_for", lambda spec: [Registry()])
    job_id, org_id = make_job([], discovery={"providers": ["wikidata"], "industry": "security"})
    pipeline.run_job(job_id, resolver=crawl_env["resolver"])
    (record,) = records(job_id, org_id)
    with session_scope(org_id) as db:
        names = db.execute(select(FieldValue).where(FieldValue.record_id == record.id,
                                                    FieldValue.field_name == "company_name")).scalars().all()
    (chosen,) = [f for f in names if f.selected]
    assert (chosen.value, chosen.method, chosen.source_url, chosen.source_page_id) == (
        "Acme Security Group", "wikidata", item, None)
    assert any(f.value == "Acme Security Ltd" and f.source_url == url("acme-security.test") for f in names
               if not f.selected)
    assert item in record.source_urls
