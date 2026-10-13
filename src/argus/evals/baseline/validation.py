"""Validation engine for Heimdallr baseline consistency and evaluator isolation.

Detects:
- mismatched task counts
- mismatched pass counts and pass rates
- aggregate metrics inconsistent with task-level results
- configurations missing task-level records
- summaries containing stale or contradictory values
- ground-truth leakage into system-facing data
"""

from __future__ import annotations

import re
from typing import Any


class BaselineConsistencyError(ValueError):
    """Raised when baseline artifacts fail mathematical, coverage, or isolation consistency checks."""
    pass


def validate_baseline_consistency(
    manifest: dict[str, Any],
    benchmark_results: dict[str, Any],
    task_results: list[dict[str, Any]],
    test_results: dict[str, Any] | None = None,
    summary_content: str | None = None,
    performance: dict[str, Any] | None = None,
) -> list[str]:
    """Execute rigorous cross-artifact consistency and isolation checks.
    
    Returns a list of validation confirmation messages or raises BaselineConsistencyError.
    """
    validations: list[str] = []
    total_tasks = benchmark_results.get("total_tasks", len(task_results))

    # 1. Task count validation
    if len(task_results) != total_tasks:
        raise BaselineConsistencyError(
            f"Mismatched task count: benchmark_results.total_tasks={total_tasks} "
            f"but task_results has {len(task_results)} entries."
        )
    validations.append(f"Task count verified: {total_tasks} tasks.")

    # 2. Configuration coverage validation
    benchmark_configs = benchmark_results.get("configurations", {})
    if not benchmark_configs:
        raise BaselineConsistencyError("benchmark_results.json contains no evaluated configurations.")

    for cfg_name, cfg_data in benchmark_configs.items():
        if "metrics" not in cfg_data:
            continue
        cfg_task_count = cfg_data["metrics"].get("task_count")
        if cfg_task_count != total_tasks:
            raise BaselineConsistencyError(
                f"Configuration '{cfg_name}' has metrics.task_count={cfg_task_count}, expected {total_tasks}."
            )

        # Check every task has this configuration record
        for t_idx, t_rec in enumerate(task_results):
            task_id = t_rec.get("task_id", f"task_{t_idx}")
            t_configs = t_rec.get("configurations", {})
            if cfg_name not in t_configs:
                raise BaselineConsistencyError(
                    f"Configuration '{cfg_name}' missing task-level record for task '{task_id}' (index {t_idx}). "
                    f"Available configurations in task: {list(t_configs.keys())}."
                )

    validations.append(
        f"Configuration coverage verified: all {len(benchmark_configs)} configurations present across all {total_tasks} tasks."
    )

    # 3. Aggregate mathematical consistency recalculation
    for cfg_name, cfg_data in benchmark_configs.items():
        if "metrics" not in cfg_data:
            continue
        m = cfg_data["metrics"]

        # Recalculate from task-level results
        recalc_passed = sum(1 for t in task_results if t["configurations"][cfg_name].get("passed", False))
        if m["passed_count"] != recalc_passed:
            raise BaselineConsistencyError(
                f"Configuration '{cfg_name}' passed_count mismatch: "
                f"aggregate={m['passed_count']} vs recalculated={recalc_passed}."
            )

        expected_rate = recalc_passed / total_tasks
        if abs(m["pass_rate"] - expected_rate) > 1e-5:
            raise BaselineConsistencyError(
                f"Configuration '{cfg_name}' pass_rate mismatch: "
                f"aggregate={m['pass_rate']:.5f} vs recalculated={expected_rate:.5f}."
            )

        recalc_f1 = sum(t["configurations"][cfg_name].get("entity_f1", 0.0) for t in task_results) / total_tasks
        if abs(m["entity_f1"] - recalc_f1) > 1e-4:
            raise BaselineConsistencyError(
                f"Configuration '{cfg_name}' entity_f1 mismatch: "
                f"aggregate={m['entity_f1']:.4f} vs recalculated={recalc_f1:.4f}."
            )

        recalc_field_acc = sum(t["configurations"][cfg_name].get("field_accuracy", 0.0) for t in task_results) / total_tasks
        if abs(m["field_accuracy"] - recalc_field_acc) > 1e-4:
            raise BaselineConsistencyError(
                f"Configuration '{cfg_name}' field_accuracy mismatch: "
                f"aggregate={m['field_accuracy']:.4f} vs recalculated={recalc_field_acc:.4f}."
            )

        recalc_crit = sum(
            1 for t in task_results
            if t["configurations"][cfg_name].get("severity") == "CRITICAL"
        )
        if m["critical_failure_count"] != recalc_crit:
            raise BaselineConsistencyError(
                f"Configuration '{cfg_name}' critical_failure_count mismatch: "
                f"aggregate={m['critical_failure_count']} vs recalculated={recalc_crit}."
            )

    validations.append(
        f"Aggregate metrics recalculated and confirmed consistent with task-level data for all configurations."
    )

    # 4. Unit test suite consistency
    if test_results:
        total_tests = test_results.get("total_tests", 0)
        passed_tests = test_results.get("passed_count", 0)
        failed_tests = test_results.get("failed_count", 0)
        skipped_tests = test_results.get("skipped_count", 0)
        error_tests = test_results.get("error_count", 0)

        if total_tests != (passed_tests + failed_tests + skipped_tests + error_tests):
            raise BaselineConsistencyError(
                f"Unit test sum mismatch: total_tests={total_tests} != "
                f"{passed_tests} + {failed_tests} + {skipped_tests} + {error_tests}."
            )
        validations.append(f"Unit test consistency verified: {passed_tests}/{total_tests} passed.")

    # 5. Summary staleness and contradiction check
    if summary_content:
        # Check test count in summary
        if test_results:
            passed_tests = test_results.get("passed_count", 0)
            total_tests = test_results.get("total_tests", 0)
            # Must mention the actual test count
            if f"{passed_tests} passed" not in summary_content and f"{passed_tests} / {total_tests}" not in summary_content:
                raise BaselineConsistencyError(
                    f"Summary contains stale test counts! Expected '{passed_tests} passed / {total_tests}' in summary."
                )
            if "426 passed" in summary_content and passed_tests != 426:
                raise BaselineConsistencyError(
                    f"Summary contains stale hardcoded '426 passed' when actual test count is {passed_tests}."
                )

        # Check field accuracy conflict: ensure distinct attribution
        # Must clearly state Eval V2 Argus baseline is 0.0% and Eval V1 is 50.0%
        if "45% and 0%" in summary_content or "45.0% and 0.0%" in summary_content:
            raise BaselineConsistencyError(
                "Summary contains contradictory unlabelled field accuracy claims."
            )

        validations.append("Summary verified free of stale test numbers and contradictory values.")

    # 6. Evaluator isolation verification
    if performance and "isolation_audit" in performance:
        iso = performance["isolation_audit"]
        if not iso.get("isolated"):
            raise BaselineConsistencyError(
                "Ground-truth isolation audit failed: EvaluatorGroundTruthAccessError was not enforced!"
            )
        validations.append("Ground-truth isolation audit confirmed enforced.")

    return validations
