"""Crawler and web acquisition package for Argus."""

from argus.crawler.engine import CrawlExecutionEngine
from argus.crawler.extractor import DocumentExtractor, StructuredDocumentResult
from argus.crawler.fetcher import BaseFetcher, TwoTierFetcher
from argus.crawler.mock import MockFetcher
from argus.crawler.models import ContentUnit, CrawlRequest, Document, generate_unit_id

__all__ = [
    "BaseFetcher",
    "ContentUnit",
    "CrawlExecutionEngine",
    "CrawlRequest",
    "Document",
    "DocumentExtractor",
    "MockFetcher",
    "StructuredDocumentResult",
    "TwoTierFetcher",
    "generate_unit_id",
]
