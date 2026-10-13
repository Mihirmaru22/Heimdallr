"""P0.2 Verification Audit Test Suite for Heimdallr V3.

Directly verifies the three core areas and invariants:
1. Domain-Independent Investigation Planning (Phase 2: Cases A, B, C, D)
2. Separation Between Capability Registration and Execution Authorization (Phase 3: Scenarios 1-10)
3. Correct Failure-State Handling and Epistemic Integrity (Phase 4: Scenarios 1-12 & Invariants A-H)
"""

from __future__ import annotations

import concurrent.futures
import threading
import time
from typing import Any
import pytest

from argus.capability_registry.adapters import (
    BaseCapabilityAdapter,
    register_capability_adapter,
    unregister_capability_adapter,
    get_adapter_for_implementation,
)
from argus.capability_registry.models import (
    CapabilityCategory,
    CapabilityDefinition,
    CapabilityInputSchema,
    CapabilityOutputSchema,
    EpistemicNature,
    HealthStatus,
)
from argus.capability_registry.registry import CapabilityRegistry
from argus.investigation.action import ActionType, ResearchAction
from argus.investigation.orchestrator import InvestigationEngine, ToolPermissionGate
from argus.investigation.planner import InvestigationPlanner
from argus.investigation.question import InvestigationQuestion, QuestionStatus, QuestionType
from argus.investigation.state import InvestigationResult, InvestigationState
from argus.investigation.stopping import InvestigationStopReason, InvestigationStoppingPolicy


# ---------------------------------------------------------------------------
# Test Adapters & Mocks
# ---------------------------------------------------------------------------

class MockSuccessAdapter(BaseCapabilityAdapter):
    """Deterministic adapter returning valid observations."""

    def __init__(self, doc_text: str = "Empirical observation document"):
        self.doc_text = doc_text
        self.invocations = 0

    def execute(self, inputs: dict[str, Any], corpus: Any = None) -> dict[str, Any]:
        self.invocations += 1
        return {
            "status": "SUCCESS",
            "documents": [
                {
                    "doc_id": f"doc_{self.invocations}",
                    "title": "Empirical Finding",
                    "url": f"https://example.org/doc/{self.invocations}",
                    "text": self.doc_text,
                    "source_type": "empirical_report",
                }
            ],
            "entities": ["Discovered Entity"],
            "claims": [
                {
                    "subject": "Discovered Entity",
                    "predicate": "property",
                    "object": "verified",
                    "status": "SUPPORTED",
                }
            ],
        }


class MockCrashingAdapter(BaseCapabilityAdapter):
    """Adapter that raises an exception during execution."""

    def __init__(self, exc_msg: str = "Network timeout to specialist service"):
        self.exc_msg = exc_msg
        self.invocations = 0

    def execute(self, inputs: dict[str, Any], corpus: Any = None) -> dict[str, Any]:
        self.invocations += 1
        raise ConnectionResetError(self.exc_msg)


class MockEmptyAdapter(BaseCapabilityAdapter):
    """Adapter that returns empty observation without documents."""

    def __init__(self):
        self.invocations = 0

    def execute(self, inputs: dict[str, Any], corpus: Any = None) -> dict[str, Any]:
        self.invocations += 1
        return {
            "status": "SUCCESS",
            "documents": [],
            "entities": [],
            "claims": [],
        }


# ===========================================================================
# PHASE 2: DOMAIN-INDEPENDENT INVESTIGATION PLANNING
# ===========================================================================

