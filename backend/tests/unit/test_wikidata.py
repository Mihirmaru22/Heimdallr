import httpx
import pytest

from app.discovery.providers import DiscoveryError, WikidataProvider
from app.spec.models import ExtractionSpec


def _spec(**discovery):
    return ExtractionSpec.model_validate({"fields": [{"name": "company_name", "type": "string"}],
                                          "discovery": {"providers": ["wikidata"], **discovery}})


def test_query_is_built_from_validated_parts_only():
    q = WikidataProvider.build_query(["Q123", "Q1; DROP"], ["DE", "x\"}"], None, 10)
    assert "wd:Q123" in q and "DROP" not in q and '"DE"' in q and 'x"}' not in q
    assert "LIMIT 10" in q and "P576" in q


def test_search_query_lists_industries_and_countries():
    q = WikidataProvider.search_query(["Q507443", "bad id"], ["DE", "FR", "zz"], None)
    assert q == "haswbstatement:P452=Q507443 haswbstatement:P17=Q183|P17=Q142"
    europe = WikidataProvider.search_query(["Q507443"], [], "europe")
    assert "P17=Q145" in europe and "P17=Q30" not in europe
    assert WikidataProvider.search_query([], ["IN"], None).startswith("haswbstatement:P31=")


def _entity(qid, label, site=None, country="Q183", hq=None, dissolved=False):
    def claim(value, rank="normal"):
        return {"rank": rank, "mainsnak": {"datavalue": {"value": value}}}
    claims = {"P17": [claim({"id": country})]}
    if site:
        claims["P856"] = [claim(site)]
    if hq:
        claims["P159"] = [claim({"id": hq})]
    if dissolved:
        claims["P576"] = [claim({"time": "+2001-00-00T00:00:00Z"})]
    return {"id": qid, "labels": {"en": {"value": label}} if label else {}, "claims": claims}


