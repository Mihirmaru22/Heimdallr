"""A website from a company's name: taken only when the search agrees and the homepage names the company."""

import httpx

from app.discovery.websites import WebsiteFinder, domain_fits, names_company


def finder(urls, pages):
    def search(request):
        return httpx.Response(200, json={"results": [{"url": u} for u in urls]})

    async def fetch_text(url):
        return pages.get(url)

    return WebsiteFinder(httpx.AsyncClient(transport=httpx.MockTransport(search)), "http://searx", fetch_text)


async def test_a_distinctive_name_is_found_and_checked_on_its_homepage():
    urls = ["https://www.accuray.com/", "https://www.accuray.com/about/", "https://www.accuray.com/x",
            "https://en.wikipedia.org/wiki/Accuray", "https://www.accuray.com/contact"]
    site, how = await finder(urls, {"https://www.accuray.com/": "Accuray | Radiation therapy"}).find("ACCURAY INC")
    assert site == "https://www.accuray.com/" and "homepage names it" in how


async def test_a_generic_name_or_an_unconfirmed_homepage_gives_no_website():
    vertex = ["https://www.vertexinc.com/", "https://www.vertex.com/", "https://www.vrtx.com/",
              "https://vertexhomes.com/", "https://www.vertexinc.com/a"]
    assert (await finder(vertex, {}).find("Vertex, Inc."))[0] == ""
    same = ["https://www.acme.com/"] * 5
    site, why = await finder(same, {"https://www.acme.com/": "Road runner supplies"}).find("Acme Holdings Inc")
    assert site == "" and "does not name" in why
    assert (await finder(same, {}).find("Acme Holdings Inc"))[1].endswith("could not be read")


def test_name_checks():
    assert domain_fits("commscope.com", "CommScope Holding Company, Inc.")
    assert not domain_fits("bloomberg.com", "CommScope Holding Company, Inc.")
    assert names_company("Welcome to CommScope", "CommScope Holding Company, Inc.")
    assert not names_company("Welcome to Vistance", "CommScope Holding Company, Inc.")


async def test_one_brand_on_several_domains_agrees_and_its_homepage_is_tried_over_https_and_www():
    urls = ["http://enersys.com/", "https://www.enersys.com.pl/", "https://www.enersys.de/",
            "https://www.ensercorp.com/", "https://www.enersys.com/en/"]
    pages = {"https://www.enersys.com/": "EnerSys | Stored energy solutions"}
    site, how = await finder(urls, pages).find("EnerSys")
    assert site == "https://www.enersys.com/" and "homepage names it" in how


async def test_when_the_agreed_domain_is_another_company_the_next_one_carrying_the_name_is_checked():
    urls = ["https://www.grs.com/", "https://www.grs.com/a", "https://www.grs.com/b",
            "https://www.grsbuildingsupplies.co.uk/", "https://www.yell.com/grs"]
    pages = {"https://grs.com/": "GRS Roadstone", "https://grsbuildingsupplies.co.uk/":
             "GRS Building Supplies, builders merchant in Kent"}
    site, _how = await finder(urls, pages).find("GRS Building Supplies")
    assert site == "https://grsbuildingsupplies.co.uk/"
