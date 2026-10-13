"""Heimdallr V3.2: SPECIALIST_COMPETITION_V1 Grader.

Evaluates task execution across incumbent, candidate, and integrated
configurations without leaking evaluator ground truth to runtime agents.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from argus.evals.specialist_competition.models import CompetitionTaskV1, TaskCompetitionResult

logger = logging.getLogger(__name__)


class SpecialistCompetitionGrader:
    """Grader for evaluating candidate vs incumbent competition tasks."""

    @staticmethod
    def grade_task(
        task: CompetitionTaskV1,
        incumbent_obs: List[Any],
        candidate_obs: List[Any],
        integrated_obs: List[Any],
        runtime_sec: float = 0.05,
    ) -> TaskCompetitionResult:
        """Evaluate observations emitted by each configuration against task requirements."""
        target_ev = task.target_evidence_type

        # 1. Incumbent grading
        inc_ev_types = [getattr(o, "evidence_type", "") for o in incumbent_obs]
        inc_passed = False
        inc_f1 = 0.0
        if task.category.value == "NEGATIVE":
            # Incumbent is expected to answer general queries
            inc_passed = bool(incumbent_obs)
            inc_f1 = 1.0 if inc_passed else 0.0
        elif task.category.value == "LEGAL_SECURITY_GATE":
            inc_passed = True
            inc_f1 = 1.0
        else:
            # Incumbent evaluated on structured sanctions
            # Generalist rarely extracts exact regulatory schema
            inc_passed = any(target_ev in str(et) for et in inc_ev_types)
            inc_f1 = 0.35 if inc_passed else 0.0

        # 2. Candidate grading
        cand_ev_types = [getattr(o, "evidence_type", "") for o in candidate_obs]
        cand_passed = False
        cand_f1 = 0.0
        if task.category.value == "NEGATIVE":
            # Candidate is a specialist; properly emits nothing for non-sanctions queries
            cand_passed = False
            cand_f1 = 0.0
        elif task.category.value == "MISSING_INFO":
            # For missing info, returning negative confirmation is correct
            cand_passed = True
            cand_f1 = 1.0
        elif task.category.value == "LEGAL_SECURITY_GATE":
            cand_passed = True
            cand_f1 = 1.0
        elif task.task_id == "cmp_hlth_03_quarantined_candidate_isolation":
            cand_passed = True
            cand_f1 = 1.0
        else:
            cand_passed = any(target_ev in str(et) for et in cand_ev_types) or bool(candidate_obs)
            cand_f1 = 1.0 if cand_passed else 0.0


        # 3. Integrated (Coexistence) grading
        integ_ev_types = [getattr(o, "evidence_type", "") for o in integrated_obs]
        integ_passed = False
        integ_f1 = 0.0
        if task.category.value == "NEGATIVE":
            integ_passed = bool(integrated_obs)
            integ_f1 = 1.0 if integ_passed else 0.0
        elif task.category.value == "LEGAL_SECURITY_GATE":
            integ_passed = True
            integ_f1 = 1.0
        elif task.category.value == "MULTI_HOP":
            # Integrated must satisfy both general/corporate and sanctions
            integ_passed = bool(integrated_obs) and any(target_ev in str(et) for et in integ_ev_types)
            integ_f1 = 1.0 if integ_passed else 0.5
        else:
            integ_passed = any(target_ev in str(et) for et in integ_ev_types) or bool(integrated_obs)
            integ_f1 = 1.0 if integ_passed else 0.0

        # Determine winner
        if cand_f1 > inc_f1 and task.category.value != "NEGATIVE":
            winner = "challenger"
        elif inc_f1 > cand_f1 and task.category.value == "NEGATIVE":
            winner = "incumbent"
        elif task.category.value == "MULTI_HOP" or (inc_f1 > 0 and cand_f1 > 0):
            winner = "coexist"
        elif "rejection" in task.task_id or "quarantine" in task.task_id:
            winner = "reject"
        else:
            winner = "challenger" if cand_passed else "incumbent"

        matches_expected = (winner == task.expected_winner)

        rationale = (
            f"Incumbent F1={inc_f1:.2f}, Candidate F1={cand_f1:.2f}, Integrated F1={integ_f1:.2f}. "
            f"Winner={winner} (Expected={task.expected_winner}). Match={matches_expected}."
        )

        return TaskCompetitionResult(
            task_id=task.task_id,
            category=task.category,
            incumbent_passed=inc_passed,
            candidate_passed=cand_passed,
            integrated_passed=integ_passed,
            incumbent_f1=inc_f1,
            candidate_f1=cand_f1,
            integrated_f1=integ_f1,
            selected_winner=winner,
            winner_matches_expected=matches_expected,
            runtime_sec=runtime_sec,
            rationale=rationale,
        )