def search_handler(entities, hits=None, calls=None):
    def handler(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if calls is not None:
            calls.append(dict(params))
        if params.get("action") == "wbsearchentities":
            return httpx.Response(200, json={"search": [{"id": "Q507443", "label": "pharmaceutical industry"}]})
        if params.get("list") == "search":
            titles = hits if hits is not None else list(entities)
            return httpx.Response(200, json={"query": {"search": [{"title": t} for t in titles]}})
        if params.get("action") == "wbgetentities":
            return httpx.Response(200, json={"entities": {i: entities[i] for i in params["ids"].split("|")
                                                          if i in entities}})
        raise AssertionError(f"unexpected request {request.url}")
    return handler


async def test_discover_uses_the_search_index_and_dedupes():
    entities = {
        "Q1": _entity("Q1", "Acme Pharma", "https://www.acme.com/en", hq="Q64"),
        "Q2": _entity("Q2", "Acme Pharma GmbH", "https://acme.com/de"),  # same site as Q1
        "Q3": _entity("Q3", "Gone AG", "https://gone.com", dissolved=True),
        "Q4": _entity("Q4", "No Site AG"),
        "Q5": _entity("Q5", None, "https://beta.com", country="Q142"),
        "Q64": {"id": "Q64", "labels": {"en": {"value": "Berlin"}}},
        "Q507443": {"id": "Q507443", "labels": {"en": {"value": "pharmaceutical industry"}}},
    }
    entities["Q1"]["claims"]["P452"] = [{"mainsnak": {"datavalue": {"value": {"id": "Q507443"}}}}]
    calls = []
    client = httpx.AsyncClient(transport=httpx.MockTransport(
        search_handler(entities, hits=["Q1", "Q2", "Q3", "Q4", "Q5"], calls=calls)))
    results = await WikidataProvider(client).discover(_spec(industry="pharmaceutical", region="europe"))
    assert [r.url for r in results] == ["https://www.acme.com/en", "https://beta.com/"]
    assert results[0].hint == {"company_name": "Acme Pharma", "headquarters": "Berlin", "country": "Germany",
                               "industry": "pharmaceutical industry", "website_url": "https://www.acme.com/en",
                               "_source": "http://www.wikidata.org/entity/Q1"}
    assert "company_name" not in results[1].hint and results[1].hint["country"] == "France"
    search = next(c for c in calls if c.get("list") == "search")
    assert "haswbstatement:P452=Q507443" in search["srsearch"] and "P17=Q183" in search["srsearch"]


async def test_search_index_failure_falls_back_to_the_query_service():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("action") == "wbsearchentities":
            return httpx.Response(200, json={"search": [{"id": "Q507443", "label": "pharmaceutical industry"}]})
        if request.url.params.get("list") == "search":
            return httpx.Response(503)
        rows = [{"org": {"value": "http://www.wikidata.org/entity/Q1"}, "orgLabel": {"value": "Q1"},
                 "website": {"value": "https://pharma.example"}}]
        return httpx.Response(200, json={"results": {"bindings": rows}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    results = await WikidataProvider(client).discover(_spec(industry="pharmaceutical", region="europe"))
    assert [r.url for r in results] == ["https://pharma.example/"]
    assert "company_name" not in results[0].hint  # a bare Q-id is not a name


async def test_rate_limit_becomes_discovery_error():
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(429)))
    with pytest.raises(DiscoveryError):
        await WikidataProvider(client).discover(_spec(countries=["DE"]))


async def test_needs_some_filter():
    with pytest.raises(DiscoveryError):
        await WikidataProvider(httpx.AsyncClient()).discover(_spec())


async def test_industry_search_prefers_the_sector_over_the_product():
    def handler(request: httpx.Request) -> httpx.Response:
        search = request.url.params.get("search")
        if search == "pharmaceutical industry":
            return httpx.Response(200, json={"search": [
                {"id": "Q507443", "label": "pharmaceutical industry", "description": "industry that develops drugs"}]})
        return httpx.Response(200, json={"search": [
            {"id": "Q12140", "label": "medication", "description": "substance used to treat a disease"},
            {"id": "Q507443", "label": "pharmaceutical industry", "description": "industry"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await WikidataProvider(client).industry_ids(client, "pharmaceutical") == ["Q507443"]


async def test_search_down_and_query_service_timeout_give_a_clear_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("action") == "wbsearchentities":
            return httpx.Response(200, json={"search": [{"id": "Q507443", "label": "pharmaceutical industry"}]})
        if request.url.params.get("list") == "search":
            return httpx.Response(503)
        raise httpx.ReadTimeout("timed out", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(DiscoveryError, match="did not answer within 60 seconds"):
        await WikidataProvider(client).discover(_spec(industry="pharmaceutical"))


async def test_no_hits_is_an_error_not_an_empty_job():
    client = httpx.AsyncClient(transport=httpx.MockTransport(search_handler({}, hits=[])))
    with pytest.raises(DiscoveryError, match="no companies"):
        await WikidataProvider(client).discover(_spec(industry="pharmaceutical", countries=["DE"]))


# --- SearXNG -------------------------------------------------------------------------------------

from app.discovery.providers import SearxngProvider  # noqa: E402


def _searx_spec(**discovery):
    return ExtractionSpec.model_validate({"entity": "company", "fields": [{"name": "company_name", "type": "string"}],
                                          "discovery": {"providers": ["searxng"], **discovery}})


def test_searxng_queries_name_the_places():
    spec = _searx_spec(industry="pharmaceutical", countries=["DE", "FR"])
    assert SearxngProvider.queries(spec) == ["pharmaceutical companies Germany", "pharmaceutical companies France"]
    assert SearxngProvider.queries(_searx_spec(industry="biotech", region="europe")) == ["biotech companies Europe"]


def test_searxng_keeps_homepages_and_drops_directories():
    assert SearxngProvider.homepage("https://www.bayer.com/en/pharma/products?x=1") == "https://www.bayer.com/"
    for url in ["https://en.wikipedia.org/wiki/Bayer", "https://www.linkedin.com/company/bayer",
                "https://www.crunchbase.com/organization/x", "mailto:a@b.com"]:
        assert SearxngProvider.homepage(url) is None


async def test_searxng_discovers_unique_sites_across_pages():
    pages = {
        "1": [{"url": "https://www.alpha-pharma.com/about"}, {"url": "https://en.wikipedia.org/wiki/Alpha"},
              {"url": "https://alpha-pharma.com/contact"}],
        "2": [{"url": "https://beta-bio.com/"}],
        "3": [],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["format"] == "json"
        return httpx.Response(200, json={"results": pages[request.url.params["pageno"]]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = SearxngProvider(client, base_url="http://searxng:8080")
    results = await provider.discover(_searx_spec(industry="pharmaceutical", region="europe", max_results=10))
    assert [r.url for r in results] == ["https://www.alpha-pharma.com/", "https://beta-bio.com/"]
    assert all(r.method == "searxng" for r in results)


async def test_searxng_not_configured_or_json_disabled():
    with pytest.raises(DiscoveryError, match="not configured"):
        await SearxngProvider(base_url="").discover(_searx_spec(industry="pharma"))
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(403)))
    with pytest.raises(DiscoveryError, match="json"):
        await SearxngProvider(client, base_url="http://s").discover(_searx_spec(industry="pharma"))


def test_search_query_stays_under_wikidatas_length_limit():
    q = WikidataProvider.search_query(["Q507443", "Q1068236", "Q5532284", "Q11190"], [], "europe")
    assert len(q) <= 290 and "P17=Q145" in q and "P452=Q11190" in q


def test_label_falls_back_to_the_language_neutral_label():
    from app.discovery.providers import wd_label

    assert wd_label({"labels": {"mul": {"value": "Roblox"}}}) == "Roblox"
    assert wd_label({"labels": {"en": {"value": "Roblox Corporation"}, "mul": {"value": "Roblox"}}}) == \
        "Roblox Corporation"
    assert wd_label({"labels": {}}) is None
