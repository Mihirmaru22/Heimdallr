"""Adversarial tests for Section 2: Entity Merge Semantics & Epistemic Correctness."""

import json
from pathlib import Path
import tempfile
import pytest

from argus.domain.claim import Claim, ClaimStatus
from argus.domain.entity import Entity
from argus.domain.evidence import Evidence
from argus.domain.objective import ResearchObjective
from argus.storage.db import DatabaseManager
from argus.storage.repository import ArgusRepository


@pytest.fixture
def repo_and_obj():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_merge.db"
        db = DatabaseManager(db_path)
        repo = ArgusRepository(db)
        obj = ResearchObjective(
            target="Apex Test Org",
            target_type="organization",
            intelligence_goal="Audit entity merge semantics",
            required_fields=["name", "officers"],
            success_criteria="rigorous audit",
        )
        repo.save_objective(obj)
        yield repo, obj


def test_1_pending_versus_corroborated_same_predicate_and_object(repo_and_obj):
    """Pending unverified claim reconciled with corroborated claim retains CORROBORATED and high confidence."""
    repo, obj = repo_and_obj
    e1 = Entity(canonical_name="Primary Entity", entity_type="organization", objective_id=obj.objective_id)
    e2 = Entity(canonical_name="Duplicate Entity", entity_type="organization", objective_id=obj.objective_id)
    repo.save_entity(e1)
    repo.save_entity(e2)

    c1 = Claim(
        subject_entity_id=e1.entity_id,
        predicate="OPERATES_DOMAIN",
        object_value="domain.com",
        status=ClaimStatus.PENDING,
        confidence=0.50,
        evidence_ids=["evi_pending_01"],
        objective_id=obj.objective_id,
    )
    c2 = Claim(
        subject_entity_id=e2.entity_id,
        predicate="OPERATES_DOMAIN",
        object_value="domain.com",
        status=ClaimStatus.CORROBORATED,
        confidence=0.96,
        evidence_ids=["evi_corrob_01", "evi_corrob_02"],
        objective_id=obj.objective_id,
    )
    repo.save_claim(c1)
    repo.save_claim(c2)

    assert repo.merge_entities(e1.entity_id, [e2.entity_id]) is True

    claims = repo.list_claims(subject_entity_id=e1.entity_id)
    assert len(claims) == 1
    merged = claims[0]
    assert merged.status == ClaimStatus.CORROBORATED
    assert merged.confidence == 0.96
    assert set(merged.evidence_ids) == {"evi_pending_01", "evi_corrob_01", "evi_corrob_02"}


def test_2_supported_versus_contradicted_preserves_contradiction_without_confidence_inflation(repo_and_obj):
    """Supported vs contradicted claims preserve BOTH distinct records; neither is erased or converted to fake consensus."""
    repo, obj = repo_and_obj
    e1 = Entity(canonical_name="Target Alpha", entity_type="organization", objective_id=obj.objective_id)
    e2 = Entity(canonical_name="Target Alpha Alias", entity_type="organization", objective_id=obj.objective_id)
    repo.save_entity(e1)
    repo.save_entity(e2)

    # Claim 1: Supported by optimistic source, conf 0.88
    c1 = Claim(
        subject_entity_id=e1.entity_id,
        predicate="ACTIVE_STATUS",
        object_value="operational",
        status=ClaimStatus.SUPPORTED,
        confidence=0.88,
        evidence_ids=["evi_source_pro"],
        objective_id=obj.objective_id,
    )
    # Claim 2: Contradicted by authoritative regulatory filing, conf 0.40
    c2 = Claim(
        subject_entity_id=e2.entity_id,
        predicate="ACTIVE_STATUS",
        object_value="operational",
        status=ClaimStatus.CONTRADICTED,
        confidence=0.40,
        evidence_ids=["evi_source_con"],
        objective_id=obj.objective_id,
    )
    repo.save_claim(c1)
    repo.save_claim(c2)

    assert repo.merge_entities(e1.entity_id, [e2.entity_id]) is True

    claims = repo.list_claims(subject_entity_id=e1.entity_id)
    # Both claims MUST be preserved in the database to retain conflicting evidence!
    assert len(claims) == 2, f"Expected 2 distinct claims preserving contradictory evidence, got {len(claims)}"
    
    statuses = {c.status for c in claims}
    assert ClaimStatus.SUPPORTED in statuses
    assert ClaimStatus.CONTRADICTED in statuses
    
    # Check each individual claim's integrity
    sup_claim = next(c for c in claims if c.status == ClaimStatus.SUPPORTED)
    con_claim = next(c for c in claims if c.status == ClaimStatus.CONTRADICTED)
    
    assert sup_claim.confidence == 0.88
    assert sup_claim.evidence_ids == ["evi_source_pro"]
    assert "contradiction" in sup_claim.inference_reason.lower()
    
    assert con_claim.confidence == 0.40
    assert con_claim.evidence_ids == ["evi_source_con"]
    assert "contradiction" in con_claim.inference_reason.lower()


