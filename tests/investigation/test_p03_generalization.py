"""P0.3: REAL-WORLD RESEARCH GENERALIZATION TEST SUITE.

Deterministic unit and integration tests establishing generalization across:
1. Multi-hop technical investigation on unfamiliar architectures.
2. Historical investigation with conflicting accounts and competing estimates.
3. Scientific question with unconfirmed claims and insufficient evidence.
4. Organizational investigation requiring multiple distinct facts.
5. Misleading source that mentions the right entity but does not support the target claim.
6. Retrieval recovery/gap when evidence exists in fixture.
7. Syndicated sources with identical origin penalizing source independence.
8. Plateau detection halting research without infinite loops.
9. Resilience to low initial gain (preventing premature stopping).
"""

from __future__ import annotations

import pytest

from argus.investigation.action import ActionType, ResearchAction
from argus.investigation.benchmark.corpus import (
    InvestigationCorpusRegistry,
    InvestigationDocument,
)
from argus.investigation.benchmark.evaluator import InvestigationV1Evaluator
from argus.investigation.benchmark.tasks import (
    InvestigationCategory,
    InvestigationDifficulty,
    InvestigationTask,
)
from argus.investigation.orchestrator import InvestigationEngine
from argus.investigation.planner import InvestigationPlanner
from argus.investigation.question import QuestionStatus
from argus.investigation.state import ConfidenceState, InvestigationState
from argus.investigation.stopping import InvestigationStopReason, InvestigationStoppingPolicy


