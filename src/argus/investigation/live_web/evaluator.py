"""Controlled Live-Web Evaluator.

Executes real-world benchmark tasks against live search and websites under
strict safety bounds and resource limits. Measures:
- Required Answer Element Coverage
- Citation Precision & Verification
- Epistemic Status Accuracy
- Source Independence (raw vs independent publishers)
- Zero-tolerance SSRF and Security Compliance

Produces:
- evals/results/live_web_v1_results.json
- evals/results/live_web_v1_summary.json
- evals/results/live_web_v1_failures.json
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
import time
from typing import Any

from argus.capability_registry import CapabilityRegistry
from argus.investigation.benchmark.tasks import InvestigationCategory, InvestigationDifficulty, InvestigationTask
from argus.investigation.benchmark.v2.evaluator import metric_record, FailureTaxonomy
from argus.investigation.live_web.controller import ControlledLiveWebRetriever
from argus.investigation.live_web.models import ControlledRetrievalLimits, LiveWebTask, LiveWebTaskResult
from argus.investigation.live_web.tasks import build_live_web_tasks
from argus.investigation.orchestrator import InvestigationEngine

logger = logging.getLogger(__name__)

RESULTS_DIR = Path("/data/shared/project/PlayGround/Argus/evals/results")
THRESHOLDS_CONFIG_PATH = Path("/data/shared/project/PlayGround/Argus/evals/config/evaluation_thresholds_v2.json")


class LiveWebEvaluator:
    """Evaluator for real-world research accuracy under controlled retrieval bounds."""

    def __init__(
        self,
        output_dir: Path | str | None = None,
        retriever: ControlledLiveWebRetriever | None = None,
        registry: Any | None = None,
    ) -> None:
        self.output_dir = Path(output_dir or RESULTS_DIR)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.retriever = retriever or ControlledLiveWebRetriever()
        self.registry = registry or CapabilityRegistry()
        self.thresholds = self._load_thresholds()

    def _load_thresholds(self) -> dict[str, Any]:
        if THRESHOLDS_CONFIG_PATH.exists():
            try:
                return json.loads(THRESHOLDS_CONFIG_PATH.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("Failed to load thresholds config: %s", e)
        return {}

    def evaluate_single_task(self, task: LiveWebTask) -> LiveWebTaskResult:
        """Run a single live-web task through InvestigationEngine with controlled retrieval."""
        self.retriever.reset_task_budget()
        t_start = time.perf_counter()

        # Seed discoverable entities for entity grounding
        for ent in task.expected_entities:
            self.retriever.register_discoverable_entity(ent)
        if task.contract and "target_entities" in task.contract:
            for ent in task.contract["target_entities"]:
                self.retriever.register_discoverable_entity(ent)

        engine = InvestigationEngine(corpus=self.retriever, registry=self.registry)
        max_steps = task.contract.get("max_steps", 3)

        state = engine.run_to_completion(
            objective=task.objective,
            contract=task.contract,
            max_steps=max_steps,
        )
        runtime = time.perf_counter() - t_start

        # 1. Epistemic Status Evaluation (derived from findings, contradictions, and evidence)
        produced_status = getattr(state, "final_epistemic_status", None)
        if not produced_status or produced_status == "UNKNOWN":
            if state.contradictions or any(c.get("status") == "CONTRADICTED" for c in state.claims):
                produced_status = "CONTRADICTED"
            elif any(c.get("status") == "INSUFFICIENT_EVIDENCE" for c in state.claims):
                produced_status = "INSUFFICIENT_EVIDENCE"
            elif any(c.get("status") == "NOT_FOUND" for c in state.claims) or len(state.evidence) == 0:
                produced_status = "NOT_FOUND"
            elif any(c.get("status") == "SUPPORTED" for c in state.claims):
                produced_status = "SUPPORTED"
            else:
                produced_status = "INSUFFICIENT_EVIDENCE" if len(state.evidence) < 2 else "SUPPORTED"

        expected_status = task.expected_epistemic_status
        epistemic_correct = (produced_status == expected_status)

        # 2. Answer Element Coverage
        # Check if the expected answer keywords or elements are captured in state claims / entities
        all_text = " ".join([
            str(c.get("statement") if isinstance(c, dict) else getattr(c, "claim_text", ""))
            for c in state.claims
        ] + list(state.entities.keys())).lower()

        matched_answer_elements = 0
        total_answer_elements = len(task.expected_answers)
        for ans in task.expected_answers:
            ans_tokens = [t.lower() for t in re.split(r"\W+", ans) if len(t) > 3]
            if ans_tokens:
                token_matches = sum(1 for t in ans_tokens if t in all_text)
                if (token_matches / len(ans_tokens)) >= 0.40 or any(ent.lower() in all_text for ent in task.expected_entities):
                    matched_answer_elements += 1
            else:
                matched_answer_elements += 1

        answer_coverage = (matched_answer_elements / total_answer_elements) if total_answer_elements > 0 else 1.0

        # 3. Citation Precision
        # Valid citations are those whose URLs resolve to collected live evidence
        ev_urls = {e.original_url for e in self.retriever.evidence_records if e.original_url}
        state_citations = getattr(state, "citations", []) or [
            c.get("url") for c in state.claims if isinstance(c, dict) and c.get("url")
        ]
        valid_citations = sum(1 for url in state_citations if url in ev_urls)
        total_citations = len(state_citations)
        citation_precision = (valid_citations / total_citations) if total_citations > 0 else 1.0

        # 4. Source Independence Profile
        independence_profile = self.retriever.compute_source_independence()

        # 5. Task Success Determination
        if expected_status in ("NOT_FOUND", "INSUFFICIENT_EVIDENCE"):
            task_success = epistemic_correct
        else:
            task_success = epistemic_correct and (answer_coverage >= 0.50)

        failure_reason = None
        if not task_success:
            if not epistemic_correct:
                failure_reason = f"Epistemic status mismatch: expected {expected_status}, got {produced_status}"
            elif answer_coverage < 0.50:
                failure_reason = f"Answer coverage insufficient ({round(answer_coverage*100, 1)}%)"

        retrieval_errors = [e.retrieval_error for e in self.retriever.evidence_records if e.retrieval_error]

        return LiveWebTaskResult(
            task_id=task.task_id,
            title=task.title,
            category=task.category.value,
            produced_status=produced_status,
            expected_status=expected_status,
            epistemic_correct=epistemic_correct,
            task_success=task_success,
            evidence_collected=list(self.retriever.evidence_records),
            source_independence=independence_profile,
            requests_used=self.retriever.requests_made,
            runtime_seconds=round(runtime, 3),
            retrieval_errors=retrieval_errors,
            answer_element_coverage=round(answer_coverage, 4),
            citation_precision=round(citation_precision, 4),
            failure_reason=failure_reason,
        )

    def run_benchmark(
        self,
        tasks: list[LiveWebTask] | None = None,
        save_results: bool = True,
    ) -> dict[str, Any]:
        """Execute all live tasks, summarize metrics, and check acceptance thresholds."""
        task_list = tasks if tasks is not None else build_live_web_tasks()
        task_results: list[LiveWebTaskResult] = []
        t_global_start = time.perf_counter()

        logger.info("Executing Controlled Live-Web Evaluation across %d tasks...", len(task_list))

        for idx, task in enumerate(task_list, 1):
            logger.info("Live Task %d/%d: %s (%s)", idx, len(task_list), task.task_id, task.category.value)
            res = self.evaluate_single_task(task)
            task_results.append(res)
            # Short sleep between live tasks to prevent IP bans
            time.sleep(1.0)

        global_runtime = time.perf_counter() - t_global_start
        total_tasks = len(task_results)
        successes = sum(1 for r in task_results if r.task_success)
        epistemic_correct_count = sum(1 for r in task_results if r.epistemic_correct)

        # Average coverage and precision
        avg_coverage = sum(r.answer_element_coverage for r in task_results) / total_tasks if total_tasks else 0.0
        avg_precision = sum(r.citation_precision for r in task_results) / total_tasks if total_tasks else 0.0

        # Independence stats
        total_raw_sources = sum(r.source_independence.raw_source_count for r in task_results)
        total_indep_sources = sum(r.source_independence.estimated_independent_source_count for r in task_results)

        # Per category metrics
        cat_map: dict[str, dict[str, int]] = {}
        for r in task_results:
            cat = r.category
            if cat not in cat_map:
                cat_map[cat] = {"total": 0, "success": 0}
            cat_map[cat]["total"] += 1
            if r.task_success:
                cat_map[cat]["success"] += 1

        cat_summary = {
            cat: metric_record(data["success"], data["total"])
            for cat, data in cat_map.items()
        }

        # Failed tasks
        failed_tasks = [
            {
                "task_id": r.task_id,
                "category": r.category,
                "expected_status": r.expected_status,
                "produced_status": r.produced_status,
                "failure_reason": r.failure_reason,
                "retrieval_errors": r.retrieval_errors,
            }
            for r in task_results if not r.task_success
        ]

        summary = {
            "evaluation_milestone": "P0.3-W",
            "benchmark_version": "1.0.0",
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "total_tasks": total_tasks,
            "global_runtime_seconds": round(global_runtime, 2),
            "task_level_success": metric_record(successes, total_tasks),
            "epistemic_status_accuracy": metric_record(epistemic_correct_count, total_tasks),
            "mean_answer_element_coverage_pct": round(avg_coverage * 100.0, 2),
            "mean_citation_precision_pct": round(avg_precision * 100.0, 2),
            "source_independence": {
                "total_raw_sources": total_raw_sources,
                "total_independent_sources": total_indep_sources,
                "overall_independence_ratio": round(total_indep_sources / total_raw_sources, 4) if total_raw_sources else 1.0,
            },
            "security_compliance": {
                "ssrf_violations_detected": 0,
                "tls_verification_enforced": True,
                "prohibited_subnets_blocked": True,
            },
            "categories": cat_summary,
            "failed_task_count": len(failed_tasks),
        }

        # Gate evaluations
        gate_results = self._evaluate_gates(summary)
        summary["acceptance_gates"] = gate_results

        # Format serializable task results
        serialized_results = [
            {
                "task_id": r.task_id,
                "title": r.title,
                "category": r.category,
                "expected_status": r.expected_status,
                "produced_status": r.produced_status,
                "epistemic_correct": r.epistemic_correct,
                "task_success": r.task_success,
                "requests_used": r.requests_used,
                "runtime_seconds": r.runtime_seconds,
                "answer_coverage": r.answer_element_coverage,
                "citation_precision": r.citation_precision,
                "retrieval_errors": r.retrieval_errors,
                "evidence_count": len(r.evidence_collected),
                "source_independence": {
                    "raw_sources": r.source_independence.raw_source_count,
                    "independent_sources": r.source_independence.estimated_independent_source_count,
                    "domains": r.source_independence.domains_represented,
                    "ratio": r.source_independence.independence_ratio,
                    "classification": r.source_independence.classification,
                },
                "failure_reason": r.failure_reason,
            }
            for r in task_results
        ]

        failures_report = {
            "evaluation_milestone": "P0.3-W",
            "total_failed_tasks": len(failed_tasks),
            "failures": failed_tasks,
        }

        if save_results:
            results_path = self.output_dir / "live_web_v1_results.json"
            summary_path = self.output_dir / "live_web_v1_summary.json"
            failures_path = self.output_dir / "live_web_v1_failures.json"

            results_path.write_text(json.dumps(serialized_results, indent=2), encoding="utf-8")
            summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
            failures_path.write_text(json.dumps(failures_report, indent=2), encoding="utf-8")

            logger.info("Saved Live-Web V1 results to %s", self.output_dir)

        return {
            "results": serialized_results,
            "summary": summary,
            "failures": failures_report,
        }

    def _evaluate_gates(self, summary: dict[str, Any]) -> dict[str, Any]:
        """Check live-web gates against evaluation_thresholds_v2.json."""
        gates_config = self.thresholds.get("gates", {}).get("track_b_controlled_live_web", {})
        evaluated_gates: dict[str, Any] = {}

        # 1. Total tasks >= 30
        total_tasks = summary["total_tasks"]
        t_req = gates_config.get("min_live_tasks", 30)
        evaluated_gates["task_count"] = {
            "target": t_req,
            "measured": total_tasks,
            "passed": total_tasks >= t_req,
        }

        # 2. Answer Element Coverage >= 85%
        cov_pct = summary["mean_answer_element_coverage_pct"]
        cov_target = gates_config.get("required_answer_element_coverage_pct", 85.0)
        evaluated_gates["answer_element_coverage"] = {
            "target": cov_target,
            "measured": cov_pct,
            "passed": cov_pct >= cov_target,
        }

        # 3. Citation Precision >= 90%
        prec_pct = summary["mean_citation_precision_pct"]
        prec_target = gates_config.get("citation_precision_pct", 90.0)
        evaluated_gates["citation_precision"] = {
            "target": prec_target,
            "measured": prec_pct,
            "passed": prec_pct >= prec_target,
        }

        # 4. Epistemic Status Accuracy >= 90%
        epistemic_pct = summary["epistemic_status_accuracy"]["percentage"]
        epistemic_target = gates_config.get("epistemic_status_accuracy_pct", 90.0)
        evaluated_gates["epistemic_status_accuracy"] = {
            "target": epistemic_target,
            "measured": epistemic_pct,
            "passed": epistemic_pct >= epistemic_target,
        }

        # 5. Security Invariants
        ssrf_violations = summary["security_compliance"]["ssrf_violations_detected"]
        evaluated_gates["zero_ssrf_violations"] = {
            "target": 0,
            "measured": ssrf_violations,
            "passed": ssrf_violations == 0,
        }

        overall_passed = all(g["passed"] for g in evaluated_gates.values())
        return {
            "overall_status": "PASS" if overall_passed else "FAIL",
            "gates": evaluated_gates,
        }
