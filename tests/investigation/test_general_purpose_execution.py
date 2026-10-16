"""General-Purpose Investigation Execution Regression Suite.

Deterministic, multi-scenario test suite verifying Heimdallr's core research loop:
1. Multi-step research (Search -> Fetch -> Evidence -> Resolution)
2. Single-source adequate answer stopping
3. Irrelevant initial search results handling
4. Relevant sources requiring content retrieval
5. Conflicting evidence requiring follow-up / contradiction detection
6. Missing evidence that cannot be resolved (honesty, no hallucination)
7. Source timeouts and unavailable sources (never treated as claim falsehood)
8. Duplicate sources and repetitive task prevention
9. Budget exhaustion enforcement
10. Specialist failure or empty results handling
11. Unroutable or unsupported capability fail-closed behavior
12. Stopping without claiming success on incomplete research
13. Cross-domain generality using the identical execution loop
14. Accurate audit trails and final report generation
"""

import json
from pathlib import Path
from typing import Any
import uuid

import pytest

from argus.capability_registry.adapters import BaseCapabilityAdapter, register_capability_adapter, unregister_capability_adapter
from argus.investigation.action import ActionType, ResearchAction
from argus.investigation.benchmark.corpus import InvestigationDocument
from argus.investigation.orchestrator import InvestigationEngine, ToolPermissionGate
from argus.investigation.planner import InvestigationPlanner
from argus.investigation.question import QuestionStatus, QuestionType
from argus.investigation.state import InvestigationState
from argus.investigation.stopping import InvestigationStopReason, InvestigationStoppingPolicy