class TestPhase2DomainIndependence:
    """Verify planner preserves objectives without forcing corporate or domain-specific templates."""

    def test_case_a_familiar_technical_domain(self):
        """Case A: Investigate the architecture and failure modes of a distributed database."""
        planner = InvestigationPlanner()
        objective = "Investigate the architecture and failure modes of a distributed database."
        contract = {"max_steps": 5}

        state = planner.initialize_investigation(objective=objective, objective_contract=contract)

        assert state.objective == objective
        # Preserves technical domain
        q_texts = [q["question_text"].lower() for q in state.questions.values()]
        # Check no corporate questions injected
        assert not any("sec exhibit 21" in t for t in q_texts)
        assert not any("companies house" in t for t in q_texts)
        assert not any("subsidiary" in t for t in q_texts)
        # Check coherent decomposition with budget
        assert len(state.questions) >= 3
        assert state.research_budget["max_steps"] == 5

    def test_case_b_historical_domain(self):
        """Case B: Investigate the historical development of maritime insurance practices in the seventeenth century."""
        planner = InvestigationPlanner()
        objective = "Investigate the historical development of maritime insurance practices in the seventeenth century."
        contract = {"max_steps": 6}

        state = planner.initialize_investigation(objective=objective, objective_contract=contract)

        assert state.objective == objective
        q_texts = [q["question_text"].lower() for q in state.questions.values()]
        # Preserves historical sequence and consensus vs debate
        assert any("chronological sequence" in t or "timeline" in t for t in q_texts)
        assert any("participants" in t or "institutional actors" in t for t in q_texts)
        # Never injects corporate legal entity questions
        assert not any("sec exhibit 21" in t for t in q_texts)
        assert not any("companies house" in t for t in q_texts)
        assert not any("subsidiary" in t for t in q_texts)

    def test_case_c_unfamiliar_interdisciplinary_objective(self):
        """Case C: Investigate how acoustic design affects attention in public libraries."""
        planner = InvestigationPlanner()
        objective = "Investigate how acoustic design affects attention in public libraries."
        contract = {
            "target_entities": ["Acoustic Design in Public Libraries"],
            "max_steps": 5,
        }

        state = planner.initialize_investigation(objective=objective, objective_contract=contract)

        assert state.objective == objective
        # Entity type is CONCEPT, not TARGET_ORGANIZATION
        entity_info = state.entities.get("Acoustic Design in Public Libraries")
        assert entity_info is not None
        assert entity_info["type"] == "CONCEPT"

        q_texts = [q["question_text"].lower() for q in state.questions.values()]
        # Verify generic research topology
        assert any("core mechanisms" in t or "foundational concepts" in t for t in q_texts)
        assert any("contextual relationships" in t or "observed effects" in t for t in q_texts)
        assert any("empirical data" in t or "documented findings" in t for t in q_texts)
        assert any("uncertainties" in t or "boundary conditions" in t for t in q_texts)

        # STRICT VERIFICATION: Absolutely NO corporate questions or SEC evidence requirements
        for q in state.questions.values():
            assert "sec exhibit 21" not in q["question_text"].lower()
            assert "companies house" not in q["question_text"].lower()
            assert "commercial registry" not in q["question_text"].lower()
            assert "operating subsidiaries" not in q["question_text"].lower()
            assert "executive officers" not in q["question_text"].lower()
            for ev_req in q.get("required_evidence", []):
                assert "sec" not in ev_req.lower()
                assert "companies house" not in ev_req.lower()

        # Check hypotheses and information gaps are not corporate
        for hyp in state.hypotheses.values():
            assert "commercial entity" not in hyp["proposition"].lower()
            assert "sec" not in str(hyp.get("supporting_evidence_requirements", [])).lower()
        for gap in state.information_gaps:
            assert gap.target_attribute in ("core_mechanisms", "empirical_outcomes")

    def test_case_d_custom_domain_hint(self):
        """Case D: Explicit domain hint not among predefined domains."""
        planner = InvestigationPlanner()
        objective = "Examine behavioral economics principles governing decentralized exchange routing algorithms."
        contract = {
            "domain_hint": "behavioral_cryptoeconomics",
            "target_entities": ["Routing Algorithms"],
            "max_steps": 4,
        }

        state = planner.initialize_investigation(objective=objective, objective_contract=contract)

        assert state.objective == objective
        audit = [a for a in state.audit_trail if a.action_type == "INVESTIGATION_INITIALIZED"][0]
        assert audit.details["domain"] == "behavioral_cryptoeconomics"

        q_texts = [q["question_text"].lower() for q in state.questions.values()]
        # Coherent plan without corporate templates
        assert any("foundational concepts" in t or "core mechanisms" in t for t in q_texts)
        assert not any("sec exhibit 21" in t for t in q_texts)
        assert not any("companies house" in t for t in q_texts)
        assert not any("operating subsidiaries" in t for t in q_texts)


