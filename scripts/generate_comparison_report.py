"""Generate machine-readable comparison report across Argus baseline and challengers."""

import json
from pathlib import Path

BASE_DIR = Path("/data/shared/project/PlayGround/Argus")

FILES = {
    "baseline": BASE_DIR / "data/evals/baseline_v1_core.json",
    "openplanter": BASE_DIR / "evals/results/experiment_openplanter.json",
    "photon": BASE_DIR / "evals/results/experiment_photon.json",
    "firecrawl": BASE_DIR / "evals/results/experiment_firecrawl.json",
    "combined": BASE_DIR / "evals/results/experiment_combined.json",
}

def load_data():
    data = {}
    for key, path in FILES.items():
        with open(path) as f:
            data[key] = json.load(f)
    return data

def build_comparison(data):
    baseline_metrics = data["baseline"]["metrics"]
    
    report = {
        "benchmark_metadata": {
            "version": "1.0",
            "mode": "frozen",
            "git_commit": data["baseline"]["git_commit"],
            "python_version": data["baseline"]["python_version"],
            "tasks_count": baseline_metrics["total_tasks"],
        },
        "experiments": {},
        "comparisons_against_baseline": {},
        "verdicts": {
            "openplanter": {
                "capability": "Research Brain / Investigation Planning & Entity Resolution",
                "verdict": "COMPLEMENT ARGUS",
                "rationale": (
                    "OpenPlanter slightly improved entity precision (16.1% vs 13.5%, +2.6%) by executing "
                    "focused recursive subtasks with lower query spam (6.4 vs 12.4 searches/task). However, "
                    "it regressed evidence correctness (91.9% vs 92.5%) and introduced a new EVIDENCE_ALIGNMENT_FAILURE "
                    "due to lack of domain-tailored facility fan-out. It should not replace Argus ResearchBrain, "
                    "but its recursive acceptance-criteria planning can complement Argus for unstructured exploratory OSINT."
                ),
            },
            "photon": {
                "capability": "Discovery / Web Crawling",
                "verdict": "REJECT CHALLENGER",
                "rationale": (
                    "Photon failed to improve discovery recall (stuck at 71.2%) and regressed entity precision "
                    "(13.0% vs 13.5%, -0.5%) and entity F1 (22.0% vs 22.7%). Photon's regex-based link harvesting "
                    "indiscriminately spiders URLs without relevance ranking or semantic query understanding, pulling "
                    "irrelevant pages. Crucially, Photon carries a restrictive GPL-3.0 copyleft license, creating an "
                    "unacceptable licensing barrier for Heimdallr proprietary integration. Rejected."
                ),
            },
            "firecrawl": {
                "capability": "Acquisition / Document Extraction",
                "verdict": "KEEP ARGUS",
                "rationale": (
                    "Firecrawl produced identical composite scores (80.5%) and pass rates (45.5%) without moving "
                    "entity precision or recall. However, its Markdown conversion stripped HTML layout and whitespace, "
                    "causing slight regressions in evidence correctness on missing-information (90% vs 100%) and "
                    "leadership research tasks (88.9% vs 91.7%). Furthermore, self-hosting full open-source Firecrawl "
                    "requires Redis, Playwright/Puppeteer workers, BullMQ queues, and carries an AGPL-3.0 license, "
                    "introducing immense infrastructure overhead for zero measured gain over Argus's built-in fetcher/extractor."
                ),
            },
            "combined_challenger_stack": {
                "capability": "Combined Challenger Stack (OpenPlanter + Photon + Firecrawl)",
                "verdict": "REJECT CHALLENGER",
                "rationale": (
                    "The combined challenger stack caused a catastrophic collapse in benchmark performance: task pass rate "
                    "collapsed from 45.5% to 9.1% (only 1 passed), entity precision fell to 9.1%, entity recall collapsed "
                    "from 71.2% to 9.1%, and discovery failures surged from 4 to 10. The three challengers compounded each "
                    "other's blind spots: OpenPlanter generated non-domain queries, Photon crawled random links without "
                    "semantic ranking, and Firecrawl stripped structural anchors, leaving downstream Argus workers with empty "
                    "or irrelevant content."
                ),
            },
        },
    }

    # Extract headline metrics for all
    keys_to_compare = [
        "composite_score",
        "overall_pass_rate",
        "entity_precision",
        "entity_recall",
        "entity_f1",
        "entity_resolution_accuracy",
        "field_accuracy",
        "claim_precision",
        "claim_recall",
        "claim_f1",
        "evidence_coverage",
        "evidence_correctness",
        "unsupported_claim_rate",
        "hallucinated_quote_rate",
        "epistemic_accuracy",
        "contradiction_detection_recall",
        "completeness_score",
        "total_security_violations",
        "avg_pages_per_task",
        "avg_searches_per_task",
        "avg_llm_calls_per_task",
        "avg_tokens_per_task",
        "avg_runtime_sec",
        "total_cost_usd",
    ]

    for exp_name, exp_json in data.items():
        m = exp_json["metrics"]
        comp = m.get("composite", {}).get("composite_score", 0.0)
        exp_summary = {
            "composite_score": comp,
            "overall_pass_rate": m["overall_pass_rate"],
            "entity_precision": m["entity_precision"],
            "entity_recall": m["entity_recall"],
            "entity_f1": m["entity_f1"],
            "entity_resolution_accuracy": m["entity_resolution_accuracy"],
            "field_accuracy": m["field_accuracy"],
            "claim_precision": m["claim_precision"],
            "claim_recall": m["claim_recall"],
            "claim_f1": m["claim_f1"],
            "evidence_coverage": m["evidence_coverage"],
            "evidence_correctness": m["evidence_correctness"],
            "unsupported_claim_rate": m["unsupported_claim_rate"],
            "hallucinated_quote_rate": m["hallucinated_quote_rate"],
            "epistemic_accuracy": m["epistemic_accuracy"],
            "contradiction_detection_recall": m["contradiction_detection_recall"],
            "completeness_score": m["completeness_score"],
            "total_security_violations": m["total_security_violations"],
            "avg_pages_per_task": m["avg_pages_per_task"],
            "avg_searches_per_task": m["avg_searches_per_task"],
            "avg_llm_calls_per_task": m["avg_llm_calls_per_task"],
            "avg_tokens_per_task": m["avg_tokens_per_task"],
            "avg_runtime_sec": m["avg_runtime_sec"],
            "total_cost_usd": m["total_cost_usd"],
            "failure_taxonomy_counts": m.get("failure_taxonomy_counts", {}),
            "category_summaries": m.get("category_summaries", {}),
        }
        report["experiments"][exp_name] = exp_summary

        if exp_name != "baseline":
            deltas = {}
            for k in keys_to_compare:
                val = exp_summary[k]
                base_val = report["experiments"]["baseline"][k]
                abs_delta = val - base_val
                rel_delta = (abs_delta / base_val) if base_val != 0 else None
                deltas[k] = {
                    "challenger_value": val,
                    "baseline_value": base_val,
                    "absolute_delta": abs_delta,
                    "relative_delta": rel_delta,
                }
            report["comparisons_against_baseline"][exp_name] = deltas

    return report

def main():
    data = load_data()
    report = build_comparison(data)
    
    out_path = BASE_DIR / "evals/results/comparison_report.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Comparison report written to {out_path}")

if __name__ == "__main__":
    main()
