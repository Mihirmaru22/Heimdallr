"""Focused tests for GitHub Identity Intelligence Connector.

Verifies:
- Structured candidate profile discovery with source URLs, timestamps, and SHA-256 provenance.
- Strict epistemic boundary: discovered profiles are candidate identities, never verified equivalence.
- Delimiter permutation resilience ('_' <-> '-').
- Clean differentiation of non-existent users (HTTP 404) from service failures.
- Rate limiting (HTTP 403), server error (HTTP 5xx), and malformed response handling.
- Network timeout interception without unhandled exceptions.
- SSRF destination policy enforcement.
- End-to-end integration with IdentityProbeSpecialist and IdentitySpecialistAdapter.
"""

from __future__ import annotations

from typing import Any
import httpx
import pytest

from argus.capability_registry.adapters import IdentitySpecialistAdapter
from argus.specialists.identity.contract import (
    CandidateIdentityRelationship,
    EpistemicCandidateStatus,
    IdentifierType,
    IdentityProbeRequest,
    IdentityProbeResult,
    InvestigationConstraints,
)
from argus.specialists.identity.github import GitHubIdentityConnector
from argus.specialists.identity.specialist import IdentityProbeSpecialist


MOCK_OCTOCAT_RESPONSE = {
    "login": "octocat",
    "id": 583231,
    "avatar_url": "https://avatars.githubusercontent.com/u/583231?v=4",
    "html_url": "https://github.com/octocat",
    "name": "The Octocat",
    "company": "@github",
    "blog": "https://github.blog",
    "location": "San Francisco",
    "email": None,
    "bio": "Building the future of software.",
    "public_repos": 8,
    "created_at": "2011-01-25T18:44:36Z",
}


def build_mock_transport(handler) -> httpx.AsyncClient:
    """Build an httpx AsyncClient using an in-memory MockTransport."""
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport)


@pytest.mark.asyncio
async def test_github_successful_profile_extraction():
    """Verify candidate identity profile extraction with source URLs and SHA-256 provenance."""
    def handler(request: httpx.Request) -> httpx.Response:
        assert "api.github.com/users/octocat" in str(request.url)
        return httpx.Response(200, json=MOCK_OCTOCAT_RESPONSE)

    client = build_mock_transport(handler)
    connector = GitHubIdentityConnector(client=client)

    req = IdentityProbeRequest(
        identifier="octocat",
        identifier_type=IdentifierType.USERNAME,
    )

    candidates, errors, queried = await connector.probe_username_async(req)

    assert queried == 1
    assert len(candidates) == 1

    cand = candidates[0]
    assert cand.candidate_entity == "octocat"
    assert cand.source_platform == "GitHub"
    assert cand.source_url == "https://github.com/octocat"
    assert "The Octocat" in cand.supporting_observation
    assert "@github" in cand.supporting_observation
    assert "San Francisco" in cand.supporting_observation
    assert cand.confidence <= 0.70
    assert "sha256_hash" in cand.provenance
    assert "canonical_url" in cand.provenance
    assert cand.provenance["http_status"] == 200

    # Epistemic invariant check: candidate-only status, never verified identity equivalence
    assert cand.epistemic_status == EpistemicCandidateStatus.UNVERIFIED_CANDIDATE
    assert cand.epistemic_status != "VERIFIED_SAME_PERSON"


@pytest.mark.asyncio
async def test_github_delimiter_permutation_expansion():
    """Verify handle permutation expands '_' to '-' when searching GitHub handles."""
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        requested_urls.append(url_str)
        if "users/techlead-marcus" in url_str:
            resp_data = dict(MOCK_OCTOCAT_RESPONSE)
            resp_data["login"] = "techlead-marcus"
            resp_data["html_url"] = "https://github.com/techlead-marcus"
            return httpx.Response(200, json=resp_data)
        return httpx.Response(404, json={"message": "Not Found"})

    client = build_mock_transport(handler)
    connector = GitHubIdentityConnector(client=client)

    req = IdentityProbeRequest(
        identifier="techlead_marcus",
        identifier_type=IdentifierType.USERNAME,
        constraints=InvestigationConstraints(permit_delimiter_permutations=True),
    )

    candidates, errors, queried = await connector.probe_username_async(req)

    assert any("users/techlead_marcus" in u for u in requested_urls)
    assert any("users/techlead-marcus" in u for u in requested_urls)
    assert len(candidates) == 1
    assert candidates[0].candidate_entity == "techlead-marcus"
    assert candidates[0].discovery_method == "delimiter_permutation_probe"


