"""Regression tests for Identity Evidence Integrity and Metrics Accuracy.

Verifies:
1. Live retrieval and fixture simulation are explicitly distinguishable.
2. Fixture records cannot masquerade as live-retrieved evidence.
3. Cryptographic response-content hashes and observation-record hashes are clearly distinguished.
4. An unavailable upstream source does not infer confirmed non-existence (NOT_FOUND).
5. Removal of the artificial 150 platforms minimum, with accurate reporting of
   queried, skipped, and available platform counts.
"""

import hashlib
import json
import httpx
import pytest

from argus.evals.vertical_corpus import VERTICAL_PLATFORM_REGISTRY
from argus.investigation.orchestrator import InvestigationEngine
from argus.specialists.identity.contract import (
    AccountClaimType,
    IdentityProbeRequest,
    InvestigationConstraints,
)
from argus.specialists.identity.github import GitHubIdentityConnector
from argus.specialists.identity.specialist import IdentityProbeSpecialist
from argus.specialists.outcome import SpecialistOutcome


def test_fixture_records_cannot_masquerade_as_live_evidence():
    """Verify that records sourced from platform registry are marked as FIXTURE_SIMULATION

    and never masquerade as live-retrieved network evidence.
    """
    specialist = IdentityProbeSpecialist(platform_registry=VERTICAL_PLATFORM_REGISTRY)
    res = specialist.search_username("s0md3v", starting_platform="github")

    assert len(res.candidates) >= 1
    for cand in res.candidates:
        assert cand.retrieval_mode == "FIXTURE_SIMULATION"
        assert cand.is_live is False
        assert cand.response_content_sha256 is None
        assert cand.observation_record_sha256 is not None
        assert len(cand.observation_record_sha256) == 64

        # Provenance verification
        prov = cand.provenance
        assert prov.get("retrieval_mode") == "FIXTURE_SIMULATION"
        assert prov.get("is_live") is False
        assert prov.get("source_origin") == "FIXTURE_REGISTRY"
        assert prov.get("response_content_sha256") is None
        assert prov.get("observation_record_sha256") == cand.observation_record_sha256

    assert len(res.claims) >= 1
    for claim in res.claims:
        assert claim.retrieval_mode == "FIXTURE_SIMULATION"
        assert claim.is_live is False
        assert claim.response_content_sha256 is None
        assert claim.observation_record_sha256 is not None


def test_live_retrieval_captures_response_content_hash_and_live_provenance():
    """Verify live connector distinguishes raw response content hash from observation record hash."""
    mock_payload = {
        "login": "live_researcher",
        "name": "Live Researcher",
        "bio": "Systems verification and formal security",
        "location": "Boston, MA",
        "public_repos": 42,
        "html_url": "https://github.com/live_researcher",
    }
    raw_bytes = json.dumps(mock_payload).encode("utf-8")
    expected_content_sha256 = hashlib.sha256(raw_bytes).hexdigest()

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=raw_bytes, headers={"Content-Type": "application/json"})

    transport = httpx.MockTransport(mock_handler)
    client = httpx.AsyncClient(transport=transport)
    gh_connector = GitHubIdentityConnector(client=client)

    specialist = IdentityProbeSpecialist(platform_registry={}, live_connector=gh_connector)
    res = specialist.search_username("live_researcher", starting_platform="github")

    assert res.outcome == SpecialistOutcome.SUCCESS_WITH_RESULTS
    assert len(res.candidates) >= 1

    cand = res.candidates[0]
    assert cand.candidate_entity == "live_researcher"
    assert cand.retrieval_mode == "LIVE"
    assert cand.is_live is True
    assert cand.response_content_sha256 == expected_content_sha256
    assert cand.observation_record_sha256 is not None

    # Crucial: observation record hash and response content hash must be distinct
    assert cand.response_content_sha256 != cand.observation_record_sha256

    prov = cand.provenance
    assert prov.get("retrieval_mode") == "LIVE"
    assert prov.get("is_live") is True
    assert prov.get("source_origin") == "LIVE_NETWORK"
    assert prov.get("response_content_sha256") == expected_content_sha256
    assert prov.get("observation_record_sha256") == cand.observation_record_sha256


def test_unavailable_source_does_not_infer_non_existence():
    """Invariant: An unavailable upstream source (5xx / timeout) must NOT infer confirmed non-existence (NOT_FOUND)."""
    def handler_500(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    transport = httpx.MockTransport(handler_500)
    client = httpx.AsyncClient(transport=transport)
    gh_connector = GitHubIdentityConnector(client=client)

    specialist = IdentityProbeSpecialist(platform_registry={}, live_connector=gh_connector)
    res = specialist.search_username("unknown_user", starting_platform="github")

    assert res.outcome == SpecialistOutcome.SOURCE_UNAVAILABLE
    assert len(res.candidates) == 0

    # Test through InvestigationEngine end-to-end slice
    engine = InvestigationEngine()
    engine.identity_specialist = specialist
    report = engine.investigate_identity(
        username="unknown_user",
        starting_platform="github",
        max_steps=2,
    )

    assert report.outcome == SpecialistOutcome.SOURCE_UNAVAILABLE
    # Epistemic status must NOT be NOT_FOUND (confirmed absence) when source is degraded/unavailable
    assert report.epistemic_status != "NOT_FOUND"
    assert report.epistemic_status in ("INSUFFICIENT_EVIDENCE", "UNKNOWN", "UNAVAILABLE")


def test_platform_metrics_remove_150_minimum_and_report_accurate_counts():
    """Verify removal of artificial 150 minimum and accurate reporting of queried, skipped, and available platforms."""
    # Full registry probe (9 platforms)
    specialist = IdentityProbeSpecialist(platform_registry=VERTICAL_PLATFORM_REGISTRY)
    res = specialist.search_username("s0md3v")

    assert res.total_platforms_probed == 9
    assert res.platforms_queried == 9
    assert res.platforms_skipped == 0
    assert res.platforms_available == len(VERTICAL_PLATFORM_REGISTRY)
    assert res.total_platforms_probed != 150  # Must not use artificial 150 ceiling

    # Constrained probe with platform filter
    req = IdentityProbeRequest(
        identifier="s0md3v",
        constraints=InvestigationConstraints(
            allowed_platforms=["github", "twitter"],
            blocked_platforms=["instagram"],
        ),
    )
    res_filtered = specialist.probe_identifier(req)
    assert res_filtered.platforms_queried == 2
    assert res_filtered.platforms_skipped == 7
    assert res_filtered.platforms_available == len(VERTICAL_PLATFORM_REGISTRY)
    assert res_filtered.total_platforms_probed == 2
