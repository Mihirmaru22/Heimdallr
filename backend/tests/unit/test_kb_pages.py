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
    html = ("<html><head><title>Contact Acme</title></head><body><p>Acme Ltd, 1 High St, London</p>"
            "<a href='mailto:info@acme.com'>info</a><a href='mailto:jane.doe@acme.com'>Jane</a>"
            "<a href='/careers'>Careers</a></body></html>")
    page, links = pages.page_from("acme.com", "contact", "https://acme.com/contact", html)
    assert page.title == "Contact Acme" and "1 High St" in page.text
    assert [e["email"] for e in page.emails] == ["info@acme.com"]
    assert ("https://acme.com/careers", "Careers") in links