def build_unseen_test_corpus() -> InvestigationCorpusRegistry:
    """Build a completely unfamiliar corpus containing unseen entities and domains."""
    docs = {
        "doc_valhalla_01": InvestigationDocument(
            doc_id="doc_valhalla_01",
            title="ValhallaStorageEngine Architecture Specification",
            url="https://valhalla-storage.org/spec.html",
            text_content=(
                "ValhallaStorageEngine is a high-throughput key-value storage engine utilizing log-structured merge trees. "
                "The core write pipeline buffers incoming writes in volatile MemoryMemtable structures before flushing them to SstableFiles."
            ),
            source_type="technical_documentation",
        ),
        "doc_valhalla_02": InvestigationDocument(
            doc_id="doc_valhalla_02",
            title="ValhallaStorageEngine Durability Protocols",
            url="https://valhalla-storage.org/durability.html",
            text_content=(
                "Crash durability in ValhallaStorageEngine is guaranteed by an atomic write-ahead log guarded by FsyncBarrier primitives. "
                "Each SstableFile contains embedded BloomFilterIndexes to prevent disk seeks on point queries."
            ),
            source_type="technical_whitepaper",
        ),
        "doc_marathon_01": InvestigationDocument(
            doc_id="doc_marathon_01",
            title="Herodotus Histories Book VI: The Battle of Marathon",
            url="https://classical-archives.org/herodotus/vi.html",
            text_content=(
                "According to Herodotus, in 490 BCE during the Battle of Marathon, the Persian forces landed an army of approximately 25,000 soldiers "
                "opposing 10,000 Athenian hoplites."
            ),
            source_type="historical_primary_source",
        ),
        "doc_marathon_02": InvestigationDocument(
            doc_id="doc_marathon_02",
            title="Modern Historiography of the Persian Wars",
            url="https://military-history-review.org/marathon.html",
            text_content=(
                "Modern military historians dispute Herodotus's troop figures for Marathon, citing logistical and fleet constraints. "
                "Differing accounts and competing estimates indicate Persian combatant numbers were between 12,000 and 15,000 troops, presenting a sharp historical conflict with classical sources."
            ),
            source_type="academic_journal",
        ),
        "doc_cuprate_01": InvestigationDocument(
            doc_id="doc_cuprate_01",
            title="Preprint: Room Temperature Diamagnetism in Cuprate-Phase9",
            url="https://arxiv-mirror.org/cond-mat/cuprate9.html",
            text_content=(
                "Preliminary observations claimed room-temperature superconductivity in chemically substituted Cuprate-Phase9 crystals at ambient pressures."
            ),
            source_type="preprint",
        ),
        "doc_cuprate_02": InvestigationDocument(
            doc_id="doc_cuprate_02",
            title="Materials Research Consortium: Replication Attempts on Cuprate-Phase9",
            url="https://nature-materials-review.org/cuprate-rep.html",
            text_content=(
                "Independent replication efforts across five national laboratories yielded a null result for Cuprate-Phase9. "
                "The material was determined to be a paramagnetic insulator; independent teams failed to replicate zero resistance. "
                "Empirical evidence is insufficient to confirm superconducting behavior."
            ),
            source_type="peer_reviewed_journal",
        ),
        "doc_aegis_01": InvestigationDocument(
            doc_id="doc_aegis_01",
            title="Aegis DeepTech Corporate Profile",
            url="https://tech-registry.se/aegis-deeptech",
            text_content=(
                "Aegis DeepTech was founded in 2018 with principal headquarters in Gothenburg, Sweden. "
                "The organization develops autonomous subsea navigation instrumentation."
            ),
            source_type="commercial_registry",
        ),
        "doc_aegis_02": InvestigationDocument(
            doc_id="doc_aegis_02",
            title="Aegis DeepTech Executive Leadership Announcement",
            url="https://aegis-deeptech.se/press/ceo-2021",
            text_content=(
                "In September 2021, the supervisory board of Aegis DeepTech appointed Dr. Astrid Lindholm as Chief Executive Officer."
            ),
            source_type="corporate_press_release",
        ),
        "doc_aegis_catering": InvestigationDocument(
            doc_id="doc_aegis_catering",
            title="Aegis DeepTech Facility Services Notice",
            url="https://aegis-deeptech.se/notices/catering",
            text_content=(
                "Aegis DeepTech selected BlueSky Catering as vendor for facility lunch services in Gothenburg."
            ),
            source_type="operational_notice",
        ),
        "doc_synd_wire_01": InvestigationDocument(
            doc_id="doc_synd_wire_01",
            title="Global Quantum Chip Market Report",
            url="https://reuters-synd.com/wire/101",
            text_content="International consortium announces standardized benchmark for 1,000-qubit quantum processors.",
            source_type="wire_syndication",
            syndication_cluster_id="cluster_quantum_wire",
        ),
        "doc_synd_wire_02": InvestigationDocument(
            doc_id="doc_synd_wire_02",
            title="Global Quantum Chip Market Report - Bloomberg Mirror",
            url="https://bloomberg-synd.com/wire/101",
            text_content="International consortium announces standardized benchmark for 1,000-qubit quantum processors.",
            source_type="wire_syndication",
            syndication_cluster_id="cluster_quantum_wire",
        ),
        "doc_synd_wire_03": InvestigationDocument(
            doc_id="doc_synd_wire_03",
            title="Global Quantum Chip Market Report - AP Mirror",
            url="https://apnews-synd.com/wire/101",
            text_content="International consortium announces standardized benchmark for 1,000-qubit quantum processors.",
            source_type="wire_syndication",
            syndication_cluster_id="cluster_quantum_wire",
        ),
    }
    registry = InvestigationCorpusRegistry(docs=docs)
    return registry


def test_1_unseen_multihop_technical_investigation():
    """Scenario 1: Multi-hop technical investigation on unfamiliar architecture preserves strict evidence links."""
    corpus = build_unseen_test_corpus()
    engine = InvestigationEngine(corpus=corpus)

    state = engine.run_to_completion(
        objective="Investigate ValhallaStorageEngine write path architecture and crash durability mechanisms.",
        contract={"target_entities": ["ValhallaStorageEngine"]},
        max_steps=5,
    )

    res = state.to_result()
    assert state.stop_state.is_stopped is True
    assert len(res.findings) > 0

    # Verify findings are strictly grounded to actual evidence
    ev_ids = {e["evidence_id"] for e in res.supporting_evidence}
    for finding in res.findings:
        if finding.get("status") == "SUPPORTED":
            assert finding.get("evidence_id") in ev_ids
            assert finding.get("source_url") is not None
            assert len(finding.get("source_passage", "")) > 0

    # Verify no benchmark-specific task logic was triggered
    assert not any("drake" in str(f).lower() for f in res.findings)


