"""Heimdallr V3.1: Capability Matcher Evaluator Grader.

Implements formal grading logic defined in Section 3, 20, 21, and 22:
- Precision, Recall, F1 against required capabilities
- Minimum Sufficient Set Accuracy (exact set match or acceptable alternative)
- Capability Tax calculation (|selected| - |min_set|)
- Forbidden capability violation detection
- Routing Regret classification
- Decoupled Implementation Selection evaluation
"""

from __future__ import annotations

import time
from typing import Any, List, Set

from argus.capability_registry.models import CapabilityCandidate, HealthStatus
from argus.evals.capability_match_v2.models import (
    CapabilityMatchTaskV2,
    FailureClassification,
    RegretType,
    TaskEvaluationResult,
)


class MatcherGraderV2:
    """Evaluates capability selection decisions strictly against evaluator-isolated ground truth."""

    def grade(
        self,
        task: CapabilityMatchTaskV2,
        selected_candidates: List[CapabilityCandidate],
        all_ranked_candidates: List[CapabilityCandidate],
        runtime_sec: float,
    ) -> TaskEvaluationResult:
        """Perform formal evaluation of selected capabilities and implementations."""
        # 1. Extract distinct selected capabilities and implementations
        selected_caps: List[str] = list(dict.fromkeys(c.capability_id for c in selected_candidates))
        selected_impls: List[str] = [c.implementation_id for c in selected_candidates]

        required_set: Set[str] = set(task.required_capabilities)
        forbidden_set: Set[str] = set(task.forbidden_capabilities)
        minimum_set: Set[str] = set(task.minimum_sufficient_set)
        alt_sets = [set(s) for s in task.acceptable_alternative_sets]
        selected_set: Set[str] = set(selected_caps)

        # 2. Formal Precision / Recall / F1
        tp = len(required_set.intersection(selected_set))
        fp = len(selected_set.difference(required_set))
        fn = len(required_set.difference(selected_set))

        if selected_set:
            precision = tp / len(selected_set)
        else:
            precision = 1.0 if not required_set else 0.0

        if required_set:
            recall = tp / len(required_set)
        else:
            recall = 1.0

        if (precision + recall) > 0.0:
            f1 = 2.0 * precision * recall / (precision + recall)
        else:
            f1 = 0.0

        unnecessary_count = len(selected_set.difference(required_set))
        missed_count = len(required_set.difference(selected_set))
        forbidden_invoked = bool(selected_set.intersection(forbidden_set))

        # 3. Minimum Capability Set Accuracy & Capability Tax
        passed_min_set = (selected_set == minimum_set) or any(selected_set == alt for alt in alt_sets)
        passed_recall = (missed_count == 0)
        capability_tax = max(0, len(selected_set) - len(minimum_set))

        # 4. Decoupled Implementation Selection
        impl_passed = True
        if task.expected_implementation_id:
            # Check if expected implementation was selected for its corresponding capability
            impl_passed = task.expected_implementation_id in selected_impls

        # 5. Routing Regret Classification
        unhealthy_invoked = False
        for c in selected_candidates:
            if c.health_status in (HealthStatus.DISABLED, HealthStatus.UNAVAILABLE, HealthStatus.QUARANTINED):
                unhealthy_invoked = True
                break

        if forbidden_invoked:
            regret = RegretType.WRONG
        elif missed_count > 0:
            regret = RegretType.MISSED_REQUIRED
        elif unhealthy_invoked:
            regret = RegretType.UNAVAILABLE
        elif unnecessary_count > 0:
            regret = RegretType.UNNECESSARY
        else:
            regret = RegretType.NONE

        # 6. Failure Classification
        if passed_min_set and impl_passed and not forbidden_invoked:
            failure_cls = FailureClassification.NONE
        elif forbidden_invoked or (task.category.value == "FALSE_SPECIALIST_TRAP" and unnecessary_count > 0):
            failure_cls = FailureClassification.LEXICAL_ROUTING_FAILURE
        elif task.category.value == "CAPABILITY_HEALTH" and unhealthy_invoked:
            failure_cls = FailureClassification.HEALTH_STATE_FAILURE
        elif not impl_passed:
            failure_cls = FailureClassification.IMPLEMENTATION_SELECTION_FAILURE
        elif unnecessary_count > 0:
            failure_cls = FailureClassification.CAPABILITY_MODEL_FAILURE
        elif missed_count > 0:
            failure_cls = FailureClassification.SEMANTIC_ROUTING_FAILURE
        else:
            failure_cls = FailureClassification.RANKING_FAILURE

        rationale = (
            f"Selected [{', '.join(selected_caps)}] (Impls: {selected_impls}). "
            f"MinSet=[{', '.join(task.minimum_sufficient_set)}]. "
            f"P={precision:.2f}, R={recall:.2f}, F1={f1:.2f}, Tax={capability_tax}. "
            f"MinSetPassed={passed_min_set}, Regret={regret.value}."
        )

        return TaskEvaluationResult(
            task_id=task.task_id,
            category=task.category,
            split=task.split,
            passed_minimum_set=passed_min_set and impl_passed and not forbidden_invoked,
            passed_recall=passed_recall,
            precision=round(precision, 4),
            recall=round(recall, 4),
            f1=round(f1, 4),
            capability_tax=capability_tax,
            unnecessary_capabilities=unnecessary_count,
            missed_capabilities=missed_count,
            forbidden_invoked=forbidden_invoked,
            selected_capabilities=selected_caps,
            selected_implementations=selected_impls,
            expected_minimum_set=task.minimum_sufficient_set,
            implementation_selection_passed=impl_passed,
            regret_type=regret,
            failure_classification=failure_cls,
            runtime_sec=round(runtime_sec, 6),
            rationale=rationale,
        )
