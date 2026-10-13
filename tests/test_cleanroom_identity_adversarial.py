"""Adversarial Safety Test Suite for Clean-Room Identity Specialist.

Verifies that IdentityProbeSpecialist and its integration with Argus Verifier
strictly prefer UNKNOWN / NOT_FOUND / UNVERIFIED / CONTRADICTED over unjustified
identity merges across 11 adversarial vulnerability vectors:

1. Same username used by multiple people
2. Common usernames
3. Reused email patterns
4. Partial identifiers
5. Conflicting profile information
6. Stale profiles
7. Deleted / suspended profiles
8. Duplicate accounts / clones
9. Misleading profile claims (impersonation / satire)
10. Weak evidence (empty bio, zero metadata)
11. Single-source identity claims
"""

import pytest
from argus.specialists.identity.contract import (
    CandidateIdentityRelationship,
    EpistemicCandidateStatus,
    IdentifierType,
    IdentityProbeRequest,
    InvestigationConstraints,
)
from argus.specialists.identity.specialist import IdentityProbeSpecialist


@pytest.fixture
def adversarial_registry():
    """Platform registry configured with challenging adversarial identity edge cases."""
    return {
        "github": {
            "name": "GitHub",
            "url_template": "https://github.com/{username}",
            "e_string": "profile_loaded",
            "users": {
                "alex": {
                    "url": "https://github.com/alex",
                    "display_name": "Alex Mercer",
                    "bio": "Systems architect in Seattle, WA",
                    "location": "Seattle, WA",
                },
                "admin": {
                    "url": "https://github.com/admin",
                    "display_name": "System Administrator",
                    "bio": "Internal devops",
                    "location": "Unknown",
                },
                "stale_user_2011": {
                    "url": "https://github.com/stale_user_2011",
                    "display_name": "Old Account",
                    "bio": "Abandoned project from 2011",
                    "location": "Chicago, IL",
                },
                "impersonator_satire": {
                    "url": "https://github.com/impersonator_satire",
                    "display_name": "Official White House",
                    "bio": "Parody account - not affiliated with US Government",
                    "location": "Washington, DC",
                },
                "empty_ghost": {
                    "url": "https://github.com/empty_ghost",
                    "display_name": "",
                    "bio": "",
                    "location": "",
                },
                "sarah_connor": {
                    "url": "https://github.com/sarah_connor",
                    "display_name": "Sarah Connor",
                    "bio": "Fitness instructor and gym trainer in Miami, FL",
                    "location": "Miami, FL",
                },
                "solo_researcher": {
                    "url": "https://github.com/solo_researcher",
                    "display_name": "Dr. Solo",
                    "bio": "Independent cryptographer",
                    "location": "Reykjavik, Iceland",
                },
            },
        },
        "soundcloud": {
            "name": "Soundcloud",
            "url_template": "https://soundcloud.com/{username}",
            "e_string": "profile_loaded",
            "users": {
                "alex": {
                    "url": "https://soundcloud.com/alex",
                    "display_name": "DJ Alex",
                    "bio": "House and techno producer in Berlin, Germany",
                    "location": "Berlin, Germany",
                },
                "sarah_connor": {
                    "url": "https://soundcloud.com/sarah_connor",
                    "display_name": "Sarah Connor Vocalist",
                    "bio": "Pop singer in Los Angeles",
                    "location": "Los Angeles, CA",
                },
            },
        },
        "twitter": {
            "name": "Twitter",
            "url_template": "https://twitter.com/{username}",
            "e_string": "profile_loaded",
            "users": {
                "sarah_connor": {
                    "url": "https://twitter.com/sarah_connor",
                    "display_name": "Dr. Sarah Connor",
                    "bio": "AI Safety and Alignment Researcher in Cambridge, UK",
                    "location": "Cambridge, UK",
                },
                "alex_clone_1": {
                    "url": "https://twitter.com/alex_clone_1",
                    "display_name": "Alex Mercer Clone",
                    "bio": "Fan account",
                    "location": "Seattle, WA",
                },
            },
        },
    }


