"""Unit tests for Specialist Orchestration, Multi-Specialist Chaining, Contradictions, and Temporal Reasoning."""

import pytest

from argus.investigation.benchmark.corpus import INVESTIGATION_CORPUS_REGISTRY
from argus.investigation.orchestrator import InvestigationEngine
from argus.investigation.planner import InvestigationPlanner
from argus.investigation.question import QuestionStatus


def test_specialist_orchestration_and_chaining():
    engine = InvestigationEngine(corpus=INVESTIGATION_CORPUS_REGISTRY)

    # Multi-specialist chain objective:
    # Corporate (Apex UK) -> Infrastructure (CT Log) -> Identity (Rachel Thorne)
    objective = (
        "Starting from Apex Technologies Group, discover its UK subsidiary, "
        "the telemetry domain SAN, and verify the administrative contact CISO."
    )
    state = engine.run_to_completion(
        objective=objective,
        contract={"target_entities": ["Apex Technologies Group"]},
        max_steps=8,
    )

    assert state.stop_state.is_stopped is True
    # Verify specialist invocations
    specs_used = {inv["specialist"] for inv in state.specialist_invocations}
    assert "corporate" in specs_used or "infrastructure" in specs_used
    # Verify entities from all 3 specialists were discovered
    assert "Apex Technologies Europe Ltd" in state.entities or "Apex Technologies Group Inc" in state.entities
    assert "telemetry-cluster-01.apex-telemetry.co.uk" in state.entities
    assert "Rachel Thorne" in state.entities


def test_contradiction_detection_and_resolution():
    engine = InvestigationEngine(corpus=INVESTIGATION_CORPUS_REGISTRY)
    objective = (
        "Form 10-K from 2020 lists Donald Vance as SVP of AI, while current report lists David Marcus. "
        "Resolve which individual is currently authoritative."
    )
    state = engine.run_to_completion(
        objective=objective,
        contract={"target_entities": ["Apex Technologies Group"]},
        max_steps=6,
    )

    assert state.stop_state.is_stopped is True
    assert "David Marcus" in state.entities
    # Authoritative succession was captured
    succession_claims = [c for c in state.claims if c.get("predicate") == "succeeded" or "succession" in str(c)]
    assert len(succession_claims) > 0 or any(c.get("subject") == "David Marcus" and c.get("predicate") == "title" for c in state.claims)


def test_temporal_investigation_historical_state():
    engine = InvestigationEngine(corpus=INVESTIGATION_CORPUS_REGISTRY)
    objective = (
        "What individual authoritatively served as SVP of Machine Learning & AI at Apex Technologies as of December 31, 2020?"
    )
    state = engine.run_to_completion(
        objective=objective,
        contract={"as_of_date": "2020-12-31"},
        as_of_date="2020-12-31",
        max_steps=6,
    )

    assert state.stop_state.is_stopped is True
    assert "Donald Vance" in state.entities
    assert any("RESIGNED" in str(c) or c.get("subject") == "Donald Vance" for c in state.claims)


def test_negative_not_found_differentiation():
    engine = InvestigationEngine(corpus=INVESTIGATION_CORPUS_REGISTRY)

    # 1. Fictitious role -> NOT_FOUND
    state_fake = engine.run_to_completion(
        objective="Verify whether Apex Technologies employs a 'Vice President of Quantum Cryptocurrency'.",
        contract={"target_entities": ["Apex Technologies Group"]},
        max_steps=4,
    )
    assert any(q.get("status") == QuestionStatus.NOT_FOUND.value for q in state_fake.questions.values())

    # 2. Phishing lookalike domain -> CONTRADICTED
    state_phish = engine.run_to_completion(
        objective="Investigate apex-g1obal-tech.com. Verify if it belongs to Apex Technologies Group or represents an adversarial imposter.",
        contract={"target_entities": ["apex-g1obal-tech.com"]},
        max_steps=4,
    )
    assert any(c.get("status") == "CONTRADICTED" for c in state_phish.claims)
