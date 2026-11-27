"""Unit tests for resilient client and browser session helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import requests
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from tests.e2e.resilient_client import (
    ForbiddenResponseError,
    RateLimitDeferredError,
    ResilientPublicClient,
    RetryPolicy,
    SessionValidationError,
    _parse_retry_after,
    _safe_url,
    goto_checked,
    require_authenticated_page,
    save_authenticated_state,
)


def test_retry_policy_validation():
    policy = RetryPolicy()
    assert policy.max_retries == 4
    assert policy.base_delay_seconds == 1.0

    with pytest.raises(ValueError, match="finite numbers"):
        RetryPolicy(base_delay_seconds=float("inf"))

    with pytest.raises(ValueError, match="finite numbers"):
        RetryPolicy(max_backoff_seconds=float("nan"))

    with pytest.raises(ValueError, match="max_retries"):
        RetryPolicy(max_retries=9)

    with pytest.raises(ValueError, match="max_retries"):
        RetryPolicy(max_retries=-1)

    with pytest.raises(ValueError, match="Backoff delays"):
        RetryPolicy(base_delay_seconds=-0.5)

    with pytest.raises(ValueError, match="Backoff delays"):
        RetryPolicy(max_backoff_seconds=65.0)

    with pytest.raises(ValueError, match="max_retry_after_seconds"):
        RetryPolicy(max_retry_after_seconds=301.0)

    with pytest.raises(ValueError, match="max_total_wait_seconds"):
        RetryPolicy(max_total_wait_seconds=301.0)

    with pytest.raises(ValueError, match="max_jitter_seconds"):
        RetryPolicy(max_jitter_seconds=3.0)


def test_safe_url():
    url = "https://user:secret_token@api.example.com:8443/v1/search?q=test#heading"
    safe = _safe_url(url)
    assert safe == "https://api.example.com:8443"
    assert "secret_token" not in safe
    assert "search" not in safe
    assert "heading" not in safe

    assert _safe_url("http://example.com/path") == "http://example.com"
    assert _safe_url("https://[::1]:8080/path") == "https://[::1]:8080"


def test_parse_retry_after():
    assert _parse_retry_after(None) is None
    assert _parse_retry_after("") is None
    assert _parse_retry_after("12.5") == 12.5
    assert _parse_retry_after("-5") == 0.0
    assert _parse_retry_after("nan") is None
    assert _parse_retry_after("inf") is None

    # HTTP-date in the future
    future_time = datetime.now(UTC) + timedelta(seconds=45)
    header_val = format_datetime(future_time)
    parsed = _parse_retry_after(header_val)
    assert parsed is not None
    assert 40.0 <= parsed <= 50.0

    # HTTP-date in the past
    past_time = datetime.now(UTC) - timedelta(seconds=30)
    assert _parse_retry_after(format_datetime(past_time)) == 0.0

    # Malformed
    assert _parse_retry_after("invalid-date-string") is None


def test_403_fails_immediately_without_retry():
    session = requests.Session()
    mock_resp = requests.Response()
    mock_resp.status_code = 403
    mock_resp.url = "https://api.example.com/protected"

    call_count = 0

    def mock_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return mock_resp

    session.request = mock_request

    client = ResilientPublicClient(session=session)
    with pytest.raises(ForbiddenResponseError) as exc_info:
        client.get("https://api.example.com/protected?key=secret")

    assert call_count == 1
    assert "https://api.example.com" in str(exc_info.value)
    assert "secret" not in str(exc_info.value)


@patch("time.sleep", return_value=None)
def test_429_retries_and_succeeds(mock_sleep):
    session = requests.Session()
    resp_429 = requests.Response()
    resp_429.status_code = 429
    resp_429.headers["Retry-After"] = "2"

    resp_200 = requests.Response()
    resp_200.status_code = 200

    responses = [resp_429, resp_200]
    call_count = 0

    def mock_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return responses.pop(0)

    session.request = mock_request

    client = ResilientPublicClient(session=session)
    res = client.get("https://api.example.com/items")
    assert res.status_code == 200
    assert call_count == 2
    mock_sleep.assert_called_once()


def test_429_excessive_retry_after_deferred():
    session = requests.Session()
    resp_429 = requests.Response()
    resp_429.status_code = 429
    resp_429.headers["Retry-After"] = "200"  # Exceeds max_retry_after_seconds=120

    session.request = MagicMock(return_value=resp_429)

    client = ResilientPublicClient(session=session)
    with pytest.raises(RateLimitDeferredError, match="above the configured"):
        client.get("https://api.example.com/items")


def test_non_retryable_methods():
    session = requests.Session()
    resp_429 = requests.Response()
    resp_429.status_code = 429

    call_count = 0

    def mock_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return resp_429

    session.request = mock_request

    client = ResilientPublicClient(session=session)
    res = client.request("POST", "https://api.example.com/items")
    assert res.status_code == 429
    assert call_count == 1  # No retries for POST


@pytest.mark.asyncio
async def test_save_authenticated_state_unauthenticated_rejected(tmp_path):
    mock_ctx = AsyncMock()
    with pytest.raises(ValueError, match="Refusing to save browser state"):
        await save_authenticated_state(mock_ctx, authenticated=False, storage_state_path=tmp_path / "auth.json")


@pytest.mark.asyncio
async def test_save_authenticated_state_file_permissions(tmp_path):
    mock_ctx = AsyncMock()
    mock_ctx.storage_state = AsyncMock(return_value={"cookies": [{"name": "sid", "value": "xyz"}]})

    state_file = tmp_path / "auth" / "state.json"
    saved_path = await save_authenticated_state(mock_ctx, authenticated=True, storage_state_path=state_file)

    assert saved_path.is_file()
    assert saved_path == state_file
    import json
    data = json.loads(saved_path.read_text(encoding="utf-8"))
    assert data["cookies"][0]["name"] == "sid"


@pytest.mark.asyncio
async def test_require_authenticated_page_timeout():
    mock_page = AsyncMock()
    mock_locator = AsyncMock()
    mock_locator.wait_for.side_effect = PlaywrightTimeoutError("Timeout exceeded")
    mock_page.locator = MagicMock(return_value=mock_locator)

    with pytest.raises(SessionValidationError, match="did not appear before the timeout"):
        await require_authenticated_page(mock_page, success_selector="#dashboard", timeout_ms=500)


@pytest.mark.asyncio
async def test_goto_checked_403_and_429():
    mock_page = AsyncMock()
    mock_resp_403 = AsyncMock()
    mock_resp_403.status = 403

    mock_page.goto.return_value = mock_resp_403
    with pytest.raises(ForbiddenResponseError, match="403 Forbidden"):
        await goto_checked(mock_page, "https://example.com/admin")

    mock_resp_429 = AsyncMock()
    mock_resp_429.status = 429
    mock_page.goto.return_value = mock_resp_429
    with pytest.raises(RateLimitDeferredError, match="rate-limiting browser navigation"):
        await goto_checked(mock_page, "https://example.com/admin")
