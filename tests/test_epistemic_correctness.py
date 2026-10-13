import pytest
from unittest.mock import AsyncMock, patch
from datetime import UTC, datetime

from argus.brain.models import (
    DossierEntitySummary,
    ResearchDossier,
    StoppingEvaluation,
)
from argus.brain.planner import ResearchBrain
from argus.contact.resolver import ContactResolutionEngine
from argus.domain.claim import Claim, ClaimStatus
from argus.domain.entity import Entity
from argus.domain.evidence import Evidence
from argus.domain.objective import ResearchObjective
from argus.llm.mock import MockLLMProvider
from argus.storage.db import DatabaseManager
from argus.storage.repository import ArgusRepository
from argus.verifier.engine import (
    ExpertVerifier,
    check_claim_evidence_alignment,
)
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
        target="ABC Motors",
        target_type="company",
        intelligence_goal="Map plants, leadership, and contact intelligence.",
        required_fields=["plant_head", "facility", "air_permit"],
        success_criteria="Verify plant manager and operating facilities",
    )
    repo.save_objective(obj)
    return obj


@pytest.fixture
def plant_entity(repo, sample_objective):
    ent = Entity(
        canonical_name="Detroit Assembly Plant",
        entity_type="facility",
        aliases=["Detroit Plant", "DAP"],
        objective_id=sample_objective.objective_id,
    )
    repo.save_entity(ent)
    return ent


@pytest.fixture
def person_entity(repo, sample_objective):
    ent = Entity(
        canonical_name="John Smith",
        entity_type="person",
        aliases=["J. Smith"],
        objective_id=sample_objective.objective_id,
    )
    repo.save_entity(ent)
    return ent


# ==============================================================================
# Test 1 — Direct Evidence: Source explicitly states claim -> SUPPORTED
# ==============================================================================
@pytest.mark.asyncio
async def test_1_direct_evidence_becomes_supported(repo, sample_objective, plant_entity):
    ev = Evidence(
        source_id="sha256_direct",
        url="https://news.abcmotors.com/press/leadership",
        passage="John Smith was appointed Plant Manager of ABC Motors Detroit Assembly Plant.",
        confidence=0.95,
    )
    repo.save_evidence(ev)

    claim = Claim(
        objective_id=sample_objective.objective_id,
        subject_entity_id=plant_entity.entity_id,
        predicate="HAS_PLANT_MANAGER",
        object_value="John Smith",
        status=ClaimStatus.PENDING,
        confidence=0.90,
        evidence_ids=[ev.evidence_id],
    )
    repo.save_claim(claim)

    verifier = ExpertVerifier(repo=repo, llm=MockLLMProvider())
    results = await verifier.adjudicate_pending_claims(sample_objective.objective_id)

    assert len(results) == 1
    assert results[0].claims_supported == 1

    reloaded = repo.get_claim(claim.claim_id)
    assert reloaded is not None
    assert reloaded.status == ClaimStatus.SUPPORTED
    assert reloaded.confidence >= 0.85
    assert reloaded.is_verified() is True


# ==============================================================================
# Test 2 — Multiple Independent Sources -> CORROBORATED
# ==============================================================================
@pytest.mark.asyncio
async def test_2_multiple_independent_sources_becomes_corroborated(
    repo, sample_objective, plant_entity
):
    ev1 = Evidence(
        source_id="sha256_reuters",
        url="https://reuters.com/business/auto/detroit-plant-head",
        passage="Reuters reports John Smith serves as Plant Manager of Detroit Assembly Plant.",
        confidence=0.90,
    )
    ev2 = Evidence(
        source_id="sha256_autonews",
        url="https://autonews.com/operations/detroit-plant-head",
        passage="According to Automotive News, John Smith is the Plant Manager at Detroit Assembly Plant.",
        confidence=0.92,
    )
    repo.save_evidence(ev1)
    repo.save_evidence(ev2)

    claim = Claim(
        objective_id=sample_objective.objective_id,
        subject_entity_id=plant_entity.entity_id,
        predicate="HAS_PLANT_MANAGER",
        object_value="John Smith",
        status=ClaimStatus.PENDING,
        confidence=0.90,
        evidence_ids=[ev1.evidence_id, ev2.evidence_id],
    )
    repo.save_claim(claim)

    verifier = ExpertVerifier(repo=repo, llm=MockLLMProvider())
    results = await verifier.adjudicate_pending_claims(sample_objective.objective_id)

    assert len(results) == 1
    assert results[0].claims_corroborated == 1

    reloaded = repo.get_claim(claim.claim_id)
    assert reloaded is not None
    assert reloaded.status == ClaimStatus.CORROBORATED
    assert reloaded.is_verified() is True
    assert len(reloaded.evidence_ids) >= 2


