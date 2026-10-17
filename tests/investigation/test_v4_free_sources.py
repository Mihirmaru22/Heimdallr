"""V4 phase 1 on free sources: multi-engine search, page reading, job posts, robots.txt."""

from __future__ import annotations

import json
import tempfile
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

import argus.investigation.live_web.controller as controller_mod
import argus.investigation.live_web.search_sources as sources_mod
from argus.investigation.claim_verification import is_verified, verify_claim
from argus.investigation.live_web.controller import ControlledLiveWebRetriever
from argus.investigation.live_web.models import ControlledRetrievalLimits
from argus.investigation.live_web.page_reader import read_page
from argus.investigation.live_web.search_sources import SearchSource, merge_results
from argus.investigation.objective_parser import parse_enumeration_objective
from argus.investigation.orchestrator import InvestigationEngine
from argus.investigation.planner import InvestigationPlanner
from argus.investigation.store import InvestigationStore
from argus.investigation.technographics import extract_technographic_deployments
from argus.search.pipeline import SearchPipeline
from argus.search.wikipedia import WikipediaSearchProvider

JOB_PAGE = """<html><head><title>PLM Administrator - Norvale Aerostructures</title>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"JobPosting",
 "title":"PLM Administrator","datePosted":"2026-09-30",
 "hiringOrganization":{"@type":"Organization","name":"Norvale Aerostructures"},
 "jobLocation":{"@type":"Place","address":{"addressLocality":"Wichita","addressRegion":"KS","addressCountry":"United States"}},
 "description":"<p>Administer our Quorvane Flux environment.</p><p>5+ years of PLM experience.</p>"}</script>
</head><body><nav>Home Jobs About Login</nav><header>Careers at Norvale</header>
<main><h1>PLM Administrator</h1><p>Join the engineering systems team in Wichita.</p></main>
<footer>Privacy Cookie settings</footer></body></html>"""


def _sr(url: str, title: str = "t", snippet: str = "") -> SimpleNamespace:
    return SimpleNamespace(url=url, title=title, snippet=snippet)


def test_merge_dedupes_by_url_and_ranks_agreement_first():
    merged = merge_results([
        ("a", [_sr("https://www.x.com/p/"), _sr("https://y.com/1")]),
        ("b", [_sr("https://y.com/2"), _sr("https://x.com/p", snippet="longer snippet")]),
    ], limit=10)
    assert merged[0].engines == ["a", "b"] and merged[0].result.snippet == "longer snippet"
    # Single-source results interleave by rank: each source's top hit before anyone's second.
    assert [m.result.url for m in merged[1:]] == ["https://y.com/2", "https://y.com/1"]


def test_wikipedia_results_parse_to_article_urls():
    data = {"query": {"search": [{"title": "Quorvane Flux", "snippet": "<span>Quorvane</span> Flux is a PLM suite"}]}}
    [r] = WikipediaSearchProvider().parse(data)
    assert r.url == "https://en.wikipedia.org/wiki/Quorvane_Flux" and r.snippet == "Quorvane Flux is a PLM suite"


class _Engine:
    def __init__(self, name: str, urls: list[str]) -> None:
        self.name, self.urls = name, urls

    async def search(self, query: Any) -> Any:
        return SimpleNamespace(results=[_sr(u, f"{self.name} {u}", f"{query.query} on {self.name}") for u in self.urls])


def test_retriever_queries_every_configured_source_within_host_budget(monkeypatch):
    engines = {
        "one": SearchSource("one", "one.example", lambda t: _Engine("one", ["https://a.com/1", "https://b.com/2"])),
        "two": SearchSource("two", "two.example", lambda t: _Engine("two", ["https://b.com/2", "https://c.com/3"])),
    }
    monkeypatch.setattr(sources_mod, "get_search_source", lambda name: engines.get(name))
    limits = ControlledRetrievalLimits(
        max_requests_per_host=1, enforce_ssrf_protection=False, search_providers=("one", "two", "missing"), min_results_per_search=5,
    )
    retriever = ControlledLiveWebRetriever(limits=limits, snapshot_dir=tempfile.mkdtemp())

    docs = retriever.search("quorvane flux customers", limit=3)
    assert [d.url for d in docs] == ["https://b.com/2", "https://a.com/1", "https://c.com/3"]
    assert retriever.requests_made == 2

    assert retriever.search("second query", limit=3) == []
    denied = {r.domain for r in retriever.evidence_records if r.extraction_method == "blocked"}
    assert denied == {"one.example", "two.example"}


