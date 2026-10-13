import pytest
from pydantic import ValidationError

from argus.domain.task import ResearchTask, TaskStatus


def test_research_task_creation():
    task = ResearchTask(
        objective_id="obj_12345",
        title="Find Ford Kentucky Truck Plant address",
        description="Search official Ford site for Kentucky Truck Plant address",
    )
    assert task.task_id.startswith("tsk_")
    assert task.objective_id == "obj_12345"
    assert task.parent_task_id is None
    assert task.status == TaskStatus.READY
    assert task.priority == 1
    assert task.depth == 0
    assert task.retry_count == 0
    assert task.max_retries == 3
    assert task.error_message is None
    assert task.created_at is not None
    assert task.updated_at is not None


def test_research_subtask_creation():
    subtask = ResearchTask(
        objective_id="obj_12345",
        parent_task_id="tsk_parent99",
        title="Find IT leader for Plant X",
        description="Search press releases for IT leadership",
        priority=10,
        depth=1,
    )
    assert subtask.parent_task_id == "tsk_parent99"
    assert subtask.priority == 10
    assert subtask.depth == 1


def test_research_task_validation_errors():
    with pytest.raises(ValidationError):
        ResearchTask(
            objective_id="",
            title="Title",
            description="Desc",
        )

    with pytest.raises(ValidationError):
        ResearchTask(
            objective_id="obj_123",
            title="",
            description="Desc",
        )

    with pytest.raises(ValidationError):
        ResearchTask(
            objective_id="obj_123",
            title="Title",
            description="Desc",
            priority=150,  # exceeds max 100
        )
