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


def test_company_names_are_cleaned():
    from app.extract.deterministic import clean_company_name

    assert clean_company_name("Merck & Co., Inc., Rahway, NJ, USA") == "Merck & Co., Inc."
    assert clean_company_name("Amicus Therapeutics | Advancing Therapies to Treat Rare Diseases") == \
        "Amicus Therapeutics"
    assert clean_company_name("BioCryst®") == "BioCryst"
    assert clean_company_name("Home | Acme Ltd", keep="last") == "Acme Ltd"
    assert clean_company_name("Acme, Inc.") == "Acme, Inc."


def test_domain_style_names_lose_to_better_names():
    from app.extract.deterministic import _name_candidate

    assert _name_candidate("JNJ.com", "meta", 0.75, "").confidence < 0.4
    assert _name_candidate("Johnson & Johnson", "meta", 0.75, "").confidence == 0.75


def test_general_contact_mailbox_beats_hr_offsite_and_placeholder_addresses():
    html = """<html><body><footer>
      <a href="mailto:hr.operations@acme.com">Jobs</a> <a href="mailto:drugsafety@distributor.com">Safety</a>
      <p>Write to info@loremacme.com or info@acme.com</p></footer></body></html>"""
    fields = [FieldSpec(name="contact_email", type="email", semantic="contact_email")]
    found = extract_page(parse_page("https://www.acme.com/contact", html), fields)["contact_email"]
    ranked = [c.value for c in sorted(found, key=lambda c: c.confidence, reverse=True)]
    assert ranked[0] == "info@acme.com"
    assert "info@loremacme.com" not in ranked
    assert "drugsafety@distributor.com" not in ranked  # another company's mailbox
    assert "hr.operations@acme.com" not in ranked  # a jobs mailbox is not the company's contact


def test_personal_and_privacy_mailboxes_rank_below_press():
    html = """<html><body><a href="mailto:nicole.shevins@acme.com">x</a> <a href="mailto:gdpr_dpo@acme.com">y</a>
      <a href="mailto:press@acme.com">z</a> <a href="mailto:info-italy@acme.com">w</a></body></html>"""
    fields = [FieldSpec(name="contact_email", type="email", semantic="contact_email")]
    found = extract_page(parse_page("https://acme.com/", html), fields)["contact_email"]
    best = max(found, key=lambda c: c.confidence)
    assert best.value in ("press@acme.com", "info-italy@acme.com")
    scores = {c.value: c.confidence for c in found}
    assert "nicole.shevins@acme.com" not in scores  # one person's inbox
    assert "gdpr_dpo@acme.com" not in scores


def test_legal_jobs_and_report_mailboxes_are_dropped():
    boxes = ["copyrightnotices", "grievanceofficer", "device.registrationservices", "cpg-report", "pandora-jobs",
             "reportabuse", "privacy", "peoplesupport-china", "pkwaremarketing", "partner-program", "contact"]
    html = "<html><body>" + " ".join(f'<a href="mailto:{b}@acme.com">x</a>' for b in boxes) + \
        '<a href="mailto:citrix_ru@acme.com">ru</a></body></html>'
    fields = [FieldSpec(name="contact_email", type="email", semantic="contact_email")]
    found = extract_page(parse_page("https://acme.com/", html), fields)["contact_email"]
    scores = {c.value: c.confidence for c in found}
    assert set(scores) == {"contact@acme.com", "citrix_ru@acme.com"}
    assert scores["citrix_ru@acme.com"] < scores["contact@acme.com"]


def test_a_job_site_s_mailboxes_are_not_the_company_contact():
    fields = [FieldSpec(name="contact_email", type="email", semantic="contact_email")]
    html = '<html><body><a href="mailto:mydelekhr@delekus.com">HR</a></body></html>'
    assert extract_page(parse_page("https://jobs.delekus.com/", html), fields)["contact_email"] == []
    assert extract_page(parse_page("https://www.delekus.com/careers/", html), fields)["contact_email"] == []
    assert extract_page(parse_page("https://www.delekus.com/contact", html), fields)["contact_email"] == []  # hr
    html = '<html><body><a href="mailto:info@delekus.com">Info</a></body></html>'
    assert [c.value for c in extract_page(parse_page("https://www.delekus.com/contact", html),
                                          fields)["contact_email"]] == ["info@delekus.com"]


def test_another_country_s_office_mailbox_is_dropped_when_countries_were_asked_for():
    from app.extract.deterministic import prefer_country_emails

    fields = [FieldSpec(name="contact_email", type="email", semantic="contact_email")]
    html = '<a href="mailto:Media_Au@peabodyenergy.com">AU</a> <a href="mailto:media_us@peabodyenergy.com">US</a>'
    found = extract_page(parse_page("https://www.peabodyenergy.com/contact", html), fields)["contact_email"]
    assert [c.value for c in prefer_country_emails(list(found), ["US"])] == ["media_us@peabodyenergy.com"]
    assert len(prefer_country_emails(list(found), [])) == 2


