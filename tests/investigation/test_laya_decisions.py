"""Laya makes the decisions; the old rules answer only without Laya; every decision is journaled."""

import json

import pytest

from argus.brain.decisions import DecisionService, get_decisions, set_decisions
from argus.capability_registry.matcher import CapabilityMatcher
from argus.investigation.question_intent import decide_intent
from argus.investigation.reported_disputes import classify_sentence
from argus.investigation.resolution import claim_kind_fits_question


class FakeRouter:
    """Answers like laya.Router.predict, from a function of (text, question)."""

    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def predict(self, text, questions):
        self.calls.append((text, questions))
        return {"answers": {qid: self.answer(text, q) for qid, q in questions.items()}}


def use_laya(answer):
    router = FakeRouter(answer)
    set_decisions(DecisionService(router=router, enabled=True))
    return router


def test_without_laya_rules_answer_and_are_journaled():
    d = get_decisions()
    assert not d.available
    out = d.choose("x", "text", "q?", {"a": "A", "b": "B"}, rule="b")
    assert (out.answer, out.by) == ("b", "rule")
    assert d.summary() == {"decisions": 1, "by_laya": 0, "by_rule": 1, "laya_disagreed_with_rule": 0}


def test_laya_overrides_rule_and_disagreement_is_counted(tmp_path):
    use_laya(lambda t, q: {"type": "choice", "choice": "a", "confidence": 0.9})
    d = get_decisions()
    d.set_journal(tmp_path / "decisions.jsonl")
    out = d.choose("x", "text", "q?", {"a": "A", "b": "B"}, rule="b")
    assert (out.answer, out.by, out.rule_answer) == ("a", "laya", "b")
    assert d.summary()["laya_disagreed_with_rule"] == 1
    row = json.loads((tmp_path / "decisions.jsonl").read_text().splitlines()[0])
    assert row["laya"] == "a" and row["rule"] == "b"


def test_unknown_label_or_low_confidence_falls_back(monkeypatch):
    use_laya(lambda t, q: {"type": "choice", "choice": "zzz", "confidence": 0.9})
    assert get_decisions().choose("x", "t", "q", {"a": "", "b": ""}, rule="b").by == "rule"
    monkeypatch.setenv("HEIMDALLR_LAYA_MIN_CONFIDENCE", "0.8")
    use_laya(lambda t, q: {"type": "choice", "choice": "a", "confidence": 0.5})
    assert get_decisions().choose("x", "t", "q", {"a": "", "b": ""}, rule="b").answer == "b"


def test_broken_laya_stops_being_asked():
    def boom(t, q):
        raise RuntimeError("model download failed")

    router = use_laya(boom)
    d = get_decisions()
    for i in range(5):
        assert d.yes_no("x", f"t{i}", "q", rule=True).answer is True
    assert len(router.calls) == 3 and not d.available


def test_question_form_is_laya_decision():
    use_laya(lambda t, q: {"type": "choice", "choice": "listing", "confidence": 0.8})
    intent = decide_intent("Tell me about manufacturers of heat pumps in Norway")
    assert intent.kind == "listing" and intent.scope


def test_domain_is_laya_decision_but_user_hint_wins():
    from argus.investigation.planner import InvestigationPlanner

    use_laya(lambda t, q: {"type": "choice", "choice": "historical", "confidence": 0.8})
    assert InvestigationPlanner._detect_domain("What caused the 1929 crash?", {}) == "historical"
    assert InvestigationPlanner._detect_domain("anything", {"domain_hint": "technical"}) == "technical"


def test_jurisdiction_rule_uses_whole_words():
    rule = CapabilityMatcher.jurisdiction_rule
    assert rule("What is the current status of the second trial?") == "GLOBAL"  # "us" in status, "sec" in second
    assert rule("Which US hospitals use Epic?") == "US"
    assert rule("SEC filings of Acme") == "US"
    assert rule("Companies in the UK using SAP") == "GB"


def test_sentence_conflict_is_laya_decision_and_plain_sentences_are_not_asked():
    router = use_laya(lambda t, q: {"type": "choice", "choice": "none", "confidence": 0.9})
    assert classify_sentence("The two studies contradict each other on dosage.") is None  # Laya: no conflict
    assert classify_sentence("The plant opened in 1998.") is None
    assert len(router.calls) == 1


def test_claim_fit_is_laya_decision_when_question_text_given():
    use_laya(lambda t, q: {"type": "noul", "noul": 0.9})
    claim = {"subject": "Acme", "predicate": "mentioned_in", "object": "Jane Doe is chief executive"}
    assert claim_kind_fits_question(claim, "OFFICER_TENURE") is False  # rule only
    assert claim_kind_fits_question(claim, "OFFICER_TENURE", "Who leads Acme?") is True


def test_openrouter_provider_refuses_paid_models(monkeypatch):
    from argus.llm.free_models import NotAFreeModel
    from argus.llm.openrouter import OpenRouterLLMProvider

    with pytest.raises(NotAFreeModel):
        OpenRouterLLMProvider(api_key="k", model="deepseek/deepseek-chat")
    assert OpenRouterLLMProvider(api_key="k").model == ""
    monkeypatch.setenv("HEIMDALLR_FREE_MODELS", "some/model:free")
    assert OpenRouterLLMProvider(api_key="k").model == "some/model:free"


def test_every_adapter_reaches_the_shared_services(monkeypatch):
    from argus.capability_registry.adapters import NoLiveSourceAdapter
    from argus.llm.free_models import FreeModelService, reset_free_model_service

    monkeypatch.setenv("HEIMDALLR_LOCAL_MODEL", "qwen2.5:7b")
    reset_free_model_service()
    adapter = NoLiveSourceAdapter("impl", "cap")
    assert isinstance(adapter.llm, FreeModelService)
    assert adapter.decisions is get_decisions()


def test_verifier_does_not_accept_pages_that_merely_say_evidence_passage():
    from argus.domain.evidence import Evidence
    from argus.verifier.engine import check_claim_evidence_alignment

    ev = Evidence(source_id="s", url="https://example.org", passage="See the evidence passage below about weather.")
    ok, _ = check_claim_evidence_alignment("Acme", [], "chief_executive", "Jane Doe", [ev])
    assert ok is False
