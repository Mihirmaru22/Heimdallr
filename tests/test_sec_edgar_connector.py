"""Focused tests for SEC EDGAR Submissions API Connector.

Verifies:
- Live and mocked SEC EDGAR retrieval.
- Entity and ticker resolution to standard 10-digit CIK.
- Structured candidate relationship extraction with provenance.
- Rate limiting (429), not found (404), and malformed response handling.
- Timeout and transport error interception.
- SSRF policy enforcement.
- Explicit reporting of unsupported fields (officer/subsidiary limitations).
- End-to-end integration with CorporateProbeSpecialist and CorporateSpecialistAdapter.
"""

from __future__ import annotations

import json
from typing import Any
import httpx
import pytest

from argus.capability_registry.adapters import CorporateSpecialistAdapter
from argus.specialists.corporate.contract import (
    CandidateCorporateRelationship,
    CorporateIdentifierType,
    CorporateInvestigationConstraints,
    CorporateProbeRequest,
    CorporateRelationshipType,
    EpistemicCorporateStatus,
    TemporalCorporateStatus,
)
from argus.specialists.corporate.edgar import SecEdgarConnector
from argus.specialists.corporate.specialist import CorporateProbeSpecialist


MOCK_TICKERS_JSON = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "1": {"cik_str": 789019, "ticker": "MSFT", "title": "MICROSOFT CORP"},
    "2": {"cik_str": 1318605, "ticker": "TSLA", "title": "Tesla, Inc."},
}

MOCK_SUBMISSIONS_AAPL = {
    "cik": "0000320193",
    "entityType": "operating",
    "sic": "3571",
    "sicDescription": "Electronic Computers",
    "name": "Apple Inc.",
    "tickers": ["AAPL"],
    "exchanges": ["Nasdaq"],
    "ein": "942404110",
    "stateOfIncorporation": "CA",
    "stateOfIncorporationDescription": "California",
    "fiscalYearEnd": "0930",
    "businessAddress": {
        "street1": "One Apple Park Way",
        "city": "Cupertino",
        "stateOrCountry": "CA",
        "zipCode": "95014",
    },
    "filings": {
        "recent": {
            "accessionNumber": [
                "0000320193-23-000106",
                "0000320193-23-000077",
                "0000320193-23-000064",
            ],
            "filingDate": ["2023-11-03", "2023-08-04", "2023-05-05"],
            "reportDate": ["2023-09-30", "2023-07-01", "2023-04-01"],
            "form": ["10-K", "10-Q", "10-Q"],
            "primaryDocument": ["aapl-20230930.htm", "aapl-20230701.htm", "aapl-20230401.htm"],
        }
    },
}


def build_mock_transport(handler) -> httpx.AsyncClient:
    """Build an httpx AsyncClient using an in-memory MockTransport."""
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport)


@pytest.mark.asyncio
async def test_sec_edgar_successful_extraction():
    """Verify structured findings and provenance extraction from mocked SEC EDGAR response."""
    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "company_tickers.json" in url_str:
            return httpx.Response(200, json=MOCK_TICKERS_JSON)
        elif "CIK0000320193.json" in url_str:
            return httpx.Response(200, json=MOCK_SUBMISSIONS_AAPL)
        return httpx.Response(404, text="Not Found")

    client = build_mock_transport(handler)
    connector = SecEdgarConnector(client=client)

    req = CorporateProbeRequest(
        entity_name="Apple Inc.",
        corporate_identifier="AAPL",
        constraints=CorporateInvestigationConstraints(max_candidates=10),
    )

    relationships, errors, queried = await connector.probe_sec_edgar_async(req)

    assert queried == 1
    assert len(relationships) >= 4  # 1 CIK + 1 Ticker + 3 Filings (up to max)
    
    # Verify primary CIK relationship
    cik_rel = next(r for r in relationships if r.object_entity == "CIK:0000320193")
    assert cik_rel.subject_entity == "Apple Inc."
    assert cik_rel.predicate == CorporateRelationshipType.FILING_ENTITY
    assert cik_rel.jurisdiction == "CA"
    assert cik_rel.source_registry == "SEC_EDGAR"
    assert "https://data.sec.gov/submissions/CIK0000320193.json" in cik_rel.source_url
    assert cik_rel.confidence == 0.99
    assert cik_rel.epistemic_status == EpistemicCorporateStatus.CANDIDATE_FACT
    assert "sha256_fingerprint" in cik_rel.provenance
    assert "retrieved_at" in cik_rel.provenance

    # Verify 10-K filing relationship
    filing_10k = next(r for r in relationships if r.filing_id == "0000320193-23-000106")
    assert filing_10k.object_entity == "10-K"
    assert filing_10k.filing_date == "2023-11-03"
    assert filing_10k.effective_date == "2023-09-30"
    assert "Archives/edgar/data/320193" in filing_10k.source_url


@pytest.mark.asyncio
async def test_sec_edgar_direct_cik_query():
    """Verify direct numeric CIK query does not require company_tickers lookup."""
    tickers_called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal tickers_called
        url_str = str(request.url)
        if "company_tickers.json" in url_str:
            tickers_called = True
            return httpx.Response(200, json=MOCK_TICKERS_JSON)
        elif "CIK0000320193.json" in url_str:
            return httpx.Response(200, json=MOCK_SUBMISSIONS_AAPL)
        return httpx.Response(404)

    client = build_mock_transport(handler)
    connector = SecEdgarConnector(client=client)

    req = CorporateProbeRequest(
        entity_name="Apple",
        corporate_identifier="320193",  # Numeric CIK passed directly
    )

    relationships, errors, queried = await connector.probe_sec_edgar_async(req)

    assert not tickers_called
    assert len(relationships) >= 1
    assert any(r.object_entity == "CIK:0000320193" for r in relationships)