# -----------------------------------------------------------------------------
# Test 1: Same username used by multiple people across platforms
# -----------------------------------------------------------------------------
def test_adversarial_same_username_multiple_people(adversarial_registry):
    specialist = IdentityProbeSpecialist(platform_registry=adversarial_registry)
    req = IdentityProbeRequest(
        identifier="alex",
        identifier_type=IdentifierType.USERNAME,
        target_entity_context={"profession": "Systems Architect", "location": "Seattle, WA"},
    )
    result = specialist.probe_identifier(req)
    
    # Must find 2 candidates (GitHub systems architect and Soundcloud DJ)
    assert len(result.candidates) == 2
    # Crucial Invariant: The specialist NEVER asserts identity equivalence
    for cand in result.candidates:
        assert cand.epistemic_status == EpistemicCandidateStatus.UNVERIFIED_CANDIDATE
        assert "SAME_PERSON" not in cand.epistemic_status.value


# -----------------------------------------------------------------------------
# Test 2: Common / generic usernames (e.g., 'admin', 'alex')
# -----------------------------------------------------------------------------
def test_adversarial_common_usernames(adversarial_registry):
    specialist = IdentityProbeSpecialist(platform_registry=adversarial_registry)
    req = IdentityProbeRequest(
        identifier="admin",
        identifier_type=IdentifierType.USERNAME,
    )
    result = specialist.probe_identifier(req)
    assert len(result.candidates) >= 1
    # Notice that common handles must not be auto-verified
    assert all(c.epistemic_status == EpistemicCandidateStatus.UNVERIFIED_CANDIDATE for c in result.candidates)


# -----------------------------------------------------------------------------
# Test 3: Reused email / generic patterns (e.g. role-based addresses)
# -----------------------------------------------------------------------------
def test_adversarial_reused_generic_email(adversarial_registry):
    specialist = IdentityProbeSpecialist(platform_registry=adversarial_registry)
    req = IdentityProbeRequest(
        identifier="contact@company.com",
        identifier_type=IdentifierType.EMAIL,
    )
    result = specialist.probe_identifier(req)
    # Generic corporate address should not resolve to personal target entity
    assert len(result.candidates) == 0 or all(c.confidence <= 0.5 for c in result.candidates)


# -----------------------------------------------------------------------------
# Test 4: Partial identifiers (prefix matches must not falsely match)
# -----------------------------------------------------------------------------
def test_adversarial_partial_identifier_rejected(adversarial_registry):
    specialist = IdentityProbeSpecialist(platform_registry=adversarial_registry)
    req = IdentityProbeRequest(
        identifier="ale",  # Prefix of 'alex'
        identifier_type=IdentifierType.USERNAME,
    )
    result = specialist.probe_identifier(req)
    # Exact handle match must not match 'alex'
    matched_urls = [c.source_url for c in result.candidates]
    assert "https://github.com/alex" not in matched_urls


# -----------------------------------------------------------------------------
# Test 5: Conflicting profile information (e.g. AI researcher vs Miami gym trainer)
# -----------------------------------------------------------------------------
def test_adversarial_conflicting_profile_information(adversarial_registry):
    specialist = IdentityProbeSpecialist(platform_registry=adversarial_registry)
    req = IdentityProbeRequest(
        identifier="sarah_connor",
        identifier_type=IdentifierType.USERNAME,
        target_entity_context={"profession": "AI Safety", "location": "Cambridge, UK"},
    )
    result = specialist.probe_identifier(req)
    assert len(result.candidates) == 3
    
    # Candidate outputs must preserve the conflicting observations without conflation
    github_cand = next(c for c in result.candidates if c.source_platform == "GitHub")
    assert "Miami, FL" in github_cand.supporting_observation
    assert "Fitness instructor" in github_cand.supporting_observation
    assert github_cand.epistemic_status == EpistemicCandidateStatus.UNVERIFIED_CANDIDATE


