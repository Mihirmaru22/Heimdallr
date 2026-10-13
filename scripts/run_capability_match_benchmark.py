"""Heimdallr V3.1: Execute CAPABILITY_MATCH_V1 Benchmark & Output Results.

Runs all 35 tasks across 10 evaluation categories:
- Computes capability selection precision, recall, F1, redundant invocations, and health resilience
- Writes evals/results/capability_match_v1_results.json
- Writes evals/results/capability_match_v1_task_results.json
"""

import json
import logging
import os
import sys

from argus.capability_registry.benchmark import CapabilityMatchEvaluator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("Initializing CAPABILITY_MATCH_V1 Benchmark Suite...")
    evaluator = CapabilityMatchEvaluator()
    summary = evaluator.run_benchmark()

    out_dir = "evals/results"
    os.makedirs(out_dir, exist_ok=True)

    results_path = os.path.join(out_dir, "capability_match_v1_results.json")
    task_results_path = os.path.join(out_dir, "capability_match_v1_task_results.json")

    task_results = summary.pop("task_results")

    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    logger.info(f"Wrote summary to {results_path}")

    with open(task_results_path, "w", encoding="utf-8") as f:
        json.dump(task_results, f, indent=2)
    logger.info(f"Wrote task results to {task_results_path}")

    logger.info("==================================================")
    logger.info(f"CAPABILITY_MATCH_V1 FINISHED: {summary['passed_tasks']}/{summary['total_tasks']} ({summary['pass_rate']*100:.2f}%)")
    logger.info(f"Selection Precision: {summary['selection_precision']}, Recall: {summary['selection_recall']}, F1: {summary['selection_f1']}")


if __name__ == "__main__":
    main()
