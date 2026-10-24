"""case_studies: organisations that a vendor's customer story, a partner's case study or a news article shows
using a technology.

Where a company never names its software itself (no SEC filing, nothing on its own site), the maker often does:
"Volkswagen standardised on Teamcenter" is on the vendor's customer stories, an implementation partner's case
studies and the trade press. Those pages are found by web search (the self-hosted SearXNG) for the product's
names next to "case study", "customer story" and "success story"; no list of vendors or sites is kept. Each page
is fetched like any crawled page (robots.txt respected), its sentences naming the product are cut out word for
word, and one free model call says who published it and which organisations it shows using the product
(app.evidence.thirdparty). Every customer is then looked up for its website, which is crawled for contact
details like any other result. Pages that show nobody are kept as rejected proof with the reason.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.config import get_settings
from app.crawl.urlnorm import normalize_url, registered_domain
from app.discovery.providers import NOT_COMPANY_SITES, DiscoveryError, DiscoveryResult
from app.discovery.websites import WebsiteFinder
from app.evidence.judge import Judge, score
from app.evidence.products import Product, product_for
from app.evidence.quotes import find_mentions, verify_quote
from app.evidence.thirdparty import MAX_SENTENCES, STRENGTH, read_page
from app.extract.deterministic import PageDoc
from app.spec.models import ExtractionSpec

PHRASES = ("case study", "customer story", "success story")
MAX_PAGES = 30  # pages read per run: one model call each
SEARCH_PAGES = 2  # result pages per query
SOURCE_TYPES = {"vendor": "Vendor case study", "partner": "Partner case study", "customer": "Customer's own page",
                "news": "News article", "other": "Web page"}

FetchPage = Callable[[str], Awaitable[PageDoc | None]]


def page_date(doc: PageDoc) -> str:
    """The page's own publication date (YYYY-MM-DD) from its metadata, or "" when it gives none."""
    for key in ("article:published_time", "article:modified_time", "date", "dc.date"):
        m = re.match(r"\d{4}-\d{2}-\d{2}", doc.meta.get(key, ""))
        if m:
            return m.group()
    for item in doc.jsonld:
        for key in ("datePublished", "dateModified"):
            value = item.get(key)
            m = re.match(r"\d{4}-\d{2}-\d{2}", value if isinstance(value, str) else "")
            if m:
                return m.group()
    return ""


