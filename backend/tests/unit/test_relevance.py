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


def test_a_multinational_is_placed_where_most_of_its_numbers_are():
    def tels(*nums):
        return "".join(f'<a href="tel:{n}">call</a>' for n in nums)

    ncc = _doc("https://www.example.com/", tels("+443316300690", "+44 (0) 161 209 5200", "+441612095200",
                                                "+18008133523", "+61295524451"))
    assert site_country(ncc) == "GB"  # two UK numbers, one US, one AU
    assert site_country(_doc("https://www.example.com/", tels("+442076644522", "+18008133523"))) is None  # a tie


def test_a_country_is_read_from_the_companys_own_pages_not_from_its_words():
    from app.discovery.relevance import pages_country

    home = _doc("https://acme.com/", "<p>Cyber security</p><a href='/contact'>Contact</a>")
    numbers = _doc("https://acme.com/contact", "<p>Sales +44 (0) 845 838 2050, support +44 20 7946 0123</p>")
    assert pages_country([home, numbers]) == ("GB", "2 phone number(s) on https://acme.com/contact")
    us = _doc("https://acme.com/about", "x", '{"@type": "Organization", "address": {"addressCountry": "US"}}')
    assert pages_country([home, numbers, us]) == ("US", "structured address on https://acme.com/about")
    words = _doc("https://acme.com/about", "<p>Teams in London; the UK is our biggest market.</p>")
    assert pages_country([home, words]) == (None, "")
    assert pages_country([_doc("https://acme.co.uk/", "x")]) == ("GB", "the country-code domain")
    offices = _doc("https://acme.com/contact", "<p>UK +44 20 7946 0123</p><p>US +1 617 904 9180, +1 833 303 6463</p>")
    assert pages_country([home, offices]) == (None, "")  # an office directory, not a headquarters
