"""Unit tests for IndependentSemanticAuditor.

Verifies correct discrimination of:
1. ENTAILED claims
2. CONTRADICTED claims
3. INSUFFICIENTLY_SUPPORTED claims
4. IRRELEVANT_EVIDENCE
5. PARTIALLY_SUPPORTED_COMPOUND claims
"""

import pytest

from argus.investigation.benchmark.v2.semantic_auditor import (
    IndependentSemanticAuditor,
    SemanticSupportStatus,
)


@pytest.fixture
def auditor():
    return IndependentSemanticAuditor(token_match_threshold=0.60)


def test_entailed_claim(auditor):
    claim = {
        "claim_id": "c_01",
        "subject": "Titan-6",
        "statement": "Titan-6 articulated robot has a rated payload capacity of 450 kg.",
        "evidence_id": "ev_01",
    }
    evidence = {
        "evidence_id": "ev_01",
        "text": "Official CE Machinery Directive Certificate: Type-examination confirms maximum certified rated payload capacity of Titan-6 is strictly 450 kg.",
    }
    res = auditor.audit_claim(claim, evidence)
    assert res.status == SemanticSupportStatus.ENTAILED


def test_contradicted_numerical_claim(auditor):
    claim = {
        "claim_id": "c_02",
        "subject": "Phoenix-1",
        "statement": "Phoenix-1 aerospike engine achieves sea-level thrust of 120 kN.",
        "evidence_id": "ev_02",
    }
    evidence = {
        "evidence_id": "ev_02",
        "text": "Static firing test reports demonstrate Phoenix-1 aerospike engine delivers sea-level thrust of strictly 85 kN under standard atmospheric pressure.",
    }
    res = auditor.audit_claim(claim, evidence)
    assert res.status == SemanticSupportStatus.CONTRADICTED
    assert "Numerical value mismatch" in res.rationale


def test_contradicted_negation_claim(auditor):
    claim = {
        "claim_id": "c_03",
        "subject": "LK-99",
        "statement": "LK-99 exhibits room-temperature superconductivity.",
        "evidence_id": "ev_03",
    }
    evidence = {
        "evidence_id": "ev_03",
        "text": "Independent replication studies confirmed LK-99 is not a superconductor and showed zero diamagnetic transition.",
    }
    res = auditor.audit_claim(claim, evidence)
    assert res.status == SemanticSupportStatus.CONTRADICTED


def test_insufficiently_supported_claim(auditor):
    claim = {
        "claim_id": "c_04",
        "subject": "Cardiax",
        "statement": "Cardiax demonstrates 40% reduction in cardiovascular mortality in clinical trials.",
        "evidence_id": "ev_04",
    }
    evidence = {
        "evidence_id": "ev_04",
        "text": "Preliminary laboratory research notes that Cardiax was evaluated in animal models, but findings are unconfirmed and pending investigation.",
    }
    res = auditor.audit_claim(claim, evidence)
    assert res.status == SemanticSupportStatus.INSUFFICIENTLY_SUPPORTED
    assert "epistemic qualification" in res.rationale


def test_irrelevant_evidence(auditor):
    claim = {
        "claim_id": "c_05",
        "subject": "Solaris SCADA",
        "statement": "Solaris SCADA Gateway firmware implements IEC 62443 security controls.",
        "evidence_id": "ev_05",
    }
    evidence = {
        "evidence_id": "ev_05",
        "text": "Oceanic deep-sea drilling platform offshore Norway reported routine maintenance on hydraulic drill risers.",
    }
    res = auditor.audit_claim(claim, evidence)
    assert res.status == SemanticSupportStatus.IRRELEVANT_EVIDENCE


def test_partially_supported_compound_claim(auditor):
    claim = {
        "claim_id": "c_06",
        "subject": "Helix BioFoundry",
        "statement": "Helix BioFoundry operates synthetic biology laboratories in Zurich, and also maintains a deep space cryogenic propulsion facility.",
        "evidence_id": "ev_06",
    }
    evidence = {
        "evidence_id": "ev_06",
        "text": "Helix BioFoundry operates high-throughput synthetic biology laboratories in Zurich specializing in enzyme engineering.",
    }
    res = auditor.audit_claim(claim, evidence)
    assert res.status == SemanticSupportStatus.PARTIALLY_SUPPORTED_COMPOUND
    assert "Partially supported compound" in res.rationale
