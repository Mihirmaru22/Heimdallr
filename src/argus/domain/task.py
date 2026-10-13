import uuid
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Execution lifecycle states for a research task."""

    READY = "ready"  # Ready to be claimed by a worker
    RUNNING = "running"  # Currently executing
    COMPLETED = "completed"  # Successfully finished
    FAILED = "failed"  # Failed during execution
    BLOCKED = "blocked"  # Waiting on a parent task dependency
    CANCELLED = "cancelled"  # Aborted or cancelled


def generate_task_id() -> str:
    return f"tsk_{uuid.uuid4().hex[:8]}"


class ResearchTask(BaseModel):
    """An atomic, executable research assignment."""

    task_id: str = Field(default_factory=generate_task_id)
    objective_id: str = Field(
        ..., min_length=1, description="Parent research objective ID"
    )
    parent_task_id: str | None = Field(
        default=None, description="Parent task ID if subtask, otherwise None"
    )
    title: str = Field(
        ...,
        min_length=1,
        description="Short human-readable title of expected discovery",
    )
    description: str = Field(
        ..., min_length=1, description="Detailed instructions for the worker"
    )
    status: TaskStatus = Field(default=TaskStatus.READY, description="Lifecycle status")
    priority: int = Field(
        default=1, ge=1, le=100, description="Queue priority (1 lowest, 100 highest)"
    )
    depth: int = Field(
        default=0, ge=0, description="Task tree depth (root tasks are 0)"
    )
    retry_count: int = Field(
        default=0, ge=0, description="Number of execution retries attempted"
    )
    max_retries: int = Field(default=3, ge=0, description="Maximum allowable retries")
    error_message: str | None = Field(
        default=None, description="Error reason if task failed"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="UTC creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC last updated timestamp",
    )
