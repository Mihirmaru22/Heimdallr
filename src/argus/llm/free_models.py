"""One shared language-model service for every component: free OpenRouter models, then a local model.

Rules (Ronak, 2026-10-17):
- only free models: every OpenRouter model id must end in ":free"; anything else is refused;
- every vertical and agent gets the same service, so the daily OpenRouter quota is shared and
  counted in one place;
- models read and write text (extraction, summaries, verification prose); decisions (relevance,
  routing, ranking, stop/continue) belong to Laya, see argus.brain.decisions.

Configuration (environment):
    OPENROUTER_API_KEY / OPEN_ROUTER_API (or .env)  the account key
    HEIMDALLR_FREE_MODELS     comma-separated OpenRouter free model ids, tried in order
    HEIMDALLR_LOCAL_MODEL     Ollama model used when OpenRouter is exhausted (default qwen2.5:7b;
                              set to "" to disable); HEIMDALLR_LLM_URL for a non-default Ollama URL
    HEIMDALLR_OPENROUTER_DAILY  requests per UTC day before switching to the local model (default 1000)
    HEIMDALLR_CACHE_DIR       where the daily usage counter is kept (default ~/.cache/heimdallr)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import threading
import time
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from argus.llm.provider import LLMProvider

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

OPENROUTER_URL = "https://openrouter.ai/api/v1"
# Free models: 20 requests per minute (openrouter.ai/docs/api-reference/limits, checked 2026-10-17).
MIN_INTERVAL_SECONDS = 3.1
DEFAULT_LOCAL_MODEL = "qwen2.5:7b"


class ModelUnavailable(Exception):
    """No configured model could answer (quota used up, refused, or unreachable)."""


class NotAFreeModel(ValueError):
    pass


def require_free(model_id: str) -> str:
    model_id = model_id.strip()
    if not model_id.endswith(":free"):
        raise NotAFreeModel(f"{model_id!r} is not a free OpenRouter model (ids must end in ':free'); paid models are not allowed")
    return model_id


def _cache_dir() -> Path:
    return Path(os.environ.get("HEIMDALLR_CACHE_DIR") or Path.home() / ".cache" / "heimdallr")


class _DailyQuota:
    """Requests used today (UTC), persisted so several runs on one day share the budget."""

    def __init__(self, limit: int, path: Path) -> None:
        self.limit, self.path = limit, path

    def _today(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def used(self) -> int:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return 0
        return int(data.get(self._today(), 0))

    def take(self) -> bool:
        used = self.used()
        if used >= self.limit:
            return False
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({self._today(): used + 1}), encoding="utf-8")
        except OSError:
            pass
        return True


class FreeModelService(LLMProvider):
    """Chat completions from free OpenRouter models, falling back to a local Ollama model."""

    def __init__(
        self,
        free_models: list[str],
        api_key: str = "",
        local_model: str = DEFAULT_LOCAL_MODEL,
        local_url: str = "http://localhost:11434",
        daily_limit: int = 1000,
        timeout: float = 120.0,
    ) -> None:
        self.free_models = [require_free(m) for m in free_models] if api_key else []
        self.api_key = api_key
        self.local_model, self.local_url = local_model, local_url.rstrip("/")
        self.timeout = timeout
        self.quota = _DailyQuota(daily_limit, _cache_dir() / "openrouter_usage.json")
        self.exhausted: set[str] = set()
        self.calls: dict[str, int] = {}
        self._lock = threading.Lock()
        self._last_openrouter = 0.0

    @classmethod
    def from_env(cls) -> "FreeModelService | None":
        from argus.llm.openrouter import OpenRouterLLMProvider  # key from env or .env

        key = OpenRouterLLMProvider().api_key
        models = [m for m in os.environ.get("HEIMDALLR_FREE_MODELS", "").split(",") if m.strip()]
        local = os.environ.get("HEIMDALLR_LOCAL_MODEL", DEFAULT_LOCAL_MODEL).strip()
        if not (key and models) and not local:
            return None
        return cls(
            free_models=models,
            api_key=key,
            local_model=local,
            local_url=os.environ.get("HEIMDALLR_LLM_URL", "http://localhost:11434"),
            daily_limit=int(os.environ.get("HEIMDALLR_OPENROUTER_DAILY", "1000") or 1000),
        )

    @property
    def label(self) -> str:
        names = [f"openrouter:{m}" for m in self.free_models] + ([f"ollama:{self.local_model}"] if self.local_model else [])
        return " > ".join(names) or "none"

    def status(self) -> dict[str, Any]:
        return {"models": self.label, "openrouter_used_today": self.quota.used(), "daily_limit": self.quota.limit,
                "exhausted": sorted(self.exhausted), "calls": dict(self.calls)}

    # --- transport -----------------------------------------------------------------------------

    def _openrouter(self, model: str, messages: list[dict[str, str]], json_mode: bool) -> str:
        with self._lock:
            if not self.quota.take():
                raise ModelUnavailable(f"OpenRouter daily limit of {self.quota.limit} reached")
            wait = MIN_INTERVAL_SECONDS - (time.monotonic() - self._last_openrouter)
            if wait > 0:
                time.sleep(wait)
            self._last_openrouter = time.monotonic()
        payload: dict[str, Any] = {"model": model, "temperature": 0, "messages": messages}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        resp = httpx.post(
            f"{OPENROUTER_URL}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "X-Title": "Heimdallr Research"},
            json=payload,
            timeout=self.timeout,
        )
        if resp.status_code in (401, 402, 403, 404, 429) or resp.status_code >= 500:
            raise ModelUnavailable(f"openrouter:{model} refused: HTTP {resp.status_code} {resp.text[:200]}")
        resp.raise_for_status()
        data = resp.json()
        if data.get("error"):
            raise ModelUnavailable(f"openrouter:{model} error: {data['error']}")
        return str(data["choices"][0]["message"]["content"])

    def _ollama(self, messages: list[dict[str, str]], json_mode: bool) -> str:
        payload: dict[str, Any] = {"model": self.local_model, "stream": False, "options": {"temperature": 0}, "messages": messages}
        if json_mode:
            payload["format"] = "json"
        resp = httpx.post(f"{self.local_url}/api/chat", json=payload, timeout=max(self.timeout, 180.0))
        if resp.status_code in (404,) or resp.status_code >= 500:
            raise ModelUnavailable(f"ollama:{self.local_model} refused: HTTP {resp.status_code}")
        resp.raise_for_status()
        return str(resp.json().get("message", {}).get("content", ""))

    def chat(self, system: str, user: str, json_mode: bool = True) -> str:
        """Text from the first model that answers; ModelUnavailable when none can."""
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        for model in self.free_models:
            if model in self.exhausted:
                continue
            try:
                out = self._openrouter(model, messages, json_mode)
                self.calls[model] = self.calls.get(model, 0) + 1
                return out
            except (ModelUnavailable, httpx.HTTPError) as exc:
                logger.warning("%s; trying the next model", exc)
                self.exhausted.add(model)
        if self.local_model and f"ollama:{self.local_model}" not in self.exhausted:
            try:
                out = self._ollama(messages, json_mode)
                self.calls[self.local_model] = self.calls.get(self.local_model, 0) + 1
                return out
            except (ModelUnavailable, httpx.HTTPError) as exc:
                logger.warning("local model unavailable: %s", exc)
                self.exhausted.add(f"ollama:{self.local_model}")
        raise ModelUnavailable("no free or local model is available")

    async def generate_structured(
        self,
        prompt: str,
        response_model: type[T],
        system_prompt: str | None = None,
        temperature: float = 0.0,
    ) -> T:
        """LLMProvider interface used by the planner, worker and verifier agents."""
        from argus.llm.openrouter import extract_json_payload

        schema = json.dumps(response_model.model_json_schema(), indent=2)
        system = (system_prompt or "").strip() + f"\n\nRespond ONLY with a JSON object conforming to this JSON schema:\n{schema}"
        raw = await asyncio.to_thread(self.chat, system.strip(), prompt, True)
        return response_model.model_validate_json(extract_json_payload(raw))


_SERVICE: FreeModelService | None = None
_SERVICE_READY = False


def get_free_model_service() -> FreeModelService | None:
    """The process-wide service (one quota, one fallback state for all components)."""
    global _SERVICE, _SERVICE_READY
    if not _SERVICE_READY:
        _SERVICE_READY = True
        try:
            _SERVICE = FreeModelService.from_env()
        except NotAFreeModel as exc:
            logger.error("%s", exc)
            raise
    return _SERVICE


def configuration_note() -> str:
    """Why the free OpenRouter models are not in use, or "" when they are configured.

    A run that falls back to the local model reads every page with the weaker model. Silence about
    that looks like a model choice; it is almost always a missing environment variable, so the run
    says which one (Ronak, 2026-10-19).
    """
    from argus.llm.openrouter import OpenRouterLLMProvider

    key = OpenRouterLLMProvider().api_key
    models = [m for m in os.environ.get("HEIMDALLR_FREE_MODELS", "").split(",") if m.strip()]
    chain = os.environ.get("HEIMDALLR_LLM", "")
    if "openrouter:" in chain:
        return "" if key else "OpenRouter is in HEIMDALLR_LLM but no key is set (OPENROUTER_API_KEY), so its models were skipped."
    missing = []
    if not key:
        missing.append("no OpenRouter key (OPENROUTER_API_KEY)")
    if not models:
        missing.append("no free model ids (HEIMDALLR_FREE_MODELS, comma-separated ids ending in ':free')")
    if not missing:
        return ""
    return ("Free OpenRouter models were not used: " + " and ".join(missing)
            + ". Every page was read by the local model instead.")


def reset_free_model_service() -> None:
    """Forget the shared service (tests, or after changing the environment)."""
    global _SERVICE, _SERVICE_READY
    _SERVICE, _SERVICE_READY = None, False
