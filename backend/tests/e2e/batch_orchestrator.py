"""Paced, failure-isolated orchestration for authorized end-to-end and public-data batches.

One batch uses one authorized browser profile/client. Transient per-item failures are recorded
and skipped after a bounded cooldown; cancellation, permission errors, and other unclassified
failures propagate so the run does not conceal them.
"""

from __future__ import annotations

import asyncio
import logging
import math
import random
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, TypeVar

import requests
from playwright.async_api import Browser, BrowserContext
from playwright.async_api import Error as PlaywrightError

from .resilient_client import (
    DEFAULT_STATE_PATH,
    RateLimitDeferredError,
    ResilientPublicClient,
    new_test_context,
)

T = TypeVar("T")
R = TypeVar("R")
log = logging.getLogger("heimdallr.e2e.batch")


@dataclass(frozen=True)
class BatchPolicy:
    min_interval_seconds: float = 2.5
    max_interval_seconds: float = 6.0
    min_error_cooldown_seconds: float = 8.0
    max_error_cooldown_seconds: float = 20.0

    def __post_init__(self) -> None:
        values = (self.min_interval_seconds, self.max_interval_seconds,
                  self.min_error_cooldown_seconds, self.max_error_cooldown_seconds)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Batch delays must be finite numbers")
        if not 0 < self.min_interval_seconds <= self.max_interval_seconds <= 30:
            raise ValueError("The inter-item interval must be positive and no longer than 30 seconds")
        if not 0 < self.min_error_cooldown_seconds <= self.max_error_cooldown_seconds <= 120:
            raise ValueError("The error cooldown must be positive and no longer than 120 seconds")


@dataclass
class BatchItemResult(Generic[T, R]):
    index: int
    item: T
    status: str  # completed | skipped
    value: R | None = None
    error_type: str | None = None


RECOVERABLE_ERRORS = (
    requests.exceptions.Timeout,
    requests.exceptions.ConnectionError,
    PlaywrightError,
    asyncio.TimeoutError,
)


async def run_batch(
    items: Iterable[T],
    operation: Callable[[T], Awaitable[R]],
    *,
    policy: BatchPolicy | None = None,
) -> list[BatchItemResult[T, R]]:
    """Run each item in order, pace fetches, and isolate the expected transient failures."""
    pacing = policy or BatchPolicy()
    results: list[BatchItemResult[T, R]] = []

    for index, item in enumerate(items):
        if index:
            await asyncio.sleep(random.uniform(pacing.min_interval_seconds, pacing.max_interval_seconds))
        try:
            value = await operation(item)
        except RECOVERABLE_ERRORS as exc:
            cooldown = random.uniform(pacing.min_error_cooldown_seconds, pacing.max_error_cooldown_seconds)
            error_type = type(exc).__name__
            log.warning("Batch item %d had a transient %s; cooling down %.1fs, then continuing",
                        index + 1, error_type, cooldown)
            results.append(BatchItemResult(index=index, item=item, status="skipped", error_type=error_type))
            await asyncio.sleep(cooldown)
        else:
            results.append(BatchItemResult(index=index, item=item, status="completed", value=value))

    return results


async def run_browser_batch(
    browser: Browser,
    items: Iterable[T],
    operation: Callable[[BrowserContext, T], Awaitable[R]],
    *,
    storage_state_path: Path = DEFAULT_STATE_PATH,
    storage_state_paths: Sequence[Path] | None = None,
    profile_rotation_every: int = 100,
    base_url: str | None = None,
    policy: BatchPolicy | None = None,
) -> list[BatchItemResult[T, R]]:
    """Run a paced batch with optional rotation across authorized test accounts.

    Rotation changes only browser authentication state. The one shared batch loop keeps pacing and
    error cooldowns across profile changes, so profiles do not create extra request-rate capacity.
    """
    profiles = tuple(Path(path) for path in (storage_state_paths or (storage_state_path,)))
    if not profiles or profile_rotation_every < 1:
        raise ValueError("At least one browser profile and a positive rotation interval are required")
    profile_index = 0
    operation_count = 0
    context = await new_test_context(browser, storage_state_path=profiles[profile_index], base_url=base_url)

    async def run_with_profile(item: T) -> R:
        nonlocal context, profile_index, operation_count
        if operation_count and operation_count % profile_rotation_every == 0 and len(profiles) > 1:
            await context.close()
            profile_index = (profile_index + 1) % len(profiles)
            context = await new_test_context(browser, storage_state_path=profiles[profile_index], base_url=base_url)
            log.info("Switched to authorized browser test profile %d of %d", profile_index + 1, len(profiles))
        operation_count += 1
        return await operation(context, item)

    try:
        return await run_batch(items, run_with_profile, policy=policy)
    finally:
        await context.close()


async def run_public_batch(
    items: Iterable[T],
    client: ResilientPublicClient,
    operation: Callable[[ResilientPublicClient, T], requests.Response],
    *,
    policy: BatchPolicy | None = None,
) -> list[BatchItemResult[T, requests.Response]]:
    """Run synchronous requests work off the event loop using one persistent public-data client."""
    return await run_batch(
        items,
        lambda item: asyncio.to_thread(_run_public_operation, client, operation, item),
        policy=policy,
    )


def _run_public_operation(
    client: ResilientPublicClient,
    operation: Callable[[ResilientPublicClient, T], requests.Response],
    item: T,
) -> requests.Response:
    response = operation(client, item)
    if response.status_code == 429:
        log.error("Public-data batch still received 429 after the client's retry budget; stopping the run")
        raise RateLimitDeferredError("The server is still rate-limiting this batch; resume after its cooldown")
    return response
