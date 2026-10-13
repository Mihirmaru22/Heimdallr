"""Unit tests for Heimdallr Vertical 6: EmailAccountSpecialist."""

import pytest
from argus.specialists.email.models import (
    AddressValidity,
    AssociationNature,
    IdentityAssociation,
    MailboxEvidence,
    TemporalStatus,
)
from argus.specialists.email.specialist import EmailAccountSpecialist


@pytest.fixture
def specialist():
    return EmailAccountSpecialist(check_live_dns=False)


def test_capability_a_account_discovery(specialist):
    """Test Capability A: Email-to-Account discovery with observation nature typing."""
    email = "lead.dev@cryptomesh.io"
    evidence = [
        type("Doc", (), {
            "url": "https://github.com/cryptolead",
            "title": "CryptoLead (cryptolead) · GitHub",
            "text_content": f"Maintainer at CryptoMesh. Email: {email}",
            "source_type": "profile",
        })()
    ]
    corpus = type("MockCorpus", (), {"search": lambda self, q, limit=5: evidence})()

    obs = specialist.discover_accounts_for_email(email=email, corpus=corpus)
    assert len(obs) == 1
    assert obs[0].platform == "github"
    assert obs[0].observed_email == email
    assert obs[0].canonical_url == "https://github.com/cryptolead"
    assert obs[0].association_nature == AssociationNature.PROFILE_EXPLICIT_PUBLICATION


def test_capability_b_identity_to_email_discovery(specialist):
    """Test Capability B: Identity-to-Email discovery and strict INFERRED candidate tagging."""
    # 1. Direct observation
    doc = type("Doc", (), {
        "url": "https://university.edu/faculty/alovelace",
        "title": "Ada Lovelace Faculty Page",
        "text_content": "Ada Lovelace, Professor of Mathematics. Contact: ada@analytical-engine.org",
        "source_type": "academic_page",
    })()
    corpus = type("MockCorpus", (), {"search": lambda self, q, limit=5: [doc]})()

    discovered = specialist.discover_emails_for_identity(
        identifier="alovelace",
        target_name="Ada Lovelace",
        corpus=corpus,
        generate_inferred_candidates=False,
    )
    assert len(discovered) == 1
    assert discovered[0].email == "ada@analytical-engine.org"
    assert discovered[0].epistemic_status == "SUPPORTED"

    # 2. Pattern generation candidate MUST be strictly tagged INFERRED
    inferred_candidates = specialist.discover_emails_for_identity(
        identifier="Ada Lovelace",
        target_name="Ada Lovelace",
        org_domain="analytical-engine.org",
        corpus=type("EmptyCorpus", (), {"search": lambda self, q, limit=5: []})(),
        generate_inferred_candidates=True,
    )
    assert len(inferred_candidates) >= 1
    for cand in inferred_candidates:
        assert cand.epistemic_status == "INFERRED"
        assert cand.derivation_method == "PATTERN_GENERATION"
        assert cand.association_nature == AssociationNature.INFERRED_PATTERN_CANDIDATE


def test_capability_c_four_dimensional_verification(specialist):
    """Test Capability C: Four-dimensional verification separating syntax, mailbox, identity, temporal."""
    # 1. Invalid syntax
    res_invalid = specialist.verify_email_address("user..name @broken..domain")
    assert res_invalid.address_validity == AddressValidity.INVALID_SYNTAX
    assert res_invalid.mailbox_evidence == MailboxEvidence.UNVERIFIED

    # 2. Valid syntax, but mailbox existence is unverified (Valid syntax != mailbox existence)
    res_valid_domain = specialist.verify_email_address("unverified-mailbox@gmail.com")
    assert res_valid_domain.address_validity == AddressValidity.DOMAIN_VALID
    assert res_valid_domain.mailbox_evidence == MailboxEvidence.UNVERIFIED

    # 3. Authorized deliverability confirmation signal
    res_confirmed = specialist.verify_email_address(
        "authorized@tenant.org", mailbox_signal="DELIVERABILITY_CONFIRMED"
    )
    assert res_confirmed.mailbox_evidence == MailboxEvidence.DELIVERABILITY_CONFIRMED

    # 4. Identity association with multiple independent sources
    context = [
        {"passage": "Dr. Sarah Connor, lead researcher. Contact: sarah@resistance.ai", "email": "sarah@resistance.ai"},
        {"passage": "Official patent filed by Sarah Connor (sarah@resistance.ai)", "email": "sarah@resistance.ai"},
    ]
    res_ident = specialist.verify_email_address(
        "sarah@resistance.ai", target_identity="Sarah Connor", context_evidence=context
    )
    assert res_ident.identity_association == IdentityAssociation.CORROBORATED_ASSOCIATION

    # 5. Temporal classification: Historical address
    res_historical = specialist.verify_email_address(
        "john.doe@old-employer.com",
        as_of_date="2026-01-01",
        temporal_hints={"is_active": False, "end_year": 2018},
    )
    assert res_historical.temporal_status == TemporalStatus.HISTORICAL


def test_capability_d_identity_resolution_and_false_merge_prevention(specialist):
    """Test Capability D: Disambiguation preventing false identity merges."""
    # 1. Shared name between different organizations
    conflict_evidence = [
        {
            "owner": "David Miller",
            "organization": "AeroTech Defense",
            "email": "david.miller@aerotech.com",
            "passage": "David Miller, Engineer at AeroTech Defense.",
        }
    ]
    verdict_shared_name = specialist.resolve_email_identity(
        email="david.miller@aerotech.com",
        target_identity="David Miller",
        evidence_records=conflict_evidence,
        known_attributes={"organization": "BioPharma Corp"},  # Different organization!
    )
    assert verdict_shared_name.is_merged is False
    assert verdict_shared_name.association_verdict == IdentityAssociation.CONTRADICTED
    assert verdict_shared_name.rejection_reason == "SHARED_NAME"

    # 2. Recycled phone number
    recycled_evidence = [
        {
            "owner": "Alice Smith",
            "phone_recycled": True,
            "email": "alice.smith@legacy.net",
            "passage": "Phone previously assigned to previous subscriber.",
        }
    ]
    verdict_recycled = specialist.resolve_email_identity(
        email="alice.smith@legacy.net",
        target_identity="Alice Smith",
        evidence_records=recycled_evidence,
    )
    assert verdict_recycled.is_merged is False
    assert verdict_recycled.rejection_reason == "RECYCLED_PHONE"

    # 3. Verified corroboration across independent authoritative sources
    corroborating_evidence = [
        {
            "owner": "Alan Turing",
            "source_type": "OFFICIAL_REGISTRY",
            "email": "a.turing@bletchley.ac.uk",
            "passage": "Official faculty directory entry: Alan Turing (a.turing@bletchley.ac.uk)",
        },
        {
            "owner": "Alan Turing",
            "source_type": "GOVERNMENT_FILING",
            "email": "a.turing@bletchley.ac.uk",
            "passage": "State patent register: Turing, Alan, Bletchley Park.",
        },
    ]
    verdict_corroborated = specialist.resolve_email_identity(
        email="a.turing@bletchley.ac.uk",
        target_identity="Alan Turing",
        evidence_records=corroborating_evidence,
    )
    assert verdict_corroborated.is_merged is True
    assert verdict_corroborated.association_verdict == IdentityAssociation.CORROBORATED_ASSOCIATION
    assert verdict_corroborated.confidence > 0.90
