"""The extraction specification: what to collect, where to look, and the limits of a job.

A spec may come from a person, from the rule-based interpreter, or (phase 2) from a model.
All three are untrusted until `validate_spec` accepts them.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

FIELD_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
MAX_FIELDS = 50
RESERVED = {"id", "org_id", "job_id", "source_urls", "excluded", "status"}


class FieldType(StrEnum):
    string = "string"
    text = "text"
    url = "url"
    email = "email"
    phone = "phone"
    number = "number"
    integer = "integer"
    date = "date"
    boolean = "boolean"
    list = "list"


class Semantic(StrEnum):
    """Built-in deterministic extractors a field can use."""

    company_name = "company_name"
    website_url = "website_url"
    contact_email = "contact_email"
    phone = "phone"
    address = "address"
    headquarters = "headquarters"
    country = "country"
    description = "description"
    page_title = "page_title"
    social_links = "social_links"
    pricing = "pricing"
    founded_year = "founded_year"
    product_categories = "product_categories"
    industry = "industry"
    source_url = "source_url"
    none = "none"


class ExtractRules(BaseModel):
    """Optional user-configured deterministic rules for a field."""

    model_config = ConfigDict(extra="forbid")
    css: list[str] = Field(default_factory=list, max_length=5)
    meta: list[str] = Field(default_factory=list, max_length=5)
    jsonld: list[str] = Field(default_factory=list, max_length=5)  # e.g. "Organization.name"
    regex: str | None = Field(default=None, max_length=300)
    labels: list[str] = Field(default_factory=list, max_length=10)  # "Founded", "HQ"

    @field_validator("css")
    @classmethod
    def _css(cls, v: list[str]) -> list[str]:
        for sel in v:
            if len(sel) > 200 or any(c in sel for c in "{};"):
                raise ValueError("CSS selector is too long or contains forbidden characters")
        return v

    @field_validator("regex")
    @classmethod
    def _regex(cls, v: str | None) -> str | None:
        if v is None:
            return v
        # Reject constructs that commonly lead to catastrophic backtracking.
        if re.search(r"\([^)]*[+*][^)]*\)[+*{]", v) or "(?" in v.replace("(?:", ""):
            raise ValueError("regex uses nested quantifiers or unsupported groups")
        re.compile(v)
        return v


class FieldSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    label: str = ""
    type: FieldType = FieldType.string
    description: str = Field(default="", max_length=500)
    required: bool = False
    semantic: Semantic = Semantic.none
    rules: ExtractRules = Field(default_factory=ExtractRules)
    max_length: int = Field(default=2000, ge=1, le=32000)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not FIELD_NAME_RE.match(v):
            raise ValueError("field names must be snake_case, start with a letter, max 63 characters")
        if v in RESERVED:
            raise ValueError(f"{v!r} is a reserved field name")
        return v

    @model_validator(mode="after")
    def _label(self) -> FieldSpec:
        if not self.label:
            self.label = self.name.replace("_", " ").capitalize()
        self.label = self.label[:80]
        return self


class CrawlSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_urls: list[str] = Field(default_factory=list, max_length=500)
    allowed_domains: list[str] = Field(default_factory=list, max_length=500)
    max_pages: int = Field(default=200, ge=1)
    max_depth: int = Field(default=2, ge=0)
    max_pages_per_site: int = Field(default=15, ge=1, le=500)
    use_sitemaps: bool = True
    follow_links: bool = True
    # Prefer pages whose URL mentions these words (contact, about, pricing...)
    priority_keywords: list[str] = Field(default_factory=lambda: ["contact", "about", "pricing", "impressum"])


class DiscoverySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    providers: list[Literal["seeds", "wikidata", "searxng", "sec_edgar", "gleif"]] = Field(
        default_factory=lambda: ["seeds"])
    industry: str | None = Field(default=None, max_length=100)
    countries: list[str] = Field(default_factory=list, max_length=60)  # ISO 3166-1 alpha-2
    # Only keep companies confirmed to be in `countries` (a hard limit), instead of only preferring them.
    strict_countries: bool = True

    @field_validator("countries")
    @classmethod
    def _iso_codes(cls, v: list[str]) -> list[str]:
        out = []
        for c in v:
            code = c.strip().upper()
            if not re.fullmatch(r"[A-Z]{2}", code):
                raise ValueError(f"{c!r} is not a two-letter country code (US, GB, IN...)")
            out.append(code)
        return list(dict.fromkeys(out))
    region: Literal["europe", "north_america", "asia", "africa", "south_america", "oceania"] | None = None
    keywords: list[str] = Field(default_factory=list, max_length=10)
    max_results: int = Field(default=50, ge=1, le=1000)
    # Filters read from a plain-language question that discovery does not apply yet (later steps of the plan):
    # a technology the company uses ("Teamcenter") and the company whose sites are wanted ("Ford").
    technology: str | None = Field(default=None, max_length=100)
    parent_company: str | None = Field(default=None, max_length=100)


class ExtractionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(default="Extraction", max_length=200)
    entity: str = Field(default="record", max_length=60)  # "company", "product"...
    record_scope: Literal["site", "page"] = "site"  # one record per website, or per page
    fields: list[FieldSpec] = Field(min_length=1, max_length=MAX_FIELDS)
    deduplication_keys: list[str] = Field(default_factory=list, max_length=5)
    crawl: CrawlSettings = Field(default_factory=CrawlSettings)
    discovery: DiscoverySettings = Field(default_factory=DiscoverySettings)
    export: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _consistent(self) -> ExtractionSpec:
        names = [f.name for f in self.fields]
        if len(set(names)) != len(names):
            raise ValueError("field names must be unique")
        unknown = [k for k in self.deduplication_keys if k not in names]
        if unknown:
            raise ValueError(f"deduplication keys are not fields: {unknown}")
        return self


def validate_spec(raw: dict[str, Any], limits: dict[str, int]) -> ExtractionSpec:
    """Parse untrusted input and clamp crawl limits to what the organization may use."""
    spec = ExtractionSpec.model_validate(raw)
    spec.crawl.max_pages = min(spec.crawl.max_pages, limits["max_pages_per_job"])
    spec.crawl.max_depth = min(spec.crawl.max_depth, limits["max_depth"])
    spec.discovery.max_results = min(spec.discovery.max_results, limits["max_pages_per_job"])
    return spec
