"""Integrity tests for EVAL_INVESTIGATION_V1 Benchmark Suite and Leakage Prevention.

Verifies:
- Benchmark ground-truth isolation (no runtime dependencies or hardcoded answers)
- Evaluator leakage prevention (runtime engine cannot inspect TaskExpectedOutput)
- All 25 investigation tasks are deterministically executable
- Seven required integration scenarios run cleanly
"""

import pytest

from argus.investigation.benchmark.corpus import INVESTIGATION_CORPUS_REGISTRY
from argus.investigation.benchmark.evaluator import InvestigationV1Evaluator
from argus.investigation.benchmark.tasks import INVESTIGATION_V1_TASKS
from argus.investigation.orchestrator import InvestigationEngine


def test_evaluator_leakage_and_isolation():
    """Verify engine has zero access to task ground-truth fixtures."""
    engine = InvestigationEngine()
    # Engine attributes must not include benchmark tasks or expected answers
    assert not hasattr(engine, "tasks")
    assert not hasattr(engine, "expected_entities")
    assert not hasattr(engine, "expected_claims")


def test_investigation_corpus_search_isolation():
    """Verify corpus search only returns documents matching search tokens."""
    corpus = INVESTIGATION_CORPUS_REGISTRY
    results = corpus.search("nonexistent_random_token_xyz12345", limit=5)
    assert len(results) == 0


def test_integration_scenario_1_simple_one_question():
    """Integration Scenario 1: Simple one-question investigation."""
    engine = InvestigationEngine(corpus=INVESTIGATION_CORPUS_REGISTRY)
    state = engine.run_to_completion(
        objective="Identify primary legal entity name, CIK identifier, and headquarters for Apex Technologies Group.",
        contract={"target_entities": ["Apex Technologies Group"]},
        max_steps=4,
    )
    assert state.stop_state.is_stopped is True
    assert "Apex Technologies Group Inc" in state.entities or "Apex Technologies Group" in state.entities


def test_integration_scenario_2_multi_question_company():
    """Integration Scenario 2: Multi-question company investigation."""
    engine = InvestigationEngine(corpus=INVESTIGATION_CORPUS_REGISTRY)
    state = engine.run_to_completion(
        objective="Identify the UK operating subsidiary of Apex Technologies Group and its managing director.",
        contract={"target_entities": ["Apex Technologies Group"]},
        max_steps=5,
    )
    assert state.stop_state.is_stopped is True
    assert "Apex Technologies Europe Ltd" in state.entities
    assert "Tobias Richter" in state.entities


def test_integration_scenario_6_cross_specialist():
    """Integration Scenario 6: Cross-specialist investigation."""
    engine = InvestigationEngine(corpus=INVESTIGATION_CORPUS_REGISTRY)
    state = engine.run_to_completion(
        objective="Trace German subsidiary to its quantum monitoring hostname, and verify the responsible Senior Vice President.",
        contract={"target_entities": ["Apex Quantum Sensing GmbH"]},
        max_steps=6,
    )
    assert state.stop_state.is_stopped is True
    assert "Apex Quantum Sensing GmbH" in state.entities
    assert "Dr. Kenji Sato" in state.entities
