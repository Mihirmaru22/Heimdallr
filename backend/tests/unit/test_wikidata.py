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


async def test_discover_parses_results_and_dedupes():
    def handler(request: httpx.Request) -> httpx.Response:
        if "wbsearchentities" in str(request.url):
            return httpx.Response(200, json={"search": [{"id": "Q3510521"}]})
        rows = [{"org": {"value": "http://www.wikidata.org/entity/Q1"}, "orgLabel": {"value": "Acme"},
                 "website": {"value": "https://acme.example"}, "countryLabel": {"value": "Germany"}},
                {"org": {"value": "http://www.wikidata.org/entity/Q1"}, "orgLabel": {"value": "Acme"},
                 "website": {"value": "https://acme.example/"}},
                {"org": {"value": "http://www.wikidata.org/entity/Q2"}, "website": {"value": "ftp://bad"}}]
        return httpx.Response(200, json={"results": {"bindings": rows}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    results = await WikidataProvider(client).discover(_spec(industry="computer security", region="europe"))
    assert [r.url for r in results] == ["https://acme.example/"]
    assert results[0].hint["company_name"] == "Acme" and results[0].hint["country"] == "Germany"


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


async def test_timeout_retries_with_a_lean_query():
    queries = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "wbsearchentities" in str(request.url):
            return httpx.Response(200, json={"search": [{"id": "Q507443", "label": "pharmaceutical industry"}]})
        body = request.content.decode()
        queries.append(body)
        if len(queries) == 1:
            raise httpx.ReadTimeout("timed out", request=request)
        rows = [{"org": {"value": "http://www.wikidata.org/entity/Q1"}, "orgLabel": {"value": "Q1"},
                 "website": {"value": "https://pharma.example"}}]
        return httpx.Response(200, json={"results": {"bindings": rows}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    results = await WikidataProvider(client).discover(_spec(industry="pharmaceutical", region="europe"))
    assert [r.url for r in results] == ["https://pharma.example/"]
    assert "P159" in queries[0] and "P159" not in queries[1]
    assert "company_name" not in results[0].hint  # a bare Q-id is not a name


async def test_two_timeouts_give_a_clear_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if "wbsearchentities" in str(request.url):
            return httpx.Response(200, json={"search": [{"id": "Q507443", "label": "pharmaceutical industry"}]})
        raise httpx.ReadTimeout("timed out", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(DiscoveryError, match="did not answer within 60 seconds"):
        await WikidataProvider(client).discover(_spec(industry="pharmaceutical"))


async def test_no_rows_is_an_error_not_an_empty_job():
    def handler(request: httpx.Request) -> httpx.Response:
        if "wbsearchentities" in str(request.url):
            return httpx.Response(200, json={"search": [{"id": "Q507443", "label": "pharmaceutical industry"}]})
        return httpx.Response(200, json={"results": {"bindings": []}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(DiscoveryError, match="no companies"):
        await WikidataProvider(client).discover(_spec(industry="pharmaceutical", countries=["DE"]))