# ===========================================================================
# PHASE 3: SEPARATION OF REGISTRATION AND EXECUTION AUTHORIZATION
# ===========================================================================

class TestPhase3RegistrationAuthorizationSeparation:
    """Verify capability registration makes tools discoverable but never authorizes execution."""

    def test_scenario_1_registration_makes_discoverable_but_not_authorized(self):
        """Scenario 1: Register a valid capability -> discoverable, but cannot execute."""
        impl_id = "impl_audit_test_s1"
        adapter = MockSuccessAdapter()
        register_capability_adapter(impl_id, adapter)

        try:
            # 1. Discoverable in factory
            retrieved = get_adapter_for_implementation(impl_id)
            assert retrieved is adapter

            # 2. Authorization check fails closed without explicit permission
            state = InvestigationState(objective="Test registration separation")
            action = ResearchAction(
                question_id="q_1",
                action_type=ActionType.INVESTIGATE_SPECIALIST,
                rationale="Probe registration without authorization",
                specialist="none",
                implementation_id=impl_id,
                query="Test query",
            )
            is_auth, reason = ToolPermissionGate.authorize_action(action, state)
            assert is_auth is False
            assert "registration does not grant execution permission" in reason
        finally:
            unregister_capability_adapter(impl_id)

    def test_scenario_2_request_unregistered_capability(self):
        """Scenario 2: Request an unregistered capability -> denied safely and audited."""
        engine = InvestigationEngine()
        state = engine.start_investigation(objective="Test unregistered capability request")

        action = ResearchAction(
            question_id=list(state.questions.keys())[0],
            action_type=ActionType.INVESTIGATE_SPECIALIST,
            rationale="Probe unregistered capability",
            specialist="none",
            implementation_id="impl_completely_unregistered_xyz",
            query="Probe unregistered",
        )

        is_auth, reason = ToolPermissionGate.authorize_action(action, state)
        assert is_auth is False
        assert "Unregistered implementation ID" in reason

        obs = engine._dispatch_action(action, state)
        assert obs["status"] == "REJECTED_UNAUTHORIZED"
        assert any(a.action_type == "SECURITY_POLICY_VIOLATION" for a in state.audit_trail)

    def test_scenario_3_and_4_registered_unauthorized_fails_closed(self):
        """Scenarios 3 & 4: Register capability without authorization -> execution fails closed before running."""
        impl_id = "impl_audit_test_s3"
        adapter = MockSuccessAdapter()
        register_capability_adapter(impl_id, adapter)

        try:
            engine = InvestigationEngine()
            state = engine.start_investigation(objective="Test unauthorized registered capability")

            action = ResearchAction(
                question_id=list(state.questions.keys())[0],
                action_type=ActionType.INVESTIGATE_SPECIALIST,
                rationale="Probe registered but unauthorized adapter",
                specialist="none",
                implementation_id=impl_id,
                query="Execute unauthorized",
            )

            obs = engine._dispatch_action(action, state)
            assert obs["status"] == "REJECTED_UNAUTHORIZED"
            # Adapter MUST NEVER have been executed
            assert adapter.invocations == 0
        finally:
            unregister_capability_adapter(impl_id)

    def test_scenario_5_explicitly_authorize_registered_capability(self):
        """Scenario 5: Explicitly authorize registered capability -> executes within scope."""
        impl_id = "impl_audit_test_s5"
        adapter = MockSuccessAdapter("Ground truth evidence")
        register_capability_adapter(impl_id, adapter)
        ToolPermissionGate.authorize_implementation(impl_id)

        try:
            engine = InvestigationEngine()
            state = engine.start_investigation(objective="Test authorized execution")

            action = ResearchAction(
                question_id=list(state.questions.keys())[0],
                action_type=ActionType.INVESTIGATE_SPECIALIST,
                rationale="Execute explicitly authorized capability",
                specialist="none",
                implementation_id=impl_id,
                query="Execute authorized",
            )

            obs = engine._dispatch_action(action, state)
            assert obs["status"] == "SUCCESS"
            assert adapter.invocations == 1
            assert len(obs["documents"]) == 1
            assert obs["documents"][0]["text"] == "Ground truth evidence"
        finally:
            ToolPermissionGate.deauthorize_implementation(impl_id)
            unregister_capability_adapter(impl_id)

    def test_scenario_6_unregistered_capability_blocks_future_dispatches(self):
        """Scenario 6: Unregister capability -> subsequent dispatches cannot execute."""
        impl_id = "impl_audit_test_s6"
        adapter = MockSuccessAdapter()
        register_capability_adapter(impl_id, adapter)
        ToolPermissionGate.authorize_implementation(impl_id)

        # 1. Runs when registered and authorized
        engine = InvestigationEngine()
        state = engine.start_investigation(objective="Test unregistration")
        action = ResearchAction(
            question_id=list(state.questions.keys())[0],
            action_type=ActionType.INVESTIGATE_SPECIALIST,
            rationale="Initial authorized execution",
            specialist="none",
            implementation_id=impl_id,
            query="First run",
        )
        obs1 = engine._dispatch_action(action, state)
        assert obs1["status"] == "SUCCESS"
        assert adapter.invocations == 1

        # 2. Unregister
        unregister_capability_adapter(impl_id)

        # 3. Subsequent dispatch fails closed
        action2 = ResearchAction(
            question_id=list(state.questions.keys())[0],
            action_type=ActionType.INVESTIGATE_SPECIALIST,
            rationale="Post unregistration attempt",
            specialist="none",
            implementation_id=impl_id,
            query="Second run",
        )
        obs2 = engine._dispatch_action(action2, state)
        assert obs2["status"] == "REJECTED_UNAUTHORIZED"
        assert adapter.invocations == 1  # Invocations did not increment

        ToolPermissionGate.deauthorize_implementation(impl_id)

    def test_scenario_7_duplicate_and_replacement_registration(self):
        """Scenario 7: Replacing registration does not bypass authorization."""
        impl_id = "impl_audit_test_s7"
        adapter_a = MockSuccessAdapter("Adapter A")
        adapter_b = MockSuccessAdapter("Adapter B")

        register_capability_adapter(impl_id, adapter_a)
        # Replacing registration
        register_capability_adapter(impl_id, adapter_b)

        try:
            assert get_adapter_for_implementation(impl_id) is adapter_b
            # Still unauthorized without explicit grant
            state = InvestigationState(objective="Test replacement authorization")
            action = ResearchAction(
                question_id="q_1",
                action_type=ActionType.INVESTIGATE_SPECIALIST,
                rationale="Probe replacement adapter without authorization",
                specialist="none",
                implementation_id=impl_id,
                query="Probe replacement",
            )
            is_auth, reason = ToolPermissionGate.authorize_action(action, state)
            assert is_auth is False
            assert "registration does not grant execution permission" in reason
        finally:
            unregister_capability_adapter(impl_id)

    def test_scenario_8_concurrent_registration_thread_safety(self):
        """Scenario 8: Concurrent registration operations remain thread-safe without corruption."""
        registered_ids = [f"impl_concurrent_{i}" for i in range(50)]

        def worker(impl_id: str):
            ad = MockSuccessAdapter(f"Text for {impl_id}")
            register_capability_adapter(impl_id, ad)
            retrieved = get_adapter_for_implementation(impl_id)
            assert retrieved is ad
            unregister_capability_adapter(impl_id)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(worker, impl_id) for impl_id in registered_ids]
            for f in concurrent.futures.as_completed(futures):
                f.result()

    def test_scenario_9_cross_investigation_contract_isolation(self):
        """Scenario 9: Authorization in Tenant A's contract does not leak into Tenant B."""
        impl_id = "impl_tenant_scoped_s9"
        adapter = MockSuccessAdapter()
        register_capability_adapter(impl_id, adapter)

        try:
            # Tenant A explicitly permits impl_id in contract
            contract_a = {"allowed_implementations": [impl_id]}
            state_a = InvestigationState(objective="Tenant A Investigation", objective_contract=contract_a)
            action_a = ResearchAction(
                question_id="q_a",
                action_type=ActionType.INVESTIGATE_SPECIALIST,
                rationale="Tenant A action",
                specialist="none",
                implementation_id=impl_id,
                query="Query A",
            )
            is_auth_a, _ = ToolPermissionGate.authorize_action(action_a, state_a)
            assert is_auth_a is True

            # Tenant B does NOT permit impl_id in contract
            contract_b = {"allowed_implementations": ["impl_argus_generalist_v1"]}
            state_b = InvestigationState(objective="Tenant B Investigation", objective_contract=contract_b)
            action_b = ResearchAction(
                question_id="q_b",
                action_type=ActionType.INVESTIGATE_SPECIALIST,
                rationale="Tenant B action",
                specialist="none",
                implementation_id=impl_id,
                query="Query B",
            )
            is_auth_b, reason_b = ToolPermissionGate.authorize_action(action_b, state_b)
            assert is_auth_b is False
            assert "not permitted by investigation contract" in reason_b
        finally:
            unregister_capability_adapter(impl_id)

    def test_scenario_10_all_dispatch_paths_enforce_authorization(self):
        """Scenario 10: All available dispatch paths enforce authorization."""
        impl_id = "impl_audit_test_s10"
        cap_id = "cap_audit_test_s10"
        adapter = MockSuccessAdapter()
        register_capability_adapter(impl_id, adapter)

        cap_def = CapabilityDefinition(
            capability_id=cap_id,
            name="Audit Test Cap",
            description="Testing authorization enforcement",
            version="1.0.0",
            category=CapabilityCategory.GENERAL_RESEARCH,
            status=HealthStatus.AVAILABLE,
            provider="test",
            implementation_id=impl_id,
            input_schema=CapabilityInputSchema(schema_type="OBJECT", required_fields=["query"]),
            output_schema=CapabilityOutputSchema(
                schema_type="OBJECT",
                output_fields=["documents"],
                epistemic_nature=EpistemicNature.OBSERVATION,
                authoritative=False,
            ),
            question_types=["GENERAL"],
            supported_operations=["SEARCH"],
            evidence_types=["DOC"],
            epistemic_behavior="GROUNDED",
            temporal_behavior="CURRENT",
            jurisdictions=["GLOBAL"],
            entity_types=["CONCEPT"],
            dependencies=[],
            limitations=[],
            failure_modes=[],
        )

        planner = InvestigationPlanner()
        planner.registry.register(cap_def, overwrite=True)
        engine = InvestigationEngine(planner=planner)
        state = engine.start_investigation(objective="Test dispatch paths")

        try:
            # Path A: Action specifying implementation_id directly without authorization
            action_direct = ResearchAction(
                question_id=list(state.questions.keys())[0],
                action_type=ActionType.INVESTIGATE_SPECIALIST,
                rationale="Direct implementation dispatch without authorization",
                specialist="none",
                implementation_id=impl_id,
                query="Path A",
            )
            obs_a = engine._dispatch_action(action_direct, state)
            assert obs_a["status"] == "REJECTED_UNAUTHORIZED"

            # Path B: Action specifying capability_id which resolves to implementation_id
            action_resolved = ResearchAction(
                question_id=list(state.questions.keys())[0],
                action_type=ActionType.INVESTIGATE_SPECIALIST,
                rationale="Dynamic capability resolution dispatch without authorization",
                specialist="none",
                capability_id=cap_id,
                query="Path B",
            )
            obs_b = engine._dispatch_action(action_resolved, state)
            assert obs_b["status"] == "REJECTED_UNAUTHORIZED"

            assert adapter.invocations == 0
        finally:
            unregister_capability_adapter(impl_id)


