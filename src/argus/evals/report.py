"""Report generation and formatting for the Argus Evaluation Harness.

Generates:
- Structured JSON output for programmatic analysis
- Human-readable Markdown scorecards and terminal reports
- Comparative regression reports diffing baseline vs current runs
"""

import json
from pathlib import Path
from typing import Any

from argus.evals.models import BenchmarkRunResult, RegressionDiff, RunStabilityResult


class EvaluationReporter:
    """Formats and serializes evaluation benchmark reports."""

    @staticmethod
    def save_json(result: BenchmarkRunResult, path: Path | str) -> None:
        """Serialize benchmark run result to JSON file."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(result.model_dump_json(indent=2))

    @staticmethod
    def load_json(path: Path | str) -> BenchmarkRunResult:
        """Load benchmark run result from JSON file."""
        p = Path(path)
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return BenchmarkRunResult.model_validate(data)

    @classmethod
    def generate_markdown_scorecard(cls, result: BenchmarkRunResult) -> str:
        """Generate human-readable Markdown evaluation scorecard."""
        m = result.metrics
        lines: list[str] = []

        lines.append(f"# ARGUS V1 EVALUATION SCORECARD")
        lines.append(f"")
        lines.append(f"> **Run ID**: `{result.run_id}`  ")
        lines.append(f"> **Benchmark Version**: `{result.benchmark_version}`  ")
        lines.append(f"> **Evaluation Mode**: `{result.evaluation_mode.upper()}`  ")
        lines.append(f"> **Subset**: `{'Core (11 tasks)' if result.is_core_subset else f'Full ({result.metrics.total_tasks} tasks)'}`  ")
        lines.append(f"> **Timestamp**: `{result.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}`  ")
        lines.append(f"> **Git Commit**: `{result.git_commit}`  ")
        lines.append(f"> **Python**: `{result.python_version}` | **Model**: `{result.model_name}`  ")
        lines.append(f"")

        # Executive Summary
        lines.append("## 1. Executive Summary")
        lines.append("")
        if m.composite:
            comp = m.composite
            lines.append(f"- **Composite Benchmark Score**: **`{comp.composite_score * 100:.1f} / 100`**")
            lines.append(f"  - Research Quality: `{comp.research_quality * 100:.1f}%` (Weight: {comp.weights.research_quality * 100:.0f}%)")
            lines.append(f"  - Evidence Quality: `{comp.evidence_quality * 100:.1f}%` (Weight: {comp.weights.evidence_quality * 100:.0f}%)")
            lines.append(f"  - Safety & Policy: `{comp.safety * 100:.1f}%` (Weight: {comp.weights.safety * 100:.0f}%)")
            lines.append(f"  - Completeness: `{comp.completeness * 100:.1f}%` (Weight: {comp.weights.completeness * 100:.0f}%)")
            lines.append(f"  - Efficiency: `{comp.efficiency * 100:.1f}%` (Weight: {comp.weights.efficiency * 100:.0f}%)")
        lines.append(f"- **Task Pass Rate**: **`{m.overall_pass_rate * 100:.1f}%`** ({m.passed_tasks}/{m.total_tasks} passed)")
        lines.append("")

        # Headline Metrics
        lines.append("## 2. Headline Metrics")
        lines.append("")
        lines.append("| Metric | Value | Target / Status |")
        lines.append("| :--- | :---: | :--- |")
        lines.append(f"| **Entity Precision** | `{m.entity_precision * 100:.1f}%` | {'✅ Optimal' if m.entity_precision >= 0.85 else '⚠️ Suboptimal'} |")
        lines.append(f"| **Entity Recall** | `{m.entity_recall * 100:.1f}%` | {'✅ Optimal' if m.entity_recall >= 0.80 else '⚠️ Suboptimal'} |")
        lines.append(f"| **Entity Resolution Accuracy** | `{m.entity_resolution_accuracy * 100:.1f}%` | {'✅ Optimal' if m.entity_resolution_accuracy >= 0.90 else '⚠️ Suboptimal'} |")
        lines.append(f"| **Field Accuracy** | `{m.field_accuracy * 100:.1f}%` | {'✅ Optimal' if m.field_accuracy >= 0.80 else '⚠️ Suboptimal'} |")
        lines.append(f"| **Claim Precision** | `{m.claim_precision * 100:.1f}%` | {'✅ Optimal' if m.claim_precision >= 0.85 else '⚠️ Suboptimal'} |")
        lines.append(f"| **Claim Recall** | `{m.claim_recall * 100:.1f}%` | {'✅ Optimal' if m.claim_recall >= 0.80 else '⚠️ Suboptimal'} |")
        lines.append(f"| **Evidence Coverage** | `{m.evidence_coverage * 100:.1f}%` | {'✅ Grounded' if m.evidence_coverage >= 0.90 else '⚠️ Low Coverage'} |")
        lines.append(f"| **Evidence Correctness** | `{m.evidence_correctness * 100:.1f}%` | {'✅ Verified' if m.evidence_correctness >= 0.90 else '⚠️ Mismatched'} |")
        lines.append(f"| **Unsupported Claim Rate** | `{m.unsupported_claim_rate * 100:.1f}%` | {'✅ Clean' if m.unsupported_claim_rate <= 0.05 else '🚨 Critical Failure'} |")
        lines.append(f"| **Hallucinated Quote Rate** | `{m.hallucinated_quote_rate * 100:.1f}%` | {'✅ Zero Fabrications' if m.hallucinated_quote_rate == 0.0 else '🚨 Hallucination Detected'} |")
        lines.append(f"| **Epistemic Accuracy** | `{m.epistemic_accuracy * 100:.1f}%` | {'✅ Disciplined' if m.epistemic_accuracy >= 0.85 else '⚠️ Escalation Risk'} |")
        lines.append(f"| **Status Escalation Errors** | `{m.status_escalation_error_count}` | {'✅ Zero Escalations' if m.status_escalation_error_count == 0 else '🚨 Escalation Errors'} |")
        lines.append(f"| **Contradiction Detection** | `{m.contradiction_detection_recall * 100:.1f}%` | {'✅ Detected' if m.contradiction_detection_recall >= 0.80 else '⚠️ Missed Conflicts'} |")
        lines.append(f"| **Unknown Accuracy** | `{m.unknown_accuracy * 100:.1f}%` | {'✅ Calibrated Uncertainty' if m.unknown_accuracy >= 0.90 else '⚠️ Overconfident'} |")
        lines.append(f"| **Research Completeness** | `{m.completeness_score * 100:.1f}%` | {'✅ Complete' if m.completeness_score >= 0.80 else '⚠️ Incomplete'} |")
        lines.append(f"| **Security Policy Violations** | `{m.total_security_violations}` | {'✅ Zero Violations' if m.total_security_violations == 0 else '🚨 Boundary Breach'} |")
        lines.append("")

        # Efficiency & Trajectories
        lines.append("## 3. Trajectory & Research Efficiency")
        lines.append("")
        lines.append("| Dimension | Value | Notes |")
        lines.append("| :--- | :---: | :--- |")
        lines.append(f"| **Avg Pages Crawled / Task** | `{m.avg_pages_per_task:.1f}` | Laya System 1 candidate pruning |")
        lines.append(f"| **Avg Searches / Task** | `{m.avg_searches_per_task:.1f}` | SearchPipeline query executions |")
        lines.append(f"| **Avg LLM Calls / Task** | `{m.avg_llm_calls_per_task:.1f}` | Worker + Verifier + Brain |")
        lines.append(f"| **Avg Tokens / Task** | `{m.avg_tokens_per_task:,.0f}` | Bounded context consumption |")
        lines.append(f"| **Avg Runtime / Task** | `{m.avg_runtime_sec:.2f} sec` | End-to-end execution latency |")
        lines.append(f"| **Estimated Cost / Task** | `${m.total_cost_usd / max(1, m.total_tasks):.4f}` | Token cost projection |")
        lines.append(f"| **Premature Stop Rate** | `{m.premature_stop_rate * 100:.1f}%` | Halted before field satisfaction |")
        lines.append(f"| **Wasteful Continuation Rate** | `{m.wasteful_continuation_rate * 100:.1f}%` | Continued after satisfaction |")
        lines.append("")

        # Category Summaries
        lines.append("## 4. Performance by Category")
        lines.append("")
        lines.append("| Category | Tasks | Passed | Pass Rate | Entity F1 | Field Acc | Evidence Corr | Unsupp Rate |")
        lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
        for cat_name, cat_m in sorted(m.category_summaries.items()):
            lines.append(
                f"| `{cat_name}` | {cat_m.task_count} | {cat_m.passed_count} | "
                f"`{cat_m.pass_rate * 100:.1f}%` | `{cat_m.avg_entity_f1 * 100:.1f}%` | "
                f"`{cat_m.avg_field_accuracy * 100:.1f}%` | `{cat_m.avg_evidence_correctness * 100:.1f}%` | "
                f"`{cat_m.avg_unsupported_claim_rate * 100:.1f}%` |"
            )
        lines.append("")

        # Failure Taxonomy Breakdown
        lines.append("## 5. Root-Cause Failure Taxonomy")
        lines.append("")
        if not m.failure_taxonomy_counts:
            lines.append("✅ **Zero failures classified across all evaluated tasks.**")
        else:
            lines.append("| Failure Classification | Occurrences | Category Description |")
            lines.append("| :--- | :---: | :--- |")
            for f_name, cnt in sorted(m.failure_taxonomy_counts.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"| `{f_name}` | **{cnt}** | Diagnostic failure classification |")
        lines.append("")

        # Per-Task Results
        lines.append("## 6. Per-Task Execution Audit")
        lines.append("")
        lines.append("| Task ID | Category | Status | Entity F1 | Field Acc | Evidence | Violations | Failures |")
        lines.append("| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |")
        for t in result.task_results:
            st = "✅ PASS" if t.passed else "❌ FAIL"
            f_str = ", ".join(f.value if hasattr(f, "value") else str(f) for f in t.failures) or "None"
            lines.append(
                f"| `{t.task_id}` | `{t.category.value if hasattr(t.category, 'value') else str(t.category)}` | "
                f"{st} | `{t.entity_f1 * 100:.0f}%` | `{t.field_accuracy * 100:.0f}%` | "
                f"`{t.evidence_correctness * 100:.0f}%` | `{t.security_violation_count}` | `{f_str}` |"
            )
        lines.append("")

        return "\n".join(lines)

    @classmethod
    def generate_regression_markdown(cls, diff: RegressionDiff) -> str:
        """Format a regression diff between baseline and current run."""
        lines: list[str] = []
        lines.append(f"# ARGUS REGRESSION REPORT")
        lines.append(f"")
        lines.append(f"> **Baseline Run**: `{diff.baseline_run_id}` (Commit: `{diff.baseline_commit}`)  ")
        lines.append(f"> **Current Run**: `{diff.current_run_id}` (Commit: `{diff.current_commit}`)  ")
        lines.append(f"> **Verdict**: **`{diff.summary_verdict}`**  ")
        lines.append(f"")

        lines.append("## 1. Summary of Changes")
        lines.append("")
        lines.append(f"- **Improvements**: {len(diff.improvements)}")
        lines.append(f"- **Regressions**: {len(diff.regressions)}")
        lines.append(f"- **Unchanged Metrics**: {len(diff.unchanged)}")
        lines.append(f"- **Cost Delta**: `{diff.cost_delta_pct:+.2f}%`")
        lines.append(f"- **Latency Delta**: `{diff.latency_delta_pct:+.2f}%`")
        lines.append("")

        if diff.improvements:
            lines.append("### 🟢 Improvements")
            for imp in diff.improvements:
                lines.append(f"- {imp}")
            lines.append("")

        if diff.regressions:
            lines.append("### 🔴 Regressions")
            for reg in diff.regressions:
                lines.append(f"- {reg}")
            lines.append("")

        if diff.new_failures:
            lines.append("### ⚠️ New Failures Introduced")
            for tid, fails in diff.new_failures.items():
                lines.append(f"- `{tid}`: {', '.join(fails)}")
            lines.append("")

        if diff.resolved_failures:
            lines.append("### ✅ Resolved Failures")
            for tid, fails in diff.resolved_failures.items():
                lines.append(f"- `{tid}`: {', '.join(fails)}")
            lines.append("")

        return "\n".join(lines)