def test_3_claims_with_different_predicates_preserved(repo_and_obj):
    """Claims with different predicates on merged entities must never be collapsed or deleted."""
    repo, obj = repo_and_obj
    e1 = Entity(canonical_name="Corp Main", entity_type="organization", objective_id=obj.objective_id)
    e2 = Entity(canonical_name="Corp Sub", entity_type="organization", objective_id=obj.objective_id)
    repo.save_entity(e1)
    repo.save_entity(e2)

    c1 = Claim(
        subject_entity_id=e1.entity_id,
        predicate="INCORPORATED_IN",
        object_value="Delaware",
        status=ClaimStatus.SUPPORTED,
        confidence=0.95,
        evidence_ids=["evi_de"],
        objective_id=obj.objective_id,
    )
    c2 = Claim(
        subject_entity_id=e2.entity_id,
        predicate="ANNUAL_REVENUE",
        object_value="$100M",
        status=ClaimStatus.SUPPORTED,
        confidence=0.90,
        evidence_ids=["evi_rev"],
        objective_id=obj.objective_id,
    )
    repo.save_claim(c1)
    repo.save_claim(c2)

    assert repo.merge_entities(e1.entity_id, [e2.entity_id]) is True

    claims = repo.list_claims(subject_entity_id=e1.entity_id)
    assert len(claims) == 2
    predicates = {c.predicate for c in claims}
    assert predicates == {"INCORPORATED_IN", "ANNUAL_REVENUE"}


def test_4_claims_with_different_temporal_periods_preserved(repo_and_obj):
    """Historical vs current claims with same predicate and object must remain distinct and NOT collapsed."""
    repo, obj = repo_and_obj
    e1 = Entity(canonical_name="Apex Holding", entity_type="organization", objective_id=obj.objective_id)
    e2 = Entity(canonical_name="Apex Holding Historic", entity_type="organization", objective_id=obj.objective_id)
    repo.save_entity(e1)
    repo.save_entity(e2)

    c_hist = Claim(
        subject_entity_id=e1.entity_id,
        predicate="HEADQUARTERS",
        object_value="Austin, TX",
        temporal_context="2015-2019",
        status=ClaimStatus.SUPPORTED,
        confidence=0.92,
        evidence_ids=["evi_hist"],
        objective_id=obj.objective_id,
    )
    c_curr = Claim(
        subject_entity_id=e2.entity_id,
        predicate="HEADQUARTERS",
        object_value="Austin, TX",
        temporal_context="current_2024",
        status=ClaimStatus.SUPPORTED,
        confidence=0.95,
        evidence_ids=["evi_curr"],
        objective_id=obj.objective_id,
    )
    repo.save_claim(c_hist)
    repo.save_claim(c_curr)

    assert repo.merge_entities(e1.entity_id, [e2.entity_id]) is True

    claims = repo.list_claims(subject_entity_id=e1.entity_id)
    assert len(claims) == 2  # Both temporal contexts preserved!
    contexts = {c.temporal_context for c in claims}
    assert contexts == {"2015-2019", "current_2024"}


