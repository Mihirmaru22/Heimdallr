from app.discovery.relevance import off_topic_reason, site_country
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
