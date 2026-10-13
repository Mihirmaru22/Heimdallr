"""Heimdallr V3.1: Leakage Knockout & Blind Validation Orchestrator.

Executes:
1. Mode A: A_CURRENT (Current benchmark run)
2. Mode B: B_BLIND (Strict blind mode, zero specialist requirements, active leakage guard)
3. Mode C: C_ADVERSARIAL (Adversarial wrong hints injected)
4. Stability Audits (3 runs each for Mode A, Mode B, Mode C)
5. Task-Level Delta Analysis (A vs B, B vs C)
6. Production Investigation Engine Object Capture
7. Generates JSON deliverables in proofs/ and evals/results/
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import shutil
import sys
import time
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from argus.capability_registry.matcher import CapabilityMatcher
from argus.capability_registry.registry import CapabilityRegistry
from argus.evals.capability_match_v2.adversarial_hint_runner import AdversarialHintRunnerV2
from argus.evals.capability_match_v2.blind_runner import BlindRunnerV2
from argus.evals.capability_match_v2.capability_label_leakage_guard import CapabilityLabelLeakageGuard
from argus.evals.capability_match_v2.fixtures.tasks import build_capability_match_v2_tasks
from argus.evals.capability_match_v2.runner import CapabilityMatchRunnerV2
from argus.investigation.orchestrator import InvestigationEngine
from argus.investigation.question import InvestigationQuestion

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROOFS_DIR = Path("/data/shared/project/PlayGround/Argus/proofs")
RESULTS_DIR = Path("/data/shared/project/PlayGround/Argus/evals/results")


def run_mode_a_current(tasks: list) -> tuple:
    runner = CapabilityMatchRunnerV2(tasks=tasks)
    return runner.evaluate_task_set(tasks, leakage_status="PASS")


def run_mode_b_blind(tasks: list) -> tuple:
    runner = BlindRunnerV2(tasks=tasks)
    return runner.run_blind_benchmark()


def run_mode_c_adversarial(tasks: list) -> tuple:
    runner = AdversarialHintRunnerV2(tasks=tasks)
    return runner.run_adversarial_benchmark()


def compute_stability(run_fn: Any, tasks: list, mode_name: str, iterations: int = 3) -> dict:
    summaries = []
    task_selections_per_run: list[dict[str, list[str]]] = []

    for i in range(iterations):
        summary, results = run_fn(tasks)[:2]
        summaries.append(summary)
        selections = {r.task_id: sorted(r.selected_capabilities) for r in results}
        task_selections_per_run.append(selections)

    pass_rates = [s.minimum_capability_set_accuracy for s in summaries]
    f1s = [s.capability_f1 for s in summaries]

    mean_pr = sum(pass_rates) / len(pass_rates)
    var_pr = sum((p - mean_pr) ** 2 for p in pass_rates) / len(pass_rates)
    std_pr = var_pr ** 0.5

    mean_f1 = sum(f1s) / len(f1s)
    var_f1 = sum((f - mean_f1) ** 2 for f in f1s) / len(f1s)

    # Agreement across runs
    first_run = task_selections_per_run[0]
    total_agreements = 0
    total_checks = 0
    for run in task_selections_per_run[1:]:
        for tid, sel in first_run.items():
            total_checks += 1
            if run.get(tid) == sel:
                total_agreements += 1

    agreement_rate = (total_agreements / total_checks) if total_checks else 1.0

    return {
        "mode": mode_name,
        "iterations": iterations,
        "mean_accuracy": mean_pr,
        "std_dev_accuracy": std_pr,
        "variance_accuracy": var_pr,
        "mean_f1": mean_f1,
        "variance_f1": var_f1,
        "task_level_agreement": agreement_rate,
        "selection_set_agreement": agreement_rate,
        "verdict": "DETERMINISTIC_PASS" if var_pr == 0.0 else "VARIABLE",
    }


def capture_production_investigation_trajectory() -> dict:
    """Run genuine InvestigationEngine and capture the actual question passed into CapabilityMatcher."""
    engine = InvestigationEngine()
    state = engine.start_investigation(
        objective="Verify corporate registration of Apex Technologies Group and enumerate its infrastructure.",
    )

    matcher = CapabilityMatcher()
    registry = CapabilityRegistry()
    from argus.capability_registry.defaults import get_default_capabilities
    for cap in get_default_capabilities():
        registry.register(cap, overwrite=True)

    captured_steps = []
    # Evaluate all initial questions through CapabilityMatcher as real InvestigationEngine does
    for q_id, q_dict in state.questions.items():
        q_obj = InvestigationQuestion(**q_dict)

        # Audit for leakage
        violations = CapabilityLabelLeakageGuard.audit_object_for_leakage(q_dict, f"ProductionQuestion[{q_id}]")

        # Runtime selection
        selected = matcher.select_minimum_sufficient_set(
            question=q_obj,
            capabilities=registry.list(),
            max_candidates=5,
        )

        captured_steps.append({
            "question_id": q_id,
            "question_text": q_obj.question_text,
            "question_type": str(q_obj.question_type),
            "required_evidence": q_obj.required_evidence,
            "specialist_requirements": q_obj.specialist_requirements,
            "evaluator_leakage_detected": bool(violations),
            "selected_capabilities": [c.capability_id for c in selected],
            "selected_implementations": [c.implementation_id for c in selected],
            "match_scores": {c.capability_id: round(c.match_score, 4) for c in selected},
        })

    return {
        "investigation_id": state.investigation_id,
        "objective": state.objective,
        "total_captured_questions": len(captured_steps),
        "steps": captured_steps,
    }


def main() -> None:
    PROOFS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    tasks = build_capability_match_v2_tasks()
    logger.info("Loaded %d frozen tasks for CAPABILITY_MATCH_V2.", len(tasks))

    # 1. Run Static AST Leakage Guard
    logger.info("Running Static AST Leakage Guard...")
    guard_results = CapabilityLabelLeakageGuard.run_ast_leakage_audit()
    logger.info("AST Leakage Guard Status: %s (Violations: %d)",
                guard_results["overall_status"], len(guard_results["violations"]))

    # 2. Run Mode A: Current
    logger.info("Running Mode A (Current)...")
    summary_a, results_a = run_mode_a_current(tasks)
    logger.info("Mode A: Pass Rate: %0.2f%%, F1: %0.4f, Mean Tax: %0.4f",
                summary_a.minimum_capability_set_accuracy * 100, summary_a.capability_f1, summary_a.capability_tax_mean)

    # 3. Run Mode B: Blind
    logger.info("Running Mode B (Blind)...")
    summary_b, results_b = run_mode_b_blind(tasks)
    logger.info("Mode B: Pass Rate: %0.2f%%, F1: %0.4f, Mean Tax: %0.4f",
                summary_b.minimum_capability_set_accuracy * 100, summary_b.capability_f1, summary_b.capability_tax_mean)

    # 4. Run Mode C: Adversarial
    logger.info("Running Mode C (Adversarial)...")
    summary_c, results_c, hints_c = run_mode_c_adversarial(tasks)
    logger.info("Mode C: Pass Rate: %0.2f%%, F1: %0.4f, Mean Tax: %0.4f",
                summary_c.minimum_capability_set_accuracy * 100, summary_c.capability_f1, summary_c.capability_tax_mean)

    # 5. Delta Analysis
    logger.info("Performing Task-Level Delta Analysis...")
    task_map_a = {r.task_id: r for r in results_a}
    task_map_b = {r.task_id: r for r in results_b}
    task_map_c = {r.task_id: r for r in results_c}

    deltas_a_vs_b = []
    deltas_b_vs_c = []

    for t in tasks:
        tid = t.task_id
        ra = task_map_a[tid]
        rb = task_map_b[tid]
        rc = task_map_c[tid]

        # A vs B
        if ra.selected_capabilities != rb.selected_capabilities:
            deltas_a_vs_b.append({
                "task_id": tid,
                "question": t.question_text,
                "a_selected": ra.selected_capabilities,
                "b_selected": rb.selected_capabilities,
                "expected": t.minimum_sufficient_set,
                "reason": "Mode B selected different capabilities than Mode A",
                "classification": "LEAKAGE_DEPENDENCY" if ra.passed_minimum_set and not rb.passed_minimum_set else "ROUTING_REFINEMENT",
            })

        # B vs C
        if rb.selected_capabilities != rc.selected_capabilities:
            injected = hints_c.get(tid, {}).get("injected_hint", "unknown")
            deltas_b_vs_c.append({
                "task_id": tid,
                "question": t.question_text,
                "expected": t.minimum_sufficient_set,
                "injected_hint": injected,
                "b_selected": rb.selected_capabilities,
                "c_selected": rc.selected_capabilities,
                "hint_influenced": bool(injected in [c.lower() for c in rc.selected_capabilities] or any(injected in c.lower() for c in rc.selected_capabilities)),
                "classification": "MATCHER_FAILURE" if not rc.passed_minimum_set else "ROBUST_SELECTION",
            })

    logger.info("Deltas A vs B: %d, Deltas B vs C: %d", len(deltas_a_vs_b), len(deltas_b_vs_c))

    # 6. Stability (3 runs each)
    logger.info("Running 3-run Stability Audits across all modes...")
    stability_a = compute_stability(run_mode_a_current, tasks, "Mode A (Current)", iterations=3)
    stability_b = compute_stability(run_mode_b_blind, tasks, "Mode B (Blind)", iterations=3)
    stability_c = compute_stability(run_mode_c_adversarial, tasks, "Mode C (Adversarial)", iterations=3)

    stability_report = {
        "benchmark": "CAPABILITY_MATCH_V2",
        "iterations_per_mode": 3,
        "modes": {
            "A_CURRENT": stability_a,
            "B_BLIND": stability_b,
            "C_ADVERSARIAL": stability_c,
        },
        "overall_stability": "DETERMINISTIC_PASS" if (stability_a["variance_accuracy"] == 0.0 and stability_b["variance_accuracy"] == 0.0 and stability_c["variance_accuracy"] == 0.0) else "VARIABLE",
    }

    # 7. Production Trajectory
    logger.info("Capturing Production Investigation Engine Trajectory...")
    production_trajectory = capture_production_investigation_trajectory()

    # 8. Save Proof Deliverables
    logger.info("Saving deliverable artifacts...")

    # Knockout comparison results
    knockout_summary = {
        "benchmark": "CAPABILITY_MATCH_V2",
        "total_tasks": len(tasks),
        "comparison_table": {
            "A_CURRENT": {
                "tasks": summary_a.total_tasks,
                "precision": summary_a.capability_precision,
                "recall": summary_a.capability_recall,
                "f1": summary_a.capability_f1,
                "minimum_set_accuracy": summary_a.minimum_capability_set_accuracy,
                "exact_set_accuracy": summary_a.exact_set_accuracy,
                "unnecessary_rate": summary_a.unnecessary_invocation_rate,
                "forbidden_rate": summary_a.forbidden_invocation_rate,
                "capability_tax": summary_a.capability_tax_mean,
                "implementation_accuracy": summary_a.implementation_selection_accuracy,
            },
            "B_BLIND": {
                "tasks": summary_b.total_tasks,
                "precision": summary_b.capability_precision,
                "recall": summary_b.capability_recall,
                "f1": summary_b.capability_f1,
                "minimum_set_accuracy": summary_b.minimum_capability_set_accuracy,
                "exact_set_accuracy": summary_b.exact_set_accuracy,
                "unnecessary_rate": summary_b.unnecessary_invocation_rate,
                "forbidden_rate": summary_b.forbidden_invocation_rate,
                "capability_tax": summary_b.capability_tax_mean,
                "implementation_accuracy": summary_b.implementation_selection_accuracy,
            },
            "C_ADVERSARIAL": {
                "tasks": summary_c.total_tasks,
                "precision": summary_c.capability_precision,
                "recall": summary_c.capability_recall,
                "f1": summary_c.capability_f1,
                "minimum_set_accuracy": summary_c.minimum_capability_set_accuracy,
                "exact_set_accuracy": summary_c.exact_set_accuracy,
                "unnecessary_rate": summary_c.unnecessary_invocation_rate,
                "forbidden_rate": summary_c.forbidden_invocation_rate,
                "capability_tax": summary_c.capability_tax_mean,
                "implementation_accuracy": summary_c.implementation_selection_accuracy,
            },
        },
        "findings": {
            "a_vs_b_divergence": len(deltas_a_vs_b),
            "b_vs_c_divergence": len(deltas_b_vs_c),
            "leakage_dependence_detected": bool(deltas_a_vs_b),
            "adversarial_resistance_rate": summary_c.minimum_capability_set_accuracy,
        },
        "decision": "GO" if summary_b.minimum_capability_set_accuracy >= 0.95 and summary_c.minimum_capability_set_accuracy >= 0.95 else "FIX",
    }

    with open(PROOFS_DIR / "capability_match_v2_knockout_results.json", "w", encoding="utf-8") as f:
        json.dump(knockout_summary, f, indent=2)
    shutil.copy(PROOFS_DIR / "capability_match_v2_knockout_results.json", RESULTS_DIR / "capability_match_v2_knockout_results.json")

    # Task Deltas
    task_deltas_data = {
        "deltas_a_vs_b": deltas_a_vs_b,
        "deltas_b_vs_c": deltas_b_vs_c,
    }
    with open(PROOFS_DIR / "capability_match_v2_task_deltas.json", "w", encoding="utf-8") as f:
        json.dump(task_deltas_data, f, indent=2)
    shutil.copy(PROOFS_DIR / "capability_match_v2_task_deltas.json", RESULTS_DIR / "capability_match_v2_task_deltas.json")

    # Leakage Audit Results
    with open(PROOFS_DIR / "capability_match_v2_leakage_audit.json", "w", encoding="utf-8") as f:
        json.dump(guard_results, f, indent=2)
    shutil.copy(PROOFS_DIR / "capability_match_v2_leakage_audit.json", RESULTS_DIR / "capability_match_v2_leakage_audit.json")

    # Stability
    with open(PROOFS_DIR / "capability_match_v2_stability.json", "w", encoding="utf-8") as f:
        json.dump(stability_report, f, indent=2)
    shutil.copy(PROOFS_DIR / "capability_match_v2_stability.json", RESULTS_DIR / "capability_match_v2_stability.json")

    # Production Trajectories
    with open(PROOFS_DIR / "capability_match_v2_trajectories.json", "w", encoding="utf-8") as f:
        json.dump(production_trajectory, f, indent=2)
    shutil.copy(PROOFS_DIR / "capability_match_v2_trajectories.json", RESULTS_DIR / "capability_match_v2_trajectories.json")

    logger.info("All knockout validation proofs written to %s and %s", PROOFS_DIR, RESULTS_DIR)


if __name__ == "__main__":
    main()
