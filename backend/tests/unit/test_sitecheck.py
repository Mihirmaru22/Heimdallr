"""Web-search results that only mention the industry (lists, associations, suppliers) are told apart from companies."""

import json

from app.crawl.urlnorm import homepage
from app.discovery.sitecheck import SiteChecker, listing_reason
from app.extract.deterministic import parse_page
from app.llm.openrouter import LLMUnavailable, Reply
from app.spec.models import ExtractionSpec


def page(title, body="We make medicines.", url="https://www.example-pharma.com/"):
    return parse_page(url, f"<html><head><title>{title}</title></head><body><p>{body}</p></body></html>")


SPEC = ExtractionSpec.model_validate({"entity": "company", "fields": [{"name": "company_name", "type": "string"}],
                                      "discovery": {"providers": ["searxng"], "industry": "pharmaceutical"}})


class Router:
    def __init__(self, answer=None, error=None):
        self.answer, self.error, self.calls = answer, error, 0

    async def chat(self, messages, **_kw):
        self.calls += 1
        if self.error:
            raise self.error
        return Reply(json.dumps(self.answer), "minimax/minimax-m3.1-flash:free")

    async def aclose(self):
        pass


def test_listing_and_association_titles_are_caught_by_rules():
    for title in ("Top Pharma Companies in India 2026", "Indian Drug Manufacturers' Association",
                  "Pharma Suppliers in Gujarat - B2B Marketplace"):
        assert listing_reason(page(title)), title
    # Borderline names go to the model instead: these are real companies.
    for title in ("Lupin | Pharmaceutical Company", "Alliance Pharma plc", "Divi's Laboratories"):
        assert listing_reason(page(title)) is None, title


async def test_the_model_drops_a_supplier_and_keeps_a_drug_maker():
    supplier = Router({"kind": "service_provider", "in_industry": False, "reason": "makes cellulose for pharma"})
    reason, by = await SiteChecker(supplier).check(page("Ankit Pulps & Boards"), SPEC)
    assert reason == "not a pharmaceutical company (service provider: makes cellulose for pharma)"
    assert by == "model:minimax/minimax-m3.1-flash:free"

    maker = Router({"kind": "company", "in_industry": True, "reason": "makes generic medicines"})
    assert (await SiteChecker(maker).check(page("Lupin"), SPEC))[0] is None


async def test_without_a_model_sites_are_kept_and_the_model_is_not_asked_again():
    router = Router(error=LLMUnavailable("no OpenRouter key is configured"))
    checker = SiteChecker(router)
    assert await checker.check(page("Acme"), SPEC) == (None, "unchecked: no OpenRouter key is configured")
    assert (await checker.check(page("Beta"), SPEC))[0] is None and router.calls == 1
    # A reply that does not fit is not a reason to drop a site either.
    assert (await SiteChecker(Router({"kind": "planet"})).check(page("Gamma"), SPEC))[0] is None


def test_a_registry_link_to_an_inner_page_becomes_the_homepage():
    assert homepage("http://www.oushadhi.org/category.php?slug=") == "http://www.oushadhi.org/"
    assert homepage("https://www.neulandlabs.com/en") == "https://www.neulandlabs.com/en"
    assert homepage("https://www.acme.com/products/drugs/") == "https://www.acme.com/"
    assert homepage("https://www.acme.com/") == "https://www.acme.com/"
