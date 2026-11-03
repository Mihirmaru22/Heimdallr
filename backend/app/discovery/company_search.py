"""company_search: proof asked for by name, for each company the question could deliver that has none yet.

The other sources start from the product and read whatever pages name it; a customer whose story search never
ranked is missed (34 of 67 missed users were never a candidate, 2026-10-30), yet one search for
'"<company>" "<product>"' found a page naming both for 22 of 22 of them. So once the sources are done, each
company already listed with a country the question asks for (an industry list, a registry, a product page that
named it without proving it) gets that one free search; with no industry to list companies by, the country's
most-linked businesses on Wikidata are the list. Only results whose title, snippet or address name both the
company and the product are read, best kind of page first, at most READS_PER_COMPANY of them, and only proof
about that company counts for it. Companies a registry places elsewhere, or whose country is unknown, are not
searched, and the list is capped (MAX_COMPANIES), so the cost is bounded before the pass starts.
"""

from __future__ import annotations

from itertools import zip_longest
from typing import Any

import httpx

from app.config import get_settings
from app.crawl.urlnorm import normalize_url, registered_domain
from app.discovery.case_studies import CaseStudiesProvider, candidate_key
from app.discovery.page_yield import Yields, page_kind
from app.discovery.providers import NOT_COMPANY_SITES, DiscoveryResult, WikidataProvider
from app.discovery.relevance import country_iso
from app.discovery.websites import names_company
from app.evidence.products import Product, product_for
from app.search import LOOKUP, SearchError, SearchHub, search_configured
from app.spec.models import ExtractionSpec

MAX_COMPANIES = 150  # companies searched per job, in the sources' own order
LARGEST = 100  # with no industry: the country's most-linked businesses taken as the list
BUSINESSES = ["Q4830453", "Q6881511", "Q783794", "Q891723"]  # business, enterprise, company, public company
READS_PER_COMPANY = 2  # pages read per company, best first; reading stops at the first proof about it
PROVEN = ("Confirmed", "Likely")
PROOF_KEYS = ("uses_technology", "evidence", "evidence_url", "evidence_date", "evidence_type")


def about(found: str, company: str) -> bool:
    """A proof row is about the company searched for: either name carries the other's distinctive words."""
    return names_company(found, company) or names_company(company, found)


def candidates(groups: list[list[DiscoveryResult]], countries: list[str]) -> list[DiscoveryResult]:
    """Named companies in the countries asked for and without proof yet, taken from the sources in turn (as the
    crawl queue is), one per name, at most MAX_COMPANIES."""
    out: list[DiscoveryResult] = []
    seen: set[str] = set()
    proven = {str(r.hint.get("company_name", "")).casefold() for g in groups for r in g
              if r.hint.get("uses_technology") in PROVEN}
    for r in (r for group in zip_longest(*groups) for r in group if r is not None):
        name = str(r.hint.get("company_name") or "").strip()
        key = name.casefold()
        if not name or r.method == "seed" or key in seen or key in proven:
            continue
        if country_iso(r.hint.get("country")) not in countries:
            continue  # elsewhere, or not known: not chased
        seen.add(key)
        out.append(r)
        if len(out) >= MAX_COMPANIES:
            break
    return out