# -----------------------------------------------------------------------------
# Test 6: Stale / Abandoned profiles (temporal provenance)
# -----------------------------------------------------------------------------
def test_adversarial_stale_profile_provenance(adversarial_registry):
    specialist = IdentityProbeSpecialist(platform_registry=adversarial_registry)
    req = IdentityProbeRequest(
        identifier="stale_user_2011",
        identifier_type=IdentifierType.USERNAME,
    )
    result = specialist.probe_identifier(req)
    assert len(result.candidates) == 1
    cand = result.candidates[0]
    assert "provenance" in cand.model_dump()
    assert "checked_timestamp" in cand.provenance
    assert cand.epistemic_status == EpistemicCandidateStatus.UNVERIFIED_CANDIDATE


# -----------------------------------------------------------------------------
# Test 7: Deleted / suspended / phantom profiles (HTTP 404 behavior)
# -----------------------------------------------------------------------------
def test_adversarial_deleted_or_nonexistent_profile(adversarial_registry):
    specialist = IdentityProbeSpecialist(platform_registry=adversarial_registry)
    req = IdentityProbeRequest(
        identifier="deleted_account_404_not_found",
        identifier_type=IdentifierType.USERNAME,
    )
    result = specialist.probe_identifier(req)
    assert len(result.candidates) == 0
    assert result.total_candidates_found == 0


# -----------------------------------------------------------------------------
# Test 8: Duplicate / clone accounts on same or different platforms
# -----------------------------------------------------------------------------
def test_adversarial_duplicate_and_clone_accounts(adversarial_registry):
    specialist = IdentityProbeSpecialist(platform_registry=adversarial_registry)
    req = IdentityProbeRequest(
        identifier="alex_clone_1",
        identifier_type=IdentifierType.USERNAME,
    )
    result = specialist.probe_identifier(req)
    assert len(result.candidates) == 1
    assert "Clone" in result.candidates[0].supporting_observation
    assert result.candidates[0].epistemic_status == EpistemicCandidateStatus.UNVERIFIED_CANDIDATE


# -----------------------------------------------------------------------------
# Test 9: Misleading profile claims (impersonation / satire)
# -----------------------------------------------------------------------------
def test_adversarial_misleading_profile_claims(adversarial_registry):
    specialist = IdentityProbeSpecialist(platform_registry=adversarial_registry)
    req = IdentityProbeRequest(
        identifier="impersonator_satire",
        identifier_type=IdentifierType.USERNAME,
    )
    result = specialist.probe_identifier(req)
    assert len(result.candidates) == 1
    cand = result.candidates[0]
    # Raw observation is captured faithfully without making true entity endorsement
    assert "Parody account" in cand.supporting_observation
    assert cand.epistemic_status == EpistemicCandidateStatus.UNVERIFIED_CANDIDATE


# -----------------------------------------------------------------------------
# Test 10: Weak evidence (empty bio, zero metadata)
# -----------------------------------------------------------------------------
def test_adversarial_weak_evidence_empty_bio(adversarial_registry):
    specialist = IdentityProbeSpecialist(platform_registry=adversarial_registry)
    req = IdentityProbeRequest(
        identifier="empty_ghost",
        identifier_type=IdentifierType.USERNAME,
    )
    result = specialist.probe_identifier(req)
    assert len(result.candidates) == 1
    cand = result.candidates[0]
    # Confidence is penalized for missing biographical signals
    assert cand.confidence <= 0.50
    assert cand.epistemic_status == EpistemicCandidateStatus.UNVERIFIED_CANDIDATE


# -----------------------------------------------------------------------------
# Test 11: Single-source identity claims (requires corroboration)
# -----------------------------------------------------------------------------
def test_adversarial_single_source_identity(adversarial_registry):
    specialist = IdentityProbeSpecialist(platform_registry=adversarial_registry)
    req = IdentityProbeRequest(
        identifier="solo_researcher",
        identifier_type=IdentifierType.USERNAME,
    )
    result = specialist.probe_identifier(req)
    # Only exists on GitHub
    assert len(result.candidates) == 1
    assert result.candidates[0].source_platform == "GitHub"
    # Never upgraded to confirmed identity without corroboration
    assert result.candidates[0].epistemic_status == EpistemicCandidateStatus.UNVERIFIED_CANDIDATE
