"""Focused Unit and Integration Tests for Specialist Outcome Semantics (P0.4.4).

Verifies accurate distinction of:
- SUCCESS_WITH_RESULTS
- SUCCESS_EMPTY (confirmed absence at endpoint; 404 does not imply non-existence elsewhere)
- SOURCE_UNAVAILABLE (5xx, rate limit 429/403, timeout must NOT be represented as absence of evidence)
- SOURCE_ERROR (malformed response, client errors)
- PARTIAL_SUCCESS (multi-source retrieval where at least one succeeded with results while another degraded)
- Backward compatibility of contracts and adapter status serialization
"""

import json
import httpx
import pytest

from argus.capability_registry.adapters import (
    CorporateSpecialistAdapter,
    IdentitySpecialistAdapter,
    InfrastructureSpecialistAdapter,
)
from argus.specialists.corporate.contract import (
    CorporateInvestigationConstraints,
    CorporateProbeRequest,
    CorporateProbeResult,
    CorporateRelationshipType,
    EpistemicCorporateStatus,
)
from argus.specialists.corporate.edgar import SEC_SUBMISSIONS_BASE, SEC_TICKERS_URL, SecEdgarConnector
from argus.specialists.corporate.specialist import CorporateProbeSpecialist
from argus.specialists.identity.contract import (
    EpistemicCandidateStatus,
    IdentityProbeRequest,
    IdentityProbeResult,
    InvestigationConstraints,
)
from argus.specialists.identity.github import GITHUB_USER_API_URL, GitHubIdentityConnector
from argus.specialists.identity.specialist import IdentityProbeSpecialist
from argus.specialists.infrastructure.contract import (
    EpistemicAssetStatus,
    InfrastructureInvestigationConstraints,
    InfrastructureProbeRequest,
    InfrastructureProbeResult,
)
from argus.specialists.infrastructure.crtsh import CRTSH_BASE_URL, CrtShConnector
from argus.specialists.infrastructure.specialist import InfrastructureProbeSpecialist
from argus.specialists.outcome import (
    SpecialistOutcome,
    SpecialistStatus,
    classify_error_message,
    determine_specialist_outcome,
)


# ============================================================================
# 1. CORPORATE SPECIALIST OUTCOMES
# ============================================================================

