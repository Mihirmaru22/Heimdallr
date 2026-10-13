"""Integration tests for Heimdallr V3.1 Capability Registry and Investigation Engine.

Verifies end-to-end integration across:
1. Identity question -> Identity capability
2. Infrastructure question -> Infrastructure capability
3. Corporate question -> Corporate capability
4. General question -> Argus (General Web Research)
5. Cross-specialist question -> Multiple capability candidates
6. Capability unavailable -> Alternate candidate / fallback
7. Two implementations -> Deterministic ranking & competition
8. Capability output -> InvestigationState mutation & audit
9. Registry restart -> Definitions preserved across serialization
10. Existing Investigation V1 benchmark -> No regression
"""

import tempfile
from pathlib import Path
import pytest

from argus.capability_registry.defaults import get_default_capabilities
from argus.capability_registry.matcher import CapabilityMatcher
from argus.capability_registry.models import HealthStatus
from argus.capability_registry.registry import CapabilityRegistry
from argus.investigation.benchmark.corpus import INVESTIGATION_CORPUS_REGISTRY
from argus.investigation.orchestrator import InvestigationEngine
from argus.investigation.planner import InvestigationPlanner
from argus.investigation.question import InvestigationQuestion, QuestionType


@pytest.fixture
def fresh_registry() -> CapabilityRegistry:
    reg = CapabilityRegistry()
    for cap in get_default_capabilities():
        reg.register(cap, overwrite=True)
    return reg


@pytest.fixture
def matcher() -> CapabilityMatcher:
    return CapabilityMatcher()


def test_1_identity_question_to_identity_capability(fresh_registry: CapabilityRegistry, matcher: CapabilityMatcher):
    """Test 1: Identity question routes to Identity capability."""
    q_ident = InvestigationQuestion(
        question_text="Identify GitHub handle 'alec-m-apex' developer persona and Keybase identity.",
        question_type=QuestionType.IDENTITY_CORRELATION,
        required_evidence=["GitHub profile commit activity", "Keybase identity proof"],
        related_entities=["alec-m-apex"],
    )
    candidates = matcher.match(q_ident, capabilities=fresh_registry.list())
    assert len(candidates) >= 1
    top = candidates[0]
    assert top.capability_id == "identity_resolution"
    assert top.match_score > 0.70
    assert "GitHub" in " ".join(top.matched_requirements) or len(top.matched_requirements) > 0


def test_2_infrastructure_question_to_infrastructure_capability(fresh_registry: CapabilityRegistry, matcher: CapabilityMatcher):
    """Test 2: Infrastructure question routes to Infrastructure capability."""
    q_infra = InvestigationQuestion(
        question_text="Discover all subdomains and TLS SAN entries for apex-telemetry.co.uk.",
        question_type=QuestionType.INFRASTRUCTURE_ATTRIBUTION,
        required_evidence=["Certificate Transparency CT log", "DNS zone records"],
        related_entities=["apex-telemetry.co.uk"],
    )
    candidates = matcher.match(q_infra, capabilities=fresh_registry.list())
    assert len(candidates) >= 1
    top = candidates[0]
    assert top.capability_id == "infrastructure_discovery"
    assert top.implementation_id == "impl_infrastructure_probe_specialist_v1"
    assert top.match_score > 0.70


def test_3_corporate_question_to_corporate_capability(fresh_registry: CapabilityRegistry, matcher: CapabilityMatcher):
    """Test 3: Corporate question routes to Corporate capability."""
    q_corp = InvestigationQuestion(
        question_text="Verify legal entity incorporation, company number, and active directors at Companies House.",
        question_type=QuestionType.OFFICER_TENURE,
        required_evidence=["Companies House statutory register", "Certificate of Incorporation"],
        related_entities=["Apex Technologies Europe Ltd"],
    )
    candidates = matcher.match(q_corp, capabilities=fresh_registry.list())
    assert len(candidates) >= 1
    top = candidates[0]
    assert top.capability_id == "corporate_registry_intelligence"
    assert top.implementation_id == "impl_corporate_registry_specialist_v1"
    assert top.match_score > 0.80


def test_4_general_question_to_argus(fresh_registry: CapabilityRegistry, matcher: CapabilityMatcher):
    """Test 4: General question routes to Argus general web research."""
    q_gen = InvestigationQuestion(
        question_text="What are general industry press statements and trade summaries about commercial satellite tech?",
        question_type=QuestionType.ENTITY_DISCOVERY,
        required_evidence=["General news articles", "Industry press release archives"],
        related_entities=["Apex Technologies Group"],
    )
    candidates = matcher.match(q_gen, capabilities=fresh_registry.list())
    assert len(candidates) >= 1
    top = candidates[0]
    assert top.capability_id == "general_web_research"
    assert top.implementation_id == "impl_argus_generalist_v1"