def test_page_reader_keeps_main_content_and_job_posting_fields():
    page = read_page(JOB_PAGE.encode(), "text/html; charset=utf-8")
    assert page.method == "html_main_content"
    assert page.title == "PLM Administrator - Norvale Aerostructures"
    assert "Employer: Norvale Aerostructures" in page.text
    assert "Location: Wichita, KS, United States" in page.text
    assert "Administer our Quorvane Flux environment." in page.text
    assert "Join the engineering systems team in Wichita." in page.text
    for furniture in ("Login", "Cookie settings", "Careers at Norvale"):
        assert furniture not in page.text


def test_pdf_is_recognised_by_signature():
    page = read_page(b"%PDF-1.4 not really a pdf", "application/octet-stream")
    assert page.method in ("pdf_text", "pdf_unreadable") and page.text == ""


def test_job_posting_names_employer_and_passes_the_gate():
    text = read_page(JOB_PAGE.encode(), "text/html").text
    url = "https://jobs.lever.co/norvale/123"
    [finding] = extract_technographic_deployments(text, doc_url=url, products=["Quorvane Flux"], geography="United States")
    assert finding.company == "Norvale Aerostructures" and finding.country == "United States"
    claim = verify_claim({
        "subject": finding.company, "predicate": "USES_SOFTWARE", "object": finding.software,
        "status": finding.status, "evidence_id": "ev1", "source_url": url, "source_passage": finding.evidence_quote,
    }, [{"evidence_id": "ev1", "url": url, "text": text}])
    assert is_verified(claim)


def test_job_posting_in_another_country_is_dropped():
    text = read_page(JOB_PAGE.replace("United States", "Canada").encode(), "text/html").text
    assert extract_technographic_deployments(text, products=["Quorvane Flux"], geography="United States") == []


def test_enumeration_plans_job_post_queries():
    state = InvestigationPlanner().initialize_investigation("companies in Brazil using Quorvane Flux")
    queries = [q for qd in state.questions.values() for q in qd["search_queries"]]
    assert '"Quorvane Flux" site:jobs.lever.co' in queries
    assert parse_enumeration_objective("companies in Brazil using Quorvane Flux").job_post_queries()[0] == '"Quorvane Flux" jobs Brazil'


def _mock_client_factory(routes: dict[str, httpx.Response]):
    def handler(request: httpx.Request) -> httpx.Response:
        key = f"{request.url.host}{request.url.path}"
        return routes.get(key, httpx.Response(404))

    def factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs.pop("transport", None)
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=kwargs.get("timeout", 5))

    return factory


def test_robots_txt_disallow_is_honoured(monkeypatch):
    monkeypatch.setattr(SearchPipeline, "is_safe_url", staticmethod(lambda url: True))
    monkeypatch.setattr(controller_mod, "create_safe_async_client", _mock_client_factory({
        "example.org/robots.txt": httpx.Response(200, text="User-agent: *\nDisallow: /private/\n"),
        "example.org/public": httpx.Response(200, text="<html><body><p>Public page text here.</p></body></html>", headers={"content-type": "text/html"}),
    }))
    retriever = ControlledLiveWebRetriever(limits=ControlledRetrievalLimits(enforce_ssrf_protection=False), snapshot_dir=tempfile.mkdtemp())
    assert retriever.get_by_url("https://example.org/private/x") is None
    assert any("disallows" in (r.retrieval_error or "") for r in retriever.evidence_records)
    doc = retriever.get_by_url("https://example.org/public")
    assert doc is not None and "Public page text here." in doc.text_content


