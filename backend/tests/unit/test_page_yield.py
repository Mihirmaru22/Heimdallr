"""Pages are read in order of how often their kind gives proof, a rate that is data, measured and updated."""

import json

from app.discovery.page_yield import Yields, page_kind


def test_a_page_s_kind_comes_from_general_words_in_its_address_and_title():
    assert page_kind("https://vendor.example/en/case-studies/acme") == "story"
    assert page_kind("https://db.example/customers-database/customers/view/acme") == "story"
    assert page_kind("https://news.example/2021/04/27/acme-goes-live") == "news"
    assert page_kind("https://jobs.example/job/atlanta/plm-lead") == "jobs"
    assert page_kind("https://partner.example/blog/ten-tips") == "article"
    assert page_kind("https://partner.example/netsuite/", "NetSuite Implementation Partner UK") == "offer"
    assert page_kind("https://acme.example/about") == "other"


def test_yields_start_from_the_measured_seed_and_learn_from_every_run(tmp_path):
    y = Yields(tmp_path / "page_yield.json")
    assert y.rate("story") > y.rate("news") > y.rate("article") > y.rate("offer")  # the seed's measured order
    before = y.rate("offer")
    for _ in range(50):
        y.record("offer", True)  # a run where service pages kept giving proof
    y.save()
    again = Yields(tmp_path / "page_yield.json")
    assert again.rate("offer") > before and json.loads((tmp_path / "page_yield.json").read_text())["offer"]["read"] > 50
    assert again.rate("never-seen") == 0.5  # a kind no run has seen starts at one half
