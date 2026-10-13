#!/usr/bin/env python3
"""Run Generalization Benchmark V2 across all 100 tasks.

Produces:
- evals/results/generalization_v2_results.json
- evals/results/generalization_v2_summary.json
- evals/results/generalization_v2_failures.json
"""

import logging
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from argus.investigation.benchmark.v2.evaluator import GeneralizationV2Evaluator
from argus.investigation.benchmark.v2.tasks import build_generalization_v2_tasks
from argus.investigation.benchmark.v2.manifest import build_v2_manifest, verify_benchmark_isolation


def main() -> int:
    print("=" * 70)
    print("HEIMDALLR V3 - GENERALIZATION BENCHMARK V2 EXECUTION (100 TASKS)")
    print("=" * 70)

    # 1. Verify holdout isolation before execution
    print("\n[Step 1] Verifying Holdout Isolation...")
    iso = verify_benchmark_isolation()
    print(f"Isolation status: {iso['status']} (Files: {iso['files_scanned']}, Violations: {len(iso['violations'])})")
    if not iso["isolation_verified"]:
        print("ERROR: Benchmark isolation check failed!", file=sys.stderr)
        return 1

    # 2. Build manifest
    manifest = build_v2_manifest()
    print(f"Manifest Version: {manifest.version} (Total: {manifest.total_tasks}, Val: {manifest.validation_partition.task_count}, Holdout: {manifest.holdout_partition.task_count})")

    # 3. Initialize Evaluator
    evaluator = GeneralizationV2Evaluator()
    tasks = build_generalization_v2_tasks()
    print(f"Loaded {len(tasks)} benchmark tasks across 8 categories.")

    # 4. Execute Benchmark
    print("\n[Step 2] Executing Benchmark across all 100 tasks...")
    out = evaluator.run_benchmark(tasks=tasks, save_results=True)
    summary = out["summary"]

    # 5. Report summary
    print("\n" + "=" * 70)
    print("GENERALIZATION BENCHMARK V2 RESULTS SUMMARY")
    print("=" * 70)
    print(f"Total Tasks: {summary['total_tasks']}")
    ts = summary["task_level_success"]
    print(f"Task-Level Success:           {ts['percentage']}% ({ts['numerator']}/{ts['denominator']}) [95% CI: {ts['ci_95'][0]}% - {ts['ci_95'][1]}%]")
    es = summary["epistemic_status_accuracy"]
    print(f"Epistemic Status Accuracy:    {es['percentage']}% ({es['numerator']}/{es['denominator']}) [95% CI: {es['ci_95'][0]}% - {es['ci_95'][1]}%]")
    sp = summary["structural_provenance_rate"]
    print(f"Structural Provenance Rate:   {sp['percentage']}% ({sp['numerator']}/{sp['denominator']}) [95% CI: {sp['ci_95'][0]}% - {sp['ci_95'][1]}%]")
    sc = summary["semantic_claim_support_rate"]
    print(f"Semantic Claim Support Rate:  {sc['percentage']}% ({sc['numerator']}/{sc['denominator']}) [95% CI: {sc['ci_95'][0]}% - {sc['ci_95'][1]}%]")

    print("\nCategory Breakdown:")
    for cat, cdata in summary["categories"].items():
        print(f"  - {cat:<32}: {cdata['percentage']}% ({cdata['numerator']}/{cdata['denominator']})")

    gates = summary["acceptance_gates"]
    print(f"\nOverall Acceptance Status: {gates['overall_status']}")
    for gname, gdata in gates["gates"].items():
        status = "PASS" if gdata["passed"] else "FAIL"
        print(f"  - Gate '{gname}': target={gdata['target']}, measured={gdata['measured']} -> {status}")

    return 0 if gates["overall_status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
