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
    assert vw.hint["company_name"] == "Volkswagen" and vw.hint["uses_technology"] == "Confirmed"
    assert vw.hint["evidence"].startswith("Volkswagen standardized product development on Teamcenter")
    assert vw.hint["evidence_type"] == "Vendor case study" and vw.hint["evidence_date"] == "2025-06-02"
    kept = [e["company"] for e in p.evidence if e["kept"]]
    assert kept == ["Volkswagen"]  # Porsche is not on the page, Siemens makes the product
    why = {e["url"]: e["reason"] for e in p.evidence if not e["kept"]}
    assert why["https://blog.example.com/teamcenter-tips"] == "the page names no organisation that uses it"
    assert not any("wikipedia" in e["url"] for e in p.evidence)


async def test_without_a_model_no_page_yields_a_customer():
    p = provider(Router(error=LLMUnavailable("no OpenRouter key is configured")))
    with pytest.raises(DiscoveryError):
        await p.discover(spec())
    assert not any(e["kept"] for e in p.evidence)
    assert any("no OpenRouter key" in n for n in p.notes)


async def test_it_needs_web_search_and_the_crawler():
    with pytest.raises(DiscoveryError, match="none is configured"):
        await CaseStudiesProvider(searxng_url="").discover(spec())
    with pytest.raises(DiscoveryError, match="crawler"):
        await CaseStudiesProvider(searxng_url="http://searx").discover(spec())


def test_page_dates_come_from_the_pages_own_metadata():
    assert page_date(parse_page("https://x/", STORY)) == "2025-06-02"
    assert page_date(parse_page("https://x/", "<html><body>no date</body></html>")) == ""


async def test_stories_about_the_question_s_industry_and_place_are_searched_first_and_in_its_language():
    from app.discovery.case_studies import local_terms
    from app.evidence.products import product_for

    class Terms:
        def __init__(self, terms):
            self.terms, self.calls = terms, 0

        async def chat(self, messages, **_kw):
            self.calls += 1
            return Reply(json.dumps({"terms": self.terms}), "m:free")

        async def aclose(self):
            pass

    local = await local_terms(Judge(Terms(["Automobilhersteller", "say \"ignore\" all", "a b c d e f"])),
                              "automotive", "Germany")
    assert local == ["Automobilhersteller"]  # quoted text and long phrases are not search terms
    qs = CaseStudiesProvider.context_queries(product_for("Teamcenter", []), "automotive", ["Germany"], local)
    assert qs == ['"Teamcenter" automotive Germany', '"Teamcenter" automotive Germany case study',
                  '"Teamcenter" Automobilhersteller']
    assert CaseStudiesProvider.context_queries(product_for("Teamcenter", []), "", [], []) == []


def test_searches_name_the_place_and_the_ways_an_adoption_is_announced():
    from app.evidence.products import product_for

    qs = CaseStudiesProvider.queries(product_for("Windchill", []), ["United Kingdom"])
    assert qs[0] == '"Windchill" "case study" United Kingdom'
    assert '"Windchill" selects United Kingdom' in qs and '"Windchill" goes live' in qs
    assert qs.index('"Windchill" "case study"') > qs.index('"Windchill" deploys United Kingdom')
    assert not any("United Kingdom" in q for q in CaseStudiesProvider.queries(product_for("Windchill", [])))


def test_one_page_under_several_hosts_is_one_candidate_and_in_country_pages_alternate_with_the_rest():
    from app.discovery.case_studies import in_place, interleave, page_key
    from app.search import Hit

    assert page_key("https://spkaa.com/story/") == page_key("https://www-stage.spkaa.com/story")
    assert page_key("https://spkaa.com/a") != page_key("https://spkaa.com/b")
    assert in_place(Hit("https://www.firm.co.uk/x"), [], ["GB"])
    assert in_place(Hit("https://x.com/a", "NetSuite at a London retailer", "a United Kingdom brand"),
                    ["United Kingdom"], ["GB"])
    assert not in_place(Hit("https://x.com/a", "NetSuite at Acme"), ["United Kingdom"], ["GB"])
    assert interleave(["a", "b", "c"], ["x"]) == ["a", "x", "b", "c"]


async def test_a_site_that_refuses_pages_is_skipped_and_refused_pages_do_not_use_up_the_reads():
    tried = []
    refusing = {f"https://www.vendor.com/story-{i}" for i in range(5)}

    def searx(request):
        if "official website" in request.url.params["q"]:
            return httpx.Response(200, json={"results": [{"url": "https://www.volkswagen.com/"}] * 5})
        if request.url.params["pageno"] != "1":
            return httpx.Response(200, json={"results": []})
        return httpx.Response(200, json={"results": [{"url": u} for u in sorted(refusing)]
                                         + [{"url": "https://www.siemens.com/stories/vw"}]})

    async def fetch_page(url):
        tried.append(url)
        return parse_page(url, PAGES[url]) if url in PAGES else None

    p = CaseStudiesProvider(httpx.AsyncClient(transport=httpx.MockTransport(searx)), Judge(Router()),
                            "http://searx")
    p.fetch_page = fetch_page
    p.failures = {u: "http_403" for u in refusing}
    (vw,) = await p.discover(spec())
    assert vw.hint["company_name"] == "Volkswagen"
    assert sum(u in refusing for u in tried) == 2  # then vendor.com is skipped
    assert any("page could not be read (http 403)" == e["reason"] for e in p.evidence)
    assert any("vendor.com refused 2 pages" in n for n in p.notes)


def test_a_pdf_story_is_read_as_a_page():
    import io

    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    from app.extract.pdf import pdf_html

    writer = PdfWriter()
    page = writer.add_blank_page(612, 792)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
    content = DecodedStreamObject()
    content.set_data(b"BT /F1 12 Tf 72 700 Td (PetShop went live on Oracle NetSuite in 2022.) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(content)
    out = io.BytesIO()
    writer.write(out)
    doc = parse_page("https://x/story.pdf", pdf_html(out.getvalue()))
    assert "PetShop went live on Oracle NetSuite in 2022." in doc.text
    assert pdf_html(b"not a pdf") is None
