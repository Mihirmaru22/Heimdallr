import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Types of auditable events emitted across the Argus lifecycle."""

    RESEARCH_STARTED = "research_started"
    RESEARCH_STOPPED = "research_stopped"
    STAGE_STARTED = "stage_started"
    STAGE_COMPLETED = "stage_completed"

    TASK_CREATED = "task_created"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"

    SEARCH_EXECUTED = "search_executed"
    CRAWL_STARTED = "crawl_started"
    CRAWL_COMPLETED = "crawl_completed"
    CRAWL_REQUEST_CREATED = "crawl_request_created"
    CRAWL_REQUEST_ENQUEUED = "crawl_request_enqueued"
    CRAWL_REQUEST_STARTED = "crawl_request_started"
    CRAWL_REQUEST_SUCCEEDED = "crawl_request_succeeded"
    CRAWL_REQUEST_FAILED = "crawl_request_failed"
    CRAWL_REQUEST_RECLAIMED = "crawl_request_reclaimed"
    CRAWL_REQUEST_REJECTED = "crawl_request_rejected"
    CRAWL_REQUEST_SKIPPED = "crawl_request_skipped"
    DOCUMENT_CREATED = "document_created"

    ENTITY_EXTRACTED = "entity_extracted"
    CLAIM_CREATED = "claim_created"
    EVIDENCE_ATTACHED = "evidence_attached"

    VERIFICATION_STARTED = "verification_started"
    VERIFICATION_COMPLETED = "verification_completed"
    CONTRADICTION_DETECTED = "contradiction_detected"


def generate_event_id() -> str:
    return f"evt_{uuid.uuid4().hex[:8]}"


class ResearchEvent(BaseModel):
    """An immutable audit event recording an action during research."""

    event_id: str = Field(default_factory=generate_event_id)
    objective_id: str = Field(
        ..., min_length=1, description="Parent research objective ID"
    )
    task_id: str | None = Field(
        default=None, description="Task ID if event occurred within a task context"
    )
    event_type: EventType = Field(..., description="Category of event")
    payload: dict[str, Any] = Field(
        default_factory=dict, description="Structured event metadata or payload"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC event creation timestamp",
    )