class CaseStudiesProvider:
    name = "case_studies"
    what = "case studies and customer stories"  # what the pages are, in notes and the live feed

    def __init__(self, client: httpx.AsyncClient | None = None, judge: Judge | None = None,
                 searxng_url: str | None = None) -> None:
        self.client = client
        self.judge = judge or Judge()
        self.searxng_url = (searxng_url if searxng_url is not None else get_settings().searxng_url).rstrip("/")
        self.notes: list[str] = []
        self.evidence: list[dict[str, Any]] = []
        self.on_note: Callable[..., None] | None = None
        self.fetch_page: FetchPage | None = None  # set by the crawler: robots.txt respected, network rules checked
        self.dates: dict[str, str] = {}  # url -> date the search source gives, when the page itself gives none

    def _say(self, kind: str, message: str, url: str | None = None) -> None:
        if self.on_note is not None:
            self.on_note(kind, message, url, source=self.name)

    @staticmethod
    def queries(product: Product) -> list[str]:
        names = [n for n in product.names if len(n) > 4][:2] or product.names[:1]
        return [f'"{n}" "{p}"' for n in names for p in PHRASES]

    async def search(self, client: httpx.AsyncClient, product: Product) -> list[str]:
        urls: list[str] = []
        for query in self.queries(product):
            for page in range(1, SEARCH_PAGES + 1):
                try:
                    resp = await client.get(f"{self.searxng_url}/search", params={
                        "q": query, "format": "json", "pageno": page, "language": "en", "safesearch": 1})
                except httpx.HTTPError as exc:
                    if urls:
                        return urls
                    raise DiscoveryError(f"SearXNG is not reachable ({type(exc).__name__})") from None
                if resp.status_code != 200:
                    break
                found = [r.get("url", "") for r in resp.json().get("results", [])]
                if not found:
                    break
                for u in found:
                    url = normalize_url(u)
                    site = registered_domain(url) if url else ""
                    if url and site and site not in NOT_COMPANY_SITES and url not in urls:
                        urls.append(url)
                await asyncio.sleep(1.0 if get_settings().env != "test" else 0)
        return urls

    def _record(self, **kw: Any) -> dict[str, Any]:
        self.evidence.append(kw)
        if kw["kept"]:
            self._say("kept", f"Proof: {kw['source_type'].lower()} shows {kw['company']} "
                              f"{kw['relationship'].replace('_', ' ')} {kw['product']} ({kw['verdict']}): "
                              f"\"{kw['quote'][:160]}\"", kw["url"])
        else:
            self._say("dropped", f"Rejected {kw['url']}: {kw['reason']}", kw["url"])
        return kw

    async def discover(self, spec: ExtractionSpec) -> list[DiscoveryResult]:
        d = spec.discovery
        if not d.technology:
            raise DiscoveryError(f"{self.what} are searched for a technology")
        if not self.searxng_url:
            raise DiscoveryError(f"{self.what} need web search (to find each customer's website); SearXNG is "
                                 "not configured, skipped")
        if self.fetch_page is None:
            raise DiscoveryError(f"{self.what} are read by the crawler; skipped outside a crawl")
        product = product_for(d.technology, d.technology_aliases)
        client = self.client or httpx.AsyncClient(timeout=30, headers={"User-Agent": get_settings().user_agent})
        users: dict[str, dict[str, Any]] = {}
        try:
            urls = await self.search(client, product)
            self._say("search", f"{len(urls)} page(s) found among {product.name} {self.what}; reading up to "
                                f"{MAX_PAGES}")
            self.notes.append(f"{self.name}: {len(urls)} candidate page(s), {min(len(urls), MAX_PAGES)} read")
            for url in urls[:MAX_PAGES]:
                base = dict(company=registered_domain(url), product=product.name, url=url, evidence_date="",
                            source_type="Web page", website="", quote="", relationship="", judged_by="",
                            strength=0.0, verdict="")
                self._say("read", f"Reading {url}", url)
                doc = await self.fetch_page(url)
                if doc is None:
                    self._record(**base, kept=False, reason="page could not be read (robots.txt, error or no text)")
                    continue
                text = f"{doc.title} {doc.text}"
                sentences = [q for q in find_mentions(doc.text, product, limit=MAX_SENTENCES)
                             if verify_quote(q, doc.text)]
                if not sentences:
                    self._record(**base, kept=False, reason="the product's name is not on the page")
                    continue
                found, why = await read_page(self.judge, product, doc.title, sentences, text, url)
                day = page_date(doc) or self.dates.get(url, "")
                if not found:
                    self._record(**{**base, "evidence_date": day, "quote": sentences[0]}, kept=False, reason=why)
                    if self.judge.unavailable:  # nothing more can be read this run
                        self.notes.append(f"{self.name}: stopped reading pages ({self.judge.unavailable})")
                        break
                    continue
                for f in found:
                    verdict, strength = score(f.relationship, STRENGTH[f.publisher], day)
                    row = {**base, "company": f.customer, "evidence_date": day, "quote": f.quote,
                           "source_type": SOURCE_TYPES[f.publisher], "relationship": f.relationship,
                           "judged_by": f.judged_by, "strength": strength, "verdict": verdict}
                    if not verdict:
                        self._record(**row, kept=False, reason=f.relationship.replace("_", " "))
                        continue
                    kept = self._record(**row, kept=True, reason=f"named by a {f.publisher} page")
                    key = f.customer.lower()
                    if key not in users or kept["strength"] > users[key]["strength"]:
                        users[key] = kept
            finder = WebsiteFinder(client, self.searxng_url, self._text)
            results: list[DiscoveryResult] = []
            seen: set[str] = set()
            for ev in sorted(users.values(), key=lambda e: -e["strength"])[:d.max_results]:
                site, how = await finder.find(ev["company"])
                ev["website"] = site
                self._say("search" if site else "skipped", f"Website of {ev['company']}: "
                          + (f"{site} ({how})" if site else f"none taken ({how})"), site or None)
                domain = registered_domain(site) if site else ""
                if not domain or domain in seen:
                    continue
                seen.add(domain)
                hint = {"company_name": ev["company"], "website_url": site, "uses_technology": ev["verdict"],
                        "evidence": ev["quote"], "evidence_url": ev["url"], "evidence_date": ev["evidence_date"],
                        "evidence_type": ev["source_type"], "_source": ev["url"], "_strength": ev["strength"]}
                results.append(DiscoveryResult(site, self.name, {k: v for k, v in hint.items() if v},
                                               referrer=ev["url"]))
        finally:
            await self.judge.aclose()
            if self.client is None:
                await client.aclose()
        missing = len(users) - len(results)
        if missing > 0:
            self.notes.append(f"{self.name}: {missing} customer(s) with proof have no confirmed website; they "
                              "are on the Evidence sheet only")
        if not results:
            raise DiscoveryError(f"none of the {self.what} showed an organisation using {product.name}")
        return results

    async def _text(self, url: str) -> str | None:
        doc = await self.fetch_page(url) if self.fetch_page else None
        return f"{doc.title} {doc.text}" if doc else None
