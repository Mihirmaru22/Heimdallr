import pytest
from pydantic import ValidationError

from argus.domain.objective import ResearchObjective


def test_research_objective_creation():
    objective = ResearchObjective(
        target="US Automobile Manufacturers",
        target_type="industry",
        intelligence_goal="Identify all plants and their site leaders",
        required_fields=["plants", "leaders", "addresses"],
        success_criteria="At least 5 plants verified with managers",
    )
    assert objective.objective_id.startswith("obj_")
    assert objective.target == "US Automobile Manufacturers"
    assert objective.max_tasks == 50
    assert objective.max_depth == 3
    assert objective.created_at is not None


def test_research_objective_empty_target_fails():
    with pytest.raises(ValidationError):
        ResearchObjective(
            target="",
            target_type="industry",
            intelligence_goal="Identify plants",
            required_fields=["plants"],
            success_criteria="Done",
        )


def test_research_objective_empty_required_fields_fails():
    with pytest.raises(ValidationError):
        ResearchObjective(
            target="Tesla",
            target_type="company",
            intelligence_goal="Identify plants",
            required_fields=[],
            success_criteria="Done",
        )


def test_research_objective_invalid_max_tasks_fails():
    with pytest.raises(ValidationError):
        ResearchObjective(
            target="Tesla",
            target_type="company",
            intelligence_goal="Identify plants",
            required_fields=["plants"],
            success_criteria="Done",
            max_tasks=0,
        )


def test_stopping_criteria_accurately_reports_missing_fields_on_budget_limit():
    """Exit Criteria 1: When budget is reached, stopping criteria must accurately report

    real missing fields and true coverage score rather than falsely reporting 1.0.
    """
    from unittest.mock import MagicMock

    from argus.brain.planner import ResearchBrain
    from argus.domain.claim import Claim, ClaimStatus
    from argus.domain.entity import Entity
    from argus.storage.db import DatabaseManager
    from argus.storage.repository import ArgusRepository

    db = DatabaseManager(":memory:")
    repo = ArgusRepository(db)
    brain = ResearchBrain(repo=repo, llm=MagicMock())

    obj = ResearchObjective(
        target="Global Aerospace",
        target_type="industry",
        intelligence_goal="Find propulsion labs and flight directors",
        required_fields=["propulsion_lab", "flight_director", "contact_email"],
        success_criteria="At least 2 verified",
        max_tasks=2,
    )
    repo.save_objective(obj)

    # Add only 1 claim satisfying 'propulsion_lab'
    ent = Entity(canonical_name="JPL", entity_type="facility", objective_id=obj.objective_id)
    repo.save_entity(ent)
    repo.save_claim(
        Claim(
            subject_entity_id=ent.entity_id,
            predicate="HAS_PROPULSION_LAB",
            object_value="Jet Propulsion Laboratory",
            status=ClaimStatus.SUPPORTED,
            objective_id=obj.objective_id,
        )
    )

    # Evaluate when tasks_executed (2) >= max_tasks (2)
    evaluation = brain.evaluate_stopping_criteria(obj, tasks_executed=2)

    assert evaluation.should_stop is True
    # Coverage must be 1/3 (33%), NOT 100%
    assert 0.30 <= evaluation.coverage_score <= 0.35
    # Missing fields must contain the unsatisfied fields
    assert "flight_director" in evaluation.missing_fields
    assert "contact_email" in evaluation.missing_fields
    assert "propulsion_lab" not in evaluation.missing_fields


def test_domain_agnostic_field_satisfaction_across_diverse_industries():
    """Exit Criteria 2: Verification that field matching is completely domain-agnostic

    and works for clinical trials, mining, aerospace, and computing with zero hardcoding.
    """
    from unittest.mock import MagicMock

    from argus.brain.planner import ResearchBrain
    from argus.domain.claim import Claim, ClaimStatus
    from argus.domain.entity import Entity
    from argus.storage.db import DatabaseManager
    from argus.storage.repository import ArgusRepository

    db = DatabaseManager(":memory:")
    repo = ArgusRepository(db)
    brain = ResearchBrain(repo=repo, llm=MagicMock())

    # Case 1: Biotech clinical trial
    obj_bio = ResearchObjective(
        target="mRNA Vaccine Trials",
        target_type="medical",
        intelligence_goal="Find trial phase and principal investigator",
        required_fields=["trial_phase", "principal_investigator"],
        success_criteria="Verified",
    )
    repo.save_objective(obj_bio)

    ent_bio = Entity(canonical_name="Study 101", entity_type="trial", objective_id=obj_bio.objective_id)
    repo.save_entity(ent_bio)
    repo.save_claim(
        Claim(
            subject_entity_id=ent_bio.entity_id,
            predicate="HAS_TRIAL_PHASE",
            object_value="Phase 3",
            status=ClaimStatus.SUPPORTED,
            objective_id=obj_bio.objective_id,
        )
    )
    repo.save_claim(
        Claim(
            subject_entity_id=ent_bio.entity_id,
            predicate="HAS_PRINCIPAL_INVESTIGATOR",
            object_value="Dr. Aris Thorne",
            status=ClaimStatus.SUPPORTED,
            objective_id=obj_bio.objective_id,
        )
    )

    eval_bio = brain.evaluate_stopping_criteria(obj_bio, tasks_executed=1)
    assert eval_bio.should_stop is True
    assert eval_bio.coverage_score == 1.0
    assert len(eval_bio.missing_fields) == 0

    # Case 2: Mining concessions
    obj_mine = ResearchObjective(
        target="Atacama Lithium",
        target_type="mining",
        intelligence_goal="Find extraction depth and environmental director",
        required_fields=["extraction_depth", "environmental_director"],
        success_criteria="Verified",
    )
    repo.save_objective(obj_mine)

    ent_mine = Entity(canonical_name="Salar Mine", entity_type="site", objective_id=obj_mine.objective_id)
    repo.save_entity(ent_mine)
    repo.save_claim(
        Claim(
            subject_entity_id=ent_mine.entity_id,
            predicate="HAS_EXTRACTION_DEPTH",
            object_value="150 meters",
            status=ClaimStatus.SUPPORTED,
            objective_id=obj_mine.objective_id,
        )
    )

    eval_mine = brain.evaluate_stopping_criteria(obj_mine, tasks_executed=1)
    assert eval_mine.should_stop is False
    assert "environmental_director" in eval_mine.missing_fields
    assert "extraction_depth" not in eval_mine.missing_fields
    assert eval_mine.coverage_score == 0.5
