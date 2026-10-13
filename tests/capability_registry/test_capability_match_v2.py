"""Unit & Integration tests for CAPABILITY_MATCH_V2 Benchmark Suite."""

import pytest

from argus.capability_registry.registry import CapabilityRegistry
from argus.capability_registry.defaults import get_default_capabilities
from argus.capability_registry.matcher import CapabilityMatcher
from argus.evals.capability_match_v2.fixtures.tasks import build_capability_match_v2_tasks
from argus.evals.capability_match_v2.leakage_audit import LeakageAuditorV2
from argus.evals.capability_match_v2.models import BenchmarkSplit, MatchCategoryV2
from argus.evals.capability_match_v2.runner import CapabilityMatchRunnerV2
from argus.evals.capability_match_v2.stability import StabilityHarnessV2
from argus.investigation.question import InvestigationQuestion, QuestionType


@pytest.fixture
def populated_registry() -> CapabilityRegistry:
    reg = CapabilityRegistry()
    for cap in get_default_capabilities():
        reg.register(cap, overwrite=True)
    return reg


@pytest.fixture
def matcher() -> CapabilityMatcher:
    return CapabilityMatcher()


def test_capability_match_v2_leakage_audit():
    """Verify that LeakageAuditorV2 reports PASS across all 6 isolation vectors."""
    auditor = LeakageAuditorV2()
    res = auditor.run_audit()
    assert res["overall_status"] == "PASS"
    for vec, data in res["vectors"].items():
        assert data["status"] == "PASS"


def test_capability_match_v2_minimum_sufficient_set(populated_registry: CapabilityRegistry, matcher: CapabilityMatcher):
    """Verify select_minimum_sufficient_set returns smallest sufficient set."""
    q_multi = InvestigationQuestion(
        question_text="Confirm registered parent entity of AeroSpace UK and map its primary cloud subdomain certificates.",
        question_type=QuestionType.INFRASTRUCTURE_ATTRIBUTION,
        required_evidence=[
            "Companies House statutory filing",
            "Certificate Transparency CT log SAN entry",
        ],
        related_entities=["AeroSpace UK Ltd"],
    )
    selected = matcher.select_minimum_sufficient_set(
        question=q_multi,
        capabilities=populated_registry.list(),
    )
    selected_caps = {c.capability_id for c in selected}
    assert selected_caps == {"corporate_registry_intelligence", "infrastructure_discovery"}
    assert len(selected) == 2


def test_capability_match_v2_false_specialist_trap(populated_registry: CapabilityRegistry, matcher: CapabilityMatcher):
    """Verify false specialist trap does not invoke superfluous infrastructure capability."""
    q_trap = InvestigationQuestion(
        question_text="A company outlines its critical infrastructure strategy in its annual statutory filing.",
        question_type=QuestionType.ENTITY_DISCOVERY,
        required_evidence=["SEC Form 10-K statutory annual report"],
        related_entities=["Apex Technologies"],
    )
    selected = matcher.select_minimum_sufficient_set(
        question=q_trap,
        capabilities=populated_registry.list(),
    )
    selected_caps = {c.capability_id for c in selected}
    assert "corporate_registry_intelligence" in selected_caps
    assert "infrastructure_discovery" not in selected_caps
    assert len(selected) == 1


def test_capability_match_v2_dev_split_execution():
    """Verify dev split tasks pass minimum-set accuracy with zero capability tax."""
    runner = CapabilityMatchRunnerV2()
    summary, results = runner.run_benchmark(split=BenchmarkSplit.DEV)
    assert summary.total_tasks >= 30
    assert summary.minimum_capability_set_accuracy >= 0.95
    assert summary.capability_tax_mean == 0.0
    assert summary.unnecessary_invocation_rate == 0.0


def test_capability_match_v2_stability():
    """Verify stability harness reports 0 variance across multiple iterations."""
    runner = CapabilityMatchRunnerV2()
    stability = StabilityHarnessV2()
    res = stability.run_stability_audit(runner=runner, iterations=3)
    assert res["verdict"] == "DETERMINISTIC_PASS"
    assert res["pass_rate_variance"] == 0.0
    assert res["task_level_agreement"] == 1.0
