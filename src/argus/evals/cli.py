"""Command line interface for the Argus Evaluation Harness.

Commands:
- run: Execute evaluation suite (core subset or full 50-task suite)
- compare: Compare baseline vs current evaluation run
- stability: Run multiple iterations to verify evaluation repeatability
"""

import argparse
import asyncio
import sys
from pathlib import Path

from argus.evals.benchmark import BenchmarkSuite
from argus.evals.metrics import RegressionComparator
from argus.evals.report import EvaluationReporter
from argus.evals.runner import ArgusEvalRunner


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "v2":
        from argus.evals.v2.cli import handle_v2_cli
        handle_v2_cli(sys.argv[2:])
        return
    elif len(sys.argv) > 1 and sys.argv[1] == "v1":
        sys.argv.pop(1)

    parser = argparse.ArgumentParser(
        prog="argus.evals",
        description="Argus Evaluation Harness CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. Run Command
    run_parser = subparsers.add_parser("run", help="Run benchmark evaluation suite")
    run_parser.add_argument(
        "--subset",
        choices=["core", "all"],
        default="core",
        help="Run core subset (11 tasks) or all (50 tasks)",
    )
    run_parser.add_argument(
        "--mode",
        choices=["frozen", "live"],
        default="frozen",
        help="Evaluation mode (frozen deterministic or live web)",
    )
    run_parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output JSON file path",
    )
    run_parser.add_argument(
        "--brain",
        choices=["argus", "openplanter", "planner_v2"],
        default="argus",
        help="Research brain engine (argus, openplanter, or planner_v2)",
    )
    run_parser.add_argument(
        "--discovery",
        choices=["argus", "photon"],
        default="argus",
        help="Discovery engine (argus or photon)",
    )
    run_parser.add_argument(
        "--acquisition",
        choices=["argus", "firecrawl"],
        default="argus",
        help="Acquisition engine (argus or firecrawl)",
    )
    run_parser.add_argument(
        "--scorecard",
        type=str,
        default=None,
        help="Output Markdown scorecard path",
    )

    # 2. Compare Command
    compare_parser = subparsers.add_parser("compare", help="Compare two evaluation runs")
    compare_parser.add_argument("baseline", type=str, help="Path to baseline.json")
    compare_parser.add_argument("current", type=str, help="Path to current.json")
    compare_parser.add_argument(
        "--report",
        type=str,
        default=None,
        help="Optional path to write markdown diff report",
    )

    # 3. Stability Command
    stab_parser = subparsers.add_parser("stability", help="Evaluate benchmark stability across runs")
    stab_parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Number of evaluation iterations",
    )
    stab_parser.add_argument(
        "--subset",
        choices=["core", "all"],
        default="core",
        help="Task subset to test",
    )

    args = parser.parse_args()

    if args.command == "run":
        asyncio.run(handle_run(args))
    elif args.command == "compare":
        handle_compare(args)
    elif args.command == "stability":
        asyncio.run(handle_stability(args))


async def handle_run(args: argparse.Namespace) -> None:
    suite = BenchmarkSuite.load_from_file()
    is_core = args.subset == "core"
    tasks = suite.filter(is_core=True) if is_core else suite.tasks

    print(f"Running Argus Evaluation Suite v{suite.version} ({len(tasks)} tasks, mode={args.mode}, brain={args.brain}, discovery={args.discovery}, acquisition={args.acquisition})...")
    runner = ArgusEvalRunner(
        evaluation_mode=args.mode,
        brain_mode=args.brain,
        discovery_mode=args.discovery,
        acquisition_mode=args.acquisition,
    )
    result = await runner.run_suite(tasks, is_core_subset=is_core)

    scorecard_md = EvaluationReporter.generate_markdown_scorecard(result)
    print("\n" + scorecard_md)

    if args.output:
        EvaluationReporter.save_json(result, args.output)
        print(f"\n[Artifact Saved] JSON result written to: {args.output}")

    if args.scorecard:
        p = Path(args.scorecard)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(scorecard_md)
        print(f"[Artifact Saved] Markdown scorecard written to: {args.scorecard}")


def handle_compare(args: argparse.Namespace) -> None:
    b_run = EvaluationReporter.load_json(args.baseline)
    c_run = EvaluationReporter.load_json(args.current)

    diff = RegressionComparator.compare(b_run, c_run)
    report_md = EvaluationReporter.generate_regression_markdown(diff)
    print("\n" + report_md)

    if args.report:
        p = Path(args.report)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(report_md)
        print(f"\n[Artifact Saved] Regression report written to: {args.report}")


async def handle_stability(args: argparse.Namespace) -> None:
    suite = BenchmarkSuite.load_from_file()
    is_core = args.subset == "core"
    tasks = suite.filter(is_core=True) if is_core else suite.tasks

    print(f"Evaluating Argus stability over {args.runs} runs ({len(tasks)} tasks)...")
    runner = ArgusEvalRunner(evaluation_mode="frozen")
    stability, runs = await runner.run_stability(tasks, num_runs=args.runs)

    print("\n=== ARGUS EVALUATION STABILITY ASSESSMENT ===")
    print(f"Total Iterations: {stability.num_runs}")
    print(f"Pass Rate Mean: {stability.pass_rate_mean * 100:.1f}% ± {stability.pass_rate_stddev * 100:.2f}%")
    print(f"Entity F1 Variance: {stability.entity_f1_variance:.4f}")
    print(f"Claim F1 Variance: {stability.claim_f1_variance:.4f}")
    print(f"Stability Score: {stability.stability_score * 100:.1f}%")
    print(f"Flaky Tasks: {stability.flaky_tasks or 'None (100% deterministic)'}")


if __name__ == "__main__":
    main()
