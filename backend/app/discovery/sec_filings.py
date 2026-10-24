"""sec_filings: companies whose own SEC filings name a technology ("Teamcenter", "SAP S/4HANA").

SEC EDGAR full-text search (efts.sec.gov, free, no key, filings since 2001) finds every filing and exhibit that
contains the product's names. For each company the newest matching document is fetched from sec.gov, the
sentences naming the product are cut out word for word, and each company is judged: user, or vendor, partner,
competitor, integrator, former user. Only users become results; everything else is kept as rejected proof
with its reason. The person sees every piece on the Evidence and Rejected sheets.

SEC's fair-access rules apply: a User-Agent naming the app and a contact, and at most 10 requests a second
(we use about 5).
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import httpx
from sqlalchemy import select

from app.config import get_settings
from app.crawl.urlnorm import homepage, normalize_url, registered_domain
from app.db import session_scope
from app.discovery.providers import DiscoveryError, DiscoveryResult
from app.discovery.sec_edgar import US_STATES, SecEdgarProvider, index_ready, sic_codes_for
from app.discovery.websites import FetchText, WebsiteFinder
from app.evidence.judge import KEEP, USE, Judge, score
from app.evidence.products import Product, product_for
from app.evidence.quotes import document_text, find_mentions, verify_quote
from app.models import SecCompany
from app.search import search_configured
from app.spec.models import ExtractionSpec

SEARCH = "https://efts.sec.gov/LATEST/search-index"
ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
FILING_STRENGTH = 0.85  # the company's own filing: first-party, reviewed, dated
FORM_ORDER = ["10-K", "20-F", "10-Q", "S-1", "8-K", "DEF 14A"]  # the most telling document first
MAX_PAGES = 5
MAX_DOC_BYTES = 25_000_000
GAP = 0.2  # seconds between requests to SEC
RETRY_WAITS = (5.0, 20.0, 60.0)  # seconds before each new try of a failed request
RETRY_STATUS = {429, 500, 502, 503, 504}


def company_name(display: str) -> str:
    """"AVIENT CORP (AVNT) (CIK 0001122976)" -> "AVIENT CORP"."""
    return re.sub(r"\s*\([^)]*\)", "", display).strip()


def document_url(cik: str, hit_id: str) -> str:
    adsh, _, filename = hit_id.partition(":")
    return f"{ARCHIVES}/{int(cik)}/{adsh.replace('-', '')}/{filename}"


# Forms only foreign private issuers file. Their business address on EDGAR is often a US agent's
# ("Grifols SA ... New York, NY"), so the form, not the address, says the company is not a US company.
FOREIGN_FORMS = {"20-F", "40-F", "6-K", "F-1", "F-3", "F-4"}
DOMAIN_RE = re.compile(r"(?<![@\w.-])(?:https?://)?((?:[a-z0-9-]+\.)+(?:com|net|org|io|co|us|biz|info|ai|tech))"
                       r"(?![\w-])", re.I)
NAME_NOISE = {"inc", "corp", "corporation", "co", "company", "companies", "holding", "holdings", "group", "ltd",
              "plc", "sa", "nv", "ag", "se", "llc", "lp", "the", "and", "of", "international", "intl", "de", "del"}


def form_rank(form: str) -> int:
    base = form.split("/")[0]
    return FORM_ORDER.index(base) if base in FORM_ORDER else len(FORM_ORDER)


def website_in(text: str, company: str) -> str:
    """The company's own website as its filing names it ("visit www.celanese.com", "investors.coty.com"):
    the most often named domain whose name carries a word of the company's name. "" when none does, so a
    vendor's or a newswire's domain in the same document is never taken for the company's."""
    words = [w for w in re.findall(r"[a-z0-9]+", company.lower()) if w not in NAME_NOISE]
    compact = "".join(words)
    counts: dict[str, int] = {}
    hosts: dict[str, set[str]] = {}
    for m in DOMAIN_RE.finditer(text):
        host = m.group(1).lower()
        domain = registered_domain(host)
        label = domain.split(".")[0]
        if not label or domain.endswith("sec.gov"):
            continue
        if len(label) >= 3 and (label in compact or any(len(w) >= 3 and w in label for w in words)):
            counts[domain] = counts.get(domain, 0) + 1
            hosts.setdefault(domain, set()).add(host)
    if not counts:
        return ""
    best = max(counts, key=lambda d: (counts[d], -len(d)))
    # The host as written: some sites answer only on www (celanese.com fails TLS, www.celanese.com works).
    # An investor or careers host is not the homepage, so www. is used when only those are named.
    host = best if best in hosts[best] else f"www.{best}"
    return f"https://{host}/"


