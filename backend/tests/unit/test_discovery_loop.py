"""Discovery that follows companies: a fixed reading order, each company's own proof search, a coverage stop."""

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
    p.targeted_urls = {"https://d.example/z"}
    order = sorted(p.meta.keys() | {"https://d.example/z"}, key=lambda u: p.rank(u, product, ["US"]))
    assert order == ["https://d.example/z", "https://c.example/us", "https://b.example/x", "https://a.example/y"]


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


async def test_a_named_company_gets_its_own_proof_search_and_those_pages_are_read_first():
    general = [("https://news.example/acme", "Acme selects Guidewire")]
    own = [("https://vendor.example/acme-goes-live", "Acme goes live on Guidewire"),
           ("https://vendor.example/other", "Someone else on Guidewire")]
    pages = {"https://news.example/acme": story("Acme"), "https://vendor.example/acme-goes-live": story("Acme")}
    p = provider(lambda q: own if q.startswith('"Acme"') else general, pages)
    users = {}
    await p._read_loop(p.client, product_for("Guidewire"), spec().discovery, [u for u, _ in general], users)
    assert "acme" in users
    assert "https://vendor.example/acme-goes-live" in p.targeted_urls
    assert "https://vendor.example/other" not in p.targeted_urls  # its title does not name Acme
    assert p.asked == {"acme"}


async def test_listed_companies_are_proven_by_their_own_search_and_only_about_themselves():
    own = {'"Farmers Insurance"': [("https://vendor.example/farmers-insurance-claimcenter",
                                    "Farmers Insurance selects Guidewire")],
           '"Mercury"': [("https://vendor.example/mercury", "Mercury selects Guidewire")]}
    pages = {"https://vendor.example/farmers-insurance-claimcenter": story("Farmers Insurance"),
             "https://vendor.example/mercury": story("Acme Mutual")}  # the page is about someone else

    def results(q):
        return next((v for k, v in own.items() if q.startswith(k)), [])

    p = provider(results, pages)
    proven = await p.prove(spec(), [("Farmers Insurance", "https://www.farmers.com/"),
                                    ("Mercury", "https://www.mercuryinsurance.com/")])
    assert list(proven) == ["Farmers Insurance"]
    assert proven["Farmers Insurance"]["website"] == "https://www.farmers.com/"
    assert proven["Farmers Insurance"]["verdict"] in ("Confirmed", "Likely")


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


async def test_a_use_needs_two_readings_to_be_confirmed_and_disagreement_leaves_a_mention():
    from app.evidence.thirdparty import read_page

    class Models:
        def __init__(self, second_says_use):
            self.second_says_use, self.calls = second_says_use, 0

        async def chat(self, messages, avoid=None, **_kw):
            self.calls += 1
            if avoid is None:
                body = {"publisher": "vendor", "customers": [{"name": "Acme", "quote": 1, "relationship": "uses"}]}
                return Reply(json.dumps(body), "first:free")
            customers = [{"name": "Acme", "quote": 1, "relationship": "uses"}] if self.second_says_use else []
            return Reply(json.dumps({"publisher": "vendor", "customers": customers}), "second:free")

        async def aclose(self):
            pass

    sentence = "Acme has selected Guidewire ClaimCenter."
    found, _ = await read_page(Judge(Models(True)), product_for("Guidewire"), "Acme", [sentence], sentence, "u")
    assert found[0].agreement == "agree" and found[0].second_by == "model:second:free"
    found, _ = await read_page(Judge(Models(False)), product_for("Guidewire"), "Acme", [sentence], sentence, "u")
    assert found[0].agreement == "disagree"

    pages = {"https://vendor.example/acme": story("Acme")}
    for second, verdict in ((True, "Confirmed"), (False, "Mentioned")):
        p = provider(lambda q: [], pages)
        p.judge = Judge(Models(second))
        rows, _ok = await p._read_one("https://vendor.example/acme", product_for("Guidewire"))
        assert rows[0]["verdict"] == verdict


async def test_a_company_the_evidence_puts_elsewhere_gets_no_proof_search_of_its_own():
    from app.discovery.entities import Resolution

    class Registry:
        async def resolve(self, company, website=""):
            return Resolution(country="AU", by="registry: wikidata", detail=f"{company} (wikidata Q1)")

    general = [("https://news.example/acme", "Acme selects Guidewire")]
    p = provider(lambda q: [("https://vendor.example/acme-2", "Acme on Guidewire")] if q.startswith('"Acme"')
                 else general, {"https://news.example/acme": story("Acme")})
    p.resolver = Registry()
    users = {}
    await p._read_loop(p.client, product_for("Guidewire"), spec().discovery, [u for u, _ in general], users)
    assert "acme" in users and p.asked == set()  # placed in AU: a US question does not chase it
    assert any(f["kind"] == "country" and f["value"] == "AU" for f in p.facts)


async def test_a_company_s_other_pages_are_not_read_once_it_has_proof():
    general = [("https://news.example/acme", "Acme selects Guidewire")]
    own = [(f"https://vendor.example/acme-{i}", "Acme selects Guidewire") for i in range(3)]
    pages = {u: story("Acme") for u, _ in general + own}
    p = provider(lambda q: own if q.startswith('"Acme"') else general, pages)
    users = {}
    await p._read_loop(p.client, product_for("Guidewire"), spec(countries=[]).discovery,
                       [u for u, _ in general], users)
    assert p.read == 1  # the news page; Acme then had Likely proof, so its own pages were not needed
    assert sum("already has proof" in e["reason"] for e in p.evidence) == 3
