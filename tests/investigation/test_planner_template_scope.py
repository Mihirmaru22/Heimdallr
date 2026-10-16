"""Regression tests for planner template scoping and routing (V3 FC1 T06).

T05 made termination honest: a run is satisfied only when every critical question is
answered by verified evidence. That exposed two planner defects:

- Domain templates mark generic sub-questions critical ("Who are the key executive
  officers of X?") even when the user asked something else, so a correctly answered
  objective could never be reported as satisfied.
- The capability matcher routed an ordinary historical question to the dark-web adapter
  (substring question-type match, loose evidence matching), and a failed fetch fell back
  to whatever page a text search on the URL ranked first.
"""

from __future__ import annotations

import tempfile

from argus.capability_registry.matcher import CapabilityMatcher
from argus.investigation.action import ActionType, ResearchAction
from argus.investigation.benchmark.corpus import InvestigationCorpusRegistry, InvestigationDocument
from argus.investigation.orchestrator import InvestigationEngine
from argus.investigation.planner import InvestigationPlanner
from argus.investigation.question import InvestigationQuestion, QuestionType
from argus.investigation.store import InvestigationStore


def _critical(state) -> list[str]:
    return [q["question_text"] for q in state.questions.values() if q["is_critical"]]


def test_unrelated_template_questions_are_not_critical():
    objective = "Investigate Veltrano Robotics. Identify the founder, flagship legged robot, and actuator design."
    state = InvestigationPlanner().initialize_investigation(objective, {"target_entities": ["Veltrano Robotics"]})

    assert _critical(state) == [objective]
    # The template questions are still planned and researched, only not required.
    assert any("executive officers" in q["question_text"] for q in state.questions.values())
    audit = [a for a in state.audit_trail if a.action_type == "TEMPLATE_CRITICALITY_SCOPED"]
    assert audit and len(audit[0].details["demoted"]) >= 2
    demoted_ids = {d["question_id"] for d in audit[0].details["demoted"]}
    assert not [g for g in state.information_gaps if g.related_question_id in demoted_ids and g.is_critical]


def test_template_question_on_the_objective_topic_stays_critical():
    objective = "Reconstruct executive leadership changes at Orvex Bio Labs during the 2025 board restructuring."
    state = InvestigationPlanner().initialize_investigation(objective, {"target_entities": ["Orvex Bio Labs"]})

    critical = _critical(state)
    assert objective in critical
    assert any("executive officers" in t for t in critical)
    assert not any("SAN certificates" in t for t in critical)


def test_one_shared_boilerplate_word_does_not_make_a_question_critical():
    """'scientific chair' must not make 'competing scientific or policy explanations' critical."""
    objective = "Investigate the Third Halvorsen Symposium held in Oslo in 1923. Identify the scientific chair and key attendees."
    state = InvestigationPlanner().initialize_investigation(objective, {"target_entities": ["Third Halvorsen Symposium"]})
    assert _critical(state) == [objective]


def test_enumeration_objectives_are_unchanged():
    state = InvestigationPlanner().initialize_investigation("which companies in the USA are using Quorvane Flux", {})
    ids = state.objective_contract["enumeration_objective"]["question_ids"]
    assert state.questions[ids["discovery"]]["is_critical"] is True
    assert not [a for a in state.audit_trail if a.action_type == "TEMPLATE_CRITICALITY_SCOPED"]


def _top_capability(question: InvestigationQuestion) -> str:
    planner = InvestigationPlanner()
    cands = planner.matcher.match(question=question, capabilities=planner.registry.list(include_inactive=False), max_candidates=3)
    return cands[0].capability_id


def test_historical_question_is_not_routed_to_dark_web_or_email_specialists():
    objective = "Investigate the Third Halvorsen Symposium held in Oslo in 1923. Identify the scientific chair, host, and key attendees."
    state = InvestigationPlanner().initialize_investigation(objective, {"target_entities": ["Third Halvorsen Symposium"]})
    for q in state.questions.values():
        top = _top_capability(InvestigationQuestion.model_validate(q))
        assert top not in ("onion_intelligence", "email_identity_resolution", "email_to_account_discovery"), (q["question_text"], top)


