import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field


def generate_objective_id() -> str:
    return f"obj_{uuid.uuid4().hex[:8]}"


class ResearchObjective(BaseModel):
    """The root research objective driving an Argus investigation."""

    objective_id: str = Field(default_factory=generate_objective_id)
    target: str = Field(
        ..., min_length=1, description="Entity or industry being researched"
    )
    target_type: str = Field(
        ...,
        min_length=1,
        description="Category of target, e.g. company, industry, facility",
    )
    intelligence_goal: str = Field(
        ..., min_length=1, description="High-level research intent/question"
    )
    required_fields: list[str] = Field(
        ...,
        min_length=1,
        description="Mandatory data points needed to satisfy the goal",
    )
    success_criteria: str = Field(
        ...,
        min_length=1,
        description="Evaluation condition determining when research is sufficient",
    )
    max_tasks: int = Field(
        default=50, gt=0, description="Operational safety limit on total tasks allowed"
    )
    max_depth: int = Field(
        default=3, ge=1, description="Maximum task tree recursion depth"
    )
    dynamic_budget: bool = Field(
        default=True,
        description="Whether to dynamically calibrate task budget and depth via Laya",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp when research was initiated",
    )
