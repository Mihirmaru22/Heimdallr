#!/usr/bin/env python3
"""Run Controlled Live-Web Evaluation (30 Tasks).

Executes the official 30 live-web evaluation tasks under strict rate limits,
SSRF security policies, and resource bounds.

Produces:
- evals/results/live_web_v1_results.json
- evals/results/live_web_v1_summary.json
- evals/results/live_web_v1_failures.json
"""

import logging
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from argus.investigation.live_web.evaluator import LiveWebEvaluator
from argus.investigation.live_web.tasks import build_live_web_tasks


def main() -> int:
    print("=" * 70)
    print("HEIMDALLR V3 - CONTROLLED LIVE-WEB EVALUATION (P0.3-W)")
    print("=" * 70)

    tasks = build_live_web_tasks()
    print(f"Loaded {len(tasks)} reproducible live-web research tasks across 10 categories.")

    evaluator = LiveWebEvaluator()
    print("\n[Step 1] Executing Controlled Live-Web Evaluation across 30 tasks...")
    out = evaluator.run_benchmark(tasks=tasks, save_results=True)
    summary = out["summary"]

    print("\n" + "=" * 70)
    print("CONTROLLED LIVE-WEB EVALUATION SUMMARY (P0.3-W)")
    print("=" * 70)
    print(f"Total Live Tasks Evaluated:  {summary['total_tasks']}")
    ts = summary["task_level_success"]
    print(f"Task-Level Success:          {ts['percentage']}% ({ts['numerator']}/{ts['denominator']}) [95% CI: {ts['ci_95'][0]}% - {ts['ci_95'][1]}%]")
    es = summary["epistemic_status_accuracy"]
    print(f"Epistemic Status Accuracy:   {es['percentage']}% ({es['numerator']}/{es['denominator']}) [95% CI: {es['ci_95'][0]}% - {es['ci_95'][1]}%]")
    print(f"Answer Element Coverage:     {summary['mean_answer_element_coverage_pct']}%")
    print(f"Citation Precision:          {summary['mean_citation_precision_pct']}%")
    print(f"Global Duration:             {summary['global_runtime_seconds']}s")

    si = summary["source_independence"]
    print(f"\nSource Independence Profile:")
    print(f"  - Raw Sources Collected:     {si['total_raw_sources']}")
    print(f"  - Independent Sources:       {si['total_independent_sources']}")
    print(f"  - Overall Independence Ratio:{si['overall_independence_ratio']}")

    sec = summary["security_compliance"]
    print(f"\nSecurity Compliance:")
    print(f"  - SSRF Violations:           {sec['ssrf_violations_detected']}")
    print(f"  - TLS Verification:          {sec['tls_verification_enforced']}")
    print(f"  - Prohibited Subnets:        {sec['prohibited_subnets_blocked']}")

    gates = summary["acceptance_gates"]
    print(f"\nOverall Live-Web Gate Status: {gates['overall_status']}")
    for gname, gdata in gates["gates"].items():
        status = "PASS" if gdata["passed"] else "FAIL"
        print(f"  - Gate '{gname}': target={gdata['target']}, measured={gdata['measured']} -> {status}")

    return 0 if gates["overall_status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
