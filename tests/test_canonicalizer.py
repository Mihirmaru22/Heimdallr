"""Unit and integration tests for Pain Point 4: Entity Canonicalization & Alias Resolution."""

import pytest

from argus.crawler.models import Document
from argus.domain.canonicalizer import (
    are_entities_equivalent,
    are_entity_types_compatible,
    extract_company_core_tokens,
    extract_facility_core_tokens,
    extract_person_core_tokens,
)
from argus.domain.claim import Claim, ClaimStatus
from argus.domain.entity import Entity
from argus.domain.evidence import Evidence
from argus.domain.objective import ResearchObjective
from argus.domain.task import ResearchTask
from argus.llm.mock import MockLLMProvider
from argus.storage.db import DatabaseManager
from argus.storage.repository import ArgusRepository
from argus.worker.engine import WorkerEngine
from argus.worker.models import (
    ExtractedClaimItem,
    ExtractedEntityItem,
    ExtractionPayload,
    RelevanceAssessment,
)


@pytest.fixture
def repo():
    db = DatabaseManager(":memory:")
    return ArgusRepository(db)


@pytest.fixture
def sample_objective(repo):
    obj = ResearchObjective(
        target="US Automobile Manufacturers",
        target_type="industry",
        intelligence_goal="Identify plants, locations, and key leadership.",
        required_fields=["name", "facility", "location"],
        success_criteria="At least 5 plants verified",
    )
    repo.save_objective(obj)
    return obj


@pytest.fixture
def sample_task(repo, sample_objective):
    task = ResearchTask(
        objective_id=sample_objective.objective_id,
        title="Extract GM Facilities",
        description="Extract Bowling Green assembly facility details.",
    )
    repo.save_task(task)
    return task


def test_fuzzy_canonicalization_triad():
    """Verify exact equivalence across the triad of real-world string variations."""
    source_a = "General Motors Bowling Green Assembly"
    source_b = "GM Bowling Green Plant"
    source_c = "Bowling Green Assembly Complex"

    # Core tokens should all resolve to {'bowling', 'green'}
    assert extract_facility_core_tokens(source_a) == frozenset({"bowling", "green"})
    assert extract_facility_core_tokens(source_b) == frozenset({"bowling", "green"})
    assert extract_facility_core_tokens(source_c) == frozenset({"bowling", "green"})

    # All pairwise comparisons across variations and sub-types should match
    assert are_entities_equivalent(source_a, "manufacturing_plant", source_b, "facility")
    assert are_entities_equivalent(source_b, "facility", source_c, "facility")
    assert are_entities_equivalent(source_a, "manufacturing_plant", source_c, "assembly_plant")


def test_fuzzy_canonicalization_negative_controls():
    """Ensure distinct entities and incompatible types do NOT match."""
    # Distinct geographic plants
    assert not are_entities_equivalent(
        "Arlington Assembly", "manufacturing_plant", "Flint Assembly", "facility"
    )

    # Incompatible semantic types: Parent Automaker vs Facility
    assert not are_entities_equivalent(
        "General Motors", "company", "General Motors Bowling Green Assembly", "facility"
    )
    assert not are_entity_types_compatible("company", "facility")
    assert not are_entity_types_compatible("person", "facility")


def test_person_canonicalization():
    """Verify person names with titles, honorifics, and middle names resolve."""
    assert are_entities_equivalent(
        "Ray Bergman, Plant Director", "person", "Ray Bergman", "director"
    )
    assert are_entities_equivalent(
        "Dr. Raymond Bergman", "executive", "Raymond Bergman", "person"
    )


