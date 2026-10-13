"""Heimdallr V2: Investigation Branch Management & Concurrency Control.

Manages isolated exploration lines (e.g. investigating multiple subsidiaries or executives concurrently):
- Prevents uncontrolled tree explosion with explicit branch step/cost budgets
- Tracks individual branch information yield
- Supports branch completion, abandonment, and knowledge merging
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid

from pydantic import BaseModel, Field


class BranchStatus(str, Enum):
    """Lifecycle statuses for an investigation branch."""

    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    ABANDONED = "ABANDONED"
    MERGED = "MERGED"


class InvestigationBranch(BaseModel):
    """An isolated line of research addressing a sub-goal or individual target entity."""

    branch_id: str = Field(default_factory=lambda: f"br_{uuid.uuid4().hex[:8]}")
    parent_branch_id: str | None = None
    purpose: str
    target_entity: str | None = None

    status: BranchStatus = BranchStatus.ACTIVE
    questions: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)

    cost_usd: float = 0.0
    cumulative_information_gain: float = 0.0
    step_budget: int = 6
    steps_taken: int = 0

    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str | None = None
    abandon_reason: str | None = None

    def can_continue(self) -> bool:
        """Return True if branch is active and within budget."""
        return self.status == BranchStatus.ACTIVE and self.steps_taken < self.step_budget

    def record_step(self, cost: float, gain: float, action_id: str | None = None) -> None:
        """Record resource consumption and information gain for a step."""
        self.steps_taken += 1
        self.cost_usd += cost
        self.cumulative_information_gain += gain
        if action_id and action_id not in self.actions:
            self.actions.append(action_id)

    def complete(self) -> None:
        """Mark branch successfully resolved."""
        self.status = BranchStatus.COMPLETED
        self.completed_at = datetime.now(timezone.utc).isoformat()

    def abandon(self, reason: str) -> None:
        """Abandon branch due to budget limit, dead-end, or low expected value."""
        self.status = BranchStatus.ABANDONED
        self.abandon_reason = reason
        self.completed_at = datetime.now(timezone.utc).isoformat()

    def merge_into_parent(self) -> None:
        """Mark branch merged into parent line."""
        self.status = BranchStatus.MERGED
        self.completed_at = datetime.now(timezone.utc).isoformat()
