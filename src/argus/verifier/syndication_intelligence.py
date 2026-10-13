"""Syndication Intelligence and Source Independence Verifier.

Enforces the core OSINT epistemic invariant:
3 copies != 3 sources!

Source A ─┐
Source B ─┼── same underlying syndication feed
Source C ─┘
       ↓
Syndication cluster
       ↓
NOT 3 independent confirmations
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SourceCluster(BaseModel):
    """An independent source origin cluster."""

    cluster_id: str
    primary_domain: str
    member_urls: list[str] = Field(default_factory=list)
    is_wire_syndication: bool = False


class IndependenceVerdict(BaseModel):
    """Evaluation of whether candidate evidence represents genuinely independent corroboration."""

    raw_evidence_count: int
    independent_clusters_count: int
    is_sufficiently_independent: bool
    clusters: list[SourceCluster] = Field(default_factory=list)
    discounted_duplicate_urls: list[str] = Field(default_factory=list)
    independence_ratio: float = 1.0
    rationale: str


class SyndicationIntelligence:
    """Detects syndicated duplicates and calculates true source diversity."""

    KNOWN_WIRE_DOMAINS = {
        "prnewswire.com",
        "businesswire.com",
        "globenewswire.com",
        "marketwatch.com",
        "yahoo.com",
        "benzinga.com",
        "accesswire.com",
    }

    def evaluate(
        self,
        evidence_items: list[dict[str, Any]],
        min_independent_sources_required: int = 3,
    ) -> IndependenceVerdict:
        """Evaluates independent corroboration across extracted evidence."""
        raw_count = len(evidence_items)
        if raw_count == 0:
            return IndependenceVerdict(
                raw_evidence_count=0,
                independent_clusters_count=0,
                is_sufficiently_independent=False,
                independence_ratio=0.0,
                rationale="Zero evidence items provided.",
            )

        cluster_map: dict[str, SourceCluster] = {}
        discounted_urls: list[str] = []

        for item in evidence_items:
            url = item.get("url", "")
            snippet = item.get("snippet", "")
            explicit_cluster = item.get("syndication_cluster_id")

            domain = urlparse(url).netloc.lower().replace("www.", "") if url else "unknown_origin"

            # Determine cluster key
            if explicit_cluster:
                cluster_key = f"syndication_{explicit_cluster}"
                is_wire = True
            elif domain in self.KNOWN_WIRE_DOMAINS:
                # Text fingerprint for wire content shingling
                text_hash = hashlib.md5(snippet[:100].encode("utf-8")).hexdigest()[:8]
                cluster_key = f"wire_feed_{text_hash}"
                is_wire = True
            else:
                cluster_key = f"domain_{domain}"
                is_wire = False

            if cluster_key not in cluster_map:
                cluster_map[cluster_key] = SourceCluster(
                    cluster_id=cluster_key,
                    primary_domain=domain,
                    member_urls=[url],
                    is_wire_syndication=is_wire,
                )
            else:
                cluster_map[cluster_key].member_urls.append(url)
                discounted_urls.append(url)

        independent_count = len(cluster_map)
        ratio = independent_count / raw_count if raw_count > 0 else 0.0
        sufficient = independent_count >= min_independent_sources_required

        rationale = (
            f"Identified {independent_count} independent source clusters from {raw_count} raw documents. "
            f"Discounted {len(discounted_urls)} syndicated mirrors."
        )

        return IndependenceVerdict(
            raw_evidence_count=raw_count,
            independent_clusters_count=independent_count,
            is_sufficiently_independent=sufficient,
            clusters=list(cluster_map.values()),
            discounted_duplicate_urls=discounted_urls,
            independence_ratio=ratio,
            rationale=rationale,
        )