def test_5_cross_specialist_question_multiple_candidates(fresh_registry: CapabilityRegistry, matcher: CapabilityMatcher):
    """Test 5: Cross-specialist question yields multiple ranked capability candidates."""
    q_cross = InvestigationQuestion(
        question_text="Is the domain apex-telemetry.co.uk registered to the UK corporate entity and who is the technical contact?",
        question_type=QuestionType.INFRASTRUCTURE_ATTRIBUTION,
        required_evidence=[
            "Certificate Transparency log SAN entry",
            "Companies House corporate filing",
            "WHOIS or contact identity record",
        ],
        related_entities=["apex-telemetry.co.uk", "Apex Technologies Europe Ltd"],
    )
    candidates = matcher.match(q_cross, capabilities=fresh_registry.list(), max_candidates=5)
    cap_ids = {c.capability_id for c in candidates}
    # Multiple distinct capabilities matched
    assert len(cap_ids) >= 2
    assert "infrastructure_discovery" in cap_ids
    assert "corporate_registry_intelligence" in cap_ids or "identity_resolution" in cap_ids


def test_6_capability_unavailable_alternate_candidate(fresh_registry: CapabilityRegistry, matcher: CapabilityMatcher):
    """Test 6: When primary capability is UNAVAILABLE or DISABLED, alternate fallback candidate is returned."""
    fresh_registry.disable("corporate_registry_intelligence")

    q_corp = InvestigationQuestion(
        question_text="Check corporate registry for filings on Apex Technologies.",
        question_type=QuestionType.ENTITY_DISCOVERY,
        required_evidence=["SEC EDGAR corporate filing"],
        related_entities=["Apex Technologies Group Inc"],
    )
    candidates = matcher.match(q_corp, capabilities=fresh_registry.list(include_inactive=False))
    selected_caps = [c.capability_id for c in candidates]
    # Corporate capability must NOT be selected
    assert "corporate_registry_intelligence" not in selected_caps
    # Argus general web research serves as fallback
    assert "general_web_research" in selected_caps


def test_7_two_implementations_deterministic_ranking(fresh_registry: CapabilityRegistry, matcher: CapabilityMatcher):
    """Test 7: Two implementations of same capability are deterministically ranked."""
    q_ident = InvestigationQuestion(
        question_text="Resolve developer PGP key and cryptographic signing identity.",
        question_type=QuestionType.IDENTITY_CORRELATION,
        required_evidence=["Keybase cryptographic proof and PGP signature"],
        related_entities=["vkroll"],
    )
    candidates = matcher.match(q_ident, capabilities=fresh_registry.list())
    ident_candidates = [c for c in candidates if c.capability_id == "identity_resolution"]
    assert len(ident_candidates) == 2

    # Verify deterministic ordering: Challenger has higher benchmark F1 and PGP match
    assert ident_candidates[0].implementation_id == "impl_challenger_identity_specialist_v2"
    assert ident_candidates[1].implementation_id == "impl_identity_probe_specialist_v1"
    assert ident_candidates[0].match_score >= ident_candidates[1].match_score


def test_8_capability_output_to_investigation_state():
    """Test 8: Capability execution populates InvestigationState observations and specialist invocations."""
    planner = InvestigationPlanner()
    engine = InvestigationEngine(planner=planner, corpus=INVESTIGATION_CORPUS_REGISTRY)

    state = engine.run_to_completion(
        objective="Determine corporate officers and UK subsidiary for Apex Technologies Group.",
        contract={"target_entities": ["Apex Technologies Group"]},
        max_steps=4,
    )

    assert state.stop_state.is_stopped is True
    assert len(state.observations) > 0
    assert len(state.specialist_invocations) > 0

    # Verify capability telemetry in specialist invocations
    first_inv = state.specialist_invocations[0]
    assert "capability_id" in first_inv
    assert "implementation_id" in first_inv
    assert first_inv["capability_id"] in [
        "corporate_registry_intelligence",
        "infrastructure_discovery",
        "identity_resolution",
        "general_web_research",
    ]


def test_9_registry_restart_definitions_preserved():
    """Test 9: Registry serialization preserves definitions across instance restarts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store_path = Path(tmpdir) / "registry.json"
        reg1 = CapabilityRegistry(persistence_path=store_path)
        for cap in get_default_capabilities():
            reg1.register(cap, overwrite=True)

        assert store_path.exists()
        original_count = len(reg1.list())

        # Simulate fresh process restart loading from disk
        reg2 = CapabilityRegistry(persistence_path=store_path)
        assert len(reg2.list()) == original_count
        cap = reg2.get("identity_resolution", implementation_id="impl_challenger_identity_specialist_v2")
        assert cap is not None
        assert cap.version == "2.0.0"
        assert cap.performance_profile.f1 == 0.980


def test_10_investigation_v1_benchmark_regression():
    """Test 10: Run multi-specialist investigation workflow to verify no regression."""
    engine = InvestigationEngine(corpus=INVESTIGATION_CORPUS_REGISTRY)

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
    # Confirm discovered entities match expected ground truth
    assert "telemetry-cluster-01.apex-telemetry.co.uk" in state.entities
    assert "Rachel Thorne" in state.entities
    assert len(state.claims) > 0
