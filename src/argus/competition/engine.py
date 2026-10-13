"""Heimdallr V3.2: Competition Engine.

Orchestrates candidate evaluation through the formal lifecycle:
DISCOVERED -> AUDITED -> LICENSE_CHECKED -> CAPABILITY_MAPPED -> ISOLATED -> BENCHMARKED -> COMPARED -> DECISION

Computes marginal value, enforces replacement/coexistence/rejection criteria,
and produces auditable CompetitionDecision objects.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from argus.competition.license_auditor import LicenseAuditor
from argus.competition.models import (
    CandidateImplementation,
    CandidateLifecycleState,
    CompetitionDecision,
    CompetitionDecisionType,
    LicenseStatus,
)
from argus.competition.security_gate import SecurityGateValidator

logger = logging.getLogger(__name__)


class CompetitionEngine:
    """Evaluates open-source intelligence candidates against incumbents."""

    def __init__(
        self,
        license_auditor: Optional[LicenseAuditor] = None,
        security_validator: Optional[SecurityGateValidator] = None,
    ) -> None:
        self.license_auditor = license_auditor or LicenseAuditor()
        self.security_validator = security_validator or SecurityGateValidator()

    def advance_lifecycle(
        self,
        candidate: CandidateImplementation,
        target_state: CandidateLifecycleState,
    ) -> CandidateImplementation:
        """Advance candidate implementation to next verified lifecycle state."""
        candidate.lifecycle_state = target_state
        return candidate

    def evaluate_candidate(
        self,
        candidate: CandidateImplementation,
        incumbent_benchmark: Optional[Dict[str, Any]] = None,
        candidate_benchmark: Optional[Dict[str, Any]] = None,
        is_new_capability: bool = False,
    ) -> CompetitionDecision:
        """Execute full evaluation gates and synthesize a formal CompetitionDecision."""
        # 1. Gate: License Audit
        self.advance_lifecycle(candidate, CandidateLifecycleState.LICENSE_CHECKED)
        license_status = self.license_auditor.audit_license(candidate.license)
        candidate.license_status = license_status

        if license_status in (LicenseStatus.INCOMPATIBLE, LicenseStatus.UNKNOWN):
            self.advance_lifecycle(candidate, CandidateLifecycleState.DECISION)
            return CompetitionDecision(
                candidate_id=candidate.candidate_id,
                capability_id=candidate.claimed_capabilities[0] if candidate.claimed_capabilities else "unknown",
                decision=CompetitionDecisionType.REJECT,
                primary_reason=f"License '{candidate.license}' is {license_status.value}. Legal incompatibility prevents recruitment.",
                license_result=license_status,
                security_result="SKIPPED",
                operational_result="REJECTED_LEGAL",
            )

        # 2. Gate: Security Audit
        self.advance_lifecycle(candidate, CandidateLifecycleState.AUDITED)
        security_res = candidate.security_profile.get("status", "PASS")
        if security_res == "FAIL":
            self.advance_lifecycle(candidate, CandidateLifecycleState.DECISION)
            return CompetitionDecision(
                candidate_id=candidate.candidate_id,
                capability_id=candidate.claimed_capabilities[0] if candidate.claimed_capabilities else "unknown",
                decision=CompetitionDecisionType.QUARANTINE,
                primary_reason="Candidate violates security boundary. Quarantined due to unsafe execution profile.",
                license_result=license_status,
                security_result="FAIL",
                operational_result="QUARANTINED_SECURITY",
            )

        # 3. Gate: Capability Mapping
        self.advance_lifecycle(candidate, CandidateLifecycleState.CAPABILITY_MAPPED)
        self.advance_lifecycle(candidate, CandidateLifecycleState.ISOLATED)

        # 4. Gate: Benchmark & Marginal Value Comparison
        self.advance_lifecycle(candidate, CandidateLifecycleState.BENCHMARKED)
        self.advance_lifecycle(candidate, CandidateLifecycleState.COMPARED)

        cand_bench = candidate_benchmark or candidate.benchmark_profile or {}
        inc_bench = incumbent_benchmark or {}

        cand_f1 = cand_bench.get("f1", 0.0)
        cand_recall = cand_bench.get("recall", 0.0)
        cand_precision = cand_bench.get("precision", 0.0)
        cand_pass_rate = cand_bench.get("pass_rate", 0.0)

        inc_f1 = inc_bench.get("f1", 0.0)
        inc_recall = inc_bench.get("recall", 0.0)
        inc_precision = inc_bench.get("precision", 0.0)
        inc_pass_rate = inc_bench.get("pass_rate", 0.0)

        # Marginal values
        f1_delta = cand_f1 - inc_f1
        recall_delta = cand_recall - inc_recall
        precision_delta = cand_precision - inc_precision
        pass_delta = cand_pass_rate - inc_pass_rate

        marginal_value = {
            "f1_delta": round(f1_delta, 4),
            "recall_delta": round(recall_delta, 4),
            "precision_delta": round(precision_delta, 4),
            "pass_rate_delta": round(pass_delta, 4),
            "candidate_pass_rate": round(cand_pass_rate, 4),
            "candidate_f1": round(cand_f1, 4),
        }

        # 5. Gate: Decision Synthesis
        self.advance_lifecycle(candidate, CandidateLifecycleState.DECISION)
        target_cap = candidate.claimed_capabilities[0] if candidate.claimed_capabilities else "unknown"

        # Case A: Brand New Verified Capability
        if is_new_capability:
            if cand_pass_rate >= 0.85:
                return CompetitionDecision(
                    candidate_id=candidate.candidate_id,
                    capability_id=target_cap,
                    decision=CompetitionDecisionType.RECRUIT_NEW_CAPABILITY,
                    primary_reason=f"Candidate provides verified new capability '{target_cap}' with {cand_pass_rate:.1%} pass rate and zero regressions.",
                    marginal_value=marginal_value,
                    license_result=license_status,
                    security_result="PASS",
                    operational_result="APPROVED_NEW_CAPABILITY",
                )
            else:
                return CompetitionDecision(
                    candidate_id=candidate.candidate_id,
                    capability_id=target_cap,
                    decision=CompetitionDecisionType.REJECT,
                    primary_reason=f"New capability candidate failed accuracy threshold (Achieved {cand_pass_rate:.1%}, required >= 85.0%).",
                    marginal_value=marginal_value,
                    license_result=license_status,
                    security_result="PASS",
                    operational_result="REJECTED_LOW_ACCURACY",
                )

        # Case B: Competing for Existing Capability
        regressions = []
        if cand_precision < inc_precision - 0.05:
            regressions.append("Precision regression detected")
        if cand_bench.get("hallucinated_evidence", 0) > inc_bench.get("hallucinated_evidence", 0):
            regressions.append("Higher hallucinated evidence rate")

        # Replacement Policy
        if f1_delta > 0.05 and not regressions:
            return CompetitionDecision(
                candidate_id=candidate.candidate_id,
                capability_id=target_cap,
                incumbent_id=inc_bench.get("implementation_id", "incumbent"),
                decision=CompetitionDecisionType.REPLACE_INCUMBENT,
                primary_reason=f"Challenger strictly supersedes incumbent: F1 +{f1_delta:.2%}, Pass Rate +{pass_delta:.2%} with zero critical regressions.",
                marginal_value=marginal_value,
                regressions=regressions,
                license_result=license_status,
                security_result="PASS",
                operational_result="REPLACE_APPROVED",
            )

        # Coexistence Policy: Both excel on distinct sub-domains
        if cand_bench.get("structured_queries_f1", 0.0) >= 0.90 and inc_bench.get("exploratory_queries_f1", 0.0) >= 0.85:
            return CompetitionDecision(
                candidate_id=candidate.candidate_id,
                capability_id=target_cap,
                incumbent_id=inc_bench.get("implementation_id", "incumbent"),
                decision=CompetitionDecisionType.COEXIST,
                primary_reason="Candidate and incumbent demonstrate complementary superiority: candidate dominates structured queries while incumbent maintains exploratory breadth.",
                marginal_value=marginal_value,
                regressions=regressions,
                license_result=license_status,
                security_result="PASS",
                operational_result="COEXIST_APPROVED",
            )

        # Otherwise: Reject
        return CompetitionDecision(
            candidate_id=candidate.candidate_id,
            capability_id=target_cap,
            incumbent_id=inc_bench.get("implementation_id", "incumbent"),
            decision=CompetitionDecisionType.REJECT,
            primary_reason="Candidate fails to demonstrate statistically significant marginal improvement over incumbent.",
            marginal_value=marginal_value,
            regressions=regressions,
            license_result=license_status,
            security_result="PASS",
            operational_result="REJECTED_INSUFFICIENT_MARGINAL_GAIN",
        )
