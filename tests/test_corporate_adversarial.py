"""Adversarial stress tests for Heimdallr Vertical 3: Corporate Intelligence."""

import pytest
from argus.specialists.corporate.contract import (
    CorporateProbeRequest,
    CorporateRelationshipType,
    EpistemicCorporateStatus,
    TemporalCorporateStatus,
)
from argus.specialists.corporate.specialist import CorporateProbeSpecialist
from argus.evals.corporate_corpus import CORPORATE_REGISTRY_DATABASE


@pytest.fixture
def specialist():
    return CorporateProbeSpecialist(registry_database=CORPORATE_REGISTRY_DATABASE)


def test_adv_01_similar_legal_entity_names(specialist):
    """Vector 1: Disambiguate parent AutoTech Corporation vs UK subsidiary AutoTech UK Limited."""
    req_us = CorporateProbeRequest(entity_name="AutoTech Corporation", jurisdiction="US-DE")
    res_us = specialist.probe_corporate_entity(req_us)
    assert any(r.subject_entity == "AutoTech Corporation" for r in res_us.relationships)

    req_uk = CorporateProbeRequest(entity_name="AutoTech UK Limited", jurisdiction="GB")
    res_uk = specialist.probe_corporate_entity(req_uk)
    assert any(r.subject_entity == "AutoTech UK Limited" for r in res_uk.relationships)


def test_adv_02_parent_subsidiary_confusion(specialist):
    """Vector 2: AutoTech Global Holdings Inc is parent, AutoTech Corporation is subsidiary (not vice-versa)."""
    req = CorporateProbeRequest(entity_name="AutoTech Corporation")
    res = specialist.probe_corporate_entity(req)
    parent_rels = [
        r for r in res.relationships
        if r.predicate == CorporateRelationshipType.PARENT_COMPANY
    ]
    assert len(parent_rels) == 1
    assert parent_rels[0].subject_entity == "AutoTech Global Holdings Inc"
    assert parent_rels[0].object_entity == "AutoTech Corporation"


def test_adv_03_brand_vs_legal_entity(specialist):
    """Vector 3: Commercial brand 'AutoTech' must not be asserted as legal corporate registrant."""
    req = CorporateProbeRequest(entity_name="AutoTech")
    res = specialist.probe_corporate_entity(req)
    brand_rels = [
        r for r in res.relationships
        if r.predicate == CorporateRelationshipType.BRAND_NAME
    ]
    assert len(brand_rels) == 1
    assert brand_rels[0].subject_entity == "AutoTech Corporation"
    assert brand_rels[0].object_entity == "AutoTech"


def test_adv_04_officer_vs_owner_confusion(specialist):
    """Vector 4: CEO Somdev Vance is corporate officer, NOT registered beneficial owner."""
    req = CorporateProbeRequest(entity_name="AutoTech Corporation")
    res = specialist.probe_corporate_entity(req)
    # Somdev Vance is officer
    vance_officer = [
        r for r in res.relationships
        if r.object_entity == "Somdev Vance" and r.predicate == CorporateRelationshipType.OFFICER
    ]
    assert len(vance_officer) >= 1

    # Somdev Vance is NOT listed as beneficial owner
    vance_owner = [
        r for r in res.relationships
        if r.object_entity == "Somdev Vance" and r.predicate == CorporateRelationshipType.BENEFICIAL_OWNER
    ]
    assert len(vance_owner) == 0


def test_adv_05_registered_agent_confusion(specialist):
    """Vector 5: Corporation Service Company is Registered Agent, NEVER officer or owner."""
    req = CorporateProbeRequest(entity_name="AutoTech Corporation")
    res = specialist.probe_corporate_entity(req)
    csc_rels = [
        r for r in res.relationships
        if "Corporation Service Company" in r.object_entity
    ]
    assert len(csc_rels) >= 1
    for r in csc_rels:
        assert r.predicate == CorporateRelationshipType.REGISTERED_AGENT
        assert r.epistemic_status == EpistemicCorporateStatus.REGISTERED_AGENT_ONLY
        assert r.predicate != CorporateRelationshipType.OFFICER
        assert r.predicate != CorporateRelationshipType.BENEFICIAL_OWNER


def test_adv_06_historical_officer_confusion(specialist):
    """Vector 6: Former officer Marcus Chen must not be asserted as current active officer."""
    req = CorporateProbeRequest(entity_name="AutoTech Corporation")
    res = specialist.probe_corporate_entity(req)
    marcus_rels = [
        r for r in res.relationships
        if r.object_entity == "Marcus Chen"
    ]
    assert len(marcus_rels) == 1
    assert marcus_rels[0].temporal_status == TemporalCorporateStatus.HISTORICAL_RESIGNED
    assert marcus_rels[0].resignation_date is not None


