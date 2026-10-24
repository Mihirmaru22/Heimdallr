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
    def __init__(self, client: httpx.AsyncClient, searxng_url: str, fetch_text: FetchText) -> None:
        self.client = client
        self.searxng_url = searxng_url.rstrip("/")
        self.fetch_text = fetch_text

    async def search(self, query: str) -> list[str]:
        resp = await self.client.get(f"{self.searxng_url}/search", params={
            "q": query, "format": "json", "pageno": 1, "language": "en", "safesearch": 1})
        if resp.status_code != 200:
            return []
        return [r.get("url", "") for r in resp.json().get("results", [])[:TOP]]

    async def find(self, company: str) -> tuple[str, str]:
        """(homepage, how it was confirmed) or ("", why not)."""
        if not self.searxng_url:
            return "", "web search is not configured"
        if not name_words(company):
            return "", "the name has no distinctive word"
        try:
            urls = await self.search(f"{company} official website")
        except httpx.HTTPError as exc:
            return "", f"web search failed ({type(exc).__name__})"
        domains = [registered_domain(u) for u in urls if normalize_url(u)]
        domains = [d for d in domains if d and d not in NOT_COMPANY_SITES]
        if not domains:
            return "", "web search found nothing"
        best, n = Counter(domains).most_common(1)[0]
        if n < AGREE:
            return "", f"web search results disagree ({', '.join(dict.fromkeys(domains))})"
        if not domain_fits(best, company):
            return "", f"{best} does not carry the company's name"
        url = homepage(next(u for u in urls if registered_domain(u) == best))
        text = await self.fetch_text(url)
        if text is None:
            return "", f"{best}'s homepage could not be read"
        if not names_company(text, company):
            return "", f"{best}'s homepage does not name {company}"
        return url, f"web search ({n} of the top {len(urls)} results) and its homepage names it"
