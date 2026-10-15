"""Comprehensive tests for error classification in outcome.py.

Verifies:
1. Actual HTTP 404 responses are correctly classified as confirmed absence (None).
2. DNS resolution failures are classified as UNAVAILABLE, not confirmed absence.
3. Timeouts (including those containing "404" in their message) are UNAVAILABLE.
4. Upstream 5xx responses are UNAVAILABLE.
5. Rate limiting (429, "rate limit") is UNAVAILABLE.
6. Unrelated error messages containing "404" or "not found" are NOT misclassified
   as confirmed absence.
7. Malformed responses, decode errors, SSRF blocks are ERROR.
8. Empty/whitespace error strings return None.
"""

import pytest
from argus.specialists.outcome import (
    classify_error_message,
    determine_specialist_outcome,
    SpecialistOutcome,
)


# ============================================================================
# 1. CONFIRMED ABSENCE (HTTP 404) — should return None
# ============================================================================

class TestConfirmedAbsence:
    """Structured HTTP 404 and explicit empty-result patterns."""

    def test_http_404_structured(self):
        assert classify_error_message("User returned 404 Not Found") is None

    def test_http_404_parenthesized(self):
        assert classify_error_message("Account does not exist (HTTP 404)") is None

    def test_status_404(self):
        assert classify_error_message("GitHub API status 404 for user xyz") is None

    def test_response_404(self):
        assert classify_error_message("response 404 from endpoint") is None

    def test_status_code_404(self):
        assert classify_error_message("status_code=404") is None

    def test_404_not_found_exact(self):
        assert classify_error_message("404 Not Found") is None

    def test_sec_edgar_not_found(self):
        assert classify_error_message("Entity not found in SEC EDGAR directory") is None

    def test_no_ct_records(self):
        assert classify_error_message("No certificate transparency records discovered") is None

    def test_no_profile_discovered(self):
        assert classify_error_message("No profile discovered for user xyz") is None

    def test_limitation_notice(self):
        assert classify_error_message("Limitation: endpoint only provides identity") is None

    def test_no_results(self):
        assert classify_error_message("No results found for query") is None

    def test_no_records(self):
        assert classify_error_message("No records matching criteria") is None

    def test_empty_results(self):
        assert classify_error_message("Empty results from search API") is None

    def test_zero_results(self):
        assert classify_error_message("Zero results returned") is None


# ============================================================================
# 2. SOURCE UNAVAILABLE — should return "UNAVAILABLE"
# ============================================================================

class TestSourceUnavailable:
    """Timeouts, 5xx, rate limits, DNS failures, transport errors."""

    def test_timeout_plain(self):
        assert classify_error_message("Request timed out after 30s") == "UNAVAILABLE"

    def test_timeout_containing_404(self):
        """CRITICAL: 'timeout after 404ms' must NOT be classified as confirmed absence."""
        assert classify_error_message("timeout after 404ms") == "UNAVAILABLE"

    def test_timed_out_variant(self):
        assert classify_error_message("Connection timed out") == "UNAVAILABLE"

    def test_500_error(self):
        assert classify_error_message("Server returned 500 Internal Server Error") == "UNAVAILABLE"

    def test_502_bad_gateway(self):
        assert classify_error_message("502 Bad Gateway") == "UNAVAILABLE"

    def test_503_service_unavailable(self):
        assert classify_error_message("503 Service Unavailable") == "UNAVAILABLE"

    def test_504_gateway_timeout(self):
        assert classify_error_message("504 Gateway Timeout") == "UNAVAILABLE"

    def test_rate_limit_429(self):
        assert classify_error_message("HTTP 429 Too Many Requests") == "UNAVAILABLE"

    def test_rate_limit_text(self):
        assert classify_error_message("API rate limit exceeded") == "UNAVAILABLE"

    def test_connection_refused(self):
        assert classify_error_message("Connection refused by target host") == "UNAVAILABLE"

    def test_connection_reset(self):
        assert classify_error_message("Connection reset by peer") == "UNAVAILABLE"

    def test_transport_error(self):
        assert classify_error_message("Transport error: socket closed unexpectedly") == "UNAVAILABLE"

    def test_service_unavailable_text(self):
        assert classify_error_message("Service unavailable, try again later") == "UNAVAILABLE"

    def test_temporarily_unavailable(self):
        assert classify_error_message("Resource temporarily unavailable") == "UNAVAILABLE"

    def test_network_execution_disabled(self):
        assert classify_error_message("Network execution disabled in test mode") == "UNAVAILABLE"

    def test_cooldown_required(self):
        assert classify_error_message("Cooldown required before retry") == "UNAVAILABLE"

    def test_mapping_unavailable(self):
        assert classify_error_message("Service mapping unavailable") == "UNAVAILABLE"

    def test_dns_resolution_failure(self):
        """CRITICAL: DNS 'host not found' must be UNAVAILABLE, not confirmed absence."""
        assert classify_error_message("DNS resolution failed: host not found") == "UNAVAILABLE"

    def test_name_resolution_failure(self):
        assert classify_error_message("Name resolution error for api.example.com") == "UNAVAILABLE"

    def test_getaddrinfo_failure(self):
        assert classify_error_message("getaddrinfo failed: NXDOMAIN") == "UNAVAILABLE"

    def test_host_unreachable(self):
        assert classify_error_message("Host unreachable: no route to host") == "UNAVAILABLE"


# ============================================================================
# 3. SOURCE ERROR — should return "ERROR"
# ============================================================================

