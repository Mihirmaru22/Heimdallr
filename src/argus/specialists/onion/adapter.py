"""Heimdallr V5: Onion & Dark-Web Adapters.

Implements strict adapter boundary contracts for:
1. impl_ahmia_search_v1 (Ahmia Search Specialist)
2. impl_torbot_crawler_v1 (TorBot Clean-Room Specialist)
3. impl_onion_integrated_v1 (Unified Onion Intelligence Specialist)

All outputs are routed through SecurityGateValidator, labeled is_authoritative = False,
and delivered as NormalizedObservation records.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
import uuid

from argus.competition.models import NormalizedObservation
from argus.competition.security_gate import SecurityGateValidator
from argus.specialists.onion.ahmia_specialist import AhmiaSearchSpecialist
from argus.specialists.onion.torbot_specialist import TorBotCrawlerSpecialist
from argus.specialists.onion.unified_specialist import UnifiedOnionSpecialist

logger = logging.getLogger(__name__)


class AhmiaSearchAdapter:
    """Adapter for Ahmia search and discovery specialist (impl_ahmia_search_v1)."""

    def __init__(self, specialist: Optional[AhmiaSearchSpecialist] = None) -> None:
        self.specialist = specialist or AhmiaSearchSpecialist()
        self.implementation_id = "impl_ahmia_search_v1"
        self.version = "1.0.0"

    def execute_query(self, query: str, context: Optional[Dict[str, Any]] = None) -> List[NormalizedObservation]:
        observations: List[NormalizedObservation] = []
        hits = self.specialist.search_onion_index(query, limit=5)

        for hit in hits:
            sanitized_payload = SecurityGateValidator.sanitize_candidate_observation(hit)
            obs = NormalizedObservation(
                observation_id=f"obs_ahmia_{uuid.uuid4().hex[:8]}",
                source_candidate_id=self.implementation_id,
                entity_name=hit.get("service_name", hit.get("onion_address")),
                evidence_type="ONION_SERVICE_DESCRIPTOR",
                payload=sanitized_payload,
                confidence=0.88,
                epistemic_status="OBSERVED_DARKWEB_DESCRIPTOR",
                is_authoritative=False,  # Unverified until Verifier corroboration
            )
            observations.append(obs)

        return observations


class TorBotCleanRoomAdapter:
    """Adapter for TorBot clean-room crawler & extractor (impl_torbot_crawler_v1)."""

    def __init__(self, specialist: Optional[TorBotCrawlerSpecialist] = None) -> None:
        self.specialist = specialist or TorBotCrawlerSpecialist()
        self.implementation_id = "impl_torbot_crawler_v1"
        self.version = "1.0.0"

    def execute_query(self, query: str, context: Optional[Dict[str, Any]] = None) -> List[NormalizedObservation]:
        observations: List[NormalizedObservation] = []

        # 1. Crawl service and extract links
        crawl_hit = self.specialist.crawl_onion_service(query)
        if crawl_hit.get("status") != "NOT_FOUND":
            sanitized_crawl = SecurityGateValidator.sanitize_candidate_observation(crawl_hit)
            obs_crawl = NormalizedObservation(
                observation_id=f"obs_torbot_crawl_{uuid.uuid4().hex[:8]}",
                source_candidate_id=self.implementation_id,
                entity_name=crawl_hit.get("service_name", query),
                evidence_type="ONION_CRAWL_SNAPSHOT",
                payload=sanitized_crawl,
                confidence=0.90,
                epistemic_status="OBSERVED_CRAWLED_STRUCTURE",
                is_authoritative=False,
            )
            observations.append(obs_crawl)

        # 2. Extract cryptographic and contact identities
        ident_hit = self.specialist.extract_cryptographic_identities(query)
        if ident_hit.get("crypto_addresses") or ident_hit.get("pgp_fingerprints"):
            sanitized_ident = SecurityGateValidator.sanitize_candidate_observation(ident_hit)
            obs_ident = NormalizedObservation(
                observation_id=f"obs_torbot_ident_{uuid.uuid4().hex[:8]}",
                source_candidate_id=self.implementation_id,
                entity_name=ident_hit.get("service_name", query),
                evidence_type="ONION_EXTRACTED_ENTITY",
                payload=sanitized_ident,
                confidence=0.92,
                epistemic_status="OBSERVED_CRYPTOGRAPHIC_IDENTIFIER",
                is_authoritative=False,
            )
            observations.append(obs_ident)

        return observations


class UnifiedOnionAdapter:
    """Adapter for unified coexistence engine (impl_onion_integrated_v1)."""

    def __init__(self, specialist: Optional[UnifiedOnionSpecialist] = None) -> None:
        self.specialist = specialist or UnifiedOnionSpecialist()
        self.implementation_id = "impl_onion_integrated_v1"
        self.version = "1.0.0"

    def execute_query(self, query: str, context: Optional[Dict[str, Any]] = None) -> List[NormalizedObservation]:
        observations: List[NormalizedObservation] = []
        result = self.specialist.full_onion_investigation(query)

        if result.get("status") == "NOT_FOUND":
            return observations

        # 1. Service Descriptor Observation
        if "primary_service" in result:
            svc = result["primary_service"]
            sanitized_svc = SecurityGateValidator.sanitize_candidate_observation(svc)
            obs_svc = NormalizedObservation(
                observation_id=f"obs_onion_svc_{uuid.uuid4().hex[:8]}",
                source_candidate_id=self.implementation_id,
                entity_name=svc.get("service_name", svc.get("onion_address")),
                evidence_type="ONION_SERVICE_DESCRIPTOR",
                payload=sanitized_svc,
                confidence=0.92,
                epistemic_status="OBSERVED_DARKWEB_DESCRIPTOR",
                is_authoritative=False,
            )
            observations.append(obs_svc)

        # 2. Deep Crawl and Cryptographic Intelligence Observation
        intel = result.get("extracted_intelligence") or result
        sanitized_intel = SecurityGateValidator.sanitize_candidate_observation(intel)
        obs_intel = NormalizedObservation(
            observation_id=f"obs_onion_crawl_{uuid.uuid4().hex[:8]}",
            source_candidate_id=self.implementation_id,
            entity_name=intel.get("service_name", query),
            evidence_type="ONION_CRAWL_SNAPSHOT",
            payload=sanitized_intel,
            confidence=0.94,
            epistemic_status="OBSERVED_DEEP_CRAWL_INTEL",
            is_authoritative=False,
        )
        observations.append(obs_intel)

        # 3. Mirror Network Observation if mirrors present
        if intel.get("verified_mirrors") or intel.get("phishing_clones"):
            mirror_payload = {
                "canonical_service": intel.get("service_name"),
                "canonical_onion": intel.get("onion_address"),
                "verified_mirrors": intel.get("verified_mirrors", []),
                "phishing_clones": intel.get("phishing_clones", []),
            }
            sanitized_mirrors = SecurityGateValidator.sanitize_candidate_observation(mirror_payload)
            obs_mirror = NormalizedObservation(
                observation_id=f"obs_onion_mirror_{uuid.uuid4().hex[:8]}",
                source_candidate_id=self.implementation_id,
                entity_name=intel.get("service_name", query),
                evidence_type="ONION_MIRROR_CLUSTER",
                payload=sanitized_mirrors,
                confidence=0.91,
                epistemic_status="OBSERVED_MIRROR_TOPOLOGY",
                is_authoritative=False,
            )
            observations.append(obs_mirror)

        return observations
