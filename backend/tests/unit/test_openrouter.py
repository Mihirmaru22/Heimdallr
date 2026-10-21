"""The free-only model gateway: which models it will use, the cost guard, the allowance and fallbacks."""

import httpx
import pytest

from app.llm.openrouter import FREE_DAILY, FUNDED_DAILY, LLMUnavailable, OpenRouter, PaidModelError, State, is_free


class FakeRedis:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, ex=None):
        self.data[key] = value

    def delete(self, key):
        self.data.pop(key, None)

    def incr(self, key):
        self.data[key] = str(int(self.data.get(key, 0)) + 1)

    def expire(self, key, seconds):
        pass

    def hincrby(self, key, field, n):
        h = self.data.setdefault(key, {})
        h[field] = h.get(field, 0) + n

    def hgetall(self, key):
        return self.data.get(key, {})


FREE = {"id": "good/model-70b:free", "context_length": 128000, "supported_parameters": ["response_format"],
        "pricing": {"prompt": "0", "completion": "0", "request": "0"}}
FREE_SMALL = {"id": "small/model-8b:free", "context_length": 32000, "supported_parameters": [],
              "pricing": {"prompt": "0", "completion": "0"}}
PAID = {"id": "paid/model", "pricing": {"prompt": "0.000003", "completion": "0.000015"}}
SNEAKY = {"id": "sneaky/model:free", "pricing": {"prompt": "0", "completion": "0.000001"}}  # :free in name only


def gateway(handler, *, key="sk-or-test", funded=True, state=None):
    calls = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [PAID, SNEAKY, FREE_SMALL, FREE]})
        if request.url.path.endswith("/key"):
            return httpx.Response(200, json={"data": {"is_free_tier": not funded, "rate_limit": {"requests": 20}}})
        return handler(request)

    async def no_sleep(_s):
        return None

    router = OpenRouter(httpx.AsyncClient(transport=httpx.MockTransport(wrapped)), state or State(FakeRedis()),
                        api_key=key, sleep=no_sleep)
    return router, calls


def answer(model, text="ready", cost=0):
    return httpx.Response(200, json={"model": model, "choices": [{"message": {"content": text}}],
                                     "usage": {"prompt_tokens": 5, "completion_tokens": 1, "cost": cost}})


def test_only_zero_priced_free_models_count_as_free():
    assert is_free(FREE) and is_free(FREE_SMALL)
    assert not is_free(PAID) and not is_free(SNEAKY)
    assert not is_free({"id": "x:free"})  # no prices listed: not trusted


async def test_uses_the_best_free_model_and_never_sends_a_fallback_list():
    router, calls = gateway(lambda r: answer("good/model-70b:free"))
    assert await router.free_models() == ["good/model-70b:free", "small/model-8b:free"]
    reply = await router.chat([{"role": "user", "content": "hi"}], json_mode=True)
    assert reply.model == "good/model-70b:free" and reply.text == "ready"
    sent = [c for c in calls if c.url.path.endswith("/chat/completions")][0]
    body = httpx.Response(200, content=sent.content).json()
    assert body["model"] == "good/model-70b:free" and "models" not in body
    assert body["response_format"] == {"type": "json_object"}
    assert router.state.used_today() == 1 and router.state.daily_limit() == FUNDED_DAILY


async def test_a_reply_from_another_model_or_with_a_cost_switches_model_use_off():
    router, _ = gateway(lambda r: answer("paid/model"))
    with pytest.raises(PaidModelError, match="reply came from paid/model"):
        await router.chat([{"role": "user", "content": "hi"}])
    with pytest.raises(LLMUnavailable, match="switched off"):
        await router.chat([{"role": "user", "content": "hi"}])
    router.state.enable()
    costly, _ = gateway(lambda r: answer("good/model-70b:free", cost=0.0004))
    with pytest.raises(PaidModelError, match="cost"):
        await costly.chat([{"role": "user", "content": "hi"}])


async def test_a_busy_model_falls_back_to_the_next_free_model():
    def handler(request):
        model = httpx.Response(200, content=request.content).json()["model"]
        if model == "good/model-70b:free":
            return httpx.Response(429, json={"error": {"code": 429, "message": "upstream rate limited"}})
        return answer(model)
    router, _ = gateway(handler)
    reply = await router.chat([{"role": "user", "content": "hi"}])
    assert reply.model == "small/model-8b:free" and reply.attempts == ["good/model-70b:free", "small/model-8b:free"]
    assert router.state.cooling("good/model-70b:free")
    assert router.state.stats()["good/model-70b:free"]["rate_limited"] == 1


async def test_the_daily_allowance_stops_calls_until_midnight():
    router, _ = gateway(lambda r: answer("good/model-70b:free"), funded=False)
    for _ in range(FREE_DAILY):
        await router.chat([{"role": "user", "content": "hi"}])
    with pytest.raises(LLMUnavailable, match="allowance is used up"):
        await router.chat([{"role": "user", "content": "hi"}])

    daily = httpx.Response(429, json={"error": {"code": 429, "message": "Rate limit exceeded: free-models-per-day"}})
    hit, _ = gateway(lambda r: daily)
    with pytest.raises(LLMUnavailable, match="allowance is used up"):
        await hit.chat([{"role": "user", "content": "hi"}])
    assert hit.state.exhausted()


async def test_no_key_means_no_calls():
    router, calls = gateway(lambda r: answer("good/model-70b:free"), key="")
    with pytest.raises(LLMUnavailable, match="no OpenRouter key"):
        await router.chat([{"role": "user", "content": "hi"}])
    assert not calls


async def test_status_reports_the_allowance_and_models():
    router, _ = gateway(lambda r: answer("good/model-70b:free"))
    await router.chat([{"role": "user", "content": "hi"}])
    status = await router.status()
    assert status["configured"] and status["daily_limit"] == FUNDED_DAILY and status["used_today"] == 1
    assert status["models"][0] == "good/model-70b:free" and status["is_free_tier"] is False


def test_reply_json_tolerates_a_code_fence():
    from app.llm.openrouter import Reply

    assert Reply('```json\n{"a": 1}\n```', "m").json() == {"a": 1}