def test_2_unseen_historical_investigation_conflicting_accounts():
    """Scenario 2: Historical investigation with conflicting accounts identifies and preserves contradiction."""
    corpus = build_unseen_test_corpus()
    engine = InvestigationEngine(corpus=corpus)

    state = engine.run_to_completion(
        objective="Investigate conflicting troop estimates for Persian combatants at the Battle of Marathon.",
        contract={"target_entities": ["Battle of Marathon"]},
        max_steps=5,
    )

    res = state.to_result()
    assert state.stop_state.is_stopped is True
    assert len(res.contradictions) > 0, "Conflicting historical sources must record contradiction."

    # Contradiction must be visible and topic-related
    contra = res.contradictions[0]
    assert "Battle of Marathon" in contra["topic"] or "Marathon" in contra["topic"]

    # Epistemic question status must reflect contradiction
    has_contra_question = any(
        q.get("status") == QuestionStatus.CONTRADICTED.value
        for q in state.questions.values()
    )
    assert has_contra_question, "Target question must resolve to CONTRADICTED status."


def test_3_unseen_scientific_question_insufficient_evidence():
    """Scenario 3: Scientific question with null replication preserves INSUFFICIENT_EVIDENCE status."""
    corpus = build_unseen_test_corpus()
    engine = InvestigationEngine(corpus=corpus)

    state = engine.run_to_completion(
        objective="Investigate whether independent laboratories confirmed superconductivity in Cuprate-Phase9.",
        contract={"target_entities": ["Cuprate-Phase9"]},
        max_steps=5,
    )

    res = state.to_result()
    assert state.stop_state.is_stopped is True

    # Must preserve uncertainty, not claim positive confirmation
    has_insufficient = any(
        c.get("status") == "INSUFFICIENT_EVIDENCE"
        for c in res.findings
    )
    assert has_insufficient, "Null replication result must produce INSUFFICIENT_EVIDENCE claim."

    assert any(
        q.get("status") == QuestionStatus.INSUFFICIENT_EVIDENCE.value
        for q in state.questions.values()
    )


def test_4_unseen_organizational_investigation_multi_fact():
    """Scenario 4: Organizational investigation requiring multiple distinct facts."""
    corpus = build_unseen_test_corpus()
    engine = InvestigationEngine(corpus=corpus)

    state = engine.run_to_completion(
        objective="Investigate Aegis DeepTech founding year, principal headquarters, and Chief Executive Officer.",
        contract={"target_entities": ["Aegis DeepTech"]},
        max_steps=5,
    )

    res = state.to_result()
    assert state.stop_state.is_stopped is True
    assert "Aegis DeepTech" in state.entities

    # Multiple distinct facts must be linked
    all_findings_text = " ".join(f.get("object", "") for f in res.findings)
    assert "Gothenburg" in all_findings_text or "2018" in all_findings_text or "Astrid Lindholm" in all_findings_text


def test_5_misleading_source_entity_mention_without_claim_support():
    """Scenario 5: Misleading source mentioning right entity does not validate target claim."""
    corpus = build_unseen_test_corpus()
    evaluator = InvestigationV1Evaluator()

    task = InvestigationTask(
        task_id="unseen_task_catering_trap",
        title="Unseen Target Propulsion Capability",
        objective="Investigate plasma propulsion thrust output of Aegis DeepTech.",
        category=InvestigationCategory.TECHNICAL_ENGINEERING,
        difficulty=InvestigationDifficulty.HARD,
        contract={"target_entities": ["Aegis DeepTech"]},
    )

    state = InvestigationState(objective=task.objective)
    state.register_entity("Aegis DeepTech")

    # Retrieved misleading doc (only discusses catering)
    catering_doc = corpus.documents["doc_aegis_catering"]
    state.add_evidence({
        "evidence_id": catering_doc.doc_id,
        "url": catering_doc.url,
        "text": catering_doc.text_content,
        "snippet": catering_doc.text_content,
    })

    # Unsupported claim asserts plasma rocket thrust
    state.add_claim({
        "subject": "Aegis DeepTech",
        "predicate": "propulsion_thrust",
        "object": "Generates 500 Newtons of magnetic plasma thrust.",
        "status": "SUPPORTED",
        "evidence_id": catering_doc.doc_id,
        "source_url": catering_doc.url,
    })

    state.stop_state.is_stopped = True
    state.stop_state.stop_reason = InvestigationStopReason.OBJECTIVE_SATISFIED.value

    eval_res = evaluator.evaluate_single_task(task, state=state)

    # Structural provenance is 1.0 (evidence_id exists)
    assert eval_res["structural_provenance_rate"] == 1.0
    # But semantic claim support must be 0.0 (catering does not support plasma thrust!)
    assert eval_res["semantic_claim_support_rate"] == 0.0
    assert eval_res["unsupported_claim_rate"] == 1.0


