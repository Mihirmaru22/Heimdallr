"""Which registered organisation a name stands for: matched by rules, settled only when the registries agree."""

import httpx

from app.discovery.entities import Candidate, EntityResolver, name_match, resolution_facts, settle
from app.evidence.thirdparty import countries_named


def test_names_match_once_legal_forms_are_set_aside_and_one_word_names_only_exactly():
    assert name_match("Kemwell BioPharma", "KEMWELL BIOPHARMA PRIVATE LIMITED") == "exact"
    assert name_match("Nationwide Insurance", "Nationwide Mutual Insurance Company") == "words"
    assert name_match("Lick", "Lick Ltd") == "exact"
    assert name_match("Lick", "Lick Sweets Ltd") == ""  # a one-word name is never a part of another
    assert name_match("Emerald Technology", "Emerald Technology Holdings Group Plc") == "exact"
    assert name_match("Siemens", "Siemens Healthineers AG") == ""


def test_the_company_s_own_website_beats_any_name():
    cands = [Candidate("wikidata", "Q1", "EnerSys", "US", website="https://www.enersys.com/"),
             Candidate("gleif", "L1", "ENERSYS SP Z O O", "PL")]
    res = settle("EnerSys", "https://www.enersys.com/en/", cands)
    assert res.country == "US" and res.by == "registry: wikidata" and "matched by website" in res.detail


def test_registries_that_disagree_settle_nothing_and_say_who_disagreed():
    cands = [Candidate("gleif", "L1", "Emerald Technology Ltd", "GB"),
             Candidate("gleif", "L2", "Emerald Technology Inc", "US")]
    res = settle("Emerald Technology", "", cands)
    assert res.country == "" and "disagree" in res.detail and "GB" in res.detail and "US" in res.detail


def test_entities_that_agree_settle_the_country_and_give_the_official_website():
    cands = [Candidate("wikidata", "Q2", "Bharat Serums and Vaccines", "IN", website="https://bsvgroup.com/"),
             Candidate("gleif", "L3", "BHARAT SERUMS AND VACCINES LIMITED", "IN", place="Mumbai")]
    res = settle("Bharat Serums and Vaccines Limited (BSV)", "", cands)
    # "(BSV)" adds a word, so these are word matches; both agree on India.
    assert res.country == "IN" and res.website == "https://bsvgroup.com/"
    (country, website) = resolution_facts("Bharat Serums", "", res)
    assert country["kind"] == "country" and country["value"] == "IN" and website["value"] == "https://bsvgroup.com/"


def test_no_match_settles_nothing():
    res = settle("Lick", "https://lick.com/", [Candidate("gleif", "L4", "LICKING VALLEY FARMS LLC", "US")])
    assert res.country == "" and "no registry entity matches" in res.detail


async def test_the_resolver_asks_wikidata_and_gleif_and_keeps_one_answer_per_name():
    calls = []

    def handler(request):
        calls.append(request.url.host)
        if "wikidata" in request.url.host:
            if request.url.params.get("action") == "wbsearchentities":
                return httpx.Response(200, json={"search": [{"id": "Q42"}]})
            return httpx.Response(200, json={"entities": {"Q42": {
                "labels": {"en": {"value": "Conmed Corporation"}},
                "claims": {"P17": [{"mainsnak": {"datavalue": {"value": {"id": "Q30"}}}}],
                           "P452": [{"mainsnak": {"datavalue": {"value": {"id": "Q11190"}}}}],
                           "P856": [{"mainsnak": {"datavalue": {"value": "https://www.conmed.com/"}}}]}}}})
        return httpx.Response(200, json={"data": []})

    resolver = EntityResolver(httpx.AsyncClient(transport=httpx.MockTransport(handler)), gleif_gap=0)
    import app.discovery.entities as entities

    entities.WIKIDATA_RETRY_WAIT = 0

    async def no_sec(_company):
        return []

    resolver._sec = no_sec
    res = await resolver.resolve("CONMED Corporation", "https://www.conmed.com/en/")
    assert res.country == "US" and res.by == "registry: wikidata"
    n = len(calls)
    await resolver.resolve("CONMED Corporation", "https://www.conmed.com/en/")
    assert len(calls) == n  # asked once per job


