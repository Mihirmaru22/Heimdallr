"""Run recording and replay, loose list-question phrasing, live extractor scope, verified-only reports."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

import argus.investigation.live_web.controller as controller_mod
import argus.investigation.live_web.search_sources as sources_mod
from argus.evals.list_benchmark import load_reference, normalize_name, score
from argus.investigation.claim_verification import is_gate_rejected, is_verified
from argus.investigation.live_web.controller import ControlledLiveWebRetriever
from argus.investigation.live_web.models import ControlledRetrievalLimits
from argus.investigation.live_web.run_recorder import RecordingCorpus, ReplayCorpus
from argus.investigation.live_web.search_sources import SearchSource
from argus.investigation.objective_parser import parse_enumeration_objective
from argus.investigation.orchestrator import InvestigationEngine
from argus.investigation.store import InvestigationStore
from argus.search.pipeline import SearchPipeline
from argus.terminal import OSINTTerminal

JOB_URL = "https://jobs.lever.co/norvale/123"
JOB_PAGE = """<html><head><title>PLM Administrator - Norvale Aerostructures</title>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"JobPosting",
 "title":"PLM Administrator","datePosted":"2026-09-30",
 "hiringOrganization":{"@type":"Organization","name":"Norvale Aerostructures"},
 "jobLocation":{"@type":"Place","address":{"addressLocality":"Wichita","addressRegion":"KS","addressCountry":"United States"}},
 "description":"<p>Administer our Quorvane Flux environment.</p>"}</script>
