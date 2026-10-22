"""Website code as proof: a product's own fingerprint on the company's pages, never a guess."""

import json

import httpx

from app.evidence.fingerprints import Fingerprints, detect, parse_rule, rule_file
from app.evidence.products import product_for
from app.evidence.site import SiteProof
from app.extract.deterministic import parse_page
from app.spec.models import ExtractionSpec

RULES = {
    "HubSpot": {"cats": [32], "html": ["<!-- Start of Async HubSpot"], "scriptSrc": ["\\.hs-scripts\\.com/"],
                "js": {"_hsq": ""}},
    "Hotjar": {"cats": [10], "cookies": {"_hjSessionUser": ""}, "scriptSrc": ["static\\.hotjar\\.com\\;confidence:50"]},
    "Hugo": {"cats": [57], "meta": {"generator": "Hugo ([\\d.]+)?\\;version:\\1"}},
    "HAProxy": {"cats": [64], "headers": {"via": "haproxy"}},
}
HUBSPOT_PAGE = ('<html><head><title>Acme</title><script src="https://js.hs-scripts.com/123.js"></script></head>'
                "<body><p>Acme builds tools.</p></body></html>")


def rules_dir(tmp_path):
    (tmp_path / "h.json").write_text(json.dumps(RULES))
    return tmp_path


def site_spec(tech):
    return ExtractionSpec.model_validate({"entity": "company", "fields": [
        {"name": "company_name", "type": "string", "semantic": "company_name", "required": True}],
        "discovery": {"providers": ["wikidata"], "industry": "software", "technology": tech}})


def test_rule_files_and_patterns():
    assert rule_file("HubSpot") == "h" and rule_file("1C") == "_"
    rule = parse_rule("Hugo", RULES["Hugo"])
    page = parse_page("https://x.com/", '<html><head><meta name="generator" content="Hugo 0.120"></head></html>')
    assert "Hugo 0.120" in detect(rule, page, [])


def test_each_kind_of_trace_is_found_and_only_a_full_match_counts():
    page = parse_page("https://acme.com/", HUBSPOT_PAGE)
    assert detect(parse_rule("HubSpot", RULES["HubSpot"]), page, []).startswith(
        "the page loads the script https://js.hs-scripts.com/123.js")
    hotjar = parse_rule("Hotjar", RULES["Hotjar"])
    half = parse_page("https://a.com/", '<script src="https://static.hotjar.com/c/hotjar.js"></script>')
    assert detect(hotjar, half, []) == ""  # one 50% pattern is not enough
    cookie = [("set-cookie", "_hjSessionUser_1=secret-value; Path=/")]
    assert detect(hotjar, half, [("set-cookie", "_hjSessionUser=abc")]) != ""
    assert detect(hotjar, half, cookie) == ""  # the cookie name must match exactly
    seen = detect(hotjar, half, [("set-cookie", "_hjSessionUser=secret-value")])
    assert "secret-value" not in seen  # cookie values are never quoted
    via = detect(parse_rule("HAProxy", RULES["HAProxy"]), half, [("via", "1.1 haproxy")])
    assert "haproxy" in via


async def test_rules_are_found_by_the_products_names_only(tmp_path):
    f = Fingerprints(rules_dir(tmp_path))
    assert [r.name for r in await f.rules_for(product_for("hubspot", []))] == ["HubSpot"]
    assert await f.rules_for(product_for("Hubble Suite", [])) == []
    assert "no known trace" in f.note


async def test_rules_are_downloaded_once_and_a_failed_download_is_reported(tmp_path):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json=RULES)

    f = Fingerprints(tmp_path / "rules", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await f.rules_for(product_for("HubSpot", []))
    assert await f.rules_for(product_for("HubSpot", []))
    assert len(calls) == 1 and calls[0].endswith("/h.json")
    down = Fingerprints(tmp_path / "none")  # the test URL refuses connections
    assert await down.rules_for(product_for("HubSpot", [])) == []
    assert "could not be downloaded" in down.note


async def test_the_site_check_keeps_confirmed_proof_from_the_code_without_a_model(tmp_path):
    proof = SiteProof(site_spec("HubSpot"), fingerprints=Fingerprints(rules_dir(tmp_path)))
    page = parse_page("https://acme.com/", HUBSPOT_PAGE)
    piece = await proof.check_code(page, [], "acme.com", "Acme")
    assert piece["kept"] and piece["verdict"] == "Confirmed" and piece["source_type"] == "Website code"
    assert piece["judged_by"] == "fingerprint:HubSpot" and "hs-scripts.com" in piece["quote"]
    assert "acme.com" in proof.proven
    assert await proof.check_code(page, [], "acme.com", "Acme") is None  # proven: not checked again
    plain = parse_page("https://b.com/", "<html><body><p>Nothing here.</p></body></html>")
    for _ in range(5):
        assert await proof.check_code(plain, [], "b.com", "B") is None
    assert proof.fingerprinted["b.com"] == 3
