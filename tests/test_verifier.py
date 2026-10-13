from datetime import UTC, datetime

import pytest

from argus.domain.claim import Claim, ClaimStatus
from argus.domain.entity import Entity
from argus.domain.event import EventType
from argus.domain.evidence import Evidence
from argus.domain.objective import ResearchObjective
from argus.llm.mock import MockLLMProvider
from argus.storage.db import DatabaseManager
from argus.storage.repository import ArgusRepository
from argus.verifier.engine import ExpertVerifier
from argus.verifier.models import (
    AdjudicationPayload,
    ClaimEvaluation,
    VerdictType,
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
def sample_entity(repo, sample_objective):
    ent = Entity(
        canonical_name="Kentucky Truck Plant",
        entity_type="facility",
        aliases=["KTP"],
        objective_id=sample_objective.objective_id,
    )
    repo.save_entity(ent)
    return ent


@pytest.mark.asyncio
async def test_verifier_corroborates_agreeing_claims(
    repo, sample_objective, sample_entity
):
    ev1 = Evidence(
        source_id="hash_1",
        url="https://source-a.com/ktp",
        passage="Kentucky Truck Plant is located in Louisville, Kentucky.",
        confidence=0.9,
    )
    ev2 = Evidence(
        source_id="hash_2",
        url="https://source-b.com/facilities",
        passage="KTP is situated in Louisville, Kentucky.",
        confidence=0.85,
    )
    repo.save_evidence(ev1)
    repo.save_evidence(ev2)

    claim1 = Claim(
        subject_entity_id=sample_entity.entity_id,
        predicate="LOCATED_IN",
        object_value="Louisville, Kentucky",
        status=ClaimStatus.PENDING,
        evidence_ids=[ev1.evidence_id],
        objective_id=sample_objective.objective_id,
    )
    claim2 = Claim(
        subject_entity_id=sample_entity.entity_id,
        predicate="LOCATED_IN",
        object_value="Louisville, Kentucky",
        status=ClaimStatus.PENDING,
        evidence_ids=[ev2.evidence_id],
        objective_id=sample_objective.objective_id,
    )
    repo.save_claim(claim1)
    repo.save_claim(claim2)

    mock_llm = MockLLMProvider(responses=[])
    verifier = ExpertVerifier(repo=repo, llm=mock_llm)

    results = await verifier.adjudicate_pending_claims(
        objective_id=sample_objective.objective_id
    )

    assert len(results) == 1
    assert results[0].claims_evaluated == 2
    assert results[0].claims_supported == 2

    # Verify both claims were corroborated
    c1 = repo.get_claim(claim1.claim_id)
    c2 = repo.get_claim(claim2.claim_id)
    assert c1.status in (ClaimStatus.SUPPORTED, ClaimStatus.CORROBORATED)
    assert c2.status in (ClaimStatus.SUPPORTED, ClaimStatus.CORROBORATED)
    assert c1.confidence >= 0.95
    assert c2.confidence >= 0.95

    # Verify evidence IDs were merged
    assert set(c1.evidence_ids) == {ev1.evidence_id, ev2.evidence_id}
    assert set(c2.evidence_ids) == {ev1.evidence_id, ev2.evidence_id}

    # Verify audit event
    events = repo.list_events(sample_objective.objective_id)
    assert len(events) == 1
    assert events[0].event_type == EventType.VERIFICATION_COMPLETED


@pytest.mark.asyncio
async def test_verifier_resolves_temporal_supersession(
    repo, sample_objective, sample_entity
):
    ev_old = Evidence(
        source_id="hash_old",
        url="https://news2021.com/ktp",
        passage="John Doe appointed plant manager in 2021.",
        published_at=datetime(2021, 5, 1, tzinfo=UTC),
    )
    ev_new = Evidence(
        source_id="hash_new",
        url="https://media.ford.com/2026/ktp-update",
        passage="Jane Smith takes over as plant manager of Kentucky Truck Plant.",
        published_at=datetime(2026, 1, 15, tzinfo=UTC),
    )
    repo.save_evidence(ev_old)
    repo.save_evidence(ev_new)

    claim_old = Claim(
        subject_entity_id=sample_entity.entity_id,
        predicate="HAS_PLANT_MANAGER",
        object_value="John Doe",
        status=ClaimStatus.PENDING,
        evidence_ids=[ev_old.evidence_id],
        objective_id=sample_objective.objective_id,
    )
    claim_new = Claim(
        subject_entity_id=sample_entity.entity_id,
        predicate="HAS_PLANT_MANAGER",
        object_value="Jane Smith",
        status=ClaimStatus.PENDING,
        evidence_ids=[ev_new.evidence_id],
        objective_id=sample_objective.objective_id,
    )
    repo.save_claim(claim_old)
    repo.save_claim(claim_new)

    mock_payload = AdjudicationPayload(
        evaluations=[
            ClaimEvaluation(
                claim_id=claim_new.claim_id,
                status=ClaimStatus.SUPPORTED,
                confidence=0.96,
                verdict=VerdictType.SUPERSEDED,
                reasoning="2026 official press release documents current plant leadership.",
            ),
            ClaimEvaluation(
                claim_id=claim_old.claim_id,
                status=ClaimStatus.REFUTED,
                confidence=0.1,
                verdict=VerdictType.SUPERSEDED,
                reasoning="Obsolete 2021 record superseded by 2026 appointment.",
            ),
        ],
        has_conflict=False,
        summary_reasoning="Temporal progression resolved: Jane Smith replaced John Doe.",
    )

    mock_llm = MockLLMProvider(responses=[mock_payload])
    verifier = ExpertVerifier(repo=repo, llm=mock_llm)

    results = await verifier.adjudicate_pending_claims(
        objective_id=sample_objective.objective_id
    )

    assert len(results) == 1
    assert results[0].claims_supported == 1
    assert results[0].claims_refuted == 1

    c_new = repo.get_claim(claim_new.claim_id)
    c_old = repo.get_claim(claim_old.claim_id)
    assert c_new.status == ClaimStatus.SUPPORTED
    assert c_new.confidence == 0.96
    assert c_old.status == ClaimStatus.REFUTED


@pytest.mark.asyncio
async def test_verifier_flags_active_contradiction(
    repo, sample_objective, sample_entity
):
    ev1 = Evidence(
        source_id="hash_a",
        url="https://source-a.com/report",
        passage="KTP annual capacity is 250,000 units.",
    )
    ev2 = Evidence(
        source_id="hash_b",
        url="https://source-b.com/report",
        passage="KTP annual capacity is 400,000 units.",
    )
    repo.save_evidence(ev1)
    repo.save_evidence(ev2)

    claim1 = Claim(
        subject_entity_id=sample_entity.entity_id,
        predicate="HAS_ANNUAL_CAPACITY",
        object_value="250,000 units",
        status=ClaimStatus.PENDING,
        evidence_ids=[ev1.evidence_id],
        objective_id=sample_objective.objective_id,
    )
    claim2 = Claim(
        subject_entity_id=sample_entity.entity_id,
        predicate="HAS_ANNUAL_CAPACITY",
        object_value="400,000 units",
        status=ClaimStatus.PENDING,
        evidence_ids=[ev2.evidence_id],
        objective_id=sample_objective.objective_id,
    )
    repo.save_claim(claim1)
    repo.save_claim(claim2)

    mock_payload = AdjudicationPayload(
        evaluations=[
            ClaimEvaluation(
                claim_id=claim1.claim_id,
                status=ClaimStatus.CONTRADICTED,
                confidence=0.5,
                verdict=VerdictType.CONTRADICTION,
                reasoning="Contradicts second contemporaneous source citing 400k capacity.",
            ),
            ClaimEvaluation(
                claim_id=claim2.claim_id,
                status=ClaimStatus.CONTRADICTED,
                confidence=0.5,
                verdict=VerdictType.CONTRADICTION,
                reasoning="Contradicts first contemporaneous source citing 250k capacity.",
            ),
        ],
        has_conflict=True,
        summary_reasoning="Disputed capacity figures between two industry reports.",
        suggested_disambiguation_tasks=[
            "Verify official annual production capacity for Kentucky Truck Plant"
        ],
    )

    mock_llm = MockLLMProvider(responses=[mock_payload])
    verifier = ExpertVerifier(repo=repo, llm=mock_llm)

    results = await verifier.adjudicate_pending_claims(
        objective_id=sample_objective.objective_id
    )

    assert len(results) == 1
    assert results[0].claims_contradicted == 2
    assert len(results[0].suggested_tasks) == 1

    c1 = repo.get_claim(claim1.claim_id)
    c2 = repo.get_claim(claim2.claim_id)
    assert c1.status == ClaimStatus.CONTRADICTED
    assert c2.status == ClaimStatus.CONTRADICTED

    # Check CONTRADICTION_DETECTED event logged
    events = repo.list_events(sample_objective.objective_id)
    contradiction_events = [
        e for e in events if e.event_type == EventType.CONTRADICTION_DETECTED
    ]
    assert len(contradiction_events) == 1
    assert (
        "Kentucky Truck Plant" in contradiction_events[0].payload["suggested_tasks"][0]
    )


@pytest.mark.asyncio
async def test_verifier_handles_insufficient_single_source(
    repo, sample_objective, sample_entity
):
    ev = Evidence(
        source_id="hash_weak",
        url="https://forum-post.com/comment",
        passage="Someone said they might build batteries there soon.",
    )
    repo.save_evidence(ev)

    claim = Claim(
        subject_entity_id=sample_entity.entity_id,
        predicate="PRODUCES_BATTERIES",
        object_value="True",
        status=ClaimStatus.PENDING,
        evidence_ids=[ev.evidence_id],
        confidence=0.3,
        objective_id=sample_objective.objective_id,
    )
    repo.save_claim(claim)

    mock_payload = AdjudicationPayload(
        evaluations=[
            ClaimEvaluation(
                claim_id=claim.claim_id,
                status=ClaimStatus.UNVERIFIED,
                confidence=0.25,
                verdict=VerdictType.INSUFFICIENT,
                reasoning="Speculative hearsay from unverified forum comment.",
            )
        ],
        has_conflict=False,
        summary_reasoning="Single unverified forum source.",
    )

    mock_llm = MockLLMProvider(responses=[mock_payload])
    verifier = ExpertVerifier(repo=repo, llm=mock_llm)

    results = await verifier.adjudicate_pending_claims(
        objective_id=sample_objective.objective_id
    )

    assert len(results) == 1
    assert results[0].claims_unverified == 1

    stored_claim = repo.get_claim(claim.claim_id)
    assert stored_claim.status == ClaimStatus.UNVERIFIED
    assert stored_claim.confidence == 0.25


@pytest.mark.asyncio
async def test_verifier_no_pending_claims(repo, sample_objective):
    mock_llm = MockLLMProvider(responses=[])
    verifier = ExpertVerifier(repo=repo, llm=mock_llm)

    results = await verifier.adjudicate_pending_claims(
        objective_id=sample_objective.objective_id
    )
    assert results == []


@pytest.mark.asyncio
async def test_verifier_detects_contradiction_against_existing_supported_claim(
    repo, sample_objective, sample_entity
):
    """Bug 1.2 Regression Test:

    Verify that a new pending claim is evaluated against pre-existing SUPPORTED claims
    for the same subject and predicate, detecting cross-task contradictions rather than
    blindly supporting conflicting facts via the single-source fast path.
    """
    # 1. Existing SUPPORTED claim from Task 1
    ev1 = Evidence(
        source_id="hash_1",
        url="https://source-1.com/leadership",
        passage="John Doe serves as plant manager of Kentucky Truck Plant.",
    )
    repo.save_evidence(ev1)

    claim_existing = Claim(
        subject_entity_id=sample_entity.entity_id,
        predicate="HAS_PLANT_MANAGER",
        object_value="John Doe",
        status=ClaimStatus.SUPPORTED,
        evidence_ids=[ev1.evidence_id],
        confidence=0.92,
        objective_id=sample_objective.objective_id,
    )
    repo.save_claim(claim_existing)

    # 2. New PENDING claim from Task 2 (would previously trigger fast path if evaluated alone!)
    ev2 = Evidence(
        source_id="hash_2",
        url="https://source-2.com/facilities",
        passage="Jane Smith is plant manager of Kentucky Truck Plant.",
    )
    repo.save_evidence(ev2)

    claim_pending = Claim(
        subject_entity_id=sample_entity.entity_id,
        predicate="HAS_PLANT_MANAGER",
        object_value="Jane Smith",
        status=ClaimStatus.PENDING,
        evidence_ids=[ev2.evidence_id],
        confidence=0.90,  # >= 0.85
        objective_id=sample_objective.objective_id,
    )
    repo.save_claim(claim_pending)

    # 3. LLM returns active contradiction
    mock_payload = AdjudicationPayload(
        evaluations=[
            ClaimEvaluation(
                claim_id=claim_existing.claim_id,
                status=ClaimStatus.CONTRADICTED,
                confidence=0.5,
                verdict=VerdictType.CONTRADICTION,
                reasoning="Disputed plant manager between source 1 and source 2.",
            ),
            ClaimEvaluation(
                claim_id=claim_pending.claim_id,
                status=ClaimStatus.CONTRADICTED,
                confidence=0.5,
                verdict=VerdictType.CONTRADICTION,
                reasoning="Disputed plant manager between source 1 and source 2.",
            ),
        ],
        has_conflict=True,
        summary_reasoning="Conflicting leadership records across tasks.",
        suggested_disambiguation_tasks=[
            "Verify official KTP manager via corporate filing"
        ],
    )

    mock_llm = MockLLMProvider(responses=[mock_payload])
    verifier = ExpertVerifier(repo=repo, llm=mock_llm)

    # 4. Adjudicate
    results = await verifier.adjudicate_pending_claims(
        objective_id=sample_objective.objective_id
    )

    assert len(results) == 1
    assert results[0].claims_evaluated == 2
    assert results[0].claims_contradicted == 2
    assert len(results[0].suggested_tasks) == 1

    # 5. Verify database state: neither claim is left as SUPPORTED
    c1 = repo.get_claim(claim_existing.claim_id)
    c2 = repo.get_claim(claim_pending.claim_id)
    assert c1.status == ClaimStatus.CONTRADICTED
    assert c2.status == ClaimStatus.CONTRADICTED

    supported_claims = repo.list_claims(
        objective_id=sample_objective.objective_id, status=ClaimStatus.SUPPORTED
    )
    assert len(supported_claims) == 0


@pytest.mark.asyncio
async def test_verifier_resolves_temporal_supersession_against_existing_supported_claim(
    repo, sample_objective, sample_entity
):
    """Bug 1.2 Regression Test:

    Verify that a new pending claim superseding an older existing supported claim
    correctly updates the older claim to REFUTED and the new claim to SUPPORTED.
    """
    ev_old = Evidence(
        source_id="h_old",
        url="https://source.com/2021",
        passage="John Doe was appointed plant manager in 2021.",
        published_at=datetime(2021, 5, 1, tzinfo=UTC),
    )
    repo.save_evidence(ev_old)

    claim_old = Claim(
        subject_entity_id=sample_entity.entity_id,
        predicate="HAS_PLANT_MANAGER",
        object_value="John Doe",
        status=ClaimStatus.SUPPORTED,
        evidence_ids=[ev_old.evidence_id],
        confidence=0.92,
        objective_id=sample_objective.objective_id,
    )
    repo.save_claim(claim_old)

    ev_new = Evidence(
        source_id="h_new",
        url="https://source.com/2026",
        passage="Jane Smith is announced as new plant manager in 2026.",
        published_at=datetime(2026, 2, 1, tzinfo=UTC),
    )
    repo.save_evidence(ev_new)

    claim_new = Claim(
        subject_entity_id=sample_entity.entity_id,
        predicate="HAS_PLANT_MANAGER",
        object_value="Jane Smith",
        status=ClaimStatus.PENDING,
        evidence_ids=[ev_new.evidence_id],
        confidence=0.95,
        objective_id=sample_objective.objective_id,
    )
    repo.save_claim(claim_new)

    mock_payload = AdjudicationPayload(
        evaluations=[
            ClaimEvaluation(
                claim_id=claim_new.claim_id,
                status=ClaimStatus.SUPPORTED,
                confidence=0.97,
                verdict=VerdictType.SUPERSEDED,
                reasoning="2026 announcement supersedes 2021 record.",
            ),
            ClaimEvaluation(
                claim_id=claim_old.claim_id,
                status=ClaimStatus.REFUTED,
                confidence=0.1,
                verdict=VerdictType.SUPERSEDED,
                reasoning="Superseded by 2026 appointment.",
            ),
        ],
        has_conflict=False,
        summary_reasoning="Temporal progression resolved.",
    )

    mock_llm = MockLLMProvider(responses=[mock_payload])
    verifier = ExpertVerifier(repo=repo, llm=mock_llm)

    results = await verifier.adjudicate_pending_claims(
        objective_id=sample_objective.objective_id
    )

    assert len(results) == 1
    assert results[0].claims_supported == 1
    assert results[0].claims_refuted == 1

    assert repo.get_claim(claim_old.claim_id).status == ClaimStatus.REFUTED
    assert repo.get_claim(claim_new.claim_id).status == ClaimStatus.SUPPORTED


@pytest.mark.asyncio
async def test_verifier_corroborates_against_existing_supported_claim(
    repo, sample_objective, sample_entity
):
    """Bug 1.2 Regression Test:

    Verify that a new pending claim confirming an existing supported claim
    is corroborated via fast path, merging evidence without extra LLM cost.
    """
    ev1 = Evidence(
        source_id="h1",
        url="https://source-a.com/loc",
        passage="KTP is in Louisville, KY.",
    )
    repo.save_evidence(ev1)

    claim1 = Claim(
        subject_entity_id=sample_entity.entity_id,
        predicate="LOCATED_IN",
        object_value="Louisville, KY",
        status=ClaimStatus.SUPPORTED,
        evidence_ids=[ev1.evidence_id],
        confidence=0.9,
        objective_id=sample_objective.objective_id,
    )
    repo.save_claim(claim1)

    ev2 = Evidence(
        source_id="h2",
        url="https://source-b.com/loc",
        passage="Kentucky Truck Plant located in Louisville, KY.",
    )
    repo.save_evidence(ev2)

    claim2 = Claim(
        subject_entity_id=sample_entity.entity_id,
        predicate="LOCATED_IN",
        object_value="Louisville, KY",
        status=ClaimStatus.PENDING,
        evidence_ids=[ev2.evidence_id],
        confidence=0.9,
        objective_id=sample_objective.objective_id,
    )
    repo.save_claim(claim2)

    mock_llm = MockLLMProvider(responses=[])
    verifier = ExpertVerifier(repo=repo, llm=mock_llm)

    results = await verifier.adjudicate_pending_claims(
        objective_id=sample_objective.objective_id
    )

    assert len(results) == 1
    c1 = repo.get_claim(claim1.claim_id)
    c2 = repo.get_claim(claim2.claim_id)
    assert c1.status in (ClaimStatus.SUPPORTED, ClaimStatus.CORROBORATED)
    assert c2.status in (ClaimStatus.SUPPORTED, ClaimStatus.CORROBORATED)
    assert ev1.evidence_id in c2.evidence_ids
    assert ev2.evidence_id in c1.evidence_ids


@pytest.mark.asyncio
async def test_verifier_bounds_duplicate_claims_and_evidence_growth(
    repo, sample_objective, sample_entity
):
    """Bug 1.3 Regression Test:

    Verify that multiple duplicate agreeing claims across tasks have their evidence aggregated
    and bounded, and redundant claim rows are pruned to prevent O(N^2) memory explosion.
    """
    claims = []
    # Create 5 identical claims with different evidence sources
    for i in range(5):
        ev = Evidence(
            source_id=f"src_{i}",
            url=f"https://source-{i}.com",
            passage=f"Evidence passage {i}",
        )
        repo.save_evidence(ev)
        clm = Claim(
            subject_entity_id=sample_entity.entity_id,
            predicate="LOCATED_IN",
            object_value="Louisville, KY",
            status=ClaimStatus.PENDING,
            evidence_ids=[ev.evidence_id],
            confidence=0.9,
            objective_id=sample_objective.objective_id,
        )
        repo.save_claim(clm)
        claims.append(clm)

    mock_llm = MockLLMProvider(responses=[])
    verifier = ExpertVerifier(repo=repo, llm=mock_llm)

    results = await verifier.adjudicate_pending_claims(
        objective_id=sample_objective.objective_id
    )

    assert len(results) == 1
    assert results[0].claims_evaluated == 5

    # Verify redundant rows were pruned to bounded number (<= 2)
    remaining_claims = repo.list_claims(
        objective_id=sample_objective.objective_id,
        predicate="LOCATED_IN",
    )
    assert len(remaining_claims) == 2
    # Verify all 5 evidence IDs were merged into the retained claims without N^2 duplication
    for rem in remaining_claims:
        assert len(rem.evidence_ids) == 5
        assert rem.status in (ClaimStatus.SUPPORTED, ClaimStatus.CORROBORATED)