# ==============================================================================
# Test 3 — Inferred Email: pattern derivation -> INFERRED, NOT SUPPORTED
# ==============================================================================
@pytest.mark.asyncio
async def test_3_inferred_email_is_inferred_not_supported(
    repo, sample_objective, person_entity
):
    # Entity represents John Smith
    company = Entity(
        canonical_name="ABC Motors",
        entity_type="company",
        attributes={"domain": "abcmotors.com", "primary_domain": "abcmotors.com"},
        objective_id=sample_objective.objective_id,
    )
    repo.save_entity(company)

    # Associate John Smith with ABC Motors
    repo.save_claim(
        Claim(
            objective_id=sample_objective.objective_id,
            subject_entity_id=person_entity.entity_id,
            predicate="WORKS_FOR",
            object_value="ABC Motors",
            status=ClaimStatus.SUPPORTED,
            confidence=0.95,
        )
    )

    engine = ContactResolutionEngine()
    with patch.object(engine, "verify_domain_mx", new_callable=AsyncMock, return_value=True):
        claims = await engine.resolve_contacts_for_objective(
            objective_id=sample_objective.objective_id,
            repo=repo,
            default_domain="abcmotors.com",
        )

    assert len(claims) >= 1
    inferred_email = next(c for c in claims if c.predicate.upper() in ("HAS_EMAIL", "EMAIL"))

    # Critical epistemic rules:
    # 1. Inferred email must NEVER be SUPPORTED
    assert inferred_email.status == ClaimStatus.INFERRED
    assert inferred_email.status != ClaimStatus.SUPPORTED
    assert inferred_email.is_inferred() is True
    # 2. Provenance derivation must be preserved
    assert inferred_email.derivation_method == "corporate_email_pattern"
    assert "john.smith@abcmotors.com" in inferred_email.object_value
    # 3. No fake evidence passages fabricated
    assert inferred_email.evidence_ids == []


# ==============================================================================
# Test 4 — Weak Evidence: Ambiguous directory result -> UNVERIFIED
# ==============================================================================
@pytest.mark.asyncio
async def test_4_weak_evidence_remains_unverified(repo, sample_objective, plant_entity):
    ev = Evidence(
        source_id="sha256_weak",
        url="https://generic-yellowpages.info/listing/992",
        passage="Unclaimed listing: DAP / Detroit Assembly might be managed by J. Smith or associate.",
        confidence=0.40,
    )
    repo.save_evidence(ev)

    claim = Claim(
        objective_id=sample_objective.objective_id,
        subject_entity_id=plant_entity.entity_id,
        predicate="HAS_PLANT_MANAGER",
        object_value="John Smith",
        status=ClaimStatus.PENDING,
        confidence=0.40,
        evidence_ids=[ev.evidence_id],
    )
    repo.save_claim(claim)

    mock_payload = AdjudicationPayload(
        evaluations=[
            ClaimEvaluation(
                claim_id=claim.claim_id,
                status=ClaimStatus.UNVERIFIED,
                confidence=0.40,
                verdict=VerdictType.INSUFFICIENT,
                reasoning="Directory entry is ambiguous and lacks official confirmation.",
            )
        ],
        has_conflict=False,
        summary_reasoning="Evidence too weak to establish plant manager.",
    )
    verifier = ExpertVerifier(repo=repo, llm=MockLLMProvider(responses=[mock_payload]))
    results = await verifier.adjudicate_pending_claims(sample_objective.objective_id)

    reloaded = repo.get_claim(claim.claim_id)
    assert reloaded is not None
    assert reloaded.status == ClaimStatus.UNVERIFIED
    assert reloaded.status != ClaimStatus.SUPPORTED


