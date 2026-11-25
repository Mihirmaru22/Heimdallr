"""Reusable helpers for authorized browser tests and public-data API reads.

The browser profile is deterministic and its saved state is a credential: keep it local and
out of version control. The HTTP helper uses one stable User-Agent, retries only idempotent
reads after 429 responses, and treats 403 as an immediate permission/session failure.
"""

from __future__ import annotations

import json
import logging
import math
import os
import random
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
)
from playwright.async_api import (
    Response as PlaywrightResponse,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)

log = logging.getLogger("heimdallr.e2e.client")

VIEWPORT = {"width": 1440, "height": 900}
LOCALE = "en-US"
USER_AGENT = "Heimdallr-E2E/1.0 (+https://github.com/Mihirmaru22/Heimdallr; authorized QA)"
DEFAULT_STATE_PATH = Path(__file__).parent / ".auth" / "storage-state.json"


async def new_test_context(
    browser: Browser,
    *,
    storage_state_path: Path = DEFAULT_STATE_PATH,
    base_url: str | None = None,
) -> BrowserContext:
    """Create a stable test context and reuse a previously saved login state when present."""
    state_path = Path(storage_state_path)
    options: dict[str, Any] = {
        "viewport": dict(VIEWPORT),
        "locale": LOCALE,
        "user_agent": USER_AGENT,
        "device_scale_factor": 1,
        "timezone_id": "UTC",
        "extra_http_headers": {"Accept-Language": "en-US,en;q=0.9"},
    }
    if base_url:
        options["base_url"] = base_url
    if state_path.is_file():
        _secure_existing_state(state_path)
        options["storage_state"] = str(state_path)
        log.info("Loading saved browser storage state from %s", state_path)
    else:
        log.info("No saved browser state found; starting a clean context")
    return await browser.new_context(**options)


