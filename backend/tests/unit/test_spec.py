import pytest
from pydantic import ValidationError

from app.spec.interpret import interpret
from app.spec.models import ExtractionSpec, validate_spec

LIMITS = {"max_pages_per_job": 100, "max_depth": 2}


def test_interpreter_cybersecurity_example():
    spec = interpret("Find up to 50 cybersecurity companies in Europe and collect company name, website, "
                     "contact email, headquarters and pricing")
    names = [f.name for f in spec.fields]
    assert names[0] == "company_name"
    assert {"website_url", "contact_email", "pricing"} <= set(names)
    assert spec.discovery.providers == ["wikidata", "gleif", "searxng"]
    assert spec.discovery.region == "europe"
    assert spec.discovery.max_results == 50


def test_interpreter_uses_start_urls_as_seeds():
    spec = interpret("Get the email and phone from these sites", ["https://a.example/", "https://b.example/"])
    assert spec.discovery.providers == ["seeds"]
    assert spec.crawl.start_urls[:2] == ["https://a.example/", "https://b.example/"]


def test_limits_are_clamped():
    raw = {"fields": [{"name": "x", "type": "string"}], "crawl": {"max_pages": 100000, "max_depth": 50}}
    spec = validate_spec(raw, LIMITS)
    assert spec.crawl.max_pages == 100 and spec.crawl.max_depth == 2


@pytest.mark.parametrize("raw", [
    {"fields": []},
    {"fields": [{"name": "Bad Name", "type": "string"}]},
    {"fields": [{"name": "org_id", "type": "string"}]},
    {"fields": [{"name": "a", "type": "string"}, {"name": "a", "type": "string"}]},
    {"fields": [{"name": "a", "type": "string"}], "deduplication_keys": ["b"]},
    {"fields": [{"name": "a", "type": "string"}], "unexpected": 1},
    {"fields": [{"name": "a", "type": "nosuchtype"}]},
])
def test_invalid_specs_rejected(raw):
    with pytest.raises(ValidationError):
        ExtractionSpec.model_validate(raw)


def test_industry_is_a_field_people_can_ask_for():
    from app.spec.interpret import interpret

    spec = interpret("Find pharmaceutical companies in the USA with their website and industry")
    (industry,) = [f for f in spec.fields if f.name == "industry"]
    assert industry.semantic == "industry"


def test_in_us_means_the_united_states_but_contact_us_does_not():
    from app.spec.interpret import interpret

    assert interpret("find 50 cybersecurity companies in us").discovery.countries == ["US"]
    assert interpret("find cybersecurity companies in the U.S.").discovery.countries == ["US"]
    assert interpret("find cybersecurity companies and their contact us page").discovery.countries == []
