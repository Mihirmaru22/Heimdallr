"""A technology question over a list of companies: each company's own pages are checked for proof."""

import json

from sqlalchemy import select

from app.db import session_scope
from app.evidence.judge import Judge
from app.llm.openrouter import Reply
from app.models import Evidence
from app.services import pipeline
from app.spec.models import ExtractionSpec
from tests.integration.test_pipeline import activity, make_job, records


class Router:
    async def chat(self, messages, **_kw):
        return Reply(json.dumps({"relationship": "uses", "quote": 1, "reason": "its engineers use it"}),
                     "minimax/minimax-m3.1-flash:free")

    async def aclose(self):
        pass


def test_companies_are_kept_only_with_proof_on_their_own_pages(db_clean, crawl_env, monkeypatch):
    from app.crawl import runner
    from app.discovery.providers import DiscoveryResult
    from app.evidence.site import SiteProof

    url = crawl_env["url"]

    class Search:
        name = "searxng"

        async def discover(self, spec):
            return [DiscoveryResult(url("initech.test"), "searxng", {"company_name": "Initech Trucks"}),
                    DiscoveryResult(url("acme-security.test"), "searxng", {"company_name": "Acme"})]

    monkeypatch.setattr(runner, "providers_for", lambda spec: [Search()])
    monkeypatch.setattr(runner, "SiteProof", lambda spec: SiteProof(spec, Judge(Router())))
    monkeypatch.setattr(runner.SiteChecker, "check", _passes)
    spec = ExtractionSpec.model_validate({"entity": "company", "fields": [
        {"name": "company_name", "type": "string", "semantic": "company_name", "required": True},
        {"name": "website_url", "type": "url", "semantic": "website_url"},
        {"name": "uses_technology", "type": "string", "required": True},
        {"name": "evidence", "type": "text"}, {"name": "evidence_url", "type": "url"},
        {"name": "evidence_date", "type": "date"}, {"name": "evidence_type", "type": "string"}],
        "discovery": {"providers": ["searxng"], "technology": "Teamcenter"}}).model_dump(mode="json")
    job_id, org_id = make_job([], fields=spec["fields"], discovery=spec["discovery"])
    assert pipeline.run_job(job_id, resolver=crawl_env["resolver"]) == "completed"

    by_name = {r.data["company_name"]: r for r in records(job_id, org_id)}
    initech = by_name["Initech Trucks"]
    assert not initech.excluded and initech.data["uses_technology"] == "Confirmed"
    assert initech.data["evidence"].startswith("Our engineers standardized on Siemens Teamcenter")
    assert initech.data["evidence_url"].endswith("/careers.html")
    assert str(initech.data["evidence_date"]) == "2026-03-02" and initech.data["evidence_type"] == "Company website"
    assert all(r.excluded for name, r in by_name.items() if name != "Initech Trucks")

    lines = activity(job_id, org_id)
    assert any(k == "kept" and m.startswith("Proof on initech.test") and "(Confirmed)" in m for k, m in lines)
    with session_scope(org_id) as db:
        rows = {e.company: e for e in db.execute(select(Evidence).where(Evidence.job_id == job_id)).scalars()}
    assert rows["Initech Trucks"].kept and rows["Initech Trucks"].judged_by.startswith("model:")
    assert not rows["Acme"].kept and rows["Acme"].reason.startswith("none of the") \
        and rows["Acme"].reason.endswith("names Teamcenter")


async def _passes(self, doc, spec):
    return None, "rules"
