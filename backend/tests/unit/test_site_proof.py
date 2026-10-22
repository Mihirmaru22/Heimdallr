"""Proof on a company's own pages: dated when the page says when, and judged like any other proof."""

import json

from app.evidence.judge import Judge, proof_confidence
from app.evidence.site import MAX_JUDGED_PER_SITE, SiteProof, page_date
from app.extract.deterministic import parse_page
from app.llm.openrouter import Reply
from app.spec.models import ExtractionSpec

SPEC = ExtractionSpec.model_validate({"fields": [{"name": "company_name", "type": "string"}],
                                      "discovery": {"technology": "Teamcenter"}})


class Router:
    def __init__(self, relationship="uses"):
        self.relationship, self.calls = relationship, 0

    async def chat(self, messages, **_kw):
        self.calls += 1
        return Reply(json.dumps({"relationship": self.relationship, "quote": 1, "reason": "its own PLM"}),
                     "minimax/minimax-m3.1-flash:free")

    async def aclose(self):
        pass


def page(body, head="", url="https://initech.com/careers"):
    return parse_page(url, f"<html><head><title>T</title>{head}</head><body><p>{body}</p></body></html>")


def test_page_dates_come_from_the_page_itself():
    assert page_date(page("x", '<meta property="article:published_time" content="2025-06-01T08:00:00Z">')) \
        == "2025-06-01"
    ld = '<script type="application/ld+json">{"@type": "NewsArticle", "datePublished": "2024-02-03"}</script>'
    assert page_date(page("x", ld)) == "2024-02-03"
    assert page_date(page("x")) == ""


async def test_a_page_naming_the_product_is_judged_and_a_proven_site_is_not_judged_again():
    router = Router()
    proof = SiteProof(SPEC, Judge(router))
    piece = await proof.check(page("Teamcenter holds the product data of every Initech truck."), "initech.com",
                              "Initech")
    assert piece["kept"] and piece["verdict"] == "Confirmed" and piece["source_type"] == "Company website"
    assert piece["quote"] == "Teamcenter holds the product data of every Initech truck."
    assert await proof.check(page("Teamcenter again."), "initech.com", "Initech") is None
    assert router.calls == 1
    assert await proof.check(page("Nothing about it."), "other.com", "Other") is None


async def test_the_makers_own_site_is_a_vendor_and_judging_stops_after_a_few_pages():
    router = Router("other_mention")
    proof = SiteProof(SPEC, Judge(router))
    vendor = await proof.check(page("Teamcenter is our PLM software."), "siemens.com", "")
    assert not vendor["kept"] and vendor["relationship"] == "vendor" and router.calls == 0
    for _ in range(MAX_JUDGED_PER_SITE + 2):
        await proof.check(page("A Teamcenter webinar."), "acme.com", "Acme")
    assert router.calls == MAX_JUDGED_PER_SITE
    await proof.check(page("We make brakes."), "plain.com", "Plain Co")
    why = {r["company"]: r["reason"] for r in proof.without_proof({"plain.com": "Plain Co"})}
    assert why["Plain Co"] == "none of the 1 page(s) read names Teamcenter; no job board linked from the site"
    assert why["acme.com"].startswith(f"{MAX_JUDGED_PER_SITE} of {MAX_JUDGED_PER_SITE + 2} page(s) read name")


def test_a_confirmed_piece_beats_a_mention_whatever_its_source():
    assert proof_confidence("Confirmed", 0.8) > proof_confidence("Likely", 0.85) > proof_confidence("Mentioned", 0.4)
