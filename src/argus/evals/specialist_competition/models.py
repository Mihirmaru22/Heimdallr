"""Heimdallr V3.2: SPECIALIST_COMPETITION_V1 Benchmark Models.

Defines the competition benchmark task contract, category taxonomy,
per-task evaluation results, and aggregate competition metrics.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from argus.competition.models import CompetitionDecisionType


class CompetitionTaskCategory(str, Enum):
    """Task archetype categories for specialist competition."""

    NORMAL = "NORMAL"                                # Direct structured query
    HARD = "HARD"                                    # Multi-jurisdiction / alias obfuscation
    AMBIGUOUS = "AMBIGUOUS"                          # Phrasing does not explicitly name sanctions/offshore
    NEGATIVE = "NEGATIVE"                            # Entity is clean / query should NOT trigger sanctions
    TEMPORAL = "TEMPORAL"                            # Historical vs active sanctions status
    CONTRADICTORY = "CONTRADICTORY"                  # Outdated corporate PR claims clean status vs active SDN
    ADVERSARIAL = "ADVERSARIAL"                      # Disguised offshore shell / nominee director evasion
    MISSING_INFO = "MISSING_INFO"                    # Incomplete records testing NOT_FOUND correctness
    EVIDENCE_GROUNDING = "EVIDENCE_GROUNDING"        # Verbatim registry reference extraction
    MULTI_HOP = "MULTI_HOP"                          # Corporate entity -> Offshore shell -> Sanctioned UBO
    HEALTH_CASCADE = "HEALTH_CASCADE"                # Candidate degraded/unavailable fallback
    LEGAL_SECURITY_GATE = "LEGAL_SECURITY_GATE"      # Unsafe code / license failure rejection


class CompetitionTaskV1(BaseModel):
    """Benchmark task in SPECIALIST_COMPETITION_V1."""

    task_id: str
    category: CompetitionTaskCategory
    question_text: str
    required_evidence: List[str] = Field(default_factory=list)
    related_entities: List[str] = Field(default_factory=list)
    temporal_context: Optional[Dict[str, Any]] = None
    jurisdiction: str = "GLOBAL"

    # Evaluator-Only Ground Truth (Quarantined from runtime candidate execution)
    expected_capabilities: List[str] = Field(default_factory=list)
    expected_winner: str = "challenger"  # "challenger", "incumbent", "coexist", "reject"
    expected_decision: CompetitionDecisionType = CompetitionDecisionType.RECRUIT_NEW_CAPABILITY
    target_evidence_type: str = "OFAC_SDN_ENTRY"
    notes: str = ""

    def get_public_view(self) -> Dict[str, Any]:
        """Return public dictionary without evaluator ground truth."""
        return {
            "task_id": self.task_id,
            "category": self.category.value,
            "question_text": self.question_text,
            "required_evidence": self.required_evidence,
            "related_entities": self.related_entities,
            "temporal_context": self.temporal_context,
            "jurisdiction": self.jurisdiction,
        }


class TaskCompetitionResult(BaseModel):
    """Evaluation result for an individual competition task."""

    task_id: str
    category: CompetitionTaskCategory
    incumbent_passed: bool
    candidate_passed: bool
    integrated_passed: bool
    incumbent_f1: float
    candidate_f1: float
    integrated_f1: float
    selected_winner: str
    winner_matches_expected: bool
    runtime_sec: float
    rationale: str
