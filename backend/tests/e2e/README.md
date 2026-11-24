# End-to-end client helpers

`resilient_client.py` provides a deterministic Playwright context and a polite `requests.Session` wrapper for
authorized browser checks and public-data reads.

Install the development tools from `backend/` with `uv sync --group dev`, then install the browser once with
`uv run playwright install chromium`.

For browser tests, call `new_test_context(browser)` to load the local saved state when it exists. After the test
has explicitly confirmed a successful login, call `require_authenticated_page(page, success_selector="...")` with
an authenticated-only UI marker, then call `save_authenticated_state(context, authenticated=True)`. Use
`goto_checked(page, url)` for bounded `domcontentloaded` navigation and immediate 403/429 handling. The bounded
marker wait turns an expired session or login redirect into a clear failure rather than a navigation loop. The
generated cookie/local-storage file is written with owner-only permissions under `.auth/`, which is ignored by
Git. Do not copy it into fixtures or commit it.

For public API reads, use `ResilientPublicClient` as a context manager. It keeps cookies in one persistent
`requests.Session`, uses one stable User-Agent, retries only `GET` and `HEAD` after `429`, honors bounded
`Retry-After` values, and applies capped exponential backoff with positive jitter. A `403` raises
`ForbiddenResponseError` immediately; it is not retried or worked around. A `429` still present after the retry
budget is returned to the caller for normal error handling; waits that exceed the total retry budget raise
`RateLimitDeferredError` instead of sleeping indefinitely.

`batch_orchestrator.py` wraps either client with a 2.5–6 second interval between items. It catches request
timeouts, connection errors, and Playwright errors per item, logs a randomized 8–20 second cooldown, records
that item as skipped, and advances the queue. Unclassified failures, cancellations, 403s, and exhausted rate
limits still stop the run. `run_browser_batch` can rotate between explicitly supplied authorized test profiles
after a fixed operation count. It keeps one shared batch pacing/cooldown loop across switches; profile rotation
does not grant additional request-rate capacity. `run_public_batch` shares one `ResilientPublicClient`.
