"""Trajectory Audit script comparing Argus Baseline, OpenPlanter, and Argus + Planner V2."""

import json
from pathlib import Path

BASE_DIR = Path("/data/shared/project/PlayGround/Argus")

FILES = {
    "baseline": BASE_DIR / "data/evals/baseline_v1_core.json",
    "openplanter": BASE_DIR / "evals/results/experiment_openplanter.json",
    "planner_v2": BASE_DIR / "evals/results/experiment_planner_v2.json",
}

def analyze_trajectories():
    results = {}
    for name, path in FILES.items():
        with open(path) as f:
            data = json.load(f)

        total_tasks_run = len(data["task_results"])
        
        # Trajectory aggregation
        total_queries = 0
        unique_queries_set = set()
        duplicate_queries_count = 0
        total_docs_acquired = 0
        total_claims_extracted = 0
        total_claims_verified = 0
        stop_reasons = {}
        budget_exhaustions = 0
        
        # In frozen benchmark, each task run creates 1 root task, plus followups if any
        # Let's count from metrics and task results
        m = data["metrics"]
        
        # Task level auditing
        for tr in data["task_results"]:
            traj = tr.get("trajectory", {})
            queries = traj.get("queries_issued", [])
            total_queries += len(queries)
            for q in queries:
                q_clean = q.strip().lower()
                if q_clean in unique_queries_set:
                    duplicate_queries_count += 1
                else:
                    unique_queries_set.add(q_clean)
            
            docs = traj.get("documents_acquired_count", 0)
            total_docs_acquired += docs
            claims_ext = traj.get("claims_extracted_count", 0)
            claims_ver = traj.get("claims_verified_count", 0)
            total_claims_extracted += claims_ext
            total_claims_verified += claims_ver
            
            sr = traj.get("stop_reason", "completed")
            stop_reasons[sr] = stop_reasons.get(sr, 0) + 1
            if "budget" in sr.lower():
                budget_exhaustions += 1

        unsupported_claims_rate = m.get("unsupported_claim_rate", 0.0)
        evidence_corr = m.get("evidence_correctness", 0.0)
        evidence_alignment_fails = m.get("failure_taxonomy_counts", {}).get("EVIDENCE_ALIGNMENT_FAILURE", 0)
        contradiction_fails = m.get("failure_taxonomy_counts", {}).get("CONTRADICTION_FAILURE", 0)
        completeness_fails = m.get("failure_taxonomy_counts", {}).get("COMPLETENESS_FAILURE", 0)

        # In baseline / openplanter / planner_v2:
        max_depth = 2 if name in ("baseline", "planner_v2") else 4
        
        results[name] = {
            "total_benchmark_tasks": total_tasks_run,
            "searches_per_task": m.get("avg_searches_per_task", 0.0),
            "pages_acquired_per_task": m.get("avg_pages_per_task", 0.0),
            "tokens_per_task": m.get("avg_tokens_per_task", 0.0),
            "llm_calls_per_task": m.get("avg_llm_calls_per_task", 0.0),
            "latency_sec_per_task": m.get("avg_runtime_sec", 0.0),
            "cost_usd_per_task": m.get("total_cost_usd", 0.0) / total_tasks_run if total_tasks_run else 0.0,
            "entity_precision": m.get("entity_precision", 0.0),
            "entity_recall": m.get("entity_recall", 0.0),
            "entity_f1": m.get("entity_f1", 0.0),
            "field_accuracy": m.get("field_accuracy", 0.0),
            "claim_f1": m.get("claim_f1", 0.0),
            "evidence_correctness": evidence_corr,
            "unsupported_claim_rate": unsupported_claims_rate,
            "evidence_alignment_failures": evidence_alignment_fails,
            "contradiction_failures": contradiction_fails,
            "completeness_failures": completeness_fails,
            "max_task_depth": max_depth,
            "budget_exhaustions": budget_exhaustions,
            "stop_reasons_summary": stop_reasons,
        }

    return results

def main():
    res = analyze_trajectories()
    out_file = BASE_DIR / "evals/results/trajectory_audit_summary.json"
    with open(out_file, "w") as f:
        json.dump(res, f, indent=2)
    print("Trajectory audit summary generated.")

    print("\n| Dimension | Argus Baseline | OpenPlanter-Only | Argus + Planner V2 |")
    print("| :--- | :---: | :---: | :---: |")
    keys = [
        ("Entity Precision", "entity_precision", "{:.1%}"),
        ("Entity Recall", "entity_recall", "{:.1%}"),
        ("Entity F1", "entity_f1", "{:.1%}"),
        ("Evidence Correctness", "evidence_correctness", "{:.1%}"),
        ("Unsupported Claim Rate", "unsupported_claim_rate", "{:.1%}"),
        ("Evidence Alignment Failures", "evidence_alignment_failures", "{:d}"),
        ("Searches / Task", "searches_per_task", "{:.1f}"),
        ("Pages / Task", "pages_acquired_per_task", "{:.1f}"),
        ("LLM Calls / Task", "llm_calls_per_task", "{:.1f}"),
        ("Tokens / Task", "tokens_per_task", "{:,.0f}"),
        ("Latency / Task", "latency_sec_per_task", "{:.2f}s"),
        ("Max Task Depth", "max_task_depth", "{:d}"),
        ("Completeness Failures", "completeness_failures", "{:d}"),
        ("Contradiction Failures", "contradiction_failures", "{:d}"),
    ]
    for label, key, fmt in keys:
        row = [label]
        for exp in ["baseline", "openplanter", "planner_v2"]:
            v = res[exp][key]
            if fmt == "{:d}":
                row.append(fmt.format(int(v)))
            else:
                row.append(fmt.format(v))
        print("| " + " | ".join(row) + " |")

if __name__ == "__main__":
    main()
