"""Heimdallr V3.1: CAPABILITY_MATCH_V2 Blind Runner (Mode B).

Executes the frozen 140 tasks under strict blind conditions:
1. Zero evaluator-derived capability labels.
2. specialist_requirements strictly quarantined to empty list.
3. CapabilityLabelLeakageGuard actively verifies zero ground truth leakage.
4. CapabilityMatcher selects minimum sufficient set solely from legitimate runtime inputs.
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
from argus.evals.capability_match_v2.capability_label_leakage_guard import (
    CapabilityLabelLeakageGuard,
    LeakageDetectedException,
)
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


class BlindRunnerV2:
    """Executes CAPABILITY_MATCH_V2 in strict blind mode (Mode B)."""

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

    def run_blind_benchmark(
        self,
        output_results_path: Optional[Path | str] = None,
        output_tasks_path: Optional[Path | str] = None,
    ) -> Tuple[CapabilityMatchV2Summary, List[TaskEvaluationResult]]:
        """Run all tasks in strict blind mode with active leakage protection."""
        task_results: List[TaskEvaluationResult] = []
        ranking_evals: Dict[str, Dict[str, Any]] = {}

        for task in self.tasks:
            # 1. Prepare runtime capabilities (respecting simulated health if present)
            runtime_caps = [c.model_copy(deep=True) for c in self.registry.list()]
            if task.simulate_health_states:
                for c in runtime_caps:
                    if c.capability_id in task.simulate_health_states:
                        c.status = task.simulate_health_states[c.capability_id]

            # 2. Construct STRICT BLIND InvestigationQuestion
            # Explicitly quarantine specialist_requirements and ground truth
            q = InvestigationQuestion(
                question_text=task.question_text,
                question_type=task.question_type,
                required_evidence=list(task.required_evidence),
                related_entities=list(task.related_entities),
                temporal_context=task.temporal_context.copy() if task.temporal_context else None,
                specialist_requirements=[],  # STRICTLY BLIND: NO CAPABILITY LABELS
            )

            # 3. Active Leakage Check
            CapabilityLabelLeakageGuard.check_question_isolation(q)

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

        return summary, task_results
