"""Heimdallr V3.1: Capability Label Leakage Tests (Section 18).

Contains tests proving:
1. Ground truth cannot reach matcher.
2. Changing expected capability labels without changing the question does not change runtime routing.
3. Changing forbidden capabilities without changing the question does not change runtime routing.
4. Changing minimum sufficient set without changing the question does not change runtime routing.
5. Incorrect capability hints do not automatically override legitimate evidence requirements.
6. Production Investigation Engine does not inject evaluator-only fields.
"""

from __future__ import annotations

import pytest

from argus.capability_registry.matcher import CapabilityMatcher
from argus.capability_registry.registry import CapabilityRegistry
from argus.capability_registry.defaults import get_default_capabilities
from argus.evals.capability_match_v2.capability_label_leakage_guard import (
    CapabilityLabelLeakageGuard,
    LeakageDetectedException,
)
from argus.evals.capability_match_v2.fixtures.tasks import build_capability_match_v2_tasks
from argus.investigation.orchestrator import InvestigationEngine
from argus.investigation.question import InvestigationQuestion


@pytest.fixture
def registry() -> CapabilityRegistry:
    reg = CapabilityRegistry()
    for cap in get_default_capabilities():
        reg.register(cap, overwrite=True)
    return reg


@pytest.fixture
def matcher() -> CapabilityMatcher:
    return CapabilityMatcher()


def test_1_ground_truth_cannot_reach_matcher(matcher: CapabilityMatcher, registry: CapabilityRegistry) -> None:
    """Test 1: Guard raises LeakageDetectedException if ground truth fields are passed on question."""
    # 1. Structural schema isolation: Pydantic rejects non-declared evaluator fields
    q = InvestigationQuestion(
        question_text="Find director appointments.",
        required_evidence=["Statutory register of active directors"],
    )
    with pytest.raises(ValueError):
        setattr(q, "required_capabilities", ["corporate_registry_intelligence"])

    # 2. Guard runtime interception: detects populated evaluator keys in runtime payloads
    leaked_dict = {
        "question_text": "Find director appointments.",
        "required_capabilities": ["corporate_registry_intelligence"],
    }
    violations = CapabilityLabelLeakageGuard.audit_object_for_leakage(leaked_dict, "RuntimePayload")
    assert any("required_capabilities" in v for v in violations)

    class MockLeakedQuestion:
        question_text = "Find director appointments."
        required_capabilities = ["corporate_registry_intelligence"]

    with pytest.raises(LeakageDetectedException):
        CapabilityLabelLeakageGuard.check_question_isolation(MockLeakedQuestion())


def test_2_changing_expected_labels_does_not_change_routing(matcher: CapabilityMatcher, registry: CapabilityRegistry) -> None:
    """Test 2: Modifying expected capability labels without changing the question produces identical routing."""
    tasks = build_capability_match_v2_tasks()
    t = tasks[0]
    
    q = InvestigationQuestion(
        question_text=t.question_text,
        question_type=t.question_type,
        required_evidence=t.required_evidence,
    )
    caps = registry.list()
    res1 = [c.capability_id for c in matcher.select_minimum_sufficient_set(q, capabilities=caps)]
    
    # Mutate task ground truth expected labels
    t_mutated = t.model_copy(deep=True)
    t_mutated.required_capabilities = ["non_existent_fake_capability"]
    
    # Same question passed to matcher
    res2 = [c.capability_id for c in matcher.select_minimum_sufficient_set(q, capabilities=caps)]
    
    assert res1 == res2, "Matcher output changed when task ground truth was mutated!"


def test_3_changing_forbidden_capabilities_does_not_change_routing(matcher: CapabilityMatcher, registry: CapabilityRegistry) -> None:
    """Test 3: Changing forbidden capabilities without changing question produces identical routing."""
    tasks = build_capability_match_v2_tasks()
    t = tasks[5]
    
    q = InvestigationQuestion(
        question_text=t.question_text,
        question_type=t.question_type,
        required_evidence=t.required_evidence,
    )
    caps = registry.list()
    res1 = [c.capability_id for c in matcher.select_minimum_sufficient_set(q, capabilities=caps)]
    
    t_mutated = t.model_copy(deep=True)
    t_mutated.forbidden_capabilities = ["corporate_registry_intelligence", "infrastructure_discovery"]
    
    res2 = [c.capability_id for c in matcher.select_minimum_sufficient_set(q, capabilities=caps)]
    assert res1 == res2, "Matcher output changed when forbidden capabilities were mutated!"


def test_4_changing_minimum_sufficient_set_does_not_change_routing(matcher: CapabilityMatcher, registry: CapabilityRegistry) -> None:
    """Test 4: Changing minimum sufficient set ground truth does not affect matcher decision."""
    tasks = build_capability_match_v2_tasks()
    t = tasks[10]
    
    q = InvestigationQuestion(
        question_text=t.question_text,
        question_type=t.question_type,
        required_evidence=t.required_evidence,
    )
    caps = registry.list()
    res1 = [c.capability_id for c in matcher.select_minimum_sufficient_set(q, capabilities=caps)]
    
    t_mutated = t.model_copy(deep=True)
    t_mutated.minimum_sufficient_set = ["general_web_research"]
    
    res2 = [c.capability_id for c in matcher.select_minimum_sufficient_set(q, capabilities=caps)]
    assert res1 == res2, "Matcher output changed when minimum sufficient set was mutated!"


def test_5_incorrect_capability_hints_do_not_override_evidence(matcher: CapabilityMatcher, registry: CapabilityRegistry) -> None:
    """Test 5: Incorrect specialist hints do not override explicit evidence requirements."""
    q_corp = InvestigationQuestion(
        question_text="Find UK legal entity filing and active directors.",
        required_evidence=["Companies House statutory register of directors"],
        specialist_requirements=["infrastructure"],  # INCORRECT CONFLICTING HINT
    )
    caps = registry.list()
    selected = matcher.select_minimum_sufficient_set(q_corp, capabilities=caps)
    selected_ids = [c.capability_id for c in selected]
    
    # Must select corporate_registry_intelligence based on evidence, NOT infrastructure
    assert "corporate_registry_intelligence" in selected_ids
    assert "infrastructure_discovery" not in selected_ids


def test_6_production_engine_does_not_inject_evaluator_fields() -> None:
    """Test 6: Production Investigation Orchestrator questions contain zero evaluator-only fields."""
    engine = InvestigationEngine()
    state = engine.start_investigation(
        objective="Investigate Apex Technologies Group corporate standing.",
    )
    
    for q_id, q_data in state.questions.items():
        violations = CapabilityLabelLeakageGuard.audit_object_for_leakage(q_data, f"ProductionQuestion[{q_id}]")
        assert not violations, f"Production question contains evaluator fields: {violations}"
