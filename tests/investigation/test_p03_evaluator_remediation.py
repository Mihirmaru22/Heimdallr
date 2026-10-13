"""P0.3-R: EVALUATOR INTEGRITY & REMEDIATION VERIFICATION SUITE.

Verifies that the evaluator correctness defects identified in the audit have been repaired:
- Layer 1 vs Layer 3: Structural provenance is separated from semantic claim support.
- Citation validity: Measures source resolution, while semantic support verifies actual content.
- Negative denominators: Empty denominators return 0.0, never silently default to 1.0.
- Contradiction integrity: Rejects unrelated contradictions that do not match the task target/topic.
- Negative task integrity: Rejects unsearched or irrelevant NOT_FOUND findings.
- Aggregate metrics: Genuinely computed without hardcoded constants or proxy substitutions.
"""

from __future__ import annotations

import pytest

from argus.investigation.benchmark.corpus import InvestigationDocument
from argus.investigation.benchmark.evaluator import InvestigationV1Evaluator
from argus.investigation.benchmark.tasks import (
    InvestigationCategory,
    InvestigationDifficulty,
    InvestigationTask,
)
from argus.investigation.state import InvestigationState
from argus.investigation.stopping import InvestigationStopReason


def test_structural_provenance_separated_from_semantic_support():
    """Verify evaluator distinguishes structural provenance from semantic claim support."""
    evaluator = InvestigationV1Evaluator()
    task = InvestigationTask(
        task_id="test_task_grounding_remediation",
        title="Testing Grounding Remediation",
        objective="Verify corporate governance of UnseenCorp.",
        category=InvestigationCategory.TECHNICAL_ENGINEERING,
        difficulty=InvestigationDifficulty.HARD,
        contract={"target_entities": ["UnseenCorp"]},
        expected_entities=["UnseenCorp"],
    )

    state = InvestigationState(objective=task.objective)
    state.register_entity("UnseenCorp")

    # Add real evidence about UnseenCorp's office lease
    state.add_evidence({
        "evidence_id": "ev_lease_123",
        "url": "https://example.com/lease",
        "snippet": "UnseenCorp signed a 5-year lease for commercial office space in Zurich.",
        "text": "UnseenCorp signed a 5-year lease for commercial office space in Zurich.",
    })

    # Add a fabricated claim that points to ev_lease_123
    state.add_claim({
        "subject": "UnseenCorp",
        "predicate": "quantum_encryption_breakthrough",
        "object": "Successfully factored RSA-4096 using a fault-tolerant topological quantum computer.",
        "status": "SUPPORTED",
        "evidence_id": "ev_lease_123",
        "source_url": "https://example.com/lease",
    })

    state.stop_state.is_stopped = True
    state.stop_state.stop_reason = InvestigationStopReason.OBJECTIVE_SATISFIED.value

    eval_result = evaluator.evaluate_single_task(task, state=state)

    # Structural provenance is 1.0 because the evidence record exists
    assert eval_result["structural_provenance_rate"] == 1.0
    # BUT semantic claim support is 0.0 because the text does not support the claim assertion
    assert eval_result["semantic_claim_support_rate"] == 0.0
    assert eval_result["unsupported_claim_rate"] == 1.0


def test_citation_validity_distinguished_from_content_support():
    """Verify citation validity checks source resolution, and empty citations yield 0.0."""
    evaluator = InvestigationV1Evaluator()
    task = InvestigationTask(
        task_id="test_task_citation_validity",
        title="Testing Citation Validity",
        objective="Verify research citations.",
        category=InvestigationCategory.TECHNICAL_ENGINEERING,
        difficulty=InvestigationDifficulty.HARD,
        contract={},
    )

    # Case A: Empty citations yield 0.0, not 1.0
    state_empty = InvestigationState(objective=task.objective)
    eval_empty = evaluator.evaluate_single_task(task, state=state_empty)
    assert eval_empty["citation_validity"] == 0.0

    # Case B: Cited URL exists in collected evidence
    state = InvestigationState(objective=task.objective)
    state.add_evidence({
        "evidence_id": "ev_doc_01",
        "url": "https://research.org/report",
        "snippet": "Semiconductor manufacturing report 2026.",
    })
    state.add_claim({
        "subject": "Fab",
        "predicate": "output",
        "object": "Semiconductor manufacturing report 2026.",
        "status": "SUPPORTED",
        "evidence_id": "ev_doc_01",
        "source_url": "https://research.org/report",
    })
    eval_res = evaluator.evaluate_single_task(task, state=state)
    assert eval_res["citation_validity"] == 1.0


