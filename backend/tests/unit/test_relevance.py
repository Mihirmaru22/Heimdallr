import pytest

from app.discovery.relevance import off_topic_reason, outside_countries_reason, site_country
from app.extract.deterministic import parse_page
from app.spec.models import ExtractionSpec


def _spec(**discovery):
    return ExtractionSpec.model_validate({"fields": [{"name": "company_name", "type": "string"}],
                                          "discovery": {"providers": ["searxng"], **discovery}})


def _doc(url, body, jsonld=""):
    script = f'<script type="application/ld+json">{jsonld}</script>' if jsonld else ""
    return parse_page(url, f"<html><head><title>Home</title>{script}</head><body>{body}</body></html>")


def test_homepage_must_mention_the_industry():
    spec = _spec(industry="cybersecurity")
    assert off_topic_reason(_doc("https://acme.com/", "<p>Cyber security for banks</p>"), spec) is None
    assert off_topic_reason(_doc("https://acme.com/", "<p>Endpoint security platform</p>"), spec) is None
    assert "does not mention" in off_topic_reason(_doc("https://drone.com/", "<p>We build drones</p>"), spec)
    pharma = _spec(industry="pharmaceutical")
    assert off_topic_reason(_doc("https://acme.com/", "<p>A pharma company</p>"), pharma) is None


def test_other_countries_are_dropped_and_unclear_ones_kept():
    spec = _spec(industry="cybersecurity", countries=["US"])
    body = "<p>cybersecurity</p>"
    assert "PL" in off_topic_reason(_doc("https://elementrica.pl/", body), spec)
    canada = '{"@type": "Organization", "address": {"addressLocality": "Vaughan", "addressCountry": "CA"}}'
    assert "CA" in off_topic_reason(_doc("https://mevo.com/", body, canada), spec)
    assert off_topic_reason(_doc("https://acme.io/", body), spec) is None  # .io says nothing about location
    assert off_topic_reason(_doc("https://acme.com/", body), spec) is None  # unknown: kept
    us = '{"@type": "Organization", "address": {"addressCountry": "United States"}}'
    assert site_country(_doc("https://acme.co.uk/", body, us)) == "US"  # structured address beats the domain
    assert site_country(_doc("https://acme.co.uk/", body)) == "GB"


def test_phone_numbers_point_to_a_country_only_when_they_agree():
    body = "<p>cybersecurity</p>"
    assert site_country(_doc("https://acme.com/", body + '<a href="tel:+48124004777">x</a>')) == "PL"
    mixed = body + '<a href="tel:+48124004777">x</a><a href="tel:+18663001261">y</a>'
    assert site_country(_doc("https://acme.com/", mixed)) is None


def test_only_these_countries_is_a_hard_limit():
    spec = _spec(countries=["us"])
    assert spec.discovery.countries == ["US"] and spec.discovery.strict_countries
    plain = _doc("https://acme.com/", "<p>hello</p>")
    # Registry entry in another country: dropped. In the country: kept.
    assert "IN" in outside_countries_reason(plain, spec, "wikidata", {"country": "India"})
    assert outside_countries_reason(plain, spec, "wikidata", {"country": "United States of America"}) is None
    # The homepage says Germany even though the registry gave no country.
    assert "DE" in outside_countries_reason(_doc("https://acme.de/", "x"), spec, "sec_edgar", {})
    # Web search: an unconfirmed country is not enough. Registries already matched it; start URLs always stay.
    assert "could not confirm" in outside_countries_reason(plain, spec, "searxng", {})
    assert outside_countries_reason(plain, spec, "wikidata", {}) is None
    assert outside_countries_reason(_doc("https://acme.de/", "x"), spec, "seed", {}) is None
    loose = _spec(countries=["US"], strict_countries=False)
    assert outside_countries_reason(_doc("https://acme.de/", "x"), loose, "searxng", {}) is None


def test_countries_must_be_two_letter_codes():
    with pytest.raises(ValueError, match="two-letter"):
        _spec(countries=["Germany"])


def test_wikidata_results_are_checked_for_the_industry_but_not_the_country():
    spec = _spec(industry="pharmaceutical", countries=["IN"])
    it_firm = _doc("https://www.techserve.in/", "<p>IT services and staffing</p>")
    assert "does not mention" in off_topic_reason(it_firm, spec, check_country=False)
    abroad = _doc("https://acme.de/", "<p>Pharmaceutical maker</p>")
    assert off_topic_reason(abroad, spec, check_country=False) is None


def test_british_and_american_spellings_both_match():
    from app.discovery.relevance import industry_terms

    for typed in ("defence", "defense", "Defence"):
        terms = industry_terms(typed)
        assert "defense" in terms and "defence" in terms
    assert "aluminum" in industry_terms("aluminium") and "aluminium" in industry_terms("aluminum")


def test_a_page_with_no_text_is_unreadable_not_off_topic():
    from app.discovery.relevance import unreadable

    assert unreadable(_doc("https://cipla.example/", "<div id='app'></div>"))
    assert not unreadable(_doc("https://acme.com/", "<p>" + "We make generic medicines. " * 10 + "</p>"))
