"""Heimdallr V3.1: CAPABILITY_MATCH_V2 Adversarial Hint Runner (Mode C).

Injects deliberately conflicting/incorrect capability hints into
specialist_requirements for all 140 tasks to determine whether the
matcher resists adversarial distortion or follows incorrect hints.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple

from argus.capability_registry.defaults import get_default_capabilities
from argus.capability_registry.matcher import CapabilityMatcher
from argus.capability_registry.models import CapabilityCandidate
from argus.capability_registry.registry import CapabilityRegistry
from argus.evals.capability_match_v2.fixtures.tasks import build_capability_match_v2_tasks
from argus.evals.capability_match_v2.matcher_grader import MatcherGraderV2
from argus.evals.capability_match_v2.metrics import MetricsCalculatorV2
from argus.evals.capability_match_v2.models import (
    CapabilityMatchTaskV2,
    CapabilityMatchV2Summary,
    TaskEvaluationResult,
)
from argus.investigation.question import InvestigationQuestion

logger = logging.getLogger(__name__)


def generate_adversarial_hint(task: CapabilityMatchTaskV2) -> str:
    """Generate a deterministic, incorrect specialist hint conflicting with task requirements."""
    req_caps = [c.lower() for c in task.required_capabilities]
    # If task needs corporate, inject infrastructure or identity
    if any("corporate" in c for c in req_caps):
        if any("infrastructure" in c for c in req_caps):
            return "identity"
        return "infrastructure"
    # If task needs infrastructure, inject identity or corporate
    if any("infrastructure" in c for c in req_caps):
        return "identity"
    # If task needs identity, inject corporate
    if any("identity" in c for c in req_caps):
        return "corporate"
    # For general research tasks, inject corporate
    return "corporate"


class AdversarialHintRunnerV2:
    """Executes CAPABILITY_MATCH_V2 in adversarial hint injection mode (Mode C)."""

    def __init__(
        self,
        registry: Optional[CapabilityRegistry] = None,
        matcher: Optional[CapabilityMatcher] = None,
        tasks: Optional[List[CapabilityMatchTaskV2]] = None,
    ) -> None:
        self.registry = registry or CapabilityRegistry()
        if not self.registry.list():
            for cap in get_default_capabilities():
                self.registry.register(cap, overwrite=True)
        self.matcher = matcher or CapabilityMatcher()
        self.grader = MatcherGraderV2()
        self.metrics_calc = MetricsCalculatorV2()
        self.tasks = tasks or build_capability_match_v2_tasks()

    def run_adversarial_benchmark(
        self,
        output_results_path: Optional[Path | str] = None,
        output_tasks_path: Optional[Path | str] = None,
    ) -> Tuple[CapabilityMatchV2Summary, List[TaskEvaluationResult], Dict[str, Dict[str, Any]]]:
        """Run all tasks with adversarial capability hints injected."""
        task_results: List[TaskEvaluationResult] = []
        ranking_evals: Dict[str, Dict[str, Any]] = {}
        injected_hints: Dict[str, Dict[str, Any]] = {}

        for task in self.tasks:
            # 1. Prepare runtime capabilities (respecting simulated health if present)
            runtime_caps = [c.model_copy(deep=True) for c in self.registry.list()]
            if task.simulate_health_states:
                for c in runtime_caps:
                    if c.capability_id in task.simulate_health_states:
                        c.status = task.simulate_health_states[c.capability_id]

            # 2. Inject adversarial hint
            wrong_hint = generate_adversarial_hint(task)
            injected_hints[task.task_id] = {
                "task_id": task.task_id,
                "required_capabilities": task.required_capabilities,
                "injected_hint": wrong_hint,
            }

            # 3. Construct InvestigationQuestion with adversarial hint
            q = InvestigationQuestion(
                question_text=task.question_text,
                question_type=task.question_type,
                required_evidence=list(task.required_evidence),
                related_entities=list(task.related_entities),
                temporal_context=task.temporal_context.copy() if task.temporal_context else None,
                specialist_requirements=[wrong_hint],  # ADVERSARIAL INJECTION
            )

            # 4. Measure execution
            t_start = time.perf_counter()
            all_ranked = self.matcher.match(
                question=q,
                state=None,
                capabilities=runtime_caps,
                max_candidates=5,
            )
            selected = self.matcher.select_minimum_sufficient_set(
                question=q,
                state=None,
                capabilities=runtime_caps,
                max_candidates=5,
            )
            elapsed = time.perf_counter() - t_start

            # 5. Ranking evaluation
            expected_set = set(task.required_capabilities)
            ranked_cap_ids = [c.capability_id for c in all_ranked]
            top1_hit = bool(ranked_cap_ids and ranked_cap_ids[0] in expected_set)
            top3_hit = bool(set(ranked_cap_ids[:3]).intersection(expected_set))

            reciprocal_rank = 0.0
            for rank_idx, cid in enumerate(ranked_cap_ids, 1):
                if cid in expected_set:
                    reciprocal_rank = 1.0 / rank_idx
                    break

            ranking_evals[task.task_id] = {
                "top1_hit": top1_hit,
                "top3_hit": top3_hit,
                "reciprocal_rank": reciprocal_rank,
            }

            # 6. Post-execution Grading
            eval_res = self.grader.grade(
                task=task,
                selected_candidates=selected,
                all_ranked_candidates=all_ranked,
                runtime_sec=elapsed,
            )
            task_results.append(eval_res)

        summary = self.metrics_calc.compute_summary(
            task_results=task_results,
            ranking_evals=ranking_evals,
            leakage_status="PASS",
        )

        if output_results_path:
            p_res = Path(output_results_path)
            p_res.parent.mkdir(parents=True, exist_ok=True)
            with open(p_res, "w", encoding="utf-8") as f:
                json.dump(summary.model_dump(), f, indent=2)

        if output_tasks_path:
            p_task = Path(output_tasks_path)
            p_task.parent.mkdir(parents=True, exist_ok=True)
            with open(p_task, "w", encoding="utf-8") as f:
                json.dump([r.model_dump() for r in task_results], f, indent=2)

        return summary, task_results, injected_hints
