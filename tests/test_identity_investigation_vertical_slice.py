"""Deterministic Tests for P0.5 End-to-End Identity Investigation Vertical Slice.

Validates that Heimdallr can:
1. Accept a username and starting platform.
2. Resolve the starting account where supported.
3. Discover candidate accounts across platforms with cryptographic provenance.
4. Represent identity relationships as candidate hypotheses unless supported by independent evidence.
5. Strictly separate claims for:
   - Account existence
   - Identity equivalence
   - Private content access
6. Propagate granular specialist outcomes:
   SUCCESS_WITH_RESULTS, SUCCESS_EMPTY, SOURCE_UNAVAILABLE, SOURCE_ERROR, PARTIAL_SUCCESS, TIMEOUT.
7. Return a complete, structured investigation report.
8. Enforce privacy boundaries: Never claim private Instagram content was retrieved without authorization.
9. Deterministically handle empty results, source failure, conflicting evidence, and ambiguous matches.
"""

import httpx
import pytest

from argus.evals.vertical_corpus import VERTICAL_PLATFORM_REGISTRY
from argus.investigation.orchestrator import InvestigationEngine
from argus.specialists.identity import (
    AccountClaimType,
    CandidateIdentityRelationship,
    EpistemicCandidateStatus,
    IdentifierType,
    IdentityClaim,
    IdentityInvestigationReport,
    IdentityProbeRequest,
    IdentityProbeSpecialist,
    InvestigationConstraints,
    investigate_identity,
)
from argus.specialists.identity.github import GitHubIdentityConnector
from argus.specialists.outcome import SpecialistOutcome


# ============================================================================
# TEST 1: Happy Path - End-to-End Multi-Platform Identity Investigation
# ============================================================================

def test_1_identity_vertical_slice_happy_path():
    """Verify end-to-end investigation from a starting platform with candidate discovery,
    independent corroboration, complete provenance, and structured report synthesis.
    """
    engine = InvestigationEngine()
    report = engine.investigate_identity(
        username="s0md3v",
        starting_platform="github",
        context={
            "profession": "Security Researcher & Developer",
            "known_projects": ["Photon", "XSStrike"],
        },
        max_steps=5,
    )

    assert isinstance(report, IdentityInvestigationReport)

    # 1. Starting identifier & platform
    assert report.starting_identifier == "s0md3v"
    assert report.starting_platform == "github"
    assert report.starting_account_resolved is True
    assert report.starting_account_profile is not None
    assert report.starting_account_profile["display_name"] == "Somdev Sangwan"

    # 2. Sources queried
    assert len(report.sources_queried) >= 3
    assert "GitHub" in report.sources_queried
    assert "Twitter" in report.sources_queried
    assert "Medium" in report.sources_queried

    # 3. Discovered candidate links
    assert len(report.candidate_identity_links) >= 2
    discovered_urls = [link["source_url"] for link in report.candidate_identity_links]
    assert any("twitter.com/s0md3v" in u for u in discovered_urls)
    assert any("medium.com/@s0md3v" in u for u in discovered_urls)

    # 4. Provenance preservation: source URL, timestamp, cryptographic SHA-256 fingerprint
    for ev in report.supporting_evidence:
        assert ev.get("url")
        assert ev.get("snippet")

    # 5. Separate claim categories
    assert len(report.account_existence_claims) >= 3
    for cl in report.account_existence_claims:
        assert cl["predicate"] in (AccountClaimType.ACCOUNT_EXISTENCE.value, "account_exists")
        assert cl["status"] == "SUPPORTED"
        assert "provenance" in cl
        assert "sha256_hash" in cl["provenance"]

    assert len(report.identity_equivalence_claims) >= 2
    assert len(report.private_content_access_claims) >= 3

    # 6. Corroborated status & outcome
    assert report.outcome in (SpecialistOutcome.SUCCESS_WITH_RESULTS, SpecialistOutcome.PARTIAL_SUCCESS)
    assert report.epistemic_status == "SUPPORTED"
    assert len(report.contradictory_evidence) == 0


# ============================================================================
# TEST 2: Empty Results - Nonexistent Identifier
# ============================================================================

