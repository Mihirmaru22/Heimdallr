"""Controlled Live-Web Evaluation Data Models.

Defines schemas for live web tasks, evaluation contracts, controlled retrieval
limits, evidence records, text snapshots, and source independence metrics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class LiveWebCategory(str, Enum):
    CORPORATE_ORGANIZATIONAL = "CORPORATE_ORGANIZATIONAL"
    OWNERSHIP_SUBSIDIARY = "OWNERSHIP_SUBSIDIARY"
    HISTORICAL_TIMELINE = "HISTORICAL_TIMELINE"
    TECHNICAL_SCIENTIFIC = "TECHNICAL_SCIENTIFIC"
    CONFLICTING_CLAIMS = "CONFLICTING_CLAIMS"
    TEMPORAL_CHANGE = "TEMPORAL_CHANGE"
    MULTI_HOP = "MULTI_HOP"
    NEGATIVE_FINDINGS = "NEGATIVE_FINDINGS"
    MULTI_SOURCE_SYNTHESIS = "MULTI_SOURCE_SYNTHESIS"
    INSUFFICIENT_PUBLIC_EVIDENCE = "INSUFFICIENT_PUBLIC_EVIDENCE"


@dataclass
class LiveWebTask:
    task_id: str
    title: str
    objective: str
    category: LiveWebCategory
    contract: dict[str, Any]
    expected_entities: list[str]
    expected_epistemic_status: str  # "SUPPORTED", "CONTRADICTED", "NOT_FOUND", "INSUFFICIENT_EVIDENCE"
    expected_answers: list[str]
    evaluation_timestamp: str = "2026-10-13T10:00:00Z"
    applicable_time_period: str = "2024-2026"
    allowed_answer_variations: list[str] = field(default_factory=list)
    failure_conditions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ControlledRetrievalLimits:
    max_requests_per_task: int = 10
    max_duration_seconds: float = 30.0
    max_requests_per_host: int = 3
    request_timeout_seconds: float = 10.0
    max_retries: int = 2
    max_response_bytes: int = 1_048_576  # 1 MB
    respect_robots_txt: bool = True
    enforce_ssrf_protection: bool = True
    # Free search sources queried per search (see live_web/search_sources.py).
    search_providers: tuple[str, ...] = ("duckduckgo",)
    # Return at least this many merged results per search, whatever the caller's limit.
    min_results_per_search: int = 0
    # When a page refuses us or fails, read the Internet Archive's copy instead (cited as such).
    archive_fallback: bool = False

    @classmethod
    def deep(cls) -> "ControlledRetrievalLimits":
        """Budget for a full research run on the user's machine: every free source, more pages."""
        from argus.investigation.live_web.search_sources import FREE_SEARCH_SOURCES

        return cls(
            max_requests_per_task=200,
            max_duration_seconds=900.0,
            max_requests_per_host=40,
            request_timeout_seconds=15.0,
            search_providers=FREE_SEARCH_SOURCES,
            min_results_per_search=8,
            archive_fallback=True,
        )


@dataclass
class LiveWebEvidenceRecord:
    evidence_id: str
    original_url: str
    final_url: str
    retrieval_timestamp: str
    http_status: int
    title: str
    domain: str
    publisher: str
    extracted_text: str
    content_hash: str  # SHA-256
    source_type: str
    extraction_method: str
    relevant_passages: list[str] = field(default_factory=list)
    retrieval_error: str | None = None
    is_duplicate: bool = False
    canonical_url: str | None = None


@dataclass
class SourceIndependenceProfile:
    raw_source_count: int
    estimated_independent_source_count: int
    duplicate_count: int
    syndicated_count: int
    domains_represented: list[str]
    independence_ratio: float  # independent / raw
    classification: str  # "HIGH", "MODERATE", "LOW", "UNKNOWN"


@dataclass
class LiveWebTaskResult:
    task_id: str
    title: str
    category: str
    produced_status: str
    expected_status: str
    epistemic_correct: bool
    task_success: bool
    evidence_collected: list[LiveWebEvidenceRecord]
    source_independence: SourceIndependenceProfile
    requests_used: int
    runtime_seconds: float
    retrieval_errors: list[str]
    answer_element_coverage: float
    citation_precision: float
    failure_reason: str | None = None
