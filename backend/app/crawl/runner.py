"""The crawl of one job: seed the frontier, fetch eligible pages, extract candidates per page.

Progress is checkpointed in Postgres after every page, so a crashed worker resumes where it
stopped. No database transaction is held open while a page is being fetched.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import time
import uuid
from datetime import timedelta
from itertools import zip_longest
from typing import Any

from selectolax.lexbor import LexborHTMLParser as HTMLParser
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.crawl.fetcher import DOCUMENT_TYPES, Fetcher, FetchError
from app.crawl.netguard import BlockedDestination, check_url, make_client
from app.crawl.politeness import LocalPoliteness, RedisPoliteness
from app.crawl.robots import RobotsCache
from app.crawl.urlnorm import (
    homepage,
    host_of,
    looks_like_page,
    normalize_url,
    registered_domain,
    url_hash,
)
from app.db import session_scope, utcnow
from app.discovery.providers import DiscoveryError, providers_for
from app.discovery.relevance import (
    COUNTRY_UNKNOWN,
    IN_COUNTRY,
    NOT_CHECKED,
    OUTSIDE_COUNTRY,
    country_status,
    off_topic_reason,
    pages_country,
    unreadable,
)
from app.discovery.sitecheck import SiteChecker
from app.evidence.judge import proof_confidence
from app.evidence.site import SiteProof
from app.extract.deterministic import (
    PageDoc,
    extract_page,
    parse_page,
    prefer_country_emails,
    prefer_country_phones,
)
from app.extract.normalize import InvalidValue, normalize_value
from app.extract.records import CONTACT_HINTS, _has_extractor
from app.models import (
    CompanyFact,
    CrawlJob,
    CrawlJobEvent,
    DiscoveredUrl,
    DomainPolicy,
    Evidence,
    FetchedPage,
    UrlStatus,
)
from app.search import JOB_CACHE
from app.services.companies import is_proof_source
from app.services.state_machine import log_event
from app.spec.models import ExtractionSpec, Semantic

log = logging.getLogger("webdata.crawl")
# A registry's name, official website and founding year beat what pages say ("JNJ.com"; a JSON-LD url on
# cascade.boeing.com; "our plant was established in 2007").
REGISTRY_CONFIDENCE = {"company_name": 0.92, "website_url": 0.93, "founded_year": 0.85}
# Proof columns: one piece of proof fills all of them, and the strongest piece wins (see proof_confidence).
PROOF_KEYS = ("uses_technology", "evidence", "evidence_url", "evidence_date", "evidence_type")
REGISTRY_METHODS = ("wikidata", "sec_edgar", "gleif", "sec_filings")
PROOF_METHODS = ("case_studies", "news")  # sources whose page named the company and the product together
PROOF_NAME_CONFIDENCE = 0.96  # above a page's JSON-LD name (0.95)
LEASE = timedelta(minutes=5)
SOURCE_NAMES = {"seeds": "your starting websites", "wikidata": "Wikidata", "sec_edgar": "SEC EDGAR",
                "gleif": "GLEIF", "searxng": "web search", "sec_filings": "SEC filings",
                "case_studies": "case studies and customer stories", "news": "news articles (GDELT)"}
RECORDS_EVERY = 20.0  # seconds between refreshes of the records shown while the crawl is still running
# A site whose homepage does not say where it is: this many of its own contact or about pages are read to find out.
COUNTRY_PAGES = 3
COUNTRY_CHECK = "country_check"  # the method of a page read to find where a company is based
CANCEL_CHECK_EVERY = 5.0  # seconds between looks at the job's state while a discovery source works


class JobCancelled(Exception):
    pass


def country_source(method: str, hint: dict[str, Any], why: str) -> str:
    """Which kind of evidence a country check used: a registry's own entry (Wikidata, SEC, GLEIF) or the
    company's own pages. Weighed in that order by the final decision."""
    if hint.get("_country_by") and " says " in why:
        return str(hint["_country_by"]).split(":", 2)[0] + ": " + str(hint["_country_by"]).split(":", 2)[1].strip()
    if hint.get("country") and f"{method} says" in why and method in REGISTRY_METHODS:
        return f"registry: {method}"
    if hint.get("country") and " says " in why:
        return f"source: {method}"
    return "own pages"


def _page_rank(url: str, keywords: list[str]) -> int:
    """0: a contact or about page, 1: a page matching another priority keyword (careers, news...), 2: other.
    Contact pages come first because they hold the email and phone; with careers and news ranked the same,
    Northrop's and NewMarket's 15-page budget went to job and 2015 news pages and no contact was read."""
    path = url.lower()
    if any(k in path for k in CONTACT_HINTS):
        return 0
    return 1 if any(k in path for k in keywords) else 2


def _priority(url: str, depth: int, keywords: list[str]) -> int:
    return depth * 50 + 50 - (40, 30, 0)[_page_rank(url, keywords)]


def _found_by(hint: dict[str, Any]) -> str:
    """"; found by tavily for 'q': "Title" - snippet", so a dropped search result shows what search said."""
    hit = next(iter(hint.get("_search") or []), None)
    if not hit:
        return ""
    said = " - ".join(x for x in (f'"{hit["title"]}"' if hit.get("title") else "", hit.get("snippet", "")) if x)
    return f"; found by {hit['provider']} for {hit['query']!r}" + (f": {said[:200]}" if said else "")


def reading_order(providers: list) -> list:
    """Sources in the plan's order, except that those reading an open-ended set of candidates go last: they take
    whatever reading time the bounded ones leave, including all of a source's share that could not be reached
    (GDELT was down once, and its half of the hour went unused while case studies had stopped at theirs)."""
    return sorted(providers, key=lambda p: bool(getattr(p, "open_ended", False)))


def reading_share(now: float, deadline: float, readers_left: int) -> float:
    """When the source whose turn it is must stop reading: an equal share of the budget left, among the sources
    still to read (this one included)."""
    return now + max(0.0, deadline - now) / max(1, readers_left)