class CompanySearch(CaseStudiesProvider):
    """Reads pages like the case-study source (same rules, same model reading, same Evidence rows), but for one
    named company at a time."""

    name = "company_search"
    what = "pages naming a company and the product"
    open_ended = False

    def __init__(self, client: httpx.AsyncClient | None = None, judge=None, searxng_url: str | None = None) -> None:
        super().__init__(client, judge, searxng_url)
        self.listed: list[list[DiscoveryResult]] = []  # the other sources' results, set by the crawler
        self.searched = 0
        self.proven = 0

    async def discover(self, spec: ExtractionSpec) -> list[DiscoveryResult]:
        if self.fetch_page is None or not search_configured(self.searxng_url):
            return []
        own = self.client is None
        # Search and Wikidata are asked directly (the self-hosted SearXNG is local), as by the case-study source.
        self.client = self.client or httpx.AsyncClient(timeout=30, headers={"User-Agent": get_settings().user_agent})
        try:
            d = spec.discovery
            groups = list(self.listed)
            if not d.industry and get_settings().company_search_largest:
                groups.append(await self.largest(spec))
            return await self.prove(spec, candidates(groups, list(d.countries)))
        finally:
            if own:
                await self.client.aclose()
                self.client = None

    def pages_for(self, hits: list, company: str, product: Product) -> list[str]:
        """The results that name both the company and the product, best kind of page first."""
        out: list[str] = []
        for hit in hits:
            url = normalize_url(hit.url)
            site = registered_domain(url) if url else ""
            if not url or not site or site in NOT_COMPANY_SITES or url in out:
                continue
            said = f"{hit.title} {hit.snippet} {url.replace('-', ' ').replace('/', ' ')}"
            if names_company(said, company) and product.mentioned_in(said):
                self.meta.setdefault(url, (hit.title or "", hit.snippet or ""))
                self.order.setdefault(url, len(self.order))
                out.append(url)
        self.yields = self.yields or Yields()
        return sorted(out, key=lambda u: (-self.yields.rate(page_kind(u, self.meta[u][0])), self.order[u]))

    async def largest(self, spec: ExtractionSpec) -> list[DiscoveryResult]:
        """The country's most-linked businesses with a website on Wikidata (no industry filter). Organisations in
        general were mostly universities, museums and clubs (GB, 2026-11-03)."""
        d = spec.discovery
        listed = spec.model_copy(update={"discovery": d.model_copy(update={"max_results": LARGEST})})
        try:
            return await WikidataProvider(self.client)._via_search(self.client, [], listed, BUSINESSES)
        except Exception as exc:  # noqa: BLE001 - a missing starting list costs this pass, never the job
            self.notes.append(f"{self.name}: no list of the country's largest companies ({type(exc).__name__})")
            return []

    async def prove(self, spec: ExtractionSpec, companies: list[DiscoveryResult]) -> list[DiscoveryResult]:
        """Each company's search and best pages; returns the companies proven, as results carrying their proof
        (the listing source's facts kept)."""
        d = spec.discovery
        product = product_for(d.technology, d.technology_aliases)
        self.countries = list(d.countries)
        self.hub = self.hub or SearchHub.from_settings(self.client, self.searxng_url)
        name = ([n for n in product.names if len(n) > 4] or product.names)[0]
        self._say("search", f"Searching {len(companies)} listed companies one by one for {product.name}")
        pages_read: dict[str, list[dict[str, Any]]] = {}  # a page several companies' searches give is read once
        out: list[DiscoveryResult] = []
        stop = "every listed company was searched"
        try:
            for r in companies:
                if self._over_budget():
                    stop = "the reading budget was reached"
                    break
                if self.judge.unavailable:
                    stop = f"no model to read pages ({self.judge.unavailable})"
                    break
                company = str(r.hint["company_name"])
                try:
                    hits = await self.hub.search(f'"{company}" "{name}"', kind=LOOKUP)
                except SearchError as exc:
                    stop = f"web search failed ({exc})"
                    break
                self.searched += 1
                best: dict[str, Any] | None = None
                for url in self.pages_for(hits, company, product)[:READS_PER_COMPANY]:
                    key = candidate_key(url)
                    if key not in pages_read:
                        rows, fetched = await self._read_one(url, product, step="company_read")
                        if fetched and self.yields is not None:
                            self.yields.record(page_kind(url, self.meta.get(url, ("", ""))[0]), bool(rows))
                        pages_read[key] = rows
                    mine = [row for row in pages_read[key] if about(row["company"], company)]
                    best = max([best, *mine] if best else mine, key=lambda row: row["strength"], default=None)
                    if best and best["verdict"] in PROVEN:
                        break
                if best and best["verdict"] in PROVEN and (best["verdict"] != r.hint.get("uses_technology")
                                                            or best["strength"] > r.hint.get("_strength", 0)):
                    out.append(self._proven(r, company, best))
        finally:
            await self.judge.aclose()
        self.proven = len(out)
        self.notes.append(f"{self.name}: {self.searched} of {len(companies)} listed companies searched, "
                          f"{len(pages_read)} page(s) read, {len(out)} proven; stopped: {stop}")
        self._say("search", f"Company search: {len(out)} of {self.searched} companies searched have proof")
        return out

    def _proven(self, r: DiscoveryResult, company: str, row: dict[str, Any]) -> DiscoveryResult:
        hint = {k: v for k, v in r.hint.items() if k not in PROOF_KEYS and not k.startswith("_")}
        if r.hint.get("_country_by"):
            hint["_country_by"] = r.hint["_country_by"]
        elif r.method in ("wikidata", "sec_edgar", "gleif", "sec_filings") and r.hint.get("country"):
            # The country is still the registry's, though this source found the proof.
            hint["_country_by"] = f"registry: {r.method}: listed by {r.method}"
        hint.update({"company_name": company, "uses_technology": row["verdict"], "evidence": row["quote"],
                     "evidence_url": row["url"], "evidence_date": row["evidence_date"],
                     "evidence_type": row["source_type"], "_source": row["url"], "_strength": row["strength"]})
        return DiscoveryResult(r.url, self.name, {k: v for k, v in hint.items() if v}, referrer=row["url"])
