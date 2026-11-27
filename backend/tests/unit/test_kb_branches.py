"""Unit tests for multi-branch extraction, plain-text postal addresses, local phones, emails, and Overture."""

from __future__ import annotations

from app.extract.deterministic import (
    _addresses,
    _emails,
    addresses_from_text,
    emails_from_text,
    parse_page,
    phones_from_text,
)
from app.kb import branches


def test_addresses_extracts_all_branches_from_jsonld_lists_and_places():
    html = """<html><head>
    <script type="application/ld+json">{
      "@context": "https://schema.org",
      "@type": "Organization",
      "name": "Acme Corp",
      "location": [
        {
          "@type": "Place",
          "address": {
            "streetAddress": "1 Canada Square",
            "addressLocality": "London",
            "postalCode": "E14 5AA",
            "addressCountry": "GB"
          }
        },
        {
          "@type": "Place",
          "address": {
            "streetAddress": "300 California St",
            "addressLocality": "San Francisco",
            "addressRegion": "CA",
            "postalCode": "94104",
            "addressCountry": "US"
          }
        }
      ]
    }</script></head><body></body></html>"""
    cands = _addresses(parse_page("https://acme.com/locations", html), "address")
    vals = [c.value for c in cands]
    assert any("1 Canada Square" in v and "E14 5AA" in v for v in vals)
    assert any("300 California St" in v and "94104" in v for v in vals)


def test_addresses_from_text_handles_multiple_branches_without_year_or_street_noise():
    text = """
    Founding in 2027 Building Tomorrow
    Head Office: 100 Market Street, Suite 200, San Francisco, CA 94105
    UK Office: 75-77 Margaret Street, London W1W 8SY
    Mumbai Plant: Plot 14, Veer Savarkar Marg, Prabhadevi, Mumbai - 400025
    Ignore copyright 2026 Acme Ltd
    """
    got = addresses_from_text(text)
    addrs = [x["address"] for x in got]
    assert any("San Francisco, CA 94105" in a for a in addrs)
    assert any("London W1W 8SY" in a for a in addrs)
    assert any("400025" in a for a in addrs)
    assert not any("2027" in a or "2026" in a for a in addrs)


def test_local_phones_decoded_using_country_hint_and_skip_dates():
    text = "NYC (212) 664-4444 Updated 2026-11-26"
    assert phones_from_text(text, countries=["US"]) == [{"phone": "+12126644444", "method": "regex_local"}]
    assert phones_from_text("Call 020 7946 0958", countries=["GB"]) == [
        {"phone": "+442079460958", "method": "regex_local"}
    ]


def test_cfemail_and_expanded_role_emails_recovered():
    key = 0x1A
    encoded = f"{key:02x}" + "".join(f"{ord(c) ^ key:02x}" for c in "info@acme.com")
    html = f"<html><body><a data-cfemail='{encoded}'>[email protected]</a></body></html>"
    found = [c.value for c in _emails(parse_page("https://acme.com/contact", html))]
    assert "info@acme.com" in found

    plain = "Write connect@acme.com or ask@acme.com or jane.doe@acme.com"
    assert [e["email"] for e in emails_from_text(plain, "acme.com")] == ["connect@acme.com", "ask@acme.com"]


def test_overture_formatting_skips_placeholder_aq_and_builds_branch_row():
    bad = {"freeform": None, "locality": None, "postcode": None, "country": "AQ"}
    assert branches.format_overture_address(bad) is None
    fmt = branches.format_overture_address({
        "freeform": "230 Fifth Ave Suite 510",
        "locality": "New York",
        "region": "NY",
        "postcode": "10001",
        "country": "US",
    })
    assert fmt == ("230 Fifth Ave Suite 510, New York, NY, 10001, US", "New York", "NY", "10001", "US")
    assert branches.extract_domain_candidates("https://stores.acme.co.uk/nyc") == ["stores.acme.co.uk", "acme.co.uk"]
