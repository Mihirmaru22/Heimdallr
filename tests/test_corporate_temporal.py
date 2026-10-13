"""Temporal corporate relationship and filing reasoning tests for Vertical 3."""

import pytest
from argus.specialists.corporate.contract import (
    CorporateProbeRequest,
    CorporateRelationshipType,
    EpistemicCorporateStatus,
    TemporalCorporateStatus,
)
from argus.specialists.corporate.specialist import CorporateProbeSpecialist
from argus.evals.corporate_corpus import CORPORATE_REGISTRY_DATABASE


def test_officer_appointment_and_resignation_dates():
    """Verify distinct appointment and resignation dates are preserved."""
    specialist = CorporateProbeSpecialist(registry_database=CORPORATE_REGISTRY_DATABASE)
    req = CorporateProbeRequest(entity_name="AutoTech Corporation")
    res = specialist.probe_corporate_entity(req)

    # 1. Marcus Chen: Former CFO resigned on 2021-03-14
    marcus_matches = [
        r for r in res.relationships
        if r.predicate == CorporateRelationshipType.OFFICER and r.object_entity == "Marcus Chen"
    ]
    assert len(marcus_matches) == 1
    marcus = marcus_matches[0]
    assert marcus.temporal_status == TemporalCorporateStatus.HISTORICAL_RESIGNED
    assert marcus.effective_date == "2018-05-01"
    assert marcus.resignation_date == "2021-03-14"

    # 2. Elena Rostova: Appointed CFO on 2021-03-15
    elena_matches = [
        r for r in res.relationships
        if r.predicate == CorporateRelationshipType.OFFICER and r.object_entity == "Elena Rostova"
    ]
    assert len(elena_matches) == 1
    elena = elena_matches[0]
    assert elena.temporal_status == TemporalCorporateStatus.CURRENT_ACTIVE
    assert elena.effective_date == "2021-03-15"
    assert elena.resignation_date is None


def test_acquisition_vs_divestiture_temporal_status():
    """Verify acquired entity vs divested entity are distinguished temporally."""
    specialist = CorporateProbeSpecialist(registry_database=CORPORATE_REGISTRY_DATABASE)
    req = CorporateProbeRequest(entity_name="AutoTech Corporation")
    res = specialist.probe_corporate_entity(req)

    # EcoDrive Sensors Inc: Acquired 2022-04-15 (currently active subsidiary)
    acq_matches = [
        r for r in res.relationships
        if r.predicate == CorporateRelationshipType.ACQUIRED_SUBSIDIARY
    ]
    assert len(acq_matches) == 1
    assert acq_matches[0].object_entity == "EcoDrive Sensors Inc"
    assert acq_matches[0].effective_date == "2022-04-15"
    assert acq_matches[0].temporal_status == TemporalCorporateStatus.CURRENT_ACTIVE

    # Legacy Sensor Systems Inc: Divested 2023-08-01 (historical, former subsidiary)
    div_matches = [
        r for r in res.relationships
        if r.predicate == CorporateRelationshipType.DIVESTED_SUBSIDIARY
    ]
    assert len(div_matches) == 1
    assert div_matches[0].object_entity == "Legacy Sensor Systems Inc"
    assert div_matches[0].effective_date == "2023-08-01"
    assert div_matches[0].temporal_status == TemporalCorporateStatus.HISTORICAL_DIVESTED


def test_amended_filing_restatement_precedence():
    """Verify that amended 10-K/A marks original 10-K as superseded."""
    specialist = CorporateProbeSpecialist(registry_database=CORPORATE_REGISTRY_DATABASE)
    req = CorporateProbeRequest(entity_name="AutoTech Corporation")
    res = specialist.probe_corporate_entity(req)

    superseded_filings = [
        r for r in res.relationships
        if r.temporal_status == TemporalCorporateStatus.AMENDED_SUPERSEDED
        or r.epistemic_status == EpistemicCorporateStatus.AMENDED_SUPERSEDED
    ]
    assert len(superseded_filings) == 1
    orig_filing = superseded_filings[0]
    assert orig_filing.object_entity == "0001899999-24-000010"
    assert orig_filing.filing_date == "2024-02-15"
