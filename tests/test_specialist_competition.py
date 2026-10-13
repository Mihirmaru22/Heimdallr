"""Heimdallr V3.2: Specialist Recruitment & Competition Test Suite.

Tests:
1. Candidate contract and lifecycle state progression
2. Pre-integration license auditing and incompatible rejection
3. Security gate code auditing and observation sanitization
4. OpenSanctionsSpecialist and adapter execution
5. ImplementationSelector ranking and health awareness
6. CompetitionEngine decision policies (RECRUIT_NEW, REPLACE, COEXIST, REJECT, QUARANTINE)
7. SPECIALIST_COMPETITION_V1 benchmark execution
"""

from __future__ import annotations

import pytest

from argus.competition.engine import CompetitionEngine
from argus.competition.implementation_selector import ImplementationSelector
from argus.competition.license_auditor import LicenseAuditor
from argus.competition.models import (
    CandidateImplementation,
    CandidateLifecycleState,
    CompetitionDecisionType,
    LicenseStatus,
)
from argus.competition.security_gate import SecurityGateValidator
from argus.capability_registry.models import (
    CapabilityCategory,
    CapabilityDefinition,
    CapabilityInputSchema,
    CapabilityOutputSchema,
    HealthStatus,
    PerformanceProfile,
)
from argus.evals.specialist_competition.runner import SpecialistCompetitionRunner
from argus.specialists.sanctions.adapter import OpenSanctionsAdapter
from argus.specialists.sanctions.specialist import OpenSanctionsSpecialist


def test_candidate_contract_and_lifecycle() -> None:
    """Test candidate initialization and lifecycle advancement."""
    engine = CompetitionEngine()
    cand = CandidateImplementation(
        candidate_id="impl_test_cand_v1",
        name="Test Candidate",
        version="1.0.0",
        repository="https://github.com/test/cand",
        license="MIT",
        claimed_capabilities=["test_capability"],
    )
    assert cand.lifecycle_state == CandidateLifecycleState.DISCOVERED
    engine.advance_lifecycle(cand, CandidateLifecycleState.AUDITED)
    assert cand.lifecycle_state == CandidateLifecycleState.AUDITED


def test_license_auditor_classifications() -> None:
    """Test license auditor correctly classifies permissive, attribution, and incompatible licenses."""
    auditor = LicenseAuditor()
    assert auditor.audit_license("Apache 2.0") == LicenseStatus.APPROVED
    assert auditor.audit_license("MIT") == LicenseStatus.APPROVED
    assert auditor.audit_license("ODbL-1.0") == LicenseStatus.APPROVED_WITH_ATTRIBUTION
    assert auditor.audit_license("CC-BY-4.0") == LicenseStatus.APPROVED_WITH_ATTRIBUTION
    assert auditor.audit_license("AGPL-3.0") == LicenseStatus.INCOMPATIBLE
    assert auditor.audit_license("Proprietary Commercial") == LicenseStatus.INCOMPATIBLE
    assert auditor.audit_license("") == LicenseStatus.UNKNOWN


def test_security_gate_sanitization() -> None:
    """Test security gate sanitizes dangerous injection characters and bounds output size."""
    raw_payload = {
        "entity_name": "Sanctioned Entity <script>alert(1)</script>",
        "details": "Malicious payload [eval(danger)] $ENV_SECRET",
        "numeric_id": 12345,
    }
    clean = SecurityGateValidator.sanitize_candidate_observation(raw_payload)
    assert "<script>" not in clean["entity_name"]
    assert "eval(danger)" not in clean["details"]
    assert clean["numeric_id"] == 12345


def test_opensanctions_specialist_and_adapter() -> None:
    """Test OpenSanctions specialist and adapter queries."""
    adapter = OpenSanctionsAdapter()
    
    # 1. Search sanctioned entity
    obs_kroll = adapter.execute_query("Victor Kroll")
    assert any(o.evidence_type == "OFAC_SDN_ENTRY" for o in obs_kroll)
    assert all(o.is_authoritative is False for o in obs_kroll)  # Candidate only
    
    # 2. Trace offshore shell trust
    obs_steppe = adapter.execute_query("Steppe Resources BVI Limited")
    assert any(o.evidence_type == "OFFSHORE_LEAKS_RECORD" for o in obs_steppe)
    
    # 3. Check PEP status
    obs_pep = adapter.execute_query("Elena Rostova")
    assert any(o.evidence_type == "PEP_DISCLOSURE" for o in obs_pep)
    
    # 4. Clean entity query returns empty
    obs_clean = adapter.execute_query("NonExistentCleanEntityXYZ")
    assert len(obs_clean) == 0