async def save_authenticated_state(
    context: BrowserContext,
    *,
    authenticated: bool,
    storage_state_path: Path = DEFAULT_STATE_PATH,
) -> Path:
    """Persist cookies and local storage atomically after the caller confirms login succeeded."""
    if not authenticated:
        raise ValueError("Refusing to save browser state before login is confirmed")

    state_path = Path(storage_state_path)
    state_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _chmod_private(state_path.parent)
    state = await context.storage_state()
    fd, temp_name = tempfile.mkstemp(prefix=".storage-state-", suffix=".tmp", dir=state_path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, ensure_ascii=False, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, state_path)
        _chmod_private(state_path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    log.info("Saved authenticated browser storage state to %s", state_path)
    return state_path


async def require_authenticated_page(page: Page, *, success_selector: str, timeout_ms: int = 10_000) -> None:
    """Bound the auth check so expired state or permission redirects fail clearly instead of looping."""
    if not 0 < timeout_ms <= 60_000:
        raise ValueError("timeout_ms must be between 1 and 60000")
    try:
        await page.locator(success_selector).wait_for(state="visible", timeout=timeout_ms)
    except PlaywrightTimeoutError as exc:
        log.error("Authenticated-page marker was not visible; inspect login state or permissions")
        raise SessionValidationError(
            "The authenticated page did not appear before the timeout; the saved session may be expired "
            "or the account may lack permission"
        ) from exc


async def goto_checked(page: Page, url: str, *, timeout_ms: int = 30_000) -> PlaywrightResponse | None:
    """Navigate once with a bounded wait and fail immediately on HTTP 403/429 responses."""
    if not 0 < timeout_ms <= 120_000:
        raise ValueError("timeout_ms must be between 1 and 120000")
    response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    if response and response.status == 403:
        log.error("403 Forbidden during browser navigation to %s; stopping for permission review", _safe_url(url))
        raise ForbiddenResponseError(f"403 Forbidden during browser navigation to {_safe_url(url)}")
    if response and response.status == 429:
        log.error("429 during browser navigation to %s; defer the batch", _safe_url(url))
        raise RateLimitDeferredError("The server is rate-limiting browser navigation; resume after its cooldown")
    return response


def _secure_existing_state(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)
    _chmod_private(path.parent)
    _chmod_private(path)


def _chmod_private(path: Path) -> None:
    """Restrict saved credentials to the current OS user where POSIX permissions apply."""
    if os.name != "nt":
        os.chmod(path, 0o700 if path.is_dir() else 0o600)


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 4
    base_delay_seconds: float = 1.0
    max_backoff_seconds: float = 30.0
    max_retry_after_seconds: float = 120.0
    max_total_wait_seconds: float = 180.0
    max_jitter_seconds: float = 1.0

    def __post_init__(self) -> None:
        delays = (self.base_delay_seconds, self.max_backoff_seconds, self.max_retry_after_seconds,
                  self.max_total_wait_seconds, self.max_jitter_seconds)
        if not all(math.isfinite(delay) for delay in delays):
            raise ValueError("Retry delays must be finite numbers")
        if not 0 <= self.max_retries <= 8:
            raise ValueError("max_retries must be between 0 and 8")
        if self.base_delay_seconds < 0 or not 0 < self.max_backoff_seconds <= 60:
            raise ValueError("Backoff delays must be nonnegative and capped at 60 seconds")
        if not 0 < self.max_retry_after_seconds <= 300:
            raise ValueError("max_retry_after_seconds must be between 0 and 300")
        if not 0 < self.max_total_wait_seconds <= 300:
            raise ValueError("max_total_wait_seconds must be between 0 and 300")
        if not 0 <= self.max_jitter_seconds <= 2:
            raise ValueError("max_jitter_seconds must be between 0 and 2")


class ForbiddenResponseError(RuntimeError):
    """A 403 must be investigated; repeating it cannot repair permissions or expired login."""


class SessionValidationError(RuntimeError):
    """Browser state did not reach a known authenticated-only page within the configured time."""


class RateLimitDeferredError(RuntimeError):
    """The server's Retry-After exceeds this client's bounded wait budget."""


class ResilientPublicClient:
    """Persistent requests.Session with respectful, bounded retries for public GET/HEAD reads."""

    RETRYABLE_METHODS = frozenset({"GET", "HEAD"})

    def __init__(self, policy: RetryPolicy | None = None, session: requests.Session | None = None) -> None:
        self.policy = policy or RetryPolicy()
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain;q=0.9, */*;q=0.8",
        })

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        method = method.upper()
        retries = self.policy.max_retries if method in self.RETRYABLE_METHODS else 0
        kwargs.setdefault("timeout", (5, 30))
        safe_url = _safe_url(url)
        total_wait = 0.0

        for attempt in range(retries + 1):
            response = self.session.request(method, url, **kwargs)
            if response.status_code == 403:
                log.error("403 Forbidden for %s %s; stopping for session/permission review", method, safe_url)
                raise ForbiddenResponseError(f"403 Forbidden for {method} {safe_url}")
            if response.status_code != 429:
                return response
            if attempt >= retries:
                log.error("429 rate limit persisted after %d retry attempt(s): %s", retries, safe_url)
                return response

            delay = self._retry_delay(response, attempt)
            if total_wait + delay > self.policy.max_total_wait_seconds:
                log.error("429 retry budget exhausted before another wait: %s", safe_url)
                raise RateLimitDeferredError(
                    f"Retrying {safe_url} would exceed the configured "
                    f"{self.policy.max_total_wait_seconds:.0f}s total wait budget"
                )
            log.warning("429 rate limit for %s; retry %d/%d in %.2fs", safe_url, attempt + 1, retries, delay)
            time.sleep(delay)
            total_wait += delay

        raise RuntimeError("unreachable retry state")

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        return self.request("GET", url, **kwargs)

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> ResilientPublicClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _retry_delay(self, response: requests.Response, attempt: int) -> float:
        retry_after = _parse_retry_after(response.headers.get("Retry-After"))
        if retry_after is not None:
            if retry_after > self.policy.max_retry_after_seconds:
                log.error("Retry-After %.2fs exceeds the configured wait budget; deferring request", retry_after)
                raise RateLimitDeferredError(
                    f"Server requested a {retry_after:.0f}s wait, above the configured "
                    f"{self.policy.max_retry_after_seconds:.0f}s limit"
                )
            base = retry_after
        else:
            base = min(self.policy.base_delay_seconds * (2**attempt), self.policy.max_backoff_seconds)

        remaining = max(0.0, self.policy.max_retry_after_seconds - base)
        jitter_ceiling = min(self.policy.max_jitter_seconds, remaining)
        jitter = random.uniform(0.0, jitter_ceiling) if jitter_ceiling else 0.0
        return base + jitter


def _parse_retry_after(value: str | None) -> float | None:
    """Parse Retry-After seconds or HTTP-date; None means use exponential backoff."""
    if not value:
        return None
    try:
        seconds = float(value.strip())
        if seconds != seconds or seconds == float("inf"):
            return None
        return max(0.0, seconds)
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)
    return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())


def _safe_url(url: str) -> str:
    """Keep path, query, fragment, and user-info credentials out of logs."""
    parts = urlsplit(url)
    host = parts.hostname or "unknown-host"
    if ":" in host:
        host = f"[{host}]"
    try:
        port = f":{parts.port}" if parts.port is not None else ""
    except ValueError:
        port = ""
    return urlunsplit((parts.scheme, f"{host}{port}", "", "", ""))
