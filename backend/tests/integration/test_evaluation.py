"""The test questions as a benchmark: past runs scored with the code they ran on, and new runs on the same plan."""

import json
from datetime import UTC, datetime

from app.db import session_scope
from app.models import CrawlJob, ExtractionSchema
from app.services import evaluation, pipeline
from tests.integration.test_pipeline import make_job


def test_runs_of_a_question_are_scored_oldest_first_with_their_code(db_clean, crawl_env, tmp_path, monkeypatch):
    url = crawl_env["url"]
    question = "Security companies with website and phone"
    first, org_id = make_job([url("acme-security.test")])
    with session_scope(bypass=True) as db:
        db.get(ExtractionSchema, db.get(CrawlJob, first).schema_id).nl_request = question
    assert pipeline.run_job(first, resolver=crawl_env["resolver"]) == "completed"
    log = tmp_path / "api.log"
    log.write_text("===== start.sh run 2000-01-01 10:00:00 +0000 claude/x abc1234 - Old =====\n")
    monkeypatch.setattr(evaluation, "API_LOG", log)
    key = {"question": "security companies, with website and phone!",
           "must_include": [{"company": "Acme Security", "website": url("acme-security.test")}]}

    with session_scope(bypass=True) as db:
        (new_name, previous, second), = evaluation.start_runs(db, {"acme": key})
        second_id = second.id
    assert new_name == "acme" and previous.id == first
    assert pipeline.run_job(second_id, resolver=crawl_env["resolver"]) == "completed"

    with session_scope(bypass=True) as db:
        rows = evaluation.history(db, {"acme": key})
        assert db.get(CrawlJob, second_id).schema_id == db.get(CrawlJob, first).schema_id  # the same plan
    assert [r["job"] for r in rows] == [str(first)[:8], str(second_id)[:8]]
    assert rows[0]["code"] == "abc1234"  # from start.sh's marker before the run
    assert rows[1]["code"] == (pipeline.code_version() or "abc1234")  # recorded on the job itself
    assert all(r["key: must-have companies found"].startswith("1/1") for r in rows)
    json.dumps(rows)


def test_code_starts_are_read_from_the_start_markers(tmp_path):
    log = tmp_path / "api.log"
    log.write_text("x\n===== start.sh run 2026-10-22 16:56:06 +0530 claude/site-done 5a9be5f - Site check =====\n")
    assert evaluation.code_starts(log) == [(datetime(2026, 10, 22, 11, 26, 6, tzinfo=UTC), "5a9be5f")]


def test_a_benchmark_run_can_take_the_sources_todays_rules_pick_and_keep_the_rest_of_the_plan(db_clean):
    job_id, _org = make_job([], discovery={"providers": ["seeds"], "technology": "SAP", "countries": ["US"]})
    with session_scope(bypass=True) as db:
        old = db.get(ExtractionSchema, db.get(CrawlJob, job_id).schema_id)
        new = evaluation.with_current_sources(db, old)
        assert new.id != old.id and new.version == old.version + 1
        assert new.spec["discovery"]["providers"] == ["sec_filings", "case_studies", "news"]
        assert {k: v for k, v in new.spec.items() if k != "discovery"} == \
            {k: v for k, v in old.spec.items() if k != "discovery"}
        assert evaluation.with_current_sources(db, new).id == new.id  # nothing to change: the same plan


def test_a_capped_health_check_run_does_not_become_the_benchmark_plan(db_clean):
    full, _ = make_job([], discovery={"providers": ["seeds"], "industry": "defense", "max_results": 50})
    capped, _ = make_job([], discovery={"providers": ["seeds"], "industry": "defense", "max_results": 10})
    with session_scope(bypass=True) as db:
        runs = [db.get(CrawlJob, full), db.get(CrawlJob, capped)]  # the capped one is the latest
        assert evaluation.plan_run(db, runs).id == full
        assert evaluation.plan_run(db, runs[:1]).id == full and evaluation.plan_run(db, []) is None