def test_5_overlapping_and_syndicated_evidence_deduplicated(repo_and_obj):
    """Overlapping evidence IDs from duplicated scrapers are deduplicated without losing unique references."""
    repo, obj = repo_and_obj
    e1 = Entity(canonical_name="Plant Node", entity_type="facility", objective_id=obj.objective_id)
    e2 = Entity(canonical_name="Plant Node Mirror", entity_type="facility", objective_id=obj.objective_id)
    repo.save_entity(e1)
    repo.save_entity(e2)

    c1 = Claim(
        subject_entity_id=e1.entity_id,
        predicate="POWER_CAPACITY",
        object_value="500MW",
        status=ClaimStatus.SUPPORTED,
        confidence=0.85,
        evidence_ids=["evi_shared", "evi_unique_1"],
        objective_id=obj.objective_id,
    )
    c2 = Claim(
        subject_entity_id=e2.entity_id,
        predicate="POWER_CAPACITY",
        object_value="500MW",
        status=ClaimStatus.SUPPORTED,
        confidence=0.85,
        evidence_ids=["evi_shared", "evi_unique_2"],
        objective_id=obj.objective_id,
    )
    repo.save_claim(c1)
    repo.save_claim(c2)

    assert repo.merge_entities(e1.entity_id, [e2.entity_id]) is True

    claims = repo.list_claims(subject_entity_id=e1.entity_id)
    assert len(claims) == 1
    assert sorted(claims[0].evidence_ids) == ["evi_shared", "evi_unique_1", "evi_unique_2"]


def test_6_different_source_provenance_and_derivation_inputs(repo_and_obj):
    """Derivation inputs and inference rationale are combined across merged claims."""
    repo, obj = repo_and_obj
    e1 = Entity(canonical_name="Derived Entity", entity_type="person", objective_id=obj.objective_id)
    e2 = Entity(canonical_name="Derived Entity Alias", entity_type="person", objective_id=obj.objective_id)
    repo.save_entity(e1)
    repo.save_entity(e2)

    c1 = Claim(
        subject_entity_id=e1.entity_id,
        predicate="ASSOCIATED_WITH",
        object_value="Consortium",
        status=ClaimStatus.INFERRED,
        confidence=0.75,
        derivation_inputs=["clm_step1"],
        derivation_method="graph_linkage",
        evidence_ids=["evi_a"],
        objective_id=obj.objective_id,
    )
    c2 = Claim(
        subject_entity_id=e2.entity_id,
        predicate="ASSOCIATED_WITH",
        object_value="Consortium",
        status=ClaimStatus.INFERRED,
        confidence=0.78,
        derivation_inputs=["clm_step2"],
        derivation_method="graph_linkage",
        evidence_ids=["evi_b"],
        objective_id=obj.objective_id,
    )
    repo.save_claim(c1)
    repo.save_claim(c2)

    assert repo.merge_entities(e1.entity_id, [e2.entity_id]) is True

    claims = repo.list_claims(subject_entity_id=e1.entity_id)
    assert len(claims) == 1
    merged = claims[0]
    assert set(merged.derivation_inputs) == {"clm_step1", "clm_step2"}
    assert set(merged.evidence_ids) == {"evi_a", "evi_b"}


def test_7_different_confidence_levels_preserved_appropriately(repo_and_obj):
    """When combining supportive claims, maximum verified confidence is preserved without arbitrary distortion."""
    repo, obj = repo_and_obj
    e1 = Entity(canonical_name="Ent 1", entity_type="organization", objective_id=obj.objective_id)
    e2 = Entity(canonical_name="Ent 2", entity_type="organization", objective_id=obj.objective_id)
    repo.save_entity(e1)
    repo.save_entity(e2)

    c1 = Claim(
        subject_entity_id=e1.entity_id,
        predicate="PATENT_COUNT",
        object_value="42",
        status=ClaimStatus.SUPPORTED,
        confidence=0.72,
        evidence_ids=["evi_p1"],
        objective_id=obj.objective_id,
    )
    c2 = Claim(
        subject_entity_id=e2.entity_id,
        predicate="PATENT_COUNT",
        object_value="42",
        status=ClaimStatus.SUPPORTED,
        confidence=0.91,
        evidence_ids=["evi_p2"],
        objective_id=obj.objective_id,
    )
    repo.save_claim(c1)
    repo.save_claim(c2)

    assert repo.merge_entities(e1.entity_id, [e2.entity_id]) is True

    claims = repo.list_claims(subject_entity_id=e1.entity_id)
    assert len(claims) == 1
    assert claims[0].confidence == 0.91