class SecFilingsProvider:
    name = "sec_filings"

    def __init__(self, client: httpx.AsyncClient | None = None, judge: Judge | None = None,
                 gap: float = GAP) -> None:
        self.client = client
        self.judge = judge or Judge()
        self.gap = gap
        self.retry_waits = RETRY_WAITS if gap else (0.0,) * len(RETRY_WAITS)  # tests pass gap=0: no waiting
        self.notes: list[str] = []
        self.evidence: list[dict[str, Any]] = []  # every piece looked at, kept or rejected
        self.on_note: Callable[..., None] | None = None  # the job's live activity feed, when there is one
        self.fetch_text: FetchText | None = None  # the crawler's own page fetch (robots.txt respected), when run

    def _say(self, kind: str, message: str, url: str | None = None) -> None:
        if self.on_note is not None:
            self.on_note(kind, message, url, source=self.name)

    async def _get(self, client: httpx.AsyncClient, url: str, **params: Any) -> httpx.Response:
        """SEC's search service flakes (timeouts, dropped TLS, HTTP 500) and answers again a minute later, so a
        failed request is tried again after RETRY_WAITS before it counts as a failure."""
        for wait in (*self.retry_waits, None):
            await asyncio.sleep(self.gap)
            try:
                resp = await client.get(url, params=params or None)
                if resp.status_code not in RETRY_STATUS or wait is None:
                    resp.raise_for_status()
                    return resp
            except httpx.TransportError:
                if wait is None:
                    raise
            self._say("failed", f"SEC did not answer ({url.split('/')[2]}); trying again in {wait:.0f}s")
            await asyncio.sleep(wait)
        raise AssertionError("unreachable")

    @staticmethod
    def query(product: Product) -> str:
        """Quoted names, any of them. EDGAR full-text search requires every term separated by a space, so the
        names are joined with OR: '"SAP S/4HANA" "SAP S4HANA"' finds 0 filings, with OR it finds 164."""
        return " OR ".join(f'"{n}"' for n in product.names)

    async def search(self, client: httpx.AsyncClient, product: Product, years: int) -> list[dict[str, Any]]:
        today = date.today()
        params = {"q": self.query(product), "dateRange": "custom",
                  "startdt": (today - timedelta(days=365 * years)).isoformat(), "enddt": today.isoformat()}
        hits: list[dict[str, Any]] = []
        for _ in range(MAX_PAGES):
            body = (await self._get(client, SEARCH, **params, **({"from": len(hits)} if hits else {}))).json()
            page = body.get("hits", {}).get("hits", [])
            hits += page
            total = body.get("hits", {}).get("total", {}).get("value", 0)
            if not page or len(hits) >= total:
                break
        return hits

    @staticmethod
    def best_per_company(hits: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """CIK -> its most telling recent document: an annual report before a quarterly, then the newest."""
        best: dict[str, dict[str, Any]] = {}
        for h in hits:
            src = h.get("_source") or {}
            ciks = src.get("ciks") or []
            if not ciks or ":" not in h.get("_id", ""):
                continue
            cik = ciks[0]
            key = (form_rank(src.get("form", "")), "".join(chr(255 - ord(c)) for c in src.get("file_date", "")))
            if cik not in best or key < best[cik]["_key"]:
                best[cik] = {**h, "_key": key}
        return best

    def _record(self, **kw: Any) -> dict[str, Any]:
        self.evidence.append(kw)
        doc = f"{kw['company']}'s {kw['source_type'].removeprefix('SEC filing ').strip('()')}"
        if kw["kept"]:
            self._say("kept", f"Proof: {doc} ({kw['evidence_date']}) shows it {kw['relationship'].replace('_', ' ')} "
                              f"{kw['product']} ({kw['verdict']}): \"{kw['quote'][:160]}\"", kw["url"])
        else:
            self._say("dropped", f"Rejected {doc}: {kw['reason']}", kw["url"])
        return kw

    async def discover(self, spec: ExtractionSpec) -> list[DiscoveryResult]:
        d = spec.discovery
        if not d.technology:
            raise DiscoveryError("SEC filings search needs a technology to look for")
        if d.countries and "US" not in d.countries:
            raise DiscoveryError("SEC filings cover companies listed in the US; skipped for "
                                 + ", ".join(d.countries))
        product = product_for(d.technology, d.technology_aliases)
        client = self.client or httpx.AsyncClient(timeout=60, follow_redirects=True,
                                                  headers={"User-Agent": get_settings().user_agent})
        try:
            try:
                hits = await self.search(client, product, d.evidence_years)
            except httpx.HTTPError as exc:
                raise DiscoveryError(f"SEC full-text search failed ({type(exc).__name__})") from exc
            companies = self.best_per_company(hits)
            self.notes.append(f"sec_filings: {len(hits)} filing(s) from {len(companies)} companies name "
                              f"{product.name} ({', '.join(product.names[:4])})")
            self._say("search", f"SEC full-text search: {len(hits)} filing(s) from {len(companies)} companies "
                                f"mention {product.name}")
            wanted_sics: set[str] | None = None
            if d.industry and index_ready():
                with session_scope(bypass=True) as db:
                    descriptions = dict(db.execute(select(SecCompany.sic, SecCompany.sic_description).where(
                        SecCompany.sic.is_not(None)).distinct()).all())
                wanted_sics = set(sic_codes_for(d.industry, descriptions))
            elif d.industry:
                self.notes.append("sec_filings: industry not applied (the SEC company list is not downloaded)")
            results: list[DiscoveryResult] = []
            users: dict[str, dict[str, Any]] = {}
            for cik, h in companies.items():
                if len(users) >= d.max_results:
                    break
                src = h["_source"]
                name = company_name((src.get("display_names") or [""])[0]) or f"CIK {cik}"
                url = document_url(cik, h["_id"])
                form = src.get("file_type") or src.get("form") or "filing"
                exhibit = f", {form}" if form != src.get("form") else ""
                source_type = f"SEC filing ({src.get('form', 'filing')}{exhibit})"
                day = src.get("file_date", "")
                base = dict(company=name, product=product.name, url=url, evidence_date=day, source_type=source_type,
                            website="", quote="", relationship="", judged_by="", strength=0.0, verdict="")
                states = set(src.get("biz_states") or [])
                if d.countries and (not states & US_STATES or src.get("form", "").split("/")[0] in FOREIGN_FORMS):
                    self._record(**base, kept=False, reason="business address outside the US")
                    continue
                if wanted_sics is not None and not set(src.get("sics") or []) & wanted_sics:
                    self._record(**base, kept=False, reason=f"not in the {d.industry} industry by its SEC code")
                    continue
                self._say("read", f"Reading {name}'s {form} filed {day}", url)
                try:
                    resp = await self._get(client, url)
                    text = document_text(resp.content[:MAX_DOC_BYTES].decode(resp.encoding or "utf-8", "replace"))
                except httpx.HTTPError as exc:
                    self._record(**base, kept=False, reason=f"filing could not be fetched ({type(exc).__name__})")
                    continue
                quotes = [q for q in find_mentions(text, product) if verify_quote(q, text)]
                if not quotes:
                    self._record(**base, kept=False, reason="the product's name was not found in the document text")
                    continue
                j = await self.judge.judge(name, product, quotes, f"{source_type} filed {day}")
                verdict, strength = score(j.relationship, FILING_STRENGTH, day)
                row = {**base, "quote": j.quote, "relationship": j.relationship, "judged_by": j.judged_by,
                       "strength": strength, "verdict": verdict}
                if j.relationship not in KEEP or not verdict:
                    self._record(**row, kept=False, reason=f"{j.relationship.replace('_', ' ')}"
                                                           + (f": {j.reason}" if j.reason else ""))
                    continue
                users[cik] = self._record(**row, kept=True, reason=j.reason,
                                          headquarters=(src.get("biz_locations") or [""])[0],
                                          named_website=website_in(text, name))
            await self._attach_websites(client, users)
        finally:
            await self.judge.aclose()
            if self.client is None:
                await client.aclose()
        seen: set[str] = set()
        no_site = 0
        for ev in users.values():
            site = ev.get("website")
            if not site:
                no_site += 1
                continue
            domain = registered_domain(site) or site
            if domain in seen:
                continue
            seen.add(domain)
            hint = {"company_name": ev["company"], "headquarters": ev.get("headquarters") or None,
                    "country": "United States", "website_url": site,
                    "uses_technology": ev["verdict"], "evidence": ev["quote"], "evidence_url": ev["url"],
                    "evidence_date": ev["evidence_date"], "evidence_type": ev["source_type"],
                    "_source": ev["url"], "_strength": ev["strength"]}
            results.append(DiscoveryResult(site, "sec_filings", {k: v for k, v in hint.items() if v},
                                           referrer=ev["url"]))
        if no_site:
            self.notes.append(f"sec_filings: {no_site} company(ies) with proof have no known website; they are "
                              "on the Evidence sheet only")
        if not results and not users:
            raise DiscoveryError(f"no US-listed company's filings show it uses {product.name}")
        return results

    async def _attach_websites(self, client: httpx.AsyncClient, users: dict[str, dict[str, Any]]) -> None:
        """Website and a cleaner name for each company: SEC's own company list first, then Wikidata."""
        if not users:
            return
        ciks = [int(c) for c in users]
        known: dict[int, tuple[str, str]] = {}
        with session_scope(bypass=True) as db:
            for c in db.execute(select(SecCompany).where(SecCompany.cik.in_(ciks))).scalars():
                if c.website:
                    known[c.cik] = (c.website, "")
        try:
            wiki = await SecEdgarProvider().from_wikidata(client, [c for c in ciks if c not in known and not
                                                                   users[f"{c:010d}"].get("named_website")])
        except httpx.HTTPError as exc:
            wiki = {}
            self.notes.append(f"sec_filings: Wikidata website lookup failed ({type(exc).__name__})")
        for cik, ev in users.items():
            site, label = known.get(int(cik), ("", ""))
            info = wiki.get(int(cik)) or {}
            # The website the filing itself names comes first: it is the company's own and current, where
            # SEC's company data can be years old (Spectrum Brands' still points at a parked hrggroup.com).
            site = ev.get("named_website") or site or info.get("website", "")
            ev["website"] = homepage(normalize_url(site) or "") if site else ""
            if info.get("label"):
                ev["company"] = info["label"]
        # Neither the filing, SEC's company data nor Wikidata gave one: look the name up, accepting a domain
        # only when the search agrees on it and its homepage names the company.
        missing = [ev for ev in users.values() if not ev["website"]]
        if missing and self.fetch_text is not None and search_configured():
            finder = WebsiteFinder(client, get_settings().searxng_url, self.fetch_text)
            for ev in missing:
                site, how = await finder.find(ev["company"])
                ev["website"] = site
                self._say("search" if site else "skipped", f"Website of {ev['company']}: "
                          + (f"{site} ({how})" if site else f"none taken ({how})"), site or None)


def strongest(evidence: list[dict[str, Any]]) -> dict[str, Any] | None:
    kept = [e for e in evidence if e.get("kept") and e.get("relationship") in USE | {"evaluating", "unreviewed"}]
    return max(kept, key=lambda e: e.get("strength", 0), default=None)
