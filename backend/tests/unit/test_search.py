"""The shared search layer: several engines merged, free allowances respected, a failing engine switched off."""

import json

import httpx
import pytest

from app.discovery.providers import SearxngProvider
from app.search import (
    EVIDENCE,
    GENERAL,
    LOOKUP,
    ExaBackend,
    KeenableBackend,
    LinkupBackend,
    SearchError,
    SearchHub,
    SearxngBackend,
    TavilyBackend,
    Usage,
)
from app.spec.models import ExtractionSpec


def hub(handler, backends, tmp_path):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return SearchHub(client, backends, Usage(tmp_path / "usage.json"))


def answer(request):
    host = request.url.host
    if host == "api.tavily.com":
        assert request.headers["authorization"] == "Bearer t-key"
        assert json.loads(request.content)["search_depth"] == "basic"
        return httpx.Response(200, json={"results": [{"url": "https://www.a.com/", "title": "A", "content": "tav"},
                                                     {"url": "https://t-only.com/"}]})
    if host == "api.linkup.so":
        return httpx.Response(200, json={"results": [
            {"type": "text", "url": "https://a.com", "name": "A", "content": "link"},
            {"type": "image", "url": "https://img.example/x.png", "name": "pic"},
            {"type": "text", "url": "https://l-only.com/", "name": "L", "content": "x" * 900}]})
    if host == "api.exa.ai":
        assert json.loads(request.content)["type"] == "lite"
        return httpx.Response(200, json={"results": [{"url": "https://e-only.com/", "title": "E"}]})
    if host == "api.keenable.ai":
        assert request.url.path == "/v1/search/public" and request.headers["x-keenable-title"]
        return httpx.Response(200, json={"results": [{"url": "https://k-only.com/", "description": "kd"}]})
    return httpx.Response(200, json={"results": [{"url": "https://s-only.com/", "content": "sx"}]})


ALL = lambda: [KeenableBackend(), TavilyBackend("t-key"), LinkupBackend("l-key"),  # noqa: E731
               ExaBackend("e-key"), SearxngBackend("http://searx")]


async def test_engines_are_asked_together_and_merged_one_each_in_turn_without_repeats(tmp_path):
    h = hub(answer, ALL(), tmp_path)
    hits = await h.search("q", kind=GENERAL)
    urls = [x.url for x in hits]
    assert "https://e-only.com/" not in urls  # Exa only answers evidence questions
    assert urls == ["https://k-only.com/", "https://www.a.com/", "https://s-only.com/", "https://t-only.com/",
                    "https://l-only.com/"]  # one from each engine in turn; a.com once; no image result
    assert len({u.split("://")[1].removeprefix("www.").rstrip("/") for u in urls}) == len(urls)  # a.com once
    assert max(len(x.snippet) for x in hits) <= 400


async def test_evidence_questions_add_exa_and_lookups_stay_on_free_engines(tmp_path):
    h = hub(answer, ALL(), tmp_path)
    assert "https://e-only.com/" in [x.url for x in await h.search("q", kind=EVIDENCE)]
    lookup = await h.search("q", kind=LOOKUP)
    assert {x.provider for x in lookup} == {"keenable", "searxng"}
    assert h.calls.get("tavily") == 1 and h.calls.get("linkup") == 1  # only the earlier evidence call


async def test_only_searxng_gives_more_pages(tmp_path):
    h = hub(answer, ALL(), tmp_path)
    assert {x.provider for x in await h.search("q", page=2)} == {"searxng"}


async def test_a_used_up_allowance_switches_that_engine_off_and_the_others_carry_on(tmp_path):
    def handler(request):
        if request.url.host == "api.tavily.com":
            return httpx.Response(432, json={"detail": "limit"})
        return answer(request)

    h = hub(handler, ALL(), tmp_path)
    assert await h.search("q")
    assert "allowance" in h.problems["tavily"]
    await h.search("q")
    assert h.calls["tavily"] == 1  # not asked again


async def test_a_refused_key_switches_the_engine_off(tmp_path):
    h = hub(lambda r: httpx.Response(401), [LinkupBackend("bad")], tmp_path)
    with pytest.raises(SearchError, match="the key was refused"):
        await h.search("q")


async def test_the_monthly_counter_stops_a_capped_engine_before_its_free_allowance_runs_out(tmp_path):
    class Cheap(TavilyBackend):
        monthly_cap = 2

    h = hub(answer, [Cheap("t-key"), SearxngBackend("http://searx")], tmp_path)
    for _ in range(4):
        await h.search("q")
    assert h.calls["tavily"] == 2 and h.calls["searxng"] == 4
    assert json.loads((tmp_path / "usage.json").read_text()).popitem()[1] == {"tavily": 2}
    again = Usage(tmp_path / "usage.json")  # a restart keeps the count
    assert again.used("tavily") == 2


async def test_repeated_failures_switch_an_engine_off_and_all_off_is_an_honest_error(tmp_path):
    def down(request):
        raise httpx.ConnectError("no route")

    h = hub(down, [SearxngBackend("http://searx")], tmp_path)
    for _ in range(4):
        assert await h.search("q") == []
    with pytest.raises(SearchError, match="5 times in a row"):
        await h.search("q")
    with pytest.raises(SearchError, match="unavailable"):
        await h.search("q")


async def test_nothing_configured_says_so(tmp_path):
    with pytest.raises(SearchError, match="not configured"):
        await hub(answer, [], tmp_path).search("q")


def test_the_same_question_is_worded_other_ways_without_changing_the_plain_one():
    spec = ExtractionSpec.model_validate({"entity": "company", "fields": [
        {"name": "company_name", "type": "string", "semantic": "company_name", "required": True}],
        "discovery": {"providers": ["searxng"], "industry": "pharmaceutical", "countries": ["DE", "FR"]}})
    assert SearxngProvider.queries(spec) == ["pharmaceutical companies Germany", "pharmaceutical companies France"]
    shapes = SearxngProvider.shapes(spec)
    assert "largest pharmaceutical companies in Germany" in shapes
    assert "pharmaceutical companies headquartered in France" in shapes
