import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field


def generate_evidence_id() -> str:
    return f"evi_{uuid.uuid4().hex[:8]}"


class Evidence(BaseModel):
    """Verifiable proof and citation backing a factual claim."""

    evidence_id: str = Field(default_factory=generate_evidence_id)
    source_id: str = Field(
        ..., min_length=1, description="Origin document or raw source ID"
    )
    url: str = Field(
        ..., min_length=1, description="Public web URL where the passage was discovered"
    )
    passage: str = Field(
        ...,
        min_length=1,
        description="Verbatim snippet/quote extracted from the source",
    )
    char_start: int | None = Field(
        default=None, ge=0, description="Character start offset in source document"
    )
    char_end: int | None = Field(
        default=None, ge=0, description="Character end offset in source document"
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Epistemic extraction confidence (0.0 to 1.0)",
    )
    retrieved_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp when content was retrieved",
    )
    published_at: datetime | None = Field(
        default=None,
        description="Publication timestamp when available from document metadata",
    )
    document_id: str | None = Field(
        default=None,
        description="Explicit ID of the source Document",
    )
    unit_id: str | None = Field(
        default=None,
        description="Explicit ID of the source ContentUnit within the document",
    )
    content_hash: str | None = Field(
        default=None,
        description="Cryptographic hash of the source content",
    )
    canonical_url: str | None = Field(
        default=None,
        description="Canonical URL of the source document",
    )