</head><body><main><h1>PLM Administrator</h1></main></body></html>"""
LIST_PAGE_URL = "https://news.example.org/top-firms"
# Labelled CEO lines of unrelated firms, as on a "top companies" page.
LIST_PAGE = """<html><head><title>Top manufacturers 2026</title></head><body><main>
<p>Chief Executive Officer: Talia Brandt.</p><p>CEO: Oren Mazur.</p>
<p>See api.listvendor.com for data. As of March 3, 2026 the list was approved.</p>
<p>Quorvane Flux is a product lifecycle platform.</p></main></body></html>"""


class _Engine:
    def __init__(self, urls: list[str]) -> None:
        self.urls = urls

    async def search(self, query: Any) -> Any:
        return SimpleNamespace(results=[SimpleNamespace(url=u, title=f"result {u}", snippet=f"{query.query} result") for u in self.urls])


def _client(routes: dict[str, httpx.Response]):
    def handler(request: httpx.Request) -> httpx.Response:
        return routes.get(f"{request.url.host}{request.url.path}", httpx.Response(404))

    def factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=5)

    return factory


@pytest.fixture
def fake_web(monkeypatch):
    monkeypatch.setattr(SearchPipeline, "is_safe_url", staticmethod(lambda url: True))
    monkeypatch.setattr(controller_mod, "create_safe_async_client", _client({
        "jobs.lever.co/robots.txt": httpx.Response(404),
        "jobs.lever.co/norvale/123": httpx.Response(200, text=JOB_PAGE, headers={"content-type": "text/html"}),
        "news.example.org/robots.txt": httpx.Response(404),
        "news.example.org/top-firms": httpx.Response(200, text=LIST_PAGE, headers={"content-type": "text/html"}),
    }))
    monkeypatch.setattr(sources_mod, "get_search_source", lambda name: SearchSource("fake", "search.example", lambda t: _Engine([JOB_URL, LIST_PAGE_URL])))

    def make() -> ControlledLiveWebRetriever:
        limits = ControlledRetrievalLimits(enforce_ssrf_protection=False, search_providers=("fake",), max_requests_per_host=60, max_requests_per_task=120)
        return ControlledLiveWebRetriever(limits=limits, snapshot_dir=tempfile.mkdtemp())

    return make


@pytest.mark.parametrize("question, obj, geo", [
    ("find me the which companies in uk uses the SAP ERP", "SAP ERP", "United Kingdom"),
    ("who uses Salesforce in Germany", "Salesforce", "Germany"),
    ("can you please tell me all the hospitals in Germany that use Epic", "Epic", "Germany"),
    ("which companies in usa uses the teamcenter", "Teamcenter", "United States"),
])
def test_loosely_phrased_list_questions_are_understood(question, obj, geo):
    enum = parse_enumeration_objective(question)
    assert enum is not None and (enum.object, enum.geography) == (obj, geo)


@pytest.mark.parametrize("question", [
    "why do companies use SAP",
    "how do banks use Temenos",
    "Who is the current CEO of Siemens?",
    "Does Ford use Siemens NX for vehicle design?",
])
def test_questions_that_are_not_list_requests_stay_general(question):
    assert parse_enumeration_objective(question) is None


def test_live_runs_do_not_attach_labelled_fields_to_the_topic(fake_web):
    engine = InvestigationEngine(corpus=fake_web(), store=InvestigationStore(tempfile.mkdtemp()))
    state = engine.run_to_completion(objective="Quorvane Flux product overview", max_steps=6)
    preds = {str(c.get("predicate")) for c in state.claims}
    assert not preds & {"officer", "infrastructure", "temporal_grounding", "title", "organization"}, preds
    assert not any(e.get("entity_type") == "EXECUTIVE_OFFICER" for e in state.entities.values() if isinstance(e, dict))


def test_recorded_run_replays_offline_with_the_same_findings(fake_web, tmp_path):
    question = "find me the which companies in the USA use Quorvane Flux"
    live = OSINTTerminal(export_dir=str(tmp_path / "live"), corpus=fake_web())
    live.run_cli(target=question, interactive=False)
    run_dir = live.run_dir
    assert run_dir is not None and (run_dir / "calls.jsonl").exists() and (run_dir / "meta.json").exists()
    recorded = json.loads((run_dir / "result.json").read_text())
    live_answers = {c["subject"] for c in recorded["claims"] if c["predicate"] == "USES_SOFTWARE" and is_verified(c)}
    assert "Norvale Aerostructures" in live_answers

    replay = ReplayCorpus(run_dir)
    assert replay.objective == question
    offline = OSINTTerminal(export_dir=str(tmp_path / "replay"), corpus=replay, record_runs=False)
    data = offline._execute_investigation(replay.objective)
    replay_answers = {c["subject"] for c in data["claims"] if c["predicate"] == "USES_SOFTWARE" and is_verified(c)}
    assert replay_answers == live_answers
    assert not replay.misses


def test_replay_reports_calls_the_recording_cannot_answer(tmp_path):
    inner = SimpleNamespace(evidence_records=[], search=lambda q, limit=5: [], get_by_url=lambda u: None)
    rec = RecordingCorpus(inner, tmp_path, objective="q")
    rec.search("first query")
    replay = ReplayCorpus(tmp_path)
    assert replay.search("first query") == [] and not replay.misses
    assert replay.search("a query the run never made") == []
    assert replay.misses == [("search", "a query the run never made")]


def test_reports_keep_rejected_candidates_out_of_the_findings(fake_web, tmp_path):
    terminal = OSINTTerminal(export_dir=str(tmp_path), corpus=fake_web(), record_runs=False)
    data = terminal._execute_investigation("companies in the USA using Quorvane Flux")
    assert not any(is_gate_rejected(c) for c in data["claims"])
    assert all(is_gate_rejected(c) for c in data["rejected_claims"])
    md = terminal.md_exporter.export_investigation(data).read_text()
    if data["rejected_claims"]:
        assert "Rejected Candidates (not findings)" in md


def test_gate_rejection_is_distinct_from_a_negative_finding():
    assert is_gate_rejected({"status": "UNVERIFIED", "verification": {"passed": False, "reason": "passage_not_in_evidence"}})
    assert not is_gate_rejected({"status": "NOT_FOUND", "verification": {"passed": False, "reason": "non_positive_status:NOT_FOUND"}})
    assert not is_gate_rejected({"status": "SUPPORTED", "verification": {"passed": True}})


def test_list_benchmark_scores_against_a_reference(tmp_path):
    ref = tmp_path / "ref.csv"
    ref.write_text("Notes\nCompany,State\nNorvale Aerostructures Inc.,KS\nKestrel Foods (Atlanta office),GA\nBrightline Tools,TX\n")
    names = load_reference(ref)
    assert names == ["Norvale Aerostructures Inc.", "Kestrel Foods (Atlanta office)", "Brightline Tools"]
    assert normalize_name("The Kestrel Foods, LLC") == "kestrel foods"
    passed = {"passed": True}
    result = {"claims": [
        {"subject": "Norvale Aerostructures", "predicate": "USES_SOFTWARE", "status": "SUPPORTED", "verification": passed},
        {"subject": "Kestrel Foods", "predicate": "USES_SOFTWARE", "status": "UNVERIFIED", "verification": {"passed": False, "reason": "x"}},
        {"subject": "Arden Labs", "predicate": "USES_SOFTWARE", "status": "SUPPORTED", "verification": passed},
    ]}
    report = score(result, names)
    assert report["recall"] == round(1 / 3, 3)
    assert report["found_in_reference"] == ["Norvale Aerostructures Inc."]
    assert report["found_not_in_reference"] == ["Arden Labs"]
    assert report["rejected_but_in_reference"] == ["Kestrel Foods (Atlanta office)"]