@pytest.mark.asyncio
async def test_worker_canonicalization_prevents_duplicate_spawning(
    repo, sample_objective, sample_task
):
    """Test that WorkerEngine resolves incoming variants to the canonical existing entity."""
    # Pre-populate repository with Source A
    existing_entity = Entity(
        canonical_name="General Motors Bowling Green Assembly",
        entity_type="manufacturing_plant",
        aliases=["Bowling Green Assembly"],
        attributes={"state": "Kentucky"},
        objective_id=sample_objective.objective_id,
    )
    repo.save_entity(existing_entity)

    # Document B arrives with Source B string and a plant manager claim
    doc_text = "GM Bowling Green Plant is currently directed by Ray Bergman."
    doc = Document(
        url="https://gm.com/bowling-green",
        title="GM Bowling Green",
        text_content=doc_text,
    )
    repo.save_document(doc)

    mock_payload = ExtractionPayload(
        relevance=RelevanceAssessment(is_relevant=True, reasoning="Direct plant details"),
        entities=[
            ExtractedEntityItem(
                name="GM Bowling Green Plant",
                entity_type="facility",
                aliases=["GM Bowling Green"],
                attributes={"city": "Bowling Green"},
            ),
            ExtractedEntityItem(
                name="Ray Bergman",
                entity_type="person",
                aliases=[],
            ),
        ],
        claims=[
            ExtractedClaimItem(
                subject_name="GM Bowling Green Plant",
                predicate="HAS_PLANT_MANAGER",
                object_value="Ray Bergman",
                verbatim_passage="GM Bowling Green Plant is currently directed by Ray Bergman.",
                confidence=0.95,
            )
        ],
    )

    provider = MockLLMProvider(responses=[mock_payload])
    engine = WorkerEngine(repo=repo, llm=provider)

    result = await engine.process_document(doc, sample_task, sample_objective)

    # GM Bowling Green Plant should be merged onto existing_entity, NOT spawned as new
    created_names = [e.canonical_name for e in result.entities_created]
    assert "GM Bowling Green Plant" not in created_names
    assert "Ray Bergman" in created_names  # Person was newly created

    # Existing entity should be updated
    assert len(result.entities_updated) == 1
    updated = result.entities_updated[0]
    assert updated.entity_id == existing_entity.entity_id
    assert "GM Bowling Green Plant" in updated.aliases or "GM Bowling Green" in updated.aliases
    assert updated.attributes["city"] == "Bowling Green"
    assert updated.attributes["state"] == "Kentucky"

    # Claim subject should point directly to existing_entity.entity_id
    assert len(result.claims_created) == 1
    claim = result.claims_created[0]
    assert claim.subject_entity_id == existing_entity.entity_id


def test_repository_merge_entities(repo, sample_objective):
    """Test repo.merge_entities repoints claims, merges metadata, and purges duplicates."""
    e1 = Entity(
        canonical_name="Arlington Assembly",
        entity_type="manufacturing_plant",
        aliases=["Arlington"],
        attributes={"state": "TX"},
        objective_id=sample_objective.objective_id,
    )
    e2 = Entity(
        canonical_name="Arlington Assembly Plant",
        entity_type="facility",
        aliases=["GM Arlington"],
        attributes={"city": "Arlington", "phone": "817-652-2200"},
        objective_id=sample_objective.objective_id,
    )
    repo.save_entity(e1)
    repo.save_entity(e2)

    c1 = Claim(
        subject_entity_id=e1.entity_id,
        predicate="LOCATED_IN",
        object_value="Arlington, TX",
        status=ClaimStatus.SUPPORTED,
        objective_id=sample_objective.objective_id,
    )
    c2 = Claim(
        subject_entity_id=e2.entity_id,
        predicate="HAS_SWITCHBOARD",
        object_value="817-652-2200",
        status=ClaimStatus.SUPPORTED,
        objective_id=sample_objective.objective_id,
    )
    repo.save_claim(c1)
    repo.save_claim(c2)

    # Execute entity merge
    success = repo.merge_entities(primary_entity_id=e1.entity_id, duplicate_entity_ids=[e2.entity_id])
    assert success is True

    # e2 should be deleted
    assert repo.get_entity(e2.entity_id) is None
    merged_e1 = repo.get_entity(e1.entity_id)
    assert merged_e1 is not None
    assert "Arlington Assembly Plant" in merged_e1.aliases
    assert merged_e1.attributes["city"] == "Arlington"
    assert merged_e1.attributes["state"] == "TX"

    # Both claims should now point to e1.entity_id
    claims_for_e1 = repo.list_claims(subject_entity_id=e1.entity_id)
    assert len(claims_for_e1) == 2
    predicates = {c.predicate for c in claims_for_e1}
    assert predicates == {"LOCATED_IN", "HAS_SWITCHBOARD"}


