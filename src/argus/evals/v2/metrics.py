"""Heimdallr Eval V2: Aggregation Metrics & Statistical Analysis."""

from __future__ import annotations

from typing import Any
from argus.evals.v2.models import (
    BenchmarkCategory,
    DifficultyTier,
    EvalV2TaskResult,
    FailureSeverity,
)


def aggregate_v2_metrics(results: list[EvalV2TaskResult]) -> dict[str, Any]:
    n = len(results)
    if n == 0:
        return {}

    passed_count = sum(1 for r in results if r.passed)
    pass_rate = passed_count / n

    # Research Quality
    avg_ent_prec = sum(r.entity_precision for r in results) / n
    avg_ent_rec = sum(r.entity_recall for r in results) / n
    avg_ent_f1 = sum(r.entity_f1 for r in results) / n
    avg_rel_prec = sum(r.relationship_precision for r in results) / n
    avg_rel_rec = sum(r.relationship_recall for r in results) / n
    avg_rel_f1 = sum(r.relationship_f1 for r in results) / n
    avg_field_acc = sum(r.field_accuracy for r in results) / n

    # Multi-hop Chains
    avg_chain_comp = sum(r.chain_completion_rate for r in results) / n
    tot_broken_chains = sum(1 for r in results if r.broken_chain_detected)

    # Evidence & Independence
    avg_ev_cov = sum(r.evidence_coverage for r in results) / n
    avg_ev_corr = sum(r.evidence_correctness for r in results) / n
    avg_ev_comp = sum(r.evidence_completeness for r in results) / n
    avg_ev_indep = sum(r.evidence_independence_score for r in results) / n

    # Epistemics
    avg_ep_acc = sum(r.epistemic_accuracy for r in results) / n
    tot_contra_ok = sum(1 for r in results if r.contradiction_resolved_correctly)

    # Temporal
    avg_temp_acc = sum(r.temporal_accuracy for r in results) / n

    # Entity Safety & Severity
    tot_fp_merges = sum(r.false_positive_merges for r in results)
    tot_fn_misses = sum(r.false_negative_misses for r in results)
    tot_critical_failures = sum(1 for r in results if r.severity == FailureSeverity.CRITICAL)
    tot_major_failures = sum(1 for r in results if r.severity == FailureSeverity.MAJOR)
    tot_minor_failures = sum(1 for r in results if r.severity == FailureSeverity.MINOR)

    # Stopping Behavior
    tot_stopping_correct = sum(1 for r in results if r.stopping_correct)
    tot_premature_stops = sum(1 for r in results if r.premature_stopping)

    # Security
    tot_security_violations = sum(1 for r in results if r.security_violation_detected)

    # Efficiency
    avg_runtime = sum(r.runtime_sec for r in results) / n
    tot_searches = sum(r.searches_count for r in results)
    tot_pages = sum(r.pages_extracted for r in results)
    tot_llm = sum(r.llm_calls_count for r in results)
    tot_tokens = sum(r.tokens_count for r in results)
    tot_cost = sum(r.cost_usd for r in results)
    cost_per_pass = tot_cost / passed_count if passed_count > 0 else 0.0

    # Failure counts
    fail_counts: dict[str, int] = {}
    for r in results:
        if r.failure_mode:
            fail_counts[r.failure_mode] = fail_counts.get(r.failure_mode, 0) + 1

    # Breakdown by Difficulty Tier
    tier_breakdown: dict[str, Any] = {}
    for tier in DifficultyTier:
        sub = [r for r in results if r.difficulty_tier == tier]
        if sub:
            tier_breakdown[tier.value] = {
                "count": len(sub),
                "passed": sum(1 for r in sub if r.passed),
                "pass_rate": sum(1 for r in sub if r.passed) / len(sub),
                "entity_f1": sum(r.entity_f1 for r in sub) / len(sub),
            }

    # Breakdown by Category
    cat_breakdown: dict[str, Any] = {}
    for cat in BenchmarkCategory:
        sub = [r for r in results if r.category == cat]
        if sub:
            cat_breakdown[cat.value] = {
                "count": len(sub),
                "passed": sum(1 for r in sub if r.passed),
                "pass_rate": sum(1 for r in sub if r.passed) / len(sub),
            }

    return {
        "task_count": n,
        "passed_count": passed_count,
        "pass_rate": pass_rate,
        "entity_precision": avg_ent_prec,
        "entity_recall": avg_ent_rec,
        "entity_f1": avg_ent_f1,
        "relationship_precision": avg_rel_prec,
        "relationship_recall": avg_rel_rec,
        "relationship_f1": avg_rel_f1,
        "field_accuracy": avg_field_acc,
        "chain_completion_rate": avg_chain_comp,
        "total_broken_chains": tot_broken_chains,
        "evidence_coverage": avg_ev_cov,
        "evidence_correctness": avg_ev_corr,
        "evidence_completeness": avg_ev_comp,
        "evidence_independence_score": avg_ev_indep,
        "epistemic_accuracy": avg_ep_acc,
        "contradiction_resolution_accuracy": tot_contra_ok / n,
        "temporal_accuracy": avg_temp_acc,
        "total_false_positive_merges": tot_fp_merges,
        "total_false_negative_misses": tot_fn_misses,
        "critical_failure_count": tot_critical_failures,
        "major_failure_count": tot_major_failures,
        "minor_failure_count": tot_minor_failures,
        "critical_failure_rate": tot_critical_failures / n,
        "major_failure_rate": tot_major_failures / n,
        "stopping_accuracy": tot_stopping_correct / n,
        "premature_stopping_rate": tot_premature_stops / n,
        "total_security_violations": tot_security_violations,
        "security_violation_rate": tot_security_violations / n,
        "avg_runtime_sec": avg_runtime,
        "total_searches": tot_searches,
        "total_pages": tot_pages,
        "total_llm_calls": tot_llm,
        "total_tokens": tot_tokens,
        "total_cost_usd": tot_cost,
        "cost_per_successful_task": cost_per_pass,
        "failure_mode_counts": fail_counts,
        "difficulty_tier_breakdown": tier_breakdown,
        "category_breakdown": cat_breakdown,
    }
