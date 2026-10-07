"""Print formatted comparison tables."""
import json

with open("evals/results/comparison_report.json") as f:
    d = json.load(f)

print("=== HEADLINE COMPARISON ===")
header = "| Metric | Baseline | OpenPlanter | Photon | Firecrawl | Combined |"
print(header)
print("| :--- | :---: | :---: | :---: | :---: | :---: |")
metrics = [
    ("Composite Score", "composite_score", "{:.1f}%"),
    ("Task Pass Rate", "overall_pass_rate", "{:.1%}"),
    ("Entity Precision", "entity_precision", "{:.1%}"),
    ("Entity Recall", "entity_recall", "{:.1%}"),
    ("Entity F1", "entity_f1", "{:.1%}"),
    ("Entity Resolution Acc", "entity_resolution_accuracy", "{:.1%}"),
    ("Field Accuracy", "field_accuracy", "{:.1%}"),
    ("Claim Precision", "claim_precision", "{:.1%}"),
    ("Claim Recall", "claim_recall", "{:.1%}"),
    ("Claim F1", "claim_f1", "{:.1%}"),
    ("Evidence Coverage", "evidence_coverage", "{:.1%}"),
    ("Evidence Correctness", "evidence_correctness", "{:.1%}"),
    ("Unsupported Claim Rate", "unsupported_claim_rate", "{:.1%}"),
    ("Hallucinated Quote Rate", "hallucinated_quote_rate", "{:.1%}"),
    ("Epistemic Accuracy", "epistemic_accuracy", "{:.1%}"),
    ("Contradiction Recall", "contradiction_detection_recall", "{:.1%}"),
    ("Research Completeness", "completeness_score", "{:.1%}"),
    ("Security Violations", "total_security_violations", "{:d}"),
    ("Avg Pages / Task", "avg_pages_per_task", "{:.1f}"),
    ("Avg Searches / Task", "avg_searches_per_task", "{:.1f}"),
    ("Avg LLM Calls / Task", "avg_llm_calls_per_task", "{:.1f}"),
    ("Avg Tokens / Task", "avg_tokens_per_task", "{:,.0f}"),
    ("Avg Runtime / Task", "avg_runtime_sec", "{:.2f}s"),
    ("Total Cost (USD)", "total_cost_usd", "${:.4f}"),
]

for label, key, fmt in metrics:
    row = [label]
    for exp in ["baseline", "openplanter", "photon", "firecrawl", "combined"]:
        val = d["experiments"][exp][key]
        if key == "composite_score":
            val = val * 100
        if fmt == "{:d}":
            row.append(fmt.format(int(val)))
        else:
            row.append(fmt.format(val))
    print("| " + " | ".join(row) + " |")

print("\n=== FAILURE TAXONOMY COUNTS ===")
fail_keys = set()
for exp in ["baseline", "openplanter", "photon", "firecrawl", "combined"]:
    fail_keys.update(d["experiments"][exp]["failure_taxonomy_counts"].keys())

print("| Failure Type | Baseline | OpenPlanter | Photon | Firecrawl | Combined |")
print("| :--- | :---: | :---: | :---: | :---: | :---: |")
for fk in sorted(fail_keys):
    row = [fk]
    for exp in ["baseline", "openplanter", "photon", "firecrawl", "combined"]:
        row.append(str(d["experiments"][exp]["failure_taxonomy_counts"].get(fk, 0)))
    print("| " + " | ".join(row) + " |")

print("\n=== CATEGORY PASS RATES ===")
categories = sorted(d["experiments"]["baseline"]["category_summaries"].keys())
print("| Category | Tasks | Baseline | OpenPlanter | Photon | Firecrawl | Combined |")
print("| :--- | :---: | :---: | :---: | :---: | :---: | :---: |")
for cat in categories:
    task_cnt = d["experiments"]["baseline"]["category_summaries"][cat]["task_count"]
    row = [cat, str(task_cnt)]
    for exp in ["baseline", "openplanter", "photon", "firecrawl", "combined"]:
        c_sum = d["experiments"][exp]["category_summaries"].get(cat, {})
        p_rate = c_sum.get("pass_rate", 0.0)
        row.append(f"{p_rate:.0%}")
    print("| " + " | ".join(row) + " |")
