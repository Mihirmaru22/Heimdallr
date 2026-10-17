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


# --- Local language-model reader -------------------------------------------------------------

from argus.evals.llm_citation_check import classify, extract_urls, run_urls  # noqa: E402
from argus.investigation.live_web.models import LiveWebEvidenceRecord  # noqa: E402
from argus.investigation.llm_reader import LLMReader, ReadFinding, _parse_findings, relation_predicate, snap_quote  # noqa: E402

CASE_URL = "https://stories.example.net/brightwater"
CASE_PAGE = """<html><head><title>Brightwater Foods | Customer story</title></head><body><main>
<h1>Closing the books faster</h1>
<p>The finance team at Brightwater Foods, in Leeds, United Kingdom, now runs month-end close on Quorvane Flux.</p>
<p>Harbor Mills in Ohio, United States, also runs month-end close on Quorvane Flux.</p>
</main></body></html>"""


class _FakeReader:
    label = "fake:model"

    def __init__(self, findings):
        self.findings, self.calls = findings, []

    def read(self, question, title, text, list_target=None):
        self.calls.append((question, list_target))
        return [f for f in self.findings if "Brightwater" in text or "Harbor" in text]


def test_snap_quote_returns_the_pages_own_words():
    page = "The finance team at Brightwater Foods now runs\n month-end close on Quorvane Flux."
    assert snap_quote("Brightwater Foods now runs month-end close on Quorvane Flux", page) == "Brightwater Foods now runs month-end close on Quorvane Flux"
    assert snap_quote("Brightwater Foods now run month end close on Quorvane Flux", page).startswith("Brightwater Foods now runs")
    assert snap_quote("Acme Corp signed a deal with Quorvane", page) == ""


def test_reader_parses_model_json_and_drops_quotes_not_on_the_page(monkeypatch):
    reader = LLMReader("ollama", "m", "http://localhost:11434")
    reply = json.dumps({"findings": [
        {"subject": "Brightwater Foods", "relation": "uses", "value": "Quorvane Flux", "country": "United Kingdom",
         "quote": "Brightwater Foods, in Leeds, United Kingdom, now runs month-end close on Quorvane Flux."},
        {"subject": "Made Up Ltd", "relation": "uses", "value": "Quorvane Flux", "quote": "Made Up Ltd uses Quorvane Flux everywhere."},
    ]})
    monkeypatch.setattr(reader, "_chat", lambda system, user: reply)
    found = reader.read("q", "t", "The finance team at Brightwater Foods, in Leeds, United Kingdom, now runs month-end close on Quorvane Flux.")
    assert [f.subject for f in found] == ["Brightwater Foods"]
    assert _parse_findings("no json here") == [] and relation_predicate("is headquartered in") == "is_headquartered_in"


def test_reader_is_off_unless_configured(monkeypatch):
    monkeypatch.delenv("HEIMDALLR_LLM", raising=False)
    assert LLMReader.from_env() is None
    monkeypatch.setenv("HEIMDALLR_LLM", "ollama:qwen2.5:7b-instruct")
    r = LLMReader.from_env()
    assert r is not None and (r.model, r.base_url) == ("qwen2.5:7b-instruct", "http://localhost:11434")


def test_model_findings_go_through_the_gate_and_the_geography(monkeypatch):
    monkeypatch.setattr(SearchPipeline, "is_safe_url", staticmethod(lambda url: True))
    monkeypatch.setattr(controller_mod, "create_safe_async_client", _client({
        "stories.example.net/robots.txt": httpx.Response(404),
        "stories.example.net/brightwater": httpx.Response(200, text=CASE_PAGE, headers={"content-type": "text/html"}),
    }))
    monkeypatch.setattr(sources_mod, "get_search_source", lambda name: SearchSource("fake", "search.example", lambda t: _Engine([CASE_URL])))
    limits = ControlledRetrievalLimits(enforce_ssrf_protection=False, search_providers=("fake",), max_requests_per_host=60, max_requests_per_task=120)
    reader = _FakeReader([
        ReadFinding("Brightwater Foods", "uses", "Quorvane Flux", "Brightwater Foods, in Leeds, United Kingdom, now runs month-end close on Quorvane Flux.", "United Kingdom"),
        ReadFinding("Harbor Mills", "uses", "Quorvane Flux", "Harbor Mills in Ohio, United States, also runs month-end close on Quorvane Flux.", "United States"),
        ReadFinding("Leeds Council", "uses", "Quorvane Flux", "Closing the books faster", ""),
    ])
    engine = InvestigationEngine(corpus=ControlledLiveWebRetriever(limits=limits, snapshot_dir=tempfile.mkdtemp()), store=InvestigationStore(tempfile.mkdtemp()), llm_reader=reader)
    state = engine.run_to_completion(objective="which companies in the UK use Quorvane Flux", max_steps=8)
    verified = {c["subject"] for c in state.claims if c.get("predicate") == "USES_SOFTWARE" and is_verified(c)}
    assert verified == {"Brightwater Foods"}, [(c.get("subject"), c.get("verification")) for c in state.claims]
    assert all(c.get("extracted_by") == "llm_reader:fake:model" for c in state.claims if c["subject"] == "Brightwater Foods")
    assert reader.calls and reader.calls[0][1] == ("organizations", "Quorvane Flux", "United Kingdom")


