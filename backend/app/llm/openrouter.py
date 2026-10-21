"""The only way the app talks to a language model: OpenRouter, free models only, enforced here.

Rules this module guarantees, whatever a caller asks for:
- Only models whose id ends in ":free" AND whose listed prices are all zero are ever requested, one
  model per request (no `models` fallback list, so OpenRouter cannot route to a paid one on its own).
- If a reply comes from a model we did not ask for, or reports any cost, model use is switched off
  for the whole app until an admin turns it back on (`python -m app.cli llm-enable`).
- Requests are counted against the key's free daily allowance (50 a day, or 1,000 once 10 credits
  have ever been bought; OpenRouter decides which from the key) and 20 a minute. When the day's
  allowance is used up, calls fail with LLMUnavailable until midnight UTC instead of going further.
- When one free model is busy or failing, the next free model is tried; never a paid one.
The API key is never logged (logging_setup redacts sk-or- keys as well).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.config import get_settings

log = logging.getLogger("webdata.llm")

API = "https://openrouter.ai/api/v1"
FREE_DAILY = 50  # requests a day for keys that never bought credits
FUNDED_DAILY = 1000  # once 10 credits have ever been bought (it does not depend on the balance)
PER_MINUTE = 20
CATALOG_TTL = 6 * 3600
MODEL_COOLDOWN = 600  # seconds a failing model is skipped
MAX_MODELS_PER_CALL = 3
# Free models built for one narrow job (moderation, code, embeddings) are no use for reading web pages.
SPECIALIZED_RE = re.compile(r"safety|guard|moderat|code|coder|embed|rerank|tts|audio|ocr", re.I)
# Room for a reasoning model's thinking before its answer; with too little, the answer comes back empty.
MIN_TOKENS = 1024


class LLMUnavailable(Exception):
    """No free model can be used right now (no key, switched off, daily allowance used, all failing)."""


class PaidModelError(LLMUnavailable):
    """A reply came from a model we did not ask for or reported a cost; model use is now switched off."""


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _seconds_to_midnight() -> int:
    now = datetime.now(UTC)
    return int((datetime(now.year, now.month, now.day, tzinfo=UTC) + timedelta(days=1) - now).total_seconds()) + 1


def is_free(model: dict[str, Any]) -> bool:
    """A model may be used only when its id says :free and every price OpenRouter lists for it is zero."""
    if not str(model.get("id", "")).endswith(":free"):
        return False
    pricing = model.get("pricing") or {}
    if not pricing:
        return False
    try:
        return all(float(v or 0) == 0 for v in pricing.values())
    except (TypeError, ValueError):
        return False


def rank_models(models: list[dict[str, Any]], preferred: list[str]) -> list[str]:
    """Free model ids, best first: the admin's preference order, then ones that can return JSON, then context size."""
    free = [m for m in models if is_free(m) and (m["id"] in preferred or not SPECIALIZED_RE.search(m["id"]))]

    def key(m: dict[str, Any]) -> tuple:
        mid = m["id"]
        params = set(m.get("supported_parameters") or [])
        return (preferred.index(mid) if mid in preferred else len(preferred),
                0 if {"response_format", "structured_outputs"} & params else 1,
                -int(m.get("context_length") or 0), mid)
    return [m["id"] for m in sorted(free, key=key)]


