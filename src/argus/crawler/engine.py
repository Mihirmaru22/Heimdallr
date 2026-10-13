from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable
from urllib.parse import urljoin, urldefrag

from bs4 import BeautifulSoup

from crawlee import Request
from crawlee.configuration import Configuration
from crawlee.storage_clients import FileSystemStorageClient, MemoryStorageClient
from crawlee.storages import RequestQueue

from argus.crawler.fetcher import BaseFetcher, TwoTierFetcher
from argus.crawler.models import CrawlRequest, Document
from argus.domain.event import EventType, ResearchEvent
from argus.search.pipeline import SearchPipeline

if TYPE_CHECKING:
    from argus.storage.repository import ArgusRepository

logger = logging.getLogger(__name__)


def sanitize_queue_name(name: str) -> str:
    """Sanitize name for Crawlee storage: only lowercase letters, digits, and hyphens."""
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip()).strip("-").lower()
    return cleaned or "default-queue"


class CrawlExecutionEngine:
    """Manages crawl request lifecycle, queue persistence, deduplication, and execution via Crawlee."""

    def __init__(
        self,
        fetcher: BaseFetcher | None = None,
        repo: ArgusRepository | None = None,
        storage_dir: str | Path | None = None,
        memory_storage: bool = False,
        max_concurrency: int = 5,
        default_max_retries: int = 2,
    ) -> None:
        self.fetcher = fetcher or TwoTierFetcher()
        self.repo = repo
        self.storage_dir = str(storage_dir or Path("data/crawlee_storage"))
        self.memory_storage = memory_storage
        self.max_concurrency = max_concurrency
        self.default_max_retries = default_max_retries
        self._queues: dict[str, RequestQueue] = {}

    def _record_audit_event(
        self,
        event_type: EventType,
        objective_id: str | None,
        task_id: str | None,
        payload: dict[str, Any],
    ) -> None:
        """Record structured crawl lifecycle audit event in Argus repository."""
        if self.repo is not None and objective_id:
            try:
                self.repo.record_event(
                    ResearchEvent(
                        objective_id=objective_id,
                        task_id=task_id,
                        event_type=event_type,
                        payload=payload,
                    )
                )
            except Exception as exc:
                logger.debug("Failed to record crawl audit event: %s", exc)

    async def get_or_create_queue(self, objective_id: str = "default") -> RequestQueue:
        """Retrieve or initialize a persistent/memory Crawlee RequestQueue for the objective."""
        safe_name = sanitize_queue_name(objective_id)
        if safe_name in self._queues:
            return self._queues[safe_name]

        if self.memory_storage:
            storage_client = MemoryStorageClient()
            rq = await RequestQueue.open(name=safe_name, storage_client=storage_client)
        else:
            cfg = Configuration(storage_dir=self.storage_dir, purge_on_start=False)
            rq = await RequestQueue.open(name=safe_name, configuration=cfg)

        self._queues[safe_name] = rq
        return rq

    async def enqueue_request(
        self,
        request: CrawlRequest,
    ) -> tuple[bool, str]:
        """Enqueue a CrawlRequest into the Crawlee queue with strict Argus security checks.

        Returns:
            (is_enqueued: bool, status: str)
            status can be: "enqueued", "duplicate", or "rejected_unsafe"
        """
        self._record_audit_event(
            event_type=EventType.CRAWL_REQUEST_CREATED,
            objective_id=request.objective_id,
            task_id=request.research_task_id,
            payload={
                "request_id": request.request_id,
                "url": request.url,
                "priority": request.priority,
                "depth": request.depth,
            },
        )

        # 1. Security check: Enforce Argus SSRF, cloud metadata, and loopback restrictions
        if not SearchPipeline.is_safe_url(request.url):
            logger.warning("SSRF / Unsafe URL rejected before acquisition: %s", request.url)
            self._record_audit_event(
                event_type=EventType.CRAWL_REQUEST_REJECTED,
                objective_id=request.objective_id,
                task_id=request.research_task_id,
                payload={
                    "request_id": request.request_id,
                    "url": request.url,
                    "reason": "Security policy violation (SSRF / reserved IP / invalid scheme)",
                },
            )
            return False, "rejected_unsafe"

        # 2. Add to Crawlee RequestQueue (provides built-in URL deduplication via unique_key)
        rq = await self.get_or_create_queue(request.objective_id or "default")
        crawlee_req = request.to_crawlee_request()
        op_info = await rq.add_request(crawlee_req)

        if op_info.was_already_present:
            self._record_audit_event(
                event_type=EventType.CRAWL_REQUEST_SKIPPED,
                objective_id=request.objective_id,
                task_id=request.research_task_id,
                payload={
                    "request_id": request.request_id,
                    "url": request.url,
                    "reason": "Duplicate URL already present or handled in queue",
                },
            )
            return False, "duplicate"

        self._record_audit_event(
            event_type=EventType.CRAWL_REQUEST_ENQUEUED,
            objective_id=request.objective_id,
            task_id=request.research_task_id,
            payload={
                "request_id": request.request_id,
                "url": request.url,
                "priority": request.priority,
                "depth": request.depth,
            },
        )
        return True, "enqueued"

    async def enqueue_urls(
        self,
        urls: list[str],
        objective_id: str,
        task_id: str | None = None,
        depth: int = 0,
        priority: int = 1,
        force_browser: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> list[CrawlRequest]:
        """Normalize, build, and enqueue a list of candidate URLs into Crawlee."""
        enqueued: list[CrawlRequest] = []
        for raw_url in urls:
            normalized_url = SearchPipeline.normalize_url(raw_url)
            req = CrawlRequest(
                url=normalized_url,
                objective_id=objective_id,
                research_task_id=task_id,
                task_id=task_id,
                depth=depth,
                priority=priority,
                force_browser=force_browser,
                max_retries=self.default_max_retries,
                metadata=metadata or {},
            )
            ok, _ = await self.enqueue_request(req)
            if ok:
                enqueued.append(req)
        return enqueued

    @staticmethod
    def extract_candidate_links(html: str, base_url: str, max_links: int = 10) -> list[str]:
        """Extract valid absolute HTTP/HTTPS links from HTML text."""
        if not html or not html.strip():
            return []
        soup = BeautifulSoup(html, "html.parser")
        discovered: list[str] = []
        seen: set[str] = set()

        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()
            if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue
            abs_url = urljoin(base_url, href)
            clean_url, _ = urldefrag(abs_url)
            if clean_url.startswith(("http://", "https://")) and clean_url not in seen:
                seen.add(clean_url)
                discovered.append(clean_url)
                if len(discovered) >= max_links:
                    break

        return discovered

    async def discover_and_enqueue_child_links(
        self,
        document: Document,
        parent_request: CrawlRequest,
        max_depth: int = 2,
        max_links: int = 5,
    ) -> list[CrawlRequest]:
        """Dynamically discover hyperlinks on an acquired document and enqueue if within depth limit."""
        if parent_request.depth >= max_depth:
            return []

        links = self.extract_candidate_links(
            html=document.text_content,
            base_url=document.url,
            max_links=max_links,
        )
        if not links:
            return []

        return await self.enqueue_urls(
            urls=links,
            objective_id=parent_request.objective_id or "default",
            task_id=parent_request.research_task_id,
            depth=parent_request.depth + 1,
            priority=max(1, parent_request.priority - 1),
            metadata={"discovered_from": parent_request.url},
        )

    async def process_next_batch(
        self,
        objective_id: str,
        max_pages: int = 3,
        task_id: str | None = None,
        discover_links: bool = False,
        max_depth: int = 2,
    ) -> list[Document]:
        """Acquire up to `max_pages` documents from the persistent Crawlee queue.

        Preserves TwoTierFetcher HTTP-first -> Playwright browser fallback, separates
        crawl failures from research failures, and records full audit lifecycle events.
        """
        rq = await self.get_or_create_queue(objective_id)
        acquired_documents: list[Document] = []
        pages_processed = 0

        while pages_processed < max_pages:
            crawlee_req = await rq.fetch_next_request()
            if crawlee_req is None:
                break

            domain_req = CrawlRequest.from_crawlee_request(crawlee_req)
            effective_task_id = domain_req.research_task_id or task_id

            self._record_audit_event(
                event_type=EventType.CRAWL_REQUEST_STARTED,
                objective_id=domain_req.objective_id or objective_id,
                task_id=effective_task_id,
                payload={
                    "request_id": domain_req.request_id,
                    "url": domain_req.url,
                    "attempt": domain_req.retry_count + 1,
                },
            )

            try:
                # Execute acquisition via TwoTierFetcher (HTTP first -> Playwright fallback)
                doc = await self.fetcher.fetch(domain_req)
                doc.crawl_request_id = domain_req.request_id
                doc.task_id = effective_task_id
                doc.objective_id = domain_req.objective_id or objective_id

                if doc.status_code == 200 and doc.fetch_method != "blocked":
                    await rq.mark_request_as_handled(crawlee_req)
                    self._record_audit_event(
                        event_type=EventType.CRAWL_REQUEST_SUCCEEDED,
                        objective_id=domain_req.objective_id or objective_id,
                        task_id=effective_task_id,
                        payload={
                            "request_id": domain_req.request_id,
                            "url": doc.url,
                            "status_code": doc.status_code,
                            "fetch_method": doc.fetch_method,
                        },
                    )
                    acquired_documents.append(doc)
                    pages_processed += 1

                    # Dynamic child link discovery
                    if discover_links:
                        await self.discover_and_enqueue_child_links(
                            document=doc,
                            parent_request=domain_req,
                            max_depth=max_depth,
                        )
                else:
                    # Non-200 or blocked: consider retry if transient
                    if (
                        doc.status_code in (500, 502, 503, 504)
                        and domain_req.retry_count < domain_req.max_retries
                    ):
                        crawlee_req.retry_count += 1
                        await rq.reclaim_request(crawlee_req)
                        self._record_audit_event(
                            event_type=EventType.CRAWL_REQUEST_RECLAIMED,
                            objective_id=domain_req.objective_id or objective_id,
                            task_id=effective_task_id,
                            payload={
                                "request_id": domain_req.request_id,
                                "url": domain_req.url,
                                "status_code": doc.status_code,
                                "next_retry": crawlee_req.retry_count,
                            },
                        )
                        pages_processed += 1
                    else:
                        await rq.mark_request_as_handled(crawlee_req)
                        self._record_audit_event(
                            event_type=EventType.CRAWL_REQUEST_FAILED,
                            objective_id=domain_req.objective_id or objective_id,
                            task_id=effective_task_id,
                            payload={
                                "request_id": domain_req.request_id,
                                "url": domain_req.url,
                                "status_code": doc.status_code,
                                "fetch_method": doc.fetch_method,
                            },
                        )
                        pages_processed += 1
                        # Still return non-empty document if content was acquired
                        if doc.text_content:
                            acquired_documents.append(doc)

            except Exception as exc:
                logger.warning("Crawl network exception on %s: %s", domain_req.url, exc)
                pages_processed += 1
                if domain_req.retry_count < domain_req.max_retries:
                    crawlee_req.retry_count += 1
                    await rq.reclaim_request(crawlee_req)
                    self._record_audit_event(
                        event_type=EventType.CRAWL_REQUEST_RECLAIMED,
                        objective_id=domain_req.objective_id or objective_id,
                        task_id=effective_task_id,
                        payload={
                            "request_id": domain_req.request_id,
                            "url": domain_req.url,
                            "error": str(exc),
                            "next_retry": crawlee_req.retry_count,
                        },
                    )
                else:
                    await rq.mark_request_as_handled(crawlee_req)
                    self._record_audit_event(
                        event_type=EventType.CRAWL_REQUEST_FAILED,
                        objective_id=domain_req.objective_id or objective_id,
                        task_id=effective_task_id,
                        payload={
                            "request_id": domain_req.request_id,
                            "url": domain_req.url,
                            "error": str(exc),
                        },
                    )

        return acquired_documents

    async def get_queue_stats(self, objective_id: str) -> dict[str, int]:
        """Return queue metrics for observation and resume verification."""
        rq = await self.get_or_create_queue(objective_id)
        total = await rq.get_total_count()
        handled = await rq.get_handled_count()
        return {
            "total": total,
            "total_requests": total,
            "handled": handled,
            "pending": max(0, total - handled),
        }

    async def is_queue_finished(self, objective_id: str) -> bool:
        """Check if all enqueued crawl requests have been handled."""
        rq = await self.get_or_create_queue(objective_id)
        return await rq.is_finished()
