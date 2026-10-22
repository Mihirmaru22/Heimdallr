"""The crawl of one job: seed the frontier, fetch eligible pages, extract candidates per page.

Progress is checkpointed in Postgres after every page, so a crashed worker resumes where it
stopped. No database transaction is held open while a page is being fetched.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import timedelta
from itertools import zip_longest
from typing import Any

from selectolax.lexbor import LexborHTMLParser as HTMLParser
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.crawl.fetcher import Fetcher, FetchError
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
from app.discovery.relevance import off_topic_reason, outside_countries_reason
from app.discovery.sitecheck import SiteChecker
from app.evidence.judge import proof_confidence
from app.evidence.site import SiteProof
from app.extract.deterministic import extract_page, parse_page, prefer_country_emails, prefer_country_phones
from app.extract.normalize import InvalidValue, normalize_value
from app.extract.records import CONTACT_HINTS, _has_extractor
from app.models import (
    CrawlJob,
    CrawlJobEvent,
    DiscoveredUrl,
    DomainPolicy,
    Evidence,
    FetchedPage,
    UrlStatus,
)
from app.services.state_machine import log_event
from app.spec.models import ExtractionSpec, Semantic

log = logging.getLogger("webdata.crawl")
# A registry's name, official website and founding year beat what pages say ("JNJ.com"; a JSON-LD url on
# cascade.boeing.com; "our plant was established in 2007").
REGISTRY_CONFIDENCE = {"company_name": 0.92, "website_url": 0.93, "founded_year": 0.85}
# Proof columns: one piece of proof fills all of them, and the strongest piece wins (see proof_confidence).
PROOF_KEYS = ("uses_technology", "evidence", "evidence_url", "evidence_date", "evidence_type")
REGISTRY_METHODS = ("wikidata", "sec_edgar", "gleif", "sec_filings")
LEASE = timedelta(minutes=5)
SOURCE_NAMES = {"seeds": "your starting websites", "wikidata": "Wikidata", "sec_edgar": "SEC EDGAR",
                "gleif": "GLEIF", "searxng": "web search", "sec_filings": "SEC filings"}
RECORDS_EVERY = 20.0  # seconds between refreshes of the records shown while the crawl is still running


class JobCancelled(Exception):
    pass


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
        self.settings = get_settings()
        self.resolver = resolver
        self.client = client or (make_client(resolver=resolver) if resolver else make_client())
        delay = self.settings.per_domain_delay_seconds
        if redis == "auto":
            import redis.asyncio as aioredis

            redis = aioredis.from_url(self.settings.redis_url)
        self.politeness = RedisPoliteness(redis, delay) if redis is not None else LocalPoliteness(delay)
        self.fetcher = Fetcher(self.client, self.politeness, resolver)
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
        try:
            for provider in providers_for(self.spec):
                label = SOURCE_NAMES.get(provider.name, provider.name)
                if provider.name != "seeds":
                    self.note("search", self._discovery_line(provider.name), source=provider.name)
                    self.flush_activity()
                if hasattr(provider, "on_note"):
                    provider.on_note = self.note
                try:
                    results = await provider.discover(self.spec)
                    per_provider.append(results)
                    if provider.name != "seeds":
                        self.note("search", f"{label[0].upper()}{label[1:]} returned {len(results)} website(s)",
                                  source=provider.name)
                except DiscoveryError as exc:
                    errors.append(f"{provider.name}: {exc}")
                    self.note("failed", f"{label}: {exc}", source=provider.name)
                self.save_evidence(provider.name, getattr(provider, "evidence", []))
                self.flush_activity()
                notes += getattr(provider, "notes", [])
        finally:
            flusher.cancel()
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
        if registered_domain(final) not in self.allowed_sites:
            self._finish(row.id, UrlStatus.skipped, f"redirected outside the crawl scope to {host_of(final)}")
            return
        with session_scope(self.org_id) as db:
            duplicate = db.execute(select(FetchedPage.id).where(
                FetchedPage.job_id == self.job_id, FetchedPage.content_hash == result.sha256)).first()
        if duplicate:
            self._finish(row.id, UrlStatus.skipped, "same content as a page already fetched")
            self.note("skipped", f"Skipped {final}: same content as a page already read", final)
            return
        doc = parse_page(final, result.text)
        if row.depth == 0 and row.method in ("searxng", "wikidata"):
            # A search result is only a link, and anyone can tag their own Wikidata item with an industry;
            # check the homepage before spending crawl budget on the site.
            reason = off_topic_reason(doc, self.spec, check_country=row.method == "searxng")
            if not reason and row.method == "searxng":
                # Mentioning the industry is not being in it: lists, associations, shops and IT firms do too.
                reason, by = await self.site_checker.check(doc, self.spec)
                if not reason and by.startswith("model:"):
                    self.note("search", f"Checked {site} with free model {by[6:]}: a company in the industry", final)
                elif by.startswith("unchecked") and not self.told_unchecked:
                    self.told_unchecked = True
                    self.note("skipped", f"Web search results are not checked by a model ({by[11:]}); "
                                         "only rules are applied", final)
            if reason:
                self.allowed_sites.discard(site)
                self._finish(row.id, UrlStatus.skipped, f"{row.method} result dropped: {reason}")
                self.note("dropped", f"Dropped {site}: {reason}", final)
                return
        if row.depth == 0:
            reason = outside_countries_reason(doc, self.spec, row.method, row.hint)
            if reason:  # "only these countries" is on: the site is left out entirely
                self.allowed_sites.discard(site)
                self._finish(row.id, UrlStatus.skipped, f"outside the requested countries: {reason}")
                self.note("dropped", f"Dropped {site}: {reason}", final)
                return
            self.note("kept", f"Kept {site}" + (f" ({row.hint['company_name']})" if row.hint.get("company_name")
                                                else "") + ": homepage checks passed", final)
        found = extract_page(doc, self.spec.fields)
        for f in self.spec.fields:
            if f.semantic == Semantic.phone and f.name in found:
                prefer_country_phones(found[f.name], self.spec.discovery.countries)
            if f.semantic == Semantic.contact_email and f.name in found:
                prefer_country_emails(found[f.name], self.spec.discovery.countries)
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
                else:
                    confidence = 0.7
                for name in [f.name for f in self.spec.fields if key in (f.name, f.semantic.value)]:
                    candidates.setdefault(name, []).append({
                        "value": value, "method": row.method, "confidence": confidence,
                        "evidence": f"{row.method}: {row.hint.get('_source', '')}"})
        if self.site_proof is not None:
            await self._check_site_proof(doc, site, candidates)
            await self._check_job_boards(result.text, site, final, candidates)
        with session_scope(self.org_id) as db:
            db.add(FetchedPage(org_id=self.org_id, job_id=self.job_id, url_id=row.id, final_url=final,
                               http_status=result.status, content_type=result.content_type[:128],
                               bytes=len(result.body), content_hash=result.sha256, title=doc.title[:1000],
                               text_excerpt=doc.text[:2000], candidates=candidates))
            db.execute(update(DiscoveredUrl).where(DiscoveredUrl.id == row.id).values(
                status=UrlStatus.fetched, status_reason=None, lease_until=None))
        self._note_found(final, found, row.depth)
        if self._site_complete(site, candidates):
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
                                                            "confidence": confidence, "evidence": piece["url"]})
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