class State:
    """Counters shared by the API and every worker, kept in Redis."""

    PREFIX = "webdata:llm:"

    def __init__(self, redis_client=None) -> None:
        if redis_client is None:
            import redis

            redis_client = redis.Redis.from_url(get_settings().redis_url, socket_timeout=2)
        self.r = redis_client

    def _get(self, key: str) -> str | None:
        v = self.r.get(self.PREFIX + key)
        return v.decode() if isinstance(v, bytes) else v

    def used_today(self) -> int:
        return int(self._get(f"day:{_today()}") or 0)

    def count_request(self, model: str, ok: bool) -> None:
        day = self.PREFIX + f"day:{_today()}"
        self.r.incr(day)
        self.r.expire(day, 2 * 86400)
        minute = self.PREFIX + f"min:{int(time.time() // 60)}"
        self.r.incr(minute)
        self.r.expire(minute, 120)
        stats = self.PREFIX + f"stats:{_today()}"
        self.r.hincrby(stats, f"{model}|{'ok' if ok else 'failed'}", 1)
        self.r.expire(stats, 8 * 86400)

    def count_failure(self, model: str, kind: str) -> None:
        stats = self.PREFIX + f"stats:{_today()}"
        self.r.hincrby(stats, f"{model}|{kind}", 1)
        self.r.expire(stats, 8 * 86400)

    def this_minute(self) -> int:
        return int(self._get(f"min:{int(time.time() // 60)}") or 0)

    def stats(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for k, v in (self.r.hgetall(self.PREFIX + f"stats:{_today()}") or {}).items():
            k = k.decode() if isinstance(k, bytes) else k
            model, kind = k.rsplit("|", 1)
            out.setdefault(model, {})[kind] = int(v)
        return out

    def daily_limit(self) -> int | None:
        v = self._get("daily_limit")
        return int(v) if v else None

    def set_daily_limit(self, limit: int) -> None:
        self.r.set(self.PREFIX + "daily_limit", str(limit), ex=86400)

    def exhaust_today(self) -> None:
        self.r.set(self.PREFIX + f"exhausted:{_today()}", "1", ex=_seconds_to_midnight())

    def exhausted(self) -> bool:
        return bool(self._get(f"exhausted:{_today()}"))

    def cool_down(self, model: str, seconds: int = MODEL_COOLDOWN) -> None:
        self.r.set(self.PREFIX + f"cooldown:{model}", "1", ex=seconds)

    def cooling(self, model: str) -> bool:
        return bool(self._get(f"cooldown:{model}"))

    def disable(self, reason: str) -> None:
        self.r.set(self.PREFIX + "disabled", reason[:500])

    def disabled(self) -> str | None:
        return self._get("disabled")

    def enable(self) -> None:
        self.r.delete(self.PREFIX + "disabled")

    def catalog(self) -> list[dict[str, Any]] | None:
        v = self._get("catalog")
        return json.loads(v) if v else None

    def save_catalog(self, models: list[dict[str, Any]]) -> None:
        self.r.set(self.PREFIX + "catalog", json.dumps(models), ex=CATALOG_TTL)


@dataclass
class Reply:
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    attempts: list[str] = field(default_factory=list)

    def json(self) -> Any:
        """The reply parsed as JSON, tolerating a ```json fence around it."""
        text = self.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else ""
            text = text.rsplit("```", 1)[0]
        return json.loads(text)


class OpenRouter:
    def __init__(self, client: httpx.AsyncClient | None = None, state: State | None = None,
                 api_key: str | None = None, sleep=asyncio.sleep) -> None:
        s = get_settings()
        self.api_key = api_key if api_key is not None else s.openrouter_api_key.get_secret_value()
        self.preferred = list(s.llm_preferred_models)
        self.client = client
        self.state = state
        self.sleep = sleep

    def _state(self) -> State:
        self.state = self.state or State()
        return self.state

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "X-Title": "WebData AI (local)"}

    async def _http(self) -> httpx.AsyncClient:
        if self.client is None:
            self.client = httpx.AsyncClient(timeout=httpx.Timeout(90, connect=10))
        return self.client

    async def free_models(self) -> list[str]:
        """Usable free model ids, best first (the catalog is refreshed every few hours)."""
        state = self._state()
        models = state.catalog()
        if models is None:
            resp = await (await self._http()).get(f"{API}/models")
            resp.raise_for_status()
            models = [{"id": m.get("id"), "pricing": m.get("pricing"), "context_length": m.get("context_length"),
                       "supported_parameters": m.get("supported_parameters")}
                      for m in resp.json().get("data", []) if is_free(m)]
            state.save_catalog(models)
        return rank_models(models, self.preferred)

    async def key_info(self) -> dict[str, Any]:
        """The key's own limits from OpenRouter; also sets the daily allowance the counters use."""
        if not self.api_key:
            raise LLMUnavailable("no OpenRouter key is configured (WEBDATA_OPENROUTER_API_KEY)")
        resp = await (await self._http()).get(f"{API}/key", headers=self._headers())
        if resp.status_code == 401:
            raise LLMUnavailable("OpenRouter rejected the API key")
        resp.raise_for_status()
        data = resp.json().get("data", {})
        limit = FREE_DAILY if data.get("is_free_tier", True) else FUNDED_DAILY
        self._state().set_daily_limit(limit)
        return {"is_free_tier": data.get("is_free_tier"), "daily_free_requests": limit,
                "rate_limit": data.get("rate_limit")}

    async def status(self) -> dict[str, Any]:
        state = self._state()
        out: dict[str, Any] = {"configured": bool(self.api_key), "disabled": state.disabled(),
                               "used_today": state.used_today(), "daily_limit": state.daily_limit(),
                               "exhausted_today": state.exhausted(), "models": [], "stats": state.stats()}
        if self.api_key and not out["disabled"]:
            try:
                out.update(await self.key_info())
                out["daily_limit"] = state.daily_limit()
                out["models"] = await self.free_models()
            except (LLMUnavailable, httpx.HTTPError) as exc:
                out["error"] = str(exc) if isinstance(exc, LLMUnavailable) else type(exc).__name__
        return out

    async def _check_allowance(self) -> None:
        if not self.api_key:
            raise LLMUnavailable("no OpenRouter key is configured (WEBDATA_OPENROUTER_API_KEY)")
        state = self._state()
        reason = state.disabled()
        if reason:
            raise LLMUnavailable(f"model use is switched off: {reason}")
        if state.daily_limit() is None:
            await self.key_info()
        if state.exhausted() or state.used_today() >= (state.daily_limit() or FREE_DAILY):
            raise LLMUnavailable("today's free model allowance is used up; it resets at midnight UTC")
        if state.this_minute() >= PER_MINUTE:
            await self.sleep(61 - time.time() % 60)

    def _check_reply(self, requested: str, body: dict[str, Any]) -> None:
        """Switch model use off if this reply was not from the free model we asked for, or cost anything."""
        got = str(body.get("model") or "")
        cost = (body.get("usage") or {}).get("cost")
        problem = None
        if got and got not in (requested, requested.removesuffix(":free")):
            problem = f"asked for {requested} but the reply came from {got}"
        elif cost not in (None, 0, 0.0, "0"):
            problem = f"a reply from {requested} reported a cost of {cost}"
        if problem:
            self._state().disable(problem)
            log.error("Model use switched off: %s", problem)
            raise PaidModelError(problem)

    async def chat(self, messages: list[dict[str, str]], *, json_mode: bool = False, max_tokens: int = 1200,
                   temperature: float = 0.0) -> Reply:
        """One completion from the best available free model, trying the next free model if one fails."""
        await self._check_allowance()
        state = self._state()
        candidates = [m for m in await self.free_models() if not state.cooling(m)]
        if not candidates:
            raise LLMUnavailable("no free model is available right now")
        http = await self._http()
        tried: list[str] = []
        problems: list[str] = []
        for model in candidates[:MAX_MODELS_PER_CALL]:
            tried.append(model)
            # Reasoning models spend tokens thinking first, so the limit has a floor, and their thinking is
            # left out of the reply (`exclude`) since only the answer is used.
            payload: dict[str, Any] = {"model": model, "messages": messages,
                                       "max_tokens": max(max_tokens, MIN_TOKENS), "temperature": temperature,
                                       "reasoning": {"effort": "low", "exclude": True}, "usage": {"include": True}}
            if json_mode:
                payload["response_format"] = {"type": "json_object"}
            try:
                resp = await http.post(f"{API}/chat/completions", headers=self._headers(), json=payload)
            except httpx.HTTPError as exc:
                state.count_failure(model, "network")
                state.cool_down(model, 120)
                problems.append(f"{model}: {type(exc).__name__}")
                continue
            state.count_request(model, resp.status_code == 200)
            try:
                body = resp.json()
            except ValueError:
                body = {}
            error = body.get("error") if isinstance(body, dict) else None
            if resp.status_code == 429 or (error and str(error.get("code")) == "429"):
                message = str((error or {}).get("message", ""))
                if "per-day" in message or "per day" in message:
                    state.exhaust_today()
                    raise LLMUnavailable("today's free model allowance is used up; it resets at midnight UTC")
                state.count_failure(model, "rate_limited")
                state.cool_down(model, 120)  # the model's upstream is busy; try another free one
                problems.append(f"{model}: rate limited")
                continue
            if resp.status_code == 402:
                # Free models can refuse a key whose balance went negative; never top up from here.
                raise LLMUnavailable("OpenRouter refused the request (402: the account balance is negative)")
            if resp.status_code != 200 or error:
                state.count_failure(model, f"http_{resp.status_code}")
                state.cool_down(model)
                problems.append(f"{model}: HTTP {resp.status_code} {str((error or {}).get('message', ''))[:120]}")
                continue
            self._check_reply(model, body)
            choices = body.get("choices") or []
            text = ((choices[0] if choices else {}).get("message") or {}).get("content") or ""
            if not text.strip():
                state.count_failure(model, "empty")
                state.cool_down(model, 120)
                finish = (choices[0] if choices else {}).get("finish_reason")
                problems.append(f"{model}: empty reply (finish_reason={finish})")
                continue
            usage = body.get("usage") or {}
            return Reply(text, model, int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0),
                         tried)
        raise LLMUnavailable("no free model answered: " + "; ".join(problems))

    async def aclose(self) -> None:
        if self.client is not None:
            await self.client.aclose()
