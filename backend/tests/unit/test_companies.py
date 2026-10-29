"""One record per company and one decision at the end: the cases measured in run 2 (2026-10-28)."""

from app.services.companies import (
    DELIVERED,
    ELSEWHERE,
    FILTER,
    NO_PROOF,
    UNCONFIRMED,
    WEAK,
    decide,
    group_companies,
    name_key,
)
from app.spec.models import ExtractionSpec


def spec(**discovery):
    return ExtractionSpec.model_validate({"entity": "company", "fields": [
        {"name": "company_name", "type": "string", "semantic": "company_name", "required": True}],
        "discovery": {"providers": ["case_studies"], "technology": "NetSuite", "countries": ["GB"], **discovery}})


def proof(company, verdict="Likely", website="", url="https://news.example/story", source="News article"):
    return {"company": company, "website": website, "url": url, "quote": f"{company} runs NetSuite.",
            "verdict": verdict, "strength": 0.5, "source_type": source, "reason": "named by a news page",
            "kept": True, "relationship": "uses", "evidence_date": ""}


def fact(site, kind, value, by="own pages", detail="", company=""):
    return {"site": site, "company": company, "kind": kind, "value": value, "by": by, "detail": detail,
            "source_url": f"https://{site}/", "quote": ""}


def one(evidence=(), facts=(), seeds=()):
    (c,) = group_companies(list(evidence), list(facts), list(seeds), []).values()
    return c


def test_a_proven_company_whose_country_cannot_be_settled_is_shown_not_dropped():
    c = one([proof("Lick", website="https://lick.com/")],
            [fact("lick.com", "country", "", detail="no address or one-country phone on 3 pages")])
    status, reasons, _ = decide(c, spec())
    assert status == UNCONFIRMED and any("no address" in r for r in reasons)


def test_the_strongest_kind_of_country_evidence_decides():
    facts = [fact("emerald.com", "country", "", detail="UK, SG and AE numbers"),
             fact("emerald.com", "country", "GB", by="registry: gleif", detail="legal address London")]
    status, _reasons, details = decide(one([proof("Emerald", website="https://emerald.com/")], facts), spec())
    assert status == DELIVERED and details["country"] == "GB" and details["country_by"].startswith("registry")
    # A registry that puts it elsewhere beats a page that looked local.
    facts = [fact("acme.co.uk", "country", "GB", detail="the country-code domain"),
             fact("acme.co.uk", "country", "US", by="registry: sec_edgar", detail="Delaware filer")]
    assert decide(one([proof("Acme", website="https://acme.co.uk/")], facts), spec())[0] == ELSEWHERE


def test_several_countries_of_one_kind_settle_nothing():
    facts = [fact("x.com", "country", "GB", by="proof"), fact("x.com", "country", "US", by="proof")]
    assert decide(one([proof("X", website="https://x.com/")], facts), spec())[0] == UNCONFIRMED


def test_a_failed_filter_is_a_visible_outcome_with_its_reason():
    facts = [fact("kemwell.com", "country", "GB"),
             fact("kemwell.com", "filter", "not met", by="model:m", detail="a CDMO, not a drug maker")]
    status, reasons, _ = decide(one([proof("Kemwell", website="https://kemwell.com/")], facts), spec())
    assert status == FILTER and any("CDMO" in r for r in reasons)


def test_proof_strength_decides_before_anything_else():
    assert decide(one([proof("Vivo", verdict="Mentioned", website="https://vivo.com/")]), spec())[0] == WEAK
    seeds = [{"url": "https://www.lupin.com/", "method": "wikidata", "name": "Lupin", "status": "fetched",
              "reason": ""}]
    lupin = one([], [fact("lupin.com", "country", "GB")], seeds)
    assert decide(lupin, spec())[0] == NO_PROOF


def test_a_name_seen_with_a_website_anywhere_joins_that_company():
    evidence = [proof("Kemwell BioPharma", website="https://kemwellbiopharma.com/"),
                proof("Kemwell Biopharma Pvt. Ltd.", url="https://press.example/k")]
    facts = [fact("kemwellbiopharma.com", "country", "GB", company="Kemwell BioPharma")]
    companies = group_companies(evidence, facts, [], [])
    assert list(companies) == ["kemwellbiopharma.com"]
    assert len(companies["kemwellbiopharma.com"].proof) == 2
    assert name_key("Kemwell BioPharma") == name_key("kemwell biopharma ltd")


def test_without_a_technology_or_countries_only_filters_decide():
    plain = ExtractionSpec.model_validate({"entity": "company", "fields": [
        {"name": "company_name", "type": "string", "semantic": "company_name", "required": True}],
        "discovery": {"providers": ["searxng"], "industry": "restaurants"}})
    seeds = [{"url": "https://pizza.example/", "method": "searxng", "name": "Pizza", "status": "fetched",
              "reason": ""}]
    ok = one([], [fact("pizza.example", "filter", "met")], seeds)
    assert decide(ok, plain)[0] == DELIVERED
    bad = one([], [fact("pizza.example", "filter", "not met", detail="a listing site")], seeds)
    assert decide(bad, plain)[0] == FILTER
