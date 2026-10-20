"""The crawl of one job: seed the frontier, fetch eligible pages, extract candidates per page.

Progress is checkpointed in Postgres after every page, so a crashed worker resumes where it
stopped. No database transaction is held open while a page is being fetched.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import timedelta
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
    host_of,
    looks_like_page,
    normalize_url,
    registered_domain,
    url_hash,
)
from app.db import session_scope, utcnow
from app.discovery.providers import DiscoveryError, providers_for
from app.extract.deterministic import extract_page, parse_page
from app.models import CrawlJob, DiscoveredUrl, DomainPolicy, FetchedPage, UrlStatus
from app.services.state_machine import log_event
from app.spec.models import ExtractionSpec

log = logging.getLogger("webdata.crawl")
LEASE = timedelta(minutes=5)


class JobCancelled(Exception):
    pass


def _priority(url: str, depth: int, keywords: list[str]) -> int:
    path = url.lower()
    boost = 30 if any(k in path for k in keywords) else 0
    return depth * 50 + 50 - boost


class CrawlRunner:
    def __init__(self, job_id: uuid.UUID, org_id: uuid.UUID, spec: ExtractionSpec, *, resolver=None,
                 redis=None, client=None) -> None:
        self.job_id, self.org_id, self.spec = job_id, org_id, spec
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
        for provider in providers_for(self.spec):
            try:
                for r in await provider.discover(self.spec):
                    site = registered_domain(r.url)
                    # One entry per website: the first source wins (Wikidata runs first and carries names).
                    if r.method != "seed" and (site in sites or found >= self.spec.discovery.max_results):
                        continue
                    found += r.method != "seed"
                    sites.add(site)
                    items.append({"url": r.url, "method": r.method, "hint": r.hint, "referrer": r.referrer})
            except DiscoveryError as exc:
                errors.append(f"{provider.name}: {exc}")
            notes += getattr(provider, "notes", [])
        with session_scope(self.org_id) as db:
            for e in errors:
                log_event(db, self.org_id, self.job_id, "warning", f"Discovery problem: {e}")
            for n in notes:
                log_event(db, self.org_id, self.job_id, "info", f"Discovery note: {n}")
            log_event(db, self.org_id, self.job_id, "info", f"Discovery found {len(items)} starting URL(s)")
        if not items and errors:
            raise DiscoveryError("; ".join(errors))
        self.allowed_sites = {registered_domain(i["url"]) for i in items}
        self.allowed_sites |= {registered_domain(d) for d in self.spec.crawl.allowed_domains}
        return self.add_urls(items)

    def _restore_scope(self) -> None:
        """On resume, the crawl scope is the set of sites the seeds belonged to."""
        with session_scope(self.org_id) as db:
            seeds = db.execute(select(DiscoveredUrl.url).where(
                DiscoveredUrl.job_id == self.job_id, DiscoveredUrl.depth == 0)).scalars().all()
        self.allowed_sites = {registered_domain(u) for u in seeds}
        self.allowed_sites |= {registered_domain(d) for d in self.spec.crawl.allowed_domains}

    def claim(self, n: int) -> list[DiscoveredUrl]:
        now = utcnow()
        with session_scope(self.org_id) as db:
            # Leases left behind by a crashed worker are released first.
            db.execute(update(DiscoveredUrl).where(
                DiscoveredUrl.job_id == self.job_id, DiscoveredUrl.status == UrlStatus.in_progress,
                DiscoveredUrl.lease_until < now).values(status=UrlStatus.queued))
            rows = db.execute(
                select(DiscoveredUrl).where(DiscoveredUrl.job_id == self.job_id,
                                            DiscoveredUrl.status == UrlStatus.queued)
                .order_by(DiscoveredUrl.priority, DiscoveredUrl.discovered_at).limit(n)
                .with_for_update(skip_locked=True)).scalars().all()
            for r in rows:
                r.status = UrlStatus.in_progress
                r.lease_until = now + LEASE
                r.attempts += 1
            return list(rows)

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
        preferred = [u for u in found if any(k in u.lower() for k in kws)]
        chosen = list(dict.fromkeys(preferred + found))[: self.spec.crawl.max_pages_per_site * 2]
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
        if self._site_page_count(site) >= self.spec.crawl.max_pages_per_site:
            self._finish(row.id, UrlStatus.skipped, "page budget for this site reached")
            return
        decision = await self.robots.check(url)
        if not decision.allowed:
            self._finish(row.id, UrlStatus.blocked_robots, decision.reason)
            return
        delay = self.robots.crawl_delay(url)
        if delay:
            self.politeness.host_delay[host_of(url)] = min(delay, 30.0)
        sem = self.host_sem.setdefault(host_of(url), asyncio.Semaphore(self.settings.per_domain_concurrency))
        async with sem:
            try:
                result = await self.fetcher.fetch(url, attempts=1)
            except FetchError as exc:
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
            return
        doc = parse_page(final, result.text)
        found = extract_page(doc, self.spec.fields)
        candidates = {name: [c.__dict__ for c in cands] for name, cands in found.items() if cands}
        if row.hint:  # values supplied by discovery (e.g. Wikidata) with their source
            for key, value in row.hint.items():
                if key.startswith("_"):
                    continue
                # A hint fills the field of that name, or any field using that extractor ("company_industry").
                for name in [f.name for f in self.spec.fields if key in (f.name, f.semantic.value)]:
                    candidates.setdefault(name, []).append({
                        # A curated registry label beats what a page calls itself ("JNJ.com").
                        "value": value, "method": row.method,
                        "confidence": 0.92 if row.method in ("wikidata", "sec_edgar") and key == "company_name"
                        else 0.7,
                        "evidence": f"{row.method}: {row.hint.get('_source', '')}"})
        with session_scope(self.org_id) as db:
            db.add(FetchedPage(org_id=self.org_id, job_id=self.job_id, url_id=row.id, final_url=final,
                               http_status=result.status, content_type=result.content_type[:128],
                               bytes=len(result.body), content_hash=result.sha256, title=doc.title[:1000],
                               text_excerpt=doc.text[:2000], candidates=candidates))
            db.execute(update(DiscoveredUrl).where(DiscoveredUrl.id == row.id).values(
                status=UrlStatus.fetched, status_reason=None, lease_until=None))
        new: list[dict[str, Any]] = []
        origin = final.split("/", 3)[0] + "//" + final.split("/", 3)[2]
        if row.depth == 0:
            new += await self._sitemap_urls(origin)
        if self.spec.crawl.follow_links and row.depth < self.spec.crawl.max_depth:
            for link, _text in doc.links[:500]:
                if registered_domain(link) in self.allowed_sites and looks_like_page(link):
                    new.append({"url": link, "method": "link", "depth": row.depth + 1, "referrer": final})
        self.add_urls(new)

    # --- the loop ---------------------------------------------------------------------------

    async def run(self) -> dict[str, int]:
        if not self.allowed_sites:
            self._restore_scope()
            self._load_policies()
        self.counts_cache = self.counts()
        try:
            while True:
                self._check_job()
                if time.monotonic() - self.started > self.settings.max_job_seconds:
                    with session_scope(self.org_id) as db:
                        log_event(db, self.org_id, self.job_id, "warning", "Job reached its time limit")
                    break
                if self.counts_cache["fetched"] >= self.spec.crawl.max_pages:
                    break
                budget = self.spec.crawl.max_pages - self.counts_cache["fetched"]
                batch = self.claim(min(self.settings.global_concurrency, budget))
                if not batch:
                    break
                await asyncio.gather(*(self.process(r) for r in batch))
                self.counts_cache = self.counts()
        finally:
            with session_scope(self.org_id) as db:
                # Anything still queued when the budget ran out is recorded as skipped.
                if self.counts_cache.get("fetched", 0) >= self.spec.crawl.max_pages:
                    db.execute(update(DiscoveredUrl).where(
                        DiscoveredUrl.job_id == self.job_id, DiscoveredUrl.status == UrlStatus.queued
                    ).values(status=UrlStatus.skipped, status_reason="job page budget reached"))
            if self.client is not None:
                await self.client.aclose()
        self.counts_cache = self.counts()
        return self.counts_cache