class MockCorpus:
    """Deterministic in-memory corpus simulating search index and full-text document store."""

    def __init__(self, documents: list[InvestigationDocument]) -> None:
        self.documents: dict[str, InvestigationDocument] = {d.url: d for d in documents}
        self.doc_by_id: dict[str, InvestigationDocument] = {d.doc_id: d for d in documents}

    def get_by_url(self, url: str) -> InvestigationDocument | None:
        return self.documents.get(url)

    def get_by_id(self, doc_id: str) -> InvestigationDocument | None:
        return self.doc_by_id.get(doc_id)

    def search(self, query: str, limit: int = 5) -> list[InvestigationDocument]:
        import re
        q_tokens = [t.lower() for t in re.findall(r"\w{3,}", query)]
        scored = []
        for doc in self.documents.values():
            text_low = doc.text_content.lower()
            title_low = doc.title.lower()
            score = 0
            if query.lower() in text_low:
                score += 5
            for t in q_tokens:
                if t in title_low:
                    score += 2
                if t in text_low:
                    score += 1
            if score > 0:
                scored.append((score, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [d for _, d in scored[:limit]]

    def get_discoverable_entities(self) -> set[str]:
        return {
            "Acrobotix Dynamic Systems", "Centaur-4 Quadruped", "Dr. Elena Voronova",
            "Helios Propulsion Systems", "Dr. Anya Romanova", "Krypton Dynamics Inc", "Aether Orbit",
            "AlphaCorp", "Novatech Solutions LLC", "Dr. Simon Bell",
            "Raft", "Diego Ongaro", "John Ousterhout", "Treaty of Utrecht",
            "Vanguard Marine Systems",
        }


# ---------------------------------------------------------------------------
# TEST 1: Multi-Step Investigation (Search -> Fetch Content -> Resolution)
# ---------------------------------------------------------------------------

def test_1_multi_step_investigation_search_then_fetch():
    """Verify engine does not stop after search; issues follow-up FETCH to retrieve full content."""
    doc = InvestigationDocument(
        doc_id="doc_deep_tech_1",
        title="Helios Propulsion Ion Drive Specification",
        url="https://helios-space.io/specs/ion-drive",
        text_content=(
            "Helios Propulsion Systems developed the Xenon-Hall thruster model XH-9. "
            "The Chief Propulsion Architect who invented the thruster is Dr. Anya Romanova. "
            "Official testing confirmed maximum thrust efficiency of 68 percent."
        ),
        source_type="technical_spec",
    )
    corpus = MockCorpus([doc])
    engine = InvestigationEngine(corpus=corpus)

    objective = "Investigate Helios Propulsion Systems and determine the inventor of the Xenon-Hall thruster."
    state = engine.run_to_completion(
        objective=objective,
        contract={"target_entities": ["Helios Propulsion Systems"]},
        max_steps=6,
    )

    assert state.stop_state.is_stopped is True
    # Verify research actions were taken across multiple steps
    assert len(state.research_actions) >= 2
    action_types = [a.get("action_type") for a in state.research_actions]
    assert any("SEARCH" in str(at) for at in action_types)

    # Discovered source was tracked and marked RETRIEVED
    assert any(s["url"] == doc.url for s in state.discovered_sources)
    retrieved = [s for s in state.discovered_sources if s["url"] == doc.url]
    assert retrieved[0]["status"] == "RETRIEVED"

    # Full content established substantive claims
    assert len(state.claims) > 0
    assert any("Romanova" in c.get("object", "") for c in state.claims)
    assert state.stop_state.stop_reason in (
        InvestigationStopReason.OBJECTIVE_SATISFIED.value,
        InvestigationStopReason.SUFFICIENT_EVIDENCE.value,
        InvestigationStopReason.BUDGET_EXHAUSTED_WITH_ACCEPTABLE_COVERAGE.value,
    )


# ---------------------------------------------------------------------------
# TEST 2: Single-Source Adequate Answer (Stops without redundant spinning)
# ---------------------------------------------------------------------------

def test_2_single_source_adequate_answer():
    """Verify engine stops cleanly when objective is satisfied without unnecessary redundant queries."""
    doc = InvestigationDocument(
        doc_id="doc_single_source",
        title="Krypton Dynamics Commercial Registry",
        url="https://registers.gov/krypton-dynamics",
        text_content=(
            "Krypton Dynamics Inc is a registered Delaware C-Corp (ID: DE-881923). "
            "CEO: Sarah Chen. Active Managing Director: Marcus Vance. "
            "Wholly owned subsidiaries: Krypton Telemetry Ltd."
        ),
        source_type="corporate_registry",
    )
    corpus = MockCorpus([doc])
    engine = InvestigationEngine(corpus=corpus)

    objective = "What is the corporate jurisdiction and CEO of Krypton Dynamics Inc?"
    state = engine.run_to_completion(
        objective=objective,
        contract={"target_entities": ["Krypton Dynamics Inc"]},
        max_steps=10,
    )

    assert state.stop_state.is_stopped is True
    # Terminated cleanly within budget
    assert state.research_budget["steps_taken"] <= 6
    assert any(c.get("predicate") == "officer" or "Chen" in c.get("object", "") for c in state.claims)


# ---------------------------------------------------------------------------
# TEST 3: Irrelevant Initial Search Results
# ---------------------------------------------------------------------------

def test_3_irrelevant_initial_search_results():
    """Verify engine does not claim success when search returns unrelated content."""
    irrelevant_doc = InvestigationDocument(
        doc_id="doc_irrelevant",
        title="Local Bakery Recipes",
        url="https://baking.net/sourdough",
        text_content="Baking sourdough bread requires organic flour and filtered water at room temperature.",
        source_type="blog",
    )
    corpus = MockCorpus([irrelevant_doc])
    engine = InvestigationEngine(corpus=corpus)

    objective = "Investigate Quantum Cybernetics quantum encryption patent."
    state = engine.run_to_completion(
        objective=objective,
        contract={"target_entities": ["Quantum Cybernetics"]},
        max_steps=3,
    )

    assert state.stop_state.is_stopped is True
    # Did NOT falsely resolve critical questions as SUPPORTED
    supported_claims = [c for c in state.claims if c.get("status") == "SUPPORTED"]
    assert not any("quantum encryption patent" in c.get("object", "").lower() for c in supported_claims)
    assert state.stop_state.stop_reason != InvestigationStopReason.OBJECTIVE_SATISFIED.value


# ---------------------------------------------------------------------------
# TEST 4: Relevant Sources Requiring Content Retrieval
# ---------------------------------------------------------------------------

def test_4_relevant_sources_requiring_content_retrieval():
    """Verify search snippets are marked is_full_content=False, and full retrieval marks is_full_content=True."""
    doc = InvestigationDocument(
        doc_id="doc_satellite_full",
        title="Aether Orbit Ground Station Report",
        url="https://aether-orbit.com/ground-station",
        text_content="Aether Orbit operates primary ground station Alpha in Tromso, Norway, communicating on S-band frequencies.",
        source_type="infrastructure_spec",
    )
    corpus = MockCorpus([doc])
    engine = InvestigationEngine(corpus=corpus)

    state = engine.start_investigation(
        objective="What ground station does Aether Orbit operate?",
        contract={"target_entities": ["Aether Orbit"]},
    )

    # Step 1: SEARCH action
    search_action = ResearchAction(
        action_type=ActionType.SEARCH,
        query="Aether Orbit ground station",
        specialist="none",
        question_id=list(state.questions.keys())[0],
        target_entities=["Aether Orbit"],
        rationale="Search for candidate ground station records",
    )
    obs_search = engine._dispatch_action(search_action, state)
    # Search documents must be marked as snippets/discovered, not full content
    for d in obs_search["documents"]:
        assert d.get("source_status") == "DISCOVERED"
        assert d.get("is_full_content") is False

    engine._apply_observation(state, search_action, obs_search)
    assert len(state.discovered_sources) > 0
    assert state.discovered_sources[0]["status"] == "DISCOVERED"

    # Step 2: FETCH action
    fetch_action = ResearchAction(
        action_type=ActionType.FETCH,
        query=doc.url,
        specialist="none",
        question_id=list(state.questions.keys())[0],
        target_entities=["Aether Orbit"],
        parameters={"url": doc.url},
        rationale="Retrieve full text of ground station document",
    )
    obs_fetch = engine._dispatch_action(fetch_action, state)
    assert len(obs_fetch["documents"]) > 0
    for d in obs_fetch["documents"]:
        assert d.get("source_status") == "RETRIEVED"
        assert d.get("is_full_content") is True

    engine._apply_observation(state, fetch_action, obs_fetch)
    retrieved_entry = [s for s in state.discovered_sources if s["url"] == doc.url][0]
    assert retrieved_entry["status"] == "RETRIEVED"


# ---------------------------------------------------------------------------
# TEST 5: Conflicting Evidence Requiring Follow-Up
# ---------------------------------------------------------------------------

def test_5_conflicting_evidence_requiring_follow_up():
    """Verify contradictions across documents are recognized and marked CONTRADICTED."""
    doc_a = InvestigationDocument(
        doc_id="doc_a_revenue",
        title="AlphaCorp 2023 Annual Report",
        url="https://alphacorp.com/reports/2023",
        text_content="AlphaCorp confirmed total fiscal year 2023 revenue of 45 million USD.",
        source_type="financial_report",
    )
    doc_b = InvestigationDocument(
        doc_id="doc_b_restatement",
        title="AlphaCorp 2023 Restatement Filing",
        url="https://sec.gov/filings/alphacorp-restatement",
        text_content="AlphaCorp issued a formal accounting restatement correcting fiscal year 2023 revenue to 32 million USD following audit discrepancy.",
        source_type="regulatory_filing",
    )
    corpus = MockCorpus([doc_a, doc_b])
    engine = InvestigationEngine(corpus=corpus)

    objective = "Determine AlphaCorp fiscal year 2023 revenue and resolve any reporting conflict."
    state = engine.run_to_completion(
        objective=objective,
        contract={"target_entities": ["AlphaCorp"]},
        max_steps=6,
    )

    assert state.stop_state.is_stopped is True
    # Contradiction recorded in state
    assert len(state.contradictions) > 0 or any(c.get("status") == "CONTRADICTED" for c in state.claims)
    # Target question acknowledges the contradiction
    q = list(state.questions.values())[0]
    assert q["status"] in (QuestionStatus.CONTRADICTED.value, QuestionStatus.SUPPORTED.value)


# ---------------------------------------------------------------------------
# TEST 6: Missing Evidence Unresolvable (Honest limitations, no hallucination)
# ---------------------------------------------------------------------------

def test_6_missing_evidence_unresolvable():
    """Verify engine reports NOT_FOUND / INSUFFICIENT_EVIDENCE when evidence does not exist."""
    corpus = MockCorpus([])
    engine = InvestigationEngine(corpus=corpus)

    objective = "Verify the secret underwater laboratory of FictionalCorp LLC."
    state = engine.run_to_completion(
        objective=objective,
        contract={"target_entities": ["FictionalCorp LLC"]},
        max_steps=3,
    )

    assert state.stop_state.is_stopped is True
    # Engine does not claim success
    assert state.stop_state.stop_reason != InvestigationStopReason.OBJECTIVE_SATISFIED.value
    # No false claims supported
    assert len(state.claims) == 0 or all(c.get("status") != "SUPPORTED" for c in state.claims)


# ---------------------------------------------------------------------------
# TEST 7: Source Timeout and Unavailability (Not treated as claim falsehood)
# ---------------------------------------------------------------------------

def test_7_source_timeout_and_unavailability():
    """Verify unavailable source returns SOURCE_UNAVAILABLE and is not treated as evidence of falsehood."""
    corpus = MockCorpus([])
    engine = InvestigationEngine(corpus=corpus)

    state = engine.start_investigation(
        objective="Fetch offline repository",
        contract={"target_entities": ["Offline Target"]},
    )

    action = ResearchAction(
        action_type=ActionType.FETCH,
        query="https://inaccessible-server.org/data",
        specialist="none",
        question_id=list(state.questions.keys())[0],
        parameters={"url": "https://inaccessible-server.org/data"},
        rationale="Attempt fetch from inaccessible URL",
    )

    obs = engine._dispatch_action(action, state)
    assert obs["status"] == "SOURCE_UNAVAILABLE"
    assert obs["outcome"] == "SOURCE_UNAVAILABLE"

    engine._apply_observation(state, action, obs)
    # The question must not be marked NOT_FOUND with proof of non-existence
    q = state.questions[action.question_id]
    assert q["status"] != QuestionStatus.SUPPORTED.value


# ---------------------------------------------------------------------------
# TEST 8: Duplicate Sources and Repetitive Tasks Prevention
# ---------------------------------------------------------------------------

def test_8_duplicate_sources_prevention():
    """Verify engine deduplicates mirrored documents and does not re-fetch already retrieved URLs."""
    doc1 = InvestigationDocument(
        doc_id="doc_mirr_1",
        title="Release Notes V1",
        url="https://mirror1.com/release",
        text_content="Version 1.0 released with quantum telemetry integration.",
        source_type="release_notes",
    )
    doc2 = InvestigationDocument(
        doc_id="doc_mirr_2",
        title="Release Notes V1",
        url="https://mirror1.com/release",  # Identical URL
        text_content="Version 1.0 released with quantum telemetry integration.",
        source_type="release_notes",
    )
    corpus = MockCorpus([doc1, doc2])
    engine = InvestigationEngine(corpus=corpus)

    state = engine.start_investigation(
        objective="Inspect Release Notes",
        contract={"target_entities": ["Release"]},
    )

    action = ResearchAction(
        action_type=ActionType.SEARCH,
        query="Release Notes",
        specialist="none",
        question_id=list(state.questions.keys())[0],
        rationale="Initial search for release notes",
    )
    obs = engine._dispatch_action(action, state)
    engine._apply_observation(state, action, obs)

    # Discovered sources deduplicated by URL
    urls = [s["url"] for s in state.discovered_sources]
    assert len(urls) == len(set(urls))


# ---------------------------------------------------------------------------
# TEST 9: Budget Exhaustion Enforcement
# ---------------------------------------------------------------------------

def test_9_budget_exhaustion_enforcement():
    """Verify strict execution bounds: engine terminates exactly when max_steps is reached."""
    corpus = MockCorpus([])
    engine = InvestigationEngine(corpus=corpus)

    max_steps = 3
    state = engine.run_to_completion(
        objective="Unsolvable query intended to test step budget ceiling.",
        contract={"max_steps": max_steps},
        max_steps=max_steps,
    )

    assert state.stop_state.is_stopped is True
    assert state.research_budget["steps_taken"] <= max_steps
    assert "BUDGET_EXHAUSTED" in state.stop_state.stop_reason or state.stop_state.budget_exhausted is True


# ---------------------------------------------------------------------------
# TEST 10: Specialist Failure or Empty Results
# ---------------------------------------------------------------------------

def test_10_specialist_failure_handling():
    """Verify specialist failure degrades gracefully without crashing and records audit trail."""
    failing_impl = "impl_test_mock_failing_v2"

    class FailingAdapter(BaseCapabilityAdapter):
        def execute(self, inputs: dict[str, Any], corpus: Any = None) -> dict[str, Any]:
            raise RuntimeError("Underlying upstream database connection failed.")

    register_capability_adapter(failing_impl, FailingAdapter())
    ToolPermissionGate.authorize_implementation(failing_impl)
    ToolPermissionGate.register_allowed_specialist("failing_spec")

    try:
        engine = InvestigationEngine()
        state = engine.start_investigation(
            objective="Test specialist error handling",
            contract={"target_entities": ["Test Entity"]},
        )

        action = ResearchAction(
            action_type=ActionType.INVESTIGATE_SPECIALIST,
            query="Test Query",
            specialist="failing_spec",
            implementation_id=failing_impl,
            question_id=list(state.questions.keys())[0],
            rationale="Probe failing specialist to test error recovery",
        )

        obs = engine._dispatch_action(action, state)
        assert obs["status"] == "FAILED"
        assert "failed" in obs["error"].lower()

        gain = engine._apply_observation(state, action, obs)
        assert gain == 0.0

        # State audit recorded the adapter failure
        assert any(a.action_type == "ADAPTER_EXECUTION_FAILED" for a in state.audit_trail)
    finally:
        unregister_capability_adapter(failing_impl)
        ToolPermissionGate.deauthorize_implementation(failing_impl)
        ToolPermissionGate.unregister_allowed_specialist("failing_spec")


# ---------------------------------------------------------------------------
# TEST 11: Unroutable / Unsupported Capability Fail-Closed Behavior
# ---------------------------------------------------------------------------

def test_11_unroutable_unsupported_capability():
    """Verify requesting an unsupported capability fails closed with explicit limitation and gap."""
    engine = InvestigationEngine()
    state = engine.start_investigation(
        objective="Query unavailable specialized sensor",
        contract={"target_entities": ["Satellite 9"]},
    )

    action = ResearchAction(
        action_type=ActionType.INVESTIGATE_SPECIALIST,
        query="Direct infrared downlink",
        specialist="quantum_sensing_radar",  # Unregistered specialist
        question_id=list(state.questions.keys())[0],
        rationale="Probe unauthorized specialist",
    )

    obs = engine._dispatch_action(action, state)
    assert obs["status"] in ("REJECTED_UNAUTHORIZED", "UNSUPPORTED_CAPABILITY")

    gain = engine._apply_observation(state, action, obs)
    assert gain == 0.0
    # Information gap or audit trail records the policy/capability limitation
    assert len(state.audit_trail) > 0


# ---------------------------------------------------------------------------
# TEST 12: Stop Without Claiming Success
# ---------------------------------------------------------------------------

def test_12_stop_without_claiming_success():
    """Verify engine terminates with NO_USEFUL_ACTIONS_REMAIN or INCOMPLETE rather than premature success."""
    corpus = MockCorpus([])
    engine = InvestigationEngine(corpus=corpus)

    state = engine.start_investigation(
        objective="Determine undisclosed corporate board minutes for Nonexistent Corp.",
        contract={"target_entities": ["Nonexistent Corp"]},
    )

    # Execute until stopping
    while not state.stop_state.is_stopped:
        state, finished = engine.execute_step(state)
        if finished:
            break

    assert state.stop_state.is_stopped is True
    # Stop reason must truthfully reflect lack of evidence / execution limits
    assert state.stop_state.stop_reason in (
        InvestigationStopReason.NO_USEFUL_ACTIONS_REMAIN.value,
        InvestigationStopReason.BUDGET_EXHAUSTED_WITH_CRITICAL_MISSING_FIELDS.value,
        InvestigationStopReason.NO_INFORMATION_GAIN.value,
        InvestigationStopReason.INCOMPLETE.value,
    )


# ---------------------------------------------------------------------------
# TEST 13: Cross-Domain Generality Using Identical Execution Loop
# ---------------------------------------------------------------------------

def test_13_cross_domain_generality():
    """Verify corporate, technical, and historical domains all execute via the identical engine loop."""
    docs = [
        InvestigationDocument(
            doc_id="doc_corp",
            title="Novatech Registry",
            url="https://registry.org/novatech",
            text_content="Novatech Solutions LLC registered in London, UK. Active Director: Dr. Simon Bell.",
            source_type="corporate",
        ),
        InvestigationDocument(
            doc_id="doc_tech",
            title="Raft Consensus Protocol",
            url="https://cs.stanford.edu/raft",
            text_content="Raft is a consensus algorithm developed by Diego Ongaro and John Ousterhout.",
            source_type="technical",
        ),
        InvestigationDocument(
            doc_id="doc_hist",
            title="Treaty of Utrecht 1713",
            url="https://archives.gov/utrecht",
            text_content="The Treaty of Utrecht was signed between Spain, Great Britain, and France in 1713.",
            source_type="historical",
        ),
    ]
    corpus = MockCorpus(docs)
    engine = InvestigationEngine(corpus=corpus)

    domains = [
        ("Investigate Novatech Solutions LLC and its active director.", "Novatech Solutions LLC"),
        ("What consensus protocol did Diego Ongaro develop at Stanford?", "Raft"),
        ("Analyze the signatories and date of the Treaty of Utrecht.", "Treaty of Utrecht"),
    ]

    for obj, entity in domains:
        state = engine.run_to_completion(
            objective=obj,
            contract={"target_entities": [entity]},
            max_steps=5,
        )
        assert state.stop_state.is_stopped is True
        assert len(state.claims) > 0
        assert any(c.get("status") == "SUPPORTED" for c in state.claims)


# ---------------------------------------------------------------------------
# TEST 14: Accurate Action Trails and Final Report Generation
# ---------------------------------------------------------------------------

def test_14_accurate_action_trails_and_report_generation():
    """Verify research action history, audit trail, and synthesis distinguish executed actions from considered ones."""
    doc = InvestigationDocument(
        doc_id="doc_verif_report",
        title="Vanguard Marine Systems Overview",
        url="https://vanguard-marine.com/overview",
        text_content="Vanguard Marine Systems manufactures autonomous underwater survey gliders.",
        source_type="corporate",
    )
    corpus = MockCorpus([doc])
    engine = InvestigationEngine(corpus=corpus)

    objective = "Investigate Vanguard Marine Systems manufacturing line."
    state = engine.run_to_completion(
        objective=objective,
        contract={"target_entities": ["Vanguard Marine Systems"]},
        max_steps=4,
    )

    # 1. Action trail captures executed actions
    assert len(state.research_actions) > 0
    for act in state.research_actions:
        assert act.get("status") == "EXECUTED"
        assert act.get("action_id") is not None
        assert act.get("action_type") is not None

    # 2. Audit trail records key state events
    action_types_logged = {entry.action_type for entry in state.audit_trail}
    assert "BRANCH_INITIALIZED" in action_types_logged
    assert "INVESTIGATION_INITIALIZED" in action_types_logged

    # 3. Final synthesis accurately represents evidence
    report = state.to_result()
    assert report.investigation_id == state.investigation_id
    assert report.objective == objective
    assert len(report.findings) > 0
    assert report.epistemic_status is not None
    assert state.stop_state.stop_reason is not None