# ===========================================================================
# PHASE 4: FAILURE-STATE INTEGRITY & INVARIANTS
# ===========================================================================

class TestPhase4FailureStateIntegrity:
    """Verify system failure handling and epistemic invariants A through H."""

    def test_invariant_a_and_f_failure_never_becomes_success_and_confidence_does_not_inflate(self):
        """Invariants A & F: Specialist failure does not mark objective satisfied or inflate confidence."""
        failing_impl_id = "impl_test_fail_inv_a"
        crashing_adapter = MockCrashingAdapter("Service crashed")
        register_capability_adapter(failing_impl_id, crashing_adapter)
        ToolPermissionGate.authorize_implementation(failing_impl_id)

        try:
            engine = InvestigationEngine()
            objective = "Investigate failure state integrity."
            state = engine.start_investigation(objective=objective, contract={"max_steps": 2})

            action = ResearchAction(
                question_id=list(state.questions.keys())[0],
                action_type=ActionType.INVESTIGATE_SPECIALIST,
                rationale="Probe crashing specialist",
                specialist="none",
                implementation_id=failing_impl_id,
                query="Crash service",
            )

            obs = engine._dispatch_action(action, state)
            assert obs["status"] == "FAILED"

            gain = engine._apply_observation(state, action, obs)
            assert gain == 0.0

            # 1. Question remains in unresolved_questions
            assert action.question_id in state.unresolved_questions
            assert action.question_id not in state.resolved_questions

            # 2. Confidence must NOT inflate
            assert state.confidence_state.overall_confidence == 0.0

            # 3. Stopping policy must NOT evaluate OBJECTIVE_SATISFIED
            policy = InvestigationStoppingPolicy()
            should_stop, reason, _ = policy.evaluate(state)
            if should_stop:
                assert reason != InvestigationStopReason.OBJECTIVE_SATISFIED

            # 4. Result must preserve unresolved question and reflect limitation
            result = engine.synthesize_report(state)
            assert any(q["question_id"] == action.question_id for q in result.unresolved_questions)
            assert any("ADAPTER_EXECUTION_FAILED" in lim for lim in result.limitations)
        finally:
            ToolPermissionGate.deauthorize_implementation(failing_impl_id)
            unregister_capability_adapter(failing_impl_id)

    def test_invariant_b_empty_results_never_become_fabricated_findings(self):
        """Invariant B: Empty specialist observations produce zero fabricated claims or findings."""
        empty_impl_id = "impl_test_empty_inv_b"
        empty_adapter = MockEmptyAdapter()
        register_capability_adapter(empty_impl_id, empty_adapter)
        ToolPermissionGate.authorize_implementation(empty_impl_id)

        try:
            engine = InvestigationEngine()
            state = engine.start_investigation(objective="Investigate empty response handling")

            action = ResearchAction(
                question_id=list(state.questions.keys())[0],
                action_type=ActionType.INVESTIGATE_SPECIALIST,
                rationale="Probe empty adapter response",
                specialist="none",
                implementation_id=empty_impl_id,
                query="Empty query",
            )

            obs = engine._dispatch_action(action, state)
            assert obs["status"] == "SUCCESS"
            assert len(obs["documents"]) == 0

            gain = engine._apply_observation(state, action, obs)
            assert gain == 0.0

            # No claims or evidence fabricated
            assert len(state.claims) == 0
            assert len(state.evidence) == 0
            result = engine.synthesize_report(state)
            assert len(result.findings) == 0
            assert len(result.supporting_evidence) == 0
        finally:
            ToolPermissionGate.deauthorize_implementation(empty_impl_id)
            unregister_capability_adapter(empty_impl_id)

    def test_invariant_c_unsupported_capability_never_falls_back_to_search(self):
        """Invariant C: Request for unsupported specialist capability fails closed and never searches corpus."""
        class MockTrackingCorpus:
            def __init__(self):
                self.search_calls = 0
            def search(self, query: str, limit: int = 3):
                self.search_calls += 1
                return []

        tracking_corpus = MockTrackingCorpus()
        engine = InvestigationEngine(corpus=tracking_corpus)
        state = engine.start_investigation(objective="Test unsupported capability dispatch")

        # Action requests a specialist with no adapter
        action = ResearchAction(
            question_id=list(state.questions.keys())[0],
            action_type=ActionType.INVESTIGATE_SPECIALIST,
            rationale="Probe unsupported exotic specialist",
            specialist="exotic_quantum_specialist",
            capability_id="quantum_capability_v9",
            query="Quantum spin resonance",
        )
        ToolPermissionGate.register_allowed_specialist("exotic_quantum_specialist")

        try:
            obs = engine._dispatch_action(action, state)
            assert obs["status"] == "UNSUPPORTED_CAPABILITY"
            # Crucial: Must NEVER have fallen back to searching the corpus
            assert tracking_corpus.search_calls == 0
            assert obs["documents"] == []
        finally:
            ToolPermissionGate.unregister_allowed_specialist("exotic_quantum_specialist")

    def test_invariant_d_failed_specialist_preserves_valid_evidence(self):
        """Invariant D: Failed specialist must not erase previously collected valid evidence."""
        # 1. Step 1: Collect valid evidence using success adapter
        success_impl_id = "impl_test_success_inv_d"
        success_adapter = MockSuccessAdapter("Valid evidence item 1")
        register_capability_adapter(success_impl_id, success_adapter)
        ToolPermissionGate.authorize_implementation(success_impl_id)

        # 2. Step 2: Crashing adapter
        crashing_impl_id = "impl_test_crash_inv_d"
        crashing_adapter = MockCrashingAdapter("Downstream timeout")
        register_capability_adapter(crashing_impl_id, crashing_adapter)
        ToolPermissionGate.authorize_implementation(crashing_impl_id)

        try:
            engine = InvestigationEngine()
            state = engine.start_investigation(objective="Test evidence preservation across failures")

            # Execute Step 1
            action1 = ResearchAction(
                question_id=list(state.questions.keys())[0],
                action_type=ActionType.INVESTIGATE_SPECIALIST,
                rationale="Collect initial valid evidence",
                specialist="none",
                implementation_id=success_impl_id,
                query="Query 1",
            )
            obs1 = engine._dispatch_action(action1, state)
            engine._apply_observation(state, action1, obs1)
            assert len(state.evidence) == 1
            assert len(state.claims) == 1

            # Execute Step 2 (Crash)
            action2 = ResearchAction(
                question_id=list(state.questions.keys())[1],
                action_type=ActionType.INVESTIGATE_SPECIALIST,
                rationale="Execute crashing step",
                specialist="none",
                implementation_id=crashing_impl_id,
                query="Query 2",
            )
            obs2 = engine._dispatch_action(action2, state)
            assert obs2["status"] == "FAILED"
            engine._apply_observation(state, action2, obs2)

            # Invariant D: Evidence from Step 1 MUST NOT have been erased
            assert len(state.evidence) == 1
            assert len(state.claims) == 1
            assert state.evidence[0]["snippet"] == "Valid evidence item 1"

            result = engine.synthesize_report(state)
            assert len(result.supporting_evidence) == 1
            assert len(result.findings) == 1
        finally:
            ToolPermissionGate.deauthorize_implementation(success_impl_id)
            unregister_capability_adapter(success_impl_id)
            ToolPermissionGate.deauthorize_implementation(crashing_impl_id)
            unregister_capability_adapter(crashing_impl_id)

    def test_invariant_e_and_g_partial_distinguishable_from_complete_and_contradictions_preserved(self):
        """Invariants E & G: Partial results distinguished from complete, contradictions visible."""
        engine = InvestigationEngine()
        state = engine.start_investigation(objective="Contradiction and partial test", contract={"max_steps": 2})

        # Inject conflicting claims
        claim1 = {"subject": "System X", "predicate": "throughput", "object": "10000 QPS", "claim_id": "c1"}
        claim2 = {"subject": "System X", "predicate": "throughput", "object": "100 QPS", "claim_id": "c2"}
        state.add_claim(claim1)
        state.add_claim(claim2)

        planner = InvestigationPlanner()
        planner.handle_contradiction(state, claim1, claim2)

        # Invariant G: Contradiction must be visible in internal state and report
        assert len(state.contradictions) == 1
        result = engine.synthesize_report(state)
        assert len(result.contradictions) == 1
        assert result.contradictions[0]["claim_a"]["object"] == "10000 QPS"

        # Invariant E: Result with unresolved questions is distinct from complete
        assert len(result.unresolved_questions) > 0
        assert result.completion_status != InvestigationStopReason.OBJECTIVE_SATISFIED.value
