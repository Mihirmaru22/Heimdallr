"""P0.3-R: HOLDOUT BENCHMARK GENERALIZATION TEST SUITE.

Runs the 10 unfamiliar holdout tasks through InvestigationEngine using the isolated
holdout corpus and evaluates them with InvestigationV1Evaluator.

Verifies:
1. InvestigationEngine can solve unseen tasks without benchmark-specific rules.
2. Evaluator computes genuine metrics across the 10 holdout tasks.
3. Results are saved separately to evals/results/p03r_holdout_results.json.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from argus.investigation.benchmark.evaluator import InvestigationV1Evaluator
from argus.investigation.benchmark.holdout_corpus import build_holdout_corpus
from argus.investigation.benchmark.holdout_tasks import build_holdout_tasks
from argus.investigation.orchestrator import InvestigationEngine


def test_holdout_benchmark_suite_execution():
    """Execute all 10 holdout tasks and verify generalizable performance."""
    corpus = build_holdout_corpus()
    tasks = build_holdout_tasks()
    engine = InvestigationEngine(corpus=corpus)
    evaluator = InvestigationV1Evaluator()

    results = []
    for task in tasks:
        engine.reset()
        state = engine.run_investigation(task, max_steps=10)
        eval_result = evaluator.evaluate_single_task(task, state=state)
        results.append(eval_result)

    assert len(results) == 10

    # Aggregate evaluation
    agg = evaluator._compute_aggregate_metrics(results, elapsed_total=5.0)

    # Save holdout results
    results_dir = Path("evals/results")
    results_dir.mkdir(parents=True, exist_ok=True)
    out_file = results_dir / "p03r_holdout_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "milestone": "P0.3-R",
            "type": "holdout_generalization_evaluation",
            "task_count": len(tasks),
            "aggregate_metrics": agg,
            "tasks": results,
        }, f, indent=2)

    assert out_file.exists()

    # Verify pass rate and core generalization metrics
    passed_count = sum(1 for r in results if r["passed"])
    pass_rate = passed_count / len(tasks)
    print(f"\nHoldout Pass Rate: {passed_count}/10 ({pass_rate:.1%})")
    print(f"Mean Evidence Coverage: {agg['5_evidence_requirement_coverage']:.3f}")
    print(f"Mean Semantic Claim Support: {agg['semantic_claim_support_rate']:.3f}")
    print(f"Mean Structural Provenance: {agg['structural_provenance_rate']:.3f}")

    # Generalization bar: at least 70% of holdout tasks must pass
    assert pass_rate >= 0.70, f"Expected holdout pass rate >= 70%, got {pass_rate:.1%}"
    assert agg["5_evidence_requirement_coverage"] >= 0.70
    assert agg["semantic_claim_support_rate"] >= 0.70


@pytest.mark.parametrize("task_idx", range(10))
def test_individual_holdout_task(task_idx: int):
    """Test individual holdout task execution deterministically."""
    corpus = build_holdout_corpus()
    tasks = build_holdout_tasks()
    task = tasks[task_idx]

    engine = InvestigationEngine(corpus=corpus)
    evaluator = InvestigationV1Evaluator()

    state = engine.run_investigation(task, max_steps=10)
    eval_result = evaluator.evaluate_single_task(task, state=state)

    # State must be stopped validly
    assert state.stop_state.is_stopped
    # Claims must be extracted
    assert len(state.claims) > 0
    # Must have structural provenance
    assert eval_result["structural_provenance_rate"] >= 0.50
