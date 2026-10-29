"""Fixes for the losses measured on 2026-10-26 (backend/var/diagnosis-2026-10-26.md): each test names the loss."""

import json

import httpx

from app.discovery.case_studies import CaseStudiesProvider, adoption_queries, candidate_key
from app.discovery.relevance import pages_country
from app.discovery.sitecheck import SiteChecker
from app.discovery.websites import WebsiteFinder
from app.evidence.judge import Judge, makes_product, rule_relationship
from app.evidence.products import product_for
from app.evidence.quotes import find_mentions, verify_quote
from app.evidence.thirdparty import read_page
from app.extract.deterministic import parse_page
from app.llm.openrouter import LLMUnavailable, Reply
from app.spec.interpret import interpret, technology_in
from app.spec.models import ExtractionSpec
from app.spec.planner import plan_spec

# --- planning without a model keeps the technology (P1) ---------------------------------------


class NoModel:
    def __init__(self, error="no OpenRouter key is configured"):
        self.error, self.calls = error, 0

    async def chat(self, *_a, **_kw):
        self.calls += 1
        raise LLMUnavailable(self.error)

    async def aclose(self):
        pass


def test_the_rules_read_the_product_from_the_question_s_grammar():
    assert technology_in("List companies in the United States that use PTC Windchill, with website") == \
        "PTC Windchill"
    assert technology_in("pharmaceutical companies in India that use Veeva Vault") == "Veeva Vault"
    assert technology_in("list out the companies who are using Siemens Teamcenter in us") == "Siemens Teamcenter"
    assert technology_in("US companies that use SAP S/4HANA, with website and contact info") == "SAP S/4HANA"
    assert technology_in("Find up to 30 pharmaceutical companies in Germany with website and phone") is None


def test_filler_words_and_country_names_are_not_industries():
    assert interpret("list out the companies who are using X in us").discovery.industry is None
    d = interpret("US companies that use SAP S/4HANA").discovery
    assert d.industry is None and d.countries == ["US"]
    assert interpret("pharmaceutical companies in India").discovery.industry == "pharmaceutical"


async def test_a_technology_question_read_by_the_rules_keeps_its_technology_and_proof_columns():
    spec, by, notes = await plan_spec("List pharmaceutical companies in India that use Veeva Vault, with company "
                                      "name, website and the link proving they use it", [], NoModel())
    d = spec.discovery
    assert by == "rules" and d.technology == "Veeva Vault" and d.industry == "pharmaceutical"
    assert d.countries == ["IN"] and d.providers[:2] == ["case_studies", "news"]
    assert "uses_technology" in [f.name for f in spec.fields] and "evidence_url" in [f.name for f in spec.fields]
    assert any("Veeva Vault" in n for n in notes)


async def test_busy_free_models_are_asked_again_before_the_rules_take_over():
    class BusyThenFine:
        def __init__(self):
            self.calls = 0

        async def chat(self, *_a, **_kw):
            self.calls += 1
            if self.calls == 1:
                raise LLMUnavailable("no free model answered: a: rate limited")
            return Reply(json.dumps({"rows": "companies", "technology": "Teamcenter"}), "m:free")

        async def aclose(self):
            pass

    router = BusyThenFine()
    spec, by, _notes = await plan_spec("who uses teamcenter", [], router, retry_waits=(0,))
    assert by == "model:m:free" and router.calls == 2 and spec.discovery.technology == "Teamcenter"
    never = NoModel()  # a missing key is not busy: the rules at once
    _spec, by, _notes = await plan_spec("who uses teamcenter", [], never, retry_waits=(0, 0))
    assert by == "rules" and never.calls == 1


# --- quotes stay inside the page block of the mention (P6) ------------------------------------

MENU_PAGE = ("<html><head><title>Komatsu America Selects Windchill</title></head><body>"
             "<nav><a>Careers</a><a>Browse All</a><a>Top Workplaces</a><a>Design</a></nav>"
             "<h1>Komatsu America Selects PTC's Windchill and Arbortext Software</h1>"
             "<p>PTC today announced that Komatsu America Corp. has chosen Windchill for its product data.</p>"
             "<p>With both <a>Windchill</a> and <a>Creo</a>, the team works from one source.</p></body></html>")


def test_a_quote_never_reaches_back_into_the_menu():
    doc = parse_page("https://news.example.com/komatsu", MENU_PAGE)
    quotes = find_mentions(doc.text, product_for("Windchill"), limit=5)
    assert quotes and all("Careers" not in q and "Top Workplaces" not in q for q in quotes)
    assert any(q.startswith("PTC today announced that Komatsu America") for q in quotes)
    assert any(q.startswith("With both") for q in quotes)  # a sentence split by links stays whole
    assert all(verify_quote(q, doc.text) for q in quotes)


