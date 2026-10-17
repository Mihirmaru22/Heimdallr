import asyncio
import json
import os
import re
from typing import TypeVar

import httpx
from pydantic import BaseModel

from argus.llm.provider import LLMProvider
from argus.search.pipeline import create_safe_async_client

T = TypeVar("T", bound=BaseModel)


def extract_json_payload(raw_content: str) -> str:
    """Extract a valid JSON object or array from model output with potential markdown or conversational prefixes."""
    text = raw_content.strip()

    # 1. Search for markdown code fences (```json ... ``` or ``` ... ```)
    fence_matches = list(
        re.finditer(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    )
    for m in fence_matches:
        candidate = m.group(1).strip()
        try:
            json.loads(candidate)
            return candidate
        except (ValueError, TypeError):
            continue

    # 2. Extract outermost JSON object {...} or array [...]
    start_brace = text.find("{")
    end_brace = text.rfind("}")
    start_bracket = text.find("[")
    end_bracket = text.rfind("]")

    candidates: list[tuple[int, str]] = []
    if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
        candidates.append((start_brace, text[start_brace : end_brace + 1]))
    if start_bracket != -1 and end_bracket != -1 and end_bracket > start_bracket:
        candidates.append((start_bracket, text[start_bracket : end_bracket + 1]))

    candidates.sort(key=lambda x: x[0])
    for _, candidate in candidates:
        try:
            json.loads(candidate)
            return candidate
        except (ValueError, TypeError):
            continue

    # 3. Fallback: strip leading/trailing code fences if partial
    cleaned = text
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    cleaned = cleaned.removesuffix("```").strip()
    return cleaned


class OpenRouterLLMProvider(LLMProvider):
    """OpenRouter LLM provider supporting structured Pydantic outputs. Free models only.

    ``model`` must be a free OpenRouter id (ending in ":free"); without one, the first of
    HEIMDALLR_FREE_MODELS is used. A paid id is refused (Ronak, 2026-10-17: no paid models).
    For the shared daily quota and the local fallback, use argus.llm.free_models instead.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout: float = 60.0,
    ) -> None:
        self.api_key = (
            api_key
            or os.getenv("OPENROUTER_API_KEY", "")
            or os.getenv("OPEN_ROUTER_API", "")
        )
        if not self.api_key:
            for env_path in ("docs/.env", ".env"):
                if os.path.isfile(env_path):
                    try:
                        with open(env_path, encoding="utf-8") as f:
                            for line in f:
                                if line.strip().startswith(("OPEN_ROUTER_API", "OPENROUTER_API_KEY")):
                                    parts = line.strip().split("=", 1)
                                    if len(parts) == 2:
                                        self.api_key = parts[1].strip()
                                        break
                    except OSError:
                        pass
                if self.api_key:
                    break

        from argus.llm.free_models import require_free

        if model is None:
            configured = [m for m in os.environ.get("HEIMDALLR_FREE_MODELS", "").split(",") if m.strip()]
            model = configured[0].strip() if configured else ""
        self.model = require_free(model) if model else ""
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def generate_structured(
        self,
        prompt: str,
        response_model: type[T],
        system_prompt: str | None = None,
        temperature: float = 0.0,
    ) -> T:
        if not self.model:
            raise ValueError("No free OpenRouter model configured (pass model='<id>:free' or set HEIMDALLR_FREE_MODELS)")
        schema = response_model.model_json_schema()
        schema_instruction = (
            f"You MUST respond ONLY with a valid JSON object strictly conforming to the following JSON schema:\n"
            f"{json.dumps(schema, indent=2)}\n"
            f"Do not include any Markdown wrapping (e.g. ```json), commentary, or text outside the JSON object."
        )

        full_system = (
            f"{system_prompt.strip()}\n\n{schema_instruction}"
            if system_prompt
            else schema_instruction
        )

        messages = [
            {"role": "system", "content": full_system},
            {"role": "user", "content": prompt},
        ]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://github.com/argus-research/argus",
            "X-Title": "Argus Research Engine",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }

        retries = 3
        backoff_delay = 5.0

        async with create_safe_async_client(timeout=self.timeout) as client:
            for attempt in range(retries):
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                if response.status_code in (429, 502, 503, 504) and attempt < retries - 1:
                    retry_after = response.headers.get("Retry-After")
                    sleep_time = (
                        float(retry_after)
                        if retry_after and retry_after.isdigit()
                        else backoff_delay * (2**attempt)
                    )
                    await asyncio.sleep(sleep_time)
                    continue

                response.raise_for_status()
                data = response.json()
                break

        raw_content = data["choices"][0]["message"]["content"]
        clean_json = extract_json_payload(raw_content)

        return response_model.model_validate_json(clean_json)
