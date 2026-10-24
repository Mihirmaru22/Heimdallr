import httpx
import pytest

from app.discovery.gleif import GleifProvider, name_words
from app.discovery.providers import DiscoveryError
from app.spec.models import ExtractionSpec


def _record(lei, name, country="IN", city="MUMBAI", region="IN-MH", category="GENERAL", status="ACTIVE"):
    addr = {"addressLines": ["SUN HOUSE, CTS NO. 201"], "city": city, "region": region, "postalCode": "400063",
            "country": country}
    return {"id": lei, "attributes": {"lei": lei, "entity": {
        "legalName": {"name": name}, "status": status, "category": category,
        "legalAddress": addr, "headquartersAddress": addr}}}


RECORDS = [
    _record("335800CMJDNI6C5GQ574", "SUN PHARMACEUTICAL INDUSTRIES LIMITED"),
    _record("335800CMJDNI6C5GQ999", "SUN PHARMACEUTICAL LABORATORIES LIMITED"),  # same group, same website
    _record("5493001KJTIIGC8Y1R12", "PHARMA GROWTH FUND", category="FUND"),
    _record("5493001KJTIIGC8Y1R13", "OLD PHARMA LTD", status="INACTIVE"),
    _record("5493001KJTIIGC8Y1R14", "UNKNOWN PHARMACEUTICALS PVT LTD"),  # not in Wikidata
]
WIKI = {"Q1": {"labels": {"en": {"value": "Sun Pharmaceutical"}}, "claims": {
    "P1278": [{"mainsnak": {"datavalue": {"value": "335800CMJDNI6C5GQ574"}}},
              {"mainsnak": {"datavalue": {"value": "335800CMJDNI6C5GQ999"}}}],
    "P856": [{"mainsnak": {"datavalue": {"value": "https://sunpharma.com/"}}}]}}}


def transport(seen):
    def handler(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if request.url.host == "api.gleif.org":
            seen.append(dict(params))
            data = RECORDS if params["filter[fulltext]"] == "pharmaceutical" else []
            return httpx.Response(200, json={"data": data, "meta": {"pagination": {"lastPage": 1}}})
        if params.get("list") == "search":
            assert len(params["srsearch"]) <= 300
            hit = "P1278=335800CMJDNI6C5GQ574" in params["srsearch"]
            return httpx.Response(200, json={"query": {"search": [{"title": "Q1"}] if hit else []}})
        return httpx.Response(200, json={"entities": {i: WIKI[i] for i in params["ids"].split("|") if i in WIKI}})
    return handler


def _spec(**discovery):
    return ExtractionSpec.model_validate({"fields": [{"name": "company_name", "type": "string"}],
                                          "discovery": {"providers": ["gleif"], **discovery}})


async def test_gleif_finds_active_companies_with_a_website():
    seen = []
    provider = GleifProvider(httpx.AsyncClient(transport=httpx.MockTransport(transport(seen))), gap=0)
    results = await provider.discover(_spec(industry="pharmaceutical", countries=["IN"]))
    assert [r.url for r in results] == ["https://sunpharma.com/"]
    hint = results[0].hint
    assert hint["company_name"] == "Sun Pharmaceutical"
    assert hint["legal_name"] == "SUN PHARMACEUTICAL INDUSTRIES LIMITED"
    assert hint["headquarters"] == "Mumbai, MH" and hint["country"] == "India"
    assert hint["address"].startswith("SUN HOUSE") and results[0].method == "gleif"
    assert seen[0]["filter[entity.legalAddress.country]"] == "IN"
    assert provider.notes == ["gleif: 1 matching companies have no known website and were left out"]


async def test_gleif_explains_why_it_found_nothing():
    provider = GleifProvider(httpx.AsyncClient(transport=httpx.MockTransport(transport([]))), gap=0)
    with pytest.raises(DiscoveryError, match="needs an industry"):
        await provider.discover(_spec(countries=["IN"]))
    with pytest.raises(DiscoveryError, match="no active companies"):
        await provider.discover(_spec(industry="restaurants", countries=["IN"]))

    def down(request):
        return httpx.Response(503)
    provider = GleifProvider(httpx.AsyncClient(transport=httpx.MockTransport(down)), gap=0)
    with pytest.raises(DiscoveryError, match="HTTP 503"):
        await provider.discover(_spec(industry="pharmaceutical"))


def test_name_words():
    assert name_words("pharmaceutical") == ["pharmaceutical", "pharmaceuticals", "pharma"]
    assert name_words("logistics") == ["logistics"]
    assert name_words("chemical") == ["chemical", "chemicals"]
    assert name_words("defence") == ["defense", "defence", "aerospace"]
    assert name_words("aluminium") == ["aluminum", "aluminium", "aluminums", "aluminiums"]
