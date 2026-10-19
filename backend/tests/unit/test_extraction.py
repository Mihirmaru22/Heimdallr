from app.extract.deterministic import extract_page, parse_page
from app.extract.normalize import InvalidValue, normalize_value
from app.extract.records import PageCandidates, assemble_record, dedupe_key
from app.spec.models import ExtractionSpec, FieldSpec

HTML = """<!doctype html><html><head><title>Acme Security | Home</title>
<meta name="description" content="Managed detection and response.">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Organization","name":"Acme Security Ltd",
"url":"https://acme.example/","email":"hello@acme.example","telephone":"+44 20 7946 0958","foundingDate":"2014",
"sameAs":["https://www.linkedin.com/company/acme-example"]}</script></head>
<body><a href="/contact">Contact</a><p>Write to sales@acme.example or call +44 20 7946 0959.</p>
<script>var x = "hidden@script.example";</script></body></html>"""

SPEC = ExtractionSpec.model_validate({"entity": "company", "deduplication_keys": ["company_name"], "fields": [
    {"name": "company_name", "type": "string", "semantic": "company_name", "required": True},
    {"name": "website_url", "type": "url", "semantic": "website_url"},
    {"name": "contact_email", "type": "email", "semantic": "contact_email"},
    {"name": "phone", "type": "phone", "semantic": "phone"},
    {"name": "founded_year", "type": "integer", "semantic": "founded_year"},
    {"name": "social_links", "type": "list", "semantic": "social_links"},
    {"name": "description", "type": "text", "semantic": "description"},
    {"name": "ceo", "type": "string"},
]})


def _record(html=HTML, url="https://acme.example/"):
    doc = parse_page(url, html)
    cands = extract_page(doc, SPEC.fields)
    return assemble_record(SPEC, [PageCandidates("p1", url, cands)])


def test_structured_data_preferred_and_values_normalized():
    rec = _record()
    assert rec.data["company_name"] == "Acme Security Ltd"
    assert rec.data["contact_email"] == "hello@acme.example"
    assert rec.data["phone"] == "+442079460958"
    assert rec.data["founded_year"] == 2014
    assert "https://www.linkedin.com/company/acme-example" in rec.data["social_links"]
    assert rec.status == "valid"


def test_missing_field_is_not_invented():
    rec = _record()
    ceo = next(f for f in rec.fields if f.name == "ceo")
    assert rec.data["ceo"] is None
    assert ceo.value_status in ("absent", "not_extracted")


def test_script_contents_are_not_extracted():
    rec = _record()
    all_values = str(rec.data)
    assert "hidden@script.example" not in all_values


def test_provenance_recorded():
    rec = _record()
    name = next(f for f in rec.fields if f.name == "company_name")
    assert name.source_url == "https://acme.example/" and name.method and name.evidence


def test_dedupe_key_normalizes_company_suffixes():
    a = dedupe_key(SPEC, {"company_name": "Acme Security Ltd"}, "x")
    b = dedupe_key(SPEC, {"company_name": "ACME Security, Ltd."}, "y")
    assert a == b
    assert dedupe_key(SPEC, {"company_name": None}, "site.example") == "src:site.example"


def test_normalize_rejects_bad_values():
    import pytest

    with pytest.raises(InvalidValue):
        normalize_value(FieldSpec(name="e", type="email"), "not-an-email")
    with pytest.raises(InvalidValue):
        normalize_value(FieldSpec(name="u", type="url"), "javascript:alert(1)")
    with pytest.raises(InvalidValue):
        normalize_value(FieldSpec(name="n", type="integer"), "twelve")
    assert normalize_value(FieldSpec(name="n", type="number"), "1,234.5") == 1234.5
