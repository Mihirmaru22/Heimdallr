"""Heimdallr V2: First-Class Persistent Investigation State.

Maintains complete, serializable, auditable representation of:
- What we know (entities, claims, evidence, temporal states)
- What remains unknown (questions, information gaps, open hypotheses)
- How we plan to find it (active branches, research actions, specialist calls)
- Why actions were taken (audit trail, information gains, stop state)
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any
import uuid

from pydantic import BaseModel, Field


class AuditTrailEntry(BaseModel):
    """Immutable audit record for every investigation transition."""

    entry_id: str = Field(default_factory=lambda: f"audit_{uuid.uuid4().hex[:10]}")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    action_type: str
    actor: str = "InvestigationEngine"
    details: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""


class InformationGap(BaseModel):
    """Explicit model of missing information required to resolve an objective."""

    gap_id: str = Field(default_factory=lambda: f"gap_{uuid.uuid4().hex[:8]}")
    description: str
    target_entity: str | None = None
    target_attribute: str | None = None
    priority: float = 0.5  # 0.0 (low) to 1.0 (critical)
    is_critical: bool = False
    related_question_id: str | None = None
    is_resolved: bool = False
    resolution_evidence_id: str | None = None


class ConfidenceState(BaseModel):
    """Overall and granular epistemic confidence across active hypotheses and claims."""

    overall_confidence: float = 0.0
    confirmed_claims_count: int = 0
    tentative_claims_count: int = 0
    contradicted_claims_count: int = 0
    unresolved_critical_gaps: int = 0
    epistemic_calibration_score: float = 1.0
    evidence_coverage: float = 0.0
    claim_verification_rate: float = 0.0
    source_independence_score: float = 1.0

    def recompute_calibration(self, state: Any) -> None:
        """Deterministically calibrate confidence across evidence, verification, and independence."""
        total_q = len(state.questions)
        resolved_q = len(state.resolved_questions)
        self.evidence_coverage = round((resolved_q / total_q), 4) if total_q > 0 else 0.0

        total_claims = len(state.claims)
        supported_claims = sum(
            1 for c in state.claims
            if (c.get("evidence_id") and any(e.get("evidence_id") == c.get("evidence_id") for e in state.evidence))
            or c.get("status") in ("NOT_FOUND", "CONTRADICTED", "INSUFFICIENT_EVIDENCE")
        )
        self.confirmed_claims_count = supported_claims
        self.claim_verification_rate = round((supported_claims / total_claims), 4) if total_claims > 0 else 1.0

        # Source independence from syndication clusters
        try:
            from argus.verifier.syndication_intelligence import SyndicationIntelligence
            verdict = SyndicationIntelligence().evaluate(state.evidence)
            self.source_independence_score = round(verdict.independence_ratio, 4)
        except Exception:
            self.source_independence_score = 1.0

        contradiction_factor = 0.75 if any(c.get("status") == "UNRESOLVED" for c in state.contradictions) else 1.0

        # Overall confidence is strictly grounded: zero inflation on missing evidence
        raw_conf = self.evidence_coverage * (0.4 + 0.6 * self.claim_verification_rate) * self.source_independence_score * contradiction_factor
        self.overall_confidence = max(0.0, min(1.0, round(raw_conf, 4)))


class StopState(BaseModel):
    """Explicit termination state with justification and taxonomy reason."""

    is_stopped: bool = False
    stop_reason: str = "IN_PROGRESS"
    stopped_at: str | None = None
    stopping_rationale: str = ""
    satisfaction_ratio: float = 0.0
    budget_exhausted: bool = False
    unresolvable_contradiction_detected: bool = False


class InvestigationState(BaseModel):
    """First-class persisted state of an active or completed investigation."""

    investigation_id: str = Field(default_factory=lambda: f"inv_{uuid.uuid4().hex[:12]}")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Objective & scope definition
    objective: str
    objective_contract: dict[str, Any] = Field(default_factory=dict)
    final_epistemic_status: str = Field(
        default="UNKNOWN",
        description="Overall synthesized epistemic status: SUPPORTED, CONTRADICTED, NOT_FOUND, INSUFFICIENT_EVIDENCE",
    )

    # Discovered knowledge graph
    entities: dict[str, dict[str, Any]] = Field(default_factory=dict)  # name -> entity metadata
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    claims: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)

    # Question & hypothesis topology
    questions: dict[str, dict[str, Any]] = Field(default_factory=dict)  # q_id -> question dict
    hypotheses: dict[str, dict[str, Any]] = Field(default_factory=dict)  # h_id -> hypothesis dict
    unresolved_questions: list[str] = Field(default_factory=list)
    resolved_questions: list[str] = Field(default_factory=list)

    # Contradictions & temporal dimensions
    contradictions: list[dict[str, Any]] = Field(default_factory=list)
    temporal_states: list[dict[str, Any]] = Field(default_factory=list)

    # Specialist orchestration tracking
    specialist_invocations: list[dict[str, Any]] = Field(default_factory=list)

    # Branching structure
    active_branches: list[str] = Field(default_factory=list)
    completed_branches: list[str] = Field(default_factory=list)
    abandoned_branches: list[str] = Field(default_factory=list)

    # Execution telemetry & observations
    research_actions: list[dict[str, Any]] = Field(default_factory=list)
    observations: list[dict[str, Any]] = Field(default_factory=list)
    information_gaps: list[InformationGap] = Field(default_factory=list)

    # Budget & marginal gain tracking
    research_budget: dict[str, Any] = Field(
        default_factory=lambda: {
            "max_steps": 15,
            "steps_taken": 0,
            "max_searches": 20,
            "searches_count": 0,
            "max_tokens": 25000,
            "tokens_consumed": 0,
            "cost_usd": 0.0,
            "consecutive_zero_gains": 0,
        }
    )
    information_gain_history: list[dict[str, Any]] = Field(default_factory=list)

    # Decision & termination states
    confidence_state: ConfidenceState = Field(default_factory=ConfidenceState)
    stop_state: StopState = Field(default_factory=StopState)
    audit_trail: list[AuditTrailEntry] = Field(default_factory=list)

    def record_audit(
        self,
        action_type: str,
        details: dict[str, Any] | None = None,
        rationale: str = "",
        actor: str = "InvestigationEngine",
    ) -> AuditTrailEntry:
        """Append an auditable event to the investigation history."""
        entry = AuditTrailEntry(
            action_type=action_type,
            actor=actor,
            details=details or {},
            rationale=rationale,
        )
        self.audit_trail.append(entry)
        self.updated_at = datetime.now(timezone.utc).isoformat()
        return entry

    def register_entity(self, name: str, entity_type: str = "UNKNOWN", metadata: dict[str, Any] | None = None) -> None:
        """Register or update an entity node in the knowledge state."""
        if name not in self.entities:
            self.entities[name] = {
                "name": name,
                "type": entity_type,
                "first_seen": datetime.now(timezone.utc).isoformat(),
                "metadata": metadata or {},
            }
        elif metadata:
            self.entities[name]["metadata"].update(metadata)

    def add_claim(self, claim: dict[str, Any]) -> str:
        """Add an evidence-backed claim to the state."""
        claim_id = claim.get("claim_id") or f"clm_{uuid.uuid4().hex[:8]}"
        claim["claim_id"] = claim_id
        claim["recorded_at"] = datetime.now(timezone.utc).isoformat()
        self.claims.append(claim)
        return claim_id

    def add_evidence(self, evidence_item: dict[str, Any]) -> str:
        """Add an evidence object with provenance to the state, deduplicating identical records."""
        url = evidence_item.get("url")
        snippet = evidence_item.get("snippet")
        for existing in self.evidence:
            if url and existing.get("url") == url:
                if not snippet or existing.get("snippet") == snippet:
                    return existing.get("evidence_id", "")

        ev_id = evidence_item.get("evidence_id") or f"evi_{uuid.uuid4().hex[:8]}"
        evidence_item["evidence_id"] = ev_id
        evidence_item["recorded_at"] = datetime.now(timezone.utc).isoformat()
        self.evidence.append(evidence_item)
        return ev_id

    def to_json(self, indent: int = 2) -> str:
        """Serialize complete investigation state to JSON."""
        return self.model_dump_json(indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> InvestigationState:
        """Deserialize complete investigation state from JSON."""
        return cls.model_validate_json(json_str)

    def summary(self) -> dict[str, Any]:
        """Produce high-level summary of investigation status and yields."""
        return {
            "investigation_id": self.investigation_id,
            "objective": self.objective,
            "entities_count": len(self.entities),
            "claims_count": len(self.claims),
            "evidence_count": len(self.evidence),
            "total_questions": len(self.questions),
            "unresolved_questions": len(self.unresolved_questions),
            "resolved_questions": len(self.resolved_questions),
            "hypotheses_count": len(self.hypotheses),
            "contradictions_count": len(self.contradictions),
            "specialist_invocations": len(self.specialist_invocations),
            "steps_taken": self.research_budget.get("steps_taken", 0),
            "is_stopped": self.stop_state.is_stopped,
            "stop_reason": self.stop_state.stop_reason,
            "overall_confidence": self.confidence_state.overall_confidence,
        }

    def to_result(self) -> InvestigationResult:
        """Synthesize a structured, domain-agnostic investigation result."""
        # Recompute calibration to guarantee up-to-date epistemic confidence
        self.confidence_state.recompute_calibration(self)

        findings = list(self.claims)
        evidence_list = list(self.evidence)

        source_refs: list[str] = []
        seen_refs = set()
        for ev in self.evidence:
            ref = ev.get("url") or ev.get("source_type") or ev.get("title")
            if ref and ref not in seen_refs:
                seen_refs.add(ref)
                source_refs.append(str(ref))

        unresolved = [
            self.questions[qid]
            for qid in self.unresolved_questions
            if qid in self.questions
        ]

        limitations: list[str] = []
        if self.stop_state.budget_exhausted:
            limitations.append(f"Execution terminated upon reaching budget limit ({self.research_budget.get('max_steps', 15)} steps).")
        for gap in self.information_gaps:
            if not gap.is_resolved and gap.is_critical:
                limitations.append(f"Unresolved critical gap: {gap.description}")
        for audit in self.audit_trail:
            if audit.action_type in ("UNSUPPORTED_CAPABILITY_REQUESTED", "ADAPTER_EXECUTION_FAILED", "SECURITY_POLICY_VIOLATION"):
                reason = audit.details.get("reason") or audit.details.get("error") or audit.rationale
                limitations.append(f"{audit.action_type}: {reason}")

        return InvestigationResult(
            investigation_id=self.investigation_id,
            objective=self.objective,
            research_scope={
                "target_entities": list(self.entities.keys()),
                "contract": dict(self.objective_contract),
                "total_questions": len(self.questions),
                "branches_count": len(self.active_branches) + len(self.completed_branches),
            },
            completion_status=self.stop_state.stop_reason,
            stopping_rationale=self.stop_state.stopping_rationale,
            findings=findings,
            supporting_evidence=evidence_list,
            source_references=source_refs,
            confidence={
                "overall_confidence": self.confidence_state.overall_confidence,
                "confirmed_claims_count": self.confidence_state.confirmed_claims_count,
                "epistemic_calibration_score": self.confidence_state.epistemic_calibration_score,
                "evidence_coverage": self.confidence_state.evidence_coverage,
                "claim_verification_rate": self.confidence_state.claim_verification_rate,
                "source_independence_score": self.confidence_state.source_independence_score,
            },
            contradictions=list(self.contradictions),
            unresolved_questions=unresolved,
            limitations=limitations,
            steps_taken=self.research_budget.get("steps_taken", 0),
            epistemic_status=self.final_epistemic_status,
        )


class InvestigationResult(BaseModel):
    """Structured, domain-agnostic synthesized output of an investigation."""

    investigation_id: str
    objective: str
    research_scope: dict[str, Any] = Field(default_factory=dict)
    completion_status: str
    stopping_rationale: str = ""
    findings: list[dict[str, Any]] = Field(default_factory=list)
    supporting_evidence: list[dict[str, Any]] = Field(default_factory=list)
    source_references: list[str] = Field(default_factory=list)
    confidence: dict[str, Any] = Field(default_factory=dict)
    contradictions: list[dict[str, Any]] = Field(default_factory=list)
    unresolved_questions: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    steps_taken: int = 0
    epistemic_status: str = Field(default="UNKNOWN")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