def test_offline_run_finds_employer_from_a_job_post(monkeypatch):
    """Search hit on a job board -> page fetched -> JSON-LD job post -> verified USES_SOFTWARE claim."""
    job_url = "https://jobs.lever.co/norvale/123"
    monkeypatch.setattr(SearchPipeline, "is_safe_url", staticmethod(lambda url: True))
    monkeypatch.setattr(controller_mod, "create_safe_async_client", _mock_client_factory({
        "jobs.lever.co/robots.txt": httpx.Response(404),
        "jobs.lever.co/norvale/123": httpx.Response(200, text=JOB_PAGE, headers={"content-type": "text/html"}),
    }))
    engine_src = SearchSource("fake", "search.example", lambda t: _Engine("fake", [job_url]))
    monkeypatch.setattr(sources_mod, "get_search_source", lambda name: engine_src)
    limits = ControlledRetrievalLimits(enforce_ssrf_protection=False, search_providers=("fake",), max_requests_per_host=20, max_requests_per_task=40)
    retriever = ControlledLiveWebRetriever(limits=limits, snapshot_dir=tempfile.mkdtemp())
    engine = InvestigationEngine(corpus=retriever, store=InvestigationStore(tempfile.mkdtemp()))

    state = engine.run_to_completion(objective="companies in the USA using Quorvane Flux", max_steps=8)

    claims = [c for c in state.claims if c.get("predicate") == "USES_SOFTWARE" and c.get("subject") == "Norvale Aerostructures"]
    assert claims and is_verified(claims[0]), [(c.get("subject"), c.get("verification")) for c in state.claims]
    assert claims[0]["source_url"] == job_url


@pytest.mark.parametrize("text", [
    "In 2004, SAP released SAP ERP as the successor of R/3.",  # sentence opening + year
    "Versions and Modules: SAP ERP\nSAP ERP has several modules.",  # heading
    "History 1972 SAP ERP",  # heading + one number
])
def test_headings_and_sentence_openings_are_not_companies(text):
    assert extract_technographic_deployments(text, products=["SAP ERP"], geography="India") == []


def test_real_rows_and_usage_sentences_still_extract():
    rows = "Company Domain Country Employees\nRavensworth Tools ravensworth.in India 1200 SAP ERP\nKestrel Foods, India, 5,400 employees SAP ERP"
    found = {f.company for f in extract_technographic_deployments(rows, products=["SAP ERP"], geography="India")}
    assert found == {"Ravensworth Tools", "Kestrel Foods"}
    prose = "Bharat Ceramics uses SAP ERP across its plants."
    assert [f.company for f in extract_technographic_deployments(prose, products=["SAP ERP"])] == ["Bharat Ceramics"]


def test_list_question_keeps_searching_after_first_answer_and_reports_consistently(monkeypatch):
    job_url = "https://jobs.lever.co/norvale/123"
    monkeypatch.setattr(SearchPipeline, "is_safe_url", staticmethod(lambda url: True))
    monkeypatch.setattr(controller_mod, "create_safe_async_client", _mock_client_factory({
        "jobs.lever.co/robots.txt": httpx.Response(404),
        "jobs.lever.co/norvale/123": httpx.Response(200, text=JOB_PAGE, headers={"content-type": "text/html"}),
    }))
    seen: list[str] = []

    class _Recording(_Engine):
        async def search(self, query: Any) -> Any:
            seen.append(query.query)
            return await super().search(query)

    monkeypatch.setattr(sources_mod, "get_search_source", lambda name: SearchSource("fake", "search.example", lambda t: _Recording("fake", [job_url])))
    limits = ControlledRetrievalLimits(enforce_ssrf_protection=False, search_providers=("fake",), max_requests_per_host=40, max_requests_per_task=80)
    retriever = ControlledLiveWebRetriever(limits=limits, snapshot_dir=tempfile.mkdtemp())
    engine = InvestigationEngine(corpus=retriever, store=InvestigationStore(tempfile.mkdtemp()))

    state = engine.run_to_completion(objective="companies in the USA using Quorvane Flux", max_steps=30)

    enum = state.objective_contract["enumeration_objective"]
    discovery = state.questions[enum["question_ids"]["discovery"]]
    assert set(discovery["search_queries"]) <= set(seen), "every discovery query runs, not just the first"
    if state.stop_state.stop_reason == "OBJECTIVE_SATISFIED":
        assert not any(lim.startswith("Unresolved critical gap") for lim in state.generate_limitations())