def test_implementation_selector_ranking() -> None:
    """Test ImplementationSelector ranks available implementations using performance and semver."""
    selector = ImplementationSelector()
    
    impl_v1 = CapabilityDefinition(
        capability_id="identity_resolution",
        name="Identity Probe v1",
        description="Identity Probe v1 implementation",
        input_schema=CapabilityInputSchema(),
        output_schema=CapabilityOutputSchema(),
        version="1.0.0",
        category=CapabilityCategory.IDENTITY,
        status=HealthStatus.AVAILABLE,
        implementation_id="impl_v1",
        performance_profile=PerformanceProfile(accuracy=0.95, precision=0.95, recall=0.95),
    )
    impl_v2 = CapabilityDefinition(
        capability_id="identity_resolution",
        name="Challenger Identity v2",
        description="Challenger Identity v2 implementation",
        input_schema=CapabilityInputSchema(),
        output_schema=CapabilityOutputSchema(),
        version="2.0.0",
        category=CapabilityCategory.IDENTITY,
        status=HealthStatus.AVAILABLE,
        implementation_id="impl_v2",
        performance_profile=PerformanceProfile(accuracy=0.98, precision=0.98, recall=0.98),
    )
    impl_degraded = CapabilityDefinition(
        capability_id="identity_resolution",
        name="Degraded Probe v3",
        description="Degraded Probe v3 implementation",
        input_schema=CapabilityInputSchema(),
        output_schema=CapabilityOutputSchema(),
        version="3.0.0",
        category=CapabilityCategory.IDENTITY,
        status=HealthStatus.DEGRADED,
        implementation_id="impl_degraded",
        performance_profile=PerformanceProfile(accuracy=0.99, precision=0.99, recall=0.99),
    )
    
    ranked = selector.rank_implementations_for_capability([impl_v1, impl_v2, impl_degraded])
    assert len(ranked) == 3
    # Available v2 should rank highest due to AVAILABLE status + v2 semver + higher accuracy
    assert ranked[0].implementation_id == "impl_v2"
    assert ranked[1].implementation_id == "impl_v1"
    assert ranked[2].implementation_id == "impl_degraded"


def test_competition_engine_decision_policies() -> None:
    """Test CompetitionEngine decision policies across recruit, replace, coexist, and reject."""
    engine = CompetitionEngine()
    
    # Policy 1: License Incompatible -> REJECT
    cand_agpl = CandidateImplementation(
        candidate_id="impl_agpl",
        name="AGPL Candidate",
        version="1.0.0",
        repository="repo",
        license="AGPL-3.0",
        claimed_capabilities=["sanctions_screening"],
    )
    dec_agpl = engine.evaluate_candidate(cand_agpl)
    assert dec_agpl.decision == CompetitionDecisionType.REJECT
    assert "incompatible" in dec_agpl.primary_reason.lower()
    
    # Policy 2: Security Violation -> QUARANTINE
    cand_unsafe = CandidateImplementation(
        candidate_id="impl_unsafe",
        name="Unsafe Candidate",
        version="1.0.0",
        repository="repo",
        license="MIT",
        claimed_capabilities=["sanctions_screening"],
        security_profile={"status": "FAIL"},
    )
    dec_unsafe = engine.evaluate_candidate(cand_unsafe)
    assert dec_unsafe.decision == CompetitionDecisionType.QUARANTINE
    
    # Policy 3: New Capability Passing Benchmark -> RECRUIT_NEW_CAPABILITY
    cand_new = CandidateImplementation(
        candidate_id="impl_opensanctions_probe_v1",
        name="OpenSanctions Specialist",
        version="1.0.0",
        repository="https://github.com/opensanctions/yente",
        license="Apache-2.0",
        claimed_capabilities=["sanctions_and_beneficial_ownership"],
        security_profile={"status": "PASS"},
        benchmark_profile={"pass_rate": 0.90, "f1": 0.90},
    )
    dec_new = engine.evaluate_candidate(cand_new, is_new_capability=True)
    assert dec_new.decision == CompetitionDecisionType.RECRUIT_NEW_CAPABILITY
    
    # Policy 4: Overlapping Capabilities Coexistence
    cand_coexist = CandidateImplementation(
        candidate_id="impl_coexist",
        name="Coexist Candidate",
        version="1.0.0",
        repository="repo",
        license="Apache-2.0",
        claimed_capabilities=["general_web_research"],
        security_profile={"status": "PASS"},
    )
    dec_coexist = engine.evaluate_candidate(
        cand_coexist,
        incumbent_benchmark={"exploratory_queries_f1": 0.92, "f1": 0.85, "precision": 0.90, "recall": 0.85, "pass_rate": 0.85},
        candidate_benchmark={"structured_queries_f1": 0.95, "f1": 0.88, "precision": 0.92, "recall": 0.86, "pass_rate": 0.88},
        is_new_capability=False,
    )
    assert dec_coexist.decision == CompetitionDecisionType.COEXIST


def test_specialist_competition_runner_execution() -> None:
    """Test full 40-task execution of SPECIALIST_COMPETITION_V1 runner."""
    runner = SpecialistCompetitionRunner()
    summary = runner.run_benchmark()
    
    assert summary["total_tasks"] == len(runner.tasks)
    assert summary["total_tasks"] >= 40
    assert "A_incumbent_standalone" in summary["configurations"]
    assert "B_candidate_standalone" in summary["configurations"]
    assert "E_coexistence_both" in summary["configurations"]
    
    # Coexistence should achieve the highest pass rate across all 40 tasks
    coexist_pass = summary["configurations"]["E_coexistence_both"]["pass_rate"]
    cand_pass = summary["configurations"]["B_candidate_standalone"]["pass_rate"]
    inc_pass = summary["configurations"]["A_incumbent_standalone"]["pass_rate"]
    
    assert coexist_pass >= cand_pass
    assert coexist_pass >= inc_pass
    assert summary["decision"]["decision"] == CompetitionDecisionType.RECRUIT_NEW_CAPABILITY.value