class CrawlRunner:
    def __init__(self, job_id: uuid.UUID, org_id: uuid.UUID, spec: ExtractionSpec, *, resolver=None,
                 redis=None, client=None, max_records: int | None = None) -> None:
        self.job_id, self.org_id, self.spec = job_id, org_id, spec
        self.max_records = max_records
        self.activity: list[dict[str, Any]] = []
        self.last_records = (0, 0)
        self.site_checker = SiteChecker()
        # A technology question: every page read is also checked for proof that the company uses it.
        self.site_proof = SiteProof(spec) if spec.discovery.technology else None
        self.site_names: dict[str, str] = {}  # site -> company name its source gave
        self.site_queued: dict[str, int] = {}  # site -> pages queued from its links and sitemap
        # Details a page can give (fields with an extractor or a source); a site whose details are all found
        # is not read further. Fields only a model could fill (phase 2) never hold a site back.
        self.wanted_fields = {f.name for f in spec.fields if _has_extractor(f) or f.name in PROOF_KEYS}
        self.fields_by_name = {f.name: f for f in spec.fields}
        self.site_found: dict[str, set[str]] = {}
        self.done_sites: set[str] = set()
        self.told_unchecked = False
        self.facts: list[dict[str, Any]] = []  # what checks established about companies, saved with each page
        self.country_checks: dict[str, int] = {}  # "only these countries": sites per outcome (IN_COUNTRY...)
        self.settings = get_settings()
        self.resolver = resolver
        self.client = client or (make_client(resolver=resolver) if resolver else make_client())
        delay = self.settings.per_domain_delay_seconds
        if redis == "auto":
            import redis.asyncio as aioredis

            redis = aioredis.from_url(self.settings.redis_url)
        self.politeness = RedisPoliteness(redis, delay) if redis is not None else LocalPoliteness(delay)
        self.fetcher = Fetcher(self.client, self.politeness, resolver)
        # Pages a discovery source reads for proof may be PDFs (case studies often are); crawled pages stay HTML.
        self.doc_fetcher = Fetcher(self.client, self.politeness, resolver, allowed_types=DOCUMENT_TYPES)
        self.robots = RobotsCache(self.fetcher, self.settings.user_agent, self.settings.respect_robots)
        self.allowed_sites: set[str] = set()
        self.denied: set[str] = set()
        self.sitemaps_done: set[str] = set()
        self.host_sem: dict[str, asyncio.Semaphore] = {}
        self.started = time.monotonic()

    # --- activity feed ----------------------------------------------------------------------

    def note(self, kind: str, message: str, url: str | None = None, **data: Any) -> None:
        """One line of the live activity feed: something the worker really did, as it happened.

        kind: search | queued | read | kept | found | links | dropped | skipped | blocked | failed | records
        """
        site = registered_domain(url) if url else data.pop("site", None)
        self.activity.append({"at": utcnow(), "message": message[:500],
                              "data": {"kind": kind, "site": site, "url": url, **data}})

    def flush_activity(self) -> None:
        if not self.activity:
            return
        rows, self.activity = self.activity, []
        with session_scope(self.org_id) as db:
            db.add_all([CrawlJobEvent(org_id=self.org_id, job_id=self.job_id, type="activity", message=r["message"],
                                      data=r["data"], created_at=r["at"]) for r in rows])

    async def _flush_every_second(self) -> None:
        while True:
            await asyncio.sleep(1)
            try:
                self.flush_activity()
            except Exception:  # noqa: BLE001 - the feed is a view; it must never stop the crawl
                log.exception("could not save activity")

    def _discovery_line(self, name: str) -> str:
        d = self.spec.discovery
        what = " ".join(x for x in (d.industry, "companies" if d.industry else "") if x) or "companies"
        if d.technology:
            what += f" using {d.technology}"
        where = ", ".join(d.countries) or (d.region or "").replace("_", " ")
        return f"Searching {SOURCE_NAMES.get(name, name)} for {what}" + (f" in {where}" if where else "")

    # --- frontier ---------------------------------------------------------------------------

    def _eligibility(self, url: str) -> tuple[str, str | None]:
        if registered_domain(url) in self.denied or host_of(url) in self.denied:
            return UrlStatus.blocked_policy, "domain is on the denylist"
        try:
            if self.resolver is not None:
                check_url(url, resolver=self.resolver)
            else:
                check_url(url)
        except BlockedDestination as exc:
            return UrlStatus.blocked_policy, str(exc)
        return UrlStatus.queued, None

    def add_urls(self, items: list[dict[str, Any]]) -> int:
        """Insert URLs into the frontier; duplicates are ignored. Returns how many were new."""
        if not items:
            return 0
        rows = []
        for it in items:
            status, reason = it.get("status") or self._eligibility(it["url"])
            rows.append({
                "id": uuid.uuid4(), "org_id": self.org_id, "job_id": self.job_id, "url": it["url"],
                "url_hash": url_hash(it["url"]), "host": host_of(it["url"]), "referrer_url": it.get("referrer"),
                "method": it["method"], "depth": it.get("depth", 0), "status": status, "status_reason": reason,
                "priority": _priority(it["url"], it.get("depth", 0), self.spec.crawl.priority_keywords),
                "hint": it.get("hint") or {}, "discovered_at": utcnow(),
            })
        with session_scope(self.org_id) as db:
            result = db.execute(insert(DiscoveredUrl).values(rows).on_conflict_do_nothing(
                index_elements=["job_id", "url_hash"]).returning(DiscoveredUrl.id))
            return len(result.fetchall())

    def _load_policies(self) -> None:
        with session_scope(self.org_id) as db:
            rows = db.execute(select(DomainPolicy.domain).where(
                DomainPolicy.rule == "deny",
                (DomainPolicy.org_id == self.org_id) | (DomainPolicy.org_id.is_(None)))).scalars().all()
            self.denied = {d.lower() for d in rows}

    async def seed(self) -> int:
        self._load_policies()
        items: list[dict[str, Any]] = []
        errors: list[str] = []
        notes: list[str] = []
        sites: set[str] = set()
        found = 0  # sites from discovery sources (not the user's own URLs), capped at max_results
        by_site: dict[str, dict[str, Any]] = {}
        per_provider: list[list[Any]] = []
        flusher = asyncio.create_task(self._flush_every_second())  # sources that read documents report live
        cache_token = JOB_CACHE.set({})  # this job's searches, reused within the job only
        from app.discovery.entities import GLEIF_GAP, REGISTRY_RETRY_WAITS, EntityResolver

        # One registry matcher for the job: each name is looked up once, by whichever step needs it first.
        testing = self.settings.env == "test"
        self.entity_resolver = EntityResolver(self.client, gleif_gap=0.0 if testing else GLEIF_GAP,
                                              retry_waits=(0.0, 0.0) if testing else REGISTRY_RETRY_WAITS)
        self.read_deadline = time.monotonic() + self.spec.discovery.read_budget_minutes * 60
        try:
            providers = reading_order(providers_for(self.spec))
            # The reading budget is shared: each source that reads proof pages gets an equal share of what is left
            # when its turn comes, so one source cannot spend it all (case studies read for the whole hour once and
            # no news article was read); time a source does not need passes to the next.
            readers_left = sum(hasattr(p, "deadline") for p in providers)
            for provider in providers:
                label = SOURCE_NAMES.get(provider.name, provider.name)
                if provider.name != "seeds":
                    self.note("search", self._discovery_line(provider.name), source=provider.name)
                    self.flush_activity()
                if hasattr(provider, "on_note"):
                    provider.on_note = self.note
                if hasattr(provider, "fetch_text"):
                    provider.fetch_text = self.fetch_text
                if hasattr(provider, "fetch_page"):
                    provider.fetch_page = self.fetch_page
                if hasattr(provider, "deadline"):
                    provider.deadline = reading_share(time.monotonic(), self.read_deadline, readers_left)
                    readers_left -= 1
                if hasattr(provider, "resolver"):
                    provider.resolver = self.entity_resolver
                try:
                    results = await self._discover_or_cancel(provider)
                    per_provider.append(results)
                    if provider.name != "seeds":
                        self.note("search", f"{label[0].upper()}{label[1:]} returned {len(results)} website(s)",
                                  source=provider.name)
                except DiscoveryError as exc:
                    errors.append(f"{provider.name}: {exc}")
                    self.note("failed", f"{label}: {exc}", source=provider.name)
                self.save_evidence(provider.name, getattr(provider, "evidence", []))
                self.save_facts(getattr(provider, "facts", None) or [])
                self.flush_activity()
                notes += getattr(provider, "notes", [])
            per_provider.append(await self._resolve_entities(per_provider, notes))
        finally:
            flusher.cancel()
            JOB_CACHE.reset(cache_token)
        # Take results from the sources in turn (Wikidata, SEC, web search, Wikidata...), so the first
        # source cannot fill the whole budget on its own and every source contributes companies.
        ordered = [r for group in zip_longest(*per_provider) for r in group if r is not None]
        for r in ordered:
            site = registered_domain(r.url)
            # One entry per website: the first source wins, and later sources only fill in hints
            # it lacked (SEC adds the industry to a company Wikidata found first).
            if site in by_site and r.method != "seed":
                earlier = by_site[site]
                earlier["hint"] = {**{k: v for k, v in r.hint.items() if not k.startswith("_")},
                                   **(earlier["hint"] or {})}
                continue
            if r.method != "seed" and found >= self.spec.discovery.max_results:
                continue
            found += r.method != "seed"
            sites.add(site)
            items.append({"url": r.url, "method": r.method, "hint": dict(r.hint), "referrer": r.referrer})
            name = r.hint.get("company_name")
            self.note("queued", f"Queued {name + ' (' + site + ')' if name else site} "
                                f"from {SOURCE_NAMES.get(r.method, r.method)}", r.url, source=r.method)
            by_site.setdefault(site, items[-1])
        by_method: dict[str, int] = {}
        for it in items:
            by_method[it["method"]] = by_method.get(it["method"], 0) + 1
        notes.append("sites per source: " + ", ".join(f"{m} {n}" for m, n in by_method.items()))
        with session_scope(self.org_id) as db:
            for e in errors:
                log_event(db, self.org_id, self.job_id, "warning", f"Discovery problem: {e}")
            for n in notes:
                log_event(db, self.org_id, self.job_id, "info", f"Discovery note: {n}")
            log_event(db, self.org_id, self.job_id, "info", f"Discovery found {len(items)} starting URL(s)")
        self.flush_activity()
        if not items and errors:
            raise DiscoveryError("; ".join(errors))
        self.allowed_sites = {registered_domain(i["url"]) for i in items}
        self.allowed_sites |= {registered_domain(d) for d in self.spec.crawl.allowed_domains}
        return self.add_urls(items)

    async def _resolve_entities(self, per_provider: list[list[Any]], notes: list[str]) -> list[Any]:
        """Match every company a source named to a registered entity, once, before anything is crawled: the
        registry's country becomes the company's country fact (and the crawl's), and its official website gives
        a company with proof but no website found one. Returns the companies that gained a website this way."""
        from app.discovery.entities import resolution_facts
        from app.discovery.providers import DiscoveryResult

        d = self.spec.discovery
        named = [r for group in per_provider for r in group if r.hint.get("company_name") and r.method != "seed"]
        with session_scope(self.org_id) as db:
            homeless = db.execute(select(Evidence).where(
                Evidence.job_id == self.job_id, Evidence.kept.is_(True), Evidence.website == "",
                Evidence.verdict.in_(("Confirmed", "Likely")))).scalars().all()
            homeless = [{"company": e.company, "verdict": e.verdict, "quote": e.quote, "url": e.url,
                         "date": e.evidence_date, "type": e.source_type, "strength": e.strength} for e in homeless]
        if not (named and d.countries) and not homeless:
            return []
        self.note("search", f"Matching {len(named) + len(homeless)} named companies to registry entries "
                            "(Wikidata, GLEIF, SEC)", source="registries")
        added: list[Any] = []
        # The crawler's own client: network rules apply, and tests decide what it can reach.
        resolver = self.entity_resolver
        settled = 0
        if d.countries:
            for r in named:
                name, site = str(r.hint["company_name"]), registered_domain(r.url) or ""
                res = await resolver.resolve(name, r.url)
                self.facts += resolution_facts(name, site, res)
                if res.country:
                    settled += 1
                    r.hint["country"], r.hint["_country_by"] = res.country, f"{res.by}: {res.detail}"
        best: dict[str, dict[str, Any]] = {}
        for e in homeless:
            key = e["company"].casefold()
            if key not in best or e["strength"] > best[key]["strength"]:
                best[key] = e
        for e in best.values():
            res = await resolver.resolve(e["company"])
            self.facts += resolution_facts(e["company"], registered_domain(res.website) if res.website else "",
                                           res)
            if not res.website:
                continue
            hint = {"company_name": e["company"], "website_url": res.website, "uses_technology": e["verdict"],
                    "evidence": e["quote"], "evidence_url": e["url"], "evidence_date": e["date"],
                    "evidence_type": e["type"], "_source": e["url"], "_strength": e["strength"]}
            if res.country:
                hint["country"], hint["_country_by"] = res.country, f"{res.by}: {res.detail}"
            added.append(DiscoveryResult(res.website, "case_studies", hint, referrer=e["url"]))
            self.note("search", f"Website of {e['company']} from {res.by.removeprefix('registry: ')}: "
                                f"{res.website}", res.website, source="registries")
        self.save_facts()
        notes.append(f"registries: {settled} of {len(named)} named companies placed in a country; "
                     f"{len(added)} of {len(best)} proven companies without a website got one")
        if resolver.problems:
            notes.append("registries: lookups failed (" + "; ".join(resolver.problems) + ")")
        self.flush_activity()
        return added

    def _cancel_requested(self) -> bool:
        with session_scope(self.org_id) as db:
            job = db.get(CrawlJob, self.job_id)
            return job is None or job.state == "cancel_requested"

    async def _discover_or_cancel(self, provider) -> list:
        """One source's results, stopping within seconds when the person cancels: a source can read for a
        quarter of an hour, and a cancel used to wait for all of it (and then failed the job)."""
        work = asyncio.ensure_future(provider.discover(self.spec))
        while True:
            done, _pending = await asyncio.wait({work}, timeout=CANCEL_CHECK_EVERY)
            if done:
                return work.result()
            if self._cancel_requested():
                work.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await work
                raise JobCancelled()

    async def fetch_page(self, url: str) -> PageDoc | None:
        """A page for a discovery source, fetched like any crawled page: robots.txt respected, network rules
        checked. None when it cannot be read or has no text."""
        got = await self._fetch_doc(url)
        return None if got is None or unreadable(got[1]) else got[1]

    async def _fetch_doc(self, url: str) -> tuple[Any, PageDoc] | None:
        """(fetch result, parsed page) under robots.txt and the network rules; None when nothing was fetched."""
        decision = await self.robots.check(url)
        if not decision.allowed:
            return None
        try:
            result = await self.doc_fetcher.fetch(url)
        except FetchError:
            return None
        return result, parse_page(normalize_url(result.final_url) or url, result.html())

    async def fetch_text(self, url: str) -> str | None:
        doc = await self.fetch_page(url)
        return f"{doc.title} {doc.text}" if doc else None

    def fact(self, site: str, company: str, kind: str, value: str, detail: str, source_url: str = "",
             by: str = "", quote: str = "") -> None:
        """Record what a check established about a company, instead of dropping it (app.services.companies)."""
        self.facts.append({"site": site or "", "company": company or "", "kind": kind, "value": value or "",
                           "detail": detail or "", "source_url": source_url or "", "by": by or "", "quote": quote})

    def save_facts(self, facts: list[dict[str, Any]] | None = None) -> None:
        rows = self.facts if facts is None else facts
        if not rows:
            return
        cols = {c.name: getattr(c.type, "length", None) for c in CompanyFact.__table__.columns
                if c.name not in ("id", "org_id", "job_id", "created_at")}
        with session_scope(self.org_id) as db:
            db.add_all([CompanyFact(org_id=self.org_id, job_id=self.job_id,
                                    **{k: (v[:cols[k]] if isinstance(v, str) and cols[k] else v)
                                       for k, v in f.items() if k in cols}) for f in rows])
        rows.clear()

    def save_evidence(self, source: str, evidence: list[dict[str, Any]]) -> None:
        """Every piece of proof a source looked at, kept or rejected, for the Evidence and Rejected sheets."""
        if not evidence:
            return
        cols = {c.name: getattr(c.type, "length", None) for c in Evidence.__table__.columns
                if c.name not in ("id", "org_id", "job_id", "created_at")}

        def clip(k: str, v: Any) -> Any:
            return v[:cols[k]] if isinstance(v, str) and cols[k] else v

        with session_scope(self.org_id) as db:
            db.add_all([Evidence(org_id=self.org_id, job_id=self.job_id,
                                 **{k: clip(k, v) for k, v in e.items() if k in cols}) for e in evidence])
        evidence.clear()

    def _restore_scope(self) -> None:
        """On resume, the crawl scope is the set of sites the seeds belonged to."""
        with session_scope(self.org_id) as db:
            seeds = db.execute(select(DiscoveredUrl.url).where(
                DiscoveredUrl.job_id == self.job_id, DiscoveredUrl.depth == 0)).scalars().all()
        self.allowed_sites = {registered_domain(u) for u in seeds}
        self.allowed_sites |= {registered_domain(d) for d in self.spec.crawl.allowed_domains}

    def claim_fair(self) -> DiscoveredUrl | None:
        """The most urgent queued page from a site that is not already being read by its share of workers."""
        now = utcnow()
        with session_scope(self.org_id) as db:
            db.execute(update(DiscoveredUrl).where(
                DiscoveredUrl.job_id == self.job_id, DiscoveredUrl.status == UrlStatus.in_progress,
                DiscoveredUrl.lease_until < now).values(status=UrlStatus.queued))
            rows = db.execute(
                select(DiscoveredUrl).where(DiscoveredUrl.job_id == self.job_id,
                                            DiscoveredUrl.status == UrlStatus.queued)
                .order_by(DiscoveredUrl.priority, DiscoveredUrl.discovered_at).limit(200)
                .with_for_update(skip_locked=True)).scalars().all()
            limit = self.settings.per_domain_concurrency
            for r in rows:
                if self.busy_hosts.get(r.host, 0) < limit:
                    r.status = UrlStatus.in_progress
                    r.lease_until = now + LEASE
                    r.attempts += 1
                    db.flush()
                    db.expunge(r)
                    return r
            return None

    async def _worker(self) -> None:
        while not self.stopping:
            if self.counts_cache["fetched"] + self.active >= self.spec.crawl.max_pages:
                if self.active == 0:
                    return
                await asyncio.sleep(0.2)
                continue
            self.active += 1
            row = None
            try:
                row = self.claim_fair()
                if row is None:
                    self.active -= 1
                    if self.active == 0 and not self.claim_possible():
                        return  # nothing queued and nothing being read that could add more
                    await asyncio.sleep(0.2)
                    continue
                self.busy_hosts[row.host] = self.busy_hosts.get(row.host, 0) + 1
                await self.process(row)
                self.counts_cache = self.counts()
            finally:
                if row is not None:
                    self.active -= 1
                    self.busy_hosts[row.host] -= 1

    def claim_possible(self) -> bool:
        with session_scope(self.org_id) as db:
            return db.execute(select(DiscoveredUrl.id).where(
                DiscoveredUrl.job_id == self.job_id,
                DiscoveredUrl.status.in_([UrlStatus.queued, UrlStatus.in_progress])).limit(1)).first() is not None

    def counts(self) -> dict[str, int]:
        with session_scope(self.org_id) as db:
            by_status = dict(db.execute(select(DiscoveredUrl.status, func.count()).where(
                DiscoveredUrl.job_id == self.job_id).group_by(DiscoveredUrl.status)).all())
            pages = db.execute(select(func.count()).select_from(FetchedPage).where(
                FetchedPage.job_id == self.job_id)).scalar_one()
        return {
            "discovered": sum(by_status.values()),
            "queued": by_status.get(UrlStatus.queued, 0) + by_status.get(UrlStatus.in_progress, 0),
            "fetched": by_status.get(UrlStatus.fetched, 0),
            "parsed": pages,
            "skipped": by_status.get(UrlStatus.skipped, 0),
            "blocked": by_status.get(UrlStatus.blocked_robots, 0) + by_status.get(UrlStatus.blocked_policy, 0),
            "failed": by_status.get(UrlStatus.failed, 0) + by_status.get(UrlStatus.dead, 0),
        }

    def _check_job(self) -> None:
        with session_scope(self.org_id) as db:
            job = db.get(CrawlJob, self.job_id)
            if job is None or job.state == "cancel_requested":
                raise JobCancelled()
            job.counters = {**job.counters, **self.counts_cache}
            job.heartbeat_at = utcnow()

    # --- one URL ----------------------------------------------------------------------------

    def _finish(self, url_id: uuid.UUID, status: str, reason: str | None = None) -> None:
        with session_scope(self.org_id) as db:
            db.execute(update(DiscoveredUrl).where(DiscoveredUrl.id == url_id).values(
                status=status, status_reason=(reason or "")[:1000] or None, lease_until=None))

    async def _sitemap_urls(self, origin: str) -> list[dict[str, Any]]:
        if origin in self.sitemaps_done or not self.spec.crawl.use_sitemaps:
            return []
        self.sitemaps_done.add(origin)
        sitemap_fetcher = Fetcher(self.client, self.politeness, self.resolver,
                                  allowed_types=("application/xml", "text/xml", "text/plain", ""))
        candidates = self.robots.sitemaps(origin + "/") or [origin + "/sitemap.xml"]
        found: list[str] = []
        for sm in candidates[:3]:
            try:
                res = await sitemap_fetcher.fetch(sm, attempts=1)
            except FetchError:
                continue
            locs = [n.text(strip=True) for n in HTMLParser(res.text[:5_000_000]).css("loc")][:2000]
            nested = [loc for loc in locs if loc.endswith(".xml")]
            pages = [loc for loc in locs if not loc.endswith(".xml")]
            for child in nested[:3]:
                try:
                    sub = await sitemap_fetcher.fetch(child, attempts=1)
                    pages += [n.text(strip=True) for n in HTMLParser(sub.text[:5_000_000]).css("loc")][:2000]
                except FetchError:
                    continue
            found += pages
        kws = self.spec.crawl.priority_keywords
        chosen = sorted(dict.fromkeys(found), key=lambda u: _page_rank(u, kws))
        chosen = chosen[: self.spec.crawl.max_pages_per_site * 2]
        out = []
        for u in chosen:
            nu = normalize_url(u)
            if nu and registered_domain(nu) in self.allowed_sites and looks_like_page(nu):
                out.append({"url": nu, "method": "sitemap", "depth": 1, "referrer": origin + "/sitemap.xml"})
        return out

    def _site_page_count(self, site: str) -> int:
        with session_scope(self.org_id) as db:
            return db.execute(select(func.count()).select_from(DiscoveredUrl).where(
                DiscoveredUrl.job_id == self.job_id, DiscoveredUrl.status == UrlStatus.fetched,
                func.lower(DiscoveredUrl.host).like(f"%{site}"))).scalar_one()

    async def _homepage_reason(self, row, doc, site: str, final: str) -> tuple[str | None, str]:
        """Why a discovered site is left out before crawling it, or None to keep it.

        A search result is only a link, and anyone can tag their own Wikidata item with an industry, so each
        piece of evidence counts: the registry's own industry, the homepage's words and the model's reading.
        A page with no readable text says nothing either way and is never judged on its content.
        """
        if unreadable(doc):
            if row.method == "searxng":  # nothing else vouches for a bare search result
                return "homepage could not be read (no text: a loader or challenge page), so it was not verified", \
                    "rules"
            self.note("search", f"{site}: homepage could not be read (no text); kept on {row.method}'s facts, "
                              "not verified from the site", final)
            return None, "rules"
        # A company that a proof source named is checked only against what the question asks of its customers,
        # its industry: the question's other keywords describe the rows to search for, and once described the
        # product itself ("HR technology" for Workday HCM), which dropped every Workday customer as a non-vendor.
        proof_named = is_proof_source(row.method)
        subject = (self.spec.discovery.industry or "") if proof_named else None
        if proof_named and not subject:
            return None, "rules"
        registry_industry = row.method == "wikidata" and bool(row.hint.get("industry"))
        if not registry_industry:  # the registry already matched the industry; a missing word does not undo it
            reason = off_topic_reason(doc, self.spec, check_country=row.method == "searxng", subject=subject)
            if reason:
                return reason, "rules"
        # Mentioning the industry is not being in it: lists, associations, shops and IT firms do too.
        reason, by = await self.site_checker.check(doc, self.spec, subject=subject)
        if not reason and by.startswith("model:"):
            self.note("search", f"Checked {site} with free model {by[6:]}: in the industry", final)
        elif by.startswith("unchecked") and not self.told_unchecked:
            self.told_unchecked = True
            self.note("skipped", f"Discovered sites are not checked by a model ({by[11:]}); "
                                 "only rules are applied", final)
        return reason, by

    def _room_for(self, site: str) -> bool:
        """True while one more page of this site may be read: within the job's page budget (counting the pages
        being read now) and the site's."""
        crawl = self.spec.crawl
        return (self.counts()["fetched"] + self.active < crawl.max_pages
                and self._site_page_count(site) + 1 < crawl.max_pages_per_site)

    def _record_check_page(self, url: str, referrer: str) -> uuid.UUID:
        """A page read to check the country is a page fetched: it counts against the page budgets and is billed
        like any other, and is not read again later."""
        values = {"status": UrlStatus.fetched, "status_reason": "read to check where the company is based",
                  "lease_until": None}
        with session_scope(self.org_id) as db:
            return db.execute(insert(DiscoveredUrl).values(
                id=uuid.uuid4(), org_id=self.org_id, job_id=self.job_id, url=url, url_hash=url_hash(url),
                host=host_of(url), referrer_url=referrer, method=COUNTRY_CHECK, depth=1, attempts=1, hint={},
                priority=_priority(url, 1, self.spec.crawl.priority_keywords), discovered_at=utcnow(), **values,
            ).on_conflict_do_update(index_elements=["job_id", "url_hash"], set_=values)
                .returning(DiscoveredUrl.id)).scalar_one()

    async def _verify_country(self, doc: PageDoc, site: str, hint: dict[str, Any]
                              ) -> tuple[str, str, list[tuple[uuid.UUID, Any, PageDoc]]]:
        """The country of a site whose homepage does not say, read from a few of its own contact and about pages
        (robots.txt, politeness and network rules as for any page, and within the page budgets). A search
        result's own page on the site is read first: what search said is a clue to where to look, never the
        answer. Also returns the pages read (row id, fetch result, page), to be kept if the site is."""
        hits = [normalize_url(h.get("url", "")) for h in hint.get("_search") or []]
        contact = sorted((link for link, _text in doc.links if _page_rank(link, []) == 0),
                         key=lambda u: next(i for i, k in enumerate(CONTACT_HINTS) if k in u.lower()))
        pages = [u for u in dict.fromkeys(hits + contact)
                 if u and u != doc.url and registered_domain(u) == site and looks_like_page(u)][:COUNTRY_PAGES]
        checked: list[tuple[uuid.UUID, Any, PageDoc]] = []
        stopped = False
        for url in pages:
            if not self._room_for(site):
                stopped = True
                break
            got = await self._fetch_doc(url)
            if got is None:
                continue
            result, page = got
            url_id = self._record_check_page(url, doc.url)
            if registered_domain(page.url) == site and not unreadable(page):
                checked.append((url_id, result, page))
        country, how = pages_country([doc] + [page for _id, _r, page in checked])
        wanted = self.spec.discovery.countries
        if country in wanted:
            return IN_COUNTRY, f"based in {country} ({how})", checked
        if country:
            return OUTSIDE_COUNTRY, f"based in {country}, outside {', '.join(wanted)} ({how})", checked
        read = len(checked)
        pages_read = f" ({', '.join(p.url for _i, _r, p in checked)})" if read else ""
        why = how or ("no address, country-code domain or one-country phone numbers on the homepage or "
                      f"{read} company page(s) read{pages_read}")
        return COUNTRY_UNKNOWN, (f"could not confirm it is based in {', '.join(wanted)}: {why}"
                                 + ("; the page budget stopped the check" if stopped else "")), checked

    def _extracted(self, doc: PageDoc) -> dict[str, list[Any]]:
        found = extract_page(doc, self.spec.fields)
        for f in self.spec.fields:
            if f.semantic == Semantic.phone and f.name in found:
                prefer_country_phones(found[f.name], self.spec.discovery.countries)
            if f.semantic == Semantic.contact_email and f.name in found:
                prefer_country_emails(found[f.name], self.spec.discovery.countries)
        return found

    async def _proof_checks(self, doc: PageDoc, result, site: str, final: str,
                            candidates: dict[str, list[dict[str, Any]]]) -> None:
        if self.site_proof is not None:
            await self._check_site_proof(doc, site, candidates)
            await self._check_code(doc, result.headers, site, candidates)
            await self._check_job_boards(result.text, site, final, candidates)

    def _save_page(self, url_id: uuid.UUID, final: str, result, doc: PageDoc,
                   candidates: dict[str, list[dict[str, Any]]], hint: dict[str, Any] | None = None) -> None:
        """The page and its candidates; with `hint`, its frontier row is marked fetched in the same transaction."""
        with session_scope(self.org_id) as db:
            db.add(FetchedPage(org_id=self.org_id, job_id=self.job_id, url_id=url_id, final_url=final,
                               http_status=result.status, content_type=result.content_type[:128],
                               bytes=len(result.body), content_hash=result.sha256, title=doc.title[:1000],
                               text_excerpt=doc.text[:2000], candidates=candidates))
            if hint is not None:
                db.execute(update(DiscoveredUrl).where(DiscoveredUrl.id == url_id).values(
                    status=UrlStatus.fetched, status_reason=None, lease_until=None, hint=hint))

    async def process(self, row: DiscoveredUrl) -> None:
        url = row.url
        site = registered_domain(url)
        if site not in self.allowed_sites:
            self._finish(row.id, UrlStatus.skipped, "outside the crawl scope")
            return
        if site in self.done_sites:
            self._finish(row.id, UrlStatus.skipped, "every detail was already found on this site")
            return
        if self._site_page_count(site) >= self.spec.crawl.max_pages_per_site:
            self._finish(row.id, UrlStatus.skipped, "page budget for this site reached")
            return
        decision = await self.robots.check(url)
        if not decision.allowed:
            self._finish(row.id, UrlStatus.blocked_robots, decision.reason)
            self.note("blocked", f"Not reading {url}: {decision.reason}", url)
            return
        self.note("read", f"Reading {url}", url, depth=row.depth)
        delay = self.robots.crawl_delay(url)
        if delay:
            self.politeness.host_delay[host_of(url)] = min(delay, 30.0)
        sem = self.host_sem.setdefault(host_of(url), asyncio.Semaphore(self.settings.per_domain_concurrency))
        async with sem:
            try:
                result = await self.fetcher.fetch(url, attempts=1)
            except FetchError as exc:
                self.note("failed" if exc.kind not in ("http_404", "http_410", "content_type", "too_large")
                          else "skipped", f"Could not read {url}: {exc}", url)
                if exc.kind == "blocked":
                    self._finish(row.id, UrlStatus.blocked_policy, str(exc))
                elif exc.kind in ("content_type", "too_large"):
                    self._finish(row.id, UrlStatus.skipped, str(exc))
                elif exc.kind in ("http_404", "http_410"):
                    # A broken link on the site is not a crawl failure.
                    self._finish(row.id, UrlStatus.skipped, f"page not found ({exc.kind.replace('_', ' ').upper()})")
                elif exc.retryable and row.attempts < self.settings.url_retry_limit:
                    self._finish(row.id, UrlStatus.queued, f"{exc.kind}: will retry")
                else:
                    self._finish(row.id, UrlStatus.dead if exc.retryable else UrlStatus.failed,
                                 f"{exc.kind}: {exc}")
                return
        final = normalize_url(result.final_url) or url
        moved_to = registered_domain(final)
        if moved_to not in self.allowed_sites:
            if row.depth != 0:
                self._finish(row.id, UrlStatus.skipped, f"redirected outside the crawl scope to {host_of(final)}")
                return
            # A company's listed homepage that moved to its current domain (volkswagen.de ->
            # volkswagen-group.com, bosch.de -> bosch.com) is the same company: crawl it there.
            self.allowed_sites.add(moved_to)
            self.note("queued", f"{site} moved to {moved_to}; reading it there", final)
            site = moved_to
        with session_scope(self.org_id) as db:
            duplicate = db.execute(select(FetchedPage.id).where(
                FetchedPage.job_id == self.job_id, FetchedPage.content_hash == result.sha256)).first()
        if duplicate:
            self._finish(row.id, UrlStatus.skipped, "same content as a page already fetched")
            self.note("skipped", f"Skipped {final}: same content as a page already read", final)
            return
        doc = parse_page(final, result.text)
        hint = row.hint or {}
        company = str(hint.get("company_name") or "")
        if row.depth == 0 and row.method in ("searxng", "wikidata", "case_studies", "news"):
            reason, by = await self._homepage_reason(row, doc, site, final)
            if reason:
                self.fact(site, company, "filter", "not met", reason, final, by)
                if not is_proof_source(row.method):
                    self.allowed_sites.discard(site)
                    self._finish(row.id, UrlStatus.skipped, f"{row.method} result dropped: {reason}")
                    self.note("dropped", f"Dropped {site}: {reason}", final)
                    self.save_facts()
                    return
                # Proof named this company: the failed filter is one of its facts, weighed in the final decision.
                self.note("kept", f"{site} has proof; recorded for the decision: {reason}", final)
        checked: list[tuple[uuid.UUID, Any, PageDoc]] = []  # pages read to check the country
        if row.depth == 0:
            status, why = country_status(doc, self.spec, row.method, hint)
            if status == COUNTRY_UNKNOWN:
                status, why, checked = await self._verify_country(doc, site, hint)
            if status != NOT_CHECKED:
                self.country_checks[status] = self.country_checks.get(status, 0) + 1
                iso = (re.search(r"based in ([A-Z]{2})\b", why) or [None, ""])[1]
                self.fact(site, company, "country", iso if status in (IN_COUNTRY, OUTSIDE_COUNTRY) else "",
                          why, final, country_source(row.method, hint, why))
            if status in (OUTSIDE_COUNTRY, COUNTRY_UNKNOWN):  # "only these countries" is on: not crawled further
                self.save_facts()
                self.allowed_sites.discard(site)
                head = "outside the requested countries" if status == OUTSIDE_COUNTRY else "country not confirmed"
                self._finish(row.id, UrlStatus.skipped, f"{head}: {why}{_found_by(hint)}")
                self.note("dropped", f"Dropped {site}: {why}", final, country=status)
                return
            if status == IN_COUNTRY:
                hint = {**hint, "_country": why}
            self.note("kept", f"Kept {site}" + (f" ({hint['company_name']})" if hint.get("company_name")
                                                else "") + ": homepage checks passed"
                      + (f"; {why}" if status == IN_COUNTRY else ""), final, country=status)
        found = self._extracted(doc)
        candidates = {name: [c.__dict__ for c in cands] for name, cands in found.items() if cands}
        if row.hint.get("company_name"):
            self.site_names.setdefault(site, str(row.hint["company_name"]))
        if self.site_proof is not None and row.hint.get("uses_technology"):
            self.site_proof.has_proof.add(site)  # its source brought proof (an SEC filing)
            if row.hint["uses_technology"] == "Confirmed":
                self.site_proof.hint_confirmed.add(site)
        if row.hint:  # values supplied by discovery (e.g. Wikidata) with their source
            for key, value in row.hint.items():
                if key.startswith("_"):
                    continue
                # A hint fills the field of that name, or any field using that extractor ("company_industry").
                if key == "website_url" and isinstance(value, str):
                    value = homepage(value)  # a registry pointing at an inner page names the site's root
                if key in PROOF_KEYS:
                    confidence = proof_confidence(row.hint.get("uses_technology", ""), row.hint.get("_strength", 0))
                elif row.method in REGISTRY_METHODS:
                    # A curated registry label beats what a page calls itself ("JNJ.com").
                    confidence = REGISTRY_CONFIDENCE.get(key, 0.7)
                elif key == "company_name" and row.method in PROOF_METHODS:
                    # The name the proof gives ("Manolo Blahnik") is the company the row is about; a page's own
                    # metadata gave "THE MANOLO BLAHNIK ARCHIVES", "foliosociety" and "TECNI" instead.
                    confidence = PROOF_NAME_CONFIDENCE
                else:
                    confidence = 0.7
                # The value came from the source (a Wikidata item, a list page), not from this page.
                source = str(row.hint.get("_source") or "")
                for name in [f.name for f in self.spec.fields if key in (f.name, f.semantic.value)]:
                    candidates.setdefault(name, []).append({
                        "value": value, "method": row.method, "confidence": confidence,
                        "evidence": f"{row.method}: {source}",
                        "source_url": source if source.startswith(("http://", "https://")) else None})
        await self._proof_checks(doc, result, site, final, candidates)
        self._save_page(row.id, final, result, doc, candidates, hint=hint)
        self.save_facts()
        self._note_found(final, found, row.depth)
        done = self._site_complete(site, candidates)
        for url_id, page_result, page in checked:  # read to check the country, so kept like any page of the site
            page_found = self._extracted(page)
            page_candidates = {name: [c.__dict__ for c in cands] for name, cands in page_found.items() if cands}
            await self._proof_checks(page, page_result, site, page.url, page_candidates)
            self._save_page(url_id, page.url, page_result, page, page_candidates)
            self._note_found(page.url, page_found, 1)
            done = done or self._site_complete(site, page_candidates)
        if done:
            return  # every detail is in hand: the rest of the site's pages are left for other sites' turn
        new: list[dict[str, Any]] = []
        origin = final.split("/", 3)[0] + "//" + final.split("/", 3)[2]
        if row.depth == 0:
            from_sitemap = await self._sitemap_urls(origin)
            if from_sitemap:
                self.note("links", f"Found {len(from_sitemap)} page(s) of {site} in its sitemap", final)
            new += from_sitemap
        if self.spec.crawl.follow_links and row.depth < self.spec.crawl.max_depth:
            for link, _text in doc.links[:500]:
                if registered_domain(link) in self.allowed_sites and looks_like_page(link):
                    new.append({"url": link, "method": "link", "depth": row.depth + 1, "referrer": final})
        # Only a site's page budget can be read, so queue about twice that, the most useful pages first,
        # instead of thousands of links that would be skipped anyway.
        room = self.spec.crawl.max_pages_per_site * 2 - self.site_queued.get(site, 0)
        kws = self.spec.crawl.priority_keywords
        new.sort(key=lambda it: _page_rank(it["url"], kws))
        new = new[:max(room, 0)]
        added = self.add_urls(new)
        self.site_queued[site] = self.site_queued.get(site, 0) + added
        if added:
            self.note("links", f"Queued {added} new page(s) of {site} to read", final)

    async def _check_site_proof(self, doc, site: str, candidates: dict[str, list[dict[str, Any]]]) -> None:
        piece = await self.site_proof.check(doc, site, self.site_names.get(site, ""))
        if piece is not None:
            short = doc.url.split("://", 1)[-1].removeprefix("www.").rstrip("/")
            self._use_proof(piece, f"on {short}", doc.url, candidates)

    async def _check_code(self, doc, headers: list[tuple[str, str]], site: str,
                          candidates: dict[str, list[dict[str, Any]]]) -> None:
        """The product's fingerprint in the page's scripts, markup, meta tags, headers or cookie names."""
        first = self.site_proof.rules is None
        piece = await self.site_proof.check_code(doc, headers, site, self.site_names.get(site, ""))
        if first and self.site_proof.fingerprints.note:
            self.note("skipped", f"Website code: {self.site_proof.fingerprints.note}", source="proof")
        if piece is not None:
            self._use_proof(piece, f"in {site}'s website code", doc.url, candidates)

    async def _check_job_boards(self, page_html: str, site: str, page_url: str,
                                candidates: dict[str, list[dict[str, Any]]]) -> None:
        """Job boards the page links to: their open jobs are read once per company."""
        def say(kind: str, message: str) -> None:
            self.note(kind, message, page_url, source="jobs")

        pieces = await self.site_proof.check_jobs(page_html, site, self.site_names.get(site, ""), self._fetch_json,
                                                  say)
        for piece in pieces:
            self._use_proof(piece, f"in a job ad of {piece['company']}", page_url, candidates)

    def _use_proof(self, piece: dict[str, Any], where: str, page_url: str,
                   candidates: dict[str, list[dict[str, Any]]]) -> None:
        """Report a piece of proof, save it, and let a kept one fill the row's proof columns."""
        if piece["kept"]:
            self.note("kept", f"Proof {where}: {piece['relationship'].replace('_', ' ')} {piece['product']} "
                              f"({piece['verdict']}): \"{piece['quote'][:160]}\"", piece["url"], source="proof")
            confidence = proof_confidence(piece["verdict"], piece["strength"])
            values = {"uses_technology": piece["verdict"], "evidence": piece["quote"], "evidence_url": piece["url"],
                      "evidence_date": piece["evidence_date"] or None, "evidence_type": piece["source_type"]}
            for name, value in values.items():
                if value and name in {f.name for f in self.spec.fields}:
                    candidates.setdefault(name, []).append({"value": value, "method": "proof",
                                                            "confidence": confidence, "evidence": piece["url"],
                                                            "source_url": piece["url"] or None})
        else:
            self.note("dropped", f"Not proof {where}: {piece['reason']}", piece["url"] or page_url, source="proof")
        self.save_evidence("proof", [piece])

    async def _fetch_json(self, url: str) -> Any:
        """A public JSON API (a job board), through the same robots rules, politeness and address checks."""
        decision = await self.robots.check(url)
        if not decision.allowed:
            raise FetchError("robots", decision.reason, retryable=False)
        fetcher = Fetcher(self.client, self.politeness, self.resolver,
                          allowed_types=("application/json", "text/json", "text/plain", ""))
        result = await fetcher.fetch(url, attempts=2)
        return json.loads(result.text)

    def _usable(self, name: str, value: Any) -> bool:
        spec = self.fields_by_name.get(name)
        if spec is None:
            return bool(value)
        try:
            return normalize_value(spec, value) not in (None, "", [])
        except InvalidValue:
            return False

    def _site_complete(self, site: str, candidates: dict[str, list[dict[str, Any]]]) -> bool:
        """True once every detail that can be found has been found for this site; its queued pages are skipped."""
        if self.spec.record_scope != "site" or not self.wanted_fields:
            return False
        have = self.site_found.setdefault(site, set())
        # Only values the record would keep count: a phone or email that fails validation is not "found"
        # (Delek's site was left as done with no email or phone at all).
        have.update(name for name, cands in candidates.items()
                    if any(self._usable(name, c.get("value")) for c in cands))
        missing = self.wanted_fields - have
        if self.site_proof is not None:
            # A technology question also needs confirmed proof; a weaker piece may still be bettered.
            missing |= set() if site in self.site_proof.proven or site in self.site_proof.hint_confirmed \
                else {"uses_technology"}
        if missing:
            return False
        self.done_sites.add(site)
        with session_scope(self.org_id) as db:
            skipped = db.execute(update(DiscoveredUrl).where(
                DiscoveredUrl.job_id == self.job_id, DiscoveredUrl.status == UrlStatus.queued,
                func.lower(DiscoveredUrl.host).like(f"%{site}")).values(
                status=UrlStatus.skipped, status_reason="every detail was already found on this site")).rowcount
        pages = self._site_page_count(site)
        self.note("kept", f"Every detail found for {site} after {pages} page(s); moving on"
                          + (f" ({skipped} queued page(s) left unread)" if skipped else ""), site=site)
        return True

    def _note_found(self, url: str, found: dict[str, list[Any]], depth: int) -> None:
        """"Found phone +1 858 812 7300, email info@example.com on example.com/contact"."""
        # The site's own address and name are on every page; they are news only on the homepage.
        every_page = {Semantic.website_url, Semantic.page_title, Semantic.description, Semantic.social_links}
        if depth:
            every_page |= {Semantic.company_name}
        labels = {f.name: (f.label or f.name.replace("_", " ")) for f in self.spec.fields
                  if f.semantic not in every_page}
        parts = []
        for name, cands in found.items():
            if cands and name in labels:
                best = max(cands, key=lambda c: c.confidence)
                value = str(best.value)
                parts.append(f"{labels[name].lower()} {value[:60] + '...' if len(value) > 60 else value}")
        if parts:
            short = url.split("://", 1)[-1].removeprefix("www.").rstrip("/")
            self.note("found", f"Found {', '.join(parts[:4])}" + (f" and {len(parts) - 4} more" if len(parts) > 4
                                                                  else "") + f" on {short}", url,
                      fields=sorted(n for n, c in found.items() if c))

    def refresh_records(self) -> None:
        """Assemble the records from the pages read so far, so they show while the crawl runs."""
        if self.max_records is None:
            return
        from app.services.finalize import finalize_job

        stats = finalize_job(self.job_id, self.org_id, self.spec, self.max_records)
        if (stats["records"], stats["valid"]) != self.last_records:
            self.last_records = (stats["records"], stats["valid"])
            self.note("records", f"{stats['records']} record(s) so far ({stats['valid']} complete)",
                      records=stats["records"])

    # --- the loop ---------------------------------------------------------------------------

    async def run(self) -> dict[str, int]:
        if not self.allowed_sites:
            self._restore_scope()
            self._load_policies()
        self.counts_cache = self.counts()
        flusher = asyncio.create_task(self._flush_every_second())
        last_records = time.monotonic()
        # A pool of workers, each taking the next page as soon as it is done, from a site no other worker is
        # reading: one slow site (a timeout, a model call, a robots delay) no longer holds up all the others.
        self.stopping = False
        self.busy_hosts: dict[str, int] = {}
        self.active = 0
        workers = [asyncio.create_task(self._worker()) for _ in range(self.settings.global_concurrency)]
        try:
            while not all(w.done() for w in workers):
                await asyncio.wait(workers, timeout=1, return_when=asyncio.FIRST_EXCEPTION)
                for w in workers:
                    if w.done() and not w.cancelled() and w.exception() is not None:
                        raise w.exception()
                self.counts_cache = self.counts()
                self._check_job()
                if time.monotonic() - self.started > self.settings.max_job_seconds and not self.stopping:
                    self.stopping = True
                    with session_scope(self.org_id) as db:
                        log_event(db, self.org_id, self.job_id, "warning", "Job reached its time limit")
                if time.monotonic() - last_records > RECORDS_EVERY:
                    last_records = time.monotonic()
                    try:
                        self.refresh_records()
                    except Exception:  # noqa: BLE001 - the final pass after the crawl builds them anyway
                        log.exception("could not refresh records during the crawl")
        finally:
            self.stopping = True
            for w in workers:
                w.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
            self.counts_cache = self.counts()
            flusher.cancel()
            try:
                self.flush_activity()
            except Exception:  # noqa: BLE001
                log.exception("could not save activity")
            with session_scope(self.org_id) as db:
                if self.country_checks:  # whether the "only these countries" check, not search, limited the output
                    c = self.country_checks
                    log_event(db, self.org_id, self.job_id, "info",
                              f"Country check (only {', '.join(self.spec.discovery.countries)}): "
                              f"{c.get(IN_COUNTRY, 0)} site(s) confirmed in the country, "
                              f"{c.get(OUTSIDE_COUNTRY, 0)} confirmed outside it, "
                              f"{c.get(COUNTRY_UNKNOWN, 0)} not confirmed either way (left out)")
                # Anything still queued when the budget ran out is recorded as skipped.
                if self.counts_cache.get("fetched", 0) >= self.spec.crawl.max_pages:
                    db.execute(update(DiscoveredUrl).where(
                        DiscoveredUrl.job_id == self.job_id, DiscoveredUrl.status == UrlStatus.queued
                    ).values(status=UrlStatus.skipped, status_reason="job page budget reached"))
            if self.client is not None:
                await self.client.aclose()
            await self.site_checker.aclose()
            if self.site_proof is not None:
                try:
                    self.save_evidence("site", self.site_proof.without_proof(self.site_names))
                except Exception:  # noqa: BLE001 - the Rejected sheet is a report; it must not fail the job
                    log.exception("could not save the sites without proof")
                await self.site_proof.aclose()
        self.counts_cache = self.counts()
        return self.counts_cache
