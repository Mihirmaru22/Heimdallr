"""Heimdallr V5: Unified Onion Intelligence Specialist.

Coexistence engine orchestrating Ahmia search discovery and TorBot clean-room crawling.
Provides complete end-to-end dark-web discovery, crawling, extraction, and mirror analysis.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from argus.specialists.onion.ahmia_specialist import AhmiaSearchSpecialist
from argus.specialists.onion.corpus import ONION_CORPUS
from argus.specialists.onion.torbot_specialist import TorBotCrawlerSpecialist

logger = logging.getLogger(__name__)


class UnifiedOnionSpecialist:
    """Unified specialist combining search discovery and deep crawling for Tor onion networks."""

    def __init__(self, corpus: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        self.corpus = corpus or ONION_CORPUS
        self.ahmia_engine = AhmiaSearchSpecialist(corpus=self.corpus)
        self.torbot_engine = TorBotCrawlerSpecialist(corpus=self.corpus)
        self.implementation_id = "impl_onion_integrated_v1"
        self.version = "1.0.0"

    def search_and_discover(self, query: str) -> List[Dict[str, Any]]:
        """Perform indexed keyword search and return matching onion services."""
        return self.ahmia_engine.search_onion_index(query)

    def crawl_and_extract(self, target: str) -> Dict[str, Any]:
        """Crawl onion service and extract all cryptographic and contact identities."""
        crawl_res = self.torbot_engine.crawl_onion_service(target)
        ident_res = self.torbot_engine.extract_cryptographic_identities(target)
        mirror_res = self.torbot_engine.trace_mirror_clusters(target)

        return {
            "target": target,
            "status": crawl_res.get("status", "NOT_FOUND"),
            "onion_address": crawl_res.get("onion_address"),
            "service_name": crawl_res.get("service_name"),
            "active": crawl_res.get("active", False),
            "crawled_pages": crawl_res.get("crawled_pages", []),
            "crypto_addresses": ident_res.get("crypto_addresses", {}),
            "pgp_fingerprints": ident_res.get("pgp_fingerprints", []),
            "contact_identities": ident_res.get("contact_identities", []),
            "verified_mirrors": mirror_res.get("verified_mirrors", []),
            "phishing_clones": mirror_res.get("phishing_clones", []),
        }

    def full_onion_investigation(self, query_or_address: str) -> Dict[str, Any]:
        """Execute comprehensive onion intelligence pipeline: search -> resolve -> crawl -> extract."""
        clean_input = query_or_address.strip()
        # 1. Check if input is a direct standalone .onion address (no spaces or ends with .onion)
        if " " not in clean_input and ".onion" in clean_input.lower():
            return self.crawl_and_extract(clean_input)

        # 2. Otherwise discover via search
        search_hits = self.search_and_discover(query_or_address)
        if not search_hits:
            return {
                "query": query_or_address,
                "status": "NOT_FOUND",
                "matched_services": [],
                "extracted_intelligence": None,
            }

        top_service = search_hits[0]
        onion_addr = top_service["onion_address"]
        deep_intel = self.crawl_and_extract(onion_addr)

        return {
            "query": query_or_address,
            "status": "RESOLVED",
            "search_hits_count": len(search_hits),
            "primary_service": top_service,
            "extracted_intelligence": deep_intel,
        }
