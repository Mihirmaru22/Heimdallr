"""Regression tests for honest question resolution, termination and limitations (V3 FC1 T05).

A question is SUPPORTED only by a claim that passed the shared verification gate,
the run may report OBJECTIVE_SATISFIED / SUFFICIENT_EVIDENCE only when every critical
question is answered by evidence, and retrieval-budget denials are recorded so the
stop reason and the limitations can say that coverage was cut.
"""

from __future__ import annotations

import tempfile
from types import SimpleNamespace
from typing import Any

import pytest

from argus.investigation.orchestrator import InvestigationEngine
from argus.investigation.planner import InvestigationPlanner
from argus.investigation.question import InvestigationQuestion, QuestionStatus, QuestionType
from argus.investigation.state import InvestigationState
from argus.investigation.stopping import InvestigationStoppingPolicy
from argus.investigation.store import InvestigationStore

from tests.investigation.test_objective_scoped_extraction import (
    HEADER,
    PAGE,
    PROVIDER_URL,
    ROWS,
    SNIPPETS,
    FixtureCorpus,
    _run_terminal,
)

SATISFIED = ("OBJECTIVE_SATISFIED", "SUFFICIENT_EVIDENCE", "BUDGET_EXHAUSTED_WITH_ACCEPTABLE_COVERAGE")
TEAMCENTER_OBJECTIVE = "Search Companies who are using TEAMCENTER in usa"