def test_phones_from_other_countries_are_dropped():
    from app.extract.deterministic import prefer_country_phones

    html = """<html><body><a href="tel:+49 7031 4644">DE</a> <a href="tel:+1 914 499 1900">US</a>
      <a href="tel:1-800-426-4968">toll free</a></body></html>"""
    fields = [FieldSpec(name="phone", type="phone", semantic="phone")]
    found = extract_page(parse_page("https://www.ibm.com/", html), fields)["phone"]
    prefer_country_phones(found, ["US"])
    assert [c.value for c in found] == ["+1 914 499 1900", "+18004264968"]
    unchanged = extract_page(parse_page("https://www.ibm.com/", html), fields)["phone"]
    assert prefer_country_phones(unchanged, []) == unchanged


def test_product_links_skip_calls_to_action_and_icon_text():
    html = """<html><body><nav>
      <a href="/products/falcon">Falcon Insight</a> <a href="/products/all">See all products</a>
      <a href="/products/x">Learn morearrow-right</a> <a href="/products/edr">EDRarrow-right</a></nav></body></html>"""
    fields = [FieldSpec(name="products", type="list", semantic="product_categories")]
    (cand,) = extract_page(parse_page("https://acme.com/", html), fields)["products"]
    assert cand.value == ["Falcon Insight", "EDR"]


def test_a_localized_organization_url_becomes_the_homepage():
    html = """<html><head><script type="application/ld+json">
      {"@type": "Organization", "name": "Acme", "url": "https://www.acme.com/in/"}</script></head></html>"""
    fields = [FieldSpec(name="website_url", type="url", semantic="website_url")]
    cands = extract_page(parse_page("https://www.acme.com/in/", html), fields)["website_url"]
    assert cands[0].value == "https://www.acme.com/"


def test_press_officer_inboxes_and_the_fda_number_are_not_company_contacts():
    html = """<html><body><a href="mailto:KMontag@its.acme.com">Kim</a> <a href="mailto:stacey.brown2@acme.com">S</a>
      <a href="mailto:mediarelations@acme.com">Media</a> <a href="mailto:clinicaltrials@acme.com">Trials</a>
      <a href="mailto:CorporateSecretary@acme.com">Sec</a>
      <a href="tel:1-800-FDA-1088">Report side effects to the FDA</a>
      <a href="tel:+1 908 740 4000">Main</a></body></html>"""
    fields = [FieldSpec(name="contact_email", type="email", semantic="contact_email"),
              FieldSpec(name="phone", type="phone", semantic="phone")]
    found = extract_page(parse_page("https://www.acme.com/news/press-releases/new-drug", html), fields)
    scores = {c.value: c.confidence for c in found["contact_email"]}
    assert set(scores) == {"KMontag@its.acme.com", "mediarelations@acme.com"}
    assert scores["KMontag@its.acme.com"] < 0.6 < scores["mediarelations@acme.com"]
    assert [c.value for c in found["phone"]] == ["+1 908 740 4000"]


def test_local_numbers_are_read_in_the_requested_country_and_extensions_dropped():
    from app.extract.deterministic import prefer_country_phones

    html = """<html><body><a href="tel:9847433522">Mobile</a> <a href="tel:+91 40 67611600 / 700">Office</a>
      </body></html>"""
    fields = [FieldSpec(name="phone", type="phone", semantic="phone")]
    found = extract_page(parse_page("https://www.example.in/", html), fields)["phone"]
    assert [c.value for c in prefer_country_phones(found, ["IN"])] == ["+919847433522", "+91 40 67611600"]


def test_a_press_officer_with_a_middle_initial_is_not_a_contact_but_customer_service_is():
    from app.spec.models import Semantic

    html = ('<html><body><a href="mailto:Kimberly.K.Aguillard@hii.com">Kim</a>'
            '<a href="mailto:customer.service@hii.com">Customer service</a></body></html>')
    doc = parse_page("https://www.hii.com/newsroom", html)
    found = extract_page(doc, [FieldSpec(name="email", type="email", semantic=Semantic.contact_email)])
    assert [c.value for c in found["email"]] == ["customer.service@hii.com"]


def test_a_founding_year_is_taken_only_from_a_sentence_about_the_company():
    from app.spec.models import Semantic

    field = [FieldSpec(name="founded", type="integer", semantic=Semantic.founded_year)]

    def years(url, text):
        return [c.value for c in extract_page(parse_page(url, f"<html><body><p>{text}</p></body></html>"), field)
                ["founded"]]

    # A tenant, a subsidiary on a product page, a partner: not the company's founding.
    assert years("https://www.copt.com/news/lease", "Semmes has deep roots. The firm was founded in 1887 and") \
        == []
    assert years("https://www.lockheedmartin.com/en-us/products/cdl-systems/about-us.html",
                 "Lockheed Martin CDL Systems was founded in 1992 in Salt Lake City.") == []
    assert years("https://www.teledyne.com/stories/oceans",
                 "Nekton, an independent research institute, was established in 2015.") == []
    assert years("https://www.potomac.com/about/", "The e-magazine he founded in 2003 grew.") == []
    # The company itself.
    assert years("https://www.acme.com/about", "Acme was founded in 1916 by two engineers.") == ["1916"]
    assert years("https://www.other.com/", "Since we were founded in 1950, we have built ships.") == ["1950"]
