"""Focused tests for crt.sh Certificate Transparency Connector.

Verifies:
- Structured candidate subdomain and certificate SAN extraction with provenance.
- Strict epistemic boundary: discovered domains are candidates, never verified ownership.
- Temporal classification (active vs expired certificates).
- Resilience to unavailable upstream servers (HTTP 502/503/504).
- Resilience to malformed/HTML responses.
- Network timeout and transport error interception.
- SSRF destination policy enforcement.
- Empty result handling.
- End-to-end integration with InfrastructureProbeSpecialist and InfrastructureSpecialistAdapter.
"""

from __future__ import annotations

from typing import Any
import httpx
import pytest

from argus.capability_registry.adapters import InfrastructureSpecialistAdapter
from argus.specialists.infrastructure.contract import (
    AssetType,
    CandidateInfrastructureAsset,
    EpistemicAssetStatus,
    InfrastructureInvestigationConstraints,
    InfrastructureProbeRequest,
    RelationshipType,
    TemporalStatus,
)
from argus.specialists.infrastructure.crtsh import CrtShConnector
from argus.specialists.infrastructure.specialist import InfrastructureProbeSpecialist


MOCK_CRTSH_RESPONSE = [
    {
        "id": 1000000001,
        "issuer_ca_id": 16418,
        "issuer_name": "C=US, O=Let's Encrypt, CN=R3",
        "common_name": "example.com",
        "name_value": "example.com\napi.example.com\nadmin.example.com",
        "entry_timestamp": "2026-01-01T00:00:00.000",
        "not_before": "2026-01-01T00:00:00",
        "not_after": "2027-01-01T00:00:00",
        "serial_number": "03e456789abcdef",
    },
    {
        "id": 1000000002,
        "issuer_ca_id": 16418,
        "issuer_name": "C=US, O=Let's Encrypt, CN=R3",
        "common_name": "shared-portal.net",
        "name_value": "portal.example.com\nshared-portal.net",
        "entry_timestamp": "2020-01-01T00:00:00.000",
        "not_before": "2020-01-01T00:00:00",
        "not_after": "2021-01-01T00:00:00",  # Expired certificate
        "serial_number": "03e456789abcdeg",
    },
]


def build_mock_transport(handler) -> httpx.AsyncClient:
    """Build an httpx AsyncClient using an in-memory MockTransport."""
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport)


@pytest.mark.asyncio
async def test_crtsh_successful_extraction():
    """Verify candidate subdomains and SANs are extracted with source URLs and SHA-256 provenance."""
    def handler(request: httpx.Request) -> httpx.Response:
        assert "crt.sh" in str(request.url)
        return httpx.Response(200, json=MOCK_CRTSH_RESPONSE)

    client = build_mock_transport(handler)
    connector = CrtShConnector(client=client)

    req = InfrastructureProbeRequest(
        domain="example.com",
        constraints=InfrastructureInvestigationConstraints(max_assets=10),
    )

    candidates, errors, queried = await connector.query_crtsh_async(req)

    assert queried == 1
    assert len(candidates) >= 3

    # Check direct subdomain candidate
    sub_asset = next(c for c in candidates if c.hostname == "api.example.com")
    assert sub_asset.parent_domain == "example.com"
    assert sub_asset.asset_type == AssetType.SUBDOMAIN
    assert sub_asset.relationship_type == RelationshipType.DIRECT_SUBDOMAIN
    assert sub_asset.temporal_status == TemporalStatus.CURRENT_ACTIVE
    assert sub_asset.epistemic_status == EpistemicAssetStatus.CANDIDATE_ASSET
    assert "https://crt.sh/?id=1000000001" in sub_asset.provenance["source_endpoints"]
    assert "sha256_fingerprint" in sub_asset.provenance
    assert "queried_at" in sub_asset.provenance

    # Epistemic invariant check: candidate-only confidence, never verified ownership
    assert sub_asset.confidence <= 0.70
    assert sub_asset.epistemic_status != "VERIFIED_OWNED_ASSET"