def test_filings_without_line_breaks_are_quoted_as_before():
    text = "Our results grew. We completed our migration to SAP S/4HANA in 2024. Costs fell."
    assert find_mentions(text, product_for("SAP S/4HANA")) == ["We completed our migration to SAP S/4HANA in 2024."]


async def test_an_unreadable_proof_answer_is_asked_of_another_model_once_and_a_plain_sentence_needs_no_model():
    class BrokenThenFine:
        def __init__(self):
            self.avoided, self.steps = [], []

        async def chat(self, messages, avoid=None, step=None, **_kw):
            self.avoided.append(avoid)
            self.steps.append(step)
            if avoid is None:
                return Reply("Sure, here is what I found:", "broken:free")
            return Reply(json.dumps({"publisher": "news", "customers": [
                {"name": "Komatsu America", "quote": 1, "relationship": "uses"}]}), "good:free")

        async def aclose(self):
            pass

    router = BrokenThenFine()
    hedged = "PTC said Komatsu America Corp. may move to Windchill next year."
    found, _why = await read_page(Judge(router), product_for("Windchill"), "Komatsu", [hedged], hedged, "u")
    assert [f.customer for f in found] == ["Komatsu America"]
    assert router.avoided == [None, "broken:free"] and router.steps == ["proof_read", "reask"]
    plain = "PTC today announced that Komatsu America Corp. has chosen Windchill."
    found, _why = await read_page(Judge(router), product_for("Windchill"), "Komatsu", [plain], plain, "u")
    assert [f.customer for f in found] == ["Komatsu America Corp."] and found[0].agreement == "rules"
    assert len(router.avoided) == 2  # the sentence says it: no model call


def test_the_maker_is_recognised_from_the_product_s_name():
    assert makes_product("PTC Inc.", product_for("PTC Windchill"))
    assert makes_product("Oracle Corporation", product_for("Oracle NetSuite"))
    assert makes_product("Workday, Inc.", product_for("Workday HCM"))
    assert not makes_product("Boston Scientific", product_for("PTC Windchill"))
    assert rule_relationship("PTC Inc", product_for("PTC Windchill"), "")[0] == "vendor"


# --- website lookup (P3) ----------------------------------------------------------------------


def finder(results, pages):
    def search(request):
        return httpx.Response(200, json={"results": [{"url": u} for u in results(request.url.params["q"])]})

    async def fetch_text(url):
        return pages.get(url)

    return WebsiteFinder(httpx.AsyncClient(transport=httpx.MockTransport(search)), "http://searx", fetch_text)


async def test_a_company_s_country_sites_agree_with_each_other():
    urls = ["https://www.enersys.com/", "https://www.enersys.com.pl/", "https://ensercorp.com/",
            "https://www.enersys.com/en/", "https://enersyscorp.com/"]
    site, how = await finder(lambda q: urls, {"https://www.enersys.com/": "EnerSys stored energy"}).find("EnerSys")
    assert site == "https://www.enersys.com/" and "homepage names it" in how


async def test_a_homepage_is_tried_at_its_https_and_www_addresses():
    urls = ["http://sram.com/"] * 5
    site, _how = await finder(lambda q: urls, {"https://www.sram.com/": "SRAM bicycle components"}).find("SRAM")
    assert site == "https://www.sram.com/"


async def test_a_company_with_proof_keeps_an_agreed_website_whose_homepage_cannot_be_read():
    urls = ["https://www.nvidia.com/"] * 5
    assert (await finder(lambda q: urls, {}).find("NVIDIA"))[0] == ""
    site, how = await finder(lambda q: urls, {}).find("NVIDIA", unverified_ok=True)
    assert site == "https://www.nvidia.com/" and "not verified" in how


async def test_the_place_settles_a_name_another_company_shares():
    def results(q):
        return ["https://grs-supplies.co.uk/"] * 5 if "United Kingdom" in q else ["https://www.grs.com/"] * 5
    pages = {"https://www.grs.com/": "GRS Group global recycling", "https://grs-supplies.co.uk/":
             "GRS Building Supplies Ltd, builders merchant"}
    site, _how = await finder(results, pages).find("GRS Building Supplies", context="United Kingdom")
    assert site == "https://grs-supplies.co.uk/"


# --- country check (P5) -----------------------------------------------------------------------


def _page(url, body):
    return parse_page(url, f"<html><body>{body}</body></html>")


def test_numbers_written_the_national_way_settle_nothing():
    # A US number is also a valid Indian national number: reading them as the requested country passed a US
    # company as Indian (run 2, 2026-10-28). Where a company is comes from registries and the proof instead.
    home = _page("https://www.example-med.com/", "Welcome")
    contact = _page("https://www.example-med.com/contact", "Call us on (508) 683-4000 or 1-888-272-1001.")
    assert pages_country([home, contact]) == (None, "")


