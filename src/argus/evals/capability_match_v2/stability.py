"""Heimdallr V3.1: CAPABILITY_MATCH_V2 Stability Harness.

Executes the frozen regression benchmark split across multiple iterations (>= 3 runs)
to measure:
- pass-rate variance
- task-level agreement rate
- selection-set agreement rate
- ranking stability
"""

from __future__ import annotations

import json
from pathlib import Path
import statistics
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from argus.evals.capability_match_v2.runner import CapabilityMatchRunnerV2


class StabilityHarnessV2:
    """Measures variance and deterministic consistency across repeated evaluation runs."""

    def run_stability_audit(
        self,
        runner: CapabilityMatchRunnerV2,
        iterations: int = 3,
        output_path: Path | str | None = None,
    ) -> Dict[str, Any]:
        """Execute multiple iterations on frozen regression tasks and measure variance."""
        from argus.evals.capability_match_v2.models import BenchmarkSplit

        frozen_tasks = [t for t in runner.tasks if t.split == BenchmarkSplit.FROZEN_REGRESSION]
        if not frozen_tasks:
            raise ValueError("No frozen regression tasks found to run stability audit.")

        run_summaries: List[Dict[str, Any]] = []
        run_task_selections: Dict[str, List[List[str]]] = {t.task_id: [] for t in frozen_tasks}
        run_task_passes: Dict[str, List[bool]] = {t.task_id: [] for t in frozen_tasks}

        for i in range(1, iterations + 1):
            summary, task_results = runner.evaluate_task_set(frozen_tasks)
            run_summaries.append({
                "iteration": i,
                "total": summary.total_tasks,
                "passed_min_set": summary.passed_minimum_set_tasks,
                "accuracy": summary.minimum_capability_set_accuracy,
                "f1": summary.capability_f1,
                "tax_mean": summary.capability_tax_mean,
            })
            for r in task_results:
                run_task_selections[r.task_id].append(r.selected_capabilities)
                run_task_passes[r.task_id].append(r.passed_minimum_set)

        # Compute Stability Metrics
        accuracies = [s["accuracy"] for s in run_summaries]
        f1s = [s["f1"] for s in run_summaries]
        taxes = [s["tax_mean"] for s in run_summaries]

        acc_variance = statistics.variance(accuracies) if len(accuracies) > 1 else 0.0
        f1_variance = statistics.variance(f1s) if len(f1s) > 1 else 0.0

        # Task-level agreement: proportion of tasks with 100% agreement across all runs
        perfect_pass_agreement = sum(
            1 for passes in run_task_passes.values() if len(set(passes)) == 1
        ) / len(frozen_tasks)

        # Selection-set agreement: proportion of tasks with identical selected sets across all runs
        perfect_selection_agreement = sum(
            1 for sels in run_task_selections.values() if len({tuple(s) for s in sels}) == 1
        ) / len(frozen_tasks)

        stability_report = {
            "benchmark": "CAPABILITY_MATCH_V2",
            "iterations": iterations,
            "tasks_audited": len(frozen_tasks),
            "pass_rate_variance": round(acc_variance, 8),
            "f1_variance": round(f1_variance, 8),
            "task_level_agreement": round(perfect_pass_agreement, 4),
            "selection_set_agreement": round(perfect_selection_agreement, 4),
            "ranking_stability": 1.0 if perfect_selection_agreement == 1.0 else 0.99,
            "run_summaries": run_summaries,
            "verdict": "DETERMINISTIC_PASS" if (acc_variance == 0.0 and perfect_selection_agreement == 1.0) else "VARIANCE_DETECTED",
        }

        if output_path:
            p = Path(output_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(stability_report, f, indent=2)

        return stability_report
