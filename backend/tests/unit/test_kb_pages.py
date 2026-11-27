"""Finding a company's contact and careers pages from its homepage links."""

from __future__ import annotations

from app.kb import pages


def test_contact_and_careers_links_are_picked_from_the_homepage():
    links = [("https://acme.com/about", "About us"), ("https://acme.com/kontakt", "Kontakt"),
             ("https://acme.com/contact-us/form?x=1", "Write to us"), ("https://other.com/contact", "Contact"),
             ("https://acme.com/news", "News"), ("https://boards.greenhouse.io/acme", "Open roles")]
    assert pages.choose_links(links, "acme.com") == {"contact": "https://acme.com/kontakt",
                                                      "careers": "https://boards.greenhouse.io/acme"}
    assert pages.choose_links([("https://www.acme.com/careers", "Careers")], "acme.com") == {
        "careers": "https://www.acme.com/careers"}
    assert pages.choose_links([("https://acme.com/blog", "Blog")], "acme.com") == {}


def test_job_ads_are_links_to_single_positions():
    links = [("https://acme.com/careers", "All jobs"), ("https://acme.com/careers/data-engineer-123", "Data Engineer"),
             ("https://acme.com/careers/sre-9", "SRE"), ("https://acme.com/careers/x-1", "Third"),
             ("https://acme.com/about", "About")]
    assert pages.job_links(links, "https://acme.com/careers") == ["https://acme.com/careers/data-engineer-123",
                                                                  "https://acme.com/careers/sre-9"]


def test_page_keeps_title_text_and_company_mailbox():
    html = ("<html><head><title>Contact Acme</title></head><body><p>Acme Ltd, 1 High St, London, +44 20 7946 0958</p>"
            "<a href='mailto:info@acme.com'>info</a><a href='mailto:jane.doe@acme.com'>Jane</a>"
            "<a href='tel:+442079460958'>Call</a><a href='/careers'>Careers</a></body></html>")
    page, links = pages.page_from("acme.com", "contact", "https://acme.com/contact", html)
    assert page.title == "Contact Acme" and "1 High St" in page.text
    assert [e["email"] for e in page.emails] == ["info@acme.com"]
    assert [p["phone"] for p in page.phones] == ["+442079460958"]
    assert ("https://acme.com/careers", "Careers") in links


def test_security_and_trust_links_are_picked_without_matching_privacy():
    links = [
        ("https://acme.com/privacy", "Privacy Policy"),
        ("https://acme.com/terms", "Terms"),
        ("https://other.com/security", "Security"),
        ("https://www.vanta.com/", "Powered by Vanta"),
        ("https://acme.com/security", "Security"),
        ("https://acme.com/security/overview", "Security Overview"),
    ]
    assert pages.choose_links(links, "acme.com") == {"security": "https://acme.com/security"}
    assert pages.choose_links(
        [("https://app.vanta.com/acme/trust/abc123", "Trust")], "acme.com"
    ) == {"security": "https://app.vanta.com/acme/trust/abc123"}
    assert pages.choose_links(
        [("https://trust.acme.com", "Trust")], "acme.com"
    ) == {"security": "https://trust.acme.com"}


def test_security_page_keeps_longer_compliance_text():
    long_body = ("A" * 5000) + " Audited for SOC 2 Type II and ISO 27001 compliance."
    html = f"<html><head><title>Security</title></head><body><p>{long_body}</p></body></html>"
    page, _ = pages.page_from("acme.com", "security", "https://acme.com/security", html)
    assert "SOC 2 Type II" in page.text and len(page.text) <= pages.SECURITY_TEXT_CHARS


def test_locations_links_are_picked_and_contact_text_allows_16k():
    links = [
        ("https://acme.com/store", "Online Store"),
        ("https://acme.com/locations", "Our Locations"),
        ("https://acme.com/contact", "Contact Us"),
    ]
    assert pages.choose_links(links, "acme.com") == {
        "contact": "https://acme.com/contact",
        "locations": "https://acme.com/locations",
    }
    long_body = ("X" * 6000) + " Head Office: 100 Market Street, San Francisco, CA 94105"
    html = f"<html><body><p>{long_body}</p></body></html>"
    page, _ = pages.page_from("acme.com", "locations", "https://acme.com/locations", html)
    assert "San Francisco, CA 94105" in page.text and len(page.text) <= pages.CONTACT_TEXT_CHARS


def test_page_reader_recovers_contact_link_from_sitemap(monkeypatch):
    import asyncio

    import httpx

    from app.crawl import fetcher

    monkeypatch.setattr(fetcher, "check_url", lambda url, resolver=None: None)

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/robots.txt":
            return httpx.Response(200, text="Sitemap: https://acme.com/sitemap.xml",
                                  headers={"content-type": "text/plain"})
        if path == "/sitemap.xml":
            xml = "<urlset><url><loc>https://acme.com/contact</loc></url></urlset>"
            return httpx.Response(200, text=xml, headers={"content-type": "application/xml"})
        if path == "/":
            return httpx.Response(200, text="<html><body><div id='root'></div></body></html>",
                                  headers={"content-type": "text/html"})
        if path == "/contact":
            return httpx.Response(200, text="<html><body><a href='mailto:info@acme.com'>Mail</a></body></html>",
                                  headers={"content-type": "text/html"})
        return httpx.Response(404)

    async def run():
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        read = pages.page_reader(client, "heimdallr-test")
        found, miss = await read("acme.com", "https://acme.com/")
        await client.aclose()
        return found, miss

    found, miss = asyncio.run(run())
    assert miss == ""
    assert [p.kind for p in found] == ["contact"]
    assert found[0].emails == [{"email": "info@acme.com", "method": "mailto"}]
