"""Controlled Live-Web Retriever and Security Controller.

Enforces:
- Configurable per-task request budget (max 10) and duration budget (max 30s)
- Per-host rate limits (max 3 requests per domain)
- Strict P0.1 SSRF defenses via SearchPipeline.is_safe_url & create_safe_async_client
- Mandatory TLS verification and multi-hop redirect validation
- Bounded retries and exponential backoff
- URL deduplication and SHA-256 content hashing
- Sanitized snapshot archiving for reproducibility
- Source independence profiling (raw sources vs independent publishers)
- Dual interface: acts as a live search controller and as an InvestigationEngine corpus
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
import re
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from argus.investigation.benchmark.corpus import InvestigationDocument
from argus.investigation.live_web.models import (
    ControlledRetrievalLimits,
    LiveWebEvidenceRecord,
    SourceIndependenceProfile,
)
from argus.search.pipeline import SearchPipeline, create_safe_async_client
from argus.search.wikipedia import research_user_agent

logger = logging.getLogger(__name__)

ROBOTS_AGENT = "Heimdallr-Research-Bot"

SNAPSHOT_DIR = Path("/data/shared/project/PlayGround/Argus/evals/evidence_snapshots")


class ControlledLiveWebRetriever:
    """Live web retriever with strict security, rate limiting, and source independence analysis."""

    def __init__(
        self,
        limits: ControlledRetrievalLimits | None = None,
        snapshot_dir: Path | str | None = None,
    ) -> None:
        self.limits = limits or ControlledRetrievalLimits()
        self.snapshot_dir = Path(snapshot_dir or SNAPSHOT_DIR)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

        self.requests_made = 0
        self.start_time = time.perf_counter()
        self.host_counts: dict[str, int] = {}
        self.seen_urls: set[str] = set()
        self.evidence_records: list[LiveWebEvidenceRecord] = []
        self.cached_documents: dict[str, InvestigationDocument] = {}
        self._discoverable_entities: set[str] = set()
        self._robots: dict[str, tuple[Any, str]] = {}

    def reset_task_budget(self) -> None:
        """Reset counters for a new investigation task."""
        self.requests_made = 0
        self.start_time = time.perf_counter()
        self.host_counts.clear()
        self.seen_urls.clear()
        self.evidence_records.clear()
        self.cached_documents.clear()

    def _canonicalize_url(self, url: str) -> str:
        """Normalize URL: lower-case host, remove tracking query params and fragments."""
        parsed = urlparse(url.strip())
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = parsed.path.rstrip("/")
        # Filter out common analytics and tracking parameters
        query_parts = []
        if parsed.query:
            for param in parsed.query.split("&"):
                k = param.split("=")[0].lower()
                if not any(k.startswith(p) for p in ("utm_", "fbclid", "gclid", "ref", "source")):
                    query_parts.append(param)
        clean_query = "&".join(sorted(query_parts))
        return f"{parsed.scheme.lower()}://{netloc}{path}" + (f"?{clean_query}" if clean_query else "")

    def is_url_permitted(self, url: str) -> tuple[bool, str | None]:
        """Verify URL complies with P0.1 SSRF policy, scheme whitelist, and per-host limits."""
        parsed = urlparse(url)
        if parsed.scheme.lower() not in ("http", "https"):
            return False, f"Prohibited scheme: {parsed.scheme}"

        # 1. SSRF and IP safety check via SearchPipeline.is_safe_url
        if self.limits.enforce_ssrf_protection:
            if not SearchPipeline.is_safe_url(url):
                return False, f"SSRF rejection: URL failed safe IP destination policy: {url}"

        # 2. Host budget limit
        host = parsed.netloc.lower()
        count = self.host_counts.get(host, 0)
        if count >= self.limits.max_requests_per_host:
            return False, f"Per-host limit reached ({count}/{self.limits.max_requests_per_host}) for {host}"

        # 3. Overall task request budget
        if self.requests_made >= self.limits.max_requests_per_task:
            return False, f"Task request budget exhausted ({self.requests_made}/{self.limits.max_requests_per_task})"

        # 4. Overall task time budget
        elapsed = time.perf_counter() - self.start_time
        if elapsed >= self.limits.max_duration_seconds:
            return False, f"Task duration budget exceeded ({round(elapsed, 1)}s/{self.limits.max_duration_seconds}s)"

        return True, None

    def is_known_blocked(self, url: str) -> bool:
        """True when this site's robots.txt, already fetched, rules the URL out (no network call)."""
        parsed = urlparse(url)
        cached = self._robots.get(f"{parsed.scheme}://{parsed.netloc.lower()}")
        if cached is None:
            return False
        parser, _ = cached
        return parser is None or not parser.can_fetch(ROBOTS_AGENT, url)

    async def _robots_allows(self, url: str) -> tuple[bool, str | None]:
        """Honour the site's robots.txt for our user agent (RFC 9309), cached per host.

        A missing robots.txt (4xx) allows everything; an unreachable one (5xx or no
        connection) is treated as disallowing, as the RFC requires.
        """
        from urllib.robotparser import RobotFileParser

        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc.lower()}"
        if origin not in self._robots:
            parser: RobotFileParser | None = RobotFileParser()
            status_note = ""
            try:
                async with create_safe_async_client(timeout=self.limits.request_timeout_seconds) as client:
                    resp = await client.get(f"{origin}/robots.txt", headers={"User-Agent": ROBOTS_AGENT}, follow_redirects=True)
                if 400 <= resp.status_code < 500:
                    parser.parse([])
                elif resp.status_code >= 500:
                    parser, status_note = None, f"HTTP {resp.status_code}"
                else:
                    parser.parse(resp.text.splitlines())
            except Exception as exc:
                parser, status_note = None, type(exc).__name__
            self._robots[origin] = (parser, status_note)
        parser, note = self._robots[origin]
        if parser is None:
            return False, f"robots.txt for {parsed.netloc} unreachable ({note}); not fetching"
        if not parser.can_fetch(ROBOTS_AGENT, url):
            return False, f"robots.txt of {parsed.netloc} disallows this page"
        return True, None

    async def fetch_url_content(self, url: str) -> LiveWebEvidenceRecord:
        """Fetch URL content through safe client with redirect validation, size limits, and timeouts."""
        canon = self._canonicalize_url(url)
        if canon in self.seen_urls:
            logger.info("URL deduplicated: %s", canon)
            return LiveWebEvidenceRecord(
                evidence_id=f"ev_dup_{hashlib.md5(canon.encode()).hexdigest()[:8]}",
                original_url=url,
                final_url=canon,
                retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
                http_status=304,
                title="Deduplicated Resource",
                domain=urlparse(canon).netloc,
                publisher="",
                extracted_text="",
                content_hash="",
                source_type="live_web",
                extraction_method="deduplication_cache",
                is_duplicate=True,
                canonical_url=canon,
            )

        permitted, reason = self.is_url_permitted(url)
        if not permitted:
            logger.warning("Fetch denied by policy: %s (%s)", url, reason)
            denied = LiveWebEvidenceRecord(
                evidence_id=f"ev_err_{hashlib.md5(url.encode()).hexdigest()[:8]}",
                original_url=url,
                final_url=url,
                retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
                http_status=403,
                title="Policy Rejection",
                domain=urlparse(url).netloc,
                publisher="",
                extracted_text="",
                content_hash="",
                source_type="live_web",
                extraction_method="blocked",
                retrieval_error=reason,
            )
            # Keep the denial visible to the investigation loop, like search denials.
            self.evidence_records.append(denied)
            return denied

        if self.limits.respect_robots_txt:
            allowed, robots_reason = await self._robots_allows(url)
            if not allowed:
                denied = LiveWebEvidenceRecord(
                    evidence_id=f"ev_err_{hashlib.md5(url.encode()).hexdigest()[:8]}",
                    original_url=url,
                    final_url=url,
                    retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
                    http_status=403,
                    title="Policy Rejection",
                    domain=urlparse(url).netloc,
                    publisher="",
                    extracted_text="",
                    content_hash="",
                    source_type="live_web",
                    extraction_method="blocked",
                    retrieval_error=robots_reason,
                )
                self.evidence_records.append(denied)
                return denied

        host = urlparse(url).netloc.lower()
        self.host_counts[host] = self.host_counts.get(host, 0) + 1
        self.requests_made += 1
        self.seen_urls.add(canon)

        client = create_safe_async_client()
        headers = {
            "User-Agent": research_user_agent().replace("Heimdallr-Research", ROBOTS_AGENT),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        retries = 0
        backoff = 0.5
        final_url = url
        http_status = 0
        raw_content = ""
        raw_bytes = b""
        content_type = ""
        error_msg = None

        while retries <= self.limits.max_retries:
            try:
                resp = await client.get(
                    url,
                    headers=headers,
                    timeout=self.limits.request_timeout_seconds,
                    follow_redirects=True,
                )
                final_url = str(resp.url)

                # Validate final redirect destination
                if not SearchPipeline.is_safe_url(final_url):
                    error_msg = f"SSRF rejection on redirected location: {final_url}"
                    http_status = 403
                    break

                http_status = resp.status_code
                if http_status == 429:  # Rate limited
                    logger.warning("Rate limited (429) on %s, backing off %0.2fs", url, backoff)
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
                    retries += 1
                    continue

                if http_status == 200:
                    raw_bytes = resp.content[:self.limits.max_response_bytes]
                    content_type = resp.headers.get("content-type", "")
                    raw_content = "ok" if raw_bytes else ""
                    break
                else:
                    error_msg = f"HTTP {http_status}"
                    break
            except Exception as exc:
                error_msg = str(exc)
                retries += 1
                await asyncio.sleep(backoff)
                backoff *= 2.0
            finally:
                if retries > self.limits.max_retries or (http_status == 200 and raw_content):
                    await client.aclose()

        # Extract title and readable text (main content, JSON-LD job posts, PDF text)
        extracted_text = ""
        title = ""
        extraction_method = "safe_html_text"
        if raw_content:
            from argus.investigation.live_web.page_reader import read_page

            page = read_page(raw_bytes, content_type, fallback_title=urlparse(final_url).netloc)
            title, extracted_text, extraction_method = page.title, page.text, page.method
            if page.note and not extracted_text:
                error_msg = page.note

        content_hash = hashlib.sha256(extracted_text.encode("utf-8")).hexdigest() if extracted_text else ""

        # Archive snapshot for evaluation reproducibility
        if extracted_text:
            snapshot_file = self.snapshot_dir / f"{content_hash[:16]}.txt"
            if not snapshot_file.exists():
                snapshot_file.write_text(f"URL: {final_url}\nDATE: {datetime.now(timezone.utc).isoformat()}\n\n{extracted_text}", encoding="utf-8")

        domain = urlparse(final_url).netloc
        ev_record = LiveWebEvidenceRecord(
            evidence_id=f"ev_web_{content_hash[:8] if content_hash else hashlib.md5(url.encode()).hexdigest()[:8]}",
            original_url=url,
            final_url=final_url,
            retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
            http_status=http_status,
            title=title or domain,
            domain=domain,
            publisher=domain,
            extracted_text=extracted_text,
            content_hash=content_hash,
            source_type="live_web",
            extraction_method=extraction_method,
            retrieval_error=error_msg,
            canonical_url=canon,
        )
        self.evidence_records.append(ev_record)
        return ev_record

    def compute_source_independence(self) -> SourceIndependenceProfile:
        """Analyze independence across retrieved web evidence records."""
        valid_records = [r for r in self.evidence_records if r.http_status == 200 and not r.is_duplicate]
        raw_count = len(valid_records)

        # Unique publishers / domains
        domain_set = {r.domain for r in valid_records if r.domain}
        content_hashes = {r.content_hash for r in valid_records if r.content_hash}

        # Independent sources estimation
        # Count distinct domains that have distinct content hashes
        independent_count = min(len(domain_set), len(content_hashes)) if domain_set else 0
        duplicate_count = sum(1 for r in self.evidence_records if r.is_duplicate)
        syndicated_count = max(0, raw_count - independent_count)

        ratio = round(independent_count / raw_count, 4) if raw_count > 0 else 0.0
        if ratio >= 0.8:
            classification = "HIGH"
        elif ratio >= 0.5:
            classification = "MODERATE"
        elif ratio > 0.0:
            classification = "LOW"
        else:
            classification = "UNKNOWN"

        return SourceIndependenceProfile(
            raw_source_count=raw_count,
            estimated_independent_source_count=independent_count,
            duplicate_count=duplicate_count,
            syndicated_count=syndicated_count,
            domains_represented=sorted(list(domain_set)),
            independence_ratio=ratio,
            classification=classification,
        )

    # -------------------------------------------------------------------------
    # InvestigationEngine Corpus Interface
    # -------------------------------------------------------------------------
    def register_discoverable_entity(self, entity: str) -> None:
        if entity:
            self._discoverable_entities.add(entity)

    def get_discoverable_entities(self) -> set[str]:
        return set(self._discoverable_entities)

    def _run_async(self, coro: Any) -> Any:
        """Run an asynchronous coroutine synchronously, handling both active and inactive event loops."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()

    @property
    def documents(self) -> dict[str, InvestigationDocument]:
        """Corpus document registry mapping doc_id to InvestigationDocument."""
        return self.cached_documents

    def search(self, query: str, limit: int = 5) -> list[InvestigationDocument]:
        """Execute live search on the configured free sources and return safe InvestigationDocuments."""
        if not query or not query.strip():
            return []
        q_str = query.strip()
        if q_str.startswith(("http://", "https://", "file://")):
            doc = self.get_by_url(q_str)
            return [doc] if doc else []
        return self._run_async(self._async_search(query, limit))

    def get_by_url(self, url: str) -> InvestigationDocument | None:
        """Retrieve live document for a URL, applying SSRF checks, security controls, and rate limits."""
        if not url or not url.strip():
            return None

        clean_url = url.strip()
        canon = self._canonicalize_url(clean_url)

        # Check if already cached with full page content
        for doc in self.cached_documents.values():
            if (doc.url == clean_url or doc.url == canon) and doc.source_type == "live_web":
                return doc

        # Fetch live via secure async fetcher
        record = self._run_async(self.fetch_url_content(clean_url))
        if record and record.http_status in (200, 304) and record.extracted_text:
            doc_id = f"doc_live_{hashlib.md5(record.final_url.encode()).hexdigest()[:8]}"
            doc = InvestigationDocument(
                doc_id=doc_id,
                title=record.title or urlparse(record.final_url).netloc,
                url=record.final_url,
                text_content=record.extracted_text,
                source_type="live_web",
                published_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            )
            self.cached_documents[doc_id] = doc
            return doc

        return None

    def get_document(self, identifier: str) -> InvestigationDocument | None:
        """Lookup document by doc_id or URL, or fetch if it is an HTTP/HTTPS URL."""
        if not identifier or not identifier.strip():
            return None
        ident = identifier.strip()
        if ident in self.cached_documents:
            return self.cached_documents[ident]
        if ident.startswith(("http://", "https://")):
            return self.get_by_url(ident)
        for doc in self.cached_documents.values():
            if doc.doc_id == ident or doc.url == ident:
                return doc
        return None

    def get_by_id(self, doc_id: str) -> InvestigationDocument | None:
        """Lookup document by doc_id."""
        return self.cached_documents.get(doc_id)

    def _search_denial(self, query: str, host: str, reason: str | None) -> None:
        logger.warning("Live search denied by policy for query '%s' on %s: %s", query, host, reason)
        self.evidence_records.append(LiveWebEvidenceRecord(
            evidence_id=f"ev_err_search_{hashlib.md5(f'{host}|{query}'.encode()).hexdigest()[:8]}",
            original_url=f"https://{host}",
            final_url=f"https://{host}",
            retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
            http_status=429 if "budget" in (reason or "").lower() or "limit" in (reason or "").lower() else 403,
            title="Policy Rejection",
            domain=host,
            publisher=host,
            extracted_text="",
            content_hash="",
            source_type="live_search_result",
            extraction_method="blocked",
            retrieval_error=reason,
        ))

    async def _async_search(self, query: str, limit: int = 5) -> list[InvestigationDocument]:
        """Search every configured free source under budget and host accounting, then merge results."""
        from argus.investigation.live_web.search_sources import get_search_source, merge_results
        from argus.search.models import SearchQuery

        want = max(limit, self.limits.min_results_per_search)
        providers = []
        for name in self.limits.search_providers:
            source = get_search_source(name)
            if source is None:
                continue
            permitted, reason = self.is_url_permitted(f"https://{source.host}")
            if not permitted:
                self._search_denial(query, source.host, reason)
                continue
            try:
                provider = source.make(self.limits.request_timeout_seconds)
            except Exception as exc:  # e.g. an optional library missing on this machine
                logger.warning("Search source %s unavailable: %s", source.name, exc)
                continue
            self.host_counts[source.host] = self.host_counts.get(source.host, 0) + 1
            self.requests_made += 1
            providers.append((source, provider))

        async def run(provider):
            return await provider.search(SearchQuery(query=query, num_results=min(50, want)))

        responses = await asyncio.gather(*(run(p) for _, p in providers), return_exceptions=True)
        per_source = []
        for (source, _), resp in zip(providers, responses):
            if isinstance(resp, BaseException):
                logger.warning("Live search error on %s for query '%s': %s", source.name, query, resp)
                continue
            per_source.append((source.name, [r for r in resp.results if r.url]))

        results: list[InvestigationDocument] = []
        for merged in merge_results(per_source, want):
            r = merged.result
            href, title, snippet = r.url, r.title, r.snippet
            doc_id = f"doc_live_{hashlib.md5(href.encode()).hexdigest()[:8]}"
            doc = InvestigationDocument(
                doc_id=doc_id,
                title=title,
                url=href,
                text_content=f"{title}\n\n{snippet}",
                source_type="live_search",
                published_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            )
            self.cached_documents[doc_id] = doc
            results.append(doc)

            # Save snapshot for reproducibility
            snap_hash = hashlib.sha256(snippet.encode()).hexdigest()
            snap_file = self.snapshot_dir / f"{snap_hash[:16]}.txt"
            if not snap_file.exists():
                snap_file.write_text(f"URL: {href}\nTITLE: {title}\nDATE: {datetime.now(timezone.utc).isoformat()}\n\n{snippet}", encoding="utf-8")

            self.evidence_records.append(LiveWebEvidenceRecord(
                evidence_id=f"ev_search_{doc_id}",
                original_url=href,
                final_url=href,
                retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
                http_status=200,
                title=title,
                domain=urlparse(href).netloc,
                publisher=urlparse(href).netloc,
                extracted_text=f"{title}\n{snippet}",
                content_hash=snap_hash,
                source_type="live_search_result",
                extraction_method="ddgs_snippet" if merged.engines == ["duckduckgo"] else "+".join(merged.engines) + "_snippet",
            ))

        return results
