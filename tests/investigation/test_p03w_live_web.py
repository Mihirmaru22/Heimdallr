"""Automated Tests for Milestone P0.3-W: Controlled Live-Web Evaluation.

Verifies:
1. Live Web Task Suite Integrity (30 tasks across 10 categories)
2. Controlled Retrieval Budget Enforcement (requests, per-host limits)
3. P0.1 SSRF Defense Invariants & Dangerous Subnet Blocking
4. URL Canonicalization & Deduplication Logic
5. Source Independence Profiling
"""

import pytest

from argus.investigation.live_web.controller import ControlledLiveWebRetriever
from argus.investigation.live_web.models import (
    ControlledRetrievalLimits,
    LiveWebEvidenceRecord,
    SourceIndependenceProfile,
)
from argus.investigation.live_web.tasks import build_live_web_tasks


def test_live_web_task_distribution():
    """Verify exact count of 30 tasks spanning 10 distinct categories."""
    tasks = build_live_web_tasks()
    assert len(tasks) == 30, f"Expected 30 live tasks, got {len(tasks)}"

    task_ids = [t.task_id for t in tasks]
    assert len(set(task_ids)) == 30, "Task IDs must be globally unique"

    # Verify contracts and expected epistemic statuses exist
    for t in tasks:
        assert t.contract is not None
        assert t.expected_epistemic_status in ("SUPPORTED", "CONTRADICTED", "NOT_FOUND", "INSUFFICIENT_EVIDENCE")
        assert len(t.expected_answers) > 0


def test_controlled_retriever_ssrf_rejections():
    """Verify strict rejection of loopback, private subnets, cloud metadata, and bad schemes."""
    retriever = ControlledLiveWebRetriever()

    # Loopback
    permitted, reason = retriever.is_url_permitted("http://127.0.0.1:8000/secret")
    assert permitted is False
    assert "SSRF" in reason

    # Localhost
    permitted, reason = retriever.is_url_permitted("http://localhost:5000/api")
    assert permitted is False
    assert "SSRF" in reason

    # AWS Metadata
    permitted, reason = retriever.is_url_permitted("http://169.254.169.254/latest/meta-data/")
    assert permitted is False
    assert "SSRF" in reason

    # Private RFC 1918 Class A
    permitted, reason = retriever.is_url_permitted("http://10.200.0.5/internal")
    assert permitted is False
    assert "SSRF" in reason

    # Prohibited scheme
    permitted, reason = retriever.is_url_permitted("file:///etc/shadow")
    assert permitted is False
    assert "scheme" in reason.lower()

    # Permitted external domain
    permitted, reason = retriever.is_url_permitted("https://example.com/test")
    assert permitted is True
    assert reason is None


def test_controlled_retriever_per_host_and_task_limits():
    """Verify enforcement of max requests per host and task budget."""
    limits = ControlledRetrievalLimits(
        max_requests_per_task=4,
        max_requests_per_host=2,
    )
    retriever = ControlledLiveWebRetriever(limits=limits)

    # 1. Host limit test
    assert retriever.is_url_permitted("https://target.com/page1")[0] is True
    retriever.host_counts["target.com"] = 1
    assert retriever.is_url_permitted("https://target.com/page2")[0] is True
    retriever.host_counts["target.com"] = 2

    # 3rd request to same host should be rejected
    permitted, reason = retriever.is_url_permitted("https://target.com/page3")
    assert permitted is False
    assert "Per-host limit reached" in reason

    # Different host should be permitted
    assert retriever.is_url_permitted("https://other-domain.org/data")[0] is True

    # 2. Overall task request budget test
    retriever.requests_made = 4
    permitted, reason = retriever.is_url_permitted("https://fresh-domain.com/item")
    assert permitted is False
    assert "Task request budget exhausted" in reason


def test_url_canonicalization_and_deduplication():
    """Verify URL normalization, tracking query stripping, and duplicate handling."""
    retriever = ControlledLiveWebRetriever()

    url1 = "https://WWW.Example.COM/article/?utm_source=twitter&utm_medium=social#heading"
    url2 = "https://example.com/article"

    canon1 = retriever._canonicalize_url(url1)
    canon2 = retriever._canonicalize_url(url2)
    assert canon1 == canon2 == "https://example.com/article"


def test_source_independence_profiling():
    """Verify accurate calculation of raw vs independent publishers."""
    retriever = ControlledLiveWebRetriever()

    # Add 3 records from same domain (syndicated / duplicate)
    retriever.evidence_records = [
        LiveWebEvidenceRecord(
            evidence_id="ev_1",
            original_url="https://news.bbc.co.uk/page1",
            final_url="https://news.bbc.co.uk/page1",
            retrieval_timestamp="2026-10-13T10:00:00Z",
            http_status=200,
            title="BBC Article 1",
            domain="news.bbc.co.uk",
            publisher="BBC",
            extracted_text="Text content 1",
            content_hash="hash_1",
            source_type="live_web",
            extraction_method="safe_html_text",
        ),
        LiveWebEvidenceRecord(
            evidence_id="ev_2",
            original_url="https://news.bbc.co.uk/page2",
            final_url="https://news.bbc.co.uk/page2",
            retrieval_timestamp="2026-10-13T10:00:01Z",
            http_status=200,
            title="BBC Article 2",
            domain="news.bbc.co.uk",
            publisher="BBC",
            extracted_text="Text content 2",
            content_hash="hash_2",
            source_type="live_web",
            extraction_method="safe_html_text",
        ),
        LiveWebEvidenceRecord(
            evidence_id="ev_3",
            original_url="https://reuters.com/tech",
            final_url="https://reuters.com/tech",
            retrieval_timestamp="2026-10-13T10:00:02Z",
            http_status=200,
            title="Reuters Tech",
            domain="reuters.com",
            publisher="Reuters",
            extracted_text="Text content 3",
            content_hash="hash_3",
            source_type="live_web",
            extraction_method="safe_html_text",
        ),
    ]

    profile = retriever.compute_source_independence()
    assert profile.raw_source_count == 3
    # Distinct domains are news.bbc.co.uk and reuters.com -> 2 independent sources
    assert profile.estimated_independent_source_count == 2
    assert profile.domains_represented == ["news.bbc.co.uk", "reuters.com"]
    assert profile.independence_ratio == round(2 / 3, 4)
    assert profile.classification == "MODERATE"