def test_citation_check_parses_links_and_classifies_outcomes(tmp_path):
    text = "See [Siemens](https://www.siemens.com/story/a). Also https://example.org/x, and https://example.org/x."
    assert extract_urls(text) == ["https://www.siemens.com/story/a", "https://example.org/x"]

    def rec(status, method="safe_html_text", err=None, text=""):
        return LiveWebEvidenceRecord("e", "u", "u", "t", status, "", "", "", text, "", "live_web", method, retrieval_error=err)

    assert classify(rec(403, "blocked", "robots.txt disallows this URL")) == "refused by robots.txt"
    assert classify(rec(200, text="x" * 500)) == "readable"
    assert classify(rec(200, text="x")).startswith("loads but little text")
    assert classify(rec(403)) == "site refused (HTTP 403)"
    (tmp_path / "calls.jsonl").write_text(json.dumps({"op": "search", "query": "q", "docs": [{"url": "https://www.siemens.com/story/a/"}]}) + "\n")
    assert run_urls(tmp_path) == ({"siemens.com/story/a"}, set())


# --- Search APIs, archive fallback, links given by the user ----------------------------------

import asyncio  # noqa: E402

from argus.investigation.live_web.search_sources import get_search_source  # noqa: E402
from argus.search.models import SearchQuery  # noqa: E402

ARTICLE = "<html><body><main><p>" + "Archived article text about Quorvane Flux customers. " * 10 + "</p></main></body></html>"


def _capture_client(routes, seen):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return routes.get(f"{request.url.host}{request.url.path}", httpx.Response(404))

    def factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=5)

    return factory


def test_search_apis_are_used_only_with_a_key(monkeypatch):
    for var in ("TAVILY_API_KEY", "EXA_API_KEY", "BRAVE_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    assert get_search_source("tavily") is None and get_search_source("exa") is None and get_search_source("brave") is None
    monkeypatch.setenv("EXA_API_KEY", "k")
    seen: list[httpx.Request] = []
    import argus.search.api_providers as api
    monkeypatch.setattr(api, "create_safe_async_client", _capture_client({
        "api.exa.ai/search": httpx.Response(200, json={"results": [{"url": "https://ex.example/a", "title": "A", "text": "Page   text\\nhere"}]}),
    }, seen))
    monkeypatch.setattr(SearchPipeline, "is_safe_url", staticmethod(lambda url: True))
    source = get_search_source("exa")
    resp = asyncio.run(source.make(5).search(SearchQuery(query="quorvane flux customers", num_results=5)))
    assert [(r.url, r.snippet) for r in resp.results] == [("https://ex.example/a", "Page text\\nhere")]
    assert seen[0].headers["x-api-key"] == "k" and json.loads(seen[0].content)["query"] == "quorvane flux customers"


def test_refused_page_is_read_from_the_archive_and_cited_as_archived(monkeypatch):
    seen: list[httpx.Request] = []
    monkeypatch.setattr(SearchPipeline, "is_safe_url", staticmethod(lambda url: True))
    monkeypatch.setattr(controller_mod, "create_safe_async_client", _capture_client({
        "blocked.example/robots.txt": httpx.Response(200, text="User-agent: *\nDisallow: /\n"),
        "archive.org/wayback/available": httpx.Response(200, json={"archived_snapshots": {"closest": {"available": True, "status": "200", "timestamp": "20260901120000", "url": "x"}}}),
        "web.archive.org/robots.txt": httpx.Response(404),
        "web.archive.org/web/20260901120000id_/https://blocked.example/story": httpx.Response(200, text=ARTICLE, headers={"content-type": "text/html"}),
    }, seen))
    limits = ControlledRetrievalLimits(enforce_ssrf_protection=False, max_requests_per_host=10, max_requests_per_task=20, archive_fallback=True)
    retriever = ControlledLiveWebRetriever(limits=limits, snapshot_dir=tempfile.mkdtemp())
    doc = retriever.get_by_url("https://blocked.example/story")
    assert doc is not None and doc.url.startswith("https://web.archive.org/web/20260901120000id_/")
    assert doc.title.startswith("[Archived copy 2026-09-01]")
    assert not any(r.url.host == "blocked.example" and r.url.path == "/story" for r in seen), "the refusing site itself is not fetched"

    off = ControlledLiveWebRetriever(limits=ControlledRetrievalLimits(enforce_ssrf_protection=False, max_requests_per_host=10, max_requests_per_task=20), snapshot_dir=tempfile.mkdtemp())
    assert off.get_by_url("https://blocked.example/story") is None


def test_link_in_the_question_is_fetched_as_a_user_request(monkeypatch):
    seen: list[httpx.Request] = []
    monkeypatch.setattr(SearchPipeline, "is_safe_url", staticmethod(lambda url: True))
    monkeypatch.setattr(controller_mod, "create_safe_async_client", _capture_client({
        "blocked.example/robots.txt": httpx.Response(200, text="User-agent: *\nDisallow: /\n"),
        "blocked.example/story": httpx.Response(200, text=ARTICLE, headers={"content-type": "text/html"}),
    }, seen))
    monkeypatch.setattr(sources_mod, "get_search_source", lambda name: None)
    limits = ControlledRetrievalLimits(enforce_ssrf_protection=False, max_requests_per_host=10, max_requests_per_task=20)
    retriever = ControlledLiveWebRetriever(limits=limits, snapshot_dir=tempfile.mkdtemp())
    engine = InvestigationEngine(corpus=retriever, store=InvestigationStore(tempfile.mkdtemp()))
    engine.run_to_completion(objective="summarise https://blocked.example/story", max_steps=4)
    page_requests = [r for r in seen if r.url.path == "/story"]
    assert page_requests and page_requests[0].headers["user-agent"].startswith("Heimdallr-User")
    # Other pages on the same site still follow robots.txt.
    assert retriever.get_by_url("https://blocked.example/other") is None