def test_rejection_of_unrelated_contradictions():
    """Verify evaluator rejects unrelated contradictions that do not match the task target or topic."""
    evaluator = InvestigationV1Evaluator()
    task = InvestigationTask(
        task_id="test_contra_mismatch",
        title="Testing Contradiction Topic Alignment",
        objective="Verify whether EntityA or EntityB won the telecom spectrum license.",
        category=InvestigationCategory.CONFLICTING_AMBIGUOUS,
        difficulty=InvestigationDifficulty.HARD,
        has_contradiction=True,
        expected_epistemic_status="CONTRADICTED",
        contract={"target_entities": ["EntityA", "EntityB"]},
    )

    state = InvestigationState(objective=task.objective)

    # Insert an unrelated contradiction about weather
    state.contradictions.append({
        "topic": "Weather Forecast in Hawaii",
        "claim_a": "Rainy",
        "claim_b": "Sunny",
        "status": "UNRESOLVED",
    })

    state.stop_state.is_stopped = True
    state.stop_state.stop_reason = InvestigationStopReason.OBJECTIVE_SATISFIED.value

    eval_result = evaluator.evaluate_single_task(task, state=state)

    # The unrelated contradiction must NOT be credited!
    assert eval_result["epistemic_status"] == "UNVERIFIED"
    assert eval_result["epistemic_correct"] is False
    assert eval_result["passed"] is False


def test_rejection_of_unsearched_negative_shortcut():
    """Verify negative task evaluator does not award credit for unsearched or irrelevant NOT_FOUND."""
    evaluator = InvestigationV1Evaluator()
    task = InvestigationTask(
        task_id="test_negative_shortcut",
        title="Testing Negative Task Verification",
        objective="Verify whether NonExistentOrg was granted an export license.",
        category=InvestigationCategory.NEGATIVE_NOT_FOUND,
        difficulty=InvestigationDifficulty.HARD,
        is_negative=True,
        expected_epistemic_status="NOT_FOUND",
        contract={"target_entities": ["NonExistentOrg"]},
    )

    state = InvestigationState(objective=task.objective)
    # Add an unrelated question resolved as NOT_FOUND without searching NonExistentOrg
    state.questions["q_fail"] = {
        "question_id": "q_fail",
        "question_text": "What is the phone number of Mars?",
        "status": "NOT_FOUND",
    }
    state.resolved_questions.append("q_fail")

    state.stop_state.is_stopped = True
    state.stop_state.stop_reason = InvestigationStopReason.OBJECTIVE_SATISFIED.value

    eval_result = evaluator.evaluate_single_task(task, state=state)

    # The unsearched entity must NOT receive credit!
    assert eval_result["epistemic_status"] == "UNVERIFIED"
    assert eval_result["epistemic_correct"] is False
    assert eval_result["passed"] is False


def test_aggregate_metrics_computed_genuinely():
    """Verify aggregate metrics are computed from real task metrics, not hardcoded constants or proxies."""
    evaluator = InvestigationV1Evaluator()
    task_results = [
        {
            "task_id": "t1",
            "title": "Task 1",
            "category": "TECHNICAL_ENGINEERING",
            "difficulty": "HARD",
            "passed": True,
            "runtime_sec": 0.1,
            "steps_taken": 5,
            "entities_found_count": 2,
            "entities_found": ["A", "B"],
            "expected_entities": ["A", "B"],
            "entity_precision": 1.0,
            "entity_recall": 1.0,
            "entity_f1": 1.0,
            "citation_validity": 1.0,
            "evidence_grounding_rate": 1.0,
            "structural_provenance_rate": 1.0,
            "semantic_claim_support_rate": 0.8,
            "unsupported_claim_rate": 0.2,
            "source_relevance_rate": 1.0,
            "claims_count": 5,
            "evidence_count": 4,
            "questions_total": 4,
            "questions_resolved": 3,
            "questions_unresolved": 1,
            "active_branches": 0,
            "completed_branches": 2,
            "stop_reason": "OBJECTIVE_SATISFIED",
            "epistemic_status": "SUPPORTED",
            "expected_epistemic_status": "SUPPORTED",
            "epistemic_correct": True,
            "specialist_invocations": [],
            "requires_multi_specialist": False,
            "multi_specialist_satisfied": True,
            "has_contradiction": False,
            "has_temporal_trap": False,
            "is_negative": False,
            "critical_questions_total": 2,
            "critical_questions_resolved": 1,
            "hypotheses_total": 3,
            "hypotheses_resolved": 2,
            "redundant_actions_count": 1,
            "over_research_steps": 0,
            "state_recovery_success": True,
        }
    ]

    agg = evaluator._compute_aggregate_metrics(task_results, elapsed_total=0.5)

    # 1. Redundant action rate is computed: 1 redundant / 5 steps = 0.2
    assert agg["8_redundant_action_rate"] == 0.2
    # 2. Critical question resolution is computed: 1 resolved / 2 critical = 0.5 (NOT proxy 3/4 = 0.75)
    assert agg["3_critical_question_resolution"] == 0.5
    assert agg["2_question_resolution_rate"] == 0.75
    assert agg["3_critical_question_resolution"] != agg["2_question_rate"] if "2_question_rate" in agg else True
    # 3. Hypothesis resolution is computed: 2 resolved / 3 hypotheses = 2/3 ≈ 0.667
    assert abs(agg["4_hypothesis_resolution"] - (2 / 3)) < 1e-4
    # 4. State recovery is computed from actual results
    assert agg["state_recovery_correctness"] == 1.0
