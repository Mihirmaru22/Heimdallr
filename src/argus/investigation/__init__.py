"""Heimdallr V2: Investigation Engine Core Package.

Transforms research from static linear search to an active, hypothesis-driven,
state-retaining autonomous investigation system.
"""

from argus.investigation.action import ActionType, ResearchAction
from argus.investigation.branch import BranchStatus, InvestigationBranch
from argus.investigation.evidence import EvidenceRequirement, EvidenceStatus
from argus.investigation.hypothesis import HypothesisStatus, InvestigationHypothesis
from argus.investigation.information_gain import InformationGainEstimator
from argus.investigation.orchestrator import InvestigationEngine
from argus.investigation.planner import InvestigationPlanner
from argus.investigation.question import InvestigationQuestion, QuestionStatus, QuestionType
from argus.investigation.state import (
    AuditTrailEntry,
    ConfidenceState,
    InformationGap,
    InvestigationResult,
    InvestigationState,
    StopState,
)
from argus.investigation.stopping import InvestigationStopReason, InvestigationStoppingPolicy
from argus.investigation.store import InvestigationStore

__all__ = [
    "ActionType",
    "AuditTrailEntry",
    "BranchStatus",
    "ConfidenceState",
    "EvidenceRequirement",
    "EvidenceStatus",
    "HypothesisStatus",
    "InformationGap",
    "InformationGainEstimator",
    "InvestigationBranch",
    "InvestigationEngine",
    "InvestigationHypothesis",
    "InvestigationPlanner",
    "InvestigationQuestion",
    "InvestigationResult",
    "InvestigationState",
    "InvestigationStopReason",
    "InvestigationStoppingPolicy",
    "InvestigationStore",
    "QuestionStatus",
    "QuestionType",
    "ResearchAction",
    "StopState",
]