# ==============================================================================
# Test 5 — Missing Field: No evidence found -> UNKNOWN / NOT_FOUND
# ==============================================================================
def test_5_missing_field_is_unknown_or_not_found(repo, sample_objective):
    brain = ResearchBrain(repo=repo, llm=MockLLMProvider())

    # Before tasks run: epistemic status for missing fields is unknown
    eval_initial = brain.evaluate_stopping_criteria(sample_objective, tasks_executed=0)
    assert eval_initial.should_stop is False
    assert "air_permit" in eval_initial.missing_fields
    assert eval_initial.field_statuses.get("air_permit") == "unknown"

    # After tasks run without discovering evidence: epistemic status is not_found
    eval_investigated = brain.evaluate_stopping_criteria(sample_objective, tasks_executed=3)
    assert "air_permit" in eval_investigated.missing_fields
    assert eval_investigated.field_statuses.get("air_permit") == "not_found"
    assert eval_investigated.field_statuses.get("plant_head") == "not_found"


# ==============================================================================
# Test 6 — Contradiction: Conflicting credible sources -> CONTRADICTED
# ==============================================================================
@pytest.mark.asyncio
async def test_6_contradiction_between_sources_marks_contradicted(
    repo, sample_objective, plant_entity
):
    ev1 = Evidence(
        source_id="sha256_src1",
        url="https://source1.com/report",
        passage="Detroit Assembly Plant is managed by John Smith as of 2025.",
        confidence=0.9,
    )
    ev2 = Evidence(
        source_id="sha256_src2",
        url="https://source2.com/report",
        passage="Detroit Assembly Plant announced Robert Taylor has taken over as Plant Manager.",
        confidence=0.9,
    )
    repo.save_evidence(ev1)
    repo.save_evidence(ev2)

    claim1 = Claim(
        objective_id=sample_objective.objective_id,
        subject_entity_id=plant_entity.entity_id,
        predicate="HAS_PLANT_MANAGER",
        object_value="John Smith",
        status=ClaimStatus.PENDING,
        confidence=0.9,
        evidence_ids=[ev1.evidence_id],
    )
    claim2 = Claim(
        objective_id=sample_objective.objective_id,
        subject_entity_id=plant_entity.entity_id,
        predicate="HAS_PLANT_MANAGER",
        object_value="Robert Taylor",
        status=ClaimStatus.PENDING,
        confidence=0.9,
        evidence_ids=[ev2.evidence_id],
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
                reasoning="Conflicting plant manager reported in contemporary source.",
            ),
            ClaimEvaluation(
                claim_id=claim2.claim_id,
                status=ClaimStatus.CONTRADICTED,
                confidence=0.5,
                verdict=VerdictType.CONTRADICTION,
                reasoning="Conflicting plant manager reported in contemporary source.",
            ),
        ],
        has_conflict=True,
        summary_reasoning="Disputed plant manager figures between two industry reports.",
        suggested_disambiguation_tasks=[
            "Verify official plant manager for Detroit Assembly Plant"
        ],
    )
    verifier = ExpertVerifier(repo=repo, llm=MockLLMProvider(responses=[mock_payload]))
    results = await verifier.adjudicate_pending_claims(sample_objective.objective_id)

    assert len(results) == 1
    assert results[0].claims_contradicted == 2

    c1_reloaded = repo.get_claim(claim1.claim_id)
    c2_reloaded = repo.get_claim(claim2.claim_id)
    assert c1_reloaded.status == ClaimStatus.CONTRADICTED
    assert c2_reloaded.status == ClaimStatus.CONTRADICTED


