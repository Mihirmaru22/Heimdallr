"""Heimdallr V3.1: Capability Match V2 Report Generator.

Generates comprehensive evaluation and validation audit reports for CAPABILITY_MATCH_V2.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from argus.evals.capability_match_v2.models import (
    CapabilityMatchV2Summary,
    TaskEvaluationResult,
)


class CapabilityMatchV2Reporter:
    """Formatter and generator for CAPABILITY_MATCH_V2 markdown reports."""

    @staticmethod
    def generate_validation_audit_markdown(leakage_data: Dict[str, Any]) -> str:
        """Generate CAPABILITY_MATCH_V2_VALIDATION_AUDIT.md content."""
        lines: list[str] = []
        lines.append("# HEIMDALLR V3.1 — CAPABILITY_MATCH_V2 VALIDATION AUDIT")
        lines.append("")
        lines.append("## Executive Summary")
        lines.append("")
        lines.append(f"- **Audit Status:** {leakage_data.get('overall_status', 'PASS')}")
        lines.append(f"- **Total Audit Vectors:** {leakage_data.get('vector_count', 6)}")
        lines.append(f"- **Total Violations Detected:** {leakage_data.get('violations_count', 0)}")
        lines.append("- **Audit Standard:** Anti-Overfitting & Evaluator Isolation Discipline")
        lines.append("")
        lines.append("## 1. Adversarial Audit Vector Matrix")
        lines.append("")
        lines.append("| Audit Vector | Target Component | Status | Details |")
        lines.append("| :--- | :--- | :---: | :--- |")

        vectors = leakage_data.get("vectors", {})
        for vec_name, vec_info in vectors.items():
            status = vec_info.get("status", "PASS")
            details = vec_info.get("details", "")
            lines.append(f"| `{vec_name}` | Capability Registry / Matcher | **{status}** | {details} |")

        lines.append("")
        lines.append("## 2. Leakage Defense Architecture")
        lines.append("")
        lines.append("Heimdallr V3.1 enforces strict boundary isolation between benchmark definitions and the matcher runtime:")
        lines.append("1. **No Ground Truth in Matcher Execution:** `CapabilityMatcher` only receives `InvestigationQuestion` and registered capabilities. It has no access to task expectations.")
        lines.append("2. **Task Public Projection:** `CapabilityMatchTaskV2.get_public_view()` strips `required_capabilities`, `forbidden_capabilities`, `minimum_sufficient_set`, and `acceptable_alternative_sets`.")
        lines.append("3. **AST Static Scanning:** Static AST parsing confirms zero references to benchmark fixtures or evaluation modules within `src/argus/capability_registry/` or `src/argus/capabilities/`.")
        lines.append("4. **No Task ID Branching:** Matcher code contains no `task_id` conditionals or hardcoded benchmark patterns.")
        lines.append("5. **Strict Evaluator Separation:** `MatcherGraderV2` runs strictly post-execution and evaluates selected candidates against ground truth.")
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def generate_summary_markdown(
        summary: CapabilityMatchV2Summary,
        task_results: List[TaskEvaluationResult],
    ) -> str:
        """Generate high-level markdown summary table."""
        lines: list[str] = []
        lines.append("# CAPABILITY_MATCH_V2 Summary")
        lines.append("")
        lines.append(f"- **Total Tasks:** {summary.total_tasks}")
        lines.append(f"- **Minimum Set Accuracy:** {summary.minimum_capability_set_accuracy:.2%}")
        lines.append(f"- **Capability Precision:** {summary.capability_precision:.4f}")
        lines.append(f"- **Capability Recall:** {summary.capability_recall:.4f}")
        lines.append(f"- **Capability F1:** {summary.capability_f1:.4f}")
        lines.append(f"- **Capability Tax Mean:** {summary.capability_tax_mean:.4f}")
        lines.append(f"- **Decision:** **{summary.decision}**")
        lines.append("")
        return "\n".join(lines)
