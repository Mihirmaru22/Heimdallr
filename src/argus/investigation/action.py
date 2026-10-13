"""Heimdallr V2: Structured Research Action Model.

Represents discrete research operations chosen by the planner:
- Encapsulates rationale, expected information gain, and targeted evidence requirements
- Coordinates specialist activation and search queries
- Tracks execution status and audit provenance
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    """Categorical actions executed within an active investigation."""

    SEARCH = "SEARCH"
    FETCH = "FETCH"
    FOLLOW_LINK = "FOLLOW_LINK"
    QUERY_SOURCE = "QUERY_SOURCE"
    VERIFY_ENTITY = "VERIFY_ENTITY"
    VERIFY_CLAIM = "VERIFY_CLAIM"
    INVESTIGATE_SPECIALIST = "INVESTIGATE_SPECIALIST"
    INVESTIGATE_RELATIONSHIP = "INVESTIGATE_RELATIONSHIP"
    INVESTIGATE_TEMPORAL_STATE = "INVESTIGATE_TEMPORAL_STATE"
    SEEK_CONTRADICTION = "SEEK_CONTRADICTION"
    SEEK_PRIMARY_SOURCE = "SEEK_PRIMARY_SOURCE"
    STOP = "STOP"


class ResearchAction(BaseModel):
    """A planned and executable research step with expected gain and evidence objectives."""

    action_id: str = Field(default_factory=lambda: f"act_{uuid.uuid4().hex[:8]}")
    question_id: str | None = None
    hypothesis_id: str | None = None
    branch_id: str | None = None
    parent_action_id: str | None = None

    action_type: ActionType = ActionType.SEARCH
    rationale: str
    expected_information_gain: float = 0.5  # 0.0 to 1.0
    estimated_cost: float = 0.001

    specialist: str | None = None  # "identity", "infrastructure", "corporate", "none"
    capability_id: str | None = None  # e.g. "corporate_registry_intelligence"
    implementation_id: str | None = None  # e.g. "impl_corporate_registry_specialist_v1"
    target_entities: list[str] = Field(default_factory=list)
    query: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    evidence_requirements: list[str] = Field(default_factory=list)

    priority: float = 0.5
    status: str = "PENDING"  # PENDING, EXECUTED, FAILED, CANCELLED

    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    executed_at: str | None = None
    execution_result_summary: str | None = None

    def mark_executed(self, summary: str = "") -> None:
        """Mark action completed with summary of findings."""
        self.status = "EXECUTED"
        self.executed_at = datetime.now(timezone.utc).isoformat()
        self.execution_result_summary = summary

    def mark_failed(self, error_msg: str) -> None:
        """Mark action failed due to execution or retrieval error."""
        self.status = "FAILED"
        self.executed_at = datetime.now(timezone.utc).isoformat()
        self.execution_result_summary = f"ERROR: {error_msg}"
