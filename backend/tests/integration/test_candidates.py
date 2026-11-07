"""Candidate recall: each answer-key company is placed at the first stage of the list it fell out of."""

from app.db import session_scope
from app.models import CompanyFact, CrawlJobEvent, DiscoveredUrl, Evidence
from app.services.candidates import (
    ELSEWHERE,
    NO_COUNTRY,
    NOT_NAMED,
    PROVEN_ALREADY,
    SEARCHABLE,
    candidate_recall,
    scorecard_rows,
)
from app.services.scorecard import score_job
from tests.integration.test_pipeline import make_job

KEY = {"must_include": [{"company": "Acme Widgets"}, {"company": "Beta Tools Ltd"}, {"company": "Gamma Foods"},
                        {"company": "Delta Labs"}, {"company": "Omega Mills"}]}


def test_each_expected_company_is_placed_at_the_stage_it_fell_out_of_the_list(db_clean):
    discovery = {"providers": ["wikidata", "case_studies"], "technology": "NetSuite", "countries": ["GB"]}
    job_id, org_id = make_job(["https://seed.example.test/"], discovery=discovery)
    with session_scope(org_id) as db:
        # A registry listed Acme in the UK: it could be searched by name.
        db.add(DiscoveredUrl(org_id=org_id, job_id=job_id, url="https://acme.example.test/", host="acme.example.test",
                             depth=0, method="wikidata", status="done", url_hash="h1",
                             hint={"company_name": "Acme Widgets", "country": "United Kingdom"}))
        # A proof page named Beta, but no source said where it is.
        db.add(Evidence(org_id=org_id, job_id=job_id, company="Beta Tools", product="NetSuite", quote="q",
                        url="https://partner.example.test/beta", verdict="Mentioned", kept=False))
        # Gamma is listed, and a registry places it in the US.
        db.add(CompanyFact(org_id=org_id, job_id=job_id, site="gamma.example.test", company="Gamma Foods",
                           kind="country", value="US", by="registry: gleif"))
        # Delta is proven and in the UK.
        db.add(Evidence(org_id=org_id, job_id=job_id, company="Delta Labs", product="NetSuite", quote="q",
                        url="https://www.netsuite.com/delta", verdict="Confirmed", kept=True))
        db.add(CompanyFact(org_id=org_id, job_id=job_id, site="delta.example.test", company="Delta Labs",
                           kind="country", value="GB", by="registry: wikidata"))
        db.add(CrawlJobEvent(org_id=org_id, job_id=job_id, type="info",
                             message="Discovery note: company_search: 40 of 120 listed companies searched"))

    with session_scope(org_id) as db:
        result = candidate_recall(db, job_id, KEY)
        card = score_job(db, job_id, KEY)

    stages = {r["company"]: r["stage"] for r in result["rows"]}
    assert stages == {"Acme Widgets": SEARCHABLE, "Beta Tools Ltd": NO_COUNTRY, "Gamma Foods": ELSEWHERE,
                      "Delta Labs": PROVEN_ALREADY, "Omega Mills": NOT_NAMED}
    named_by = {r["company"]: r["named by"] for r in result["rows"]}
    assert named_by["Acme Widgets"] == ["wikidata"] and named_by["Omega Mills"] == []
    rows = scorecard_rows(result)
    assert rows["key: candidate recall (named by a source)"] == "4/5 (80%)"
    assert rows["key: candidate recall (named, in the asked country)"] == "2/5 (40%)"
    assert rows[f"key: candidate stage: {NOT_NAMED}"] == "1 (Omega Mills)"
    assert rows["company search note 1"] == "company_search: 40 of 120 listed companies searched"
    assert card["key: candidate recall (named by a source)"] == "4/5 (80%)"
