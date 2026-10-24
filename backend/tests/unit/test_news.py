"""News: organisations a news article shows using a product, found in GDELT and read like a case study."""

import json
from datetime import UTC, datetime

import httpx

from app.discovery.news import NewsProvider, gdelt_query, seen_date
from app.evidence.judge import Judge
from app.evidence.products import product_for
from app.extract.deterministic import parse_page
from app.llm.openrouter import Reply
from app.spec.models import ExtractionSpec

ARTICLE = ("<html><head><title>Ford rolls out Teamcenter</title></head><body><p>Ford rolled out Teamcenter "
           "to its engineering teams in Dearborn this spring, the carmaker said.</p></body></html>")
PAGES = {
    "https://www.autonews.com/ford-teamcenter": ARTICLE,
    "https://www.ford.com/": "<html><head><title>Ford Motor Company</title></head><body><p>Ford builds cars, "
                             "trucks and vans for drivers around the world.</p></body></html>",
}


def spec():
    return ExtractionSpec.model_validate({"entity": "company", "fields": [
        {"name": "company_name", "type": "string", "semantic": "company_name", "required": True}],
        "discovery": {"providers": ["news"], "technology": "Teamcenter", "evidence_years": 1}})


class Router:
    async def chat(self, messages, **_kw):
        if "Ford rolled out" in messages[-1]["content"]:
            return Reply(json.dumps({"publisher": "news", "customers": [
                {"name": "Ford", "quote": 1, "relationship": "rolling_out"}]}), "m:free")
        return Reply(json.dumps({"publisher": "other", "customers": []}), "m:free")

    async def aclose(self):
        pass


def test_the_query_quotes_each_name_and_brackets_alternatives():
    assert gdelt_query(product_for("Hooli Mail", [])) == '"Hooli Mail"'
    q = gdelt_query(product_for("SAP S/4HANA", ["S4HANA"]))
    assert q.startswith("(") and ' OR ' in q and '"S4HANA"' in q
    assert seen_date("20250602T101500Z") == "2025-06-02" and seen_date("") == ""


async def test_windows_of_three_months_reach_back_and_articles_are_read_like_case_studies():
    windows = []

    def handler(request):
        if request.url.host == "gdelt.test":
            windows.append((request.url.params["startdatetime"], request.url.params["enddatetime"]))
            if len(windows) == 2:
                return httpx.Response(200, text="Please limit requests to one every 5 seconds")
            if len(windows) > 2:
                return httpx.Response(200, json={})
            article = {"url": "https://www.autonews.com/ford-teamcenter", "title": "Ford rolls out Teamcenter",
                       "seendate": "20260501T080000Z"}
            copy = {**article, "url": "https://www.other-paper.com/ford", "title": "FORD rolls out  Teamcenter"}
            return httpx.Response(200, json={"articles": [article, copy]})
        if "official website" in request.url.params["q"]:
            return httpx.Response(200, json={"results": [{"url": "https://www.ford.com/"}] * 5})
        return httpx.Response(200, json={"results": []})

    async def fetch_page(url):
        return parse_page(url, PAGES[url]) if url in PAGES else None

    p = NewsProvider(httpx.AsyncClient(transport=httpx.MockTransport(handler)), Judge(Router()), "http://searx",
                     gdelt_url="http://gdelt.test/api")
    p.now = lambda: datetime(2026, 10, 1, tzinfo=UTC)
    p.fetch_page = fetch_page
    (ford,) = await p.discover(spec())
    assert ford.method == "news" and ford.url == "https://www.ford.com/"
    assert ford.hint["company_name"] == "Ford" and ford.hint["evidence_type"] == "News article"
    assert ford.hint["evidence_date"] == "2026-05-01"  # the page has none: GDELT's date is used
    assert windows[0] == ("20260703000000", "20261001000000") and windows[1][1] == windows[0][0]
    assert windows[-1][0] == "20251001000000"  # one year, no further
    assert len(p.evidence) == 1  # the syndicated copy was not read again
    assert any("GDELT refused one search window" in n for n in p.notes)
