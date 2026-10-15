"""Specialist and Capability Outcome Status Taxonomy.

Defines granular operational and epistemic outcome statuses for specialists,
connectors, and capability adapters:
- SUCCESS_WITH_RESULTS: Source(s) responded successfully and yielded matching candidate evidence.
- SUCCESS_EMPTY: Source(s) responded successfully (or confirmed 404 resource non-existence),
  yielding 0 candidate records. Confirms absence of records at the queried endpoint,
  NOT global non-existence of the entity.
- SOURCE_UNAVAILABLE: Query could not reach source or source is degraded (HTTP 5xx, rate limit 429,
  socket timeout, connection reset). Crucially, this MUST NOT be treated as absence of evidence.
- SOURCE_ERROR: Source returned a malformed response or internal parsing error. Crucially,
  this MUST NOT be treated as absence of evidence.
- PARTIAL_SUCCESS: When multiple sources/registries were queried, at least one succeeded with results
  while another source timed out, returned 5xx/429, or failed.
- TIMEOUT: Specialist execution exceeded configured deadline.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class SpecialistOutcome(str, Enum):
    """Granular outcome status for specialist probes and adapter execution."""

    SUCCESS_WITH_RESULTS = "SUCCESS_WITH_RESULTS"
    SUCCESS_EMPTY = "SUCCESS_EMPTY"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    SOURCE_ERROR = "SOURCE_ERROR"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    TIMEOUT = "TIMEOUT"


class SpecialistStatus(str):
    """Backward-compatible specialist status string that satisfies legacy equality checks.
    
    Permits existing code asserting `res["status"] == "SUCCESS"`, `res["status"] == "TIMEOUT"`,
    or `res["status"] == "FAILED"` to continue passing while serializing to the granular outcome name.
    """

    def __new__(cls, value: str) -> SpecialistStatus:
        return super().__new__(cls, value)

    def __eq__(self, other: Any) -> bool:
        if super().__eq__(other):
            return True
        val_str = str(self)
        if val_str in ("SUCCESS_WITH_RESULTS", "SUCCESS_EMPTY", "PARTIAL_SUCCESS") and other == "SUCCESS":
            return True
        if val_str in ("SOURCE_UNAVAILABLE", "TIMEOUT") and other in ("TIMEOUT", "FAILED"):
            return True
        if val_str in ("SOURCE_ERROR",) and other == "FAILED":
            return True
        return False

    def __hash__(self) -> int:
        return super().__hash__()


def classify_error_message(err: str) -> str | None:
    """Classify an error string as 'UNAVAILABLE', 'ERROR', or None (informational/empty).
    
    Invariants:
    - Timeouts, 5xx, rate limits, transport errors -> 'UNAVAILABLE' (must NOT imply confirmed absence).
    - Malformed responses, decoding errors, client errors -> 'ERROR' (must NOT imply confirmed absence).
    - HTTP 404, empty results, or informational notices -> None (indicates confirmed absence at that specific endpoint).
    
    ORDERING INVARIANT:
    UNAVAILABLE and ERROR patterns MUST be evaluated BEFORE 404/not-found patterns.
    Broad substring matches ("404", "not found") would otherwise misclassify unrelated
    messages (e.g. "timeout after 404ms", "DNS: host not found") as confirmed absence.
    """
    if not err or not err.strip():
        return None

    err_lower = err.lower()

    # ── Phase 1: Source UNAVAILABLE (transport/network failures) ────────────
    # Must be checked FIRST to prevent "timeout after 404ms" or
    # "rate limit 404 response" from being classified as confirmed absence.
    unavailable_patterns = [
        "rate limit",
        "429",
        "timed out",
        "timeout",
        "500",
        "502",
        "503",
        "504",
        "service unavailable",
        "temporarily unavailable",
        "transport error",
        "connection reset",
        "connection refused",
        "network execution disabled",
        "cooldown required",
        "mapping unavailable",
        "dns resolution",
        "name resolution",
        "getaddrinfo",
        "unreachable",
        "dns:",
        "dns error",
    ]
    if any(pat in err_lower for pat in unavailable_patterns):
        return "UNAVAILABLE"

    # ── Phase 2: Source ERROR (parsing/policy failures) ─────────────────────
    # Must be checked BEFORE 404/not-found to prevent "decode error: not found
    # in charset table" from being classified as confirmed absence.
    error_patterns = [
        "malformed json",
        "malformed response",
        "decode error",
        "byte limit",
        "ssrf blocked",
        "violates destination policy",
        "prohibited by network",
        "invalid or empty",
    ]
    if any(pat in err_lower for pat in error_patterns):
        return "ERROR"

    # ── Phase 3: Informational notices and confirmed absence ───────────────
    # Only reached after UNAVAILABLE and ERROR patterns have been excluded.
    if "limitation:" in err_lower:
        return None
    if "not found in sec edgar directory" in err_lower:
        return None
    if "no certificate transparency records discovered" in err_lower:
        return None
    if "no profile discovered" in err_lower:
        return None

    # Structured HTTP 404 patterns: require explicit HTTP status context to
    # prevent bare "404" or "not found" in unrelated messages from triggering
    # false confirmed-absence classification.
    _http_404_patterns = [
        "http 404",
        "returned 404",
        "status 404",
        "response 404",
        "status_code=404",
        "status code 404",
        "(404)",
        "404 not found",
        "does not exist (http 404)",
    ]
    if any(pat in err_lower for pat in _http_404_patterns):
        return None

    # Explicit "no results" / "no records" / "empty" patterns
    _empty_result_patterns = [
        "no results",
        "no records",
        "no matches",
        "empty results",
        "0 results",
        "zero results",
    ]
    if any(pat in err_lower for pat in _empty_result_patterns):
        return None

    # Fallback: unrecognized error messages default to ERROR (fail-safe;
    # unknown errors must NOT imply confirmed absence).
    return "ERROR"


def determine_specialist_outcome(
    has_results: bool,
    errors: list[str] | None = None,
    multiple_sources: bool = False,
) -> SpecialistOutcome:
    """Accurately determine specialist outcome distinguishing results, empty, unavailable, and error.
    
    Rules:
    1. If results were returned:
       - If any source was unavailable or failed -> PARTIAL_SUCCESS
       - Otherwise -> SUCCESS_WITH_RESULTS
    2. If NO results were returned:
       - If any source was unavailable (5xx, 429, timeout, network error) -> SOURCE_UNAVAILABLE
         (Invariant: must NEVER be represented as confirmed absence of evidence).
       - If any source returned an error (malformed, decoding failure) -> SOURCE_ERROR
         (Invariant: must NEVER be represented as confirmed absence of evidence).
       - If all queried sources responded normally without results (or 404) -> SUCCESS_EMPTY
    """
    errors = errors or []
    has_unavailable = False
    has_error = False

    for err in errors:
        c = classify_error_message(err)
        if c == "UNAVAILABLE":
            has_unavailable = True
        elif c == "ERROR":
            has_error = True

    if has_results:
        if has_unavailable or has_error or multiple_sources:
            return SpecialistOutcome.PARTIAL_SUCCESS if (has_unavailable or has_error) else SpecialistOutcome.SUCCESS_WITH_RESULTS
        return SpecialistOutcome.SUCCESS_WITH_RESULTS

    # No results
    if has_unavailable:
        return SpecialistOutcome.SOURCE_UNAVAILABLE
    if has_error:
        return SpecialistOutcome.SOURCE_ERROR
    return SpecialistOutcome.SUCCESS_EMPTY
