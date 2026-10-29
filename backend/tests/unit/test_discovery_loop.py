"""Discovery over proof pages: a fixed reading order, rules before the model, a country check before reading,
a coverage stop. No company gets a proof search of its own."""

import json

import httpx

from app.discovery.case_studies import MIN_READ, PLATEAU, CaseStudiesProvider
from app.evidence.judge import Judge
from app.evidence.products import product_for
from app.extract.deterministic import parse_page
from app.llm.openrouter import Reply
from app.search import JOB_CACHE, Hit, SearchHub
from app.spec.models import ExtractionSpec


def spec(**discovery):
    return ExtractionSpec.model_validate({"entity": "company", "fields": [
        {"name": "company_name", "type": "string", "semantic": "company_name", "required": True}],
        "discovery": {"providers": ["case_studies"], "technology": "Guidewire", "countries": ["US"], **discovery}})


def story(company):
    return (f"<html><head><title>{company} selects Guidewire</title></head><body><p>{company} has selected "
            "Guidewire ClaimCenter to run its claims.</p></body></html>")


class Reader:
    """Reads a story page: the customer is the company named in its title."""

    async def chat(self, messages, **_kw):
        user = messages[-1]["content"]
        title = user.split("Title: ", 1)[1].split("\n", 1)[0]
        name = title.split(" selects")[0] if " selects" in title else ""
        customers = [{"name": name, "quote": 1, "relationship": "uses"}] if name else []
        publisher = "news" if "Page: https://news." in user else "vendor"  # news proof is Likely, not Confirmed
        return Reply(json.dumps({"publisher": publisher, "customers": customers}), "m:free")

    async def aclose(self):
        pass


def provider(results, pages):
    def searx(request):
        q = request.url.params["q"]
        if request.url.params.get("pageno", "1") != "1":
            return httpx.Response(200, json={"results": []})
        return httpx.Response(200, json={"results": [{"url": u, "title": t} for u, t in results(q)]})

    async def fetch_page(url):
        return parse_page(url, pages[url]) if url in pages else None

    p = CaseStudiesProvider(httpx.AsyncClient(transport=httpx.MockTransport(searx)), Judge(Reader()), "http://searx")
    p.fetch_page = fetch_page
    return p


def test_the_reading_order_comes_from_the_pages_not_the_engines():
    p = CaseStudiesProvider(searxng_url="http://searx")
    product = product_for("Guidewire")
    p.meta = {"https://b.example/x": ("Guidewire customer story", ""), "https://a.example/y": ("Other news", ""),
              "https://c.example/us": ("Guidewire in the US", "")}
    order = sorted(p.meta, key=lambda u: p.rank(u, product, ["US"]))
    assert order == ["https://c.example/us", "https://b.example/x", "https://a.example/y"]


async def test_reading_stops_when_pages_stop_naming_new_companies_and_says_so():
    noise = [(f"https://blog{i}.example/guidewire-tips", "Guidewire tips") for i in range(60)]
    pages = {u: "<html><head><title>Tips</title></head><body><p>Five Guidewire tips for admins.</p></body></html>"
             for u, _t in noise}
    p = provider(lambda q: noise, pages)
    users = {}
    stop = await p._read_loop(p.client, product_for("Guidewire"), spec().discovery, [u for u, _ in noise], users)
    # Never fewer than MIN_READ pages, then a run of PLATEAU empty ones: here both end at MIN_READ.
    assert stop.startswith("coverage") and p.read == max(MIN_READ, PLATEAU)
    assert sum(e["reason"].startswith("not read: coverage") for e in p.evidence) == 60 - max(MIN_READ, PLATEAU)


async def test_only_the_general_searches_are_read_no_company_is_searched_for_on_its_own():
    general = [("https://news.example/acme", "Acme selects Guidewire")]
    asked = []

    def results(q):
        asked.append(q)
        return general

    p = provider(results, {"https://news.example/acme": story("Acme")})
    users = {}
    await p._read_loop(p.client, product_for("Guidewire"), spec().discovery, [u for u, _ in general], users)
    assert "acme" in users and asked == []  # reading a page never starts a search of its own
    assert not hasattr(p, "prove") and not hasattr(p, "targeted")


async def test_a_job_asks_each_search_once():
    calls = []

    class Engine:
        name, kinds, pages, fallback, monthly_cap = "engine", ("general",), 1, False, None

        async def search(self, client, query, page):
            calls.append(query)
            return [Hit(f"https://x.example/{len(calls)}")]

    hub = SearchHub(httpx.AsyncClient(), [Engine()])
    token = JOB_CACHE.set({})
    try:
        first = await hub.search("Guidewire  case study")
        again = await hub.search("guidewire case study")
    finally:
        JOB_CACHE.reset(token)
    assert first == again and len(calls) == 1
    await hub.search("guidewire case study")  # outside a job: asked again, nothing is kept between jobs
    assert len(calls) == 2