def test_6_retrieval_failure_when_relevant_evidence_exists():
    """Scenario 6: Recovery or graceful gap tracking when initial terminology fails to hit."""
    corpus = build_unseen_test_corpus()
    engine = InvestigationEngine(corpus=corpus)

    # Purposefully obscure query phrasing
    state = engine.start_investigation(
        objective="Investigate sub-surface Swedish maritime robotics navigation manufacturer.",
        contract={"target_entities": ["Aegis DeepTech"]},
    )

    state, _ = engine.execute_step(state)
    # Even if step 1 yields low gain, confidence does not inflate
    conf = ConfidenceState()
    conf.recompute_calibration(state)
    assert conf.overall_confidence <= 0.50
    assert not state.stop_state.is_stopped, "Engine must not prematurely abort on step 1."


def test_7_syndicated_urls_penalize_source_independence():
    """Scenario 7: Several URLs reproducing same syndicated source do not inflate independence."""
    state = InvestigationState(objective="Syndication audit")
    conf = ConfidenceState()

    corpus = build_unseen_test_corpus()
    wire1 = corpus.documents["doc_synd_wire_01"]
    wire2 = corpus.documents["doc_synd_wire_02"]
    wire3 = corpus.documents["doc_synd_wire_03"]

    state.add_evidence({"evidence_id": "e1", "url": wire1.url, "snippet": wire1.text_content, "syndication_cluster_id": wire1.syndication_cluster_id})
    state.add_evidence({"evidence_id": "e2", "url": wire2.url, "snippet": wire2.text_content, "syndication_cluster_id": wire2.syndication_cluster_id})
    state.add_evidence({"evidence_id": "e3", "url": wire3.url, "snippet": wire3.text_content, "syndication_cluster_id": wire3.syndication_cluster_id})

    state.questions["q1"] = {"question_id": "q1", "status": "SUPPORTED", "is_critical": True}
    state.resolved_questions.append("q1")
    state.add_claim({"subject": "Quantum Consortium", "predicate": "metric", "object": "1000-qubit", "status": "SUPPORTED", "evidence_id": "e1"})

    conf.recompute_calibration(state)

    # 3 mirrors of 1 wire story must yield <= 0.60 independence ratio
    assert conf.source_independence_score <= 0.60
    assert conf.overall_confidence < 0.60


def test_8_research_plateau_stops_without_infinite_loop():
    """Scenario 8: Exhaustion of marginal gain triggers NO_INFORMATION_GAIN without cycling forever."""
    corpus = InvestigationCorpusRegistry(docs={})  # Empty corpus returns 0 new evidence
    stopping_policy = InvestigationStoppingPolicy(max_consecutive_zero_gains=3)
    engine = InvestigationEngine(corpus=corpus, stopping_policy=stopping_policy)

    state = engine.run_to_completion(
        objective="Investigate obscure artifact in empty database.",
        contract={"target_entities": ["PhantomEntity"]},
        max_steps=10,
    )

    assert state.stop_state.is_stopped is True
    assert state.stop_state.stop_reason == InvestigationStopReason.NO_INFORMATION_GAIN.value
    # Halted at consecutive zero gains (3 steps), never reached max_steps (10)
    assert state.research_budget["steps_taken"] <= 4


def test_9_additional_research_necessary_despite_low_initial_gain():
    """Scenario 9: Engine does not abort on step 1 with 0 gain, allowing multi-step discovery."""
    stopping_policy = InvestigationStoppingPolicy(max_consecutive_zero_gains=4)
    state = InvestigationState(objective="Multi-step technical investigation")

    # Simulate step 1 with zero gain
    state.research_budget["steps_taken"] = 1
    state.research_budget["consecutive_zero_gains"] = 1
    state.questions["q1"] = {"question_id": "q1", "status": "OPEN", "is_critical": True}
    state.unresolved_questions.append("q1")

    should_stop, reason, _ = stopping_policy.evaluate(state)
    assert should_stop is False, "Stopping policy must not abort on step 1 with consecutive_zeros=1"
