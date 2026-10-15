"""Heimdallr V2: First-Class Investigation Stopping Policy & Taxonomy.

Evaluates termination criteria based on objective satisfaction, evidence coverage,
budget limits, and information gain plateaus.
Never permits "LLM thinks it is done" stopping.
"""

from __future__ import annotations

from enum import Enum
import logging
from typing import Any

from argus.investigation.question import QuestionStatus
from argus.investigation.state import InvestigationState, StopState

logger = logging.getLogger(__name__)


class InvestigationStopReason(str, Enum):
    """Rigorous taxonomy of valid investigation stop reasons."""

    OBJECTIVE_SATISFIED = "OBJECTIVE_SATISFIED"
    SUFFICIENT_EVIDENCE = "SUFFICIENT_EVIDENCE"
    NO_INFORMATION_GAIN = "NO_INFORMATION_GAIN"
    NO_USEFUL_ACTIONS_REMAIN = "NO_USEFUL_ACTIONS_REMAIN"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    BUDGET_EXHAUSTED_WITH_ACCEPTABLE_COVERAGE = "BUDGET_EXHAUSTED_WITH_ACCEPTABLE_COVERAGE"
    BUDGET_EXHAUSTED_WITH_CRITICAL_MISSING_FIELDS = "BUDGET_EXHAUSTED_WITH_CRITICAL_MISSING_FIELDS"
    UNRESOLVABLE_CONTRADICTION = "UNRESOLVABLE_CONTRADICTION"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"
    INCOMPLETE = "INCOMPLETE"
    SAFETY_STOP = "SAFETY_STOP"


class InvestigationStoppingPolicy:
    """Evaluates whether an active investigation has reached an authorized stop point."""

    def __init__(
        self,
        max_consecutive_zero_gains: int = 4,
        min_satisfaction_ratio: float = 0.85,
    ) -> None:
        self.max_consecutive_zero_gains = max_consecutive_zero_gains
        self.min_satisfaction_ratio = min_satisfaction_ratio

    def evaluate(self, state: InvestigationState) -> tuple[bool, InvestigationStopReason | None, str]:
        """Evaluate investigation state and determine if research should stop."""
        budget = state.research_budget
        steps_taken = budget.get("steps_taken", 0)
        max_steps = budget.get("max_steps", 15)
        consecutive_zeros = budget.get("consecutive_zero_gains", 0)

        # 1. Safety check
        if state.stop_state.stop_reason == InvestigationStopReason.SAFETY_STOP.value:
            return True, InvestigationStopReason.SAFETY_STOP, state.stop_state.stopping_rationale

        # 2. Objective questions resolution check
        total_questions = len(state.questions)
        resolved_count = len(state.resolved_questions)

        # Critical questions check
        critical_questions = [
            q for q in state.questions.values() if q.get("is_critical", False)
        ]
        unresolved_critical = [
            q
            for q in critical_questions
            if q.get("question_id", q.get("id")) in state.unresolved_questions
            or (
                q.get("question_id", q.get("id")) not in state.resolved_questions
                and q.get("status")
                not in (
                    QuestionStatus.SUPPORTED.value,
                    QuestionStatus.NOT_FOUND.value,
                    QuestionStatus.CONTRADICTED.value,
                    "INSUFFICIENT_EVIDENCE",
                )
            )
        ]

        # 1b. Executive contract completion check
        expected_exec = state.objective_contract.get("expected_executive_count")
        min_evidence_needed = 6 if expected_exec and expected_exec >= 10 else 1
        if (
            expected_exec is not None
            and len(state.completed_branches) >= expected_exec
            and len(state.evidence) >= min_evidence_needed
            and len(unresolved_critical) == 0
        ):
            return (
                True,
                InvestigationStopReason.OBJECTIVE_SATISFIED,
                f"All {expected_exec} required executive dossiers successfully verified with sufficient evidence depth ({len(state.evidence)} sources).",
            )

        if total_questions > 0 and len(state.unresolved_questions) == 0:
            return (
                True,
                InvestigationStopReason.OBJECTIVE_SATISFIED,
                f"All {total_questions} investigation questions successfully resolved.",
            )

        if total_questions > 0 and len(unresolved_critical) == 0 and resolved_count / total_questions >= self.min_satisfaction_ratio:
            return (
                True,
                InvestigationStopReason.SUFFICIENT_EVIDENCE,
                f"Resolved {resolved_count}/{total_questions} questions with 0 unresolved critical questions.",
            )

        # 3. Information gain plateau check
        if consecutive_zeros >= self.max_consecutive_zero_gains and steps_taken >= 3:
            if total_questions > 0 and len(unresolved_critical) == 0 and resolved_count / total_questions >= 0.70:
                return (
                    True,
                    InvestigationStopReason.SUFFICIENT_EVIDENCE,
                    f"Plateau reached after {consecutive_zeros} zero gains with acceptable coverage ({resolved_count}/{total_questions} questions resolved).",
                )
            return (
                True,
                InvestigationStopReason.NO_INFORMATION_GAIN,
                f"Terminated after {consecutive_zeros} consecutive actions with zero marginal information gain.",
            )

        # 4. Budget exhaustion check
        if steps_taken >= max_steps:
            if len(unresolved_critical) == 0 and (total_questions == 0 or resolved_count / total_questions >= 0.70):
                return (
                    True,
                    InvestigationStopReason.BUDGET_EXHAUSTED_WITH_ACCEPTABLE_COVERAGE,
                    f"Max step limit reached ({max_steps} steps) with acceptable coverage ({resolved_count}/{total_questions} questions resolved).",
                )
            else:
                return (
                    True,
                    InvestigationStopReason.BUDGET_EXHAUSTED_WITH_CRITICAL_MISSING_FIELDS,
                    f"Max step limit reached ({max_steps} steps) but {len(unresolved_critical)} critical questions remain unresolved.",
                )

        return False, None, "Investigation in progress."
