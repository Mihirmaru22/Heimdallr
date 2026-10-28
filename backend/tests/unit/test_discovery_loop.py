"""Discovery that follows companies: a fixed reading order, each company's own proof search, a coverage stop."""

import json

import httpx

from app.discovery.case_studies import PLATEAU, CaseStudiesProvider
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
    noise = [(f"https://blog{i}.example/guidewire-tips", "Guidewire tips") for i in range(30)]
    pages = {u: "<html><head><title>Tips</title></head><body><p>Five Guidewire tips for admins.</p></body></html>"
             for u, _t in noise}
    p = provider(lambda q: noise, pages)
    users = {}
    stop = await p._read_loop(p.client, product_for("Guidewire"), spec().discovery, [u for u, _ in noise], users)
    assert stop.startswith("coverage") and p.read == PLATEAU
    assert sum(e["reason"].startswith("not read: coverage") for e in p.evidence) == 30 - PLATEAU


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