def test_corporate_success_with_results():
    """Verify SUCCESS_WITH_RESULTS when regulatory source yields candidate relationships."""
    sample_tickers = {"0": {"cik_str": 1899999, "ticker": "AUTOT", "title": "AutoTech Corporation"}}
    sample_sub = {
        "cik": "0001899999",
        "name": "AutoTech Corporation",
        "stateOfIncorporation": "DE",
        "filings": {
            "recent": {
                "accessionNumber": ["0001899999-24-000001"],
                "form": ["10-K"],
                "filingDate": ["2024-03-15"],
            }
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if "company_tickers.json" in str(request.url):
            return httpx.Response(200, json=sample_tickers)
        elif "CIK0001899999.json" in str(request.url):
            return httpx.Response(200, json=sample_sub)
        return httpx.Response(404, text="Not Found")

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    sec = SecEdgarConnector(client=client)
    specialist = CorporateProbeSpecialist(registry_database={}, sec_connector=sec)
    adapter = CorporateSpecialistAdapter(specialist=specialist)

    req = CorporateProbeRequest(entity_name="AutoTech Corporation")
    res = specialist.probe_corporate_entity(req)

    assert res.outcome == SpecialistOutcome.SUCCESS_WITH_RESULTS
    assert res.total_relationships_found >= 1
    assert any(r.subject_entity == "AutoTech Corporation" for r in res.relationships)

    # Invariant: Cryptographic provenance and candidate epistemic status retained
    for r in res.relationships:
        assert "sha256_fingerprint" in r.provenance
        assert r.epistemic_status == EpistemicCorporateStatus.CANDIDATE_FACT

    # Adapter serialization
    adapt_res = adapter.execute({"company_name": "AutoTech Corporation"})
    assert adapt_res["outcome"] == SpecialistOutcome.SUCCESS_WITH_RESULTS.value
    assert adapt_res["status"] == "SUCCESS"
    assert adapt_res["status"] == "SUCCESS_WITH_RESULTS"
    assert adapt_res["documents_count"] >= 1


def test_corporate_success_empty_confirmed_directory_miss():
    """Verify SUCCESS_EMPTY when source is reached normally but entity is absent from directory."""
    sample_tickers = {"0": {"cik_str": 1234567, "ticker": "OTHER", "title": "Other Corp"}}

    def handler(request: httpx.Request) -> httpx.Response:
        if "company_tickers.json" in str(request.url):
            return httpx.Response(200, json=sample_tickers)
        return httpx.Response(404, text="Not Found")

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    sec = SecEdgarConnector(client=client)
    specialist = CorporateProbeSpecialist(registry_database={}, sec_connector=sec)
    adapter = CorporateSpecialistAdapter(specialist=specialist)

    req = CorporateProbeRequest(entity_name="Nonexistent Phantom Corporation")
    res = specialist.probe_corporate_entity(req)

    assert res.outcome == SpecialistOutcome.SUCCESS_EMPTY
    assert len(res.relationships) == 0

    # Invariant: Confirms absence at queried endpoint, NOT global non-existence
    assert "CANDIDATES ONLY" in res.epistemic_notice

    # Adapter serialization
    adapt_res = adapter.execute({"company_name": "Nonexistent Phantom Corporation"})
    assert adapt_res["outcome"] == SpecialistOutcome.SUCCESS_EMPTY.value
    assert adapt_res["status"] == "SUCCESS"
    assert adapt_res["status"] == "SUCCESS_EMPTY"
    assert adapt_res["documents_count"] == 0


def test_corporate_source_unavailable_timeout_and_5xx():
    """Verify SOURCE_UNAVAILABLE when endpoint times out or returns HTTP 5xx.
    
    Invariant: Timeout or 5xx MUST NOT be represented as confirmed absence of evidence (SUCCESS_EMPTY).
    """
    def handler_503(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="SEC EDGAR Gateway Service Unavailable")

    transport = httpx.MockTransport(handler_503)
    client = httpx.AsyncClient(transport=transport)
    sec = SecEdgarConnector(client=client)
    specialist = CorporateProbeSpecialist(registry_database={}, sec_connector=sec)
    adapter = CorporateSpecialistAdapter(specialist=specialist)

    req = CorporateProbeRequest(entity_name="AutoTech Corporation", corporate_identifier="CIK0001899999")
    res = specialist.probe_corporate_entity(req)

    # Invariant: MUST NOT be SUCCESS_EMPTY
    assert res.outcome == SpecialistOutcome.SOURCE_UNAVAILABLE
    assert res.outcome != SpecialistOutcome.SUCCESS_EMPTY
    assert len(res.relationships) == 0
    assert any("503" in e or "unavailable" in e.lower() for e in res.errors)

    # Adapter serialization: satisfies legacy FAILED/TIMEOUT assertions
    adapt_res = adapter.execute({"company_name": "AutoTech Corporation", "corporate_identifier": "CIK0001899999"})
    assert adapt_res["outcome"] == SpecialistOutcome.SOURCE_UNAVAILABLE.value
    assert adapt_res["status"] == "FAILED"
    assert adapt_res["status"] == "TIMEOUT"
    assert adapt_res["status"] == "SOURCE_UNAVAILABLE"
    assert len(adapt_res["errors"]) > 0


def test_corporate_source_unavailable_rate_limit_429():
    """Verify SOURCE_UNAVAILABLE when SEC rate limit HTTP 429 is encountered.
    
    Invariant: Rate limits MUST NOT be represented as confirmed absence of evidence.
    """
    def handler_429(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="SEC EDGAR Rate Limit Exceeded")

    transport = httpx.MockTransport(handler_429)
    client = httpx.AsyncClient(transport=transport)
    sec = SecEdgarConnector(client=client)
    specialist = CorporateProbeSpecialist(registry_database={}, sec_connector=sec)

    req = CorporateProbeRequest(entity_name="AutoTech Corporation", corporate_identifier="0001899999")
    res = specialist.probe_corporate_entity(req)

    assert res.outcome == SpecialistOutcome.SOURCE_UNAVAILABLE
    assert res.outcome != SpecialistOutcome.SUCCESS_EMPTY
    assert any("429" in e or "rate limit" in e.lower() for e in res.errors)


def test_corporate_source_error_malformed_response():
    """Verify SOURCE_ERROR when SEC EDGAR returns malformed/corrupted payload."""
    def handler_corrupt(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<HTML>500 Internal Error Page returned with 200 OK</HTML>")

    transport = httpx.MockTransport(handler_corrupt)
    client = httpx.AsyncClient(transport=transport)
    sec = SecEdgarConnector(client=client)
    specialist = CorporateProbeSpecialist(registry_database={}, sec_connector=sec)

    req = CorporateProbeRequest(entity_name="AutoTech Corporation", corporate_identifier="0001899999")
    res = specialist.probe_corporate_entity(req)

    assert res.outcome == SpecialistOutcome.SOURCE_ERROR
    assert res.outcome != SpecialistOutcome.SUCCESS_EMPTY
    assert any("malformed" in e.lower() for e in res.errors)


def test_corporate_partial_success_multi_source():
    """Verify PARTIAL_SUCCESS when local registry succeeds but secondary live source fails."""
    local_db = {
        "autotech_corp": {
            "legal_name": "AutoTech Corporation",
            "brand_name": "AutoTech",
            "identifiers": {"STATE_CORP_ID": "SR-998877"},
            "jurisdiction": "US-DE",
            "query_live_sec": True,  # triggers secondary live SEC lookup
        }
    }

    # Live SEC endpoint returns 503
    def handler_503(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    transport = httpx.MockTransport(handler_503)
    client = httpx.AsyncClient(transport=transport)
    sec = SecEdgarConnector(client=client)
    specialist = CorporateProbeSpecialist(registry_database=local_db, sec_connector=sec)
    adapter = CorporateSpecialistAdapter(specialist=specialist)

    req = CorporateProbeRequest(entity_name="AutoTech Corporation")
    res = specialist.probe_corporate_entity(req)

    assert res.outcome == SpecialistOutcome.PARTIAL_SUCCESS
    assert len(res.relationships) > 0
    assert len(res.errors) > 0

    adapt_res = adapter.execute({"company_name": "AutoTech Corporation"})
    assert adapt_res["outcome"] == SpecialistOutcome.PARTIAL_SUCCESS.value
    assert adapt_res["status"] == "SUCCESS"
    assert adapt_res["status"] == "PARTIAL_SUCCESS"


# ============================================================================
# 2. INFRASTRUCTURE SPECIALIST OUTCOMES
# ============================================================================

def test_infrastructure_success_with_results():
    """Verify SUCCESS_WITH_RESULTS when Certificate Transparency yields candidate assets."""
    sample_ct = [
        {
            "id": 11111,
            "issuer_name": "C=US, O=Let's Encrypt",
            "common_name": "api.autotech.corp",
            "name_value": "api.autotech.corp\nportal.autotech.corp",
            "not_before": "2024-01-01T00:00:00",
            "not_after": "2027-01-01T00:00:00",
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=sample_ct)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    crtsh = CrtShConnector(client=client)
    specialist = InfrastructureProbeSpecialist(registry={}, crtsh_connector=crtsh)
    adapter = InfrastructureSpecialistAdapter(specialist=specialist)

    req = InfrastructureProbeRequest(domain="autotech.corp")
    res = specialist.enumerate_infrastructure(req)

    assert res.outcome == SpecialistOutcome.SUCCESS_WITH_RESULTS
    assert len(res.assets) >= 1
    assert any("api.autotech.corp" in a.hostname for a in res.assets)

    for asset in res.assets:
        assert asset.epistemic_status in (EpistemicAssetStatus.CANDIDATE_ASSET, EpistemicAssetStatus.EXPIRED_HISTORICAL)
        assert "sha256_fingerprint" in asset.provenance

    adapt_res = adapter.execute({"target_domain": "autotech.corp"})
    assert adapt_res["outcome"] == SpecialistOutcome.SUCCESS_WITH_RESULTS.value
    assert adapt_res["status"] == "SUCCESS"


def test_infrastructure_success_empty():
    """Verify SUCCESS_EMPTY when crt.sh responds HTTP 200 with no records discovered."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    crtsh = CrtShConnector(client=client)
    specialist = InfrastructureProbeSpecialist(registry={}, crtsh_connector=crtsh)

    req = InfrastructureProbeRequest(domain="empty-domain-with-no-certs.org")
    res = specialist.enumerate_infrastructure(req)

    assert res.outcome == SpecialistOutcome.SUCCESS_EMPTY
    assert len(res.assets) == 0


def test_infrastructure_source_unavailable_http5xx():
    """Verify SOURCE_UNAVAILABLE when crt.sh responds HTTP 502/503.
    
    Invariant: Upstream CT gateway failure MUST NOT be treated as confirmed absence of domains.
    """
    def handler_502(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="Bad Gateway on crt.sh database query")

    transport = httpx.MockTransport(handler_502)
    client = httpx.AsyncClient(transport=transport)
    crtsh = CrtShConnector(client=client)
    specialist = InfrastructureProbeSpecialist(registry={}, crtsh_connector=crtsh)
    adapter = InfrastructureSpecialistAdapter(specialist=specialist)

    req = InfrastructureProbeRequest(domain="autotech.corp")
    res = specialist.enumerate_infrastructure(req)

    assert res.outcome == SpecialistOutcome.SOURCE_UNAVAILABLE
    assert res.outcome != SpecialistOutcome.SUCCESS_EMPTY
    assert len(res.assets) == 0
    assert any("502" in e or "unavailable" in e.lower() for e in res.errors)

    adapt_res = adapter.execute({"target_domain": "autotech.corp"})
    assert adapt_res["outcome"] == SpecialistOutcome.SOURCE_UNAVAILABLE.value
    assert adapt_res["status"] == "FAILED"
    assert adapt_res["status"] == "TIMEOUT"


def test_infrastructure_partial_success_multi_source():
    """Verify PARTIAL_SUCCESS when passive DNS records exist in registry but live CT query fails."""
    local_registry = {
        "autotech.corp": {
            "query_live_ct": True,
            "records": {
                "vpn.autotech.corp": {
                    "type": "A",
                    "ip": ["198.51.100.5"],
                    "sources": ["dns_zone_transfer"],
                }
            }
        }
    }

    def handler_502(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="Bad Gateway on crt.sh")

    transport = httpx.MockTransport(handler_502)
    client = httpx.AsyncClient(transport=transport)
    crtsh = CrtShConnector(client=client)
    specialist = InfrastructureProbeSpecialist(registry=local_registry, crtsh_connector=crtsh)

    req = InfrastructureProbeRequest(domain="autotech.corp")
    res = specialist.enumerate_infrastructure(req)

    assert res.outcome == SpecialistOutcome.PARTIAL_SUCCESS
    assert len(res.assets) >= 1
    assert any("vpn.autotech.corp" in a.hostname for a in res.assets)
    assert len(res.errors) >= 1


# ============================================================================
# 3. IDENTITY SPECIALIST OUTCOMES
# ============================================================================

def test_identity_success_with_results():
    """Verify SUCCESS_WITH_RESULTS when candidate profile is retrieved with full provenance."""
    sample_gh_user = {
        "login": "octocat",
        "name": "The Octocat",
        "company": "GitHub",
        "location": "San Francisco",
        "bio": "GitHub mascot",
        "public_repos": 8,
        "created_at": "2011-01-25T18:44:36Z",
        "html_url": "https://github.com/octocat",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=sample_gh_user)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    gh = GitHubIdentityConnector(client=client)
    specialist = IdentityProbeSpecialist(platform_registry={}, live_connector=gh)
    adapter = IdentitySpecialistAdapter(specialist=specialist)

    req = IdentityProbeRequest(identifier="octocat")
    res = specialist.probe_identifier(req)

    assert res.outcome == SpecialistOutcome.SUCCESS_WITH_RESULTS
    assert len(res.candidates) >= 1
    assert any(c.candidate_entity == "octocat" for c in res.candidates)

    for c in res.candidates:
        assert c.epistemic_status == EpistemicCandidateStatus.UNVERIFIED_CANDIDATE
        assert "sha256_hash" in c.provenance

    adapt_res = adapter.execute({"identifier": "octocat"})
    assert adapt_res["outcome"] == SpecialistOutcome.SUCCESS_WITH_RESULTS.value
    assert adapt_res["status"] == "SUCCESS"


def test_identity_success_empty_confirmed_404():
    """Verify SUCCESS_EMPTY when platform returns HTTP 404 (user does not exist on this platform).
    
    Invariant: 404 on one platform MUST NOT imply the person does not exist elsewhere.
    """
    def handler_404(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    transport = httpx.MockTransport(handler_404)
    client = httpx.AsyncClient(transport=transport)
    gh = GitHubIdentityConnector(client=client)
    specialist = IdentityProbeSpecialist(platform_registry={}, live_connector=gh)
    adapter = IdentitySpecialistAdapter(specialist=specialist)

    req = IdentityProbeRequest(identifier="nonexistent_dev_998877")
    res = specialist.probe_identifier(req)

    assert res.outcome == SpecialistOutcome.SUCCESS_EMPTY
    assert len(res.candidates) == 0
    # Invariant: Specialist notice emphasizes candidates only
    assert "CANDIDATES ONLY" in res.epistemic_notice

    adapt_res = adapter.execute({"identifier": "nonexistent_dev_998877"})
    assert adapt_res["outcome"] == SpecialistOutcome.SUCCESS_EMPTY.value
    assert adapt_res["status"] == "SUCCESS"


def test_identity_source_unavailable_rate_limit_403():
    """Verify SOURCE_UNAVAILABLE when platform rate limit HTTP 403 is received.
    
    Invariant: Platform rate limits MUST NOT be represented as absence of the account.
    """
    def handler_403(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "API rate limit exceeded"})

    transport = httpx.MockTransport(handler_403)
    client = httpx.AsyncClient(transport=transport)
    gh = GitHubIdentityConnector(client=client)
    specialist = IdentityProbeSpecialist(platform_registry={}, live_connector=gh)
    adapter = IdentitySpecialistAdapter(specialist=specialist)

    req = IdentityProbeRequest(identifier="target_user")
    res = specialist.probe_identifier(req)

    assert res.outcome == SpecialistOutcome.SOURCE_UNAVAILABLE
    assert res.outcome != SpecialistOutcome.SUCCESS_EMPTY
    assert len(res.candidates) == 0
    assert any("rate limit" in e.lower() for e in res.errors)

    adapt_res = adapter.execute({"identifier": "target_user"})
    assert adapt_res["outcome"] == SpecialistOutcome.SOURCE_UNAVAILABLE.value
    assert adapt_res["status"] == "FAILED"
    assert adapt_res["status"] == "TIMEOUT"


def test_identity_partial_success_multi_platform():
    """Verify PARTIAL_SUCCESS when one platform succeeds with results while another fails."""
    local_registry = {
        "twitter": {
            "name": "Twitter",
            "users": {
                "dev_alice": {
                    "display_name": "Alice Developer",
                    "bio": "Rust and Python Systems Engineer",
                    "url": "https://twitter.com/dev_alice",
                }
            }
        }
    }

    # Live GitHub platform is down (500)
    def handler_500(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    transport = httpx.MockTransport(handler_500)
    client = httpx.AsyncClient(transport=transport)
    gh = GitHubIdentityConnector(client=client)
    specialist = IdentityProbeSpecialist(platform_registry=local_registry, live_connector=gh)
    adapter = IdentitySpecialistAdapter(specialist=specialist)

    req = IdentityProbeRequest(identifier="dev_alice")
    res = specialist.probe_identifier(req)

    assert res.outcome == SpecialistOutcome.PARTIAL_SUCCESS
    assert len(res.candidates) >= 1
    assert any(c.source_platform == "Twitter" for c in res.candidates)
    assert any("500" in e or "unavailable" in e.lower() for e in res.errors)

    adapt_res = adapter.execute({"identifier": "dev_alice"})
    assert adapt_res["outcome"] == SpecialistOutcome.PARTIAL_SUCCESS.value
    assert adapt_res["status"] == "SUCCESS"
    assert adapt_res["status"] == "PARTIAL_SUCCESS"


# ============================================================================
# 4. ADAPTER SERIALIZATION AND STATUS BACKWARD COMPATIBILITY
# ============================================================================

def test_specialist_status_legacy_equality_matrix():
    """Verify SpecialistStatus satisfies backward compatibility across all legacy consumers."""
    # 1. Success outcomes evaluate True against 'SUCCESS'
    s_results = SpecialistStatus("SUCCESS_WITH_RESULTS")
    assert s_results == "SUCCESS_WITH_RESULTS"
    assert s_results == "SUCCESS"
    assert "SUCCESS" == s_results

    s_empty = SpecialistStatus("SUCCESS_EMPTY")
    assert s_empty == "SUCCESS_EMPTY"
    assert s_empty == "SUCCESS"
    assert "SUCCESS" == s_empty

    s_partial = SpecialistStatus("PARTIAL_SUCCESS")
    assert s_partial == "PARTIAL_SUCCESS"
    assert s_partial == "SUCCESS"
    assert "SUCCESS" == s_partial

    # 2. Unavailable and Timeout outcomes evaluate True against 'FAILED' and 'TIMEOUT'
    s_unavail = SpecialistStatus("SOURCE_UNAVAILABLE")
    assert s_unavail == "SOURCE_UNAVAILABLE"
    assert s_unavail == "FAILED"
    assert s_unavail == "TIMEOUT"
    assert "FAILED" == s_unavail

    s_timeout = SpecialistStatus("TIMEOUT")
    assert s_timeout == "TIMEOUT"
    assert s_timeout == "FAILED"

    # 3. Source error evaluates True against 'FAILED'
    s_err = SpecialistStatus("SOURCE_ERROR")
    assert s_err == "SOURCE_ERROR"
    assert s_err == "FAILED"
    assert s_err != "SUCCESS"


def test_adapter_json_serialization_roundtrip():
    """Verify all outcomes and statuses serialize cleanly to standard JSON."""
    adapter_payload = {
        "status": SpecialistStatus("SUCCESS_WITH_RESULTS"),
        "outcome": SpecialistOutcome.SUCCESS_WITH_RESULTS.value,
        "documents": [
            {
                "doc_id": "test_1",
                "is_authoritative": False,
                "epistemic_status": "CANDIDATE_FACT",
                "payload": {"provenance": {"sha256": "abc1234"}},
            }
        ],
        "errors": ["SEC EDGAR Submissions API limitation: Endpoint provides identity only."],
    }

    raw_json = json.dumps(adapter_payload)
    parsed = json.loads(raw_json)

    assert parsed["status"] == "SUCCESS_WITH_RESULTS"
    assert parsed["outcome"] == "SUCCESS_WITH_RESULTS"
    assert parsed["documents"][0]["epistemic_status"] == "CANDIDATE_FACT"
    assert parsed["documents"][0]["is_authoritative"] is False
    assert len(parsed["errors"]) == 1
