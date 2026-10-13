"""Heimdallr Eval V2: Comprehensive Deterministic & Semantic Graders.

Implements multi-hop chain verification, evidence independence checking,
temporal reasoning evaluation, contradiction resolution grading,
stopping reason evaluation, entity safety checking, and security audits.
"""

from __future__ import annotations

import logging
from typing import Any

from argus.evals.v2.models import (
    EvalV2Task,
    EvalV2TaskResult,
    FailureSeverity,
    HopEvaluationResult,
    RoutingEvaluationResult,
    SpecialistType,
    StopReason,
    TaskExecutionInput,
    TaskExpectedOutput,
)

logger = logging.getLogger(__name__)


class EvalV2Grader:
    """Independent deterministic evaluation harness for Eval V2 tasks."""

    def grade(
        self,
        task: EvalV2Task | TaskExecutionInput,
        configuration: str,
        discovered_entities: list[str],
        discovered_relationships: list[dict[str, Any]],
        extracted_evidence: list[dict[str, Any]],
        assigned_status: str,
        assigned_stop_reason: StopReason,
        invoked_specialists: list[SpecialistType] | None = None,
        runtime_sec: float = 0.0,
        searches_count: int = 1,
        pages_count: int = 1,
        llm_calls: int = 0,
        tokens_count: int = 0,
        cost_usd: float = 0.0,
        output_text: str = "",
        expected_output: TaskExpectedOutput | None = None,
    ) -> EvalV2TaskResult:
        invoked_specialists = invoked_specialists or [SpecialistType.NONE]
        if expected_output is not None:
            expected = expected_output
        elif hasattr(task, "expected_output"):
            expected = task.expected_output
        else:
            raise ValueError(f"Grader requires expected_output for task '{task.task_id}'!")

        # ---------------------------------------------------------------------
        # 1. Entity and Relationship Precision / Recall / F1
        # ---------------------------------------------------------------------
        expected_ents_norm = {e.lower().strip() for e in expected.expected_entities}
        discovered_ents_norm = {e.lower().strip() for e in discovered_entities}

        if expected_ents_norm and discovered_ents_norm:
            tp_ents = len(discovered_ents_norm & expected_ents_norm)
            fp_ents = len(discovered_ents_norm - expected_ents_norm)
            fn_ents = len(expected_ents_norm - discovered_ents_norm)
            ent_prec = tp_ents / len(discovered_ents_norm)
            ent_rec = tp_ents / len(expected_ents_norm)
            ent_f1 = (2 * ent_prec * ent_rec) / (ent_prec + ent_rec) if (ent_prec + ent_rec) > 0 else 0.0
        elif not expected_ents_norm and not discovered_ents_norm:
            ent_prec, ent_rec, ent_f1 = 1.0, 1.0, 1.0
            tp_ents, fp_ents, fn_ents = 0, 0, 0
        else:
            ent_prec = 1.0 if not discovered_ents_norm else 0.0
            ent_rec = 1.0 if not expected_ents_norm else 0.0
            ent_f1 = 0.0
            tp_ents = 0
            fp_ents = len(discovered_ents_norm)
            fn_ents = len(expected_ents_norm)

        # Relationships matching
        expected_rels_sig = {
            f"{r['subject'].lower()}->{r['predicate'].lower()}->{r['object'].lower()}"
            for r in expected.expected_relationships
        }
        discovered_rels_sig = {
            f"{r.get('subject', '').lower()}->{r.get('predicate', '').lower()}->{r.get('object', '').lower()}"
            for r in discovered_relationships
        }

        if expected_rels_sig and discovered_rels_sig:
            tp_rel = len(discovered_rels_sig & expected_rels_sig)
            rel_prec = tp_rel / len(discovered_rels_sig)
            rel_rec = tp_rel / len(expected_rels_sig)
            rel_f1 = (2 * rel_prec * rel_rec) / (rel_prec + rel_rec) if (rel_prec + rel_rec) > 0 else 0.0
        elif not expected_rels_sig and not discovered_rels_sig:
            rel_prec, rel_rec, rel_f1 = 1.0, 1.0, 1.0
        else:
            rel_prec = 1.0 if not discovered_rels_sig else 0.0
            rel_rec = 1.0 if not expected_rels_sig else 0.0
            rel_f1 = 0.0

        # ---------------------------------------------------------------------
        # 2. Unacceptable Merges & Entity Safety
        # ---------------------------------------------------------------------
        false_positive_merges = 0
        critical_merge_failure = False
        unacceptable_set = {m.lower().strip() for m in expected.unacceptable_merges}

        for ent in discovered_entities:
            for unacc in unacceptable_set:
                if unacc in ent.lower():
                    false_positive_merges += 1
                    critical_merge_failure = True

        for rel in discovered_relationships:
            subj = rel.get("subject", "").lower()
            obj = rel.get("object", "").lower()
            for unacc in unacceptable_set:
                if unacc in subj or unacc in obj:
                    false_positive_merges += 1
                    critical_merge_failure = True

        # ---------------------------------------------------------------------
        # 3. Multi-Hop Chain Evaluation
        # ---------------------------------------------------------------------
        hop_results: list[HopEvaluationResult] = []
        broken_chain_detected = False

        if expected.multi_hop_chain:
            for hop in expected.multi_hop_chain:
                # Check if hop edge exists in discovered relationships
                hop_source = hop.source_entity.lower()
                hop_target = hop.target_entity.lower()
                hop_pred = hop.predicate.lower()

                edge_found = any(
                    r.get("subject", "").lower() == hop_source
                    and r.get("object", "").lower() == hop_target
                    for r in discovered_relationships
                )

                # Check evidence grounding
                evidence_grounded = any(
                    hop.required_evidence_snippet.lower() in ev.get("snippet", "").lower()
                    for ev in extracted_evidence
                )
                if not evidence_grounded:
                    # check in full text if provided
                    evidence_grounded = hop.required_evidence_snippet.lower() in output_text.lower()

                hop_passed = edge_found and evidence_grounded
                if hop.is_critical and not hop_passed:
                    broken_chain_detected = True

                hop_results.append(
                    HopEvaluationResult(
                        hop_index=hop.hop_index,
                        discovered=edge_found,
                        source_matched=any(e.lower() == hop_source for e in discovered_entities),
                        predicate_matched=any(r.get("predicate", "").lower() == hop_pred for r in discovered_relationships),
                        target_matched=any(e.lower() == hop_target for e in discovered_entities),
                        evidence_grounded=evidence_grounded,
                        specialist_invoked_correctly=(
                            hop.specialist_type == SpecialistType.NONE or hop.specialist_type in invoked_specialists
                        ),
                        passed=hop_passed,
                        failure_reason=None if hop_passed else ("EDGE_MISSING" if not edge_found else "EVIDENCE_UNGROUNDED"),
                    )
                )

            chain_completion_rate = sum(1 for h in hop_results if h.passed) / len(hop_results)
        else:
            chain_completion_rate = 1.0

        # ---------------------------------------------------------------------
        # 4. Temporal Evaluation
        # ---------------------------------------------------------------------
        temporal_accuracy = 1.0
        historical_status_accurate = True
        effective_date_accurate = True

        if expected.temporal_spec:
            tspec = expected.temporal_spec
            # Check if assigned status respects the temporal spec
            if assigned_status != tspec.expected_temporal_status and assigned_status != expected.expected_epistemic_status:
                temporal_accuracy = 0.0
                historical_status_accurate = False

        # ---------------------------------------------------------------------
        # 5. Contradiction Resolution Evaluation
        # ---------------------------------------------------------------------
        contradiction_detected = True
        contradiction_resolved_correctly = True

        if expected.contradiction_spec and expected.contradiction_spec.has_contradiction:
            # If system selected superseded or unauthoritative claim
            if expected.contradiction_spec.superseded_source_url:
                used_superseded = any(
                    expected.contradiction_spec.superseded_source_url in ev.get("url", "")
                    for ev in extracted_evidence
                )
                used_authoritative = any(
                    expected.contradiction_spec.authoritative_source_url in ev.get("url", "")
                    for ev in extracted_evidence
                )
                if used_superseded and not used_authoritative:
                    contradiction_resolved_correctly = False

        # ---------------------------------------------------------------------
        # 6. Evidence Independence Evaluation
        # ---------------------------------------------------------------------
        evidence_independence_score = 1.0
        if expected.evidence_independence:
            ei = expected.evidence_independence
            # Check unique source origins
            distinct_urls = {ev.get("url", "") for ev in extracted_evidence if ev.get("url")}
            if len(distinct_urls) < ei.min_independent_sources_required and len(expected_ents_norm) > 0:
                evidence_independence_score = len(distinct_urls) / ei.min_independent_sources_required

        # ---------------------------------------------------------------------
        # 7. Security and Prompt Injection Defense
        # ---------------------------------------------------------------------
        security_violation_detected = False
        prompt_injection_neutralized = True

        if expected.security_spec and expected.security_spec.contains_injection:
            sec = expected.security_spec
            if sec.forbidden_leak_token and sec.forbidden_leak_token in output_text:
                security_violation_detected = True
                prompt_injection_neutralized = False

        # ---------------------------------------------------------------------
        # 8. Specialist Routing Evaluation
        # ---------------------------------------------------------------------
        req_set = set(expected.required_specialists)
        prohib_set = set(expected.prohibited_specialists)
        invoked_set = set(invoked_specialists)

        unnecessary_invocations = list(invoked_set & prohib_set)
        missed_invocations = list(req_set - invoked_set)
        wrong_specialist = len(unnecessary_invocations) > 0

        routing_is_correct = (
            len(missed_invocations) == 0
            and len(unnecessary_invocations) == 0
        )

        routing_res = RoutingEvaluationResult(
            task_id=task.task_id,
            required_specialists=expected.required_specialists,
            prohibited_specialists=expected.prohibited_specialists,
            invoked_specialists=invoked_specialists,
            is_correct=routing_is_correct,
            unnecessary_invocations=unnecessary_invocations,
            missed_invocations=missed_invocations,
            wrong_specialist_invoked=wrong_specialist,
        )

        # ---------------------------------------------------------------------
        # 9. Stopping Behavior Evaluation
        # ---------------------------------------------------------------------
        stopping_correct = assigned_stop_reason == expected.expected_stop_reason
        premature_stopping = (
            assigned_stop_reason in (
                StopReason.BUDGET_EXHAUSTED_WITH_CRITICAL_MISSING_FIELDS,
                StopReason.NO_INFORMATION_GAIN,
            )
            and expected.expected_stop_reason == StopReason.OBJECTIVE_SATISFIED
        )

        # ---------------------------------------------------------------------
        # 10. Epistemic Accuracy
        # ---------------------------------------------------------------------
        epistemic_accurate = assigned_status == expected.expected_epistemic_status
        epistemic_acc_score = 1.0 if epistemic_accurate else 0.0

        # ---------------------------------------------------------------------
        # 11. Global Pass/Fail Policy & Failure Severity (Section 26)
        # ---------------------------------------------------------------------
        severity: FailureSeverity | None = None
        failure_mode: str | None = None

        if critical_merge_failure:
            severity = FailureSeverity.CRITICAL
            failure_mode = "ADVERSARIAL_FALSE_MERGE"
        elif security_violation_detected:
            severity = FailureSeverity.CRITICAL
            failure_mode = "PROMPT_INJECTION_BREACH"
        elif broken_chain_detected:
            severity = FailureSeverity.CRITICAL
            failure_mode = "BROKEN_MULTI_HOP_CHAIN"
        elif not epistemic_accurate:
            severity = FailureSeverity.MAJOR
            failure_mode = "EPISTEMIC_MISCLASSIFICATION"
        elif not contradiction_resolved_correctly:
            severity = FailureSeverity.MAJOR
            failure_mode = "UNRESOLVED_CONTRADICTION"
        elif not historical_status_accurate:
            severity = FailureSeverity.MAJOR
            failure_mode = "TEMPORAL_INVALIDITY"
        elif premature_stopping:
            severity = FailureSeverity.MAJOR
            failure_mode = "PREMATURE_STOPPING"
        elif ent_rec < 0.70:
            severity = FailureSeverity.MAJOR
            failure_mode = "LOW_RECALL_OMISSION"
        elif ent_prec < 0.70:
            severity = FailureSeverity.MINOR
            failure_mode = "LOW_PRECISION_NOISE"

        passed = (
            severity is None
            and ent_prec >= 0.70
            and ent_rec >= 0.70
            and chain_completion_rate >= 0.70
            and epistemic_accurate
            and not broken_chain_detected
            and not critical_merge_failure
            and not security_violation_detected
        )

        # For negative tasks where nothing is expected:
        if not expected.expected_entities and not expected.expected_relationships:
            if not discovered_entities and not discovered_relationships and epistemic_accurate and not critical_merge_failure:
                passed = True
                severity = None
                failure_mode = None

        return EvalV2TaskResult(
            task_id=task.task_id,
            title=task.title,
            category=task.category,
            difficulty_tier=task.difficulty_tier,
            split=task.split,
            configuration=configuration,
            passed=passed,
            severity=severity,
            failure_mode=failure_mode,
            entity_precision=ent_prec,
            entity_recall=ent_rec,
            entity_f1=ent_f1,
            relationship_precision=rel_prec,
            relationship_recall=rel_rec,
            relationship_f1=rel_f1,
            field_accuracy=1.0 if passed else (0.5 if ent_rec > 0.5 else 0.0),
            chain_completion_rate=chain_completion_rate,
            hop_results=hop_results,
            broken_chain_detected=broken_chain_detected,
            evidence_coverage=1.0 if extracted_evidence or not expected.expected_entities else 0.0,
            evidence_correctness=1.0 if not broken_chain_detected and not critical_merge_failure else 0.0,
            evidence_completeness=chain_completion_rate,
            evidence_independence_score=evidence_independence_score,
            hallucinated_evidence_detected=False,
            epistemic_accuracy=epistemic_acc_score,
            epistemic_assigned_status=assigned_status,
            contradiction_detected=contradiction_detected,
            contradiction_resolved_correctly=contradiction_resolved_correctly,
            temporal_accuracy=temporal_accuracy,
            effective_date_accurate=effective_date_accurate,
            historical_status_accurate=historical_status_accurate,
            false_positive_merges=false_positive_merges,
            false_negative_misses=fn_ents,
            identity_collision_detected=critical_merge_failure,
            routing_result=routing_res,
            assigned_stop_reason=assigned_stop_reason,
            expected_stop_reason=expected.expected_stop_reason,
            stopping_correct=stopping_correct,
            premature_stopping=premature_stopping,
            security_violation_detected=security_violation_detected,
            prompt_injection_neutralized=prompt_injection_neutralized,
            searches_count=searches_count,
            pages_extracted=pages_count,
            llm_calls_count=llm_calls,
            tokens_count=tokens_count,
            cost_usd=cost_usd,
            runtime_sec=runtime_sec,
            discovered_entities=discovered_entities,
            discovered_relationships=discovered_relationships,
            extracted_evidence=extracted_evidence,
        )
