"""Regression tests for objective-scoped extraction (V3 FC1 T04).

For an organization-enumeration objective, incidental page artefacts (CDN hosts,
payment scripts, support e-mails) must not become findings or trigger follow-up
investigations, and the deployment extractor must take the product from the
objective and tolerate common table/prose layouts instead of one provider's layout.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any

import pytest

from argus.investigation.action import ActionType, ResearchAction
from argus.investigation.benchmark.corpus import InvestigationDocument
from argus.investigation.planner import InvestigationPlanner
from argus.investigation.question import QuestionType
from argus.investigation.store import InvestigationStore
from argus.investigation.technographics import extract_technographic_deployments


PROVIDER_URL = "https://theirstack.com/en/technology/siemens-teamcenter/us"
TC = ["Siemens Teamcenter", "Teamcenter"]
HEADER = "API Export Company Country Industry Employees Revenue Technologies "
ROWS = (
    "Northrop Grumman United States Defense and Space Manufacturing 95k $39B {p} "
    "Honeywell United States Appliances, Electrical, and Electronics Manufacturing 95k $36B {p} "
    "Ford Motor Company United States Motor Vehicle Manufacturing 177k $176B {p} "
    "Hermeus United States Aviation and Aerospace Component Manufacturing 140 {p}"
)
# Stand-in provider page: table rows from the repo's existing fixture, wrapped in
# illustrative navigation/footer artefacts. Not live data.
PAGE = (
    "Companies that use Siemens Teamcenter in United States | TheirStack "
    "Pricing Docs Blog Log in Try for free. Use our API at https://api.theirstack.com/v1/companies/search or "
    "status.theirstack.com. Payments secured by js.stripe.com. Widgets load from cdn.jsdelivr.net. "
    + HEADER + ROWS.format(p="Siemens Teamcenter") + " Contact support@theirstack.com. Data is collected from job postings."
)
# Real DuckDuckGo results recorded in the 2026-10-14 Teamcenter export (git 93eb9de).
SNIPPETS = [
    (PROVIDER_URL, "Companies that use Siemens Teamcenter in United States",
     "Download a list of 592 companies that use Siemens Teamcenter in United States with enriched data including industry, company size, location, funding rounds, and revenue figures."),
    ("https://theirstack.com/en/technology/siemens-teamcenter", "Companies that use Siemens Teamcenter - theirstack.com",
     "Download a list of 2,604 companies that use Siemens Teamcenter with enriched data including industry, company size, location, funding rounds, and revenue figures."),
    ("https://data.landbase.com/technology/siemens-teamcenter-plm-software/", "Companies using Siemens Teamcenter PLM Software in 2026 | Landbase",
     "Siemens Teamcenter PLM Software by Siemens is a comprehensive Product Lifecycle Management (PLM) platform that centralizes product information and processes."),
]


class FixtureCorpus:
    """Offline stand-in for the live retriever: recorded snippets plus one stand-in page."""

    def __init__(self, snippets: list[tuple[str, str, str]], pages: dict[str, str]) -> None:
        self.snippets = snippets
        self.pages = pages
        self.documents: dict[str, Any] = {}
        self.calls: list[tuple[str, str]] = []

    def get_discoverable_entities(self) -> set[str]:
        return set()

    def search(self, query: str, limit: int = 5) -> list[Any]:
        self.calls.append(("search", query))
        if query.startswith("http"):
            doc = self.get_by_url(query)
            return [doc] if doc else []
        out = []
        for url, title, snippet in self.snippets[:limit]:
            doc = InvestigationDocument(doc_id="s_" + url[-12:], title=title, url=url,
                                        text_content=f"{title}\n\n{snippet}", source_type="live_search",
                                        published_date="2026-10-16")
            self.documents[doc.doc_id] = doc
            out.append(doc)
        return out

    def get_by_url(self, url: str) -> Any:
        self.calls.append(("fetch", url))
        if url in self.pages:
            return InvestigationDocument(doc_id="p_" + url[-12:], title=f"Page {url[-20:]}", url=url,
                                         text_content=self.pages[url], source_type="live_web", published_date="2026-10-16")
        return None


def _run_terminal(objective: str, corpus: FixtureCorpus) -> tuple[dict[str, Any], Any]:
    import argus.terminal as T
    from argus.terminal import OSINTTerminal

    orig_sleep = T.time.sleep
    T.time.sleep = lambda *_: None
    try:
        term = OSINTTerminal(export_dir=tempfile.mkdtemp(), corpus=corpus)
        data = term._execute_investigation(objective)
    finally:
        T.time.sleep = orig_sleep
    return data, term


def test_teamcenter_fixture_yields_companies_and_no_incidental_findings_or_investigations():
    corpus = FixtureCorpus(SNIPPETS, {PROVIDER_URL: PAGE})
    data, term = _run_terminal("Search Companies who are using TEAMCENTER in usa", corpus)

    deployments = {c["subject"]: c for c in data["claims"] if str(c["predicate"]).startswith("USES_")}
    assert set(deployments) == {"Northrop Grumman", "Honeywell", "Ford Motor Company", "Hermeus"}
    for c in deployments.values():
        assert c["object"] == "Siemens Teamcenter"
        assert c["status"] == "TECHNOGRAPHIC_PROVIDER_ASSERTION"
        assert c["confidence"] is None
        assert c["citation"] == PROVIDER_URL
        assert c["subject"] in c["source_passage"] and "Siemens Teamcenter" in c["source_passage"]

    # No host / e-mail / page-furniture artefacts as entities or claims.
    for name in data["entities"]:
        assert not any(h in name for h in ("stripe", "jsdelivr", "theirstack.com", "@")), name
    assert not [c for c in data["claims"] if c["predicate"] in ("infrastructure", "admin_contact")]

    # No follow-up investigations of incidental hosts or of the companies' "identity".
    state = term.engine.store.load_state(data["investigation_id"])
    chained = [q for q in state.questions.values()
               if q["question_type"] in (QuestionType.INFRASTRUCTURE_ATTRIBUTION, QuestionType.IDENTITY_CORRELATION)]
    assert not chained
    searched = [q for kind, q in corpus.calls if kind == "search"]
    assert searched and all("Teamcenter" in q for q in searched)
    assert not any(h in q for q in searched for h in ("stripe", "jsdelivr", "api.theirstack"))


def test_unknown_product_works_end_to_end_without_code_knowledge():
    product = "Quorvane Flux"
    src_root = Path(__file__).resolve().parents[2] / "src"
    assert not any(product.lower() in p.read_text(encoding="utf-8", errors="ignore").lower()
                   for p in src_root.rglob("*.py")), "test product must not appear in the code"

    url = "https://stackintel.example/technology/quorvane-flux/us"
    page = "Companies using Quorvane Flux. Payments by js.stripe.com. " + HEADER + ROWS.format(p="Quorvane Flux")
    snippets = [
        (url, "Companies that use Quorvane Flux in the United States", "Find companies that use Quorvane Flux."),
        ("https://news.example.org/flux", "Brightline adopts Quorvane Flux", "Brightline Logistics has standardized on Quorvane Flux for routing."),
    ]
    corpus = FixtureCorpus(snippets, {url: page})
    data, term = _run_terminal("which companies in the USA are using Quorvane Flux", corpus)

    companies = {c["subject"] for c in data["claims"] if str(c["predicate"]).startswith("USES_")}
    assert {"Northrop Grumman", "Honeywell", "Ford Motor Company", "Hermeus"} <= companies
    assert "Brightline Logistics" in companies
    assert not [e for e in data["entities"] if "stripe" in e]
    state = term.engine.store.load_state(data["investigation_id"])
    assert state.objective_contract["enumeration_objective"]["object"] == product


@pytest.mark.parametrize(
    "row, company, country, employees, revenue",
    [
        ("Ford Motor Company United States Motor Vehicle Manufacturing 177,000 $176.2B Siemens Teamcenter", "Ford Motor Company", "United States", "177,000", "$176.2B"),
        ("Ford Motor Company ford.com United States Motor Vehicle Manufacturing 177k $176B Siemens Teamcenter", "Ford Motor Company", "United States", "177k", "$176B"),
        ("Ford Motor Company US Motor Vehicle Manufacturing 177k $176B Siemens Teamcenter", "Ford Motor Company", "United States", "177k", "$176B"),
        ("Ford Motor Company United States Motor Vehicle Manufacturing 177k $176B Siemens NX, Siemens Teamcenter", "Ford Motor Company", "United States", "177k", "$176B"),
        ("Ford Motor Company United States Motor Vehicle Manufacturing 177k $176B High Siemens Teamcenter", "Ford Motor Company", "United States", "177k", "$176B"),
        ("iRobot United States Consumer Electronics 1k $890M Siemens Teamcenter", "iRobot", "United States", "1k", "$890M"),
        ("Bank of America United States Banking 200k $90B Siemens Teamcenter", "Bank of America", "United States", "200k", "$90B"),
        ("Lockheed Martin Employees 88k · Revenue $35B · Defense and Space Manufacturing Siemens Teamcenter", "Lockheed Martin", "", "88k", "$35B"),
    ],
)
def test_layout_variants_yield_clean_company_rows(row, company, country, employees, revenue):
    findings = extract_technographic_deployments(row, doc_url=PROVIDER_URL, products=TC, geography="United States")
    assert [f.company for f in findings] == [company]
    f = findings[0]
    assert (f.country, f.employees, f.revenue) == (country, employees, revenue)
    assert f.software == "Siemens Teamcenter"
    assert f.evidence_quote in row and f.evidence_quote.startswith(company)


@pytest.mark.parametrize(
    "sentence, company",
    [
        ("Hyundai Motor Group has standardized on Teamcenter for vehicle programs.", "Hyundai Motor Group"),
        ("In 2024 Acme Aerospace selected Siemens Teamcenter to manage configuration.", "Acme Aerospace"),
        ("Boeing uses Siemens Teamcenter across programs.", "Boeing"),
    ],
)
def test_usage_sentences_are_extracted(sentence, company):
    findings = extract_technographic_deployments(sentence, doc_url="https://press.example/x", products=TC)
    assert [f.company for f in findings] == [company]


@pytest.mark.parametrize(
    "text",
    [
        "Globex does not use Teamcenter.",
        "Companies that use Siemens Teamcenter in United States | TheirStack Pricing Docs",
        "Download a list of 592 companies that use Siemens Teamcenter in United States.",
    ],
)
def test_non_assertions_and_page_titles_yield_nothing(text):
    assert extract_technographic_deployments(text, doc_url=PROVIDER_URL, products=TC, geography="United States") == []


def test_rows_outside_the_objective_geography_are_dropped_and_country_is_never_assumed():
    text = (
        "Tata Motors India Motor Vehicle Manufacturing 80k $40B Siemens Teamcenter "
        "Ford Motor Company United States Motor Vehicle Manufacturing 177k $176B Siemens Teamcenter. "
        "Boeing uses Siemens Teamcenter across programs."
    )
    findings = {f.company: f for f in extract_technographic_deployments(text, products=TC, geography="United States")}
    assert "Tata Motors" not in findings
    assert findings["Ford Motor Company"].country == "United States"
    assert findings["Boeing"].country == ""


def test_extractor_has_no_product_without_an_objective():
    assert extract_technographic_deployments("Boeing uses Siemens Teamcenter across programs.", target_query="Who is Ronak Raiyani") == []


def test_legacy_objectives_keep_their_extractors():
    """Scoping applies to enumeration objectives only; other objectives still extract relations."""
    from argus.investigation.orchestrator import InvestigationEngine

    engine = InvestigationEngine(corpus=FixtureCorpus([], {}), store=InvestigationStore(tempfile.mkdtemp()))
    state = InvestigationPlanner().initialize_investigation("Investigate Acme Orbital corporate structure", {"max_steps": 5})
    text = "Acme Orbital annual report. Wholly owned subsidiary: Acme Telemetry Ltd."
    action = ResearchAction(action_type=ActionType.FETCH, rationale="test", query="https://acme.example/report")
    engine._apply_observation(state, action, {
        "status": "SUCCESS",
        "documents": [{"url": "https://acme.example/report", "title": "Report", "text": text, "source_type": "live_web"}],
        "combined_text": "Report " + text,
    })
    assert any(c.get("predicate") == "subsidiary" for c in state.claims)


def test_narrative_template_is_not_selected_by_product_keywords():
    from argus.export.narrative import generate_narrative_intelligence

    out = generate_narrative_intelligence({"target": "Teamcenter history and architecture", "claims": [], "entities": {}, "evidence": []})
    assert "Enterprise Deployments" not in out["primary_name"]