async def test_a_page_s_own_sentence_settles_it_and_the_model_reads_a_page_once_unless_unsure():
    from app.evidence.thirdparty import read_page

    class Models:
        def __init__(self, sure, second_says_use=True):
            self.sure, self.second_says_use, self.calls = sure, second_says_use, 0

        async def chat(self, messages, avoid=None, **_kw):
            self.calls += 1
            if avoid is None:
                body = {"publisher": "vendor", "sure": self.sure,
                        "customers": [{"name": "Acme", "quote": 1, "relationship": "uses"}]}
                return Reply(json.dumps(body), "first:free")
            customers = [{"name": "Acme", "quote": 1, "relationship": "uses"}] if self.second_says_use else []
            return Reply(json.dumps({"publisher": "vendor", "customers": customers}), "second:free")

        async def aclose(self):
            pass

    product = product_for("Guidewire")
    plain = "Acme has selected Guidewire ClaimCenter."
    models = Models(sure=True)
    found, _ = await read_page(Judge(models), product, "Acme", [plain], plain, "https://vendor.example/acme")
    assert found[0].customer == "Acme" and found[0].agreement == "rules" and models.calls == 0
    unclear = "Guidewire ClaimCenter powers the claims desk at Acme."  # no adoption verb joins them
    models = Models(sure=True)
    found, _ = await read_page(Judge(models), product, "Acme", [unclear], unclear, "u")
    assert found[0].agreement == "single" and models.calls == 1  # sure: one reading
    models = Models(sure=False)
    found, _ = await read_page(Judge(models), product, "Acme", [unclear], unclear, "u")
    assert found[0].agreement == "agree" and found[0].second_by == "model:second:free" and models.calls == 2
    found, _ = await read_page(Judge(Models(sure=False, second_says_use=False)), product, "Acme", [unclear],
                               unclear, "u")
    assert found[0].agreement == "disagree"

    # A rule sentence on the maker's page is first-hand (Confirmed); on someone else's page it is Likely.
    for url, verdict in (("https://guidewire.com/acme", "Confirmed"), ("https://blog.example/acme", "Likely")):
        p = provider(lambda q: [], {url: story("Acme")})
        rows, _ok = await p._read_one(url, product)
        assert rows[0]["verdict"] == verdict and rows[0]["judged_by"].startswith("rules")


async def test_a_page_about_a_company_known_to_be_elsewhere_is_not_given_to_the_model():
    from app.discovery.entities import Resolution

    class Registry:
        async def resolve(self, company, website=""):
            return Resolution(country="AU", by="registry: wikidata", detail=f"{company} (wikidata Q1)")

    class Counting(Reader):
        calls = 0

        async def chat(self, messages, **kw):
            Counting.calls += 1
            return await super().chat(messages, **kw)

    unclear = ("<html><head><title>Acme on Guidewire</title></head><body><p>Guidewire ClaimCenter powers the "
               "claims desk at Acme.</p></body></html>")
    pages = {"https://news.example/acme": story("Acme"), "https://vendor.example/acme-on-guidewire": unclear}
    p = provider(lambda q: [], pages)
    p.judge = Judge(Counting())
    p.resolver = Registry()
    p.meta = {"https://news.example/acme": ("Acme selects Guidewire", ""),
              "https://vendor.example/acme-on-guidewire": ("Acme on Guidewire", "")}
    p.countries = ["US"]
    users = {}
    await p._read_loop(p.client, product_for("Guidewire"), spec().discovery,
                       ["https://news.example/acme", "https://vendor.example/acme-on-guidewire"], users)
    # The first page's own sentence named Acme (no model); the registry places it in AU, so the second page, about
    # Acme, is not read by the model.
    assert "acme" in users and Counting.calls == 0
    assert any(f["kind"] == "country" and f["value"] == "AU" for f in p.facts)
    why = {e["url"]: e["reason"] for e in p.evidence if not e["kept"]}
    assert why["https://vendor.example/acme-on-guidewire"].startswith("not read: Acme is in AU")
    # A company whose country is unknown is still read.
    p = provider(lambda q: [], {"https://vendor.example/acme-on-guidewire": unclear})
    p.judge, p.countries = Judge(Counting()), ["US"]
    await p._read_one("https://vendor.example/acme-on-guidewire", product_for("Guidewire"))
    assert Counting.calls == 1
