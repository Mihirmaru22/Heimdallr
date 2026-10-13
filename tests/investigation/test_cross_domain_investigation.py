"""Cross-Domain Investigation Test Suite (Phase F Validation).

Deterministic test suite demonstrating that the generalized Heimdallr V3 orchestrator
can represent, plan, and execute materially different investigations across unfamiliar
domains while preserving deterministic security gates, evidence integrity, and bounded execution.

Tests:
- TEST 1: Technical Investigation (Vector Databases)
- TEST 2: Historical Investigation (Chronology, participants, consensus vs dispute)
- TEST 3: Organization Investigation (Public products, leadership, partnerships, strategy)
- TEST 4: Scientific or Policy Investigation (Competing explanations, uncertainties)
- TEST 5: Unsupported Domain or Capability (Explicit limitation, no fabricated results)
- TEST 6: Planner Failure (Malformed plan rejection)
- TEST 7: Specialist Failure (Timeout/exception recovery, consistent state)
- TEST 8: Budget Exhaustion (Strict termination, unresolved gaps reported)
- TEST 9: Security Boundary (Unauthorized capability/implementation rejected before invocation)
"""

from __future__ import annotations

import pytest
from typing import Any

from argus.capability_registry.adapters import (
    BaseCapabilityAdapter,
    register_capability_adapter,
    unregister_capability_adapter,
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
from argus.investigation.stopping import (
    InvestigationStopReason,
    InvestigationStoppingPolicy,
)


# ---------------------------------------------------------------------------
# Deterministic Test Fixtures & Fake Specialists
# ---------------------------------------------------------------------------

class DeterministicTechnicalAdapter(BaseCapabilityAdapter):
    """Deterministic specialist for software and technical benchmarks."""

    def execute(self, inputs: dict[str, Any], corpus: Any = None) -> dict[str, Any]:
        q = inputs.get("query", "").lower()
        docs = []
        if "filtering" in q:
            docs.append({
                "doc_id": "doc_tech_filter_01",
                "title": "Vector DB Filtering Architecture Benchmark",
                "url": "https://tech-bench.org/vector-filtering-eval",
                "text": "Qdrant employs payload-based filtering indexes using HNSW-graph traversals with pre-filtering support. Milvus utilizes segment-level bitset filtering with scalar index integration.",
                "source_type": "technical_benchmark",
            })
        if "licensing" in q:
            docs.append({
                "doc_id": "doc_tech_lic_01",
                "title": "Open Source Licensing Matrix",
                "url": "https://oss-licenses.org/vector-dbs",
                "text": "Qdrant is licensed under Apache-2.0. Milvus core is licensed under Apache-2.0 with separate commercial enterprise offerings.",
                "source_type": "repository_license",
            })
        if "operational" in q or "complexity" in q:
            docs.append({
                "doc_id": "doc_tech_ops_01",
                "title": "Operational Overhead Evaluation",
                "url": "https://ops-bench.io/vector-complexity",
                "text": "Qdrant operates as a single Rust binary with minimal operational dependencies. Milvus distributed mode depends on etcd, Pulsar, and MinIO object storage.",
                "source_type": "architecture_review",
            })
        if "performance" in q:
            docs.append({
                "doc_id": "doc_tech_perf_01",
                "title": "Throughput and Latency Measurements",
                "url": "https://benchmarks.io/vector-perf-2026",
                "text": "Qdrant achieved 4200 QPS with p99 latency of 12ms. Milvus cluster achieved 5100 QPS with p99 latency of 15ms under high-dimensional embedding loads.",
                "source_type": "empirical_benchmark",
            })

        if not docs:
            docs.append({
                "doc_id": "doc_tech_general",
                "title": "Vector Database Technical Overview",
                "url": "https://tech-bench.org/overview",
                "text": "General comparison of open-source vector database architectures and capabilities.",
                "source_type": "technical_report",
            })

        return {
            "status": "SUCCESS",
            "documents": docs,
            "entities": ["Qdrant", "Milvus"],
            "claims": [
                {"subject": "Qdrant", "predicate": "license", "object": "Apache-2.0", "status": "SUPPORTED"},
                {"subject": "Milvus", "predicate": "license", "object": "Apache-2.0", "status": "SUPPORTED"},
            ],
        }


class DeterministicHistoricalCorpus:
    """Deterministic corpus for historical decisions and event sequencing."""

    def search(self, query: str, limit: int = 3) -> list[Any]:
        class HistDoc:
            def __init__(self, doc_id: str, title: str, url: str, text: str, source_type: str):
                self.doc_id = doc_id
                self.title = title
                self.url = url
                self.text_content = text
                self.source_type = source_type

        q_lower = query.lower()
        if "participant" in q_lower or "actor" in q_lower:
            return [
                HistDoc(
                    "doc_hist_01",
                    "Apollo Program Directive 1961 Transcripts",
                    "https://history.nasa.gov/apollo-directive",
                    "President John F. Kennedy formulated the national objective in May 1961. Key participants included NASA Administrator James Webb, Deputy Associate Administrator George Low, and lead rocket engineer Wernher von Braun.",
                    "archival_transcript",
                )
            ]
        if "sequence" in q_lower or "chronological" in q_lower or "decision" in q_lower:
            return [
                HistDoc(
                    "doc_hist_02",
                    "Chronology of the Lunar Orbit Rendezvous Decision",
                    "https://history.nasa.gov/lor-decision-chronology",
                    "In 1961, Direct Ascent was initially preferred. In early 1962, John Houbolt advocated Lunar Orbit Rendezvous (LOR). The formal decision selecting LOR was ratified on July 11, 1962.",
                    "institutional_chronology",
                )
            ]
        return [
            HistDoc(
                "doc_hist_03",
                "Historical Consensus and Debated Interpretations of Apollo",
                "https://history.nasa.gov/consensus-vs-debate",
                "Consensus facts: The Saturn V rocket and Apollo spacecraft successfully landed humans on the Moon on July 20, 1969. Disputed interpretations: Scholarly disagreement persists regarding whether geopolitical competition vs scientific priority was the decisive factor.",
                "scholarly_analysis",
            )
        ]

    def get_discoverable_entities(self) -> list[str]:
        return ["Apollo 11", "James Webb", "George Low", "John Houbolt", "Wernher von Braun"]


class DeterministicFailingAdapter(BaseCapabilityAdapter):
    """Adapter that deterministically raises runtime exceptions to test resilience."""

    def execute(self, inputs: dict[str, Any], corpus: Any = None) -> dict[str, Any]:
        raise TimeoutError("Specialist worker timed out after 30.0s")


# ---------------------------------------------------------------------------
# TEST 1: Technical Investigation
# ---------------------------------------------------------------------------

def test_1_technical_investigation():
    """Verify that the orchestrator decomposes and executes a technical vector database comparison."""
    impl_id = "impl_test_technical_specialist_v1"
    register_capability_adapter(impl_id, DeterministicTechnicalAdapter())
    ToolPermissionGate.register_allowed_specialist("technical")

    planner = InvestigationPlanner()
    cap_def = CapabilityDefinition(
        capability_id="technical_software_benchmark",
        name="Technical Software Specialist",
        description="Software architecture, vector database benchmarks, and licensing intelligence.",
        version="1.0.0",
        category=CapabilityCategory.GENERAL_RESEARCH,
        status=HealthStatus.AVAILABLE,
        provider="technical_team",
        implementation_id=impl_id,
        input_schema=CapabilityInputSchema(schema_type="OBJECT", required_fields=["query"]),
        output_schema=CapabilityOutputSchema(
            schema_type="OBJECT",
            output_fields=["documents"],
            epistemic_nature=EpistemicNature.OBSERVATION,
            authoritative=False,
        ),
        question_types=["FIND_PUBLIC_INFORMATION", "ENTITY_DISCOVERY", "GENERAL_INQUIRY"],
        supported_operations=["SEARCH_BENCHMARKS"],
        evidence_types=["BENCHMARK_REPORT"],
        epistemic_behavior="UNINTERPRETED_OBSERVATIONS_GROUNDED_IN_SOURCES",
        temporal_behavior="SOURCE_TIMESTAMP_AWARE",
        jurisdictions=["GLOBAL"],
        entity_types=["TECHNICAL_SYSTEM"],
        dependencies=[],
        limitations=[],
        failure_modes=[],
    )
    planner.registry.register(cap_def, overwrite=True)

    try:
        objective = "Compare two open-source vector databases on filtering capabilities, operational complexity, licensing, and performance evidence."
        contract = {
            "target_entities": ["Qdrant", "Milvus"],
            "domain_hint": "technical",
            "max_steps": 4,
            "allowed_specialists": ["technical", "none"],
            "allowed_capabilities": ["technical_software_benchmark", "general_web_research"],
            "allowed_implementations": [impl_id, "impl_argus_generalist_v1"],
        }

        engine = InvestigationEngine(planner=planner)
        state = engine.start_investigation(objective=objective, contract=contract)

        # 1. Verify Domain and Entity Representation
        assert "Qdrant" in state.entities
        assert "Milvus" in state.entities
        assert state.entities["Qdrant"]["type"] == "TECHNICAL_SYSTEM"

        # 2. Verify Question Topology
        q_texts = [q["question_text"].lower() for q in state.questions.values()]
        assert any("filtering capabilities" in t for t in q_texts)
        assert any("operational complexity" in t for t in q_texts)
        assert any("license" in t for t in q_texts)
        assert any("performance evidence" in t for t in q_texts)

        # 3. Execute step using registered technical capability
        state, is_finished = engine.execute_step(state)

        # 4. Synthesize report and check domain-agnostic result
        result = engine.synthesize_report(state)
        assert isinstance(result, InvestigationResult)
        assert result.objective == objective
        assert "Qdrant" in result.research_scope["target_entities"]
        assert len(result.findings) > 0
        assert any(f.get("predicate") == "license" for f in result.findings)
        assert len(result.source_references) > 0

    finally:
        unregister_capability_adapter(impl_id)
        ToolPermissionGate.unregister_allowed_specialist("technical")


# ---------------------------------------------------------------------------
# TEST 2: Historical Investigation
# ---------------------------------------------------------------------------

def test_2_historical_investigation():
    """Verify historical investigation does not force corporate fields or entity models."""
    corpus = DeterministicHistoricalCorpus()
    planner = InvestigationPlanner()
    engine = InvestigationEngine(planner=planner, corpus=corpus)

    objective = "Investigate the sequence of events leading to a specified historical decision, identify the major participants, and distinguish established facts from disputed interpretations."
    contract = {
        "target_entities": ["Apollo 11 Decision"],
        "domain_hint": "historical",
        "max_steps": 4,
    }

    state = engine.start_investigation(objective=objective, contract=contract)

    # 1. Verify entity type is historical, not corporate
    assert state.entities["Apollo 11 Decision"]["type"] == "HISTORICAL_SUBJECT"

    # 2. Verify questions focus on chronology, actors, consensus vs dispute
    q_texts = [q["question_text"].lower() for q in state.questions.values()]
    assert any("chronological sequence of events" in t for t in q_texts)
    assert any("key historical participants" in t for t in q_texts)
    assert any("factual consensus" in t or "disputed" in t for t in q_texts)

    # 3. Execute 2 steps using general search over historical corpus
    for _ in range(2):
        if not state.stop_state.is_stopped:
            state, _ = engine.execute_step(state)

    # 4. Verify no corporate fields are required
    assert len(state.evidence) > 0
    report = engine.synthesize_report(state)
    assert report.objective == objective
    assert len(report.source_references) > 0
    assert "https://history.nasa.gov" in report.source_references[0]


# ---------------------------------------------------------------------------
# TEST 3: Organization Investigation
# ---------------------------------------------------------------------------

def test_3_organization_investigation():
    """Verify unfamiliar organization investigation is planned with general capabilities."""
    planner = InvestigationPlanner()
    engine = InvestigationEngine(planner=planner)

    objective = "Investigate an unfamiliar organization's public products, leadership, partnerships, and documented strategic changes."
    contract = {
        "target_entities": ["Open Governance Foundation"],
        "domain_hint": "organization",
        "max_steps": 3,
    }

    state = engine.start_investigation(objective=objective, contract=contract)

    # 1. Verify organization entity typing
    assert state.entities["Open Governance Foundation"]["type"] == "ORGANIZATION"

    # 2. Verify questions cover products, leadership, partnerships, and strategy
    q_texts = [q["question_text"].lower() for q in state.questions.values()]
    assert any("public products, programs" in t for t in q_texts)
    assert any("key executive leaders" in t or "governing board" in t for t in q_texts)
    assert any("strategic partnerships" in t for t in q_texts)
    assert any("documented strategic changes" in t for t in q_texts)

    # 3. Verify information gaps are appropriate
    gap_attrs = [g.target_attribute for g in state.information_gaps]
    assert "products_and_programs" in gap_attrs


# ---------------------------------------------------------------------------
# TEST 4: Scientific or Policy Investigation
# ---------------------------------------------------------------------------

def test_4_scientific_policy_investigation():
    """Verify scientific/policy investigation represents competing explanations and uncertainties."""
    planner = InvestigationPlanner()
    engine = InvestigationEngine(planner=planner)

    objective = "Compare competing explanations for a scientific or public-policy question and identify the strongest available evidence and unresolved uncertainties."
    contract = {
        "target_entities": ["Urban Heat Island Mitigation"],
        "domain_hint": "scientific_policy",
        "max_steps": 3,
    }

    state = engine.start_investigation(objective=objective, contract=contract)

    # 1. Verify scientific entity typing
    assert state.entities["Urban Heat Island Mitigation"]["type"] == "SCIENTIFIC_TOPIC"

    # 2. Verify questions address competing explanations, empirical evidence, and uncertainties
    q_texts = [q["question_text"].lower() for q in state.questions.values()]
    assert any("competing scientific or policy explanations" in t for t in q_texts)
    assert any("empirical evidence, data quality" in t for t in q_texts)
    assert any("unresolved uncertainties" in t for t in q_texts)

    # 3. Verify contradiction/uncertainty handling can ingest conflicting claims
    claim_a = {"subject": "Albedo Strategy", "predicate": "cooling_effect", "object": "1.5C reduction", "claim_id": "c1"}
    claim_b = {"subject": "Albedo Strategy", "predicate": "cooling_effect", "object": "Negligible reduction", "claim_id": "c2"}
    contra_q = planner.handle_contradiction(state, claim_a, claim_b)

    assert len(state.contradictions) == 1
    assert "c1" == state.contradictions[0]["claim_a"]["claim_id"]
    assert contra_q.question_type == QuestionType.CONTRADICTION_RESOLUTION


# ---------------------------------------------------------------------------
# TEST 5: Unsupported Domain or Capability
# ---------------------------------------------------------------------------

def test_5_unsupported_capability_handling():
    """Verify request for unsupported capability returns explicit limitation and never fabricates results."""
    planner = InvestigationPlanner()
    engine = InvestigationEngine(planner=planner)

    # Register specialist in permission whitelist so gate permits dispatch,
    # but do NOT register implementation in CapabilityRegistry or adapter map
    ToolPermissionGate.register_allowed_specialist("quantum_spectroscopy")

    try:
        objective = "Perform quantum cryogenic materials spectroscopy under ultra-high vacuum."
        contract = {
            "target_entities": ["Superconducting Film X"],
            "allowed_specialists": ["quantum_spectroscopy", "none"],
            "max_steps": 2,
        }

        state = engine.start_investigation(objective=objective, contract=contract)

        # Plan action requiring unsupported capability
        action = ResearchAction(
            question_id=list(state.questions.keys())[0],
            action_type=ActionType.INVESTIGATE_SPECIALIST,
            rationale="Probe unsupported capability execution",
            specialist="quantum_spectroscopy",
            capability_id="cryogenic_spectroscopy_v1",
            query="Analyze microwave absorption resonance",
            target_entities=["Superconducting Film X"],
        )

        obs = engine._dispatch_action(action, state)

        # 1. Must return explicit status without fabricating documents
        assert obs["status"] == "UNSUPPORTED_CAPABILITY"
        assert obs["documents"] == []
        assert "unsupported" in obs["error"].lower()

        # 2. Action must be marked FAILED
        assert action.status == "FAILED"

        # 3. Must record audit entry
        audits = [a.action_type for a in state.audit_trail]
        assert "UNSUPPORTED_CAPABILITY_REQUESTED" in audits

        # 4. Explicit information gap recorded
        assert any(g.target_attribute == "unsupported_capability" for g in state.information_gaps)

        # 5. Synthesized result explicitly notes limitation
        report = engine.synthesize_report(state)
        assert any("UNSUPPORTED_CAPABILITY_REQUESTED" in lim for lim in report.limitations)

    finally:
        ToolPermissionGate.unregister_allowed_specialist("quantum_spectroscopy")


# ---------------------------------------------------------------------------
# TEST 6: Planner Failure (Malformed Plan Rejection)
# ---------------------------------------------------------------------------

def test_6_planner_failure_rejection():
    """Verify planner safely rejects malformed objectives and invalid plan schemas."""
    planner = InvestigationPlanner()

    # Case A: Empty or whitespace objective
    with pytest.raises(ValueError, match="Investigation objective must be a non-empty string"):
        planner.initialize_investigation(objective="   ")

    # Case B: Non-dictionary contract
    with pytest.raises(ValueError, match="Objective contract must be a dictionary"):
        planner.initialize_investigation(objective="Valid Objective", objective_contract="invalid_string")  # type: ignore

    # Case C: Invalid max_steps
    with pytest.raises(ValueError, match="Contract max_steps must be a positive integer"):
        planner.initialize_investigation(objective="Valid Objective", objective_contract={"max_steps": -5})

    # Case D: Malformed custom questions list (dict missing question_text)
    malformed_questions = [{"invalid_key": "No text"}]
    with pytest.raises(ValueError, match="missing question_text"):
        planner.initialize_investigation(
            objective="Valid Objective",
            objective_contract={"initial_questions": malformed_questions},
        )


# ---------------------------------------------------------------------------
# TEST 7: Specialist Failure (Graceful Degradation)
# ---------------------------------------------------------------------------

def test_7_specialist_failure_handling():
    """Verify specialist runtime exception preserves state consistency and marks failure."""
    failing_impl_id = "impl_test_failing_specialist_v1"
    register_capability_adapter(failing_impl_id, DeterministicFailingAdapter())
    ToolPermissionGate.register_allowed_specialist("failing_worker")
    ToolPermissionGate.authorize_implementation(failing_impl_id)

    try:
        planner = InvestigationPlanner()
        engine = InvestigationEngine(planner=planner)

        objective = "Test graceful specialist failure recovery."
        state = engine.start_investigation(objective=objective, contract={"max_steps": 2})

        action = ResearchAction(
            question_id=list(state.questions.keys())[0],
            action_type=ActionType.INVESTIGATE_SPECIALIST,
            rationale="Probe failing specialist",
            specialist="failing_worker",
            implementation_id=failing_impl_id,
            query="Trigger failure",
        )

        obs = engine._dispatch_action(action, state)

        # 1. Observation status must be FAILED with error
        assert obs["status"] == "FAILED"
        assert "timed out" in obs["error"]

        # 2. Action marked FAILED
        assert action.status == "FAILED"

        # 3. State integrity preserved
        assert len(state.audit_trail) > 0
        assert any(a.action_type == "ADAPTER_EXECUTION_FAILED" for a in state.audit_trail)

        # 4. Applying observation updates target question without crashing
        gain = engine._apply_observation(state, action, obs)
        assert gain == 0.0

        target_q = state.questions[action.question_id]
        assert target_q["status"] == QuestionStatus.NOT_FOUND.value
        assert "FAILED" in target_q["resolution_reason"]

    finally:
        unregister_capability_adapter(failing_impl_id)
        ToolPermissionGate.deauthorize_implementation(failing_impl_id)
        ToolPermissionGate.unregister_allowed_specialist("failing_worker")


# ---------------------------------------------------------------------------
# TEST 8: Budget Exhaustion
# ---------------------------------------------------------------------------

def test_8_budget_exhaustion_termination():
    """Verify strict execution bounds: engine terminates when step budget is reached and records gaps."""
    class EmptyCorpus:
        def search(self, query: str, limit: int = 3):
            return []
        def get_discoverable_entities(self):
            return []

    stopping_policy = InvestigationStoppingPolicy(max_consecutive_zero_gains=10)
    planner = InvestigationPlanner()
    engine = InvestigationEngine(planner=planner, stopping_policy=stopping_policy, corpus=EmptyCorpus())

    objective = "Exhaust step budget on unfamiliar domain questions."
    contract = {
        "target_entities": ["Unrecorded Mystery Entity 99"],
        "max_steps": 2,
    }

    state = engine.run_to_completion(objective=objective, contract=contract, max_steps=2)

    # 1. Stopped state must be verified
    assert state.stop_state.is_stopped is True
    assert state.stop_state.budget_exhausted is True
    assert state.stop_state.stop_reason in [
        InvestigationStopReason.BUDGET_EXHAUSTED_WITH_CRITICAL_MISSING_FIELDS.value,
        InvestigationStopReason.BUDGET_EXHAUSTED_WITH_ACCEPTABLE_COVERAGE.value,
    ]
    assert state.research_budget["steps_taken"] <= 2

    # 2. Synthesized report must document budget limitation
    report = engine.synthesize_report(state)
    assert any("budget limit (2 steps)" in lim for lim in report.limitations)
    assert len(report.unresolved_questions) > 0


# ---------------------------------------------------------------------------
# TEST 9: Security Boundary Enforcement
# ---------------------------------------------------------------------------

def test_9_security_boundary_enforcement():
    """Verify unauthorized capability, specialist, or injection payload is rejected at boundary."""
    planner = InvestigationPlanner()
    engine = InvestigationEngine(planner=planner)

    objective = "Verify application-level security boundaries."
    contract = {
        "allowed_specialists": ["corporate"],
        "max_steps": 3,
    }
    state = engine.start_investigation(objective=objective, contract=contract)

    # Case A: Unauthorized specialist requested
    unauth_action = ResearchAction(
        question_id=list(state.questions.keys())[0],
        action_type=ActionType.INVESTIGATE_SPECIALIST,
        rationale="Probe unauthorized specialist tool",
        specialist="unauthorized_hacker_tool",
        query="Extract confidential data",
    )
    is_auth, reason = ToolPermissionGate.authorize_action(unauth_action, state)
    assert is_auth is False
    assert "Unauthorized specialist" in reason

    obs = engine._dispatch_action(unauth_action, state)
    assert obs["status"] == "REJECTED_UNAUTHORIZED"
    assert any(a.action_type == "SECURITY_POLICY_VIOLATION" for a in state.audit_trail)

    # Case B: Specialist outside contract whitelist
    contract_blocked_action = ResearchAction(
        question_id=list(state.questions.keys())[0],
        action_type=ActionType.INVESTIGATE_SPECIALIST,
        rationale="Probe contract-blocked specialist",
        specialist="infrastructure",  # Valid global specialist, but excluded by contract allowed_specialists=["corporate"]
        query="Probe DNS assets",
    )
    is_auth, reason = ToolPermissionGate.authorize_action(contract_blocked_action, state)
    assert is_auth is False
    assert "not permitted by investigation contract" in reason

    # Case C: Command injection / dangerous shell metacharacters in query
    injection_action = ResearchAction(
        question_id=list(state.questions.keys())[0],
        action_type=ActionType.SEARCH,
        rationale="Probe command injection pattern",
        specialist="none",
        query="search query; rm -rf /etc/passwd",
    )
    is_auth, reason = ToolPermissionGate.authorize_action(injection_action, state)
    assert is_auth is False
    assert "Adversarial or shell metacharacters detected" in reason
