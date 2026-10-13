"""Unit and Integration Tests for Clean-Room InfrastructureProbeSpecialist."""

import pytest
from argus.evals.infrastructure_corpus import INFRASTRUCTURE_REGISTRY
from argus.evals.infrastructure_runner import InfrastructureBenchmarkRunner
from argus.specialists.infrastructure import (
    AssetType,
    CandidateInfrastructureAsset,
    EpistemicAssetStatus,
    InfrastructureInvestigationConstraints,
    InfrastructureProbeRequest,
    InfrastructureProbeSpecialist,
    RelationshipType,
    TemporalStatus,
)


def test_infrastructure_specialist_contract():
    req = InfrastructureProbeRequest(
        domain="autotech.corp",
        entity_name="AutoTech Corporation",
    )
    assert req.domain == "autotech.corp"
    assert req.entity_name == "AutoTech Corporation"


def test_infrastructure_specialist_discovers_subdomains():
    specialist = InfrastructureProbeSpecialist(registry=INFRASTRUCTURE_REGISTRY)
    res = specialist.discover_domain("autotech.corp")
    assert res.total_assets_found >= 3
    hosts = [a.hostname for a in res.assets]
    assert "portal.autotech.corp" in hosts
    assert "api.autotech.corp" in hosts
    assert "dev.autotech.corp" in hosts

    for a in res.assets:
        assert a.epistemic_status == EpistemicAssetStatus.CANDIDATE_ASSET
        assert "sha256_fingerprint" in a.provenance
        assert a.confidence >= 0.70


def test_infrastructure_specialist_phantom_returns_zero():
    specialist = InfrastructureProbeSpecialist(registry=INFRASTRUCTURE_REGISTRY)
    res = specialist.discover_domain("nonexistent-phantom-infrastructure-987654321.xyz")
    assert res.total_assets_found == 0
    assert len(res.assets) == 0


def test_runner_integrated_rejection_of_lookalikes():
    runner = InfrastructureBenchmarkRunner()
    # Task 9 is billing.autotech-security.com (adversarial lookalike phishing campaign)
    res = runner.run_integrated(runner.tasks[8])
    assert res.passed is True
    assert res.epistemic_status == "ADVERSARIAL_LOOKALIKE"
    assert "billing.autotech-security.com" not in res.discovered_assets


def test_runner_integrated_scope_boundary_saas():
    runner = InfrastructureBenchmarkRunner()
    # Task 11 is autotech.zendesk.com (third-party SaaS)
    res = runner.run_integrated(runner.tasks[10])
    assert res.passed is True
    assert res.epistemic_status == "THIRD_PARTY_SERVICE"
    assert "autotech.zendesk.com" not in res.discovered_assets
