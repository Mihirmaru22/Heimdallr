"""Heimdallr V3.1: Capability-Label Leakage Guard and Detector.

Provides static AST analysis and runtime interception to detect any
evaluator-only capability information reaching the runtime CapabilityMatcher,
CapabilityRegistry, InvestigationPlanner, or action execution layers.
"""

from __future__ import annotations

import ast
import functools
import inspect
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class LeakageDetectedException(RuntimeError):
    """Raised when evaluator-only ground truth or benchmark metadata reaches runtime."""
    pass


# Forbidden evaluator attribute names that must NEVER be accessed by runtime components
FORBIDDEN_EVALUATOR_ATTRIBUTES: Set[str] = {
    "required_capabilities",
    "forbidden_capabilities",
    "minimum_sufficient_set",
    "acceptable_alternative_sets",
    "expected_implementation_id",
    "expected_entities",
    "expected_relationships",
    "grader",
    "grader_labels",
    "benchmark_answers",
    "hidden_task_labels",
    "simulate_health_states",
}


class CapabilityLabelLeakageGuard:
    """Static and runtime guard against evaluator label leakage."""

    @staticmethod
    def audit_object_for_leakage(obj: Any, context: str = "") -> List[str]:
        """Inspect an object or dictionary for forbidden evaluator ground truth fields.
        
        Returns a list of violation messages if leakage is detected.
        """
        violations: List[str] = []
        if obj is None:
            return violations

        # Check dictionary keys
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in FORBIDDEN_EVALUATOR_ATTRIBUTES and v not in (None, [], {}):
                    violations.append(
                        f"LEAKAGE_DETECTED in {context}: dictionary contains populated evaluator key '{k}'"
                    )
                violations.extend(CapabilityLabelLeakageGuard.audit_object_for_leakage(v, f"{context}.{k}"))

        # Check object attributes
        elif hasattr(obj, "__dict__"):
            for attr in FORBIDDEN_EVALUATOR_ATTRIBUTES:
                if hasattr(obj, attr):
                    val = getattr(obj, attr)
                    if val not in (None, [], {}):
                        violations.append(
                            f"LEAKAGE_DETECTED in {context}: object '{type(obj).__name__}' has populated evaluator attribute '{attr}'"
                        )
        return violations

    @staticmethod
    def check_question_isolation(question: Any) -> None:
        """Enforce strict runtime isolation on an InvestigationQuestion before matcher execution."""
        violations = CapabilityLabelLeakageGuard.audit_object_for_leakage(question, "InvestigationQuestion")
        if violations:
            msg = "; ".join(violations)
            logger.error("CapabilityLabelLeakageGuard violation: %s", msg)
            raise LeakageDetectedException(msg)

    @classmethod
    def guarded_matcher_call(cls, func: Callable[..., Any]) -> Callable[..., Any]:
        """Decorator for matcher methods to verify runtime input isolation."""
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Check question argument if present
            question = kwargs.get("question")
            if question is None and len(args) > 1:
                question = args[1]
            if question is not None:
                cls.check_question_isolation(question)
            return func(*args, **kwargs)
        return wrapper

    @staticmethod
    def run_ast_leakage_audit(
        source_paths: Optional[List[Path | str]] = None,
    ) -> Dict[str, Any]:
        """Perform static AST inspection of runtime capability code.
        
        Verifies that production runtime modules do not import or reference
        benchmark task fixtures, graders, or evaluator ground-truth attributes.
        """
        if source_paths is None:
            source_paths = [
                Path("/data/shared/project/PlayGround/Argus/src/argus/capability_registry/matcher.py"),
                Path("/data/shared/project/PlayGround/Argus/src/argus/capability_registry/registry.py"),
                Path("/data/shared/project/PlayGround/Argus/src/argus/capability_registry/models.py"),
                Path("/data/shared/project/PlayGround/Argus/src/argus/investigation/orchestrator.py"),
                Path("/data/shared/project/PlayGround/Argus/src/argus/investigation/planner.py"),
            ]

        results: Dict[str, Any] = {
            "overall_status": "PASS",
            "files_audited": len(source_paths),
            "violations": [],
        }

        for path in source_paths:
            p = Path(path)
            if not p.exists():
                continue
            with open(p, "r", encoding="utf-8") as f:
                content = f.read()

            try:
                tree = ast.parse(content, filename=str(p))
            except Exception as e:
                results["violations"].append(f"Failed to parse AST for {p.name}: {e}")
                results["overall_status"] = "FAIL"
                continue

            for node in ast.walk(tree):
                # Check for direct imports of benchmark tasks or fixtures
                if isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    if "fixtures.tasks" in mod or "matcher_grader" in mod:
                        results["violations"].append(
                            f"LEAKAGE_DETECTED in {p.name}: imports benchmark module '{mod}' at line {node.lineno}"
                        )
                        results["overall_status"] = "FAIL"

                # Check for attribute accesses matching forbidden ground-truth names
                elif isinstance(node, ast.Attribute):
                    if node.attr in FORBIDDEN_EVALUATOR_ATTRIBUTES:
                        # Allow models.py or definition files if they define schema, but not in matcher.py
                        if p.name in ("matcher.py", "orchestrator.py"):
                            results["violations"].append(
                                f"LEAKAGE_DETECTED in {p.name}: accesses evaluator attribute '{node.attr}' at line {node.lineno}"
                            )
                            results["overall_status"] = "FAIL"

        return results
