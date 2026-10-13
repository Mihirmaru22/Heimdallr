"""Heimdallr V3.2: OpenSanctions & Beneficial Ownership Specialist.

Clean-room implementation of the OpenSanctions entity schema and yente
reconciliation standard. Performs structured international sanctions screening,
PEP identification, and cross-border offshore trust tracing.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from argus.specialists.sanctions.corpus import SANCTIONS_CORPUS

logger = logging.getLogger(__name__)


class OpenSanctionsSpecialist:
    """Specialist engine for global sanctions, PEPs, and offshore beneficial ownership."""

    def __init__(self, corpus: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        self.corpus = corpus or SANCTIONS_CORPUS

    def sanitize_query(self, query: str) -> str:
        """Strip dangerous characters and normalize whitespace."""
        return re.sub(r'[^a-zA-Z0-9\s\.\-_]', '', query).strip().lower()

    def search_sanctions(self, query: str) -> List[Dict[str, Any]]:
        """Search consolidated sanctions lists by entity name, alias, intermediary, or owner."""
        clean_q = self.sanitize_query(query)
        if not clean_q:
            return []

        results: List[Dict[str, Any]] = []
        for key, entity in self.corpus.items():
            # Check primary name
            if clean_q in entity["entity_name"].lower() or entity["entity_name"].lower() in clean_q:
                results.append(entity)
                continue

            # Check aliases
            matched_alias = False
            for alias in entity.get("aliases", []):
                if clean_q in alias.lower() or alias.lower() in clean_q:
                    results.append(entity)
                    matched_alias = True
                    break
            if matched_alias:
                continue

            # Check intermediaries (e.g. Cyprus Corporate Services Trust)
            matched_inter = False
            for intermediary in entity.get("known_intermediaries", []):
                if clean_q in intermediary.lower() or intermediary.lower() in clean_q:
                    results.append(entity)
                    matched_inter = True
                    break
            if matched_inter:
                continue

            # Check controlled entities or owners
            for ce in entity.get("controlled_entities", []) + entity.get("beneficial_owners", []):
                if clean_q in ce.lower() or ce.lower() in clean_q:
                    results.append(entity)
                    break

        return results


    def trace_beneficial_ownership(self, entity_name: str) -> Dict[str, Any]:
        """Trace cross-border trusts, nominee directors, and ultimate beneficial owners."""
        clean_name = self.sanitize_query(entity_name)
        matched = None
        for key, entity in self.corpus.items():
            if clean_name in key.lower() or key.lower() in clean_name:
                matched = entity
                break

        if not matched:
            return {
                "entity": entity_name,
                "status": "NOT_FOUND",
                "beneficial_owners": [],
                "offshore_nodes": [],
            }

        owners = matched.get("beneficial_owners", [])
        intermediaries = matched.get("known_intermediaries", []) + ([matched.get("registered_agent")] if "registered_agent" in matched else [])
        intermediaries = [i for i in intermediaries if i]

        return {
            "entity": matched["entity_name"],
            "status": "RESOLVED",
            "jurisdiction": matched.get("jurisdiction", "UNKNOWN"),
            "beneficial_owners": owners,
            "intermediaries": intermediaries,
            "leak_source": matched.get("leak_source", "REGULATORY_REGISTRY"),
            "sanctions_programs": matched.get("sanctions_programs", []),
        }

    def check_pep_status(self, person_name: str) -> Dict[str, Any]:
        """Check if an individual is a Politically Exposed Person (PEP)."""
        clean_name = self.sanitize_query(person_name)
        for key, entity in self.corpus.items():
            if entity.get("entity_type") == "INDIVIDUAL" and (clean_name in key.lower() or key.lower() in clean_name):
                if entity.get("pep_status") == "POLITICALLY_EXPOSED_PERSON" or "PEP_REGISTRY" in entity.get("sanctions_programs", []):
                    return {
                        "name": entity["entity_name"],
                        "is_pep": True,
                        "pep_role": entity.get("pep_role", "Political Official"),
                        "citizenship": entity.get("citizenship", []),
                    }

        return {"name": person_name, "is_pep": False, "pep_role": None}