def test_8_multiple_distinct_claims_across_multiple_entities(repo_and_obj):
    """Merging entities carrying distinct clusters of claims maintains all non-duplicate claims intact."""
    repo, obj = repo_and_obj
    e1 = Entity(canonical_name="Corp Alpha", entity_type="organization", objective_id=obj.objective_id)
    e2 = Entity(canonical_name="Corp Beta", entity_type="organization", objective_id=obj.objective_id)
    repo.save_entity(e1)
    repo.save_entity(e2)

    # 3 distinct claims on e1
    repo.save_claim(Claim(subject_entity_id=e1.entity_id, predicate="TAG_A", object_value="ValA", objective_id=obj.objective_id))
    repo.save_claim(Claim(subject_entity_id=e1.entity_id, predicate="TAG_B", object_value="ValB", objective_id=obj.objective_id))
    repo.save_claim(Claim(subject_entity_id=e1.entity_id, predicate="TAG_C", object_value="ValC", objective_id=obj.objective_id))

    # 2 distinct claims on e2
    repo.save_claim(Claim(subject_entity_id=e2.entity_id, predicate="TAG_D", object_value="ValD", objective_id=obj.objective_id))
    repo.save_claim(Claim(subject_entity_id=e2.entity_id, predicate="TAG_E", object_value="ValE", objective_id=obj.objective_id))

    assert repo.merge_entities(e1.entity_id, [e2.entity_id]) is True

    claims = repo.list_claims(subject_entity_id=e1.entity_id)
    assert len(claims) == 5
    predicates = {c.predicate for c in claims}
    assert predicates == {"TAG_A", "TAG_B", "TAG_C", "TAG_D", "TAG_E"}


def test_9_repeated_merges_and_idempotency(repo_and_obj):
    """Repeated execution of merge_entities is completely idempotent and safe."""
    repo, obj = repo_and_obj
    e1 = Entity(canonical_name="Canonical Master", entity_type="organization", objective_id=obj.objective_id)
    e2 = Entity(canonical_name="Duplicate A", entity_type="organization", objective_id=obj.objective_id)
    repo.save_entity(e1)
    repo.save_entity(e2)

    c1 = Claim(subject_entity_id=e1.entity_id, predicate="CODE", object_value="XYZ", objective_id=obj.objective_id)
    c2 = Claim(subject_entity_id=e2.entity_id, predicate="CODE", object_value="XYZ", objective_id=obj.objective_id)
    repo.save_claim(c1)
    repo.save_claim(c2)

    # First merge
    res1 = repo.merge_entities(e1.entity_id, [e2.entity_id])
    assert res1 is True
    assert len(repo.list_claims(subject_entity_id=e1.entity_id)) == 1

    # Second merge (idempotent call with already-deleted duplicate ID)
    res2 = repo.merge_entities(e1.entity_id, [e2.entity_id])
    assert res2 is True
    assert len(repo.list_claims(subject_entity_id=e1.entity_id)) == 1

    # Third merge with empty duplicate list
    res3 = repo.merge_entities(e1.entity_id, [])
    assert res3 is False


def test_10_invalid_and_missing_evidence_references(repo_and_obj):
    """Claims with empty, whitespace, or malformed evidence IDs do not crash merge and preserve valid IDs."""
    repo, obj = repo_and_obj
    e1 = Entity(canonical_name="Robust Node", entity_type="organization", objective_id=obj.objective_id)
    e2 = Entity(canonical_name="Robust Node Alias", entity_type="organization", objective_id=obj.objective_id)
    repo.save_entity(e1)
    repo.save_entity(e2)

    c1 = Claim(
        subject_entity_id=e1.entity_id,
        predicate="PROPERTY",
        object_value="Static",
        evidence_ids=["", "  ", "evi_valid_only"],
        objective_id=obj.objective_id,
    )
    c2 = Claim(
        subject_entity_id=e2.entity_id,
        predicate="PROPERTY",
        object_value="Static",
        evidence_ids=[],
        objective_id=obj.objective_id,
    )
    repo.save_claim(c1)
    repo.save_claim(c2)

    assert repo.merge_entities(e1.entity_id, [e2.entity_id]) is True

    claims = repo.list_claims(subject_entity_id=e1.entity_id)
    assert len(claims) == 1
    assert claims[0].evidence_ids == ["evi_valid_only"]


