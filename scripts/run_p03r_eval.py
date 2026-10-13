"""P0.3-R: Full Benchmark and Holdout Evaluation Runner.

Runs:
1. Official Development Benchmark (25 frozen tasks)
2. Isolated Holdout Benchmark (10 unfamiliar tasks)
Saves results and prints comparison scorecards.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from argus.investigation.benchmark.evaluator import InvestigationV1Evaluator
from argus.investigation.benchmark.holdout_corpus import build_holdout_corpus
from argus.investigation.benchmark.holdout_tasks import build_holdout_tasks
from argus.investigation.benchmark.tasks import RESEARCH_ACCURACY_V3_TASKS
from argus.investigation.orchestrator import InvestigationEngine


def run_all_evaluations():
    out_dir = Path("evals/results")
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("1. RUNNING P0.3-R DEVELOPMENT BENCHMARK (25 FROZEN TASKS)")
    print("=" * 80)
    dev_evaluator = InvestigationV1Evaluator(output_dir=out_dir)
    dev_res = dev_evaluator.run_benchmark(RESEARCH_ACCURACY_V3_TASKS)

    dev_agg = dev_res["results"]
    dev_tasks = dev_res["tasks"]

    with open(out_dir / "p03r_benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump({
            "milestone": "P0.3-R",
            "type": "development_frozen_benchmark",
            "total_tasks": len(dev_tasks),
            "passed_tasks": sum(1 for t in dev_tasks if t["passed"]),
            "pass_rate": dev_agg["1_objective_completion"],
            "aggregate_metrics": dev_agg,
            "tasks": dev_tasks,
        }, f, indent=2)

    print(f"\nDevelopment Benchmark Complete: {sum(1 for t in dev_tasks if t['passed'])}/{len(dev_tasks)} passed ({dev_agg['1_objective_completion']:.1%})")
    print(f"Mean Evidence Requirement Coverage (Recall): {dev_agg['5_evidence_requirement_coverage']:.3f}")
    print(f"Mean Relevant Evidence Precision: {dev_agg['6_relevant_evidence_precision']:.3f}")
    print(f"Mean Structural Provenance: {dev_agg['structural_provenance_rate']:.3f}")
    print(f"Mean Semantic Claim Support: {dev_agg['semantic_claim_support_rate']:.3f}")
    print(f"Citation Validity: {dev_agg['citation_validity_rate']:.3f}")
    print(f"Redundant Action Rate: {dev_agg['8_redundant_action_rate']:.3f}")

    print("\n" + "=" * 80)
    print("2. RUNNING P0.3-R HOLDOUT BENCHMARK (10 UNFAMILIAR TASKS)")
    print("=" * 80)
    holdout_corpus = build_holdout_corpus()
    holdout_tasks = build_holdout_tasks()
    holdout_evaluator = InvestigationV1Evaluator(output_dir=out_dir)
    holdout_evaluator.corpus = holdout_corpus

    holdout_results = []
    t_start = time.perf_counter()
    for task in holdout_tasks:
        res = holdout_evaluator.evaluate_single_task(task)
        holdout_results.append(res)
    elapsed = time.perf_counter() - t_start

    holdout_agg = holdout_evaluator._compute_aggregate_metrics(holdout_results, elapsed_total=elapsed)

    with open(out_dir / "p03r_holdout_results.json", "w", encoding="utf-8") as f:
        json.dump({
            "milestone": "P0.3-R",
            "type": "holdout_generalization_benchmark",
            "total_tasks": len(holdout_tasks),
            "passed_tasks": sum(1 for t in holdout_results if t["passed"]),
            "pass_rate": holdout_agg["1_objective_completion"],
            "aggregate_metrics": holdout_agg,
            "tasks": holdout_results,
        }, f, indent=2)

    print(f"\nHoldout Benchmark Complete: {sum(1 for t in holdout_results if t['passed'])}/{len(holdout_tasks)} passed ({holdout_agg['1_objective_completion']:.1%})")
    print(f"Mean Evidence Requirement Coverage (Recall): {holdout_agg['5_evidence_requirement_coverage']:.3f}")
    print(f"Mean Relevant Evidence Precision: {holdout_agg['6_relevant_evidence_precision']:.3f}")
    print(f"Mean Structural Provenance: {holdout_agg['structural_provenance_rate']:.3f}")
    print(f"Mean Semantic Claim Support: {holdout_agg['semantic_claim_support_rate']:.3f}")
    print(f"Citation Validity: {holdout_agg['citation_validity_rate']:.3f}")

    print("\n" + "=" * 80)
    print("EVALUATION RUN COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    run_all_evaluations()
