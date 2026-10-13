"""Heimdallr V3.1: Execute Full CAPABILITY_MATCH_V2 Benchmark Suite.

Executes:
1. Evaluator Leakage Audit
2. Benchmark Task Runner across all 140 tasks
3. Stability Variance Audit (3 iterations of frozen regression split)
4. Trajectory Generation
5. Deliverable outputs in proofs/ and evals/results/
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import shutil
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from argus.evals.capability_match_v2.leakage_audit import LeakageAuditorV2
from argus.evals.capability_match_v2.runner import CapabilityMatchRunnerV2
from argus.evals.capability_match_v2.stability import StabilityHarnessV2
from scripts.generate_v2_trajectory_samples import generate_trajectory_samples

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROOFS_DIR = Path("/data/shared/project/PlayGround/Argus/proofs")
RESULTS_DIR = Path("/data/shared/project/PlayGround/Argus/evals/results")


def main() -> None:
    PROOFS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Leakage Audit
    logger.info("==================================================")
    logger.info("Executing Evaluator Leakage Audit...")
    auditor = LeakageAuditorV2()
    leakage_res = auditor.run_audit(output_path=PROOFS_DIR / "capability_match_v2_leakage_audit.json")
    shutil.copy(PROOFS_DIR / "capability_match_v2_leakage_audit.json", RESULTS_DIR / "capability_match_v2_leakage_audit.json")
    logger.info("Leakage Audit Status: %s", leakage_res["overall_status"])

    # 2. Benchmark Runner
    logger.info("==================================================")
    logger.info("Executing CAPABILITY_MATCH_V2 Benchmark across all 140 tasks...")
    runner = CapabilityMatchRunnerV2()
    summary, task_results = runner.run_benchmark(
        output_results_path=PROOFS_DIR / "capability_match_v2_results.json",
        output_tasks_path=PROOFS_DIR / "capability_match_v2_task_results.json",
        leakage_status=leakage_res["overall_status"],
    )
    shutil.copy(PROOFS_DIR / "capability_match_v2_results.json", RESULTS_DIR / "capability_match_v2_results.json")
    shutil.copy(PROOFS_DIR / "capability_match_v2_task_results.json", RESULTS_DIR / "capability_match_v2_task_results.json")

    logger.info("Benchmark Finished: %d/%d tasks passed minimum-set (%0.2f%%)",
                summary.passed_minimum_set_tasks, summary.total_tasks, summary.minimum_capability_set_accuracy * 100)
    logger.info("Precision: %0.4f, Recall: %0.4f, F1: %0.4f",
                summary.capability_precision, summary.capability_recall, summary.capability_f1)
    logger.info("Capability Tax Mean: %0.4f (Max: %d)", summary.capability_tax_mean, summary.capability_tax_max)
    logger.info("Decision: %s", summary.decision)

    # 3. Stability Audit
    logger.info("==================================================")
    logger.info("Executing Stability Audit (3 iterations)...")
    stability_harness = StabilityHarnessV2()
    stability_res = stability_harness.run_stability_audit(
        runner=runner,
        iterations=3,
        output_path=PROOFS_DIR / "capability_match_v2_stability.json",
    )
    shutil.copy(PROOFS_DIR / "capability_match_v2_stability.json", RESULTS_DIR / "capability_match_v2_stability.json")
    logger.info("Stability Verdict: %s (Variance: %s)", stability_res["verdict"], stability_res["pass_rate_variance"])

    # 4. Trajectory Samples
    logger.info("==================================================")
    logger.info("Generating Trajectory Samples...")
    generate_trajectory_samples([
        PROOFS_DIR / "capability_match_v2_trajectory_samples.json",
        RESULTS_DIR / "capability_match_v2_trajectory_samples.json",
    ])
    logger.info("All deliverables produced in %s and %s", PROOFS_DIR, RESULTS_DIR)


if __name__ == "__main__":
    main()
