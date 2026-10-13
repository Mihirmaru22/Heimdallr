"""Heimdallr V3.1: CAPABILITY_MATCH_V2 Evaluation Runner.

Executes tasks through the Capability Registry and Capability Matcher,
grades decisions through MatcherGraderV2, and aggregates metrics.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple

from argus.capability_registry.defaults import get_default_capabilities
from argus.capability_registry.matcher import CapabilityMatcher
from argus.capability_registry.models import CapabilityCandidate, HealthStatus
from argus.capability_registry.registry import CapabilityRegistry
from argus.evals.capability_match_v2.fixtures.tasks import build_capability_match_v2_tasks
from argus.evals.capability_match_v2.matcher_grader import MatcherGraderV2
from argus.evals.capability_match_v2.metrics import MetricsCalculatorV2
from argus.evals.capability_match_v2.models import (
    BenchmarkSplit,
    CapabilityMatchTaskV2,
    CapabilityMatchV2Summary,
    TaskEvaluationResult,
)
from argus.investigation.question import InvestigationQuestion

logger = logging.getLogger(__name__)


class CapabilityMatchRunnerV2:
    """Orchestrates benchmark task execution, grading, and deliverable production."""

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

    def evaluate_task_set(
        self, tasks: List[CapabilityMatchTaskV2], leakage_status: str = "PASS"
    ) -> Tuple[CapabilityMatchV2Summary, List[TaskEvaluationResult]]:
        """Evaluate a given list of benchmark tasks."""
        task_results: List[TaskEvaluationResult] = []
        ranking_evals: Dict[str, Dict[str, Any]] = {}

        for task in tasks:
            # 1. Prepare runtime registry view with simulated health states if requested
            runtime_caps = [c.model_copy(deep=True) for c in self.registry.list()]
            if task.simulate_health_states:
                for c in runtime_caps:
                    if c.capability_id in task.simulate_health_states:
                        c.status = task.simulate_health_states[c.capability_id]

            # 2. Convert public task fields into real InvestigationQuestion
            public_view = task.get_public_view()
            q = InvestigationQuestion(
                question_text=public_view["question_text"],
                question_type=public_view["question_type"],
                required_evidence=public_view["required_evidence"],
                related_entities=public_view["related_entities"],
                temporal_context=public_view["temporal_context"],
                specialist_requirements=public_view["specialist_requirements"],
            )

            # 3. Time and execute candidate matching and minimum sufficient set selection
            t_start = time.perf_counter()

            # Candidate ranking
            all_ranked: List[CapabilityCandidate] = self.matcher.match(
                question=q,
                state=None,
                capabilities=runtime_caps,
                max_candidates=5,
            )

            # Minimum sufficient set selection
            selected: List[CapabilityCandidate] = self.matcher.select_minimum_sufficient_set(
                question=q,
                state=None,
                capabilities=runtime_caps,
                max_candidates=5,
            )
            elapsed = time.perf_counter() - t_start

            # 4. Evaluate Ranking Quality
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

            # 5. Grade task result
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
            leakage_status=leakage_status,
        )

        return summary, task_results

    def run_benchmark(
        self,
        output_results_path: Optional[Path | str] = None,
        output_tasks_path: Optional[Path | str] = None,
        split: Optional[BenchmarkSplit] = None,
        leakage_status: str = "PASS",
    ) -> Tuple[CapabilityMatchV2Summary, List[TaskEvaluationResult]]:
        """Run benchmark on selected split (or all tasks) and save JSON results."""
        if split:
            target_tasks = [t for t in self.tasks if t.split == split]
        else:
            target_tasks = self.tasks

        summary, task_results = self.evaluate_task_set(target_tasks, leakage_status=leakage_status)

        if output_results_path:
            p_res = Path(output_results_path)
            p_res.parent.mkdir(parents=True, exist_ok=True)
            with open(p_res, "w", encoding="utf-8") as f:
                json.dump(summary.model_dump(), f, indent=2)
            logger.info("Saved CAPABILITY_MATCH_V2 results to %s", p_res)

        if output_tasks_path:
            p_task = Path(output_tasks_path)
            p_task.parent.mkdir(parents=True, exist_ok=True)
            with open(p_task, "w", encoding="utf-8") as f:
                json.dump([r.model_dump() for r in task_results], f, indent=2)
            logger.info("Saved CAPABILITY_MATCH_V2 task results to %s", p_task)

        return summary, task_results
