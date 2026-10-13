"""Unit and Integration Tests for Clean-Room IdentityProbeSpecialist."""

import pytest
from argus.evals.vertical_corpus import VERTICAL_PLATFORM_REGISTRY
from argus.evals.vertical_runner import VerticalBenchmarkRunner
from argus.specialists.identity import (
    CandidateIdentityRelationship,
    EpistemicCandidateStatus,
    IdentifierType,
    IdentityProbeRequest,
    IdentityProbeSpecialist,
    InvestigationConstraints,
)


def test_specialist_contract_validation():
    req = IdentityProbeRequest(
        identifier="s0md3v",
        identifier_type=IdentifierType.USERNAME,
        target_entity_context={"profession": "Security Researcher"},
    )
    assert req.identifier == "s0md3v"
    assert req.identifier_type == IdentifierType.USERNAME


def test_specialist_finds_accounts_with_provenance():
    specialist = IdentityProbeSpecialist(platform_registry=VERTICAL_PLATFORM_REGISTRY)
    result = specialist.search_username("s0md3v")
    assert result.total_candidates_found >= 3
    urls = [c.source_url for c in result.candidates]
    assert "https://github.com/s0md3v" in urls
    assert "https://twitter.com/s0md3v" in urls
    assert "https://medium.com/@s0md3v" in urls

    for c in result.candidates:
        assert c.epistemic_status == EpistemicCandidateStatus.UNVERIFIED_CANDIDATE
        assert "sha256_hash" in c.provenance
        assert c.provenance["http_status"] == 200


def test_specialist_phantom_returns_zero():
    specialist = IdentityProbeSpecialist(platform_registry=VERTICAL_PLATFORM_REGISTRY)
    result = specialist.search_username("nonexistent_phantom_handle_987654321_xyz")
    assert result.total_candidates_found == 0
    assert len(result.candidates) == 0


def test_specialist_delimiter_permutation_expansion():
    specialist = IdentityProbeSpecialist(platform_registry=VERTICAL_PLATFORM_REGISTRY)
    # Target has underscore, but GitHub has hyphen 'techlead-marcus'
    req = IdentityProbeRequest(
        identifier="techlead_marcus",
        identifier_type=IdentifierType.USERNAME,
        constraints=InvestigationConstraints(permit_delimiter_permutations=True),
    )
    result = specialist.probe_identifier(req)
    urls = [c.source_url for c in result.candidates]
    assert "https://twitter.com/techlead_marcus" in urls
    assert "https://github.com/techlead-marcus" in urls


def test_vertical_runner_cleanroom_standalone():
    runner = VerticalBenchmarkRunner()
    res = runner.run_cleanroom_specialist_standalone(runner.tasks[0])  # s0md3v
    assert res.passed is True
    assert res.candidate_recall == 1.0


def test_vertical_runner_cleanroom_integrated_filters_collision():
    runner = VerticalBenchmarkRunner()
    # Task 4 is Joe Bobnar (LinkedIn plant manager, Twitch gamer is unacceptable merge)
    res = runner.run_cleanroom_integrated(runner.tasks[3])
    assert res.passed is True
    assert "https://twitch.tv/jbobnar" not in res.discovered_accounts
    assert "https://linkedin.com/in/jbobnar" in res.discovered_accounts


def test_vertical_runner_cleanroom_integrated_contradiction():
    runner = VerticalBenchmarkRunner()
    # Task 7 is Sarah Connor (AI researcher in Cambridge vs Miami gym trainer)
    res = runner.run_cleanroom_integrated(runner.tasks[6])
    assert res.passed is True
    assert res.epistemic_status == "CONTRADICTED"
    assert "https://github.com/sarah_connor_ai" not in res.discovered_accounts
