import pytest
from pydantic import ValidationError

from argus.domain.claim import Claim, ClaimStatus
from argus.domain.entity import Entity
from argus.domain.evidence import Evidence


def test_entity_creation():
    entity = Entity(
        entity_type="facility",
        canonical_name="Kentucky Truck Plant",
        aliases=["KTP", "Ford Louisville Truck Plant"],
        attributes={"address": "3001 Chamberlain Ln, Louisville, KY", "sqft": 6000000},
    )
    assert entity.entity_id.startswith("ent_")
    assert entity.entity_type == "facility"
    assert entity.canonical_name == "Kentucky Truck Plant"
    assert len(entity.aliases) == 2
    assert entity.attributes["sqft"] == 6000000
    assert entity.created_at is not None


def test_evidence_creation():
    evidence = Evidence(
        source_id="doc_scrape_001",
        url="https://media.ford.com/plants/ktp",
        passage="Kentucky Truck Plant employs 9,000 workers and builds the Ford F-Series Super Duty.",
        char_start=120,
        char_end=207,
        confidence=0.98,
    )
    assert evidence.evidence_id.startswith("evi_")
    assert evidence.url.startswith("https://")
    assert evidence.confidence == 0.98
    assert evidence.char_start == 120
    assert evidence.char_end == 207


def test_evidence_invalid_confidence():
    with pytest.raises(ValidationError):
        Evidence(
            source_id="doc_1",
            url="https://example.com",
            passage="Test passage",
            confidence=1.5,  # must be <= 1.0
        )


def test_claim_creation_and_linking():
    claim = Claim(
        subject_entity_id="ent_ford_01",
        predicate="OPERATES_FACILITY",
        object_value="Kentucky Truck Plant",
        object_entity_id="ent_ktp_01",
        status=ClaimStatus.SUPPORTED,
        evidence_ids=["evi_01", "evi_02"],
        confidence=0.95,
    )
    assert claim.claim_id.startswith("clm_")
    assert claim.subject_entity_id == "ent_ford_01"
    assert claim.predicate == "OPERATES_FACILITY"
    assert claim.status == ClaimStatus.SUPPORTED
    assert len(claim.evidence_ids) == 2
    assert claim.confidence == 0.95