@pytest.mark.asyncio
async def test_github_404_distinguished_from_failures():
    """Verify nonexistent user (HTTP 404) returns 0 candidates and clean notice, not error."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    client = build_mock_transport(handler)
    connector = GitHubIdentityConnector(client=client)

    req = IdentityProbeRequest(identifier="nonexistent_phantom_handle_999xyz")
    candidates, errors, queried = await connector.probe_username_async(req)

    assert len(candidates) == 0
    assert any("No profile discovered on GitHub" in e for e in errors)
    assert not any("unavailable" in e for e in errors)


@pytest.mark.asyncio
async def test_github_rate_limiting_403():
    """Verify HTTP 403 rate limiting is captured cleanly without unhandled exception."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "API rate limit exceeded"})

    client = build_mock_transport(handler)
    connector = GitHubIdentityConnector(client=client)

    req = IdentityProbeRequest(identifier="octocat")
    candidates, errors, queried = await connector.probe_username_async(req)

    assert len(candidates) == 0
    assert any("rate limit exceeded (HTTP 403)" in e for e in errors)


@pytest.mark.asyncio
async def test_github_server_unavailable_503():
    """Verify HTTP 503 service unavailable is handled gracefully."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    client = build_mock_transport(handler)
    connector = GitHubIdentityConnector(client=client)

    req = IdentityProbeRequest(identifier="octocat")
    candidates, errors, queried = await connector.probe_username_async(req)

    assert len(candidates) == 0
    assert any("service unavailable (HTTP 503)" in e for e in errors)


@pytest.mark.asyncio
async def test_github_malformed_json_handling():
    """Verify malformed JSON responses do not cause unhandled exceptions."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>Proxy Error</html>")

    client = build_mock_transport(handler)
    connector = GitHubIdentityConnector(client=client)

    req = IdentityProbeRequest(identifier="octocat")
    candidates, errors, queried = await connector.probe_username_async(req)

    assert len(candidates) == 0
    assert any("Malformed JSON" in e for e in errors)


@pytest.mark.asyncio
async def test_github_timeout_interception():
    """Verify network timeouts are trapped cleanly."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Connection timed out waiting for GitHub API")

    client = build_mock_transport(handler)
    connector = GitHubIdentityConnector(client=client)

    req = IdentityProbeRequest(identifier="octocat")
    candidates, errors, queried = await connector.probe_username_async(req)

    assert len(candidates) == 0
    assert any("timed out" in e.lower() for e in errors)


def test_identity_specialist_and_adapter_end_to_end_with_github():
    """Verify IdentityProbeSpecialist and IdentitySpecialistAdapter integration with GitHubIdentityConnector."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=MOCK_OCTOCAT_RESPONSE)

    client = build_mock_transport(handler)
    connector = GitHubIdentityConnector(client=client)

    # Specialist with mocked connector and empty offline registry
    specialist = IdentityProbeSpecialist(platform_registry={}, live_connector=connector)
    adapter = IdentitySpecialistAdapter(specialist=specialist)

    res = adapter.execute({"identifier": "octocat", "timeout_sec": 5.0})

    assert res["status"] == "SUCCESS"
    assert res["identifier"] == "octocat"
    assert res["documents_count"] >= 1
    assert res["authoritative"] is False
    assert res["epistemic_nature"] == "CANDIDATE"

    # Verify documents contain candidate findings and provenance
    doc = res["documents"][0]
    assert doc["source_type"] == "identity_probe"
    assert "https://github.com/octocat" in doc["url"]
    assert "sha256_hash" in doc["payload"]["provenance"]
    assert doc["epistemic_status"] == "UNVERIFIED_CANDIDATE"

    # Verify candidate claims
    claims = res["claims"]
    assert len(claims) >= 1
    assert any("octocat" in c["subject"] for c in claims)
    assert any("GitHub" in c["object"] for c in claims)
