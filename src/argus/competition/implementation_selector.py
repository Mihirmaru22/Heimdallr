"""Heimdallr V3.2: Implementation Selector.

Ranks and selects concrete specialist implementations for an ALREADY-SELECTED
abstract capability based on performance profiles, runtime health, licensing,
cost, and question evidence requirements.

CRITICAL INVARIANT: Implementation selection MUST NEVER alter the capability
requirement itself.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from argus.capability_registry.models import CapabilityCandidate, CapabilityDefinition, HealthStatus
from argus.investigation.question import InvestigationQuestion

logger = logging.getLogger(__name__)


class ImplementationSelector:
    """Selects the optimal concrete implementation adapter for a chosen capability."""

    def __init__(self, registry: Optional[Any] = None) -> None:
        self.registry = registry

    def select_implementation(
        self,
        capability: CapabilityDefinition,
        question: Optional[InvestigationQuestion] = None,
        prefer_challenger: bool = False,
        candidate_implementations: Optional[List[CapabilityDefinition]] = None,
    ) -> CapabilityDefinition:
        """Select the best implementation for an already-decided capability.
        
        Evaluates:
        1. Runtime Health (EXCLUDE UNAVAILABLE / QUARANTINED, penalize DEGRADED)
        2. Performance Profile (F1 score, precision, accuracy)
        3. SemVer Version Priority (e.g. v2.0.0 over v1.0.0)
        4. Operational Cost and Latency
        """
        candidates = candidate_implementations
        if not candidates and self.registry and hasattr(self.registry, "get_implementations"):
            candidates = self.registry.get_implementations(capability.capability_id)
        if not candidates:
            candidates = [capability]

        ranked = self.rank_implementations_for_capability(candidates, question=question)
        if ranked:
            return ranked[0]
        return capability

    def rank_implementations_for_capability(
        self,
        implementations: List[CapabilityDefinition],
        question: Optional[InvestigationQuestion] = None,
    ) -> List[CapabilityDefinition]:
        """Rank a candidate pool of implementations offering the same capability."""
        valid_impls = [
            impl for impl in implementations
            if impl.status not in (HealthStatus.UNAVAILABLE, HealthStatus.DISABLED, HealthStatus.QUARANTINED)
        ]

        if not valid_impls:
            # All implementations unavailable
            return []

        def sort_key(impl: CapabilityDefinition) -> tuple:
            # 1. Health tier (AVAILABLE > DEGRADED)
            health_weight = 1.0 if impl.status == HealthStatus.AVAILABLE else 0.5

            # 2. Performance benchmark profile
            prof = impl.performance_profile
            perf_score = (
                getattr(prof, "accuracy", 1.0) * 0.4
                + getattr(prof, "precision", 1.0) * 0.3
                + getattr(prof, "recall", 1.0) * 0.3
            )

            # 3. SemVer version priority (parse vX.Y.Z)
            semver_tuple = (0, 0, 0)
            try:
                clean_v = impl.version.lstrip("v").split(".")
                semver_tuple = tuple(int(x) for x in clean_v[:3])
            except Exception:
                pass

            # 4. Latency / cost penalty
            cost_penalty = getattr(prof, "cost_usd", 0.0) * 0.1

            # Higher is better: (health_weight, perf_score, semver_tuple, -cost_penalty)
            return (health_weight, perf_score, semver_tuple, -cost_penalty)


        return sorted(valid_impls, key=sort_key, reverse=True)