def test_countries_a_sentence_names_and_states():
    from app.evidence.thirdparty import countries_stated

    assert countries_stated("Ringers Western ... Roadshow heads to New Zealand") == set()
    assert countries_stated("Lick, the UK-headquartered home decor brand") == {"GB"}
    assert countries_stated("Acme, a company based in Germany, chose it") == {"DE"}
    assert countries_named("Lick, the UK-headquartered home décor brand, has turned to NetSuite") == {"GB"}
    assert countries_named("Kemwell BioPharma, India's largest biologics CDMO") == {"IN"}
    assert countries_named("it helps us grow") == set()  # "us" the word is not the US
    assert countries_named("offices in the US and Germany") == {"US", "DE"}


async def test_a_registry_that_times_out_is_asked_again_and_a_failure_is_not_kept_as_no_match():
    calls = {"gleif": 0}

    def handler(request):
        if "wikidata" in request.url.host:
            return httpx.Response(200, json={"search": []})
        calls["gleif"] += 1
        if calls["gleif"] == 1:
            raise httpx.ReadTimeout("busy")  # a busy moment, then an answer
        return httpx.Response(200, json={"data": [{"id": "L1", "attributes": {"lei": "L1", "entity": {
            "legalName": {"name": "GREENSILL CAPITAL (UK) LIMITED"}, "status": "ACTIVE",
            "legalAddress": {"country": "GB", "city": "Warrington"},
            "headquartersAddress": {"country": "GB", "city": "Warrington"}}}}]})

    async def no_sec(_company):
        return []

    resolver = EntityResolver(httpx.AsyncClient(transport=httpx.MockTransport(handler)), gleif_gap=0,
                              retry_waits=(0.0, 0.0))
    resolver._sec = no_sec
    res = await resolver.resolve("Greensill Capital")
    assert res.country == "GB" and calls["gleif"] == 2

    def down(request):
        if "wikidata" in request.url.host:
            return httpx.Response(200, json={"search": []})
        return httpx.Response(503)

    resolver = EntityResolver(httpx.AsyncClient(transport=httpx.MockTransport(down)), gleif_gap=0,
                              retry_waits=(0.0, 0.0))
    resolver._sec = no_sec
    res = await resolver.resolve("Greensill Capital")
    assert res.country == "" and res.detail.startswith("registry lookup failed (gleif)")
    assert not resolver.cache  # not kept: the next step that needs the name asks again


def test_each_source_reading_pages_gets_an_equal_share_of_the_budget_left():
    from app.crawl.runner import reading_share

    assert reading_share(0.0, 3600.0, 2) == 1800.0  # case studies, then news: half each
    assert reading_share(600.0, 3600.0, 1) == 3600.0  # the last source gets all that is left, early finish included
    assert reading_share(4000.0, 3600.0, 1) == 4000.0  # past the deadline: no time


def test_sources_with_open_ended_candidates_read_last_and_take_the_time_left():
    from types import SimpleNamespace

    from app.crawl.runner import reading_order, reading_share

    cases = SimpleNamespace(name="case_studies", deadline=None, open_ended=True)
    news = SimpleNamespace(name="news", deadline=None, open_ended=False)
    filings = SimpleNamespace(name="sec_filings")
    assert [p.name for p in reading_order([filings, cases, news])] == ["sec_filings", "news", "case_studies"]
    # News is unreachable and ends at once: case studies, last, get the whole hour that is left, not half.
    assert reading_share(0.0, 3600.0, 2) == 1800.0
    assert reading_share(5.0, 3600.0, 1) == 3600.0
