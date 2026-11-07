"""The maker's own customer stories and press releases, listed from its sitemaps: which hosts, which pages."""

import asyncio

from app.discovery.vendor_archive import VendorArchiveProvider, choose, keep, names_product, page_key
from app.evidence.products import product_for
from app.search import Hit

WINDCHILL = product_for("Windchill")


def test_stories_and_product_releases_are_kept_from_the_address_alone():
    assert keep("https://www.ptc.com/en/case-studies/welbilt-lower-tco-rapid-mass-customization", WINDCHILL)
    assert keep("https://investor.ptc.com/news-releases/news-release-details/cummins-inc-selects-ptcs-windchill-plm",
                WINDCHILL)
    # A release about something else, a product page and a job ad are not candidates.
    assert not keep("https://investor.ptc.com/news-releases/news-release-details/ptc-reports-q3-results", WINDCHILL)
    assert not keep("https://www.ptc.com/en/products/windchill/features", WINDCHILL)
    assert not keep("https://www.ptc.com/en/careers/jobs/windchill-consultant", WINDCHILL)
    assert names_product("https://x.example/news/2010/Raytheon-Selects-PTC-Windchill", WINDCHILL)


def test_language_copies_are_kept_once_and_stories_naming_the_product_come_first():
    urls = ["https://www.ptc.com/de/case-studies/hp-minimizes-complexity",
            "https://www.ptc.com/en/case-studies/hp-minimizes-complexity",
            "https://www.ptc.com/case-studies/hp-minimizes-complexity",
            "https://investor.ptc.com/news-releases/raytheon-windchill",
            "https://www.ptc.com/en/case-studies/polaris-windchill-rollout"]
    assert page_key(urls[0]) == page_key(urls[1]) == page_key(urls[2])
    assert choose(urls, WINDCHILL) == ["https://www.ptc.com/en/case-studies/polaris-windchill-rollout",
                                       "https://www.ptc.com/case-studies/hp-minimizes-complexity",
                                       "https://investor.ptc.com/news-releases/raytheon-windchill"]


class FakeHub:
    def __init__(self, hits):
        self.hits, self.queries, self.problems = hits, [], {}

    async def search(self, query, page=1, kind="general"):
        self.queries.append(query)
        return self.hits


def test_the_makers_hosts_come_from_search_results_and_their_sitemaps_are_followed_story_files_first():
    hub = FakeHub([Hit("https://investor.ptc.com/news-releases/x", "PTC news", "", "fake"),
                   Hit("https://www.ptc.com/en/products/windchill", "Windchill", "", "fake"),
                   Hit("https://www.spkaa.com/windchill-guide", "Guide", "", "fake")])  # a partner: not the maker
    files = {
        "https://www.ptc.com/sitemap-index.xml": "<sitemapindex><sitemap><loc>https://www.ptc.com/sitemap-products.xml"
            "</loc></sitemap><sitemap><loc>https://www.ptc.com/sitemap-case-studies.xml</loc></sitemap>"
            "<sitemap><loc>https://www.ptc.com/sitemap-old.xml.gz</loc></sitemap></sitemapindex>",
        "https://www.ptc.com/sitemap-case-studies.xml": "<urlset><url><loc>https://www.ptc.com/en/case-studies/"
            "welbilt-lower-tco</loc></url></urlset>",
        "https://www.ptc.com/sitemap-products.xml": "<urlset><url><loc>https://www.ptc.com/en/products/creo</loc>"
            "</url></urlset>",
        "https://investor.ptc.com/sitemap.xml": "<urlset><url><loc>https://investor.ptc.com/news-releases/"
            "cummins-selects-ptcs-windchill</loc></url><url><loc>https://investor.ptc.com/news-releases/q3-results"
            "</loc></url></urlset>",
    }
    fetched = []

    async def fetch_xml(url):
        fetched.append(url)
        return files.get(url)

    async def sitemaps_of(origin):
        return ["https://www.ptc.com/sitemap-index.xml"] if origin == "https://www.ptc.com" else []

    p = VendorArchiveProvider()
    p.hub, p.fetch_xml, p.sitemaps_of = hub, fetch_xml, sitemaps_of
    urls = asyncio.run(p.search(None, WINDCHILL))

    assert set(p.hosts) == {"investor.ptc.com", "www.ptc.com"}
    assert urls == ["https://www.ptc.com/en/case-studies/welbilt-lower-tco",
                    "https://investor.ptc.com/news-releases/cummins-selects-ptcs-windchill"]
    # The story sitemap was read before the products one, and the compressed one was never asked for.
    assert fetched.index("https://www.ptc.com/sitemap-case-studies.xml") < fetched.index(
        "https://www.ptc.com/sitemap-products.xml")
    assert not any(u.endswith(".gz") for u in fetched)
    assert "2 kept as stories or product releases" in p.notes[-1]


def test_no_maker_site_in_search_means_no_candidates_and_a_note_saying_so():
    p = VendorArchiveProvider()
    p.hub = FakeHub([Hit("https://www.spkaa.com/windchill-guide", "Guide", "", "fake")])
    assert asyncio.run(p.search(None, WINDCHILL)) == []
    assert "no site of Windchill's maker" in p.notes[-1]


def test_the_maker_is_recognised_from_the_products_own_names():
    from app.discovery.vendor_archive import maker_site

    assert maker_site("ptc.com", WINDCHILL)  # "PTC Windchill" is one of its names
    assert maker_site("oracle.com", product_for("NetSuite")) and maker_site("netsuite.co.uk", product_for("NetSuite"))
    assert maker_site("veeva.com", product_for("Veeva Vault"))
    assert not maker_site("spkaa.com", WINDCHILL)