def test_adv_07_acquired_company_status(specialist):
    """Vector 7: Acquired company retains historical acquisition date."""
    req = CorporateProbeRequest(entity_name="AutoTech Corporation")
    res = specialist.probe_corporate_entity(req)
    ecodrive = [
        r for r in res.relationships
        if r.object_entity == "EcoDrive Sensors Inc"
    ]
    assert len(ecodrive) == 1
    assert ecodrive[0].predicate == CorporateRelationshipType.ACQUIRED_SUBSIDIARY
    assert ecodrive[0].effective_date == "2022-04-15"


def test_adv_08_divested_company_status(specialist):
    """Vector 8: Divested company marked as HISTORICAL_DIVESTED, not active subsidiary."""
    req = CorporateProbeRequest(entity_name="AutoTech Corporation")
    res = specialist.probe_corporate_entity(req)
    legacy = [
        r for r in res.relationships
        if r.object_entity == "Legacy Sensor Systems Inc"
    ]
    assert len(legacy) == 1
    assert legacy[0].predicate == CorporateRelationshipType.DIVESTED_SUBSIDIARY
    assert legacy[0].temporal_status == TemporalCorporateStatus.HISTORICAL_DIVESTED


def test_adv_09_amended_filing_precedence(specialist):
    """Vector 9: Original filing marked AMENDED_SUPERSEDED upon restatement."""
    req = CorporateProbeRequest(entity_name="AutoTech Corporation")
    res = specialist.probe_corporate_entity(req)
    orig_filing = [
        r for r in res.relationships
        if r.object_entity == "0001899999-24-000010"
    ]
    assert len(orig_filing) == 1
    assert orig_filing[0].epistemic_status == EpistemicCorporateStatus.AMENDED_SUPERSEDED


def test_adv_10_duplicate_filing_deduplication(specialist):
    """Vector 10: Repeated queries produce stable deduplicated identifiers."""
    req = CorporateProbeRequest(entity_name="AutoTech Corporation")
    res1 = specialist.probe_corporate_entity(req)
    res2 = specialist.probe_corporate_entity(req)
    assert len(res1.relationships) == len(res2.relationships)


def test_adv_11_cross_jurisdiction_collision(specialist):
    """Vector 11: AutoTech US (US-DE) and AutoTech UK (GB) keep distinct jurisdictions."""
    req = CorporateProbeRequest(entity_name="AutoTech Corporation")
    res = specialist.probe_corporate_entity(req)
    uk_subs = [
        r for r in res.relationships
        if r.object_entity == "AutoTech UK Limited"
    ]
    assert len(uk_subs) == 1
    assert uk_subs[0].jurisdiction == "GB"


def test_adv_12_shell_company_probe(specialist):
    """Vector 12: Unlisted shell companies return no fictitious officers or revenue."""
    req = CorporateProbeRequest(entity_name="Cayman Shell Vehicle 001 Ltd")
    res = specialist.probe_corporate_entity(req)
    assert len(res.relationships) == 0


def test_adv_13_common_personal_names(specialist):
    """Vector 13: Names like 'Somdev Vance' are qualified with company jurisdiction and role."""
    req = CorporateProbeRequest(entity_name="AutoTech Corporation")
    res = specialist.probe_corporate_entity(req)
    vance_rels = [r for r in res.relationships if r.object_entity == "Somdev Vance"]
    for r in vance_rels:
        assert r.jurisdiction in ("US-DE", "GB")
        assert r.predicate == CorporateRelationshipType.OFFICER


def test_adv_14_filing_reference_to_third_party(specialist):
    """Vector 14: Filing auditor or transfer agent is not assigned corporate ownership."""
    req = CorporateProbeRequest(entity_name="AutoTech Corporation")
    res = specialist.probe_corporate_entity(req)
    owners = [
        r for r in res.relationships
        if r.predicate == CorporateRelationshipType.BENEFICIAL_OWNER
    ]
    for o in owners:
        assert o.object_entity != "Ernst & Young LLP"
        assert o.object_entity != "Computershare"


def test_adv_15_missing_ownership_data(specialist):
    """Vector 15: Non-existent entities return UNKNOWN/empty without manufacturing data."""
    req = CorporateProbeRequest(entity_name="Phantom Capital Partners LLC 987654321")
    res = specialist.probe_corporate_entity(req)
    assert len(res.relationships) == 0
    assert res.total_relationships_found == 0