def _questions(term: Any, data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    state = term.engine.store.load_state(data["investigation_id"])
    ids = state.objective_contract["enumeration_objective"]["question_ids"]
    return {role: state.questions[qid] for role, qid in ids.items()}


def test_snippet_only_run_does_not_claim_the_objective_is_satisfied():
    """Search snippets name no organization and every fetch fails."""
    corpus = FixtureCorpus(SNIPPETS, pages={})
    data, term = _run_terminal(TEAMCENTER_OBJECTIVE, corpus)

    assert data["stop_reason"] not in SATISFIED
    qs = _questions(term, data)
    assert qs["discovery"]["status"] != QuestionStatus.SUPPORTED.value
    assert any("Which organizations in the United States use Siemens Teamcenter?" in lim for lim in data["limitations"])


def test_provider_only_answer_is_partial_and_reported_as_a_limitation():
    """One technographic provider table is an unverified answer, not a resolved objective."""
    corpus = FixtureCorpus(SNIPPETS, {PROVIDER_URL: PAGE})
    data, term = _run_terminal(TEAMCENTER_OBJECTIVE, corpus)

    qs = _questions(term, data)
    assert qs["discovery"]["status"] == QuestionStatus.PARTIALLY_RESOLVED.value
    assert len(qs["discovery"]["resolved_by_claim_ids"]) == 4
    assert qs["corroboration"]["status"] != QuestionStatus.SUPPORTED.value
    assert data["stop_reason"] not in SATISFIED
    assert any("answered only by unverified assertions" in lim and "TECHNOGRAPHIC_PROVIDER_ASSERTION" in lim
               for lim in data["limitations"])
    # Every corroboration query ran instead of the run stopping after the first document.
    searched = [q for kind, q in corpus.calls if kind == "search"]
    assert any("case study" in q for q in searched) and any("implementation announcement" in q for q in searched)


def test_vendor_confirmation_upgrades_the_answer_and_satisfies_the_objective():
    product = "Quorvane Flux"
    provider_url = "https://theirstack.com/en/technology/quorvane-flux/us"
    vendor_url = "https://www.quorvane.com/customers/ford"
    page = f"Companies using {product}. " + HEADER + ROWS.format(p=product)
    snippets = [
        (provider_url, f"Companies that use {product} in the United States", f"Find companies that use {product}."),
        (vendor_url, f"Ford Motor Company customer story | Quorvane",
         f"Ford Motor Company has standardized on {product} for vehicle programs."),
    ]
    corpus = FixtureCorpus(snippets, {provider_url: page})
    data, term = _run_terminal(f"which companies in the USA are using {product}", corpus)

    ford = next(c for c in data["claims"] if c["subject"] == "Ford Motor Company" and str(c["predicate"]).startswith("USES_"))
    assert ford["status"] in ("CORROBORATED", "VENDOR_CONFIRMED")
    qs = _questions(term, data)
    assert qs["discovery"]["status"] == QuestionStatus.SUPPORTED.value
    assert qs["corroboration"]["status"] == QuestionStatus.SUPPORTED.value
    assert data["stop_reason"] == "OBJECTIVE_SATISFIED"


def test_documents_without_a_verified_claim_do_not_support_a_question():
    """The old rule resolved SUPPORTED whenever any document arrived."""
    engine = InvestigationEngine(corpus=FixtureCorpus([], {}), store=InvestigationStore(tempfile.mkdtemp()))
    state = InvestigationPlanner().initialize_investigation("Investigate Acme Orbital corporate structure", {"max_steps": 5})
    qid = state.unresolved_questions[0]
    from argus.investigation.action import ActionType, ResearchAction

    action = ResearchAction(action_type=ActionType.FETCH, rationale="test", query="https://acme.example/menu", question_id=qid)
    engine._apply_observation(state, action, {
        "status": "SUCCESS",
        "documents": [{"url": "https://acme.example/menu", "title": "Menu", "text": "Lunch menu: soup and bread.", "source_type": "live_web"}],
        "combined_text": "Menu Lunch menu: soup and bread.",
    })
    q = state.questions[qid]
    assert q["status"] != QuestionStatus.SUPPORTED.value
    from argus.investigation.resolution import question_is_answered

    assert not question_is_answered(q, {})


def test_claim_about_another_kind_of_fact_does_not_answer_a_typed_question():
    """An infrastructure question is not answered by a verified founding-date sentence."""
    engine = InvestigationEngine(corpus=FixtureCorpus([], {}), store=InvestigationStore(tempfile.mkdtemp()))
    state = InvestigationState(objective="Investigate Acme Orbital")
    q = InvestigationQuestion(
        question_text="What public infrastructure domains are registered to Acme Orbital?",
        question_type=QuestionType.INFRASTRUCTURE_ATTRIBUTION,
        related_entities=["Acme Orbital"],
    )
    state.questions[q.question_id] = q.model_dump()
    state.unresolved_questions.append(q.question_id)
    from argus.investigation.action import ActionType, ResearchAction

    text = "Acme Orbital was founded in 2019 in Toulouse."
    action = ResearchAction(action_type=ActionType.FETCH, rationale="test", query="https://acme.example/about",
                            question_id=q.question_id, target_entities=["Acme Orbital"])
    engine._apply_observation(state, action, {
        "status": "SUCCESS",
        "documents": [{"url": "https://acme.example/about", "title": "About", "text": text, "source_type": "live_web"}],
        "combined_text": "About " + text,
    })
    assert any(c.get("status") == "SUPPORTED" for c in state.claims), "fixture should yield a verified claim"
    assert state.questions[q.question_id]["status"] != QuestionStatus.SUPPORTED.value


def test_chained_questions_do_not_count_toward_coverage():
    """Ten answered follow-ups on incidental discoveries must not make 1-of-2 objective questions 'sufficient'."""
    policy = InvestigationStoppingPolicy()
    state = InvestigationState(objective="Coverage")
    answered = InvestigationQuestion(question_text="Answered", status=QuestionStatus.SUPPORTED)
    pending = InvestigationQuestion(question_text="Pending")
    state.questions[answered.question_id] = answered.model_dump()
    state.resolved_questions.append(answered.question_id)
    state.questions[pending.question_id] = pending.model_dump()
    state.unresolved_questions.append(pending.question_id)
    for i in range(10):
        ch = InvestigationQuestion(question_text=f"Chained {i}", origin="chained", status=QuestionStatus.SUPPORTED)
        state.questions[ch.question_id] = ch.model_dump()
        state.resolved_questions.append(ch.question_id)
    stop, reason, rationale = policy.evaluate(state)
    assert not stop, (reason, rationale)


def test_closed_but_unanswered_critical_question_blocks_objective_satisfied():
    policy = InvestigationStoppingPolicy()
    state = InvestigationState(objective="Closed")
    q = InvestigationQuestion(question_text="Critical", is_critical=True, status=QuestionStatus.INSUFFICIENT_EVIDENCE)
    state.questions[q.question_id] = q.model_dump()
    state.resolved_questions.append(q.question_id)
    stop, reason, rationale = policy.evaluate(state)
    assert stop and reason.value == "NO_USEFUL_ACTIONS_REMAIN"
    assert "'Critical'" in rationale


class _FakeSearch:
    """Offline stand-in for the DuckDuckGo provider; records each call."""

    calls: list[str] = []

    def __init__(self, *_: Any, **__: Any) -> None:
        pass

    async def search(self, query: Any) -> Any:
        _FakeSearch.calls.append(query.query)
        return SimpleNamespace(results=[
            SimpleNamespace(url="https://127.0.0.1:9/quorvane-flux/customers",
                            title="Quorvane Flux customers", snippet="Find companies that use Quorvane Flux."),
        ])


def test_retrieval_budget_denial_is_recorded_and_reflected_in_stop_and_limitations(monkeypatch):
    from argus.investigation.live_web.controller import ControlledLiveWebRetriever
    from argus.investigation.live_web.models import ControlledRetrievalLimits
    import argus.search.duckduckgo as ddg

    _FakeSearch.calls = []
    monkeypatch.setattr(ddg, "DuckDuckGoSearchProvider", _FakeSearch)
    limits = ControlledRetrievalLimits(max_requests_per_host=1, enforce_ssrf_protection=False, request_timeout_seconds=1.0)
    retriever = ControlledLiveWebRetriever(limits=limits, snapshot_dir=tempfile.mkdtemp())
    engine = InvestigationEngine(corpus=retriever, store=InvestigationStore(tempfile.mkdtemp()))

    state = engine.run_to_completion(objective="which companies in the USA are using Quorvane Flux", max_steps=10)

    assert len(_FakeSearch.calls) == 1, "only the first search fits the per-host budget"
    budget = [d for d in state.retrieval_denials if "Per-host limit reached" in str(d["reason"])]
    assert budget and all(d["query"] for d in budget)
    assert any(a.action_type == "RETRIEVAL_DENIED" for a in state.audit_trail)
    assert state.stop_state.stop_reason == "BUDGET_EXHAUSTED_WITH_CRITICAL_MISSING_FIELDS"
    limitations = state.generate_limitations()
    assert any(lim.startswith("Retrieval budget denied") and "duckduckgo.com" in lim for lim in limitations)
    assert any("Critical question not answered" in lim for lim in limitations)
    assert state.to_result().limitations == limitations
