"""A company's website from its name, when no source gave one.

Measured on S/4HANA filers with proof but no website (SEC's company data and Wikidata had none): a web search
for the name returns the company's own domain on every top result when the name is distinctive (Accuray,
CommScope), and five different companies when it is not ("Vertex"). So a domain is taken only when:
- most of the top results agree on it,
- its name carries a word of the company's name,
- and its homepage, fetched like any page (robots.txt respected), names the company.
Anything less leaves the company without a website rather than with someone else's.

Agreement is counted per brand, not per exact domain: enersys.com, enersys.com.pl and enersys.de are one company's
sites (set 1 lost EnerSys as "results disagree"). A homepage is tried over https, with and without www, before it
counts as unreadable (SRAM's search result was http://sram.com/, which answers 404). When the most common brand's
homepage does not name the company (GRS Building Supplies vs grs.com), the next brands that carry the name are
tried, each still needing its homepage to name the company.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Awaitable, Callable

import httpx

from app.crawl.urlnorm import _extract, homepage, normalize_url, registered_domain
from app.discovery.providers import NOT_COMPANY_SITES
from app.search import LOOKUP, SearchError, SearchHub

NAME_NOISE = {"inc", "corp", "corporation", "co", "company", "companies", "holding", "holdings", "group", "ltd",
              "plc", "sa", "nv", "ag", "se", "llc", "lp", "the", "and", "of", "international", "intl", "de", "del",
              "gmbh", "limited", "pvt", "private"}
TOP = 5  # search results considered
AGREE = 3  # of them on one brand
MAX_BRANDS = 3  # brands whose homepage is checked, most agreed first

FetchText = Callable[[str], Awaitable[str | None]]  # a page's visible text, or None when it cannot be read


def name_words(company: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", company.lower()) if w not in NAME_NOISE]


def domain_fits(domain: str, company: str) -> bool:
    """"accuray.com" fits "ACCURAY INC"; "bloomberg.com" does not."""
    label = domain.split(".")[0]
    words = name_words(company)
    return len(label) >= 3 and (label in "".join(words) or any(len(w) >= 3 and w in label for w in words))


def brand(domain: str) -> str:
    """"enersys" for enersys.com, enersys.com.pl and www.enersys.de."""
    return _extract(domain).domain.lower() or domain


def homepage_variants(url: str) -> list[str]:
    """The homepage over https, with and without www, then as found."""
    from urllib.parse import urlsplit

    p = urlsplit(url)
    host = (p.hostname or "").removeprefix("www.")
    path = p.path or "/"
    return list(dict.fromkeys([f"https://{host}{path}", f"https://www.{host}{path}", url]))


def names_company(text: str, company: str) -> bool:
    """The page says the company's name: its distinctive words together, as written ("CommScope")."""
    words = [w for w in name_words(company) if len(w) >= 3]
    if not words:
        return False
    flat = re.sub(r"[^a-z0-9]+", "", text.lower())
    return "".join(words) in flat or all(re.search(rf"\b{re.escape(w)}\b", text, re.I) for w in words)


class WebsiteFinder:
    def __init__(self, client: httpx.AsyncClient, searxng_url: str, fetch_text: FetchText,
                 hub: SearchHub | None = None) -> None:
        self.client = client
        self.hub = hub or SearchHub.from_settings(client, searxng_url)
        self.fetch_text = fetch_text

    async def search(self, query: str) -> list[str]:
        return [h.url for h in (await self.hub.search(query, kind=LOOKUP))[:TOP]]

    async def find(self, company: str) -> tuple[str, str]:
        """(homepage, how it was confirmed) or ("", why not)."""
        if not self.hub.configured:
            return "", "web search is not configured"
        if not name_words(company):
            return "", "the name has no distinctive word"
        try:
            urls = await self.search(f"{company} official website")
        except SearchError as exc:
            return "", str(exc)
        found = [(u, registered_domain(u)) for u in urls if normalize_url(u)]
        found = [(u, d) for u, d in found if d and d not in NOT_COMPANY_SITES]
        if not found:
            return "", "web search found nothing"
        brands = Counter(brand(d) for _u, d in found)
        ranked = [(b, n) for b, n in brands.most_common()]
        words = [w for w in name_words(company) if len(w) >= 3]

        def whole_name(b: str) -> bool:  # "grsbuildingsupplies" for "GRS Building Supplies"
            return len(words) >= 2 and all(w in b for w in words)

        # The agreed brand first. After it, brands seen twice or carrying the whole name; without an agreed brand
        # only the latter, since a one-word name ("Vertex") spreads over many companies' sites. Every one still
        # needs its homepage to name the company.
        agreed = [(b, k) for b, k in ranked[:1] if k >= AGREE]
        ranked = agreed + [(b, k) for b, k in ranked
                           if (b, k) not in agreed and (whole_name(b) or (agreed and k >= 2))]
        if not ranked:
            return "", f"web search results disagree ({', '.join(dict.fromkeys(d for _u, d in found))})"
        why = ""
        for b, k in ranked[:MAX_BRANDS]:
            domains = [d for _u, d in found if brand(d) == b]
            domain = Counter(domains).most_common(1)[0][0]
            if not domain_fits(domain, company):
                why = why or f"{domain} does not carry the company's name"
                continue
            first = next(u for u, d in found if d == domain)
            for url in homepage_variants(homepage(first)):
                text = await self.fetch_text(url)
                if text is not None:
                    break
            else:
                why = why or f"{domain}'s homepage could not be read"
                continue
            if not names_company(text, company):
                why = why or f"{domain}'s homepage does not name {company}"
                continue
            return url, f"web search ({k} of the top {len(urls)} results) and its homepage names it"
        return "", why
