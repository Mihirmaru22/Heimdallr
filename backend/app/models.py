"""SQLAlchemy models. Tenant tables carry org_id and are protected by row-level security."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin, new_id, utcnow

UUIDPK = UUID(as_uuid=True)


def org_fk() -> Mapped[uuid.UUID]:
    return mapped_column(UUIDPK, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)


class Role(StrEnum):
    owner = "owner"
    admin = "admin"
    member = "member"


ROLE_RANK = {Role.member: 1, Role.admin: 2, Role.owner: 3}


class JobState(StrEnum):
    created = "created"
    validating = "validating"
    planning = "planning"
    queued = "queued"
    running = "running"
    waiting_quota = "waiting_quota"
    validating_results = "validating_results"
    exporting = "exporting"
    completed = "completed"
    partially_completed = "partially_completed"
    failed = "failed"
    cancel_requested = "cancel_requested"
    cancelled = "cancelled"


class UrlStatus(StrEnum):
    queued = "queued"
    in_progress = "in_progress"
    fetched = "fetched"
    skipped = "skipped"  # out of scope, duplicate content, non-HTML
    blocked_robots = "blocked_robots"
    blocked_policy = "blocked_policy"  # SSRF guard or domain denylist
    failed = "failed"  # will be retried
    dead = "dead"  # retries exhausted (dead letter)


# --- identity and tenancy ---------------------------------------------------------------------


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(UUIDPK, primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    max_active_jobs: Mapped[int | None] = mapped_column(Integer)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    # Only the SHA-256 of the cookie value is stored, so a database leak does not leak sessions.
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUIDPK, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ip: Mapped[str] = mapped_column(String(64), default="")


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(320), index=True)  # email or ip
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"
    id: Mapped[uuid.UUID] = mapped_column(UUIDPK, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # Overrides that can only lower the platform limits, e.g. {"max_pages_per_job": 500}.
    limits: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    retention_days: Mapped[int | None] = mapped_column(Integer)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Membership(TimestampMixin, Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (UniqueConstraint("org_id", "user_id"),)
    id: Mapped[uuid.UUID] = mapped_column(UUIDPK, primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = org_fk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUIDPK, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)


# --- projects and jobs ------------------------------------------------------------------------


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    id: Mapped[uuid.UUID] = mapped_column(UUIDPK, primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = org_fk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUIDPK, ForeignKey("users.id", ondelete="SET NULL"))


class ExtractionSchema(TimestampMixin, Base):
    __tablename__ = "extraction_schemas"
    __table_args__ = (UniqueConstraint("project_id", "version"),)
    id: Mapped[uuid.UUID] = mapped_column(UUIDPK, primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = org_fk()
    project_id: Mapped[uuid.UUID] = mapped_column(UUIDPK, ForeignKey("projects.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    nl_request: Mapped[str] = mapped_column(Text, default="", nullable=False)
    spec: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)  # draft|confirmed
    interpreter: Mapped[str] = mapped_column(String(64), default="rules", nullable=False)


class CrawlJob(TimestampMixin, Base):
    __tablename__ = "crawl_jobs"
    __table_args__ = (
        UniqueConstraint("org_id", "idempotency_key"),
        Index("ix_crawl_jobs_org_state_created", "org_id", "state", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUIDPK, primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = org_fk()
    project_id: Mapped[uuid.UUID] = mapped_column(UUIDPK, ForeignKey("projects.id", ondelete="CASCADE"))
    schema_id: Mapped[uuid.UUID] = mapped_column(UUIDPK, ForeignKey("extraction_schemas.id"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUIDPK, ForeignKey("users.id", ondelete="SET NULL"))
    state: Mapped[str] = mapped_column(String(32), default=JobState.created, nullable=False)
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    counters: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lock_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class CrawlJobEvent(Base):
    __tablename__ = "crawl_job_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[uuid.UUID] = org_fk()
    job_id: Mapped[uuid.UUID] = mapped_column(UUIDPK, ForeignKey("crawl_jobs.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)  # transition|info|warning|error
    from_state: Mapped[str | None] = mapped_column(String(32))
    to_state: Mapped[str | None] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DiscoveredUrl(Base):
    __tablename__ = "discovered_urls"
    __table_args__ = (
        UniqueConstraint("job_id", "url_hash"),
        Index("ix_discovered_urls_frontier", "job_id", "status", "priority"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUIDPK, primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = org_fk()
    job_id: Mapped[uuid.UUID] = mapped_column(UUIDPK, ForeignKey("crawl_jobs.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(Text, nullable=False)
    url_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    referrer_url: Mapped[str | None] = mapped_column(Text)
    method: Mapped[str] = mapped_column(String(32), nullable=False)  # seed|sitemap|link|wikidata|gleif...
    depth: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)  # lower runs first
    status: Mapped[str] = mapped_column(String(32), default=UrlStatus.queued, nullable=False)
    status_reason: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Optional hint carried from discovery (e.g. the company name a registry gave this website).
    hint: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FetchedPage(Base):
    __tablename__ = "fetched_pages"
    __table_args__ = (Index("ix_fetched_pages_job_hash", "job_id", "content_hash"),)
    id: Mapped[uuid.UUID] = mapped_column(UUIDPK, primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = org_fk()
    job_id: Mapped[uuid.UUID] = mapped_column(UUIDPK, ForeignKey("crawl_jobs.id", ondelete="CASCADE"))
    url_id: Mapped[uuid.UUID] = mapped_column(
        UUIDPK, ForeignKey("discovered_urls.id", ondelete="CASCADE"), unique=True
    )
    final_url: Mapped[str] = mapped_column(Text, nullable=False)
    http_status: Mapped[int] = mapped_column(Integer, nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    fetch_mode: Mapped[str] = mapped_column(String(16), default="http", nullable=False)
    title: Mapped[str] = mapped_column(Text, default="", nullable=False)
    text_excerpt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Deterministic extraction output for this page: {field: [candidate, ...]}. Records are
    # assembled from these, so a job can be re-finalized without fetching pages again.
    candidates: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class ExtractedRecord(TimestampMixin, Base):
    __tablename__ = "extracted_records"
    __table_args__ = (UniqueConstraint("job_id", "dedupe_key"),)
    id: Mapped[uuid.UUID] = mapped_column(UUIDPK, primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = org_fk()
    job_id: Mapped[uuid.UUID] = mapped_column(UUIDPK, ForeignKey("crawl_jobs.id", ondelete="CASCADE"), index=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="partial", nullable=False)  # valid|partial|invalid
    quality_score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    excluded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    user_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_urls: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)


class FieldValue(Base):
    """Provenance for one field of one record: where it came from and how sure we are."""

    __tablename__ = "extraction_field_values"
    __table_args__ = (Index("ix_field_values_record", "record_id", "field_name"),)
    id: Mapped[uuid.UUID] = mapped_column(UUIDPK, primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = org_fk()
    record_id: Mapped[uuid.UUID] = mapped_column(
        UUIDPK, ForeignKey("extracted_records.id", ondelete="CASCADE"), nullable=False
    )
    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[Any] = mapped_column(JSONB)
    # found | absent (looked, not on the page) | not_extracted (could not determine) | invalid
    value_status: Mapped[str] = mapped_column(String(16), nullable=False)
    method: Mapped[str] = mapped_column(String(32), nullable=False)
    source_page_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDPK, ForeignKey("fetched_pages.id", ondelete="SET NULL")
    )
    source_url: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column()
    error: Mapped[str | None] = mapped_column(Text)
    selected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Export(TimestampMixin, Base):
    __tablename__ = "exports"
    id: Mapped[uuid.UUID] = mapped_column(UUIDPK, primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = org_fk()
    job_id: Mapped[uuid.UUID] = mapped_column(UUIDPK, ForeignKey("crawl_jobs.id", ondelete="CASCADE"), index=True)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(UUIDPK, ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)  # pending|ready|failed
    options: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    file_path: Mapped[str | None] = mapped_column(Text)
    file_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)


# --- configuration, usage and audit -----------------------------------------------------------


class ProviderConfiguration(TimestampMixin, Base):
    __tablename__ = "provider_configurations"
    id: Mapped[uuid.UUID] = mapped_column(UUIDPK, primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = org_fk()
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # llm|discovery
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class UsageRecord(Base):
    __tablename__ = "usage_records"
    __table_args__ = (Index("ix_usage_org_period_kind", "org_id", "period_month", "kind"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[uuid.UUID] = org_fk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUIDPK)
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUIDPK)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # pages|llm_request|export_rows
    quantity: Mapped[int] = mapped_column(BigInteger, default=1, nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    period_month: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_org_created", "org_id", "created_at"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[uuid.UUID | None] = mapped_column(UUIDPK, ForeignKey("organizations.id", ondelete="CASCADE"))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUIDPK)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(32))
    target_id: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(64))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DomainPolicy(TimestampMixin, Base):
    """Admin-managed domain denylist (org_id NULL = applies to everyone)."""

    __tablename__ = "domain_policies"
    __table_args__ = (UniqueConstraint("org_id", "domain"),)
    id: Mapped[uuid.UUID] = mapped_column(UUIDPK, primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID | None] = mapped_column(UUIDPK, ForeignKey("organizations.id", ondelete="CASCADE"))
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    rule: Mapped[str] = mapped_column(String(16), default="deny", nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)


class Evidence(Base):
    """One piece of proof that a company uses a technology, or a page that was looked at and rejected.

    The quote is always a verbatim sentence from a page or filing that was fetched; nothing here is written by a
    model except the relationship, which is a choice from a fixed list.
    """

    __tablename__ = "evidence"
    id: Mapped[uuid.UUID] = mapped_column(UUIDPK, primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = org_fk()
    job_id: Mapped[uuid.UUID] = mapped_column(UUIDPK, ForeignKey("crawl_jobs.id", ondelete="CASCADE"), index=True)
    company: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    website: Mapped[str] = mapped_column(Text, default="", nullable=False)
    product: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    quote: Mapped[str] = mapped_column(Text, default="", nullable=False)
    url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    evidence_date: Mapped[str] = mapped_column(String(10), default="", nullable=False)  # YYYY-MM-DD
    source_type: Mapped[str] = mapped_column(String(60), default="", nullable=False)  # "SEC filing (10-K)"
    relationship: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    judged_by: Mapped[str] = mapped_column(String(120), default="", nullable=False)  # rules | model:<id> | unreviewed
    strength: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    verdict: Mapped[str] = mapped_column(String(20), default="", nullable=False)  # Confirmed | Likely | Mentioned
    kept: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)  # why it was rejected
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SecCompany(Base):
    """Shared, non-tenant copy of SEC EDGAR's list of listed companies (public data, refreshed by a task)."""

    __tablename__ = "sec_companies"
    cik: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    ticker: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    exchange: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False, index=True)  # order in SEC's list (largest first)
    sic: Mapped[str | None] = mapped_column(String(4), index=True)
    sic_description: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    city: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    state: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    foreign: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    website: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


TENANT_TABLES = [
    "projects",
    "extraction_schemas",
    "crawl_jobs",
    "crawl_job_events",
    "discovered_urls",
    "fetched_pages",
    "extracted_records",
    "extraction_field_values",
    "exports",
    "provider_configurations",
    "usage_records",
]
