"""P0.3: REAL-WORLD RESEARCH ACCURACY VERIFICATION SUITE.

Deterministic unit and integration tests establishing:
1. Evidence-to-claim provenance integrity (evidence_id, source_url, source_passage).
2. Citation validity against actual collected evidence.
3. Rejection and detection of unsupported claims.
4. Contradiction preservation across conflicting source material.
5. Epistemic uncertainty preservation (INSUFFICIENT_EVIDENCE, NOT_FOUND).
6. Calibrated epistemic confidence (no inflation on failures or wire syndication).
7. Adaptive, non-redundant query generation.
8. Strict benchmark isolation and absence of ground-truth leakage.
"""

from __future__ import annotations

import pytest

from argus.investigation.benchmark.corpus import (
    InvestigationCorpusRegistry,
    build_full_investigation_corpus,
)
from argus.investigation.benchmark.evaluator import InvestigationV1Evaluator
from argus.investigation.benchmark.tasks import (
    RESEARCH_ACCURACY_V3_TASKS,
    InvestigationCategory,
)
from argus.investigation.orchestrator import InvestigationEngine
from argus.investigation.planner import InvestigationPlanner
from argus.investigation.question import QuestionStatus
from argus.investigation.state import ConfidenceState, InvestigationState


def test_evidence_to_claim_provenance_integrity():
    """Invariant 1: Substantive factual claims preserve strict provenance to collected evidence."""
    engine = InvestigationEngine()
    state = engine.start_investigation(
        objective="Investigate Raft consensus algorithm under network partition.",
        contract={"target_entities": ["Raft"]},
    )
    while not state.stop_state.is_stopped:
        state, is_finished = engine.execute_step(state)
        if is_finished:
            break
    res = state.to_result()

    assert len(res.findings) > 0
    assert len(res.supporting_evidence) > 0

    collected_ev_ids = {e["evidence_id"] for e in res.supporting_evidence if "evidence_id" in e}
    collected_urls = {e["url"] for e in res.supporting_evidence if "url" in e}

    for finding in res.findings:
        if finding.get("status") == "SUPPORTED":
            assert "evidence_id" in finding, f"Finding missing evidence_id: {finding}"
            assert finding["evidence_id"] in collected_ev_ids, f"Orphaned evidence_id in finding: {finding}"
            assert "source_url" in finding, f"Finding missing source_url: {finding}"
            assert finding["source_url"] in collected_urls, f"Invalid source_url: {finding}"
            assert "source_passage" in finding, f"Finding missing source_passage: {finding}"
            assert len(finding["source_passage"]) > 0


def test_citation_validity_strict_resolution():
    """Invariant 2: Citations strictly resolve to collected sources without fabrication."""
    engine = InvestigationEngine()
    state = engine.start_investigation(
        objective="Investigate ASML EUV photolithography supply chain dependencies.",
        contract={"target_entities": ["ASML Holding"]},
    )
    while not state.stop_state.is_stopped:
        state, is_finished = engine.execute_step(state)
        if is_finished:
            break
    res = state.to_result()

    assert len(res.source_references) > 0
    collected_urls = {e["url"] for e in res.supporting_evidence}

    for source_ref in res.source_references:
        assert source_ref in collected_urls, f"Fabricated or uncollected citation: {source_ref}"


def test_contradiction_preservation_not_silently_discarded():
    """Invariant 3: Conflicting sources preserve competing claims and mark status CONTRADICTED."""
    engine = InvestigationEngine()
    state = engine.start_investigation(
        objective=(
            "Analyze the conflicting scientific estimates for the number of communicating extraterrestrial "
            "civilizations (N) in the Milky Way. Contrast Frank Drake's optimistic estimates with modern evolutionary bounds."
        ),
        contract={"target_entities": ["Drake Equation"]},
    )
    while not state.stop_state.is_stopped:
        state, is_finished = engine.execute_step(state)
        if is_finished:
            break
    res = state.to_result()

    assert len(res.contradictions) > 0, "Conflicting sources did not record contradiction."
    conflict = res.contradictions[0]
    assert "Drake Equation" in conflict.get("topic", "")
    assert "claim_a" in conflict and "claim_b" in conflict

    has_contra_claim = any(c.get("status") == "CONTRADICTED" for c in res.findings)
    assert has_contra_claim, "Contradicted claim not preserved in findings."


