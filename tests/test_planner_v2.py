"""Unit tests for ArgusPlannerV2 (OpenPlanter absorption)."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from argus.brain.models import TaskPlanningPayload, PlannedTask
from argus.brain.planner_v2 import ArgusPlannerV2, PlannedTaskV2, TaskPlanningPayloadV2
from argus.storage.db import DatabaseManager
from argus.domain.claim import Claim, ClaimStatus
from argus.domain.entity import Entity
from argus.domain.objective import ResearchObjective
from argus.domain.task import ResearchTask, TaskStatus
from argus.storage.repository import ArgusRepository


@pytest.fixture
def repo():
    db = DatabaseManager(":memory:")
    return ArgusRepository(db)


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.generate_structured = AsyncMock()
    return llm


@pytest.mark.asyncio
async def test_planner_v2_initial_tasks_has_acceptance_criteria(repo, mock_llm):
    mock_llm.generate_structured.return_value = TaskPlanningPayloadV2(
        planned_tasks=[
            PlannedTaskV2(
                title="Investigate Kentucky Truck Plant operations",
                target_entity="Kentucky Truck Plant",
                required_output="plant_manager, location, vehicles_produced",
                acceptance_criteria="Identified verified plant manager and vehicles produced for Kentucky Truck Plant.",
                description="Map plant leadership and production specs.",
                search_queries=[
                    "Kentucky Truck Plant plant manager official",
                    "Kentucky Truck Plant vehicles produced",
                ],
                priority=9,
                max_search_budget=3,
            )
        ],
        strategic_rationale="Focused facility investigation.",
    )

    planner = ArgusPlannerV2(repo=repo, llm=mock_llm, max_queries_per_task=3)
    objective = ResearchObjective(
        objective_id="obj_test_1",
        target="Kentucky Truck Plant",
        target_type="assembly_plant",
        intelligence_goal="Map plant leadership",
        required_fields=["plant_manager", "location"],
        success_criteria="Verify plant manager",
    )
    repo.save_objective(objective)

    tasks = await planner.plan_initial_tasks(objective)
    assert len(tasks) == 1
    task = tasks[0]
    assert "Acceptance Criteria:" in task.description
    assert "Target Entity: Kentucky Truck Plant" in task.description
    assert "Max Search Budget: 3" in task.description
    assert task.depth == 0

    # Verify query extraction bounds
    queries = planner.extract_search_queries(task, objective_target="Kentucky Truck Plant")
    assert len(queries) <= 3
    assert "Kentucky Truck Plant plant manager official" in queries


@pytest.mark.asyncio
async def test_planner_v2_preserves_facility_fan_out(repo, mock_llm):
    planner = ArgusPlannerV2(repo=repo, llm=mock_llm, max_depth=2)
    objective = ResearchObjective(
        objective_id="obj_fan_out",
        target="Ford Motor Company",
        target_type="company",
        intelligence_goal="Discover facilities and leadership",
        required_fields=["facility", "plant_manager"],
        success_criteria="Verify plants and managers",
        max_tasks=10,
        max_depth=2,
    )
    repo.save_objective(objective)

    # Discovered facility in repo
    fac = Entity(
        entity_id="ent_boc_1",
        objective_id=objective.objective_id,
        entity_type="assembly_plant",
        canonical_name="BlueOval City",
    )
    repo.save_entity(fac)

    parent_task = ResearchTask(
        task_id="tsk_root",
        objective_id=objective.objective_id,
        title="Root Investigation",
        description="Root",
        depth=0,
    )
    repo.save_task(parent_task)

    # Spawning followup tasks for missing plant_manager
    followups = await planner.plan_followup_tasks(
        objective=objective,
        missing_fields=["plant_manager"],
        disambiguation_tasks=[],
        parent_task=parent_task,
    )

    assert len(followups) == 1
    fac_task = followups[0]
    assert "BlueOval City" in fac_task.title
    assert "Acceptance Criteria:" in fac_task.description
    assert fac_task.depth == 1
    assert fac_task.parent_task_id == "tsk_root"


@pytest.mark.asyncio
async def test_planner_v2_bounds_recursion_at_max_depth(repo, mock_llm):
    planner = ArgusPlannerV2(repo=repo, llm=mock_llm, max_depth=2)
    objective = ResearchObjective(
        objective_id="obj_depth",
        target="Ford",
        target_type="company",
        intelligence_goal="History",
        required_fields=["history"],
        success_criteria="Verify history",
        max_depth=2,
    )

    deep_task = ResearchTask(
        task_id="tsk_deep",
        objective_id=objective.objective_id,
        title="Deep Task",
        description="Deep",
        depth=2,  # Already at max_depth
    )

    followups = await planner.plan_followup_tasks(
        objective=objective,
        missing_fields=["history"],
        disambiguation_tasks=["Contradiction query"],
        parent_task=deep_task,
    )
    assert len(followups) == 0  # Bounded, stops recursion!
