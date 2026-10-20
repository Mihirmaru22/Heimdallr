import httpx
import pytest
from sqlalchemy import select

from app.db import session_scope
from app.discovery.providers import DiscoveryError, providers_for
from app.discovery.sec_edgar import SecEdgarProvider, refresh_index, sic_codes_for
from app.models import SecCompany
from app.spec.interpret import interpret
from app.spec.models import ExtractionSpec

TICKERS = {"fields": ["cik", "name", "ticker", "exchange"], "data": [
    [78003, "PFIZER INC", "PFE", "NYSE"],
    [320193, "Apple Inc.", "AAPL", "Nasdaq"],
    [78003, "PFIZER INC", "PFE-B", "NYSE"],  # a second ticker for the same company
    [59478, "ELI LILLY & Co", "LLY", "NYSE"],
    [1000001, "TINY PHARMA CORP", "TINY", "OTC"],
    [1000002, "LONDON DRUGS PLC", "LDN", "NYSE"],
]}


def _sub(sic, desc, city, state, website="", foreign=False):
    return {"sic": sic, "sicDescription": desc, "website": website, "addresses": {"business": {
        "city": city, "stateOrCountry": state, "stateOrCountryDescription": "United Kingdom" if foreign else state,
        "isForeignLocation": 1 if foreign else 0}}}


SUBMISSIONS = {
    78003: _sub("2834", "Pharmaceutical Preparations", "NEW YORK", "NY"),
    320193: _sub("3571", "Electronic Computers", "CUPERTINO", "CA", website="https://www.apple.com"),
    59478: _sub("2834", "Pharmaceutical Preparations", "INDIANAPOLIS", "IN"),
    1000001: _sub("2834", "Pharmaceutical Preparations", "AUSTIN", "TX"),
    1000002: _sub("2834", "Pharmaceutical Preparations", "LONDON", "X0", foreign=True),
}


def sec_transport(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("company_tickers_exchange.json"):
        return httpx.Response(200, json=TICKERS)
    cik = int(request.url.path.rsplit("CIK", 1)[1].removesuffix(".json"))
    return httpx.Response(200, json=SUBMISSIONS[cik]) if cik in SUBMISSIONS else httpx.Response(404)


def _build_index():
    with httpx.Client(transport=httpx.MockTransport(sec_transport)) as client:
        return refresh_index(client, rate=0)


def _spec(**discovery):
    return ExtractionSpec.model_validate({"fields": [{"name": "company_name", "type": "string"}],
                                          "discovery": {"providers": ["sec_edgar"], **discovery}})


def wikidata_transport(by_cik):
    """Wikidata answers: CIK 78003 -> Pfizer with a website, 59478 -> Lilly with a website."""
    entities = {
        "Q206921": {"labels": {"en": {"value": "Pfizer"}}, "claims": {
            "P5531": [{"mainsnak": {"datavalue": {"value": "0000078003"}}}],
            "P856": [{"mainsnak": {"datavalue": {"value": "https://www.pfizer.com/"}}}]}},
        "Q632760": {"labels": {"en": {"value": "Eli Lilly and Company"}}, "claims": {
            "P5531": [{"mainsnak": {"datavalue": {"value": "0000059478"}}}],
            "P856": [{"mainsnak": {"datavalue": {"value": "https://www.lilly.com/"}}}]}},
    }
    qid_for = {"0000078003": "Q206921", "0000059478": "Q632760"}

    def handler(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if params.get("list") == "search":
            by_cik.append(params["srsearch"])
            hits = [qid for cik, qid in qid_for.items() if f"P5531={cik}" in params["srsearch"]]
            return httpx.Response(200, json={"query": {"search": [{"title": q} for q in hits]}})
        ids = params["ids"].split("|")
        return httpx.Response(200, json={"entities": {i: entities[i] for i in ids if i in entities}})
    return handler


def test_refresh_index_stores_one_row_per_company_with_its_industry(db_clean):
    result = _build_index()
    assert result == {"companies": 5, "looked_up": 5, "failed": 0}
    with session_scope(bypass=True) as db:
        rows = {r.cik: r for r in db.execute(select(SecCompany)).scalars()}
    assert rows[78003].ticker == "PFE" and rows[78003].rank == 0
    assert rows[78003].sic == "2834" and rows[78003].city == "New York" and rows[78003].state == "NY"
    assert rows[1000002].foreign and rows[1000002].state == "United Kingdom"
    assert rows[320193].website == "https://www.apple.com/"
    # A second run only looks up companies that are due again.
    with httpx.Client(transport=httpx.MockTransport(sec_transport)) as client:
        assert refresh_index(client, rate=0)["looked_up"] == 0


def test_industry_words_map_to_sic_codes():
    descriptions = {"2834": "Pharmaceutical Preparations", "2836": "Biological Products, (No Diagnostic Substances)",
                    "7372": "Services-Prepackaged Software", "6022": "State Commercial Banks"}
    assert sic_codes_for("pharmaceutical", descriptions) == ["2834"]
    assert sic_codes_for("biotech", descriptions) == ["2834", "2836"]
    assert sic_codes_for("software", descriptions) == ["7372"]
    assert sic_codes_for("banking", descriptions) == ["6022"]
    assert sic_codes_for("restaurants", descriptions) == []


async def test_discovery_finds_listed_companies_and_their_websites(db_clean):
    _build_index()
    searches = []
    client = httpx.AsyncClient(transport=httpx.MockTransport(wikidata_transport(searches)))
    provider = SecEdgarProvider(client)
    results = await provider.discover(_spec(industry="pharmaceutical", countries=["US"], max_results=10))
    # Largest first; the UK filer is left out of a US search; Tiny Pharma has no known website.
    assert [r.url for r in results] == ["https://www.pfizer.com/", "https://www.lilly.com/"]
    assert results[0].hint == {"company_name": "Pfizer", "headquarters": "New York, NY", "country": "United States",
                               "industry": "Pharmaceutical Preparations", "website_url": "https://www.pfizer.com/",
                               "_source": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000078003"}
    assert all(r.method == "sec_edgar" for r in results)
    assert provider.notes == ["sec_edgar: 1 matching companies have no known website and were left out"]
    assert all(len(s) <= 300 for s in searches)


async def test_discovery_explains_why_it_was_skipped(db_clean):
    provider = SecEdgarProvider(httpx.AsyncClient())
    with pytest.raises(DiscoveryError, match="only lists US-listed"):
        await provider.discover(_spec(industry="pharmaceutical", region="europe"))
    with pytest.raises(DiscoveryError, match="refresh-sec"):
        await provider.discover(_spec(industry="pharmaceutical", countries=["US"]))
    _build_index()
    with pytest.raises(DiscoveryError, match="no SEC industry code"):
        await provider.discover(_spec(industry="restaurants", countries=["US"]))


def test_us_requests_use_sec_edgar_by_default():
    spec = interpret("Find 50 pharmaceutical companies in the United States with their website")
    assert spec.discovery.providers == ["wikidata", "sec_edgar", "searxng"]
    assert [p.name for p in providers_for(spec)] == ["wikidata", "sec_edgar", "searxng"]
    europe = interpret("Find 50 pharmaceutical companies in Europe with their website")
    assert "sec_edgar" not in europe.discovery.providers
