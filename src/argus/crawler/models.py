import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


def generate_document_id() -> str:
    return f"doc_{uuid.uuid4().hex[:8]}"


def generate_crawl_request_id() -> str:
    return f"req_{uuid.uuid4().hex[:8]}"


class CrawlRequest(BaseModel):
    """A single web acquisition request representing a URL to fetch."""

    request_id: str = Field(
        default_factory=generate_crawl_request_id,
        description="Unique identifier for the crawl request",
    )
    url: str = Field(..., min_length=1, description="Target public URL to acquire")
    objective_id: str | None = Field(
        default=None, description="Linked ResearchObjective ID if known"
    )
    research_task_id: str | None = Field(
        default=None, description="Linked ResearchTask ID if known"
    )
    task_id: str | None = Field(
        default=None, description="Alias for research_task_id for backwards compatibility"
    )
    priority: int = Field(default=1, ge=1, le=100, description="Queue priority")
    depth: int = Field(default=0, ge=0, description="Crawl depth from seed request")
    max_retries: int = Field(
        default=2, ge=0, description="Maximum retry attempts on network error"
    )
    retry_count: int = Field(
        default=0, ge=0, description="Current retry attempt number"
    )
    force_browser: bool = Field(
        default=False,
        description="Whether to skip HTTP and force Playwright browser rendering",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Custom crawl request metadata"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp of the request",
    )

    def model_post_init(self, context: Any) -> None:
        super().model_post_init(context)
        if not self.research_task_id and self.task_id:
            self.research_task_id = self.task_id
        elif not self.task_id and self.research_task_id:
            self.task_id = self.research_task_id

    @property
    def creation_time(self) -> datetime:
        return self.created_at

    def to_crawlee_request(self) -> Any:
        """Convert this domain CrawlRequest into a Crawlee Request instance."""
        from crawlee import Request
        from argus.search.pipeline import SearchPipeline

        unique_key = SearchPipeline.normalize_url(self.url)
        return Request.from_url(
            url=self.url,
            unique_key=unique_key,
            user_data={
                "request_id": self.request_id,
                "objective_id": self.objective_id,
                "research_task_id": self.research_task_id,
                "task_id": self.task_id,
                "priority": self.priority,
                "depth": self.depth,
                "force_browser": self.force_browser,
                "max_retries": self.max_retries,
                "retry_count": self.retry_count,
                "metadata": self.metadata,
                "created_at": self.created_at.isoformat(),
            },
        )

    @classmethod
    def from_crawlee_request(cls, req: Any) -> "CrawlRequest":
        """Instantiate a domain CrawlRequest from a Crawlee Request instance."""
        u_data = req.user_data or {}
        if hasattr(u_data, "model_dump"):
            u_dict = u_data.model_dump()
        elif hasattr(u_data, "__dict__"):
            u_dict = vars(u_data)
        elif isinstance(u_data, dict):
            u_dict = u_data
        else:
            u_dict = {}

        created_at_val = u_dict.get("created_at")
        if created_at_val and isinstance(created_at_val, str):
            try:
                created_at_dt = datetime.fromisoformat(created_at_val)
            except Exception:
                created_at_dt = datetime.now(UTC)
        elif isinstance(created_at_val, datetime):
            created_at_dt = created_at_val
        else:
            created_at_dt = datetime.now(UTC)

        return cls(
            request_id=u_dict.get("request_id") or generate_crawl_request_id(),
            url=req.url,
            objective_id=u_dict.get("objective_id"),
            research_task_id=u_dict.get("research_task_id") or u_dict.get("task_id"),
            task_id=u_dict.get("task_id") or u_dict.get("research_task_id"),
            priority=u_dict.get("priority", 1),
            depth=u_dict.get("depth", 0),
            max_retries=u_dict.get("max_retries", 2),
            retry_count=req.retry_count if hasattr(req, "retry_count") else u_dict.get("retry_count", 0),
            force_browser=bool(u_dict.get("force_browser", False)),
            metadata=u_dict.get("metadata", {}),
            created_at=created_at_dt,
        )


def generate_unit_id() -> str:
    return f"unit_{uuid.uuid4().hex[:8]}"


class ContentUnit(BaseModel):
    """A discrete, structured segment of a document (heading, paragraph, table, list item)."""

    unit_id: str = Field(default_factory=generate_unit_id)
    document_id: str = Field(..., description="ID of parent Document")
    unit_type: str = Field(
        ...,
        description="Type of structural unit: 'heading', 'paragraph', 'table', 'list_item'",
    )
    sequence: int = Field(default=0, ge=0, description="Sequential index within document")
    heading_level: int | None = Field(
        default=None, ge=1, le=6, description="Heading level (1-6) if unit is a heading"
    )
    section_title: str | None = Field(
        default=None, description="Title of the immediate enclosing section/heading"
    )
    text: str = Field(default="", description="Substantive text content of this unit")
    char_start: int | None = Field(
        default=None, ge=0, description="Start offset within parent document text_content"
    )
    char_end: int | None = Field(
        default=None, ge=0, description="End offset within parent document text_content"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Custom metadata (e.g. table headers, row count)"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC creation timestamp",
    )


class Document(BaseModel):
    """A clean, processed text document ready for information extraction."""

    document_id: str = Field(default_factory=generate_document_id)
    url: str = Field(..., min_length=1, description="Final resolved destination URL")
    canonical_url: str | None = Field(
        default=None, description="Canonical URL if specified by metadata or normalization"
    )
    title: str = Field(default="", description="Extracted webpage title")
    text_content: str = Field(
        default="", description="Cleaned, substantive body text without boilerplate"
    )
    status_code: int = Field(default=200, description="HTTP response status code")
    content_hash: str = Field(
        default="", description="Cryptographic SHA-256 hash of cleaned text"
    )
    fetch_method: str = Field(
        default="http",
        description="Acquisition technique: 'http', 'browser', or 'blocked'",
    )
    fetched_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp of content retrieval",
    )
    published_at: datetime | None = Field(
        default=None,
        description="UTC timestamp of content publication if known",
    )
    crawl_request_id: str | None = Field(
        default=None,
        description="Originating CrawlRequest ID for provenance tracking",
    )
    task_id: str | None = Field(
        default=None,
        description="Originating ResearchTask ID for provenance tracking",
    )
    objective_id: str | None = Field(
        default=None,
        description="Originating ResearchObjective ID for provenance tracking",
    )
    content_units: list[ContentUnit] = Field(
        default_factory=list, description="Ordered sequence of structural content units"
    )
    outgoing_links: list[dict[str, Any]] = Field(
        default_factory=list, description="Extracted hyperlinks with anchor text and unit references"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Document metadata (JSON-LD, open graph, description)"
    )

    def model_post_init(self, context: Any) -> None:
        """Automatically compute SHA-256 content_hash if text_content exists."""
        super().model_post_init(context)
        if not self.content_hash and self.text_content:
            self.content_hash = hashlib.sha256(
                self.text_content.encode("utf-8")
            ).hexdigest()

    @property
    def research_task_id(self) -> str | None:
        return self.task_id

    def get_unit_by_id(self, unit_id: str) -> ContentUnit | None:
        """Find a ContentUnit by unit_id."""
        for u in self.content_units:
            if u.unit_id == unit_id:
                return u
        return None

    def find_unit_for_offset(self, offset: int) -> ContentUnit | None:
        """Find the ContentUnit containing the given character offset in text_content."""
        for u in self.content_units:
            if u.char_start is not None and u.char_end is not None:
                if u.char_start <= offset < u.char_end or (offset == u.char_end and offset > u.char_start):
                    return u
        return None