def test_materialize_matrix_consolidates_fragmented_entities(repo, sample_objective):
    """Test that materialize_plant_leadership_matrix consolidates fragmented rows into 1 complete row."""
    # Two fragmented entities for Bowling Green
    fac_a = Entity(
        canonical_name="Bowling Green Assembly",
        entity_type="manufacturing_plant",
        attributes={"address": "Bowling Green, KY"},
        objective_id=sample_objective.objective_id,
    )
    fac_b = Entity(
        canonical_name="GM Bowling Green Plant",
        entity_type="facility",
        attributes={"facility_phone": "(270) 745-8000"},
        objective_id=sample_objective.objective_id,
    )
    person = Entity(
        canonical_name="Ray Bergman",
        entity_type="person",
        attributes={"email": "ray.bergman@gm.com"},
        objective_id=sample_objective.objective_id,
    )
    repo.save_entity(fac_a)
    repo.save_entity(fac_b)
    repo.save_entity(person)

    ev1 = Evidence(
        source_id="h1", url="https://gm.com/press", passage="Bowling Green plant located in KY", confidence=0.9
    )
    ev2 = Evidence(
        source_id="h2", url="https://gm.com/contact", passage="Ray Bergman manages the plant", confidence=0.9
    )
    repo.save_evidence(ev1)
    repo.save_evidence(ev2)

    # Claim on fac_a (location)
    c1 = Claim(
        subject_entity_id=fac_a.entity_id,
        predicate="LOCATED_IN",
        object_value="Bowling Green, KY",
        status=ClaimStatus.SUPPORTED,
        evidence_ids=[ev1.evidence_id],
        objective_id=sample_objective.objective_id,
    )
    # Claim on fac_b (plant head + switchboard)
    c2 = Claim(
        subject_entity_id=fac_b.entity_id,
        predicate="HAS_PLANT_MANAGER",
        object_value="Ray Bergman",
        object_entity_id=person.entity_id,
        status=ClaimStatus.SUPPORTED,
        evidence_ids=[ev2.evidence_id],
        objective_id=sample_objective.objective_id,
    )
    c3 = Claim(
        subject_entity_id=fac_b.entity_id,
        predicate="HAS_FACILITY_PHONE",
        object_value="(270) 745-8000",
        status=ClaimStatus.SUPPORTED,
        evidence_ids=[ev2.evidence_id],
        objective_id=sample_objective.objective_id,
    )
    repo.save_claim(c1)
    repo.save_claim(c2)
    repo.save_claim(c3)

    # Materialize plant matrix
    count = repo.materialize_plant_leadership_matrix(objective_id=sample_objective.objective_id)

    # Should consolidate into EXACTLY 1 row, not 2 half-empty rows!
    assert count == 1

    with repo.db.transaction() as cur:
        cur.execute("SELECT * FROM plant_leadership_matrix")
        rows = cur.fetchall()
        assert len(rows) == 1
        row = rows[0]
        # Row has data merged from both fac_a and fac_b
        assert "Bowling Green" in row["plant_name"]
        assert row["plant_location"] == "Bowling Green, KY"
        assert row["plant_contact"] == "(270) 745-8000"
        assert row["plant_head"] == "Ray Bergman"
        assert row["plant_head_email"] == "ray.bergman@gm.com"
        assert "https://gm.com/press" in row["source_urls"]
        assert "https://gm.com/contact" in row["source_urls"]
