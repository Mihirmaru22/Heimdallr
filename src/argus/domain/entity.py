import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


def generate_entity_id() -> str:
    return f"ent_{uuid.uuid4().hex[:8]}"


class Entity(BaseModel):
    """A real-world object discovered during research (Company, Facility, Person)."""

    entity_id: str = Field(default_factory=generate_entity_id)
    objective_id: str | None = Field(
        default=None, description="Parent research objective ID"
    )
    entity_type: str = Field(
        ...,
        min_length=1,
        description="Category of entity, e.g. company, facility, person",
    )
    canonical_name: str = Field(
        ..., min_length=1, description="Primary resolved name of the entity"
    )
    aliases: list[str] = Field(
        default_factory=list, description="Known alternative names or acronyms"
    )
    attributes: dict[str, Any] = Field(
        default_factory=dict, description="Arbitrary verified structured attributes"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="UTC creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC last updated timestamp",
    )
