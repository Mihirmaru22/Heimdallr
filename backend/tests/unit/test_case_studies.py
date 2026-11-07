"""Case studies: organisations a vendor, partner or news page shows using a product, never guessed."""

import json

import httpx
import pytest

from app.discovery.case_studies import CaseStudiesProvider, page_date
from app.discovery.providers import DiscoveryError
from app.evidence.judge import Judge
from app.extract.deterministic import parse_page
from app.llm.openrouter import LLMUnavailable, Reply
from app.spec.models import ExtractionSpec

STORY = ("<html><head><title>Volkswagen standardizes on Teamcenter | Siemens</title>"
         '<meta property="article:published_time" content="2025-06-02T10:00:00Z"></head><body>'
         "<p>Volkswagen standardized product development on Teamcenter across 40 plants. "
         "Partners such as Acme Consulting helped. Siemens makes Teamcenter.</p></body></html>")
PAGES = {
    "https://www.siemens.com/stories/vw": STORY,
    "https://blog.example.com/teamcenter-tips": "<html><head><title>Tips</title></head><body><p>Five "
        "Teamcenter tips for admins who like long weekends and fast searches.</p></body></html>",
    "https://www.volkswagen.com/": "<html><head><title>Volkswagen</title></head><body><p>Welcome to the "
                                       "Volkswagen group, makers of cars and vans for everyone.</p></body></html>",
}


def spec(**discovery):
    return ExtractionSpec.model_validate({"entity": "company", "fields": [
        {"name": "company_name", "type": "string", "semantic": "company_name", "required": True}],
        "discovery": {"providers": ["case_studies"], "technology": "Teamcenter", **discovery}})


class Router:
    def __init__(self, error=None):
        self.error, self.calls = error, 0

    async def chat(self, messages, **_kw):
        self.calls += 1
        if self.error:
            raise self.error
        user = messages[-1]["content"]
        if "Volkswagen" in user:
            customers = [{"name": "Volkswagen", "quote": 1, "relationship": "uses"},
                         {"name": "Porsche", "quote": 1, "relationship": "uses"},  # not on the page
                         {"name": "Siemens", "quote": 1, "relationship": "uses"}]  # the maker
            return Reply(json.dumps({"publisher": "vendor", "customers": customers}), "m:free")
        return Reply(json.dumps({"publisher": "other", "customers": []}), "m:free")

    async def aclose(self):
        pass


def provider(router):
    def searx(request):
        if "official website" in request.url.params["q"]:
            return httpx.Response(200, json={"results": [{"url": "https://www.volkswagen.com/"}] * 5})
        if request.url.params["pageno"] != "1":
            return httpx.Response(200, json={"results": []})
        return httpx.Response(200, json={"results": [{"url": u} for u in PAGES if "volkswagen" not in u]
                                         + [{"url": "https://en.wikipedia.org/wiki/Teamcenter"}]})

    async def fetch_page(url):
        return parse_page(url, PAGES[url]) if url in PAGES else None

    p = CaseStudiesProvider(httpx.AsyncClient(transport=httpx.MockTransport(searx)), Judge(router), "http://searx")
    p.fetch_page = fetch_page
    return p


async def test_a_vendor_story_names_its_customer_whose_website_is_then_found():
    p = provider(Router())
    (vw,) = await p.discover(spec())
    assert vw.url == "https://www.volkswagen.com/" and vw.method == "case_studies"
    # The maker's own case study, recent, saying it outright: first-hand, so Confirmed.
    assert vw.hint["company_name"] == "Volkswagen" and vw.hint["uses_technology"] == "Confirmed"
    # The title says it in so many words ("Volkswagen standardizes on Teamcenter"): settled by rule, quoted.
    assert vw.hint["evidence"].startswith("Volkswagen standardizes on Teamcenter")
    assert vw.hint["evidence_type"] == "Vendor case study" and vw.hint["evidence_date"] == "2025-06-02"
    kept = [e["company"] for e in p.evidence if e["kept"]]
    assert kept == ["Volkswagen"]  # Porsche is not on the page, Siemens makes the product
    why = {e["url"]: e["reason"] for e in p.evidence if not e["kept"]}
    # Nobody but the product is named on the tips page: no model is asked about it.
    assert why["https://blog.example.com/teamcenter-tips"].startswith("the page names no organisation but")
    assert not any("wikipedia" in e["url"] for e in p.evidence)


async def test_without_a_model_only_a_page_s_own_words_yield_a_customer():
    router = Router(error=LLMUnavailable("no OpenRouter key is configured"))
    p = provider(router)
    (vw,) = await p.discover(spec())  # the story's title says it outright: no model needed
    assert vw.hint["company_name"] == "Volkswagen" and [e["company"] for e in p.evidence if e["kept"]] == ["Volkswagen"]
    assert router.calls == 0  # the tips page names nobody, so it was not given to the (missing) model either


async def test_it_needs_web_search_and_the_crawler():
    with pytest.raises(DiscoveryError, match="none is configured"):
        await CaseStudiesProvider(searxng_url="").discover(spec())
    with pytest.raises(DiscoveryError, match="crawler"):
        await CaseStudiesProvider(searxng_url="http://searx").discover(spec())


def test_page_dates_come_from_the_pages_own_metadata():
    assert page_date(parse_page("https://x/", STORY)) == "2025-06-02"
    assert page_date(parse_page("https://x/", "<html><body>no date</body></html>")) == ""


async def test_stories_about_the_question_s_industry_and_place_are_searched_first_and_in_its_language():
    from app.evidence.products import product_for

    p = CaseStudiesProvider(searxng_url="http://searx", judge=Judge(Router(error=AssertionError("no model"))))
    spec_de = spec(industry="automotive", countries=["DE"]).discovery
    qs = await p._context(product_for("Teamcenter", []), spec_de)
    # The question's industry and place first, then the place's own words for an adoption: no model writes them.
    assert qs[:2] == ['"Teamcenter" automotive Germany', '"Teamcenter" automotive Germany case study']
    assert '"Teamcenter" Germany implemented' in qs and '"Teamcenter" Fallstudie' in qs
    assert any(n.startswith("case_studies: searches:") for n in p.notes)
    assert CaseStudiesProvider.context_queries(product_for("Teamcenter", []), "", [], []) == []
