"""Pydantic request and response models for the API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- auth / orgs ------------------------------------------------------------------------------


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=200)
    display_name: str = Field(default="", max_length=120)
    organization_name: str = Field(default="", max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=200)


class UserOut(ORM):
    id: uuid.UUID
    email: str
    display_name: str
    is_platform_admin: bool


class OrgOut(ORM):
    id: uuid.UUID
    name: str
    slug: str
    role: str | None = None


class MeOut(BaseModel):
    user: UserOut
    organizations: list[OrgOut]
    csrf_token: str


class OrgIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class OrgUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    retention_days: int | None = Field(default=None, ge=1, le=3650)


class MemberIn(BaseModel):
    email: EmailStr
    role: Literal["admin", "member"] = "member"


class MemberUpdate(BaseModel):
    role: Literal["owner", "admin", "member"]


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: str
    display_name: str
    role: str
    created_at: datetime


# --- projects / schemas -----------------------------------------------------------------------


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)


class ProjectOut(ORM):
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    description: str
    created_at: datetime
    updated_at: datetime


class GenerateSchemaIn(BaseModel):
    request: str = Field(min_length=3, max_length=5000)
    start_urls: list[str] = Field(default_factory=list, max_length=500)


class SchemaOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    version: int
    nl_request: str
    spec: dict[str, Any]
    status: str
    interpreter: str
    created_at: datetime
    notes: list[str] = []  # how the question was read, and what is not applied yet (only on generate)


class SchemaUpdate(BaseModel):
    spec: dict[str, Any]


class UrlCheck(BaseModel):
    url: str
    normalized: str | None
    allowed: bool
    reason: str


class PlanPreview(BaseModel):
    spec: dict[str, Any]
    urls: list[UrlCheck]
    discovery_providers: list[str]
    estimated_max_pages: int
    estimated_llm_calls: int
    warnings: list[str]


# --- jobs -------------------------------------------------------------------------------------


class JobIn(BaseModel):
    schema_id: uuid.UUID


class JobOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    schema_id: uuid.UUID
    state: str
    counters: dict[str, int]
    settings: dict[str, Any]
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    heartbeat_at: datetime | None


class JobProgress(BaseModel):
    id: uuid.UUID
    state: str
    counters: dict[str, int]
    records: int
    valid_records: int
    elapsed_seconds: float | None
    error: str | None
    terminal: bool


class EventOut(ORM):
    id: int
    type: str
    from_state: str | None
    to_state: str | None
    message: str
    data: dict[str, Any]
    created_at: datetime


class UrlOut(ORM):
    id: uuid.UUID
    url: str
    method: str
    depth: int
    status: str
    status_reason: str | None
    referrer_url: str | None
    attempts: int
    discovered_at: datetime


# --- records / exports ------------------------------------------------------------------------


class RecordOut(ORM):
    id: uuid.UUID
    data: dict[str, Any]
    status: str
    quality_score: float
    excluded: bool
    user_edited: bool
    source_urls: list[str]
    updated_at: datetime


class FieldValueOut(ORM):
    field_name: str
    value: Any
    value_status: str
    method: str
    source_url: str | None
    evidence: str | None
    confidence: float | None
    error: str | None
    selected: bool


class RecordDetail(RecordOut):
    fields: list[FieldValueOut]


class RecordPatch(BaseModel):
    data: dict[str, Any] | None = None
    excluded: bool | None = None


class ExcludeIn(BaseModel):
    record_ids: list[uuid.UUID] = Field(min_length=1, max_length=1000)
    excluded: bool = True


class ExportIn(BaseModel):
    include_excluded: bool = False
    statuses: list[Literal["valid", "partial", "invalid"]] = Field(default_factory=lambda: ["valid", "partial"])
    record_ids: list[uuid.UUID] | None = Field(default=None, max_length=100_000)
    columns: list[str] | None = None
    include_metadata: bool = True
    include_sources: bool = True
    include_issues: bool = True
    data_sheet_name: str = Field(default="Data", max_length=31)


class ExportOut(ORM):
    id: uuid.UUID
    job_id: uuid.UUID
    status: str
    row_count: int
    file_bytes: int
    expires_at: datetime | None
    error: str | None
    created_at: datetime
    download_url: str | None = None


class UsageOut(BaseModel):
    period: str
    pages: int
    llm_requests: int
    export_rows: int
    active_jobs: int
    limits: dict[str, int]
