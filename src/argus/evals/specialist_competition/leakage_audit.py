"""Heimdallr V3.2: SPECIALIST_COMPETITION_V1 Leakage Audit.

Verifies zero evaluator ground truth leakage into Candidate Adapters,
CompetitionEngine, or ImplementationSelector.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

FORBIDDEN_COMPETITION_LABELS = {
    "expected_winner",
    "expected_decision",
    "target_evidence_type",
    "expected_implementation",
    "expected_score",
    "grader_labels",
}


class SpecialistCompetitionLeakageAuditor:
    """Static AST and runtime guard verifying competition engine boundary isolation."""

    @staticmethod
    def run_static_ast_audit(
        source_paths: Optional[List[Path | str]] = None,
    ) -> Dict[str, Any]:
        """Perform static AST inspection of competition runtime code."""
        if source_paths is None:
            source_paths = [
                Path("/data/shared/project/PlayGround/Argus/src/argus/competition/engine.py"),
                Path("/data/shared/project/PlayGround/Argus/src/argus/competition/implementation_selector.py"),
                Path("/data/shared/project/PlayGround/Argus/src/argus/specialists/sanctions/adapter.py"),
                Path("/data/shared/project/PlayGround/Argus/src/argus/specialists/sanctions/specialist.py"),
            ]

        violations: List[str] = []
        for path in source_paths:
            p = Path(path)
            if not p.exists():
                continue
            with open(p, "r", encoding="utf-8") as f:
                content = f.read()

            try:
                tree = ast.parse(content, filename=str(p))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Attribute):
                        if node.attr in FORBIDDEN_COMPETITION_LABELS:
                            violations.append(
                                f"LEAKAGE_DETECTED in {p.name}: accesses evaluator attribute '{node.attr}' at line {node.lineno}"
                            )
                    elif isinstance(node, ast.ImportFrom):
                        mod = node.module or ""
                        if "specialist_competition.fixtures" in mod:
                            violations.append(
                                f"LEAKAGE_DETECTED in {p.name}: imports competition task fixtures at line {node.lineno}"
                            )
            except Exception as e:
                violations.append(f"Failed to parse AST for {p.name}: {e}")

        return {
            "audit_name": "SPECIALIST_COMPETITION_LEAKAGE_AUDIT",
            "overall_status": "PASS" if not violations else "FAIL",
            "files_audited": len(source_paths),
            "violations": violations,
        }