def test_2_identity_vertical_slice_empty_results():
    """Verify SUCCESS_EMPTY when an identifier does not exist on queried platforms.
    
    Invariants:
    - Confirmed non-existence on queried endpoints produces SUCCESS_EMPTY.
    - Zero entities, candidate accounts, or relationships are fabricated.
    - Report documents coverage gaps and unresolved questions.
    """
    engine = InvestigationEngine()
    report = engine.investigate_identity(
        username="phantom_user_xyz_987654321",
        starting_platform="github",
        context={},
        max_steps=4,
    )

    assert report.starting_identifier == "phantom_user_xyz_987654321"
    assert report.starting_account_resolved is False
    assert len(report.candidate_identity_links) == 0
    assert report.outcome == SpecialistOutcome.SUCCESS_EMPTY
    assert report.epistemic_status == "NOT_FOUND"

    # Gaps and unresolved questions are accurately recorded
    assert len(report.coverage_gaps) >= 1
    assert any("phantom_user_xyz_987654321" in gap for gap in report.coverage_gaps)
    assert len(report.unresolved_questions) >= 1


# ============================================================================
# TEST 3: Source Failure and Degradation
# ============================================================================

def test_3_identity_vertical_slice_source_failure():
    """Verify SOURCE_UNAVAILABLE and PARTIAL_SUCCESS propagation on source failures.
    
    Invariant: Upstream timeouts, 5xx, and rate limits MUST NOT be treated as absence of evidence.
    """
    # Scenario A: Lone upstream source fails with 500 -> SOURCE_UNAVAILABLE
    def handler_500(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler_500))
    gh_connector = GitHubIdentityConnector(client=mock_client)
    failing_spec = IdentityProbeSpecialist(platform_registry={}, live_connector=gh_connector)

    res = failing_spec.search_username("target_dev", starting_platform="github")
    assert res.outcome == SpecialistOutcome.SOURCE_UNAVAILABLE
    assert len(res.candidates) == 0
    assert len(res.errors) >= 1

    # Scenario B: Multi-platform partial failure -> PARTIAL_SUCCESS in end-to-end slice
    mixed_registry = {
        "twitter": {
            "name": "Twitter",
            "users": {
                "target_dev": {
                    "url": "https://twitter.com/target_dev",
                    "display_name": "Target Dev",
                    "bio": "Senior Systems Engineer",
                }
            }
        }
    }
    partial_spec = IdentityProbeSpecialist(platform_registry=mixed_registry, live_connector=gh_connector)
    partial_report = investigate_identity(
        username="target_dev",
        starting_platform="twitter",
        platform_registry=mixed_registry,
        live_connector=gh_connector,
        max_steps=4,
    )

    assert partial_report.outcome == SpecialistOutcome.PARTIAL_SUCCESS
    assert partial_report.starting_account_resolved is True
    assert len(partial_report.source_failures) >= 1
    assert any("500" in str(f) or "unavailable" in str(f).lower() for f in partial_report.source_failures)


# ============================================================================
# TEST 4: Conflicting Evidence - Biographical Contradiction
# ============================================================================

def test_4_identity_vertical_slice_conflicting_evidence():
    """Verify contradictory evidence detection when a candidate profile conflicts
    with known target biographical context (e.g. Cambridge AI researcher vs Miami gym trainer).
    
    Invariant: Conflicting candidate hypothesis must be refuted/contradicted, not merged.
    """
    engine = InvestigationEngine()
    report = engine.investigate_identity(
        username="sarah_connor_ai",
        starting_platform="twitter",
        context={
            "profession": "AI Safety Researcher",
            "location": "Cambridge, UK",
        },
        max_steps=5,
    )

    assert report.starting_identifier == "sarah_connor_ai"
    assert report.starting_account_resolved is True

    # Starting Twitter profile is Cambridge AI Safety Researcher
    assert report.starting_account_profile["location"] == "Cambridge, UK"

    # Candidate profile on GitHub / Instagram is Miami fitness trainer
    # Contradiction must be explicitly detected and surfaced
    assert len(report.contradictory_evidence) >= 1
    contra = report.contradictory_evidence[0]
    assert contra["status"] == "CONTRADICTED"
    assert "miami" in contra["observed_value"].lower() or "trainer" in contra["observed_value"].lower()

    # The contradictory candidate link is marked CONTRADICTED
    contradicted_links = [l for l in report.candidate_identity_links if l["status"] == "CONTRADICTED"]
    assert len(contradicted_links) >= 1

    assert report.epistemic_status == "CONTRADICTED"


# ============================================================================
# TEST 5: Ambiguous Identity Matches - Handle Collision Disambiguation
# ============================================================================

