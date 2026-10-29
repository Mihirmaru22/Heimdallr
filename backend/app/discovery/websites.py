"""A company's website from its name, when no source gave one.

Measured on S/4HANA filers with proof but no website (SEC's company data and Wikidata had none): a web search
for the name returns the company's own domain on every top result when the name is distinctive (Accuray,
CommScope), and five different companies when it is not ("Vertex"). So a domain is taken only when:
- most of the top results agree on it,
- its name carries a word of the company's name,
- and its homepage, fetched like any page (robots.txt respected), names the company.
Anything less leaves the company without a website rather than with someone else's.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Awaitable, Callable

import httpx

from app.crawl.urlnorm import homepage, normalize_url, registered_domain
from app.discovery.providers import NOT_COMPANY_SITES
from app.search import LOOKUP, SearchError, SearchHub

NAME_NOISE = {"inc", "corp", "corporation", "co", "company", "companies", "holding", "holdings", "group", "ltd",
              "plc", "sa", "nv", "ag", "se", "llc", "lp", "the", "and", "of", "international", "intl", "de", "del",
              "gmbh", "limited", "pvt", "private"}
TOP = 5  # search results considered
AGREE = 3  # of them on one domain

FetchText = Callable[[str], Awaitable[str | None]]  # a page's visible text, or None when it cannot be read


def name_words(company: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", company.lower()) if w not in NAME_NOISE]


def domain_fits(domain: str, company: str) -> bool:
    """"accuray.com" fits "ACCURAY INC"; "bloomberg.com" does not."""
    label = domain.split(".")[0]
    words = name_words(company)
    return len(label) >= 3 and (label in "".join(words) or any(len(w) >= 3 and w in label for w in words))


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

    async def _homepage_text(self, url: str) -> tuple[str, str | None]:
        """(the homepage address that answered, its text). A search result's address is not always the one a
        site serves: "http://sram.com/" answers 404 where "https://www.sram.com/" is the site."""
        host = url.split("://", 1)[-1].split("/", 1)[0]
        bare = host.removeprefix("www.")
        tried: list[str] = []
        for candidate in (url, f"https://{host}/", f"https://www.{bare}/", f"https://{bare}/"):
            if candidate in tried:
                continue
            tried.append(candidate)
            text = await self.fetch_text(candidate)
            if text is not None:
                return candidate, text
        return url, None

    async def _pick(self, company: str, query: str) -> tuple[str | None, str, int, int]:
        """(homepage of the domain most results agree on, why, agreeing results, results) for one search."""
        try:
            urls = await self.search(query)
        except SearchError as exc:
            return None, str(exc), 0, 0
        pairs = [(u, registered_domain(u)) for u in urls if normalize_url(u)]
        pairs = [(u, d) for u, d in pairs if d and d not in NOT_COMPANY_SITES]
        if not pairs:
            return None, "web search found nothing", 0, len(urls)
        # One company's country sites (enersys.com, enersys.com.pl) agree with each other: they are counted by
        # the brand name in front of the suffix, and the address search gave most often stands for them.
        brands = Counter(d.split(".")[0] for _u, d in pairs)
        brand, n = brands.most_common(1)[0]
        domains = Counter(d for _u, d in pairs if d.split(".")[0] == brand)
        best = domains.most_common(1)[0][0]
        if n < AGREE:
            return None, f"web search results disagree ({', '.join(dict.fromkeys(d for _u, d in pairs))})", n, len(urls)
        if not domain_fits(best, company):
            return None, f"{best} does not carry the company's name", n, len(urls)
        return homepage(next(u for u, d in pairs if d == best)), best, n, len(urls)

    async def find(self, company: str, context: str = "", unverified_ok: bool = False) -> tuple[str, str]:
        """(homepage, how it was confirmed) or ("", why not).

        `context` (the place asked for) is added to a second search when the first one does not settle it.
        `unverified_ok`: for a company that already has proof, a homepage that cannot be read does not cost its
        website when search agrees on it and its domain carries the name; the reason says it was not verified."""
        if not self.hub.configured:
            return "", "web search is not configured"
        if not name_words(company):
            return "", "the name has no distinctive word"
        queries = [f"{company} official website"]
        if context:
            queries.append(f"{company} {context} official website")
        why = ""
        for query in queries:
            url, best, n, total = await self._pick(company, query)
            if url is None:
                why = best
                continue
            url, text = await self._homepage_text(url)
            if text is None:
                if unverified_ok:
                    return url, (f"web search ({n} of the top {total} results) and the name in its domain; "
                                 "its homepage could not be read, so it is not verified")
                why = f"{best}'s homepage could not be read"
                continue
            if not names_company(text, company):
                why = f"{best}'s homepage does not name {company}"
                continue
            return url, f"web search ({n} of the top {total} results) and its homepage names it"
        return "", why
