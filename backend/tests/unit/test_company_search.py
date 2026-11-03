"""Company search: each listed company in the asked country, searched by name for proof, bounded."""

import json

import httpx

from app.discovery import company_search
from app.discovery.company_search import CompanySearch, about, candidates
from app.discovery.providers import DiscoveryResult
from app.evidence.judge import Judge
from app.extract.deterministic import parse_page
from app.llm.openrouter import Reply
from app.spec.models import ExtractionSpec

STORY = ("<html><head><title>Acme Foods goes live on NetSuite</title></head><body>"
         "<p>Acme Foods went live on NetSuite in March, replacing three older systems.</p></body></html>")
OTHER = ("<html><head><title>Beta Retail goes live on NetSuite</title></head><body>"
         "<p>Beta Retail went live on NetSuite last spring. Acme Foods NetSuite partner day.</p></body></html>")
PAGES = {"https://partner.example.com/stories/acme-foods-netsuite": STORY,
         "https://news.example.org/beta-retail-netsuite": OTHER}


def spec(**discovery):
    return ExtractionSpec.model_validate({"entity": "company", "fields": [
        {"name": "company_name", "type": "string", "semantic": "company_name", "required": True}],
        "discovery": {"providers": ["case_studies"], "technology": "NetSuite", "countries": ["GB"],
                      "industry": "food", **discovery}})


def listed(name, country="United Kingdom", method="wikidata", **hint):
    site = name.lower().replace(" ", "")
    return DiscoveryResult(f"https://www.{site}.co.uk/", method,
                           {"company_name": name, "country": country, **hint}, referrer="wd")


class Router:
    calls = 0

    async def chat(self, messages, **_kw):
        self.calls += 1
        return Reply(json.dumps({"publisher": "other", "customers": []}), "m:free")

    async def aclose(self):
        pass


def searcher(results_for):
    asked = []

    def searx(request):
        q = request.url.params["q"]
        asked.append(q)
        return httpx.Response(200, json={"results": results_for(q)})

    async def fetch_page(url):
        return parse_page(url, PAGES[url]) if url in PAGES else None

    s = CompanySearch(httpx.AsyncClient(transport=httpx.MockTransport(searx)), Judge(Router()), "http://searx")
    s.fetch_page = fetch_page
    return s, asked


def test_only_companies_in_the_asked_country_without_proof_are_searched_once_each():
    groups = [[listed("Acme Foods"), listed("Gamma GmbH", "Germany"), listed("Nowhere Ltd", "")],
              [listed("Acme Foods", "GB", method="gleif"), listed("Delta Ltd", "GB", uses_technology="Likely"),
               DiscoveryResult("https://seed.example/", "seed", {"company_name": "Seed", "country": "GB"})],
              [listed("Epsilon plc", "GB", method="case_studies", uses_technology="Mentioned")]]
    names = [r.hint["company_name"] for r in candidates(groups, ["GB"])]
    # Elsewhere or unknown: not chased. Already Likely: nothing to add. A mention is not proof, so it is searched.
    assert names == ["Acme Foods", "Epsilon plc"]


def test_the_list_is_capped_before_the_pass_starts(monkeypatch):
    monkeypatch.setattr(company_search, "MAX_COMPANIES", 3)
    assert len(candidates([[listed(f"Firm {i}") for i in range(10)]], ["GB"])) == 3


async def test_a_page_naming_the_company_and_the_product_proves_it_and_keeps_the_listing_s_facts():
    def results(q):
        return [{"url": "https://www.linkedin.com/posts/acme-foods-netsuite", "title": "Acme Foods NetSuite"},
                {"url": "https://shop.example.com/acme-foods", "title": "Acme Foods shop"},  # no product named
                {"url": "https://partner.example.com/stories/acme-foods-netsuite",
                 "title": "Acme Foods goes live on NetSuite"}] if "Acme" in q else []

    s, asked = searcher(results)
    (acme,) = await s.prove(spec(), [listed("Acme Foods", industry="food")])
    assert asked == ['"Acme Foods" "NetSuite"']
    assert acme.method == "company_search" and acme.url == "https://www.acmefoods.co.uk/"
    assert acme.hint["uses_technology"] in ("Confirmed", "Likely") and acme.hint["industry"] == "food"
    assert acme.hint["evidence_url"] == "https://partner.example.com/stories/acme-foods-netsuite"
    assert acme.hint["_country_by"].startswith("registry: wikidata")  # the country is still the registry's
    # LinkedIn is not read, and a page not naming the product is not read either.
    assert [e["url"] for e in s.evidence] == ["https://partner.example.com/stories/acme-foods-netsuite"]


async def test_proof_about_another_company_on_the_page_does_not_count_for_the_one_searched():
    def results(q):
        return [{"url": "https://news.example.org/beta-retail-netsuite", "title": "Acme Foods and NetSuite",
                 "content": "Beta Retail went live"}]

    s, _ = searcher(results)
    assert await s.prove(spec(), [listed("Acme Foods")]) == []
    assert any(e["company"] == "Beta Retail" and e["kept"] for e in s.evidence)  # kept on the Evidence sheet


async def test_the_pass_stops_at_the_reading_budget():
    s, asked = searcher(lambda q: [])
    s.deadline = 0.0
    assert await s.prove(spec(), [listed("Acme Foods")]) == []
    assert asked == [] and "reading budget" in s.notes[-1]


def test_names_match_either_way():
    assert about("Acme Foods Ltd", "Acme Foods") and about("Acme Foods", "ACME FOODS LIMITED")
    assert not about("Beta Retail", "Acme Foods")


