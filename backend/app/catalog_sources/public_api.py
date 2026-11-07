"""Small, persistent HTTP client for documented public-data APIs."""

from __future__ import annotations

import logging
import math
import random
import threading
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import requests

log = logging.getLogger("webdata.catalog_sources")
USER_AGENT = "Heimdallr/0.1 (public-data catalog; https://github.com/Mihirmaru22/Heimdallr)"


class PublicApiError(RuntimeError):
    """An upstream API failed after bounded, polite retries."""


def retry_after_seconds(value: str | None, *, now: datetime | None = None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        current = now or datetime.now(UTC)
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        return max(0.0, (retry_at - current).total_seconds())


class PublicApiSession:
    """Persistent public API session with bounded retries and fail-fast authorization errors."""

    def __init__(self, *, session: requests.Session | None = None, timeout: float = 20.0,
                 max_retries: int = 4, max_wait: float = 120.0,
                 min_interval_seconds: float = 0.5) -> None:
        if (not 0 < timeout <= 120 or not 0 <= max_retries <= 6 or not 0 < max_wait <= 300
                or not math.isfinite(min_interval_seconds) or not 0 <= min_interval_seconds <= 60):
            raise ValueError("Invalid public API retry limits")
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_wait = max_wait
        self.min_interval_seconds = min_interval_seconds
        self._pace_lock = threading.Lock()
        self._last_request_at = 0.0

    def get_json(self, url: str, *, params: dict[str, Any] | None = None,
                 auth: tuple[str, str] | None = None) -> dict[str, Any]:
        return self.request_json("GET", url, params=params, auth=auth)

    def post_json(self, url: str, *, json_body: dict[str, Any],
                  params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request_json("POST", url, params=params, json_body=json_body)

    def request_json(self, method: str, url: str, *, params: dict[str, Any] | None = None,
                     auth: tuple[str, str] | None = None,
                     json_body: dict[str, Any] | None = None) -> dict[str, Any]:
        if method not in {"GET", "POST"}:
            raise ValueError("Only GET and POST are supported")
        for attempt in range(self.max_retries + 1):
            self._pace()
            try:
                response = self.session.request(method, url, params=params, auth=auth,
                                                json=json_body, timeout=self.timeout)
            except (requests.Timeout, requests.ConnectionError) as exc:
                if attempt >= self.max_retries:
                    raise PublicApiError(f"Public API request failed: {type(exc).__name__}") from exc
                delay = min(self.max_wait, 2**attempt + random.uniform(0.0, 0.5))
                log.warning("Public API network error; retrying in %.1fs", delay)
                time.sleep(delay)
                continue

            if response.status_code == 403:
                raise PublicApiError("Public API returned 403; credentials or access policy need attention")
            if response.status_code == 429 or response.status_code >= 500:
                if attempt >= self.max_retries:
                    raise PublicApiError(f"Public API returned HTTP {response.status_code} after retries")
                retry_after = retry_after_seconds(response.headers.get("Retry-After"))
                delay = min(self.max_wait, retry_after if retry_after is not None else 2**attempt)
                delay = min(self.max_wait, delay + random.uniform(0.0, min(0.5, delay * 0.1)))
                log.warning("Public API returned HTTP %s; retrying after %.1fs", response.status_code, delay)
                time.sleep(delay)
                continue
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise PublicApiError("Public API returned a non-object JSON response")
            return payload
        raise AssertionError("retry loop exhausted")

    def _pace(self) -> None:
        if not self.min_interval_seconds:
            return
        with self._pace_lock:
            now = time.monotonic()
            delay = self.min_interval_seconds - (now - self._last_request_at)
            if delay > 0:
                time.sleep(delay)
            self._last_request_at = time.monotonic()