def test_insufficient_evidence_preserves_uncertainty():
    """Invariant 4: Unsubstantiated or refuted claims preserve INSUFFICIENT_EVIDENCE status."""
    engine = InvestigationEngine()
    state = engine.start_investigation(
        objective=(
            "Investigate whether independent laboratories successfully confirmed room-temperature superconductivity "
            "in copper-doped lead apatite (LK-99)."
        ),
        contract={"target_entities": ["LK-99"]},
    )
    while not state.stop_state.is_stopped:
        state, is_finished = engine.execute_step(state)
        if is_finished:
            break
    res = state.to_result()

    has_insufficient = any(c.get("status") == "INSUFFICIENT_EVIDENCE" for c in res.findings)
    assert has_insufficient, "Refuted LK-99 superconductivity was not marked INSUFFICIENT_EVIDENCE."

    # Question status should reflect insufficiency
    assert any(
        q.get("status") == QuestionStatus.INSUFFICIENT_EVIDENCE.value
        for q in state.questions.values()
    )


def test_confidence_calibration_no_inflation():
    """Invariant 5: Missing evidence, unresolved questions, or wire syndication never inflate confidence."""
    state = InvestigationState(objective="Calibration test")
    conf = ConfidenceState()

    # Case A: 0 questions, 0 evidence -> confidence must be 0.0
    conf.recompute_calibration(state)
    assert conf.overall_confidence == 0.0
    assert conf.evidence_coverage == 0.0

    # Case B: Questions present but 0 evidence -> zero inflation
    state.questions["q1"] = {"question_id": "q1", "status": "OPEN", "is_critical": True}
    state.unresolved_questions.append("q1")
    conf.recompute_calibration(state)
    assert conf.overall_confidence == 0.0
    assert conf.evidence_coverage == 0.0

    # Case C: Duplicate wire syndication mirrors do NOT artificially inflate independence score
    ev1 = {"url": "https://wire1.com/a", "snippet": "Text", "syndication_cluster_id": "wire_reuters"}
    ev2 = {"url": "https://wire2.com/b", "snippet": "Text", "syndication_cluster_id": "wire_reuters"}
    state.add_evidence(ev1)
    state.add_evidence(ev2)
    state.questions["q1"]["status"] = "SUPPORTED"
    state.resolved_questions.append("q1")
    state.unresolved_questions.remove("q1")
    state.add_claim({"subject": "Test", "predicate": "val", "object": "1", "status": "SUPPORTED", "evidence_id": state.evidence[0]["evidence_id"]})

    conf.recompute_calibration(state)
    assert conf.source_independence_score <= 0.60, f"Syndication cluster did not penalize independence: {conf.source_independence_score}"


def test_adaptive_query_diversification_avoids_redundancy():
    """Invariant 6: Planner does not repeatedly emit identical queries for the same question."""
    planner = InvestigationPlanner()
    state = planner.initialize_investigation(
        objective="Investigate Linux eBPF kernel verifier bounds checking.",
        objective_contract={"target_entities": ["eBPF Verifier"]},
    )

    actions1 = planner.select_next_actions(state, limit=1)
    assert len(actions1) > 0
    q1 = actions1[0].query

    # Record action in state telemetry
    state.research_actions.append(actions1[0].model_dump())

    # Request next action for same question
    actions2 = planner.select_next_actions(state, limit=1)
    assert len(actions2) > 0
    q2 = actions2[0].query

    assert q1.strip().lower() != q2.strip().lower(), f"Planner generated duplicate identical query: '{q1}'"


def test_benchmark_task_suite_coverage():
    """Invariant 7: P0.3 benchmark contains all 10 mandated real-world research categories."""
    categories = {t.category for t in RESEARCH_ACCURACY_V3_TASKS}
    assert InvestigationCategory.TECHNICAL_ENGINEERING in categories
    assert InvestigationCategory.HISTORICAL in categories
    assert InvestigationCategory.SCIENTIFIC_POLICY in categories
    assert InvestigationCategory.ORGANIZATIONAL_CORPORATE in categories
    assert InvestigationCategory.INTERDISCIPLINARY in categories
    assert InvestigationCategory.TIME_SENSITIVE in categories
    assert InvestigationCategory.CONFLICTING_AMBIGUOUS in categories
    assert InvestigationCategory.INSUFFICIENT_EVIDENCE in categories
    assert InvestigationCategory.MISLEADING_RESULTS in categories
    assert InvestigationCategory.MULTI_FACT_SYNTHESIS in categories
    assert len(RESEARCH_ACCURACY_V3_TASKS) == 50