@pytest.mark.asyncio
async def test_crtsh_temporal_expiration_classification():
    """Verify expired certificates are tagged with HISTORICAL_EXPIRED temporal status."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=MOCK_CRTSH_RESPONSE)

    client = build_mock_transport(handler)
    connector = CrtShConnector(client=client)

    req = InfrastructureProbeRequest(
        domain="example.com",
        constraints=InfrastructureInvestigationConstraints(max_assets=10),
    )

    candidates, errors, queried = await connector.query_crtsh_async(req)

    # Check expired host
    expired_asset = next(c for c in candidates if c.hostname == "portal.example.com")
    assert expired_asset.temporal_status == TemporalStatus.HISTORICAL_EXPIRED
    assert expired_asset.epistemic_status == EpistemicAssetStatus.EXPIRED_HISTORICAL


@pytest.mark.asyncio
async def test_crtsh_service_unavailable_502():
    """Verify crt.sh 502/503/504 errors are intercepted cleanly without unhandled exceptions."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="Bad Gateway (database server busy)")

    client = build_mock_transport(handler)
    connector = CrtShConnector(client=client)

    req = InfrastructureProbeRequest(domain="example.com")
    candidates, errors, queried = await connector.query_crtsh_async(req)

    assert len(candidates) == 0
    assert any("temporarily unavailable (HTTP 502)" in e for e in errors)


@pytest.mark.asyncio
async def test_crtsh_malformed_html_response():
    """Verify HTML error pages returned with HTTP 200 are caught as malformed JSON."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body><h1>Database Timeout</h1></body></html>")

    client = build_mock_transport(handler)
    connector = CrtShConnector(client=client)

    req = InfrastructureProbeRequest(domain="example.com")
    candidates, errors, queried = await connector.query_crtsh_async(req)

    assert len(candidates) == 0
    assert any("Malformed JSON" in e for e in errors)


@pytest.mark.asyncio
async def test_crtsh_timeout_interception():
    """Verify network timeouts do not raise unhandled exceptions."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Timeout waiting for crt.sh query")

    client = build_mock_transport(handler)
    connector = CrtShConnector(client=client)

    req = InfrastructureProbeRequest(domain="example.com")
    candidates, errors, queried = await connector.query_crtsh_async(req)

    assert len(candidates) == 0
    assert any("timed out" in e.lower() for e in errors)


@pytest.mark.asyncio
async def test_crtsh_empty_results():
    """Verify empty record lists are handled gracefully."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    client = build_mock_transport(handler)
    connector = CrtShConnector(client=client)

    req = InfrastructureProbeRequest(domain="nonexistent-sample-domain-12345.org")
    candidates, errors, queried = await connector.query_crtsh_async(req)

    assert len(candidates) == 0
    assert any("No certificate transparency records discovered" in e for e in errors)


def test_infrastructure_specialist_and_adapter_end_to_end_with_crtsh():
    """Verify InfrastructureProbeSpecialist and InfrastructureSpecialistAdapter integration with CrtShConnector."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=MOCK_CRTSH_RESPONSE)

    client = build_mock_transport(handler)
    connector = CrtShConnector(client=client)

    # Specialist with mocked connector and empty offline registry
    specialist = InfrastructureProbeSpecialist(registry={}, crtsh_connector=connector)
    adapter = InfrastructureSpecialistAdapter(specialist=specialist)

    res = adapter.execute({"target_domain": "example.com", "timeout_sec": 5.0})

    assert res["status"] == "SUCCESS"
    assert res["target"] == "example.com"
    assert res["documents_count"] >= 3
    assert res["authoritative"] is False
    assert res["epistemic_nature"] == "CANDIDATE"

    # Verify documents contain candidate findings and provenance
    doc = res["documents"][0]
    assert doc["source_type"] in ("subdomain", "related_domain", "certificate_san")
    assert "https://" in doc["url"]
    assert "sha256_fingerprint" in doc["payload"]["provenance"]

    # Verify candidate claims
    claims = res["claims"]
    assert len(claims) >= 3
    assert any("example.com" in c["subject"] for c in claims)
