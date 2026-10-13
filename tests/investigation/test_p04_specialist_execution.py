"""Tests for P0.4: Real Specialist Execution, Structured I/O, Timeouts, and Orchestrator Integration."""

import time
import pytest

from argus.capability_registry.adapters import (
    CorporateSpecialistAdapter,
    IdentitySpecialistAdapter,
    InfrastructureSpecialistAdapter,
)
from argus.evals.corporate_corpus import CORPORATE_REGISTRY_DATABASE
from argus.evals.infrastructure_corpus import INFRASTRUCTURE_REGISTRY
from argus.evals.vertical_corpus import VERTICAL_PLATFORM_REGISTRY
from argus.investigation.action import ActionType, ResearchAction
from argus.investigation.orchestrator import InvestigationEngine
from argus.specialists.corporate import CorporateProbeSpecialist
from argus.specialists.corporate.contract import CorporateProbeRequest
from argus.specialists.identity import IdentityProbeSpecialist
from argus.specialists.identity.contract import IdentityProbeRequest
from argus.specialists.infrastructure import InfrastructureProbeSpecialist
from argus.specialists.infrastructure.contract import InfrastructureProbeRequest


def test_corporate_specialist_real_execution():
    """Verify real corporate specialist invocation with structured request, response, and cryptographic provenance."""
    specialist = CorporateProbeSpecialist(registry_database=CORPORATE_REGISTRY_DATABASE)
    adapter = CorporateSpecialistAdapter(specialist=specialist)

    res = adapter.execute({"company_name": "AutoTech Corporation", "timeout_sec": 5.0})

    assert res["status"] == "SUCCESS"
    assert res["capability_id"] == "corporate_registry_intelligence"
    assert res["implementation_id"] == "impl_corporate_registry_specialist_v1"
    assert res["documents_count"] >= 3
    assert "AutoTech Corporation" in res["entities"]
    assert "AutoTech" in res["entities"]

    # Verify cryptographic provenance and candidate safety
    for doc in res["documents"]:
        if "payload" in doc and doc["payload"]:
            payload = doc["payload"]
            assert "provenance" in payload
            assert "sha256_fingerprint" in payload["provenance"]
            assert doc["is_authoritative"] is False


def test_infrastructure_specialist_real_execution():
    """Verify real infrastructure specialist invocation with subdomain discovery and SAN mapping."""
    specialist = InfrastructureProbeSpecialist(registry=INFRASTRUCTURE_REGISTRY)
    adapter = InfrastructureSpecialistAdapter(specialist=specialist)

    res = adapter.execute({"target_domain": "autotech.corp", "timeout_sec": 5.0})

    assert res["status"] == "SUCCESS"
    assert res["capability_id"] == "infrastructure_discovery"
    assert res["documents_count"] >= 3

    # Check discovered hosts
    hostnames = {doc.get("title", "") for doc in res["documents"]}
    assert any("portal.autotech.corp" in h for h in hostnames)
    assert any("api.autotech.corp" in h for h in hostnames)

    # Verify candidate-only epistemic safety
    for doc in res["documents"]:
        assert doc["is_authoritative"] is False


def test_identity_specialist_real_execution():
    """Verify real identity specialist invocation with cross-platform handle correlation."""
    specialist = IdentityProbeSpecialist(platform_registry=VERTICAL_PLATFORM_REGISTRY)
    adapter = IdentitySpecialistAdapter(specialist=specialist)

    res = adapter.execute({"identifier": "s0md3v", "timeout_sec": 5.0})

    assert res["status"] == "SUCCESS"
    assert res["capability_id"] == "identity_resolution"
    assert res["documents_count"] >= 2
    assert "s0md3v" in res["entities"]

    urls = [d.get("url", "") for d in res["documents"]]
    assert any("github.com/s0md3v" in u for u in urls)


def test_specialist_timeout_handling():
    """Verify that a slow specialist call is terminated and handled gracefully without hanging."""
    class SlowSpecialist:
        def probe_corporate_entity(self, req):
            time.sleep(2.0)
            return None

    adapter = CorporateSpecialistAdapter(specialist=SlowSpecialist())
    res = adapter.execute({"company_name": "SlowCo", "timeout_sec": 0.1})

    assert res["status"] == "TIMEOUT"
    assert "timed out after 0.1s" in res["error"]
    assert res["documents_count"] == 0


def test_specialist_error_handling():
    """Verify that specialist runtime exceptions are caught and reported in structured output."""
    class FailingSpecialist:
        def probe_corporate_entity(self, req):
            raise ValueError("Corrupt statutory registry payload")

    adapter = CorporateSpecialistAdapter(specialist=FailingSpecialist())
    res = adapter.execute({"company_name": "BrokenCo", "timeout_sec": 2.0})

    assert res["status"] == "FAILED"
    assert "Corrupt statutory registry payload" in res["error"]


def test_orchestrator_integration_with_real_specialist():
    """Verify end-to-end integration: orchestrator dispatches action, executes real specialist, and updates state."""
    engine = InvestigationEngine()
    state = engine.start_investigation(
        objective="Investigate AutoTech Corporation corporate structure and regulatory officers.",
        contract={"target_entities": ["AutoTech Corporation"]},
    )

    action = ResearchAction(
        action_type=ActionType.INVESTIGATE_SPECIALIST,
        query="AutoTech Corporation",
        specialist="corporate",
        target_entities=["AutoTech Corporation"],
        rationale="Query corporate registry intelligence for regulatory filings and officers.",
    )

    obs = engine._dispatch_action(action, state)
    assert obs["status"] == "SUCCESS"
    assert obs["documents_count"] >= 3

    # Check specialist invocations record
    assert len(state.specialist_invocations) >= 1
    inv = state.specialist_invocations[-1]
    assert inv["specialist"] == "corporate"
    assert inv["implementation_id"] == "impl_corporate_registry_specialist_v1"
    assert inv["status"] == "SUCCESS"

    # Update state via belief update
    engine._apply_observation(state, action, obs)
    assert "AutoTech Corporation" in state.entities
    # Discovered relationships or officers are extracted into state
    discovered = set(state.entities.keys())
    assert any("AutoTech" in e or "Somdev Vance" in e or "Elena Rostova" in e for e in discovered)


def test_orchestrator_specialist_timeout_audit():
    """Verify that orchestrator records an audit trail event when a specialist times out."""
    from argus.capability_registry.adapters import (
        BaseCapabilityAdapter,
        register_capability_adapter,
        unregister_capability_adapter,
    )

    class MockSlowCorpAdapter(BaseCapabilityAdapter):
        def execute(self, inputs, corpus=None):
            return {"status": "TIMEOUT", "error": "Execution deadline exceeded (0.1s)"}

    register_capability_adapter("impl_corporate_registry_specialist_v1", MockSlowCorpAdapter())

    try:
        engine = InvestigationEngine()
        state = engine.start_investigation(
            objective="Query corporate officers",
            contract={"target_entities": ["TestCorp"]},
        )

        action = ResearchAction(
            action_type=ActionType.INVESTIGATE_SPECIALIST,
            query="TestCorp",
            specialist="corporate",
            target_entities=["TestCorp"],
            rationale="Test timeout behavior",
        )

        obs = engine._dispatch_action(action, state)
        assert obs["status"] == "TIMEOUT"
        assert action.status == "FAILED"
        assert any(a.action_type == "SPECIALIST_EXECUTION_TIMEOUT" for a in state.audit_trail)
    finally:
        unregister_capability_adapter("impl_corporate_registry_specialist_v1")
