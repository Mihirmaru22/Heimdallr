"""Heimdallr V3.2: OpenSanctions Adapter Boundary.

Isolates candidate OpenSanctionsSpecialist behind strict adapter contracts.
Emits NormalizedObservation records and never mutates authoritative state directly.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from argus.competition.models import NormalizedObservation
from argus.competition.security_gate import SecurityGateValidator
from argus.specialists.sanctions.specialist import OpenSanctionsSpecialist

logger = logging.getLogger(__name__)


class OpenSanctionsAdapter:
    """Production adapter bridge for OpenSanctions candidate specialist."""

    def __init__(self, specialist: Optional[OpenSanctionsSpecialist] = None) -> None:
        self.specialist = specialist or OpenSanctionsSpecialist()
        self.implementation_id = "impl_opensanctions_probe_v1"
        self.version = "1.0.0"

    def execute_query(self, query: str, context: Optional[Dict[str, Any]] = None) -> List[NormalizedObservation]:
        """Execute sanctions screening or beneficial ownership query and return normalized observations."""
        observations: List[NormalizedObservation] = []

        # 1. Check for sanctions listings
        sanctions_hits = self.specialist.search_sanctions(query)
        for hit in sanctions_hits:
            sanitized_payload = SecurityGateValidator.sanitize_candidate_observation(hit)
            ev_type = "OFAC_SDN_ENTRY" if hit.get("listing_authority") == "US_OFAC" else (
                "UK_OFSI_ENTRY" if hit.get("listing_authority") == "UK_OFSI" else "EU_SANCTIONS_ENTRY"
            )
            obs = NormalizedObservation(
                observation_id=f"obs_sanc_{uuid.uuid4().hex[:8]}",
                source_candidate_id=self.implementation_id,
                entity_name=hit["entity_name"],
                evidence_type=ev_type,
                payload=sanitized_payload,
                confidence=0.95,
                epistemic_status="OBSERVED_REGULATORY_SANCTION",
                is_authoritative=False,  # Unverified until passed through Heimdallr Verifier
            )
            observations.append(obs)

        # 2. Check for beneficial ownership / offshore trust records
        bo_hit = self.specialist.trace_beneficial_ownership(query)
        if bo_hit.get("status") == "RESOLVED":
            sanitized_bo = SecurityGateValidator.sanitize_candidate_observation(bo_hit)
            obs_bo = NormalizedObservation(
                observation_id=f"obs_bo_{uuid.uuid4().hex[:8]}",
                source_candidate_id=self.implementation_id,
                entity_name=bo_hit["entity"],
                evidence_type="OFFSHORE_LEAKS_RECORD" if "PANAMA" in str(bo_hit.get("leak_source", "")) or "PANDORA" in str(bo_hit.get("leak_source", "")) else "BENEFICIAL_OWNERSHIP_DISCLOSURE",
                payload=sanitized_bo,
                confidence=0.90,
                epistemic_status="OBSERVED_OFFSHORE_STRUCTURE",
                is_authoritative=False,
            )
            observations.append(obs_bo)

        # 3. Check for PEP status
        pep_hit = self.specialist.check_pep_status(query)
        if pep_hit.get("is_pep"):
            sanitized_pep = SecurityGateValidator.sanitize_candidate_observation(pep_hit)
            obs_pep = NormalizedObservation(
                observation_id=f"obs_pep_{uuid.uuid4().hex[:8]}",
                source_candidate_id=self.implementation_id,
                entity_name=pep_hit["name"],
                evidence_type="PEP_DISCLOSURE",
                payload=sanitized_pep,
                confidence=0.92,
                epistemic_status="OBSERVED_POLITICAL_EXPOSURE",
                is_authoritative=False,
            )
            observations.append(obs_pep)

        return observations
