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


def test_countries_a_sentence_names():
    assert countries_named("Lick, the UK-headquartered home décor brand, has turned to NetSuite") == {"GB"}
    assert countries_named("Kemwell BioPharma, India's largest biologics CDMO") == {"IN"}
    assert countries_named("it helps us grow") == set()  # "us" the word is not the US
    assert countries_named("offices in the US and Germany") == {"US", "DE"}