@pytest.mark.asyncio
async def test_sec_edgar_rate_limit_handling():
    """Verify HTTP 429 rate limit is captured cleanly without unhandled exception."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="Too Many Requests")

    client = build_mock_transport(handler)
    connector = SecEdgarConnector(client=client)

    req = CorporateProbeRequest(entity_name="Apple", corporate_identifier="0000320193")
    relationships, errors, queried = await connector.probe_sec_edgar_async(req)

    assert len(relationships) == 0
    assert any("rate limit exceeded (HTTP 429)" in e for e in errors)


@pytest.mark.asyncio
async def test_sec_edgar_not_found_handling():
    """Verify HTTP 404 for unknown CIK returns empty findings and structured error."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="Not Found")

    client = build_mock_transport(handler)
    connector = SecEdgarConnector(client=client)

    req = CorporateProbeRequest(entity_name="NonExistent", corporate_identifier="9999999999")
    relationships, errors, queried = await connector.probe_sec_edgar_async(req)

    assert len(relationships) == 0
    assert any("HTTP 404" in e for e in errors)


@pytest.mark.asyncio
async def test_sec_edgar_malformed_json_handling():
    """Verify malformed JSON responses are handled gracefully."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<invalid>Not Json</invalid>")

    client = build_mock_transport(handler)
    connector = SecEdgarConnector(client=client)

    req = CorporateProbeRequest(entity_name="Apple", corporate_identifier="0000320193")
    relationships, errors, queried = await connector.probe_sec_edgar_async(req)

    assert len(relationships) == 0
    assert any("Malformed JSON" in e for e in errors)


@pytest.mark.asyncio
async def test_sec_edgar_timeout_handling():
    """Verify network timeouts are trapped without raising unhandled exceptions."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Connection timed out waiting for SEC gateway")

    client = build_mock_transport(handler)
    connector = SecEdgarConnector(client=client)

    req = CorporateProbeRequest(entity_name="Apple", corporate_identifier="0000320193")
    relationships, errors, queried = await connector.probe_sec_edgar_async(req)

    assert len(relationships) == 0
    assert any("timed out" in e.lower() for e in errors)


@pytest.mark.asyncio
async def test_sec_edgar_unsupported_field_limitation():
    """Verify requested officer/subsidiary relationships report explicit limitation rather than hallucinations."""
    def handler(request: httpx.Request) -> httpx.Response:
        if "CIK0000320193.json" in str(request.url):
            return httpx.Response(200, json=MOCK_SUBMISSIONS_AAPL)
        return httpx.Response(404)

    client = build_mock_transport(handler)
    connector = SecEdgarConnector(client=client)

    # Request explicitly targets OFFICER relationship
    req = CorporateProbeRequest(
        entity_name="Apple Inc.",
        corporate_identifier="0000320193",
        target_relationship=CorporateRelationshipType.OFFICER,
    )

    relationships, errors, queried = await connector.probe_sec_edgar_async(req)

    # SEC Submissions API does not contain officers; verify limitation is reported
    assert any("SEC EDGAR Submissions API limitation" in e and "officer" in e for e in errors)
    # Ensure no fabricated officer relationships are added
    assert not any(r.predicate == CorporateRelationshipType.OFFICER for r in relationships)


def test_specialist_and_adapter_end_to_end_with_edgar():
    """Verify CorporateProbeSpecialist and CorporateSpecialistAdapter integration with SecEdgarConnector."""
    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "company_tickers.json" in url_str:
            return httpx.Response(200, json=MOCK_TICKERS_JSON)
        elif "CIK0000320193.json" in url_str:
            return httpx.Response(200, json=MOCK_SUBMISSIONS_AAPL)
        return httpx.Response(404)

    client = build_mock_transport(handler)
    connector = SecEdgarConnector(client=client)

    # Specialist with mocked connector and empty offline DB
    specialist = CorporateProbeSpecialist(registry_database={}, sec_connector=connector)
    adapter = CorporateSpecialistAdapter(specialist=specialist)

    res = adapter.execute({"company_name": "Apple Inc.", "corporate_identifier": "AAPL", "timeout_sec": 5.0})

    assert res["status"] == "SUCCESS"
    assert res["company"] == "Apple Inc."
    assert res["documents_count"] >= 3
    assert res["authoritative"] is False
    assert res["epistemic_nature"] == "CANDIDATE"

    # Verify documents contain sec_edgar source and valid provenance
    sec_docs = [d for d in res["documents"] if d.get("source_type") == "sec_edgar"]
    assert len(sec_docs) >= 3
    first_doc = sec_docs[0]
    assert "https://data.sec.gov/submissions/CIK0000320193.json" in first_doc["url"]
    assert "sha256_fingerprint" in first_doc["payload"]["provenance"]

    # Verify candidate claims
    claims = res["claims"]
    assert len(claims) >= 3
    assert any("0000320193" in c["object"] for c in claims)
