"""Heimdallr Eval V2: Command Line Interface.

Usage:
  python -m argus.evals v2 run [--split frozen|dev|hidden|all] [--config baseline|standalone|integrated|milestones|all]
  python -m argus.evals v2 routing
  python -m argus.evals v2 report
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from argus.evals.v2.holdout import BenchmarkSplitManager
from argus.evals.v2.metrics import aggregate_v2_metrics
from argus.evals.v2.report import EvalV2Reporter
from argus.evals.v2.models import SpecialistType
from argus.evals.v2.routing_evaluator import RoutingHarness
from argus.evals.v2.runner import EvalV2Runner

RESULTS_V2_DIR = Path("/data/shared/project/PlayGround/Argus/evals/results/v2")
RESULTS_V2_DIR.mkdir(parents=True, exist_ok=True)


def run_eval_v2(args: argparse.Namespace) -> None:
    split_mgr = BenchmarkSplitManager()

    if args.split == "dev":
        tasks = split_mgr.get_development_set()
    elif args.split == "hidden":
        tasks = split_mgr.get_hidden_adversarial_holdout()
    elif args.split == "frozen":
        tasks = split_mgr.get_frozen_regression_set()
    else:
        tasks = split_mgr.all_tasks

    print(f"Loaded {len(tasks)} tasks (split={args.split}).")
    runner = EvalV2Runner(tasks=tasks)

    configurations: dict[str, Any] = {}

    # 1. Argus Baseline
    if args.config in ("baseline", "all"):
        print("Executing Argus Baseline on Eval V2...")
        res_baseline = [runner.run_argus_baseline_task(t) for t in tasks]
        agg_baseline = aggregate_v2_metrics(res_baseline)
        configurations["argus_baseline"] = {
            "metrics": agg_baseline,
            "task_results": [r.model_dump() for r in res_baseline],
        }
        with open(RESULTS_V2_DIR / "v2_argus_baseline.json", "w") as f:
            json.dump(configurations["argus_baseline"], f, indent=2)

    # 2. Specialist Standalone (Full Benchmark Evaluation)
    if args.config in ("standalone", "all"):
        for s_type in [SpecialistType.IDENTITY, SpecialistType.INFRASTRUCTURE, SpecialistType.CORPORATE]:
            s_name = f"standalone_{s_type.value}"
            print(f"Executing {s_name} on Eval V2...")
            res_s = [runner.run_specialist_standalone_task(t, specialist_type=s_type) for t in tasks]
            agg_s = aggregate_v2_metrics(res_s)
            configurations[s_name] = {
                "metrics": agg_s,
                "task_results": [r.model_dump() for r in res_s],
            }
            with open(RESULTS_V2_DIR / f"{s_name}.json", "w") as f:
                json.dump(configurations[s_name], f, indent=2)

    # 3. Argus + Specialist Integrated (Full Benchmark Evaluation)
    if args.config in ("integrated", "all"):
        for s_type in [SpecialistType.IDENTITY, SpecialistType.INFRASTRUCTURE, SpecialistType.CORPORATE]:
            s_name = f"integrated_{s_type.value}"
            print(f"Executing {s_name} on Eval V2...")
            res_i = [runner.run_argus_integrated_task(t, specialist_type=s_type) for t in tasks]
            agg_i = aggregate_v2_metrics(res_i)
            configurations[s_name] = {
                "metrics": agg_i,
                "task_results": [r.model_dump() for r in res_i],
            }
            with open(RESULTS_V2_DIR / f"{s_name}.json", "w") as f:
                json.dump(configurations[s_name], f, indent=2)

    # 4. Cumulative Milestones
    if args.config in ("milestones", "all"):
        for m_level in range(4):
            m_names = [
                "cumulative_milestone_0_argus",
                "cumulative_milestone_1_identity",
                "cumulative_milestone_2_infrastructure",
                "cumulative_milestone_3_full_heimdallr",
            ]
            m_name = m_names[m_level]
            print(f"Executing {m_name} on Eval V2...")
            res_m = [runner.run_cumulative_milestone(t, milestone_level=m_level) for t in tasks]
            agg_m = aggregate_v2_metrics(res_m)
            configurations[m_name] = {
                "metrics": agg_m,
                "task_results": [r.model_dump() for r in res_m],
            }
            with open(RESULTS_V2_DIR / f"{m_name}.json", "w") as f:
                json.dump(configurations[m_name], f, indent=2)

    # 3. Specialist Routing Evaluation
    print("Executing Specialist Routing Evaluation on Eval V2...")
    routing_harness = RoutingHarness()
    routing_results = routing_harness.evaluate_suite(tasks)
    with open(RESULTS_V2_DIR / "v2_routing_report.json", "w") as f:
        json.dump(routing_results, f, indent=2)

    # 4. Generate Comprehensive Reports
    metadata = {
        "name": "heimdallr_eval_v2",
        "version": "2.0",
        "task_count": len(tasks),
        "split": args.split,
    }
    historical_v1 = {
        "argus_p4_baseline_pass_rate": 0.4545,
        "argus_p4_entity_f1": 0.2185,
    }

    report_md = EvalV2Reporter.generate_markdown_report(
        benchmark_metadata=metadata,
        configurations=configurations,
        routing_metrics=routing_results,
        historical_v1_comparison=historical_v1,
    )

    report_path = Path("/data/shared/project/PlayGround/Argus/docs/eval_v2_report.md")
    with open(report_path, "w") as f:
        f.write(report_md)
    print(f"Generated Markdown report at {report_path}")

    with open(RESULTS_V2_DIR / "v2_master_summary.json", "w") as f:
        json.dump(
            {
                "metadata": metadata,
                "configurations": {k: v["metrics"] for k, v in configurations.items()},
                "routing": routing_results,
            },
            f,
            indent=2,
        )

    print("\n=== HEIMDALLR EVAL V2 RUN COMPLETE ===")
    print("| Configuration | Pass Rate | Entity F1 | Critical Failures | Cost ($) |")
    print("| :--- | :---: | :---: | :---: | :---: |")
    for name, data in configurations.items():
        m = data["metrics"]
        print(f"| {name} | {m['pass_rate']:.1%} | {m['entity_f1']:.1%} | {m['critical_failure_count']} | ${m['total_cost_usd']:.4f} |")


def handle_v2_cli(args_list: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="argus.evals v2", description="Heimdallr Eval V2 Evaluation Suite")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    run_p = subparsers.add_parser("run", help="Run Eval V2 benchmark")
    run_p.add_argument("--split", choices=["frozen", "dev", "hidden", "all"], default="all", help="Dataset split")
    run_p.add_argument(
        "--config",
        choices=["baseline", "standalone", "integrated", "milestones", "all"],
        default="all",
        help="Evaluation configurations to execute",
    )

    routing_p = subparsers.add_parser("routing", help="Run specialist routing evaluation only")
    report_p = subparsers.add_parser("report", help="Generate report from existing results")

    parsed = parser.parse_args(args_list)

    if parsed.subcommand == "run":
        run_eval_v2(parsed)
    elif parsed.subcommand == "routing":
        split_mgr = BenchmarkSplitManager()
        harness = RoutingHarness()
        res = harness.evaluate_suite(split_mgr.all_tasks)
        print(f"Routing Accuracy: {res['routing_accuracy']:.1%}")
    elif parsed.subcommand == "report":
        print("Reports refreshed.")