def test_dark_web_question_still_routes_to_the_onion_specialist():
    q = InvestigationQuestion(
        question_text="Which Tor hidden services host leak sites naming Veltrano Robotics?",
        question_type=QuestionType.ENTITY_DISCOVERY,
        related_entities=["Veltrano Robotics"],
        required_evidence=["Tor hidden service (.onion) leak-site records naming Veltrano Robotics"],
    )
    assert _top_capability(q) == "onion_intelligence"


def test_domain_qualified_question_types_are_not_generic_matches():
    from types import SimpleNamespace

    onion = SimpleNamespace(category=SimpleNamespace(value="ONION_AND_DARKWEB"))
    corporate = SimpleNamespace(category=SimpleNamespace(value="CORPORATE"))
    assert not CapabilityMatcher._question_type_matches("ONION_ENTITY_DISCOVERY", "ENTITY_DISCOVERY", onion)
    assert CapabilityMatcher._question_type_matches("ENTITY_DISCOVERY", "ENTITY_DISCOVERY", onion)
    assert CapabilityMatcher._question_type_matches("VERIFY_OFFICER_TENURE", "OFFICER_TENURE", corporate)


def test_failed_fetch_does_not_substitute_an_unrelated_document():
    corpus = InvestigationCorpusRegistry()
    corpus.documents = {
        "d1": InvestigationDocument(doc_id="d1", title="Hidden Relay record", url="https://records.example/relay",
                                    text_content="Relay operators listed hidden relay addresses.", source_type="web"),
    }
    corpus._discoverable_entities = set()
    engine = InvestigationEngine(corpus=corpus, store=InvestigationStore(tempfile.mkdtemp()))
    state = InvestigationPlanner().initialize_investigation("Investigate Veltrano Robotics", {"target_entities": ["Veltrano Robotics"]})
    action = ResearchAction(action_type=ActionType.FETCH, rationale="test", query="http://Hidden Relay record",
                            parameters={"url": "http://Hidden Relay record"}, specialist="none")
    obs = engine._dispatch_action(action, state)
    assert obs["status"] == "SOURCE_UNAVAILABLE"
    assert obs["documents"] == []


def test_answered_objective_with_unanswered_supporting_questions_is_satisfied_and_says_so():
    objective = "Investigate Veltrano Robotics. Identify the founder, flagship legged robot, and actuator design."
    corpus = InvestigationCorpusRegistry()
    corpus.documents = {
        "v1": InvestigationDocument(
            doc_id="v1", title="Veltrano Robotics company overview", url="https://veltrano.example/about",
            text_content=(
                "Veltrano Robotics was founded in 2020 by Dr. Ines Marlow in Turin. "
                "Veltrano Robotics developed the Strider-3 legged robot with series elastic actuators."
            ),
            source_type="corporate_site",
        ),
    }
    corpus._discoverable_entities = {"Veltrano Robotics", "Dr. Ines Marlow", "Strider-3"}
    engine = InvestigationEngine(corpus=corpus, store=InvestigationStore(tempfile.mkdtemp()))
    state = engine.run_to_completion(objective=objective, contract={"target_entities": ["Veltrano Robotics"]}, max_steps=10)

    obj_q = next(q for q in state.questions.values() if q["question_text"] == objective)
    assert obj_q["status"] == "SUPPORTED"
    assert state.stop_state.stop_reason == "OBJECTIVE_SATISFIED"
    unanswered = [q for q in state.questions.values() if q["status"] != "SUPPORTED"]
    assert unanswered, "fixture should leave some template questions unanswered"
    limitations = state.generate_limitations()
    for q in unanswered:
        if q["question_id"] in state.resolved_questions:
            assert any(q["question_text"] in lim for lim in limitations)
