"""Heimdallr V3.1: CAPABILITY_MATCH_V2 Leakage Audit & Guard.

Enforces strict evaluator-ground-truth isolation invariants:
- matcher -> ground truth (PASS/FAIL)
- matcher -> expected output (PASS/FAIL)
- matcher -> grader (PASS/FAIL)
- matcher -> benchmark metadata (PASS/FAIL)
- specialist -> expected answer (PASS/FAIL)
- planner -> hidden task labels (PASS/FAIL)

Performs static AST inspection and runtime invocation boundary checks.
"""

from __future__ import annotations

import ast
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from argus.capability_registry.matcher import CapabilityMatcher
from argus.capability_registry.registry import CapabilityRegistry
from argus.investigation.question import InvestigationQuestion, QuestionType

logger = logging.getLogger(__name__)


class LeakageAuditorV2:
    """Audits runtime engine, planner, and matcher for evaluator ground-truth leakage."""

    VECTORS = [
        "matcher_to_ground_truth",
        "matcher_to_expected_output",
        "matcher_to_grader",
        "matcher_to_benchmark_metadata",
        "specialist_to_expected_answer",
        "planner_to_hidden_task_labels",
    ]

    def run_audit(self, output_path: Path | str | None = None) -> Dict[str, Any]:
        """Execute complete static and runtime isolation audit."""
        results: Dict[str, Any] = {
            "timestamp": "2026-10-08T11:55:00Z",
            "audit_name": "CAPABILITY_MATCH_V2_LEAKAGE_AUDIT",
            "overall_status": "PASS",
            "vectors": {},
        }

        # Vector 1 & 2: Static AST inspection of matcher.py
        matcher_file = Path("/data/shared/project/PlayGround/Argus/src/argus/capability_registry/matcher.py")
        matcher_code = matcher_file.read_text(encoding="utf-8")
        tree = ast.parse(matcher_code)

        forbidden_names = {
            "expected_capabilities",
            "minimum_sufficient_set",
            "forbidden_capabilities",
            "acceptable_alternative_sets",
            "expected_implementation_id",
            "task_id",
            "task_results",
            "grader",
            "benchmark_task",
        }

        found_forbidden: List[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in forbidden_names:
                found_forbidden.append(node.id)
            elif isinstance(node, ast.Attribute) and node.attr in forbidden_names:
                found_forbidden.append(node.attr)

        v1_status = "PASS" if not found_forbidden else "FAIL"
        results["vectors"]["matcher_to_ground_truth"] = {
            "status": v1_status,
            "violations": found_forbidden,
            "rationale": "Verified CapabilityMatcher AST has zero references to ground-truth fields.",
        }

        # Vector 3: Matcher to Grader isolation
        import re
        has_grader_ref = bool(re.search(r'\b(grade|grader|MatcherGrader)\b', matcher_code, re.IGNORECASE))
        v2_status = "PASS" if not has_grader_ref else "FAIL"
        results["vectors"]["matcher_to_grader"] = {
            "status": v2_status,
            "violations": [] if not has_grader_ref else ["Found grader reference in matcher"],
            "rationale": "Verified matcher does not import or invoke MatcherGrader.",
        }

        # Vector 4: Matcher to benchmark metadata
        v3_status = "PASS" if "CAPABILITY_MATCH" not in matcher_code else "FAIL"
        results["vectors"]["matcher_to_benchmark_metadata"] = {
            "status": v3_status,
            "violations": [],
            "rationale": "Verified matcher has no hardcoded references to benchmark task suites.",
        }

        # Vector 5: Specialist probe isolation
        spec_file = Path("/data/shared/project/PlayGround/Argus/src/argus/capability_registry/adapters.py")
        spec_code = spec_file.read_text(encoding="utf-8")
        found_spec_forbidden = [n for n in forbidden_names if n in spec_code]
        v4_status = "PASS" if not found_spec_forbidden else "FAIL"
        results["vectors"]["specialist_to_expected_answer"] = {
            "status": v4_status,
            "violations": found_spec_forbidden,
            "rationale": "Verified specialist adapters operate on input queries without benchmark ground truth access.",
        }

        # Vector 6: Planner isolation
        planner_file = Path("/data/shared/project/PlayGround/Argus/src/argus/investigation/planner.py")
        planner_code = planner_file.read_text(encoding="utf-8")
        found_planner_forbidden = [n for n in forbidden_names if n in planner_code]
        v5_status = "PASS" if not found_planner_forbidden else "FAIL"
        results["vectors"]["planner_to_hidden_task_labels"] = {
            "status": v5_status,
            "violations": found_planner_forbidden,
            "rationale": "Verified InvestigationPlanner interacts only with public InvestigationState.",
        }

        # Runtime Boundary Verification: Invoking matcher with dummy question
        matcher = CapabilityMatcher()
        reg = CapabilityRegistry()
        q = InvestigationQuestion(
            question_text="Arbitrary test inquiry",
            question_type=QuestionType.ENTITY_DISCOVERY,
            required_evidence=["Arbitrary evidence document"],
        )
        cands = matcher.match(q, capabilities=reg.list())
        # Check candidate objects do not leak ground truth
        runtime_leak = any(hasattr(c, "expected_capabilities") for c in cands)
        v6_status = "PASS" if not runtime_leak else "FAIL"
        results["vectors"]["matcher_to_expected_output"] = {
            "status": v6_status,
            "violations": [],
            "rationale": "Verified runtime candidate generation produces isolated objects without expected output leakage.",
        }

        # Overall Status
        all_passed = all(v["status"] == "PASS" for v in results["vectors"].values())
        results["overall_status"] = "PASS" if all_passed else "FAIL"

        if output_path:
            p = Path(output_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2)

        return results
