"""End-to-End Identity Investigation Vertical Slice Workflow.

Exposes a bounded, evidence-backed identity investigation capability coordinating
the existing orchestrator, Identity Intelligence specialist, and platform registries.
"""

from __future__ import annotations

from typing import Any

from argus.evals.vertical_corpus import VERTICAL_PLATFORM_REGISTRY
from argus.specialists.identity.contract import (
    AccountClaimType,
    CandidateIdentityRelationship,
    EpistemicCandidateStatus,
    IdentifierType,
    IdentityClaim,
    IdentityInvestigationReport,
    IdentityProbeRequest,
    IdentityProbeResult,
    InvestigationConstraints,
)
from argus.specialists.identity.specialist import IdentityProbeSpecialist


def investigate_identity(
    username: str,
    starting_platform: str = "github",
    context: dict[str, Any] | None = None,
    platform_registry: dict[str, dict[str, Any]] | None = None,
    live_connector: Any | None = None,
    max_steps: int = 10,
) -> IdentityInvestigationReport:
    """Investigate a username on a starting platform and return a structured report.
    
    Args:
        username: Target handle, username, or identifier string.
        starting_platform: Starting platform (e.g. 'github', 'instagram', 'twitter', 'linkedin').
        context: Optional known biographical or organizational context for corroboration.
        platform_registry: Optional custom platform registry (defaults to VERTICAL_PLATFORM_REGISTRY).
        live_connector: Optional live profile connector (e.g. GitHubIdentityConnector).
        max_steps: Maximum step budget for the investigation.
        
    Returns:
        IdentityInvestigationReport containing findings, candidate links, rationales,
        contradictory evidence, sources queried, and privacy boundaries.
    """
    from argus.investigation.orchestrator import InvestigationEngine
    registry = platform_registry if platform_registry is not None else VERTICAL_PLATFORM_REGISTRY
    specialist = IdentityProbeSpecialist(platform_registry=registry, live_connector=live_connector)

    engine = InvestigationEngine()
    engine.identity_specialist = specialist

    return engine.investigate_identity(
        username=username,
        starting_platform=starting_platform,
        context=context,
        max_steps=max_steps,
    )