def test_11_database_rollback_on_injected_exception(repo_and_obj):
    """An unhandled error mid-merge rolls back the entire database transaction, preserving pre-merge state."""
    repo, obj = repo_and_obj
    e1 = Entity(canonical_name="Tx Master", entity_type="organization", objective_id=obj.objective_id)
    e2 = Entity(canonical_name="Tx Duplicate", entity_type="organization", objective_id=obj.objective_id)
    repo.save_entity(e1)
    repo.save_entity(e2)

    c1 = Claim(subject_entity_id=e1.entity_id, predicate="STATUS", object_value="A", objective_id=obj.objective_id)
    c2 = Claim(subject_entity_id=e2.entity_id, predicate="STATUS", object_value="B", objective_id=obj.objective_id)
    repo.save_claim(c1)
    repo.save_claim(c2)

    # Monkey-patch cursor execution in transaction to simulate failure on claims deletion
    orig_transaction = repo.db.transaction

    class CursorWrapper:
        def __init__(self, cursor):
            self._cursor = cursor
        def execute(self, sql, *args, **kwargs):
            if "DELETE FROM entities" in sql:
                raise RuntimeError("Simulated mid-transaction failure during entity deletion!")
            return self._cursor.execute(sql, *args, **kwargs)
        def __getattr__(self, name):
            return getattr(self._cursor, name)

    from contextlib import contextmanager
    @contextmanager
    def failing_transaction():
        with orig_transaction() as cur:
            yield CursorWrapper(cur)

    repo.db.transaction = failing_transaction

    with pytest.raises(RuntimeError, match="Simulated mid-transaction failure"):
        repo.merge_entities(e1.entity_id, [e2.entity_id])

    # Restore transaction
    repo.db.transaction = orig_transaction

    # Verify complete rollback: e2 still exists in entities table!
    assert repo.get_entity(e2.entity_id) is not None
    assert repo.get_entity(e1.entity_id).canonical_name == "Tx Master"
    
    # Claims are still associated with their original subjects!
    c1_db = repo.get_claim(c1.claim_id)
    c2_db = repo.get_claim(c2.claim_id)
    assert c1_db.subject_entity_id == e1.entity_id
    assert c2_db.subject_entity_id == e2.entity_id


def test_12_object_entity_repointing(repo_and_obj):
    """When an entity is merged, claims where it appears as object_entity_id are correctly repointed to the primary entity."""
    repo, obj = repo_and_obj
    e_primary = Entity(canonical_name="Holding Corp", entity_type="organization", objective_id=obj.objective_id)
    e_alias = Entity(canonical_name="Holding Corp Alias", entity_type="organization", objective_id=obj.objective_id)
    e_subsidiary = Entity(canonical_name="Sub Unit LLC", entity_type="organization", objective_id=obj.objective_id)
    repo.save_entity(e_primary)
    repo.save_entity(e_alias)
    repo.save_entity(e_subsidiary)

    # Claim points to e_alias as object_entity_id
    c_sub = Claim(
        subject_entity_id=e_subsidiary.entity_id,
        predicate="SUBSIDIARY_OF",
        object_value="Holding Corp Alias",
        object_entity_id=e_alias.entity_id,
        objective_id=obj.objective_id,
    )
    repo.save_claim(c_sub)

    assert repo.merge_entities(e_primary.entity_id, [e_alias.entity_id]) is True

    # Check that c_sub was repointed to e_primary in persisted database
    persisted = repo.get_claim(c_sub.claim_id)
    assert persisted is not None
    assert persisted.object_entity_id == e_primary.entity_id

