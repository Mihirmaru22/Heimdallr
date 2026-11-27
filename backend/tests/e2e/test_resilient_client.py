from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
import requests

pytest.importorskip("playwright")

from tests.e2e import batch_orchestrator, resilient_client


class FakeContext:
    def __init__(self, state=None):
        self.state = state or {"cookies": [{"name": "session", "value": "secret"}], "origins": []}
        self.closed = False

    async def storage_state(self):
        return self.state

    async def close(self):
        self.closed = True


class FakeBrowser:
    def __init__(self):
        self.calls = []
        self.contexts = []

    async def new_context(self, **kwargs):
        self.calls.append(kwargs)
        context = FakeContext()
        self.contexts.append(context)
        return context


class FakeResponse:
    def __init__(self, status):
        self.status = status


class FakePage:
    async def goto(self, *args, **kwargs):
        return FakeResponse(403)


def test_context_settings_and_authenticated_storage_state_are_deterministic(tmp_path: Path):
    async def run():
        state_path = tmp_path / ".auth" / "state.json"
        context = FakeContext()
        await resilient_client.save_authenticated_state(context, authenticated=True, storage_state_path=state_path)
        assert json.loads(state_path.read_text()) == context.state
        if hasattr(state_path, "stat"):
            assert state_path.stat().st_mode & 0o777 == 0o600

        browser = FakeBrowser()
        reused = await resilient_client.new_test_context(browser, storage_state_path=state_path, base_url="http://local.test")
        options = browser.calls[0]
        assert options["viewport"] == {"width": 1440, "height": 900}
        assert options["locale"] == "en-US"
        assert options["user_agent"] == resilient_client.USER_AGENT
        assert options["storage_state"] == str(state_path)
        assert options["base_url"] == "http://local.test"
        await reused.close()

        with pytest.raises(ValueError, match="before login"):
            await resilient_client.save_authenticated_state(context, authenticated=False, storage_state_path=state_path)

    asyncio.run(run())


@pytest.mark.asyncio
async def test_real_browser_context_and_saved_state_on_local_site(sites, tmp_path: Path):
    from playwright.async_api import Error as PlaywrightError
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        try:
            browser = await playwright.chromium.launch()
        except PlaywrightError as exc:
            pytest.skip(f"Chromium is not installed for Playwright: {exc}")
        try:
            state_path = tmp_path / ".auth" / "local-state.json"
            base_url = f"http://127.0.0.1:{sites['port']}"
            context = await resilient_client.new_test_context(browser, storage_state_path=state_path,
                                                              base_url=base_url)
            page = await context.new_page()
            await page.goto("/", wait_until="domcontentloaded")
            initial = await page.evaluate("""() => ({width: innerWidth, height: innerHeight,
                language: navigator.language, userAgent: navigator.userAgent})""")
            assert (initial["width"], initial["height"]) == (1440, 900)
            assert initial["language"] == "en-US"
            assert initial["userAgent"] == resilient_client.USER_AGENT
            await page.evaluate("localStorage.setItem('test-token', 'local-value')")
            await context.add_cookies([{"name": "session", "value": "cookie-value", "url": base_url}])
            await resilient_client.save_authenticated_state(context, authenticated=True, storage_state_path=state_path)
            await context.close()

            restored = await resilient_client.new_test_context(browser, storage_state_path=state_path,
                                                               base_url=base_url)
            restored_page = await restored.new_page()
            await restored_page.goto("/", wait_until="domcontentloaded")
            values = await restored_page.evaluate("""() => ({token: localStorage.getItem('test-token'),
                cookie: document.cookie})""")
            assert values["token"] == "local-value"
            assert "session=cookie-value" in values["cookie"]
            await restored.close()
        finally:
            await browser.close()


def test_browser_403_is_fail_fast():
    async def run():
        with pytest.raises(resilient_client.ForbiddenResponseError, match="403 Forbidden"):
            await resilient_client.goto_checked(FakePage(), "https://private.test/path?token=not-logged")

    asyncio.run(run())


def test_http_retry_after_and_403_fail_fast(monkeypatch):
    sleeps = []
    monkeypatch.setattr(resilient_client.time, "sleep", sleeps.append)
    monkeypatch.setattr(resilient_client.random, "uniform", lambda _a, _b: 0)

    class Response:
        def __init__(self, status, headers=None):
            self.status_code = status
            self.headers = headers or {}

    class Session:
        def __init__(self, responses):
            self.responses = iter(responses)
            self.headers = {}
            self.calls = 0

        def request(self, *_args, **_kwargs):
            self.calls += 1
            return next(self.responses)

    session = Session([Response(429, {"Retry-After": "3"}), Response(200)])
    client = resilient_client.ResilientPublicClient(
        policy=resilient_client.RetryPolicy(max_retries=1, max_jitter_seconds=0), session=session)
    assert client.get("https://public.test/api").status_code == 200
    assert sleeps == [3]
    assert session.calls == 2

    forbidden = Session([Response(403), Response(200)])
    client = resilient_client.ResilientPublicClient(session=forbidden)
    with pytest.raises(resilient_client.ForbiddenResponseError):
        client.get("https://public.test/api")
    assert forbidden.calls == 1


def test_batch_continues_after_socket_timeout(monkeypatch):
    async def no_sleep(_duration):
        return None

    monkeypatch.setattr(batch_orchestrator.asyncio, "sleep", no_sleep)

    async def operation(item):
        if item == "drop":
            raise requests.exceptions.Timeout("local simulated timeout")
        return item.upper()

    async def run():
        results = await batch_orchestrator.run_batch(
            ["drop", "ok"], operation,
            policy=batch_orchestrator.BatchPolicy(min_interval_seconds=0.01, max_interval_seconds=0.01,
                                                  min_error_cooldown_seconds=0.01,
                                                  max_error_cooldown_seconds=0.01))
        assert [result.status for result in results] == ["skipped", "completed"]
        assert results[1].value == "OK"

    asyncio.run(run())


def test_browser_profiles_rotate_without_resetting_batch_pacing(monkeypatch, tmp_path: Path):
    async def no_sleep(_duration):
        return None

    monkeypatch.setattr(batch_orchestrator.asyncio, "sleep", no_sleep)
    browser = FakeBrowser()
    profiles = [tmp_path / ".auth" / "state1.json", tmp_path / ".auth" / "state2.json"]
    for profile in profiles:
        profile.parent.mkdir(parents=True, exist_ok=True)
        profile.write_text(json.dumps({"cookies": [], "origins": []}))
    seen = []

    async def operation(context, item):
        seen.append(item)
        return item

    async def run():
        results = await batch_orchestrator.run_browser_batch(
            browser, [1, 2, 3], operation, storage_state_paths=profiles, profile_rotation_every=1,
            policy=batch_orchestrator.BatchPolicy(min_interval_seconds=0.01, max_interval_seconds=0.01,
                                                  min_error_cooldown_seconds=0.01,
                                                  max_error_cooldown_seconds=0.01))
        assert [result.value for result in results] == [1, 2, 3]

    asyncio.run(run())
    assert seen == [1, 2, 3]
    assert [call["storage_state"] for call in browser.calls] == [str(profiles[0]), str(profiles[1]), str(profiles[0])]
    assert browser.contexts[0].closed and browser.contexts[1].closed and browser.contexts[2].closed