# --- reading order and cap (P4, P7) -----------------------------------------------------------


def test_copies_of_one_page_share_a_key():
    a = candidate_key("https://www.spkaa.com/case-study/strattec/")
    assert a == candidate_key("https://www-stage.spkaa.com/case-study/strattec?utm=x")
    assert a != candidate_key("https://www.spkaa.com/case-study/sram")


async def test_a_refusing_site_is_passed_over_and_unread_pages_stay_visible():
    pages = {f"https://refuser.example/story-{i}": None for i in range(5)}
    story = ("<html><head><title>Acme picks Teamcenter</title></head><body><p>Acme Corp standardized on "
             "Teamcenter.</p></body></html>")

    def searx(request):
        if "official website" in request.url.params["q"]:
            return httpx.Response(200, json={"results": [{"url": "https://www.acme.com/"}] * 5})
        if request.url.params["pageno"] != "1":
            return httpx.Response(200, json={"results": []})
        return httpx.Response(200, json={"results": [{"url": u} for u in [*pages, "https://partner.example/acme",
                                                                           "https://www.partner.example/acme/"]]})

    async def fetch_page(url):
        if url == "https://partner.example/acme":
            return parse_page(url, story)
        if url == "https://www.acme.com/":
            return parse_page(url, "<html><body>Acme Corp makes things</body></html>")
        return None

    class Router:
        async def chat(self, messages, **_kw):
            return Reply(json.dumps({"publisher": "partner", "customers": [
                {"name": "Acme Corp", "quote": 1, "relationship": "uses"}]}), "m:free")

        async def aclose(self):
            pass

    p = CaseStudiesProvider(httpx.AsyncClient(transport=httpx.MockTransport(searx)), Judge(Router()), "http://searx")
    p.fetch_page = fetch_page
    spec = ExtractionSpec.model_validate({"entity": "company", "fields": [
        {"name": "company_name", "type": "string", "semantic": "company_name", "required": True}],
        "discovery": {"providers": ["case_studies"], "technology": "Teamcenter"}})
    (acme,) = await p.discover(spec)
    assert acme.hint["company_name"] == "Acme Corp"
    reasons = [e["reason"] for e in p.evidence if e["url"].startswith("https://refuser.example")]
    assert sum(r.startswith("page could not be read") for r in reasons) == 2  # then the site is passed over
    assert sum("refused or gave no text" in r for r in reasons) == 3
    assert not any(e["url"] == "https://www.partner.example/acme/" for e in p.evidence)  # a copy, not read


async def test_adoption_searches_are_fixed_templates_so_the_same_question_asks_the_same_searches():
    first = adoption_queries("Windchill", "United States", "US")
    assert first == adoption_queries("Windchill", "United States", "US")  # every run the same
    assert first == ['"Windchill" United States implemented', '"Windchill" United States "went live"',
                     '"Windchill" United States selects', '"Windchill" United States customer']
    assert all('"Windchill"' in q for q in adoption_queries("Windchill", "Japan", "JP"))
    assert '"Windchill" 導入事例' in adoption_queries("Windchill", "Japan", "JP")  # the place's own words
    assert adoption_queries("Windchill", "", "") == []
    q = CaseStudiesProvider.queries(product_for("Teamcenter"), "Germany")
    assert q[0] == '"Teamcenter" "case study" Germany'


# --- site check survives a busy moment (P9) ---------------------------------------------------


async def test_a_busy_moment_does_not_switch_the_site_check_off_for_the_run():
    class BusyOnce:
        def __init__(self):
            self.calls = 0

        async def chat(self, *_a, **_kw):
            self.calls += 1
            if self.calls == 1:
                raise LLMUnavailable("no free model answered: a: rate limited")
            return Reply(json.dumps({"kind": "news_or_blog", "in_industry": False, "reason": "a news site"}),
                         "m:free")

        async def aclose(self):
            pass

    spec = ExtractionSpec.model_validate({"entity": "company", "fields": [
        {"name": "company_name", "type": "string", "semantic": "company_name", "required": True}],
        "discovery": {"providers": ["searxng"], "industry": "pharmaceutical"}})
    checker = SiteChecker(BusyOnce(), wait=0)
    reason, by = await checker.check(_page("https://pharma-news.example/", "Pharma news every day"), spec)
    assert reason and "news or blog" in reason and by == "model:m:free" and checker.unavailable is None
    always_busy = SiteChecker(NoModel("no free model answered: a: rate limited"), wait=0)
    assert (await always_busy.check(_page("https://x.example/", "pharma"), spec))[1].startswith("unchecked")
    assert always_busy.unavailable is None  # the next site is asked again