# ==============================================================================
# Test 7 — Related-but-insufficient Evidence: Alignment check prevents false SUPPORTED
# ==============================================================================
@pytest.mark.asyncio
async def test_7_related_but_insufficient_evidence_cannot_be_supported(
    repo, sample_objective, plant_entity
):
    # Evidence proves company operates the plant, but says NOTHING about John Smith
    ev = Evidence(
        source_id="sha256_plant_only",
        url="https://abcmotors.com/locations",
        passage="ABC Motors operates the Detroit Assembly Plant for battery truck manufacturing.",
        confidence=0.95,
    )
    repo.save_evidence(ev)

    # Claim asserts John Smith is Plant Manager
    claim = Claim(
        objective_id=sample_objective.objective_id,
        subject_entity_id=plant_entity.entity_id,
        predicate="HAS_PLANT_MANAGER",
        object_value="John Smith",
        status=ClaimStatus.PENDING,
        confidence=0.88,
        evidence_ids=[ev.evidence_id],
    )
    repo.save_claim(claim)

    # Alignment check should explicitly fail because "John Smith" is absent from passage
    is_aligned, reason = check_claim_evidence_alignment(
        subject_name=plant_entity.canonical_name,
        subject_aliases=plant_entity.aliases,
        predicate=claim.predicate,
        object_value=claim.object_value,
        evidences=[ev],
    )
    assert is_aligned is False
    assert "does not support exact claim" in reason.lower()

    # Even if LLM attempted to mark it SUPPORTED, verifier engine catches misalignment
    hallucinated_payload = AdjudicationPayload(
        evaluations=[
            ClaimEvaluation(
                claim_id=claim.claim_id,
                status=ClaimStatus.SUPPORTED,
                confidence=0.9,
                verdict=VerdictType.DIRECT_SUPPORT,
                reasoning="Hallucinated confirmation without passage grounding",
            )
        ],
        has_conflict=False,
        summary_reasoning="Hallucinated confirmation without passage grounding",
    )
    verifier = ExpertVerifier(repo=repo, llm=MockLLMProvider(responses=[hallucinated_payload]))
    await verifier.adjudicate_pending_claims(sample_objective.objective_id)

    reloaded = repo.get_claim(claim.claim_id)
    assert reloaded.status != ClaimStatus.SUPPORTED
    assert reloaded.status == ClaimStatus.UNVERIFIED


# ==============================================================================
# Test 8 — Entity Match Does Not Imply Claim Support
# ==============================================================================
@pytest.mark.asyncio
async def test_8_entity_resolution_does_not_imply_claim_support(
    repo, sample_objective, person_entity
):
    # Create alias entity "Johnny Smith"
    alias_entity = Entity(
        canonical_name="Johnny Smith",
        entity_type="person",
        objective_id=sample_objective.objective_id,
    )
    repo.save_entity(alias_entity)

    # Associated ungrounded patent claim
    ev = Evidence(
        source_id="sha256_unrelated",
        url="https://abcmotors.com/news/smith",
        passage="Johnny Smith joined ABC Motors corporate communications team in Chicago.",
        confidence=0.9,
    )
    repo.save_evidence(ev)

    patent_claim = Claim(
        objective_id=sample_objective.objective_id,
        subject_entity_id=alias_entity.entity_id,
        predicate="INVENTED_PATENT",
        object_value="US-1029384-B2 Solid State Cathode",
        status=ClaimStatus.UNVERIFIED,
        confidence=0.85,
        evidence_ids=[ev.evidence_id],
    )
    repo.save_claim(patent_claim)

    # Perform entity merge
    repo.merge_entities(person_entity.entity_id, [alias_entity.entity_id])

    # Claim subject repointed, but claim MUST REMAIN UNVERIFIED
    reloaded_claim = repo.get_claim(patent_claim.claim_id)
    assert reloaded_claim.subject_entity_id == person_entity.entity_id
    assert reloaded_claim.status == ClaimStatus.UNVERIFIED
    assert reloaded_claim.status != ClaimStatus.SUPPORTED