class TestSourceError:
    """Malformed responses, parsing errors, policy blocks."""

    def test_malformed_json(self):
        assert classify_error_message("Malformed JSON in API response") == "ERROR"

    def test_malformed_response(self):
        assert classify_error_message("Malformed response body from server") == "ERROR"

    def test_decode_error(self):
        assert classify_error_message("Decode error: invalid UTF-8 sequence") == "ERROR"

    def test_byte_limit(self):
        assert classify_error_message("Response exceeded byte limit") == "ERROR"

    def test_ssrf_blocked(self):
        assert classify_error_message("SSRF blocked: destination 10.0.0.1 is private") == "ERROR"

    def test_destination_policy(self):
        assert classify_error_message("URL violates destination policy") == "ERROR"

    def test_prohibited_by_network(self):
        assert classify_error_message("Request prohibited by network policy") == "ERROR"

    def test_invalid_or_empty(self):
        assert classify_error_message("Response body invalid or empty") == "ERROR"

    def test_unknown_error_defaults_to_error(self):
        """Unrecognized errors must default to ERROR, never confirmed absence."""
        assert classify_error_message("Something completely unexpected happened") == "ERROR"


# ============================================================================
# 4. CRITICAL: FALSE-POSITIVE PREVENTION
# ============================================================================

class TestFalsePositivePrevention:
    """Messages containing '404' or 'not found' that must NOT be classified as confirmed absence."""

    def test_timeout_with_404_in_duration(self):
        """'timeout after 404ms' contains '404' but is a timeout, not a 404 response."""
        result = classify_error_message("timeout after 404ms")
        assert result == "UNAVAILABLE", f"Expected UNAVAILABLE, got {result}"

    def test_rate_limit_with_404_in_message(self):
        """Rate limit message that happens to mention 404."""
        result = classify_error_message("Rate limit exceeded, retry in 404 seconds")
        assert result == "UNAVAILABLE", f"Expected UNAVAILABLE, got {result}"

    def test_dns_host_not_found(self):
        """DNS 'host not found' is a network error, not a 404."""
        result = classify_error_message("DNS: host not found")
        assert result == "UNAVAILABLE", f"Expected UNAVAILABLE, got {result}"

    def test_connection_error_not_found(self):
        """Connection error with 'not found' in error detail."""
        result = classify_error_message("Connection refused: service not found on port 8080")
        assert result == "UNAVAILABLE", f"Expected UNAVAILABLE, got {result}"

    def test_5xx_with_404_in_body(self):
        """A 500 error whose body mentions 404."""
        result = classify_error_message("500 Internal Server Error: downstream returned 404")
        assert result == "UNAVAILABLE", f"Expected UNAVAILABLE, got {result}"

    def test_decode_error_not_found_in_charset(self):
        """A decode error mentioning 'not found'."""
        result = classify_error_message("Decode error: encoding not found in charset table")
        assert result == "ERROR", f"Expected ERROR, got {result}"


# ============================================================================
# 5. EDGE CASES
# ============================================================================

class TestEdgeCases:
    """Empty, whitespace, and boundary inputs."""

    def test_empty_string(self):
        assert classify_error_message("") is None

    def test_whitespace_only(self):
        assert classify_error_message("   ") is None

    def test_case_insensitivity(self):
        assert classify_error_message("TIMEOUT after 30 seconds") == "UNAVAILABLE"
        assert classify_error_message("HTTP 404 NOT FOUND") is None
        assert classify_error_message("MALFORMED JSON") == "ERROR"


# ============================================================================
# 6. INTEGRATION: determine_specialist_outcome with error classification
# ============================================================================

class TestDetermineOutcomeWithErrors:
    """Verify that determine_specialist_outcome correctly routes error classifications."""

    def test_timeout_error_yields_unavailable_not_empty(self):
        """A timeout error must yield SOURCE_UNAVAILABLE, never SUCCESS_EMPTY."""
        result = determine_specialist_outcome(
            has_results=False,
            errors=["timeout after 404ms"],
        )
        assert result == SpecialistOutcome.SOURCE_UNAVAILABLE

    def test_dns_error_yields_unavailable_not_empty(self):
        result = determine_specialist_outcome(
            has_results=False,
            errors=["DNS resolution failed: host not found"],
        )
        assert result == SpecialistOutcome.SOURCE_UNAVAILABLE

    def test_5xx_yields_unavailable(self):
        result = determine_specialist_outcome(
            has_results=False,
            errors=["Server returned 500 Internal Server Error"],
        )
        assert result == SpecialistOutcome.SOURCE_UNAVAILABLE

    def test_rate_limit_yields_unavailable(self):
        result = determine_specialist_outcome(
            has_results=False,
            errors=["429 Too Many Requests"],
        )
        assert result == SpecialistOutcome.SOURCE_UNAVAILABLE

    def test_confirmed_404_yields_success_empty(self):
        result = determine_specialist_outcome(
            has_results=False,
            errors=["User returned 404 Not Found"],
        )
        assert result == SpecialistOutcome.SUCCESS_EMPTY

    def test_mixed_unavailable_and_results_yields_partial(self):
        result = determine_specialist_outcome(
            has_results=True,
            errors=["Connection timed out"],
        )
        assert result == SpecialistOutcome.PARTIAL_SUCCESS

    def test_no_errors_with_results(self):
        result = determine_specialist_outcome(has_results=True)
        assert result == SpecialistOutcome.SUCCESS_WITH_RESULTS

    def test_no_errors_no_results(self):
        result = determine_specialist_outcome(has_results=False)
        assert result == SpecialistOutcome.SUCCESS_EMPTY
