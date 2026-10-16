"""Identity Specialist Package for Heimdallr."""

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
from argus.specialists.identity.github import GitHubIdentityConnector
from argus.specialists.identity.specialist import IdentityProbeSpecialist


def investigate_identity(*args, **kwargs):
    from argus.specialists.identity.workflow import investigate_identity as _impl
    return _impl(*args, **kwargs)


__all__ = [
    "AccountClaimType",
    "CandidateIdentityRelationship",
    "EpistemicCandidateStatus",
    "IdentifierType",
    "IdentityClaim",
    "IdentityInvestigationReport",
    "IdentityProbeRequest",
    "IdentityProbeResult",
    "InvestigationConstraints",
    "IdentityProbeSpecialist",
    "GitHubIdentityConnector",
    "investigate_identity",
]