# ==============================================================================
# Test 9 — Provenance Integrity: Inferred claims retain derivation, evidence immutable
# ==============================================================================
def test_9_provenance_integrity_and_derivation_separation(repo, sample_objective, person_entity):
    # Original source evidence
    original_text = "ABC Motors announced John Smith as Senior Director of Systems Engineering."
    ev = Evidence(
        source_id="sha256_source_clean",
        url="https://abcmotors.com/news/leadership",
        passage=original_text,
        confidence=0.95,
    )
    repo.save_evidence(ev)

    # Create an inferred claim with explicit derivation metadata
    inferred_claim = Claim(
        objective_id=sample_objective.objective_id,
        subject_entity_id=person_entity.entity_id,
        predicate="HAS_EMAIL",
        object_value="john.smith@abcmotors.com",
        status=ClaimStatus.INFERRED,
        confidence=0.70,
        derivation_method="corporate_email_pattern",
        derivation_inputs=["John Smith", "abcmotors.com", "{first}.{last}@{domain}"],
        inference_reason="Inferred from observed corporate domain pattern and canonical person name",
        evidence_ids=[],  # Never link raw source passage as if source stated the email!
    )
    repo.save_claim(inferred_claim)

    # Retrieve from DB and verify exact provenance retention
    reloaded_claim = repo.get_claim(inferred_claim.claim_id)
    assert reloaded_claim is not None
    assert reloaded_claim.status == ClaimStatus.INFERRED
    assert reloaded_claim.derivation_method == "corporate_email_pattern"
    assert "abcmotors.com" in reloaded_claim.derivation_inputs
    assert reloaded_claim.derivation["method"] == "corporate_email_pattern"

    # Original evidence passage must remain strictly immutable
    reloaded_ev = repo.get_evidence(ev.evidence_id)
    assert reloaded_ev is not None
    assert reloaded_ev.passage == original_text
    assert "john.smith@abcmotors.com" not in reloaded_ev.passage


# ==============================================================================
# Test 10 — Synthesis Preserves Epistemic Status (Qualifies Inferred / Unverified)
# ==============================================================================
@pytest.mark.asyncio
async def test_10_synthesis_preserves_epistemic_status_without_flattening(
    repo, sample_objective, plant_entity, person_entity
):
    # 1. Supported claim
    repo.save_claim(
        Claim(
            objective_id=sample_objective.objective_id,
            subject_entity_id=plant_entity.entity_id,
            predicate="HAS_LOCATION",
            object_value="Louisville, KY",
            status=ClaimStatus.SUPPORTED,
            confidence=0.95,
        )
    )

    # 2. Inferred claim
    repo.save_claim(
        Claim(
            objective_id=sample_objective.objective_id,
            subject_entity_id=person_entity.entity_id,
            predicate="HAS_EMAIL",
            object_value="john.smith@abcmotors.com",
            status=ClaimStatus.INFERRED,
            confidence=0.70,
            derivation_method="corporate_email_pattern",
            inference_reason="Derived corporate pattern",
        )
    )

    # 3. Unverified candidate claim
    repo.save_claim(
        Claim(
            objective_id=sample_objective.objective_id,
            subject_entity_id=plant_entity.entity_id,
            predicate="PLANT_SQUARE_FEET",
            object_value="4,500,000 sq ft",
            status=ClaimStatus.UNVERIFIED,
            confidence=0.50,
        )
    )

    brain = ResearchBrain(repo=repo, llm=MockLLMProvider())
    dossier = await brain.synthesize_dossier(
        objective=sample_objective,
        total_tasks=3,
        total_documents=2,
    )

    assert isinstance(dossier, ResearchDossier)

    # Entity summary partition check
    plant_summary = next(s for s in dossier.entities if s.entity.entity_id == plant_entity.entity_id)
    person_summary = next(s for s in dossier.entities if s.entity.entity_id == person_entity.entity_id)

    assert len(plant_summary.supported_claims) == 1
    assert len(plant_summary.unverified_claims) == 1
    assert len(person_summary.inferred_claims) == 1
    assert len(person_summary.supported_claims) == 0

    # Epistemic fields preserved in dossier
    assert "air_permit" in dossier.field_statuses
    assert dossier.field_statuses["air_permit"] == "not_found"

    # Executive summary preserves distinction between verified facts and derivations
    assert "inferred values" in dossier.executive_summary or "inferred" in dossier.executive_summary.lower()
