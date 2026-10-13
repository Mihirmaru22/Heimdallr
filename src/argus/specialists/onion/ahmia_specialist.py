"""Heimdallr V5: Ahmia Onion Search Specialist.

Permissively licensed (BSD-3-Clause) adapter for Ahmia search & discovery engine.
Provides indexed keyword search across public Tor hidden services, title matching,
and initial service discovery.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional
from argus.specialists.onion.corpus import ONION_CORPUS
from argus.specialists.onion.models import OnionService, OnionServiceStatus

logger = logging.getLogger(__name__)


class AhmiaSearchSpecialist:
    """Ahmia-style indexed search engine for Tor hidden services."""

    def __init__(self, corpus: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        self.corpus = corpus or ONION_CORPUS
        self.implementation_id = "impl_ahmia_search_v1"
        self.version = "1.0.0"

    def sanitize_query(self, query: str) -> str:
        """Strip non-alphanumeric punctuation from user query."""
        return re.sub(r'[^a-zA-Z0-9\s\.\-_]', '', query).strip().lower()

    def search_onion_index(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search indexed onion services by keywords, entity names, or titles."""
        clean_q = self.sanitize_query(query)
        if not clean_q:
            return []

        stopwords = {
            "what", "is", "the", "primary", "tor", "hidden", "service", "address",
            "for", "locate", "where", "posts", "find", "identify", "active", "site",
            "portal", "which", "with", "from", "that", "this", "does", "have", "data",
            "leak", "about", "show", "query", "operational", "official", "onion",
        }
        tokens = [w for w in re.findall(r'[a-zA-Z0-9_\-\.]+', clean_q) if len(w) >= 3 and w not in stopwords]

        results: List[Dict[str, Any]] = []
        for key, service in self.corpus.items():
            score = 0.0
            svc_name = service["service_name"].lower()
            svc_desc = service.get("description", "").lower()
            svc_addr = service["onion_address"].lower()
            assoc_entities = [e.lower() for e in service.get("associated_entities", [])]
            mirrors = [m.lower() for m in service.get("mirrors", [])]

            # Direct address or mirror match
            if svc_addr in clean_q or clean_q in svc_addr:
                score += 15.0
            if any(m in clean_q or clean_q in m for m in mirrors):
                score += 12.0

            # Substring matches
            if clean_q in svc_name or svc_name in clean_q:
                score += 8.0
            if any(clean_q in e or e in clean_q for e in assoc_entities):
                score += 7.0
            if clean_q in svc_desc:
                score += 4.0

            # Tokenized keyword scoring
            for t in tokens:
                if t in svc_addr:
                    score += 6.0
                if any(t in m for m in mirrors):
                    score += 5.0
                if t in svc_name:
                    score += 4.5
                if any(t in e for e in assoc_entities):
                    score += 5.0
                if t in key.lower():
                    score += 3.5
                if t in svc_desc:
                    score += 2.0

            # Search in sample pages if present
            for page in service.get("sample_pages", []):
                p_title = page.get("title", "").lower()
                p_text = page.get("text", "").lower()
                if clean_q in p_title or clean_q in p_text:
                    score += 5.0
                for t in tokens:
                    if t in p_title:
                        score += 3.0
                    elif t in p_text:
                        score += 1.5

            if score > 0.0:
                results.append({
                    "onion_address": service["onion_address"],
                    "service_name": service["service_name"],
                    "category": service["category"],
                    "description": service["description"],
                    "status": service["status"],
                    "relevance_score": score,
                    "first_seen": service.get("first_seen"),
                    "last_seen": service.get("last_seen"),
                    "mirrors": service.get("mirrors", []),
                    "associated_entities": service.get("associated_entities", []),
                })

        # Sort by relevance
        results.sort(key=lambda r: r["relevance_score"], reverse=True)
        return results[:limit]

    def discover_onion_service(self, target_entity: str) -> Dict[str, Any]:
        """Discover primary onion service and verified mirrors for a known entity."""
        hits = self.search_onion_index(target_entity, limit=3)
        if not hits:
            return {
                "target_entity": target_entity,
                "status": "NOT_FOUND",
                "matched_services": [],
            }

        top_hit = hits[0]
        return {
            "target_entity": target_entity,
            "status": "RESOLVED",
            "primary_onion": top_hit["onion_address"],
            "service_name": top_hit["service_name"],
            "mirrors": top_hit.get("mirrors", []),
            "current_status": top_hit["status"],
            "associated_entities": top_hit.get("associated_entities", []),
            "first_seen": top_hit.get("first_seen"),
            "last_seen": top_hit.get("last_seen"),
        }
