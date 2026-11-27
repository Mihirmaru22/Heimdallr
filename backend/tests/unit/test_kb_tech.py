"""Tests for passive tech fingerprinting, compliance standards, DNS MX/TXT rules, and job-ad tech."""

from __future__ import annotations

import json

from app.kb import tech


def test_detect_compliance_matches_explicit_standards_only():
    hits = {m.tech for m in tech.detect_compliance(
        "Acme is SOC 2 Type II and ISO/IEC 27001 certified, HIPAA compliant, and PCI-DSS validated. "
        "We also obey GDPR cookie rules."
    )}
    assert {"SOC 2", "ISO 27001", "HIPAA", "PCI DSS"} <= hits
    assert "GDPR" not in hits  # only explicit compliance phrasing counts, not generic banner text
    assert "GDPR" in {m.tech for m in tech.detect_compliance("Our platform is GDPR compliant.")}


def test_dns_matches_mx_txt_and_spf():
    matches = tech.dns_matches_from_records(
        ["aspmx.l.google.com.", "mxa-001.pphosted.com."],
        ["atlassian-domain-verification=abc", "v=spf1 include:_spf.google.com include:sendgrid.net ~all"],
    )
    by_src = {(m.tech, m.source): m.category for m in matches}
    assert by_src[("Google Workspace", "dns_mx")] == "Email hosting"
    assert by_src[("Proofpoint", "dns_mx")] == "Email security"
    assert by_src[("Atlassian", "dns_txt")] == "Collaboration"
    assert by_src[("SendGrid", "dns_txt")] == "Email delivery"


def test_tech_index_scans_html_headers_and_job_ads(tmp_path):
    tdir = tmp_path / "technologies"
    tdir.mkdir(parents=True)
    (tmp_path / "categories.json").write_text(json.dumps({
        "10": {"name": "Analytics"},
        "22": {"name": "Web servers"},
        "31": {"name": "CDN"},
        "62": {"name": "PaaS"},
    }))
    for ch in "abcdefghijklmnopqrstuvwxyz_":
        (tdir / f"{ch}.json").write_text("{}")
    (tdir / "h.json").write_text(json.dumps({
        "HubSpot": {"cats": [10], "scriptSrc": ["js\\.hs-scripts\\.com"]},
    }))
    (tdir / "c.json").write_text(json.dumps({
        "Cloudflare": {"cats": [31], "headers": {"server": "^cloudflare$"}},
    }))
    (tdir / "k.json").write_text(json.dumps({
        "Kubernetes": {"cats": [62], "headers": {"x-k8s": "1"}},
    }))

    idx = tech.TechIndex.load(tmp_path)
    html = "<html><body><script src='https://js.hs-scripts.com/12.js'></script>SOC 2 certified</body></html>"
    found = {(m.tech, m.source) for m in idx.scan_page("https://acme.com/", html, [("server", "cloudflare")])}
    assert ("HubSpot", "webappanalyzer") in found
    assert ("Cloudflare", "webappanalyzer") in found
    assert ("SOC 2", "compliance") in found

    jobs = {m.tech for m in idx.scan_job_text("We deploy microservices on Kubernetes clusters.")}
    assert "Kubernetes" in jobs
    assert idx.scan_job_text("Kuberneteser is not a match.") == []


def test_required_literal_never_drops_mandatory_tokens():
    assert tech._required_literal(r"https?://js\.hs-scripts\.com/\d+\.js") == "://js.hs-scripts.com/"
    assert tech._required_literal(r"(?:foo|bar)\.cdn\.net") == ".cdn.net"
    assert tech._required_literal(r"\x3cscript/vendor\.js") == "script/vendor.js"
    assert tech._required_literal(r"foo|bar") is None


def test_phones_from_text_validates_dedups_and_filters_third_party():
    from app.extract.deterministic import phones_from_text

    text = (
        "Call London +44 20 7946 0958 or +44 (0) 20 7946 0958, NYC +1 212-664-4444. "
        "Report to FDA +1-800-332-1088. Ignore version +1 2020 2025 or +1234567."
    )
    got = phones_from_text(text)
    assert got == [
        {"phone": "+442079460958", "method": "regex"},
        {"phone": "+12126644444", "method": "regex"},
    ]
