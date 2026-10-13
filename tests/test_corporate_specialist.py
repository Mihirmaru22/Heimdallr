"""Unit tests for Heimdallr Vertical 3: Corporate Financial & Registry Specialist."""

import pytest
from argus.specialists.corporate.contract import (
    CandidateCorporateRelationship,
    CorporateIdentifierType,
    CorporateInvestigationConstraints,
    CorporateProbeRequest,
    CorporateProbeResult,
    CorporateRelationshipType,
    EpistemicCorporateStatus,
    TemporalCorporateStatus,
)
from argus.specialists.corporate.specialist import CorporateProbeSpecialist
from argus.evals.corporate_corpus import CORPORATE_REGISTRY_DATABASE


def test_contract_models_and_enums():
    """Verify pydantic models, relationship types, and provenance validation."""
    prov = {
        "source_registry": "SEC_EDGAR",
        "jurisdiction": "US-SEC",
        "filing_identifier": "0001899999-24-000010",
        "filing_date": "2024-02-15",
        "source_url": "https://www.sec.gov/edgar/data/0001899999/000189999924000010/autotech-20231231.htm",
        "raw_observation": "AutoTech Corporation 10-K Annual Report",
        "extraction_method": "sec_edgar_json_api",
    }
    assert prov["source_registry"] == "SEC_EDGAR"
    assert prov["filing_identifier"] == "0001899999-24-000010"

    rel = CandidateCorporateRelationship(
        relationship_id="rel_test_01",
        subject_entity="AutoTech Corporation",
        predicate=CorporateRelationshipType.OFFICER,
        object_entity="Somdev Vance",
        jurisdiction="US-DE",
        source_registry="SEC_EDGAR",
        source_url="https://www.sec.gov/edgar/data/0001899999/000189999924000010/autotech-20231231.htm",
        observation="Officer Somdev Vance listed as CEO",
        extraction_method="sec_edgar_json_api",
        provenance=prov,
        temporal_status=TemporalCorporateStatus.CURRENT_ACTIVE,
        effective_date="2020-01-10",
        filing_date="2024-02-15",
        confidence=0.99,
        epistemic_status=EpistemicCorporateStatus.CANDIDATE_FACT,
    )
    assert rel.subject_entity == "AutoTech Corporation"
    assert rel.predicate == CorporateRelationshipType.OFFICER
    assert rel.object_entity == "Somdev Vance"
    assert rel.confidence == 0.99
    assert rel.epistemic_status == EpistemicCorporateStatus.CANDIDATE_FACT


def test_specialist_initialization_and_probing():
    """Verify specialist queries simulated database across multiple registries."""
    specialist = CorporateProbeSpecialist(registry_database=CORPORATE_REGISTRY_DATABASE)
    req = CorporateProbeRequest(
        entity_name="AutoTech Corporation",
        corporate_identifier="0001899999",
        identifier_type=CorporateIdentifierType.CIK,
        jurisdiction="US-DE",
    )
    result: CorporateProbeResult = specialist.probe_corporate_entity(req)

    assert result.target_entity == "AutoTech Corporation"
    assert result.total_registries_queried >= 3
    assert len(result.relationships) > 0

    # Ensure CIK identifier was found
    filing_entities = [
        r for r in result.relationships
        if r.predicate == CorporateRelationshipType.FILING_ENTITY and "CIK" in r.object_entity
    ]
    assert len(filing_entities) == 1
    assert "0001899999" in filing_entities[0].object_entity

    # Ensure LEI identifier was found
    lei_entities = [
        r for r in result.relationships
        if r.predicate == CorporateRelationshipType.FILING_ENTITY and "LEI" in r.object_entity
    ]
    assert len(lei_entities) == 1
    assert "5493001KJTIIGC8Y1R12" in lei_entities[0].object_entity


def test_specialist_non_existent_entity():
    """Verify specialist behavior when querying completely nonexistent entity."""
    specialist = CorporateProbeSpecialist(registry_database=CORPORATE_REGISTRY_DATABASE)
    req = CorporateProbeRequest(
        entity_name="Totally NonExistent Enterprise 999XYZ",
        constraints=CorporateInvestigationConstraints(),
    )
    result = specialist.probe_corporate_entity(req)

    assert result.target_entity == "Totally NonExistent Enterprise 999XYZ"
    assert len(result.relationships) == 0
    assert result.total_relationships_found == 0
