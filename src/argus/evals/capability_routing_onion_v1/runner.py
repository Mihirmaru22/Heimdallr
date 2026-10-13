"""Heimdallr V5: CAPABILITY_ROUTING_ONION_V1 Runner.

Evaluates positive and negative routing performance of CapabilityMatcher and ImplementationSelector
across 100 frozen routing tasks (50 positive, 50 negative).
Strictly verifies that keyword appearance alone (e.g. "onion", "dark", "Tor") does not trigger
unwarranted routing to the Onion specialist when the semantic intent and evidence requirement differ.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from argus.capability_registry.defaults import get_default_capabilities
from argus.capability_registry.matcher import CapabilityMatcher
from argus.capability_registry.registry import CapabilityRegistry
from argus.competition.implementation_selector import ImplementationSelector
from argus.evals.capability_routing_onion_v1.tasks import (
    OnionRoutingTask,
    build_routing_onion_v1_tasks,
)
from argus.investigation.question import InvestigationQuestion

logger = logging.getLogger(__name__)


def build_v5_active_registry() -> CapabilityRegistry:
    """Build registry with all capabilities active (including Onion Intelligence)."""
    reg = CapabilityRegistry()
    for cap in get_default_capabilities():
        reg.register(cap.model_copy(deep=True), overwrite=True)
    return reg


class CapabilityRoutingOnionRunner:
    """Runner for CAPABILITY_ROUTING_ONION_V1 benchmark."""

    def __init__(self, tasks: Optional[List[OnionRoutingTask]] = None) -> None:
        self.tasks = tasks or build_routing_onion_v1_tasks()
        self.registry = build_v5_active_registry()
        self.matcher = CapabilityMatcher(self.registry)
        self.selector = ImplementationSelector()

    def execute_routing_suite(self) -> Dict[str, Any]:
        """Execute all 100 tasks and compute positive + negative routing metrics."""
        task_records: List[Dict[str, Any]] = []

        onion_tp = 0
        onion_fp = 0
        onion_fn = 0
        onion_tn = 0

        minimum_set_matches = 0
        unnecessary_invocations_total = 0
        implementation_selection_successes = 0

        for task in self.tasks:
            # Match capabilities strictly from query and evidence requirements (no label peeking!)
            q_obj = InvestigationQuestion(
                question_text=task.query,
                required_evidence=task.evidence_requirements,
            )
            selected_candidates = self.matcher.select_minimum_sufficient_set(
                question=q_obj,
                capabilities=self.registry.list(),
            )
            matched_cap_ids = [c.capability_id for c in selected_candidates]

            # Evaluate Onion specialist invocation
            onion_routed = "onion_intelligence" in matched_cap_ids

            if task.is_onion_positive:
                if onion_routed:
                    onion_tp += 1
                else:
                    onion_fn += 1
            else:
                if onion_routed:
                    onion_fp += 1
                else:
                    onion_tn += 1

            # Minimum capability set accuracy: matched set matches or covers expected evaluator set
            exp_set = set(task.expected_capabilities_evaluator_only)
            matched_set = set(matched_cap_ids)
            is_min_set_match = exp_set.issubset(matched_set) or (task.is_onion_positive and "onion_intelligence" in matched_set)
            if is_min_set_match:
                minimum_set_matches += 1

            # Unnecessary invocations: capabilities matched that were not in expected set and not helpful
            unnecessary_caps = matched_set - exp_set if not task.is_onion_positive else matched_set - {"onion_intelligence"}
            unnecessary_invocations_total += len(unnecessary_caps)

            # Implementation Selector test: for each matched capability, select best implementation
            impl_selected = None
            if onion_routed:
                cap_def = self.registry.get("onion_intelligence")
                if cap_def:
                    sel = self.selector.select_implementation(cap_def)
                    if sel and sel.implementation_id == "impl_onion_integrated_v1":
                        implementation_selection_successes += 1
                        impl_selected = sel.implementation_id
            else:
                implementation_selection_successes += 1

            task_records.append({
                "task_id": task.task_id,
                "is_onion_positive": task.is_onion_positive,
                "query": task.query,
                "matched_capabilities": matched_cap_ids,
                "selected_implementation": impl_selected,
                "onion_routed": onion_routed,
                "expected_evaluator": task.expected_capabilities_evaluator_only,
                "passed": (onion_routed == task.is_onion_positive),
            })

        pos_count = sum(1 for t in self.tasks if t.is_onion_positive)
        neg_count = sum(1 for t in self.tasks if not t.is_onion_positive)
        total = len(self.tasks)

        precision = onion_tp / (onion_tp + onion_fp) if (onion_tp + onion_fp) > 0 else 0.0
        recall = onion_tp / (onion_tp + onion_fn) if (onion_tp + onion_fn) > 0 else 0.0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
        fpr = onion_fp / neg_count if neg_count > 0 else 0.0
        fnr = onion_fn / pos_count if pos_count > 0 else 0.0

        routing_regret = round((onion_fp + onion_fn) / total, 4)

        return {
            "total_tasks": total,
            "positive_tasks": pos_count,
            "negative_tasks": neg_count,
            "confusion_matrix": {
                "TP": onion_tp,
                "TN": onion_tn,
                "FP": onion_fp,
                "FN": onion_fn,
            },
            "metrics": {
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
                "false_positive_rate": round(fpr, 4),
                "false_negative_rate": round(fnr, 4),
                "minimum_capability_set_accuracy": round(minimum_set_matches / total, 4),
                "implementation_selection_accuracy": round(implementation_selection_successes / total, 4),
                "routing_regret": routing_regret,
            },
            "unnecessary_invocations_total": unnecessary_invocations_total,
            "task_records": task_records,
        }