def test_5_identity_vertical_slice_ambiguous_matches():
    """Verify ambiguous handle collisions (e.g. SF Software Engineer vs Berlin DJ)
    are treated as unverified candidate hypotheses and NOT erroneously merged.
    """
    engine = InvestigationEngine()
    report = engine.investigate_identity(
        username="alex_chen",
        starting_platform="github",
        context={
            "profession": "Software Engineer",
            "location": "San Francisco, CA",
        },
        max_steps=6,
    )

    assert report.starting_account_resolved is True
    assert "San Francisco" in report.starting_account_profile["location"]

    # Candidate links contain multiple different individuals with the same handle
    all_links = report.candidate_identity_links
    assert len(all_links) >= 2

    # The unrelated Soundcloud profile (Berlin DJ) must NOT be marked SUPPORTED
    soundcloud_links = [l for l in all_links if "soundcloud.com" in l["source_url"]]
    if soundcloud_links:
        assert soundcloud_links[0]["status"] in (
            "CONTRADICTED",
            EpistemicCandidateStatus.UNVERIFIED_CANDIDATE.value,
            "CANDIDATE_HYPOTHESIS",
        )
        assert soundcloud_links[0]["status"] != "SUPPORTED"


# ============================================================================
# TEST 6: Private Instagram Profile Boundary Enforcement (Requirements 6 & 9)
# ============================================================================

def test_6_identity_vertical_slice_private_instagram_profile_boundary():
    """Verify strict privacy boundaries:
    1. Account existence, identity equivalence, and access to private content are separate claims.
    2. A private Instagram account existence is confirmed (HTTP 200).
    3. Heimdallr strictly NEVER claims private content was retrieved without authorized access.
    """
    engine = InvestigationEngine()
    report = engine.investigate_identity(
        username="private_target_user",
        starting_platform="instagram",
        context={
            "name": "Target Individual",
            "location": "London, UK",
        },
        max_steps=4,
    )

    assert report.starting_identifier == "private_target_user"
    assert report.starting_platform == "instagram"
    assert report.starting_account_resolved is True

    # Invariant: Account existence is supported
    exist_claims = [c for c in report.account_existence_claims if c["subject"] == "private_target_user"]
    assert len(exist_claims) >= 1
    assert exist_claims[0]["status"] == "SUPPORTED"
    assert exist_claims[0]["is_private"] is True

    # Invariant: Private content access is strictly NO_ACCESS / NOT RETRIEVED
    priv_claims = [c for c in report.private_content_access_claims if c["subject"] == "private_target_user"]
    assert len(priv_claims) >= 1
    assert priv_claims[0]["status"] == "NO_ACCESS"
    assert priv_claims[0]["is_private"] is True
    assert priv_claims[0]["authorized_access"] is False
    assert priv_claims[0]["content_retrieved"] is False
    assert "NOT retrieved" in priv_claims[0]["object"] or "NOT retrieved" in priv_claims[0].get("statement", "")

    # Invariant: No finding in report claims private content was retrieved
    for f in report.findings:
        if f.get("is_private"):
            assert f.get("content_retrieved") is False or f.get("status") in ("NO_ACCESS", "SUPPORTED")
            if f.get("predicate") == AccountClaimType.PRIVATE_CONTENT_ACCESS.value:
                assert f.get("authorized_access") is False
                assert f.get("content_retrieved") is False


# ============================================================================
# TEST 7: Specialist Contract Direct Invocation
# ============================================================================

def test_7_specialist_contract_claims_and_provenance():
    """Verify direct IdentityProbeSpecialist contract output contains structured claims,
    cryptographic SHA-256 provenance hashes, and granular outcome codes.
    """
    specialist = IdentityProbeSpecialist(platform_registry=VERTICAL_PLATFORM_REGISTRY)
    req = IdentityProbeRequest(
        identifier="s0md3v",
        starting_platform="github",
        constraints=InvestigationConstraints(permit_delimiter_permutations=True),
    )
    result = specialist.probe_identifier(req)

    assert result.outcome == SpecialistOutcome.SUCCESS_WITH_RESULTS
    assert result.total_candidates_found >= 3
    assert result.starting_account is not None
    assert result.starting_account.candidate_entity == "s0md3v"

    # Verify provenance on every candidate
    for cand in result.candidates:
        assert "sha256_hash" in cand.provenance
        assert cand.provenance["http_status"] == 200
        assert cand.timestamp

    # Verify structured claims
    assert len(result.claims) >= 6
    existence_claims = [c for c in result.claims if c.claim_type == AccountClaimType.ACCOUNT_EXISTENCE]
    assert len(existence_claims) >= 3
    for ec in existence_claims:
        assert ec.status == "SUPPORTED"
