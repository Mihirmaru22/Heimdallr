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
