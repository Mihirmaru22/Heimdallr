"""Heimdallr V2: Investigation Engine Orchestrator.

The central execution core that drives persistent, hypothesis-driven investigations:
- Coordinates Planner, Stopping Policy, Persistence Store, and Domain Specialists
- Executes multi-specialist chaining (Corporate -> Infra -> Identity -> Corporate)
- Updates epistemic state and maintains full crash-recovery persistence
"""

from __future__ import annotations
from argus.specialists.outcome import SpecialistOutcome, SpecialistStatus

from datetime import datetime, timezone
import concurrent.futures
import logging
import re
import threading
import time
from typing import Any
import uuid

from argus.domain.jurisdiction_graph import JurisdictionEntityGraph
from argus.investigation.action import ActionType, ResearchAction
from argus.investigation.benchmark.corpus import INVESTIGATION_CORPUS_REGISTRY
from argus.investigation.branch import BranchStatus, InvestigationBranch
from argus.investigation.evidence import EvidenceRequirement, EvidenceStatus
from argus.investigation.hypothesis import HypothesisStatus, InvestigationHypothesis
from argus.investigation.planner import InvestigationPlanner
from argus.investigation.question import InvestigationQuestion, QuestionStatus, QuestionType
from argus.investigation.state import (
    AuditTrailEntry,
    InformationGap,
    InvestigationResult,
    InvestigationState,
    StopState,
)
from argus.investigation.stopping import InvestigationStopReason, InvestigationStoppingPolicy
from argus.investigation.store import InvestigationStore
from argus.specialists.corporate import CorporateProbeSpecialist
from argus.specialists.identity import IdentityProbeSpecialist
from argus.specialists.infrastructure import InfrastructureProbeSpecialist
from argus.verifier.syndication_intelligence import SyndicationIntelligence
from argus.verifier.temporal_reasoner import (
    LifecycleState,
    TemporalRecord,
    TemporalStateReasoner,
)
from argus.capability_registry.registry import CapabilityRegistry
from argus.capability_registry.adapters import get_adapter_for_implementation, simulated_registry
from argus.competition.security_gate import SecurityGateValidator
from argus.investigation.contradiction_resolver import (
    ContradictionRecord,
    ContradictionResolver,
    EntityScopeVerifier,
    EpistemicSufficiencyEvaluator,
)
from argus.investigation.reported_disputes import classify_sentence, detect_reported_disputes, split_sentences
from argus.investigation.benchmark.v2.semantic_auditor import (
    IndependentSemanticAuditor,
    SemanticSupportStatus,
)
from argus.investigation.relevance import clean_entity_name, is_contextually_relevant_host
from argus.investigation.technographics import extract_technographic_deployments
from argus.investigation.claim_verification import (
    POSITIVE_STATUSES,
    add_support,
    ground_passage,
    term_in_passage,
    verify_claim,
)
from argus.investigation.resolution import (
    budget_denials,
    claim_kind_fits_question,
    claims_index,
    coverage,
    incomplete_stop,
    positive_linked_claims,
    verified_linked_claims,
)
from argus.investigation.objective_parser import EnumerationObjective
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class ToolPermissionGate:
    """Enforces deterministic application-level authorization and permission gating on all research tools/actions."""

    ALLOWED_SPECIALISTS = {
        "corporate",
        "infrastructure",
        "identity",
        "sanctions",
        "onion",
        "email",
        "none",
    }
    DYNAMIC_ALLOWED_SPECIALISTS: set[str] = set()

    BUILTIN_AUTHORIZED_IMPLEMENTATIONS: set[str] = {
        "impl_argus_generalist_v1",
        "impl_identity_probe_specialist_v1",
        "impl_infrastructure_probe_specialist_v1",
        "impl_corporate_registry_specialist_v1",
        "impl_challenger_identity_specialist_v2",
        "impl_opensanctions_probe_v1",
        "impl_onion_integrated_v1",
        "impl_ahmia_search_v1",
        "impl_torbot_crawler_v1",
        "impl_email_to_account_discovery_v1",
        "impl_identity_to_email_discovery_v1",
        "impl_email_address_verification_v1",
        "impl_email_identity_resolution_v1",
        "impl_email_account_specialist_v1",
    }
    DYNAMIC_AUTHORIZED_IMPLEMENTATIONS: set[str] = set()
    _auth_lock = threading.Lock()

    @classmethod
    def register_allowed_specialist(cls, specialist_name: str) -> None:
        """Register a domain specialist as authorized under application policy."""
        with cls._auth_lock:
            cls.DYNAMIC_ALLOWED_SPECIALISTS.add(specialist_name.lower())

    @classmethod
    def unregister_allowed_specialist(cls, specialist_name: str) -> None:
        """Unregister a domain specialist."""
        with cls._auth_lock:
            cls.DYNAMIC_ALLOWED_SPECIALISTS.discard(specialist_name.lower())

    @classmethod
    def authorize_implementation(cls, implementation_id: str) -> None:
        """Explicitly authorize an implementation ID for execution under application policy."""
        with cls._auth_lock:
            cls.DYNAMIC_AUTHORIZED_IMPLEMENTATIONS.add(implementation_id)

    @classmethod
    def deauthorize_implementation(cls, implementation_id: str) -> None:
        """Deauthorize an implementation ID from execution."""
        with cls._auth_lock:
            cls.DYNAMIC_AUTHORIZED_IMPLEMENTATIONS.discard(implementation_id)

    DISALLOWED_PARAM_KEYS = {
        "cmd", "command", "shell", "exec", "script", "eval", "system", "code", "run",
    }

    DANGEROUS_COMMAND_PATTERNS = [
        re.compile(r"(\$\([^\)]+\)|`[^`]+`)"),  # Command substitution
        re.compile(r"(&&|;|\|)\s*(rm|cat|ls|nc|bash|sh|curl|wget|id|whoami|python|perl|eval|exec|chmod|chown)\b", re.IGNORECASE),
        re.compile(r"(\.\./|\.\.\\){2,}"),  # Path traversal
        re.compile(r"(?i)(/etc/(passwd|shadow|hosts)|~/\.ssh|c:\\windows)"),  # Sensitive system paths
        re.compile(r"(?i)\b(system\s+override|ignore\s+(all\s+)?prior\s+instructions)\b"),  # Prompt injection overrides
    ]

    @classmethod
    def _validate_structured_param_node(cls, node: Any, depth: int = 0) -> tuple[bool, str]:
        """Recursively inspect parameter trees to prevent smuggled commands, callables, or injection payloads."""
        if depth > 10:
            return False, "Parameter nesting exceeds maximum permitted depth of 10"
        if callable(node) or hasattr(node, "__code__"):
            return False, "Callable parameter value prohibited in parameters"
        if isinstance(node, dict):
            if len(node) > 50:
                return False, "Dictionary exceeds maximum key limit of 50"
            for k, v in node.items():
                if not isinstance(k, str) or len(k) > 64:
                    return False, f"Invalid action parameter key: {k!r}"
                if k.lower() in cls.DISALLOWED_PARAM_KEYS:
                    return False, f"Disallowed execution parameter key: {k}"
                ok, err = cls._validate_structured_param_node(v, depth + 1)
                if not ok:
                    return False, err
        elif isinstance(node, (list, tuple, set)):
            if len(node) > 100:
                return False, "Collection parameter exceeds maximum item limit of 100"
            for item in node:
                ok, err = cls._validate_structured_param_node(item, depth + 1)
                if not ok:
                    return False, err
        elif isinstance(node, str):
            if len(node) > 65536:
                return False, "Parameter string value exceeds maximum length of 65536"
        elif not isinstance(node, (int, float, bool, type(None))):
            return False, f"Unexpected parameter value type: {type(node).__name__}"
        return True, ""

    @classmethod
    def authorize_action(
        cls,
        action: ResearchAction,
        state: InvestigationState,
    ) -> tuple[bool, str]:
        """Verify whether the requested research action is authorized under current policy.

        Returns (is_authorized, rejection_reason).
        """
        # 1. Enforce ActionType schema validity
        if not isinstance(action.action_type, ActionType):
            try:
                ActionType(str(action.action_type))
            except ValueError:
                return False, f"Unauthorized ActionType: {action.action_type}"

        # 2. Enforce Specialist whitelist
        spec = (action.specialist or "none").lower()
        contract = state.objective_contract or {}
        contract_specs = [s.lower() for s in contract.get("allowed_specialists", [])]

        is_allowed = (
            spec in cls.ALLOWED_SPECIALISTS
            or spec in cls.DYNAMIC_ALLOWED_SPECIALISTS
            or spec in contract_specs
        )
        if not is_allowed:
            return False, f"Unauthorized specialist requested: {action.specialist}"

        # 3. Enforce Contract-Level Specialist constraints if defined
        allowed_contract_specialists = contract.get("allowed_specialists")
        if allowed_contract_specialists is not None:
            if spec != "none" and spec not in contract_specs:
                return False, f"Specialist '{spec}' is not permitted by investigation contract"

        # 4. Enforce Contract-Level Capability constraints if defined
        if action.capability_id:
            allowed_contract_capabilities = contract.get("allowed_capabilities")
            if allowed_contract_capabilities is not None:
                if action.capability_id not in allowed_contract_capabilities:
                    return False, f"Capability '{action.capability_id}' is not permitted by investigation contract"

        # 5. Enforce Implementation Authorization & Registration
        if action.implementation_id:
            try:
                get_adapter_for_implementation(action.implementation_id)
            except KeyError:
                return False, f"Unregistered implementation ID: {action.implementation_id}"

            allowed_contract_implementations = contract.get("allowed_implementations")
            if allowed_contract_implementations is not None:
                if action.implementation_id not in allowed_contract_implementations:
                    return False, f"Implementation '{action.implementation_id}' is not permitted by investigation contract"

            with cls._auth_lock:
                is_authorized = (
                    action.implementation_id in cls.BUILTIN_AUTHORIZED_IMPLEMENTATIONS
                    or action.implementation_id in cls.DYNAMIC_AUTHORIZED_IMPLEMENTATIONS
                    or (allowed_contract_implementations is not None and action.implementation_id in allowed_contract_implementations)
                )
            if not is_authorized:
                return False, (
                    f"Unauthorized implementation '{action.implementation_id}': "
                    f"capability registration does not grant execution permission"
                )

        # 6. Structured Argument Validation (Deep Recursive Validation)
        if action.parameters is not None:
            if not isinstance(action.parameters, dict):
                return False, "Action parameters must be a dictionary"
            ok, err = cls._validate_structured_param_node(action.parameters, depth=0)
            if not ok:
                return False, err

        # 7. Query Validation (Preserving Legitimate Research Queries)
        query = action.query or ""
        if len(query) > 10000:
            return False, "Action query exceeds maximum permitted length of 10000 characters"

        for pat in cls.DANGEROUS_COMMAND_PATTERNS:
            if pat.search(query):
                return False, f"Adversarial or shell metacharacters detected in action query: {query}"

        return True, ""


# Role words that precede a name in running text ("founder and Chief Executive
# Officer Dr. Jane Roe has stepped down"); they are not part of the person's name.
_ROLE_PREFIX_WORDS = {
    "chief", "executive", "officer", "operating", "financial", "technology", "scientific",
    "founder", "co-founder", "president", "vice", "senior", "interim", "acting", "former",
    "director", "chairman", "chairwoman", "chair", "head", "general", "counsel", "managing",
    "ceo", "cfo", "cto", "coo", "cso", "and", "the", "our", "its", "board", "member",
}


def _name_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def person_name_from_span(span: str) -> str:
    """The person's name at the end of a captured span, without leading role words."""
    tokens = (span or "").strip().split()
    while tokens and tokens[-1].lower() in {"has", "had", "have"}:
        tokens.pop()
    while tokens and tokens[0].lower().strip(".,") in _ROLE_PREFIX_WORDS:
        tokens.pop(0)
    return " ".join(tokens).strip(" ,")


class InvestigationEngine:
    """Autonomous, persistent investigation engine orchestrating research planning and verification."""

    def __init__(
        self,
        planner: InvestigationPlanner | None = None,
        stopping_policy: InvestigationStoppingPolicy | None = None,
        store: InvestigationStore | None = None,
        corpus: Any | None = None,
        registry: CapabilityRegistry | None = None,
        simulated_registries: bool | None = None,
    ) -> None:
        self.registry = registry or (getattr(planner, "registry", None) if planner else None) or CapabilityRegistry()
        self.planner = planner or InvestigationPlanner(registry=self.registry)
        self.stopping_policy = stopping_policy or InvestigationStoppingPolicy()
        self.store = store or InvestigationStore()
        self.corpus = corpus or INVESTIGATION_CORPUS_REGISTRY
        # Frozen benchmark registries (invented companies, hosts, accounts) belong to the
        # offline benchmark corpus only. Default: on when no corpus is given (that run
        # reads INVESTIGATION_CORPUS_REGISTRY), off for any supplied corpus such as the
        # live web retriever.
        self.simulated_registries = (corpus is None) if simulated_registries is None else simulated_registries

        # Specialist adaptations
        if self.simulated_registries:
            self.identity_specialist = IdentityProbeSpecialist(platform_registry=simulated_registry("identity"))
            self.infra_specialist = InfrastructureProbeSpecialist(registry=simulated_registry("infrastructure"))
            self.corp_specialist = CorporateProbeSpecialist(registry_database=simulated_registry("corporate"))
        else:
            self.identity_specialist = IdentityProbeSpecialist()
            self.infra_specialist = InfrastructureProbeSpecialist()
            self.corp_specialist = CorporateProbeSpecialist()

        # Upgraded domain reasoners
        self.temporal_reasoner = TemporalStateReasoner()
        self.jurisdiction_graph = JurisdictionEntityGraph()
        self.syndication_intel = SyndicationIntelligence()
        self.contradiction_resolver = ContradictionResolver()
        self.semantic_auditor = IndependentSemanticAuditor()

    def start_investigation(
        self,
        objective: str,
        contract: dict[str, Any] | None = None,
        as_of_date: str | None = None,
    ) -> InvestigationState:
        """Initialize and persist a new investigation session."""
        state = self.planner.initialize_investigation(
            objective=objective,
            objective_contract=contract,
            as_of_date=as_of_date,
        )
        self.store.save_state(state)
        return state

    def resume_investigation(
        self,
        investigation_id: str,
        max_additional_steps: int = 10,
    ) -> InvestigationState:
        """Reload persisted investigation from store and resume research execution."""
        state = self.store.load_state(investigation_id)
        budget = state.research_budget
        budget["max_steps"] = budget.get("steps_taken", 0) + max_additional_steps
        state.stop_state.is_stopped = False
        state.record_audit(
            action_type="INVESTIGATION_RESUMED",
            details={"investigation_id": investigation_id, "additional_steps": max_additional_steps},
            rationale="Resumed interrupted investigation from disk snapshot.",
        )
        self.store.save_state(state)
        return state

    def execute_step(self, state: InvestigationState) -> tuple[InvestigationState, bool]:
        """Execute a single planned research cycle. Return (state, is_finished)."""
        # 1. Pre-step stopping evaluation
        should_stop, reason, rationale = self.stopping_policy.evaluate(state)
        if should_stop:
            state.stop_state.is_stopped = True
            state.stop_state.stop_reason = reason.value if reason else "STOPPED"
            state.stop_state.stopping_rationale = rationale
            state.stop_state.stopped_at = datetime.now(timezone.utc).isoformat()
            if reason in (
                InvestigationStopReason.BUDGET_EXHAUSTED_WITH_ACCEPTABLE_COVERAGE,
                InvestigationStopReason.BUDGET_EXHAUSTED_WITH_CRITICAL_MISSING_FIELDS,
            ) or state.research_budget.get("steps_taken", 0) >= state.research_budget.get("max_steps", 15):
                state.stop_state.budget_exhausted = True
            state.record_audit(
                action_type="INVESTIGATION_STOPPED",
                details={"stop_reason": state.stop_state.stop_reason},
                rationale=rationale,
            )
            self.store.save_state(state)
            return state, True

        # 2. Plan next prioritized actions
        actions = self.planner.select_next_actions(state, limit=1)
        if not actions:
            # No open actions could be planned; evaluate termination
            state.stop_state.is_stopped = True
            total_questions = len(state.questions)
            resolved_count = len(state.resolved_questions)

            cov = coverage(state)

            if total_questions > 0 and len(state.unresolved_questions) == 0 and not cov["unanswered_critical"] and cov["any_answered"]:
                state.stop_state.stop_reason = InvestigationStopReason.OBJECTIVE_SATISFIED.value
                state.stop_state.stopping_rationale = (
                    f"All {total_questions} investigation questions closed; "
                    f"{cov['objective_answered']}/{cov['objective_total']} objective questions answered by evidence."
                )
            elif cov["unanswered_critical"] and budget_denials(state):
                reason, rationale = incomplete_stop(state)
                state.stop_state.stop_reason = reason
                state.stop_state.stopping_rationale = rationale
                state.stop_state.budget_exhausted = True
            elif any(obs.get("outcome") == "SOURCE_UNAVAILABLE" or obs.get("status") == "SOURCE_UNAVAILABLE" for obs in state.observations):
                state.stop_state.stop_reason = InvestigationStopReason.SOURCE_UNAVAILABLE.value
                state.stop_state.stopping_rationale = "Required primary sources are unavailable or inaccessible."
            elif any(obs.get("status") in ("FAILED", "UNSUPPORTED_CAPABILITY") for obs in state.observations) and resolved_count == 0:
                state.stop_state.stop_reason = InvestigationStopReason.EXECUTION_FAILED.value
                state.stop_state.stopping_rationale = "Research actions failed or requested unsupported capabilities."
            else:
                reason, rationale = incomplete_stop(state)
                state.stop_state.stop_reason = reason
                state.stop_state.stopping_rationale = rationale
            state.stop_state.stopped_at = datetime.now(timezone.utc).isoformat()
            self.store.save_state(state)
            return state, True

        action = actions[0]
        state.research_actions.append(action.model_dump())
        state.research_budget["steps_taken"] += 1

        # 3. Execute action via corpus or appropriate specialist
        records = getattr(self.corpus, "evidence_records", None)
        records_before = len(records) if isinstance(records, list) else 0
        obs = self._dispatch_action(action, state)
        self._record_retrieval_denials(state, action, obs, records_before)
        state.observations.append(obs)

        # 4. Apply observation to state & update belief topology
        gain = self._apply_observation(state, action, obs)

        # Update budget and gain history
        budget = state.research_budget
        budget["tokens_consumed"] += obs.get("tokens", 250)
        budget["cost_usd"] += obs.get("cost_usd", 0.001)

        if gain < 0.05:
            budget["consecutive_zero_gains"] = budget.get("consecutive_zero_gains", 0) + 1
        else:
            budget["consecutive_zero_gains"] = 0

        state.information_gain_history.append({
            "step": budget["steps_taken"],
            "action_id": action.action_id,
            "information_gain": gain,
        })

        action.mark_executed(summary=f"Observation yielded gain={gain:.2f}")
        for ra in state.research_actions:
            if ra.get("action_id") == action.action_id:
                ra["status"] = "EXECUTED"
                ra["summary"] = f"Observation yielded gain={gain:.2f}"

        # 5. Post-step stopping evaluation
        should_stop, reason, rationale = self.stopping_policy.evaluate(state)
        if should_stop:
            state.stop_state.is_stopped = True
            state.stop_state.stop_reason = reason.value if reason else "STOPPED"
            state.stop_state.stopping_rationale = rationale
            state.stop_state.stopped_at = datetime.now(timezone.utc).isoformat()
            if reason in (
                InvestigationStopReason.BUDGET_EXHAUSTED_WITH_ACCEPTABLE_COVERAGE,
                InvestigationStopReason.BUDGET_EXHAUSTED_WITH_CRITICAL_MISSING_FIELDS,
            ) or state.research_budget.get("steps_taken", 0) >= state.research_budget.get("max_steps", 15):
                state.stop_state.budget_exhausted = True
            state.record_audit(
                action_type="INVESTIGATION_STOPPED",
                details={"stop_reason": state.stop_state.stop_reason},
                rationale=rationale,
            )

        # 6. Checkpoint state to persistence store
        self.store.save_state(state)
        return state, state.stop_state.is_stopped

    def run_to_completion(
        self,
        objective: str,
        contract: dict[str, Any] | None = None,
        as_of_date: str | None = None,
        max_steps: int = 15,
    ) -> InvestigationState:
        """Run investigation loop until an authorized stopping condition is satisfied."""
        contract = contract or {}
        contract["max_steps"] = max_steps
        state = self.start_investigation(objective=objective, contract=contract, as_of_date=as_of_date)

        while not state.stop_state.is_stopped:
            state, finished = self.execute_step(state)
            if finished:
                break

        state.final_epistemic_status = self.synthesize_epistemic_status(state)
        self.store.save_state(state)
        return state

    def synthesize_epistemic_status(self, state: InvestigationState) -> str:
        """Synthesize final epistemic status from question topology, contradictions, and evidence."""
        obj_lower = (state.objective or "").lower()
        contract_entities = [str(e).lower() for e in (state.objective_contract.get("target_entities") or [])]

        obj_tokens = set(re.findall(r"\w{4,}", obj_lower))
        stop_words = {
            "investigate", "determine", "identify", "analyze", "examine",
            "compare", "verify", "whether", "their", "which", "against",
            "between", "using", "from", "with", "into", "through",
        }
        target_concept_tokens = obj_tokens - stop_words - set(re.findall(r"\w{4,}", " ".join(contract_entities)))

        # Organizational form words: they say what kind of body something is, not which one.
        GENERIC_CORP_TOKENS = {
            "corp", "corporation", "ltd", "limited", "inc", "llc", "plc", "gmbh", "company", "co",
            "division", "department", "unit", "group", "holdings", "alliance", "consortium",
            "center", "centre", "institute", "foundation", "agency", "bureau", "office",
        }

        def is_relevant(subj: str, text: str) -> bool:
            s_low = (subj or "").lower()
            t_low = (text or "").lower()
            combined = f"{s_low} {t_low}"
            if not s_low or s_low == "entity":
                return True
            if contract_entities:
                for ce in contract_entities:
                    if ce in s_low or s_low in ce:
                        return True
                    ce_tokens = set(re.findall(r"\w{3,}", ce))
                    s_tokens = set(re.findall(r"\w{3,}", s_low))
                    ce_distinctive = ce_tokens - GENERIC_CORP_TOKENS
                    s_distinctive = s_tokens - GENERIC_CORP_TOKENS

                    # If contract entity specifies a scoped child/unit (e.g. "<Brand> cryogenic
                    # rocket division"), the leading distinctive token is the parent brand and the
                    # remaining distinctive tokens scope the child.
                    ce_ordered = [t for t in re.findall(r"\w{3,}", ce) if t not in GENERIC_CORP_TOKENS]
                    child_modifiers = set(ce_ordered[1:]) - {ce_ordered[0]} if ce_ordered else set()
                    if len(child_modifiers) >= 1 and len(ce_distinctive) >= 2:
                        if any(m in combined for m in child_modifiers):
                            return True
                        continue

                    if ce_distinctive and s_distinctive:
                        if ce_distinctive & s_distinctive:
                            return True
                    elif ce_tokens & s_tokens:
                        return True
                return False
            if s_low in obj_lower:
                return True
            s_tokens = set(re.findall(r"\w{4,}", s_low)) - GENERIC_CORP_TOKENS
            o_tokens = set(re.findall(r"\w{4,}", obj_lower)) - GENERIC_CORP_TOKENS
            return bool(s_tokens & o_tokens)

        def claim_substantiates_objective(claim: dict[str, Any]) -> bool:
            c_text = (
                claim.get("object", "") + " " +
                claim.get("predicate", "") + " " +
                claim.get("subject", "") + " " +
                claim.get("source_passage", "")
            ).lower()
            c_tokens = set(re.findall(r"[a-zA-Z0-9]{4,}", c_text))
            if target_concept_tokens:
                return bool(target_concept_tokens & c_tokens)
            return True

        # 1. Contradictions on core research objective
        if state.contradictions:
            relevant_contras = [
                c for c in state.contradictions
                if is_relevant(c.get("subject", ""), c.get("topic", "") + " " + c.get("claim_a", ""))
            ]
            if relevant_contras:
                return "CONTRADICTED"



        # 2. Check explicitly scoped negative findings
        not_found_claims = [c for c in state.claims if c.get("status") == "NOT_FOUND"]
        if not_found_claims:
            if any(is_relevant(c.get("subject", ""), c.get("object", "") + " " + (c.get("source_passage") or "")) for c in not_found_claims):
                rel_supp = [
                    c for c in state.claims
                    if c.get("status") == "SUPPORTED" and is_relevant(c.get("subject", ""), c.get("object", "")) and claim_substantiates_objective(c)
                ]
                if not rel_supp:
                    return "NOT_FOUND"

        # 3. Check for Epistemic Sufficiency / Abstention
        insuff_claims = [
            c for c in state.claims
            if c.get("status") == "INSUFFICIENT_EVIDENCE" and is_relevant(c.get("subject", ""), c.get("object", ""))
        ]
        supp_claims = [
            c for c in state.claims
            if c.get("status") == "SUPPORTED" and is_relevant(c.get("subject", ""), c.get("object", "")) and claim_substantiates_objective(c)
        ]

        # 4. Critical questions resolution
        critical_questions = [q for q in state.questions.values() if q.get("is_critical", False)]
        target_questions = critical_questions if critical_questions else list(state.questions.values())

        if any(q.get("status") in (QuestionStatus.CONTRADICTED.value, "CONTRADICTED") for q in target_questions):
            return "CONTRADICTED"

        if any(q.get("status") in (QuestionStatus.NOT_FOUND.value, "NOT_FOUND") for q in target_questions) and not supp_claims:
            return "NOT_FOUND"

        # If relevant substantiated claims exist, investigation succeeded
        if supp_claims:
            return "SUPPORTED"

        relevant_contra_claims = [
            c for c in state.claims
            if c.get("status") == "CONTRADICTED" and is_relevant(c.get("subject", ""), c.get("object", "") + " " + c.get("predicate", ""))
        ]
        if relevant_contra_claims:
            return "CONTRADICTED"

        # If relevant findings exist but are insufficient or fragmentary
        if insuff_claims or any(q.get("status") in (QuestionStatus.INSUFFICIENT_EVIDENCE.value, "INSUFFICIENT_EVIDENCE") for q in target_questions):
            return "INSUFFICIENT_EVIDENCE"

        if not state.evidence:
            # Do not infer that an unavailable source proves an account does not exist
            if any("FAIL" in a.action_type or "TIMEOUT" in a.action_type or "UNAVAILABLE" in a.action_type for a in state.audit_trail) or any(
                inv.get("outcome") in ("SOURCE_UNAVAILABLE", "SOURCE_ERROR", "TIMEOUT") for inv in state.specialist_invocations
            ):
                return "INSUFFICIENT_EVIDENCE"
            return "NOT_FOUND"

        return "INSUFFICIENT_EVIDENCE"

    def reset(self) -> None:
        """Reset internal state/planner for a new investigation task."""
        self.planner = InvestigationPlanner(registry=self.registry)
        self.store = InvestigationStore()

    def run_investigation(
        self,
        task_or_objective: Any,
        contract: dict[str, Any] | None = None,
        as_of_date: str | None = None,
        max_steps: int = 15,
    ) -> InvestigationState:
        """Execute an investigation from either a task object or an objective string."""
        if hasattr(task_or_objective, "objective"):
            obj = task_or_objective.objective
            c = dict(task_or_objective.contract) if getattr(task_or_objective, "contract", None) else (contract or {})
            m_steps = c.get("max_steps", max_steps)
            a_date = as_of_date or c.get("as_of_date")
            return self.run_to_completion(objective=obj, contract=c, as_of_date=a_date, max_steps=m_steps)
        return self.run_to_completion(objective=str(task_or_objective), contract=contract, as_of_date=as_of_date, max_steps=max_steps)

    def synthesize_report(self, state: InvestigationState) -> InvestigationResult:
        """Synthesize final investigation findings into a domain-agnostic structured report."""
        return state.to_result()

    def synthesize_identity_report(self, state: InvestigationState) -> Any:
        """Synthesize final identity investigation findings into a structured, evidence-backed report."""
        from argus.specialists.identity.contract import (
            AccountClaimType,
            IdentityInvestigationReport,
        )
        from argus.specialists.outcome import SpecialistStatus, SpecialistOutcome

        contract = state.objective_contract or {}
        username = contract.get("username") or (contract.get("target_entities") or [""])[0] or state.objective
        starting_platform = contract.get("starting_platform") or "unknown"

        sources_queried: list[str] = []
        starting_account_resolved = False
        starting_account_profile = None
        outcome = SpecialistOutcome.SUCCESS_EMPTY

        identity_outcomes = []
        for inv in state.specialist_invocations:
            for s in inv.get("sources_queried", []):
                if s not in sources_queried:
                    sources_queried.append(s)
            if inv.get("specialist") == "identity" and inv.get("outcome"):
                try:
                    identity_outcomes.append(SpecialistOutcome(inv.get("outcome")))
                except ValueError:
                    pass

        for obs in state.observations:
            ad_res = obs.get("adapter_result") or {}
            for s in ad_res.get("sources_queried", []):
                if s not in sources_queried:
                    sources_queried.append(s)
            sa = ad_res.get("starting_account")
            if sa:
                starting_account_resolved = True
                starting_account_profile = sa.get("raw_profile_data")
            if obs.get("specialist") == "identity" and ad_res.get("outcome"):
                try:
                    identity_outcomes.append(SpecialistOutcome(ad_res.get("outcome")))
                except ValueError:
                    pass

        if identity_outcomes:
            for cand_out in (
                SpecialistOutcome.SUCCESS_WITH_RESULTS,
                SpecialistOutcome.PARTIAL_SUCCESS,
                SpecialistOutcome.SOURCE_ERROR,
                SpecialistOutcome.SOURCE_UNAVAILABLE,
                SpecialistOutcome.TIMEOUT,
                SpecialistOutcome.SUCCESS_EMPTY,
            ):
                if cand_out in identity_outcomes:
                    outcome = cand_out
                    break
            else:
                outcome = identity_outcomes[-1]

        candidate_links = []
        for c in state.claims:
            pred = c.get("predicate", "")
            if pred in (AccountClaimType.IDENTITY_EQUIVALENCE.value, "candidate_profile", "candidate_identity_link"):
                candidate_links.append({
                    "subject": c.get("subject"),
                    "link_description": c.get("object"),
                    "status": c.get("status"),
                    "source_url": c.get("source_url"),
                    "rationale": c.get("object") or "Candidate profile correlation hypothesis",
                })

        account_existence_claims = [
            c for c in state.claims
            if c.get("predicate") in (AccountClaimType.ACCOUNT_EXISTENCE.value, "account_exists")
        ]
        identity_equivalence_claims = [
            c for c in state.claims
            if c.get("predicate") in (AccountClaimType.IDENTITY_EQUIVALENCE.value, "candidate_profile", "candidate_identity_link")
        ]
        private_content_access_claims = [
            c for c in state.claims
            if c.get("predicate") in (AccountClaimType.PRIVATE_CONTENT_ACCESS.value, "private_content_access")
        ]

        source_failures = []
        for audit in state.audit_trail:
            if "FAIL" in audit.action_type or "TIMEOUT" in audit.action_type or "UNAVAILABLE" in audit.action_type:
                source_failures.append({
                    "action_type": audit.action_type,
                    "details": audit.details,
                    "rationale": audit.rationale,
                })
        for inv in state.specialist_invocations:
            for e in inv.get("errors", []):
                if "404" not in e.lower() and "limitation:" not in e.lower():
                    source_failures.append({"source": inv.get("specialist"), "error": e})

        platforms_queried = 0
        platforms_skipped = 0
        platforms_available = 0
        for obs in state.observations:
            ad_res = obs.get("adapter_result") or {}
            if "platforms_queried" in ad_res:
                platforms_queried = max(platforms_queried, ad_res.get("platforms_queried", 0))
            if "platforms_skipped" in ad_res:
                platforms_skipped = max(platforms_skipped, ad_res.get("platforms_skipped", 0))
            if "platforms_available" in ad_res:
                platforms_available = max(platforms_available, ad_res.get("platforms_available", 0))

        coverage_gaps = [
            gap.description for gap in state.information_gaps if not gap.is_resolved
        ]

        unresolved = [
            state.questions[qid]
            for qid in state.unresolved_questions
            if qid in state.questions
        ]

        return IdentityInvestigationReport(
            investigation_id=state.investigation_id,
            starting_identifier=username,
            starting_platform=starting_platform,
            starting_account_resolved=starting_account_resolved,
            starting_account_profile=starting_account_profile,
            sources_queried=sources_queried,
            findings=list(state.claims),
            supporting_evidence=list(state.evidence),
            candidate_identity_links=candidate_links,
            contradictory_evidence=list(state.contradictions),
            source_failures=source_failures,
            coverage_gaps=coverage_gaps,
            unresolved_questions=unresolved,
            outcome=outcome,
            platforms_queried=platforms_queried,
            platforms_skipped=platforms_skipped,
            platforms_available=platforms_available,
            account_existence_claims=account_existence_claims,
            identity_equivalence_claims=identity_equivalence_claims,
            private_content_access_claims=private_content_access_claims,
            epistemic_status=state.final_epistemic_status,
            stopping_rationale=state.stop_state.stopping_rationale,
            steps_taken=state.research_budget.get("steps_taken", 0),
            created_at=state.created_at,
        )

    def investigate_identity(
        self,
        username: str,
        starting_platform: str = "github",
        context: dict[str, Any] | None = None,
        max_steps: int = 10,
    ) -> Any:
        """Execute end-to-end identity investigation vertical slice."""
        contract = {
            "domain_hint": "identity",
            "target_entities": [username],
            "username": username,
            "starting_platform": starting_platform,
            "known_context": context or {},
            "max_steps": max_steps,
        }
        objective = f"Investigate username '{username}' starting from platform '{starting_platform}' and resolve cross-platform public-source evidence."
        state = self.run_to_completion(objective=objective, contract=contract, max_steps=max_steps)
        return self.synthesize_identity_report(state)

    # -------------------------------------------------------------------------
    # Internal Dispatch & Execution
    # -------------------------------------------------------------------------
    def _record_retrieval_denials(
        self,
        state: InvestigationState,
        action: ResearchAction,
        obs: dict[str, Any],
        records_before: int,
    ) -> None:
        """Surface requests the retriever refused or failed during this action.

        The live retriever logs budget/policy denials and fetch errors in its own
        ``evidence_records`` and returns nothing; without this the loop and the report
        cannot tell "not retrieved" from "no evidence exists".
        """
        records = getattr(self.corpus, "evidence_records", None)
        if not isinstance(records, list):
            return
        start = records_before if records_before <= len(records) else 0
        denials = []
        for rec in records[start:]:
            err = getattr(rec, "retrieval_error", None) if not isinstance(rec, dict) else rec.get("retrieval_error")
            if not err:
                continue
            get = rec.get if isinstance(rec, dict) else (lambda k, r=rec: getattr(r, k, None))
            denials.append({
                "action_id": action.action_id,
                "question_id": action.question_id,
                "query": action.query,
                "url": get("original_url"),
                "domain": get("domain"),
                "http_status": get("http_status"),
                "reason": err,
                "step": state.research_budget.get("steps_taken", 0),
            })
        if not denials:
            return
        # Candidate pages the site's robots.txt (already fetched) rules out are not
        # queued for retrieval: each would spend a research step on a known refusal.
        known_blocked = getattr(self.corpus, "is_known_blocked", None)
        if callable(known_blocked):
            for src in getattr(state, "discovered_sources", []) or []:
                if src.get("status") == "DISCOVERED" and src.get("url") and known_blocked(src["url"]):
                    src["status"] = "BLOCKED_BY_ROBOTS"
        state.retrieval_denials.extend(denials)
        obs["retrieval_denials"] = denials
        if not obs.get("documents"):
            obs["outcome"] = "RETRIEVAL_DENIED"
        for d in denials:
            state.record_audit(
                action_type="RETRIEVAL_DENIED",
                details={k: d[k] for k in ("query", "url", "http_status", "reason")},
                rationale=f"Retriever did not return content for '{d['query'] or d['url']}': {d['reason']}",
            )

    def _dispatch_action(self, action: ResearchAction, state: InvestigationState) -> dict[str, Any]:
        """Dispatch action to appropriate specialist or generalist search engine."""
        # Enforce deterministic application-level tool permission gate
        is_auth, rejection_reason = ToolPermissionGate.authorize_action(action, state)
        if not is_auth:
            logger.warning("ToolPermissionGate REJECTED action %s: %s", action.action_id, rejection_reason)
            state.record_audit(
                action_type="SECURITY_POLICY_VIOLATION",
                details={
                    "action_id": action.action_id,
                    "specialist": action.specialist,
                    "implementation_id": action.implementation_id,
                    "query": action.query,
                    "reason": rejection_reason,
                },
                rationale="Deterministic application-level tool permission gate blocked unauthorized execution.",
            )
            action.status = "REJECTED_UNAUTHORIZED"
            return {
                "observation_id": f"obs_unauth_{uuid.uuid4().hex[:8]}",
                "action_id": action.action_id,
                "query": action.query,
                "specialist": action.specialist,
                "documents": [],
                "text_content": "",
                "status": "REJECTED_UNAUTHORIZED",
                "rejection_reason": rejection_reason,
                "is_authoritative": False,
            }

        q_str = action.query or state.objective
        spec = action.specialist or "none"
        start_t = time.perf_counter()

        retrieved_docs: list[Any] = []
        specialist_result: dict[str, Any] = {}

        # Capability Adapter & Specialist Execution
        adapter = None
        impl_id = action.implementation_id
        if not impl_id and action.capability_id and hasattr(self, "registry") and self.registry:
            cap_def = self.registry.get(action.capability_id)
            if cap_def and cap_def.implementation_id:
                impl_id = cap_def.implementation_id

        if not impl_id and spec:
            specialist_impl_map = {
                "corporate": "impl_corporate_registry_specialist_v1",
                "infrastructure": "impl_infrastructure_probe_specialist_v1",
                "identity": "impl_identity_probe_specialist_v1",
            }
            impl_id = specialist_impl_map.get(spec)

        if action.action_type == ActionType.FETCH:
            adapter = None
        elif spec == "identity" and getattr(self, "identity_specialist", None):
            from argus.capability_registry.adapters import IdentitySpecialistAdapter
            adapter = IdentitySpecialistAdapter(specialist=self.identity_specialist)
        elif impl_id:
            try:
                adapter = get_adapter_for_implementation(impl_id, simulated=self.simulated_registries)
            except KeyError:
                adapter = None

        adapter_res = None
        if adapter:
            if not action.implementation_id and impl_id:
                temp_act = action.model_copy()
                temp_act.implementation_id = impl_id
                auth_ok, auth_err = ToolPermissionGate.authorize_action(temp_act, state)
                if not auth_ok:
                    logger.warning("ToolPermissionGate REJECTED resolved implementation %s: %s", impl_id, auth_err)
                    state.record_audit(
                        action_type="SECURITY_POLICY_VIOLATION",
                        details={"capability_id": action.capability_id, "implementation_id": impl_id, "reason": auth_err},
                        rationale="Tool permission gate blocked execution of unauthorized resolved implementation.",
                    )
                    action.status = "REJECTED_UNAUTHORIZED"
                    return {
                        "observation_id": f"obs_unauth_{uuid.uuid4().hex[:8]}",
                        "action_id": action.action_id,
                        "query": q_str,
                        "specialist": spec,
                        "documents": [],
                        "text_content": "",
                        "status": "REJECTED_UNAUTHORIZED",
                        "rejection_reason": auth_err,
                        "is_authoritative": False,
                    }
            try:
                adapter_inputs = {
                    "query": q_str,
                    "company_name": q_str,
                    "entity_name": q_str,
                    "target_domain": q_str,
                    "identifier": q_str,
                    "as_of_date": getattr(state, "as_of_date", None) or (state.objective_contract.get("as_of_date") if hasattr(state, "objective_contract") else None),
                    "limit": 3,
                    "timeout_sec": 5.0,
                }
                if getattr(action, "parameters", None):
                    adapter_inputs.update(action.parameters)

                adapter_res = adapter.execute(adapter_inputs, corpus=self.corpus)
                raw_outcome = adapter_res.get("outcome")
                raw_status = str(adapter_res.get("status", ""))
                if raw_outcome == "TIMEOUT" or (raw_status == "TIMEOUT" and raw_outcome not in ("SOURCE_UNAVAILABLE", "SOURCE_ERROR")):
                    raise concurrent.futures.TimeoutError(adapter_res.get("error", f"Specialist {impl_id} timed out."))
                elif raw_status == "FAILED" and raw_outcome not in ("SOURCE_UNAVAILABLE", "SOURCE_ERROR", "TIMEOUT"):
                    raise RuntimeError(adapter_res.get("error", f"Specialist {impl_id} failed."))

                state.specialist_invocations.append({
                    "specialist": spec,
                    "capability_id": action.capability_id or impl_id,
                    "implementation_id": impl_id,
                    "query": q_str,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "status": adapter_res.get("status", "SUCCESS"),
                    "outcome": adapter_res.get("outcome"),
                    "errors": adapter_res.get("errors", []),
                    "sources_queried": adapter_res.get("sources_queried", []),
                })
            except (concurrent.futures.TimeoutError, TimeoutError) as te:
                logger.warning("Adapter %s execution timed out: %s", impl_id, te)
                action.mark_failed(f"Adapter execution timeout: {te}")
                state.record_audit(
                    action_type="SPECIALIST_EXECUTION_TIMEOUT",
                    details={"error": str(te), "implementation_id": impl_id},
                    rationale="Capability specialist execution exceeded timeout threshold.",
                )
                state.record_audit(
                    action_type="ADAPTER_EXECUTION_FAILED",
                    details={"error": str(te), "implementation_id": impl_id},
                    rationale="Capability specialist execution exceeded timeout threshold.",
                )
                return {
                    "observation_id": f"obs_timeout_{uuid.uuid4().hex[:8]}",
                    "action_id": action.action_id,
                    "query": q_str,
                    "specialist": spec,
                    "documents": [],
                    "text_content": "",
                    "status": SpecialistStatus("TIMEOUT"),
                    "outcome": "TIMEOUT",
                    "error": str(te),
                    "is_authoritative": False,
                }
            except Exception as e:
                logger.warning("Adapter %s execution failed: %s", impl_id, e)
                action.mark_failed(f"Adapter execution exception: {e}")
                state.record_audit(
                    action_type="ADAPTER_EXECUTION_FAILED",
                    details={"error": str(e), "implementation_id": impl_id},
                    rationale="Capability adapter raised runtime exception during execution.",
                )
                return {
                    "observation_id": f"obs_failed_{uuid.uuid4().hex[:8]}",
                    "action_id": action.action_id,
                    "query": q_str,
                    "specialist": spec,
                    "documents": [],
                    "text_content": "",
                    "status": "FAILED",
                    "error": str(e),
                    "is_authoritative": False,
                }
        elif spec == "corporate":
            docs = self.corpus.search(q_str, limit=3)
            retrieved_docs.extend(docs)
            state.specialist_invocations.append({
                "specialist": "corporate",
                "capability_id": action.capability_id or "corporate_registry_intelligence",
                "implementation_id": action.implementation_id or "impl_corporate_registry_specialist_v1",
                "query": q_str,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        elif spec == "infrastructure":
            docs = self.corpus.search(q_str, limit=3)
            retrieved_docs.extend(docs)
            state.specialist_invocations.append({
                "specialist": "infrastructure",
                "capability_id": action.capability_id or "infrastructure_discovery",
                "implementation_id": action.implementation_id or "impl_infrastructure_probe_specialist_v1",
                "query": q_str,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        elif spec == "identity":
            docs = self.corpus.search(q_str, limit=3)
            retrieved_docs.extend(docs)
            state.specialist_invocations.append({
                "specialist": "identity",
                "capability_id": action.capability_id or "identity_resolution",
                "implementation_id": action.implementation_id or "impl_identity_probe_specialist_v1",
                "query": q_str,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        elif action.action_type == ActionType.FETCH:
            target_url = (action.parameters.get("url") if action.parameters else None) or q_str
            fetched_doc = None
            if hasattr(self.corpus, "get_by_url"):
                fetched_doc = self.corpus.get_by_url(target_url)
            elif hasattr(self.corpus, "get_document"):
                fetched_doc = self.corpus.get_document(target_url)
            elif hasattr(self.corpus, "get_by_id"):
                fetched_doc = self.corpus.get_by_id(target_url)

            if not fetched_doc and hasattr(self.corpus, "documents") and isinstance(self.corpus.documents, dict):
                fetched_doc = self.corpus.documents.get(target_url)
                if not fetched_doc:
                    for d in self.corpus.documents.values():
                        if getattr(d, "url", None) == target_url or getattr(d, "doc_id", None) == target_url:
                            fetched_doc = d
                            break

            if not fetched_doc and hasattr(self.corpus, "doc_by_id") and isinstance(self.corpus.doc_by_id, dict):
                fetched_doc = self.corpus.doc_by_id.get(target_url)

            if not fetched_doc and hasattr(self.corpus, "search"):
                # A text search on the URL returns the best-scoring document, which can be any
                # page; only a document actually at the requested address counts as fetched.
                matches = self.corpus.search(target_url, limit=3)
                fetched_doc = next(
                    (m for m in matches if getattr(m, "url", None) == target_url or getattr(m, "doc_id", None) == target_url),
                    None,
                )

            if fetched_doc:
                retrieved_docs.append(fetched_doc)
            else:
                action.mark_failed(f"Source '{target_url}' could not be retrieved from corpus or network.")
                return {
                    "observation_id": f"obs_unavail_{uuid.uuid4().hex[:8]}",
                    "action_id": action.action_id,
                    "query": q_str,
                    "specialist": spec,
                    "documents_count": 0,
                    "documents": [],
                    "combined_text": "",
                    "runtime_sec": time.perf_counter() - start_t,
                    "tokens": 0,
                    "cost_usd": 0.0,
                    "status": "SOURCE_UNAVAILABLE",
                    "outcome": "SOURCE_UNAVAILABLE",
                    "error": f"Source at '{target_url}' was unavailable or inaccessible.",
                    "is_authoritative": False,
                }
        elif spec in ("none", "") or action.action_type == ActionType.SEARCH:
            docs = self.corpus.search(q_str, limit=3) if hasattr(self.corpus, "search") else []
            retrieved_docs.extend(docs)
        else:
            # Capability requested has no executable adapter; fail closed with explicit limitation
            logger.warning("Unsupported capability requested: %s (specialist: %s)", action.capability_id, spec)
            action.mark_failed(f"Capability '{action.capability_id or spec}' is unsupported or unregistered.")
            state.record_audit(
                action_type="UNSUPPORTED_CAPABILITY_REQUESTED",
                details={"capability_id": action.capability_id, "specialist": spec, "action_id": action.action_id},
                rationale="Task requested an unsupported or unregistered capability; failing closed with explicit limitation.",
            )
            state.information_gaps.append(
                InformationGap(
                    description=f"Unsupported capability: {action.capability_id or spec}",
                    target_entity=action.target_entities[0] if action.target_entities else None,
                    target_attribute="unsupported_capability",
                    priority=1.0,
                    is_critical=True,
                    related_question_id=action.question_id,
                )
            )
            return {
                "observation_id": f"obs_unsupported_{uuid.uuid4().hex[:8]}",
                "action_id": action.action_id,
                "query": q_str,
                "specialist": spec,
                "documents": [],
                "text_content": "",
                "status": "UNSUPPORTED_CAPABILITY",
                "error": f"Capability '{action.capability_id or spec}' is unsupported or unregistered in current environment.",
                "is_authoritative": False,
            }

        elapsed = time.perf_counter() - start_t
        is_fetch_action = (action.action_type == ActionType.FETCH)
        all_docs = [
            {
                "doc_id": d.doc_id,
                "title": d.title,
                "url": d.url,
                "text": d.text_content,
                "source_type": d.source_type,
                "syndication_cluster_id": getattr(d, "syndication_cluster_id", None),
                "published_date": getattr(d, "published_date", None),
                "is_full_content": is_fetch_action or getattr(d, "is_full_content", False),
                "source_status": "RETRIEVED" if is_fetch_action else "DISCOVERED",
            }
            for d in retrieved_docs
        ]

        if adapter_res and "documents" in adapter_res:
            for ad in adapter_res["documents"]:
                # Defuse prompt injections and enforce unprivileged boundary
                raw_title = ad.get("title", "Candidate Document")
                raw_text = ad.get("text", "")
                clean_title = SecurityGateValidator.sanitize_text(str(raw_title))
                clean_text = SecurityGateValidator.sanitize_text(str(raw_text))
                raw_payload = ad.get("payload")
                clean_payload = (
                    SecurityGateValidator.sanitize_candidate_observation(raw_payload)
                    if isinstance(raw_payload, dict)
                    else raw_payload
                )
                all_docs.append({
                    "doc_id": ad.get("doc_id", "doc_adapter"),
                    "title": clean_title,
                    "url": ad.get("url", ""),
                    "text": clean_text,
                    "source_type": ad.get("source_type", "candidate_observation"),
                    "syndication_cluster_id": None,
                    "payload": clean_payload,
                    "epistemic_status": ad.get("epistemic_status", "OBSERVATION"),
                    "is_authoritative": False,  # Strict epistemic boundary: Candidate observations can NEVER claim authoritativeness
                })

        # Deduplicate all_docs by unique identifier (URL, doc_id, or text) to prevent double processing
        seen_keys = set()
        deduped_docs = []
        for d in all_docs:
            k = d.get("url") or d.get("doc_id") or d.get("title") or d.get("text")
            if k and k in seen_keys:
                continue
            if k:
                seen_keys.add(k)
            deduped_docs.append(d)
        all_docs = deduped_docs

        text_snippets = [f"{d.get('title', '')} {d.get('text', '')}" for d in all_docs]
        text_content = " ".join(text_snippets)

        return {
            "observation_id": f"obs_{uuid.uuid4().hex[:8]}",
            "action_id": action.action_id,
            "query": q_str,
            "specialist": spec,
            "documents_count": len(all_docs),
            "documents": all_docs,
            "combined_text": text_content,
            "runtime_sec": elapsed,
            "tokens": len(text_content.split()) * 2,
            "cost_usd": 0.001,
            "status": "SUCCESS",
            "adapter_result": adapter_res,
        }

    # -------------------------------------------------------------------------
    # Belief State Update & Multi-Specialist Chaining
    # -------------------------------------------------------------------------
    def _apply_observation(
        self,
        state: InvestigationState,
        action: ResearchAction,
        observation: dict[str, Any],
    ) -> float:
        """Process observation, update knowledge, resolve questions, and trigger chaining."""
        status = observation.get("status")
        if status in ("UNSUPPORTED_CAPABILITY", "FAILED", "REJECTED_UNAUTHORIZED"):
            if action and action.question_id and action.question_id in state.questions:
                q_dict = state.questions[action.question_id]
                q = InvestigationQuestion.model_validate(q_dict)
                err_msg = observation.get("error") or observation.get("rejection_reason") or status
                # Crucial epistemic integrity:
                # An action failure, unsupported capability, or authorization rejection means
                # the target question remains UNRESOLVED. It must NOT be added to resolved_questions
                # or removed from unresolved_questions, preventing artificial confidence inflation
                # or false OBJECTIVE_SATISFIED termination.
                q.status = QuestionStatus.NOT_FOUND
                q.resolution_reason = f"Action execution terminated with status FAILED ({status}): {err_msg}"
                state.questions[action.question_id] = q.model_dump()
            return 0.0

        docs = observation.get("documents", [])
        if not docs:
            return 0.0

        information_gain = 0.0
        new_entities_found: list[str] = []
        new_claims_found: list[str] = []
        # Existing claims that received another sighting in this observation.
        supported_claims_found: list[str] = []

        # 0. Specialized Identity Observation Processing
        is_ident_obs = (
            observation.get("specialist") == "identity"
            or (action and action.specialist == "identity")
            or (observation.get("adapter_result") and observation.get("adapter_result", {}).get("capability_id") == "identity_resolution")
        )
        if is_ident_obs:
            ad_res = observation.get("adapter_result") or {}
            for ent in ad_res.get("entities", []):
                state.register_entity(name=ent, entity_type="IDENTITY_HANDLE")

            known_ctx = state.objective_contract.get("known_context") or {}
            for claim_data in ad_res.get("claims", []):
                cand_obj = claim_data.get("object", "")
                has_bio_contra = False
                if known_ctx:
                    cand_low = cand_obj.lower()
                    loc_known = str(known_ctx.get("location", "")).lower()
                    prof_known = str(known_ctx.get("profession", "")).lower()
                    role_known = str(known_ctx.get("role", "")).lower()
                    target_prof = f"{prof_known} {role_known}".strip()

                    # Check location conflict
                    m_loc = re.search(r"(?:location|loc):\s*([^\n|]+)", cand_low)
                    cand_loc = m_loc.group(1).strip() if m_loc else ""
                    if loc_known and cand_loc:
                        known_loc_tokens = {t for t in re.findall(r"\w{3,}", loc_known) if t not in {"the", "and", "near"}}
                        cand_loc_tokens = {t for t in re.findall(r"\w{3,}", cand_loc) if t not in {"the", "and", "near"}}
                        if known_loc_tokens and cand_loc_tokens and known_loc_tokens.isdisjoint(cand_loc_tokens):
                            has_bio_contra = True

                    # Check profession/role conflict
                    m_bio = re.search(r"(?:bio|title|role|profession|career):\s*([^\n|]+)", cand_low)
                    cand_bio = m_bio.group(1).strip() if m_bio else ""
                    if target_prof and cand_bio:
                        known_prof_tokens = {t for t in re.findall(r"\w{3,}", target_prof) if t not in {"the", "and", "for", "with"}}
                        cand_bio_tokens = {t for t in re.findall(r"\w{3,}", cand_bio) if t not in {"the", "and", "for", "with"}}
                        if known_prof_tokens and cand_bio_tokens and known_prof_tokens.isdisjoint(cand_bio_tokens):
                            has_bio_contra = True

                if has_bio_contra:
                    claim_data["status"] = "CONTRADICTED"
                    contra_rec = {
                        "contradiction_id": f"contra_{uuid.uuid4().hex[:8]}",
                        "field": "biographical_context",
                        "subject": claim_data.get("subject"),
                        "known_value": str(known_ctx),
                        "observed_value": cand_obj,
                        "status": "CONTRADICTED",
                        "source_url": claim_data.get("source_url"),
                        "rationale": f"Biographical conflict: candidate profile ({cand_obj[:120]}) contradicts target known context ({known_ctx})",
                    }
                    state.contradictions.append(contra_rec)
                    state.record_audit(
                        action_type="IDENTITY_CONTRADICTION_DETECTED",
                        details=contra_rec,
                        rationale="Candidate profile contradicts target known biographical context.",
                    )
                elif known_ctx and any(
                    k.lower() in cand_obj.lower()
                    for k in [
                        str(known_ctx.get("profession", "")),
                        str(known_ctx.get("company", "")),
                        str(known_ctx.get("role", "")),
                        str(known_ctx.get("location", "")),
                    ] + [str(p) for p in known_ctx.get("known_projects", [])]
                    if len(k) > 3
                ):
                    if claim_data.get("predicate") in ("candidate_profile", "IDENTITY_EQUIVALENCE"):
                        claim_data["status"] = "SUPPORTED"

                # Cite the observation retrieved from the claim's own URL (never another document).
                if not claim_data.get("evidence_id") and claim_data.get("source_url"):
                    src_doc = next((d for d in docs if d.get("url") == claim_data.get("source_url")), None)
                    if src_doc is not None:
                        src_doc["evidence_id"] = state.add_evidence({
                            "url": src_doc["url"],
                            "source_type": src_doc.get("source_type"),
                            "title": src_doc.get("title"),
                            "snippet": src_doc.get("text", ""),
                            "published_date": src_doc.get("published_date"),
                            "syndication_cluster_id": src_doc.get("syndication_cluster_id"),
                        })
                        claim_data["evidence_id"] = src_doc["evidence_id"]
                        if claim_data.get("predicate") in ("ACCOUNT_EXISTENCE", "account_exists", "candidate_profile"):
                            # An account (candidate) profile is shown by the observation retrieved from that URL.
                            claim_data["grounding_scope"] = "resource"
                            claim_data.setdefault("source_passage", src_doc.get("text", ""))

                cid = state.add_claim(claim_data)
                new_claims_found.append(cid)
                information_gain += 0.35

            if ad_res.get("starting_account"):
                for gap in state.information_gaps:
                    if gap.target_attribute == "starting_account_profile":
                        gap.is_resolved = True
            if ad_res.get("entities"):
                for gap in state.information_gaps:
                    if gap.target_attribute == "cross_platform_candidates":
                        gap.is_resolved = True

        # 1. Evidence Extraction & Verification
        for d in docs:
            text = d["text"]
            ev_id = state.add_evidence({
                "url": d["url"],
                "source_type": d["source_type"],
                "title": d["title"],
                "snippet": text,
                "published_date": d.get("published_date"),
                "syndication_cluster_id": d.get("syndication_cluster_id"),
            })
            d["evidence_id"] = ev_id

            # Register discovered source into state lifecycle tracking
            src_url = d.get("url") or d.get("doc_id")
            if src_url:
                is_ret = d.get("is_full_content", False) or bool(action and action.action_type == ActionType.FETCH)
                state.add_discovered_source(
                    url=src_url,
                    title=d.get("title", ""),
                    snippet=text[:300],
                    is_retrieved=is_ret,
                    source_type=d.get("source_type", "web"),
                    target_entity=action.target_entities[0] if (action and action.target_entities) else None,
                )
                if is_ret:
                    state.mark_source_retrieved(src_url)

            # Check syndicated duplicates
            if d.get("syndication_cluster_id"):
                state.record_audit(
                    action_type="SYNDICATED_SOURCE_RECORDED",
                    details={"url": d["url"], "cluster": d["syndication_cluster_id"]},
                    rationale="Recorded syndicated mirror under origin cluster ID.",
                )

        # Let retrieved sources qualify the objective's object (e.g. the vendor name).
        self.planner.refine_objective_from_evidence(state)

        # Objective-scoped extraction: an objective that declares the dimensions it
        # needs runs only those extractors; other objectives keep the full extractor set.
        enum_dict = state.objective_contract.get("enumeration_objective")
        enum_objective = EnumerationObjective.from_dict(enum_dict) if enum_dict else None
        extraction_scope = set(enum_objective.extraction_scope) if enum_objective else None
        if extraction_scope is None and getattr(self.corpus, "is_live_web", False):
            # The labelled-field extractors ("CEO: ...", "Subsidiaries: ...", "BIOGRAPHY:", hostnames,
            # dated "as of" notes) were written for the labelled benchmark corpora. On real web pages
            # they attach whatever they match to the action's target entity, e.g. a list of UK firms'
            # CEOs became "officers of SAP ERP". Live runs use the sentence-level extractors, which
            # take the subject from the sentence itself, and the evidence gate.
            extraction_scope = {"target_sentences", "deployment", "chaining"}

        def in_scope(dimension: str) -> bool:
            return extraction_scope is None or dimension in extraction_scope

        def get_best_evidence_for_pattern(pat_regex: str) -> dict[str, Any]:
            for d in docs:
                if re.search(pat_regex, d.get("text", ""), re.IGNORECASE):
                    return d
            return {}

        def match_entity_in_text(ent_name: str, text: str) -> bool:
            """Robust boundary-aware entity matching supporting unicode, hyphens, punctuation, acronyms, and short names."""
            if not ent_name or not text:
                return False
            ent = ent_name.strip()
            if not ent:
                return False
            # For short names (<= 2 chars like 'Io', 'AI'), require case-sensitive token match
            # to strictly prevent matching substrings inside words like 'navigation', 'action', or 'onion'
            if len(ent) <= 2:
                pat_short = rf'(?:^|[\s\(\[\{{"\'`.,;:!?/\\<>\-—–])({re.escape(ent)})(?:$|[\s\)\]\}}\"\'`.,;:!?/\\<>\-—–])'
                return bool(re.search(pat_short, text))
            # General boundary match
            pattern = rf'(?:^|[\s\(\[\{{"\'`.,;:!?/\\<>\-—–])({re.escape(ent)})(?:$|[\s\)\]\}}\"\'`.,;:!?/\\<>\-—–])'
            if re.search(pattern, text, re.IGNORECASE):
                return True
            if any(ch in ent for ch in "-.+_/'"):
                tokens = ent.split()
                if len(tokens) == 1:
                    pat_strict = rf'(?:^|\s|[\(\[\{{"\'`.,;:!?/\\<>])({re.escape(ent)})(?:$|\s|[\)\]\}}\"\'`.,;:!?/\\<>])'
                    return bool(re.search(pat_strict, text, re.IGNORECASE))
            # Multi-token entity distinctive token match
            ent_tokens = [
                t for t in re.split(r"[\s\-_]+", ent)
                if len(t) > 3 and t.lower() not in {"battle", "department", "division", "project", "event", "conference"}
            ]
            if len(ent_tokens) >= 1:
                pat_tokens = [
                    rf'(?:^|[\s\(\[\{{"\'`.,;:!?/\\<>\-—–])({re.escape(t)})(?:$|[\s\)\]\}}\"\'`.,;:!?/\\<>\-—–])'
                    for t in ent_tokens
                ]
                if all(re.search(p, text, re.IGNORECASE) for p in pat_tokens):
                    return True
            return False

        def get_best_evidence_for_name(name_str: str) -> dict[str, Any]:
            for d in docs:
                if match_entity_in_text(name_str, d.get("text", "")):
                    return d
            return {}

        def cite_passage(*terms: str) -> tuple[dict[str, Any], str]:
            """Find the document and verbatim passage that mention all terms.

            Falls back to the first document mentioning the first term (with an
            empty passage) so the verification gate can reject the claim rather
            than borrowing an unrelated document's text.
            """
            terms_l = [t for t in terms if t]
            for d in docs:
                passage = ground_passage(d.get("text", ""), terms_l)
                if passage:
                    return d, passage
            if terms_l:
                for d in docs:
                    if match_entity_in_text(terms_l[0], d.get("text", "")):
                        return d, ground_passage(d.get("text", ""), terms_l[:1])
            return {}, ""

        def extract_sentence_for_entity(doc_text: str, ent_name: str) -> str:
            raw_sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", doc_text) if s.strip()]
            sentences: list[str] = []
            for s in raw_sentences:
                if sentences and re.search(r"\b(Dr|Mr|Ms|Prof|Sr|Jr|U\.S|vs)\.$", sentences[-1]):
                    sentences[-1] = sentences[-1] + " " + s
                else:
                    sentences.append(s)
            matching = [s for s in sentences if match_entity_in_text(ent_name, s)]
            return matching[0] if matching else ""

        def extract_grounded_claim_for_sentence(
            entity: str,
            sentence: str,
            doc: dict[str, Any],
        ) -> dict[str, Any] | None:
            """Extract a grounded claim only when the passage provides substantive predication."""
            if not sentence or not entity:
                return None
            s_clean = sentence.strip()
            if len(s_clean) < 15:
                return None

            contra_markers = [
                "contradict", "conflict", "dispute", "incompatible", "opposing",
                "differing", "discrepancy", "refute", "refuted", "refutes",
                "disprove", "disproved", "disproven", "retracted", "debunked",
                "debunk", "untrue", "denied", "contrary to", "inconsistent",
            ]
            # A sentence saying earlier information is outdated resolves a conflict
            # rather than reporting an open one.
            if any(m in s_clean.lower() for m in contra_markers) and classify_sentence(s_clean) != "supersession":
                return {
                    "subject": entity,
                    "predicate": "conflict_noted",
                    "object": s_clean,
                    "status": "CONTRADICTED",
                    "evidence_id": doc.get("evidence_id"),
                    "source_url": doc.get("url"),
                    "source_passage": s_clean,
                }

            neg_markers = [
                "zero affiliation", "no affiliation", "unrelated", "not affiliated",
                "does not exist", "never granted", "never issued", "no division", "no record", "fictitious",
                "insufficient evidence", "null result", "failed to replicate", "unconfirmed",
                "inconclusive", "unsubstantiated", "failed peer review",
                "remain unproven", "unproven", "trade secret", "will not be disclosed",
                "preliminary", "alleged", "allegedly", "speculative", "speculates", "anecdotal",
                "unverified", "pending investigation", "cannot be confirmed", "rumored", "rumor",
                "doubtful", "open question", "unresolved", "not yet established", "insufficient data",
            ]
            if any(m in s_clean.lower() for m in neg_markers):
                st = "NOT_FOUND" if any(k in s_clean.lower() for k in ("affiliation", "unrelated", "not affiliated", "does not exist", "never granted", "never issued", "no division", "no record", "fictitious")) else "INSUFFICIENT_EVIDENCE"
                return {
                    "subject": entity,
                    "predicate": "investigation_finding",
                    "object": s_clean,
                    "status": st,
                    "evidence_id": doc.get("evidence_id"),
                    "source_url": doc.get("url"),
                    "source_passage": s_clean,
                }

            # Substantive verbs ensuring an actual factual assertion is present
            substantive_verbs = [
                "is", "was", "are", "were", "has", "have", "had", "operates", "developed", "founded", "acquired",
                "completed", "exhibits", "exhibited", "entered", "includes", "included",
                "demonstrated", "demonstrates", "published", "discovered", "reported", "appointed", "serves",
                "holds", "manages", "leads", "resigned", "succeeded", "measured", "calculated",
                "approved", "crossed", "implemented", "solved", "contains", "provides", "utilize", "utilizes",
                "achieves", "achieved", "features", "featured", "yields", "yielded", "maintains", "maintained",
                "reaches", "reached", "shows", "showed", "signed", "ceded", "established", "establishes",
                "ratified", "passed", "enacted", "manufactures", "manufactured", "deploys", "deployed",
                "records", "recorded", "identifies", "identified", "secures", "secured", "routes", "routed", "clusters", "registered", "registers"
            ]
            words = set(re.findall(r"\b\w+\b", s_clean.lower()))
            if not any(v in words for v in substantive_verbs):
                return None

            predicate = "finding"
            if any(w in words for w in ("ceo", "officer", "director", "president", "founder", "leads", "appointed", "serves")):
                predicate = "leadership_role"
            elif any(w in words for w in ("subsidiary", "acquired", "parent", "operates")):
                predicate = "corporate_structure"
            elif any(w in words for w in ("discovered", "demonstrated", "measured", "calculated", "published", "developed")):
                predicate = "scientific_finding"
            elif any(w in words for w in ("sanctioned", "sdn", "pep")):
                predicate = "regulatory_status"

            # Independent semantic audit before marking SUPPORTED
            audit_res = self.semantic_auditor.audit_claim(
                {"subject": entity, "object": s_clean, "predicate": predicate, "evidence_id": doc.get("evidence_id")},
                doc,
            )
            if audit_res.status == SemanticSupportStatus.CONTRADICTED:
                st = "CONTRADICTED"
                predicate = "conflict_noted"
            elif audit_res.status in (
                SemanticSupportStatus.INSUFFICIENTLY_SUPPORTED,
                SemanticSupportStatus.IRRELEVANT_EVIDENCE,
                SemanticSupportStatus.PARTIALLY_SUPPORTED_COMPOUND,
            ):
                st = "INSUFFICIENT_EVIDENCE"
                predicate = "investigation_finding"
            else:
                st = "SUPPORTED"

            return {
                "subject": entity,
                "predicate": predicate,
                "object": s_clean,
                "status": st,
                "evidence_id": doc.get("evidence_id"),
                "source_url": doc.get("url"),
                "source_passage": s_clean,
            }

        # 2. Extract grounded entities matching corpus vocabulary or specialist output
        all_text = observation.get("combined_text", "")
        if hasattr(self.corpus, "get_discoverable_entities"):
            discoverable = self.corpus.get_discoverable_entities()
            found_in_text = [
                ent for ent in discoverable
                if match_entity_in_text(ent, all_text)
            ]
            for ent in found_in_text:
                if ent not in state.entities:
                    state.register_entity(name=ent)
                    new_entities_found.append(ent)
                    information_gain += 0.25

                # Grounded factual claim extraction only if substantive predication exists
                # and executive schedule/bio handler does not have higher priority
                is_exec_goal = any(k in state.objective.lower() for k in ("executive", "leadership", "officer"))
                if not is_exec_goal:
                    for d in docs:
                        if match_entity_in_text(ent, d.get("text", "")):
                            if not any(c.get("subject") == ent and c.get("evidence_id") == d.get("evidence_id") for c in state.claims):
                                excerpt = extract_sentence_for_entity(d.get("text", ""), ent)
                                if excerpt:
                                    clm = extract_grounded_claim_for_sentence(ent, excerpt, d)
                                    if clm:
                                        cid = state.add_claim(clm)
                                        new_claims_found.append(cid)
                                        information_gain += 0.20

        # 2b. General Entity Extraction from target entities and adapter result
        adapter_res = observation.get("adapter_result")
        if isinstance(adapter_res, dict):
            for ent in adapter_res.get("entities", []):
                ent_name = ent.get("name") if isinstance(ent, dict) else str(ent)
                if ent_name and ent_name not in state.entities:
                    ent_type = ent.get("type", "ENTITY") if isinstance(ent, dict) else "ENTITY"
                    state.register_entity(name=ent_name, entity_type=ent_type)
                    new_entities_found.append(ent_name)
                    information_gain += 0.25

            for clm in adapter_res.get("claims", []) + adapter_res.get("findings", []):
                if isinstance(clm, dict):
                    if "evidence_id" not in clm and docs:
                        # Only the document the adapter actually cited; never docs[0].
                        matching_doc = next((d for d in docs if clm.get("source_url") and d.get("url") == clm.get("source_url")), None)
                        if matching_doc is not None:
                            clm["evidence_id"] = matching_doc.get("evidence_id")
                            if not clm.get("source_passage"):
                                clm["source_passage"] = ground_passage(
                                    matching_doc.get("text", ""),
                                    [str(clm.get("subject") or ""), str(clm.get("object") or "")],
                                )
                    cid = state.add_claim(clm)
                    new_claims_found.append(cid)
                    information_gain += 0.35
                elif isinstance(clm, str):
                    subj = action.target_entities[0] if (action and action.target_entities) else "Entity"
                    best_doc, passage = cite_passage(subj, clm)
                    cid = state.add_claim({
                        "subject": subj,
                        "predicate": "finding",
                        "object": clm,
                        "status": "SUPPORTED",
                        "evidence_id": best_doc.get("evidence_id"),
                        "source_url": best_doc.get("url"),
                        "source_passage": passage,
                    })
                    new_claims_found.append(cid)
                    information_gain += 0.35

        target_ents = (action.target_entities if action else []) or (state.objective_contract.get("target_entities") or []) or list(state.entities.keys())
        if target_ents and in_scope("target_sentences"):
            for ent in target_ents:
                if ent not in state.entities and (match_entity_in_text(ent, all_text) or not all_text):
                    state.register_entity(name=ent, entity_type="TARGET_ENTITY")
                    new_entities_found.append(ent)
                    information_gain += 0.20
                for d in docs:
                    if match_entity_in_text(ent, d.get("text", "")):
                        if not any(c.get("subject") == ent and c.get("evidence_id") == d.get("evidence_id") for c in state.claims):
                            excerpt = extract_sentence_for_entity(d.get("text", ""), ent)
                            if excerpt:
                                clm = extract_grounded_claim_for_sentence(ent, excerpt, d)
                                if clm:
                                    cid = state.add_claim(clm)
                                    new_claims_found.append(cid)
                                    information_gain += 0.20

        # 3. Dynamic Relational Claim Extraction & Knowledge Graph Update
        # Reusable semantic patterns extracting corporate structure, officers, infrastructure, and sanctions
        dynamic_relations: list[tuple[str, str, str, str]] = []

        # 3-0. Enterprise Technographic Deployment Intelligence
        # Extracts enterprise software deployments from live evidence passages and technographic telemetry.
        # Extraction runs per document only: a pass over concatenated documents can join text across
        # document boundaries and attribute the result to a document that never states it.
        # The product names come from the interpreted objective, never from a fixed list.
        deployment_products = enum_objective.object_names if (enum_objective and in_scope("deployment")) else []
        for d in docs:
            d_text = d.get("text", "")
            d_url = d.get("url", "")
            d_ev_id = d.get("evidence_id")
            if d_text and deployment_products:
                tech_findings = extract_technographic_deployments(
                    d_text,
                    doc_url=d_url,
                    products=deployment_products,
                    geography=enum_objective.geography,
                )
                for tf in tech_findings:
                    if tf.company not in state.entities:
                        state.register_entity(
                            name=tf.company,
                            entity_type="ORGANIZATION",
                            metadata={
                                "country": tf.country,
                                "industry": tf.industry,
                                "employees": tf.employees,
                                "revenue": tf.revenue,
                                "software": tf.software,
                                "source_type": tf.source_type,
                                "source_url": tf.source_url or d_url,
                                "qualifier": tf.qualifier,
                            },
                        )
                        new_entities_found.append(tf.company)
                        information_gain += 0.30
                    else:
                        ent_obj = state.entities[tf.company]
                        meta = getattr(ent_obj, "metadata", {}) or {}
                        if tf.country and not meta.get("country"):
                            meta["country"] = tf.country
                        if tf.industry and not meta.get("industry"):
                            meta["industry"] = tf.industry
                        if tf.employees and not meta.get("employees"):
                            meta["employees"] = tf.employees
                        if tf.revenue and not meta.get("revenue"):
                            meta["revenue"] = tf.revenue

                    pred = "USES_SOFTWARE"
                    candidate = {
                        "subject": tf.company,
                        "predicate": pred,
                        "object": tf.software,
                        "status": tf.status,
                        "evidence_id": d_ev_id,
                        "source_url": d_url,
                        "source_passage": tf.evidence_quote,
                        "country": tf.country,
                        "industry": tf.industry,
                        "employees": tf.employees,
                        "revenue": tf.revenue,
                        "source_type": tf.source_type,
                        "qualifier": tf.qualifier,
                    }
                    if tf.matched_alias and tf.matched_alias.lower() != tf.software.lower():
                        # The source names the product by an alias the objective established
                        # from evidence (e.g. "Teamcenter" for "Siemens Teamcenter").
                        candidate["grounding_terms"] = [tf.matched_alias]
                    existing_claim = next(
                        (c for c in state.claims if c.get("subject") == tf.company and c.get("predicate") == pred and c.get("object") == tf.software),
                        None,
                    )
                    if not existing_claim:
                        cid = state.add_claim(candidate)
                        new_claims_found.append(cid)
                        information_gain += 0.40
                    else:
                        # A repeat sighting is a candidate support; the shared gate
                        # decides whether it is an independent voice.
                        add_support(existing_claim, verify_claim(candidate, state.evidence))
                        if existing_claim.get("claim_id"):
                            supported_claims_found.append(existing_claim["claim_id"])

        # Incidental relation extractors (subsidiaries, officers, acquisitions, hosts,
        # e-mails, succession, sanctions, ownership) run only when the objective needs them.
        if in_scope("relations"):
            # A. Corporate Subsidiary Declarations
            m_subs_block = re.findall(r"(?:subsidiaries(?:\s+include)?|Subsidiaries held|Wholly owned subsidiaries):\s*([^\n\r]+)", all_text, re.IGNORECASE)
            for s_block in m_subs_block:
                parent_cand = action.target_entities[0] if (action and action.target_entities) else "Parent Organization"
                for sub_name in re.split(r"[,;]\s*", s_block):
                    sub_name_clean = sub_name.strip().rstrip(".")
                    if len(sub_name_clean) >= 3 and re.search(r"\b(?:Ltd|Limited|LLC|GmbH|Inc|Corp|Corporation|plc|PLC|AG|SA|S\.A|BV|B\.V|Pty|LLP|LP|Co)\b\.?", sub_name_clean):
                        dynamic_relations.append((sub_name_clean, parent_cand, "subsidiary", sub_name_clean))

            m_single_sub = re.finditer(
                r"(?:Technical Infrastructure Subsidiary|Wholly owned subsidiary|Active Subsidiary|Subsidiary):\s*([A-Z][A-Za-z0-9\s.,&-]{2,50}?)(?:\.|\n|;|$)",
                all_text,
                re.IGNORECASE,
            )
            for m_sub in m_single_sub:
                sub_cand = m_sub.group(1).strip()
                parent_cand = action.target_entities[0] if (action and action.target_entities) else "Parent Organization"
                if len(sub_cand) >= 3:
                    if sub_cand not in state.entities:
                        state.register_entity(sub_cand, "SUBSIDIARY", metadata={"context": m_sub.group(0)})
                        new_entities_found.append(sub_cand)
                    dynamic_relations.append((sub_cand, parent_cand, "subsidiary", sub_cand))

            # B. Corporate Officers & Leadership Titles
            m_officers = re.finditer(
                r"(?:Chief Executive Officer|Managing Director|Active Managing Director|Chief Technology Officer|CTO|CEO|President|General Counsel):\s*([A-Z][A-Za-z\s.'-]{2,40}?)(?:\.|\n|;|$)",
                all_text,
                re.IGNORECASE,
            )
            for m_off in m_officers:
                off_name = m_off.group(1).strip()
                org_cand = action.target_entities[0] if (action and action.target_entities) else "Corporate Entity"
                if len(off_name) >= 3 and " " in off_name:
                    dynamic_relations.append((off_name, org_cand, "officer", off_name))

            # C. Acquisitions
            m_acq = re.finditer(
                r"([A-Z][A-Za-z0-9\s.,&-]{2,40}?)\s+(?:completed acquisition of|acquired)\s+([A-Z][A-Za-z0-9\s.,&-]{2,40})",
                all_text,
            )
            for ma in m_acq:
                acquirer = ma.group(1).strip()
                target = ma.group(2).strip()
                dynamic_relations.append((target, acquirer, "acquired", target))

            # D. Infrastructure Hostnames & Associated Domain Entities
            found_hosts = re.findall(r"\b([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.(?:[a-z0-9-]+\.)+(?:com|org|net|de|co\.uk|io))\b", all_text)
            for host in set(found_hosts):
                # Check contextual relevance of host
                doc_urls = [d.get("url", "") for d in docs if host in d.get("text", "")]
                primary_doc_url = doc_urls[0] if doc_urls else ""
                if not is_contextually_relevant_host(
                    host,
                    doc_url=primary_doc_url,
                    target_objective=state.objective,
                    target_entities=list(state.entities.keys()),
                ):
                    continue

                if host not in state.entities:
                    state.register_entity(host, "INFRASTRUCTURE_ENDPOINT")
                    new_entities_found.append(host)
                for d in docs:
                    if host in d.get("text", ""):
                        org_cand = clean_entity_name(d.get("title", "").split(" - ")[0].split(":")[0].strip())
                        if not org_cand or len(org_cand) < 3:
                            org_cand = clean_entity_name(action.target_entities[0] if (action and action.target_entities) else "Host Entity")
                        dynamic_relations.append((host, org_cand, "infrastructure", host))

            # E. Admin / Contact Emails associated with domains
            found_emails = re.findall(r"\b([a-zA-Z0-9._%+-]+@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,}))\b", all_text)
            for full_email, email_dom in found_emails:
                dynamic_relations.append((full_email, email_dom, "admin_contact", full_email))
                # Match person whose surname is present in the email prefix
                email_user = full_email.split("@")[0].lower()
                all_known = list(state.entities.keys()) + list(self.corpus.get_discoverable_entities() if hasattr(self.corpus, "get_discoverable_entities") else [])
                for cand_p in all_known:
                    if " " in cand_p:
                        surname = cand_p.split()[-1].lower()
                        if len(surname) >= 4 and surname in email_user:
                            if cand_p not in state.entities:
                                state.register_entity(cand_p, "INDIVIDUAL")
                                new_entities_found.append(cand_p)

            # F. Corporate Succession & Historical Tenure
            m_succ = re.finditer(r"([A-Z][A-Za-z\s.'-]{2,30}?)\s+succeeded\s+([A-Z][A-Za-z\s.'-]{2,30})", all_text)
            for ms in m_succ:
                dynamic_relations.append((ms.group(2).strip(), ms.group(1).strip(), "succeeded", ms.group(2).strip()))

            m_res = re.finditer(r"([A-Z][A-Za-z\s.'-]{2,40}?)\s*(?:\b(?:has|had|have)\s+)?(?:\bRESIGNED\b|\bresigned\b|\bstepped down\b)(?:\s+(?:in\s+)?(\d{4}))?", all_text)
            for mr in m_res:
                res_person = person_name_from_span(mr.group(1))
                if len(res_person) >= 3:
                    dynamic_relations.append((res_person, res_person, "tenure_status", "HISTORICAL_RESIGNED"))

            # G. Regulatory Sanctions, OFAC / OFSI Designations
            m_sanc = re.finditer(r"([A-Z][A-Za-z0-9\s.,&-]{2,40}?)\s*(?:sanctioned by|placed on SDN list by|designated by|US_OFAC|UK_OFSI|OFAC_SDN_ENTRY|UK_OFSI_ENTRY)\s*(US_OFAC|UK_OFSI|OFAC_SDN_ENTRY|UK_OFSI_ENTRY|[A-Za-z0-9_\s-]+)?", all_text)
            for msn in m_sanc:
                sanc_ent = msn.group(1).strip()
                auth = (msn.group(2) or "SANCTIONS_REGULATOR").strip()
                if "OFAC" in all_text:
                    auth = "US_OFAC"
                elif "OFSI" in all_text:
                    auth = "UK_OFSI"
                dynamic_relations.append((sanc_ent, sanc_ent, "sanctioned_by", auth))

            # H. Beneficial Ownership & PEP Status
            m_bo = re.finditer(r"(?:beneficial_owners|beneficial owners?|controlling shareholder):\s*([A-Z][A-Za-z\s.'-]{2,40})", all_text, re.IGNORECASE)
            for mbo in m_bo:
                owner = mbo.group(1).strip()
                org_cand = action.target_entities[0] if (action and action.target_entities) else "Offshore Entity"
                dynamic_relations.append((owner, org_cand, "beneficial_owner", owner))

            m_pep = re.finditer(r"([A-Z][A-Za-z\s.'-]{2,30}?)\s*(?:POLITICALLY_EXPOSED_PERSON|Former Deputy Minister|politically exposed person)", all_text)
            for mp in m_pep:
                pep_name = mp.group(1).strip()
                if len(pep_name) >= 3:
                    dynamic_relations.append((pep_name, pep_name, "pep_status", "POLITICALLY_EXPOSED_PERSON"))

            # Coded objects (e.g. HISTORICAL_RESIGNED) are grounded by the cue the source actually states.
            relation_cues = {
                "tenure_status": ("resigned", "stepped down"),
                "pep_status": ("politically exposed person", "former deputy minister"),
                "sanctioned_by": ("sanctioned", "ofac", "ofsi", "sdn", "designated"),
            }
            for pat_str, s, p, o in dynamic_relations:
                existing = any(
                    r.get("subject") == s and r.get("predicate") == p and r.get("object") == o
                    for r in state.relationships
                )
                if not existing:
                    state.relationships.append({"subject": s, "predicate": p, "object": o})
                    grounding_terms = None
                    if p in relation_cues:
                        best_doc, passage = {}, ""
                        for cue in relation_cues[p]:
                            best_doc, passage = cite_passage(s, cue)
                            # cite_passage falls back to a passage naming only the
                            # subject; the cue must be in the passage it returns.
                            if passage and term_in_passage(cue, passage):
                                grounding_terms = [cue]
                                break
                        if not passage:
                            best_doc, passage = cite_passage(s)
                    else:
                        best_doc, passage = cite_passage(*([s] if s == o else [s, o]))
                    relation_claim = {
                        "subject": s,
                        "predicate": p,
                        "object": o,
                        "status": "SUPPORTED",
                        "evidence_id": best_doc.get("evidence_id"),
                        "source_url": best_doc.get("url"),
                        "source_passage": passage,
                    }
                    if grounding_terms:
                        relation_claim["grounding_terms"] = grounding_terms
                    cid = state.add_claim(relation_claim)
                    new_claims_found.append(cid)
                    information_gain += 0.35

        # 3b. Genuine Executive Officer & Leadership Extraction from Observed Evidence
        is_exec_goal = (
            state.objective_contract.get("expected_executive_count") is not None
            or any(k in state.objective.lower() for k in ("executive", "officer", "leadership"))
        )

        def extract_clean_email(raw_val: str) -> str | None:
            if not raw_val or any(k in raw_val.lower() for k in ("none disclosed", "not disclosed", "none")):
                return None
            m_email = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", raw_val)
            return m_email.group(0) if m_email else None

        extracted_executives: dict[str, dict[str, Any]] = {}

        # Determine target organization dynamically
        target_org = "Target Organization"
        if action and action.target_entities:
            target_org = action.target_entities[0]
        elif state.objective_contract.get("target_entities"):
            target_org = state.objective_contract["target_entities"][0]
        else:
            m_org = re.search(r"([A-Z][A-Za-z0-9\s&]+(?:Inc|Corp|Ltd|LLC|Group|GmbH|SE))", all_text)
            if m_org:
                target_org = m_org.group(1).strip()

        sec_sched_pattern = re.compile(
            r"^-\s*([^\n\r:()]+?):\s*([^()\n\r]+?)(?:\s*\(([^()\n\r]+?)\))?\.\s*(?:Public Contact|Contact):\s*(.*?)(?:\.\s*$|$)",
            re.MULTILINE,
        )
        for m in sec_sched_pattern.finditer(all_text):
            name = m.group(1).strip()
            title = m.group(2).strip()
            resp = (m.group(3) or "").strip()
            contact_raw = (m.group(4) or "").strip()
            if len(name) >= 3 and any(k in title for k in ("President", "Officer", "General Counsel", "Managing Director", "Executive", "Director")):
                email = extract_clean_email(contact_raw)
                extracted_executives[name] = {
                    "name": name,
                    "title": title,
                    "responsibility": resp or f"Executive duties as {title}",
                    "org": target_org,
                    "email": email,
                    "history": f"Executive tenure as {title}.",
                }

        bio_splits = list(re.finditer(r"(?:^|\n)BIOGRAPHY:\s*([^\n\r]+)", all_text))
        for i, b_match in enumerate(bio_splits):
            name = b_match.group(1).strip()
            start_pos = b_match.end()
            end_pos = bio_splits[i + 1].start() if i + 1 < len(bio_splits) else len(all_text)
            block_text = all_text[start_pos:end_pos]

            title_m = re.search(r"(?:^|\n)Title:\s*([^\n\r]+)", block_text)
            scope_m = re.search(r"(?:^|\n)(?:Scope|Responsibility):\s*([^\n\r]+)", block_text)
            hist_m = re.search(r"(?:^|\n)(?:Career History|History):\s*([^\n\r]+)", block_text)
            contact_m = re.search(r"(?:^|\n)(?:Business Inquiries|Public Contact|Contact):\s*([^\n\r]+)", block_text)

            title = title_m.group(1).strip() if title_m else ""
            resp = scope_m.group(1).strip() if scope_m else ""
            hist = hist_m.group(1).strip() if hist_m else ""
            contact_raw = contact_m.group(1).strip() if contact_m else ""
            email = extract_clean_email(contact_raw)

            if len(name) >= 3:
                existing = extracted_executives.get(name, {})
                extracted_executives[name] = {
                    "name": name,
                    "title": title or existing.get("title", "Executive Officer"),
                    "responsibility": resp or existing.get("responsibility", f"Executive scope as {title or 'Officer'}"),
                    "org": target_org,
                    "email": email if email is not None else existing.get("email"),
                    "history": hist or existing.get("history", f"Executive tenure as {title or 'Officer'}."),
                }

        if not in_scope("executives"):
            extracted_executives.clear()
        for ex_name, ex in extracted_executives.items():
            if ex_name not in state.entities:
                state.register_entity(name=ex_name, entity_type="EXECUTIVE_OFFICER", metadata=ex)
                new_entities_found.append(ex_name)
                information_gain += 0.20

            if not any(c.get("subject") == ex_name and c.get("predicate") == "title" for c in state.claims):
                # Each attribute cites the passage that states it; the gate rejects
                # attributes (e.g. defaulted responsibility text) that no source states.
                for ex_pred, ex_obj in (
                    ("title", ex["title"]),
                    ("organization", ex["org"]),
                    ("responsibility", ex["responsibility"]),
                    ("career_history", ex["history"]),
                ):
                    ex_doc, ex_pass = cite_passage(ex_name, ex_obj)
                    state.add_claim({"subject": ex_name, "predicate": ex_pred, "object": ex_obj, "status": "SUPPORTED", "evidence_id": ex_doc.get("evidence_id"), "source_url": ex_doc.get("url"), "source_passage": ex_pass})
                if ex["email"]:
                    ex_doc, ex_pass = cite_passage(ex_name, ex["email"])
                    state.add_claim({"subject": ex_name, "predicate": "contact_channel", "object": ex["email"], "status": "SUPPORTED", "evidence_id": ex_doc.get("evidence_id"), "source_url": ex_doc.get("url"), "source_passage": ex_pass})
                else:
                    ex_doc = get_best_evidence_for_name(ex_name)
                    state.add_claim({"subject": ex_name, "predicate": "contact_channel", "object": "NOT_FOUND", "status": "NOT_FOUND", "evidence_id": ex_doc.get("evidence_id"), "source_url": ex_doc.get("url"), "source_passage": extract_sentence_for_entity(ex_doc.get("text", ""), ex_name)})
                information_gain += 0.30

            if is_exec_goal:
                safe_slug = ex_name.lower().replace(" ", "_").replace(".", "").replace("'", "")
                branch_id = f"br_exec_{safe_slug}"
                if branch_id not in state.active_branches and branch_id not in state.completed_branches:
                    branch = InvestigationBranch(
                        branch_id=branch_id,
                        purpose=f"Executive Leadership Verification: {ex_name}",
                        target_entity=ex_name,
                        step_budget=5,
                    )
                    branch.complete()
                    state.completed_branches.append(branch_id)
                    state.record_audit(
                        action_type="BRANCH_COMPLETED",
                        details={"branch_id": branch_id, "executive": ex_name, "title": ex["title"]},
                        rationale=f"Successfully verified leadership dossier for {ex_name}.",
                    )

        # 3c. Domain-General Contradiction Detection & Multi-Domain Conflict Resolution
        topic_subject = action.target_entities[0] if (action and action.target_entities) else "Subject Matter"
        target_entities_list = (action.target_entities if action else []) or [topic_subject]
        all_candidate_subjects = list(
            dict.fromkeys(
                ((action.target_entities if action else []) or [])
                + (state.objective_contract.get("target_entities") or [])
                + [ent for ent in state.entities if any(match_entity_in_text(ent, d.get("text", "")) for d in docs)]
                + [topic_subject]
            )
        )

        # Use ContradictionResolver to extract comparable claims and detect cross-document conflicts
        for subj in all_candidate_subjects:
            comparable_claims = self.contradiction_resolver.extract_comparable_claims(docs, subj)
            detected_contras = self.contradiction_resolver.detect_contradictions(comparable_claims)
            for c_rec in detected_contras:
                already_recorded = any(
                    c.get("subject") == c_rec.subject
                    and c.get("property_dim") == c_rec.property_dim
                    for c in state.contradictions
                ) or any(c.get("topic") == c_rec.topic for c in state.contradictions)
                if not already_recorded:
                    state.contradictions.append(c_rec.model_dump())
                    claim_status = "CONTRADICTED" if c_rec.status == "UNRESOLVED_CONTRADICTION" else "SUPPORTED"
                    res_str = str(c_rec.resolved_value or "")
                    use_b = bool(res_str and res_str in str(c_rec.value_b or "") and c_rec.evidence_id_b)
                    ev_id = (c_rec.evidence_id_b if use_b else c_rec.evidence_id_a) or c_rec.evidence_id_a or c_rec.evidence_id_b
                    src_url = (c_rec.source_b if use_b else c_rec.source_a) or c_rec.source_a
                    src_pass = (c_rec.claim_b[:300] if use_b else c_rec.claim_a[:300]) or c_rec.claim_a[:300]
                    cid = state.add_claim({
                        "subject": c_rec.subject,
                        "predicate": f"metric_{c_rec.property_dim}",
                        "object": f"Resolved finding: {c_rec.resolved_value or c_rec.value_a} (Adjudication: {c_rec.adjudication_rationale})",
                        "status": claim_status,
                        "evidence_id": ev_id,
                        "source_url": src_url,
                        "source_passage": src_pass,
                        "grounding_terms": [str(c_rec.resolved_value or c_rec.value_a)],
                    })
                    new_claims_found.append(cid)
                    information_gain += 0.40

                    if c_rec.status == "UNRESOLVED_CONTRADICTION":
                        # Mark all existing claims for this subject and property dimension as CONTRADICTED
                        prop_tokens = {c_rec.property_dim.lower(), str(c_rec.value_a).lower(), str(c_rec.value_b).lower()}
                        for clm in state.claims:
                            if clm.get("subject") == c_rec.subject and clm.get("status") == "SUPPORTED":
                                clm_text = (clm.get("object", "") + " " + clm.get("predicate", "")).lower()
                                if any(tok in clm_text for tok in prop_tokens if len(tok) >= 2):
                                    clm["status"] = "CONTRADICTED"
                    elif c_rec.status.startswith("RESOLVED_"):
                        # Mark superseded conflicting claim as CONTRADICTED
                        res_str = str(c_rec.resolved_value or "")
                        a_str = str(c_rec.value_a or "")
                        b_str = str(c_rec.value_b or "")
                        rejected_val = b_str if res_str and res_str in a_str else a_str
                        rej_nums = re.findall(r"\d+(?:\.\d+)?", rejected_val)
                        rej_core = rej_nums[0].rstrip(".0") if rej_nums else rejected_val.lower()
                        for clm in state.claims:
                            if clm.get("subject") == c_rec.subject and clm.get("status") == "SUPPORTED":
                                clm_text = (clm.get("object", "") + " " + clm.get("predicate", "")).lower()
                                if rej_core and rej_core in clm_text:
                                    clm["status"] = "CONTRADICTED"

        # Disputes and supersessions the sources themselves state ("later analyses
        # contradict the cometary model", "earlier reports ... are outdated"). These
        # rarely appear as two comparable values, so the resolver above misses them.
        # An unresolved dispute is recorded with a grounded conflict claim; a
        # supersession is recorded as resolved and leaves other claims untouched.
        dispute_subjects = list(dict.fromkeys(
            ((action.target_entities if action else []) or [])
            + (state.objective_contract.get("target_entities") or [])
        ))
        for subj in dispute_subjects:
            for d_rec in detect_reported_disputes(docs, subj):
                if any(
                    c.get("subject") == d_rec.subject
                    and c.get("property_dim") == d_rec.property_dim
                    and c.get("evidence_id_b") == d_rec.evidence_id_b
                    for c in state.contradictions
                ):
                    continue
                state.contradictions.append(d_rec.model_dump())
                state.record_audit(
                    action_type="SOURCE_REPORTED_CONFLICT",
                    details={"subject": subj, "kind": d_rec.property_dim, "status": d_rec.status,
                             "source_url": d_rec.source_b, "passage": d_rec.claim_b[:300]},
                    rationale=d_rec.adjudication_rationale,
                )
                if d_rec.status == "UNRESOLVED_CONTRADICTION":
                    cid = state.add_claim({
                        "subject": subj,
                        "predicate": "conflict_noted",
                        "object": d_rec.claim_b,
                        "status": "CONTRADICTED",
                        "evidence_id": d_rec.evidence_id_b,
                        "source_url": d_rec.source_b,
                        "source_passage": d_rec.claim_b,
                    })
                    new_claims_found.append(cid)
                information_gain += 0.30

        # 3d. Adversarial, Negative & Empirical Uncertainty Resolution
        # A. Lookalike Phishing / Homoglyph Neutralization
        # Only documents about one of the investigation's targets count, and the threat
        # finding cites a sentence that names the flagged domain or package together
        # with the threat the source states. An affiliation is disavowed only with a
        # party the source says is imitated: when the user asks about the malicious
        # package itself, the old rule asserted that the package disavows itself.
        lookalike_targets = [t for t in dict.fromkeys(target_entities_list + (state.objective_contract.get("target_entities") or [])) if t and t != "Subject Matter"]
        flagged_name_re = re.compile(
            r"[\'\"\u2018\u201c]([A-Za-z0-9][\w.-]{2,})[\'\"\u2019\u201d]"
            r"|\b([a-z0-9][a-z0-9_-]*(?:\.[a-z0-9-]+)*\.(?:com|org|net|io|de|co\.uk|info|biz|xyz|app|dev))\b"
        )
        imitated_party_re = re.compile(
            r"\b(?:mimic|mimics|mimicking|impersonat\w*|imitat\w*|spoof\w*|posing as|masquerading as)\s+(?:the\s+)?"
            r"([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*)*)"
        )
        threat_re = re.compile(r"\b(phishing|lookalike|homoglyph|imposter|impersonat\w*|typosquat\w*|malicious|malware|exfiltrat\w*)\b", re.IGNORECASE)
        for d in docs:
            d_text = d.get("text", "")
            if not threat_re.search(d_text):
                continue
            if lookalike_targets and not any(term_in_passage(t, f"{d.get('title', '')} {d_text}") for t in lookalike_targets):
                continue
            # The flagged name is taken from the sentence that states the threat: a
            # domain, or a quoted package or account name.
            bad_domain, threat_sentence, threat_cue = "", "", ""
            for sent in split_sentences(d_text):
                m_cue = threat_re.search(sent)
                if not m_cue:
                    continue
                m_name = flagged_name_re.search(sent)
                if m_name:
                    bad_domain = next(g for g in m_name.groups() if g)
                    threat_sentence, threat_cue = sent, m_cue.group(1)
                    break
            if not bad_domain and len(d_text.strip()) <= 400:
                # A short structured record (e.g. WHOIS fields on separate lines) states
                # the threat on one line and the name on another; it is cited whole.
                named = [t for t in lookalike_targets if term_in_passage(t, d_text)]
                m_cue = threat_re.search(d_text)
                if named and m_cue:
                    bad_domain, threat_sentence, threat_cue = named[0], d_text.strip(), m_cue.group(1)
            if not bad_domain:
                continue
            if any(c.get("subject") == bad_domain and c.get("predicate") == "security_assessment" for c in state.claims):
                continue
            # Disavow an affiliation only with the party the source says is being
            # imitated, never with the flagged name itself.
            m_imit = imitated_party_re.search(threat_sentence)
            imitated = m_imit.group(1).strip(" .,;:") if m_imit else ""
            if imitated and _name_key(imitated) != _name_key(bad_domain):
                state.add_claim({
                    "subject": bad_domain,
                    "predicate": "affiliation",
                    "object": imitated,
                    "status": "CONTRADICTED",
                    "evidence_id": d.get("evidence_id"),
                    "source_url": d.get("url"),
                    "source_passage": threat_sentence,
                })
            cid = state.add_claim({
                "subject": bad_domain,
                "predicate": "security_assessment",
                "object": threat_sentence,
                "status": "SUPPORTED",
                "evidence_id": d.get("evidence_id"),
                "source_url": d.get("url"),
                "source_passage": threat_sentence,
                "grounding_terms": [threat_cue],
            })
            new_claims_found.append(cid)
            state.record_audit(
                action_type="ADVERSARIAL_IMPENETRATION_NEUTRALIZED",
                details={"domain": bad_domain, "finding": "Lookalike / Phishing neutralized", "threat": threat_cue},
                rationale="Source identifies the domain or package as a threat.",
            )
            break

        # B. Negative Findings & Affiliation Disavowals
        # Check explicit negative indicators and EntityScopeVerifier
        for target_ent in target_entities_list:
            if EntityScopeVerifier.is_negative_or_scoped_query(target_ent, state.objective):
                is_grounded, is_explicitly_absent, rationale = EntityScopeVerifier.verify_entity_presence(target_ent, docs)
                if is_explicitly_absent or not is_grounded:
                    if not any(c.get("subject") == target_ent and c.get("status") == "NOT_FOUND" for c in state.claims):
                        # An absence finding rests on all retrieved documents, so it cites
                        # none of them individually rather than borrowing docs[0].
                        cid = state.add_claim({
                            "subject": target_ent,
                            "predicate": "existence_verification",
                            "object": rationale,
                            "status": "NOT_FOUND",
                            "evidence_id": None,
                            "source_url": None,
                            "source_passage": "",
                        })
                        new_claims_found.append(cid)
                        information_gain += 0.35

        neg_indicators = ("zero affiliation", "no affiliation", "unrelated entity", "no connection", "unaffiliated", "no record", "no division", "zero record")
        for d in docs:
            d_text = d.get("text", "")
            if any(k in d_text.lower() for k in neg_indicators):
                target_entity = action.target_entities[0] if (action and action.target_entities) else "Target Entity"
                if EntityScopeVerifier.is_negative_or_scoped_query(target_entity, state.objective) and any(match_entity_in_text(te, d_text) for te in target_entities_list):
                    d_sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", d_text) if s.strip()]
                    for s in d_sentences:
                        if any(k in s.lower() for k in neg_indicators):
                            if not any(c.get("subject") == target_entity and c.get("status") == "NOT_FOUND" for c in state.claims):
                                state.add_claim({
                                    "subject": target_entity,
                                    "predicate": "affiliation",
                                    "object": s[:200],
                                    "status": "NOT_FOUND",
                                    "evidence_id": d.get("evidence_id"),
                                    "source_url": d.get("url"),
                                    "source_passage": d_text[:300],
                                })
                            break

        # C. Empirical Null Results & Scientific Insufficient Evidence
        is_sufficient, suff_rationale = EpistemicSufficiencyEvaluator.evaluate_sufficiency(docs, state.objective)
        if not is_sufficient:
            target_subj = action.target_entities[0] if (action and action.target_entities) else "Target Hypothesis"
            if not any(c.get("subject") == target_subj and c.get("status") == "INSUFFICIENT_EVIDENCE" for c in state.claims):
                best_doc = next(
                    (d for d in docs if any(m in (d.get("text") or "").lower() for m in EpistemicSufficiencyEvaluator.PRELIMINARY_MARKERS)),
                    {},
                )
                cid = state.add_claim({
                    "subject": target_subj,
                    "predicate": "empirical_sufficiency",
                    "object": suff_rationale,
                    "status": "INSUFFICIENT_EVIDENCE",
                    "evidence_id": best_doc.get("evidence_id"),
                    "source_url": best_doc.get("url"),
                    "source_passage": best_doc.get("text", "")[:300] if best_doc else suff_rationale,
                })
                new_claims_found.append(cid)
                information_gain += 0.35

        insufficient_markers = [
            "insufficient evidence", "null result", "failed to replicate", "unconfirmed",
            "inconclusive", "not confirmed", "unsubstantiated", "failed peer review",
        ]
        # The objective's own content words; a sentence that negates one of them about the
        # target ("X is ... not a superconductor" for "...superconductivity in X") refutes the
        # proposition being investigated.
        objective_stems = {w[:6] for w in re.findall(r"[a-z]{6,}", (state.objective or "").lower())}

        def negates_objective_term(sentence: str) -> bool:
            for m_neg in re.finditer(r"\b(?:not|no|never|neither|nor)\s+(?:an?\s+|the\s+)?([a-z]{6,})", sentence.lower()):
                if m_neg.group(1)[:6] in objective_stems:
                    return True
            return False

        for d in docs:
            d_text = d.get("text", "")
            d_sentences_all = [s.strip() for s in re.split(r"(?<=[.!?])\s+", d_text) if s.strip()]
            if any(k in d_text.lower() for k in insufficient_markers) or any(negates_objective_term(s) for s in d_sentences_all):
                target_subj = action.target_entities[0] if (action and action.target_entities) else "Target Hypothesis"
                if any(match_entity_in_text(te, d_text) for te in target_entities_list):
                    d_sentences = d_sentences_all
                    for s in d_sentences:
                        if any(k in s.lower() for k in insufficient_markers) or (
                            negates_objective_term(s) and any(match_entity_in_text(te, s) for te in target_entities_list)
                        ):
                            if not any(c.get("subject") == target_subj and c.get("status") == "INSUFFICIENT_EVIDENCE" for c in state.claims):
                                cid = state.add_claim({
                                    "subject": target_subj,
                                    "predicate": "empirical_status",
                                    "object": s[:200],
                                    "status": "INSUFFICIENT_EVIDENCE",
                                    "evidence_id": d.get("evidence_id"),
                                    "source_url": d.get("url"),
                                    "source_passage": d_text[:300],
                                })
                                new_claims_found.append(cid)
                                information_gain += 0.35
                                break

        # D. Temporal State Grounding
        m_dates = re.findall(r"\b(20\d\d-\d\d-\d\d|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:,\s+20\d\d)?)\b", all_text)
        if in_scope("temporal") and m_dates and any(k in all_text.lower() for k in ("as of", "handover", "resigned", "succeeded", "effective", "approved")):
            target_subj = action.target_entities[0] if (action and action.target_entities) else "Temporal State"
            best_doc = get_best_evidence_for_name(target_subj)
            temporal_sentence = extract_sentence_for_entity(best_doc.get("text", ""), target_subj)
            state.temporal_states.append({
                "entity": target_subj,
                "recorded_dates": m_dates,
                "context": all_text[:200],
            })
            state.add_claim({
                "subject": target_subj,
                "predicate": "temporal_grounding",
                "object": temporal_sentence,
                "status": "SUPPORTED",
                "evidence_id": best_doc.get("evidence_id"),
                "source_url": best_doc.get("url"),
                "source_passage": temporal_sentence,
            })
            information_gain += 0.30

        # 4. Resolve Target Question Strictly From Grounded Observations
        if action and action.question_id and action.question_id in state.questions:
            q_dict = state.questions[action.question_id]
            q = InvestigationQuestion.model_validate(q_dict)

            # Check for active contradictions in state or claims
            q_entities = q.related_entities or action.target_entities or []
            current_contra_claims = [
                c for c in state.claims
                if c.get("status") == "CONTRADICTED"
                and (not q_entities or c.get("subject") in q_entities or c.get("subject") == "Subject Matter")
            ]
            current_insufficient_claims = [
                c for c in state.claims
                if c.get("status") == "INSUFFICIENT_EVIDENCE"
                and (not q_entities or c.get("subject") in q_entities or c.get("subject") == "Entity")
            ]
            current_not_found_claims = [
                c for c in state.claims
                if c.get("status") == "NOT_FOUND"
                and c.get("predicate") != "contact_channel"
                and (not q_entities or c.get("subject") in q_entities or c.get("subject") == "Entity")
            ]

            # An open contradiction about another subject does not make this question
            # contradicted.
            unresolved_contras = [
                c for c in state.contradictions
                if c.get("status") == "UNRESOLVED_CONTRADICTION"
                and (not q_entities or any(
                    term_in_passage(e, f"{c.get('subject', '')} {c.get('topic', '')}") for e in q_entities
                ))
            ]
            has_contra = bool(unresolved_contras) or bool(current_contra_claims)

            # Check if this question is a negative verification question or asking about an absent scoped entity
            has_not_found = False
            for q_ent in q_entities:
                if EntityScopeVerifier.is_negative_or_scoped_query(q_ent, state.objective):
                    is_gr, is_abs, _ = EntityScopeVerifier.verify_entity_presence(q_ent, docs)
                    if is_abs or not is_gr:
                        has_not_found = True
                        break
            if not has_not_found:
                has_not_found = bool(current_not_found_claims)

            has_insufficient = bool(current_insufficient_claims) or (not is_sufficient)

            # If search discovered candidate sources that are not yet retrieved,
            # do not prematurely resolve the question as SUPPORTED.
            is_search_action = bool(action and action.action_type == ActionType.SEARCH)
            unretrieved_sources = [
                s for s in state.get_unretrieved_sources()
                if not action.target_entities or s.get("target_entity") in action.target_entities or not s.get("target_entity")
            ]
            has_pending_fetches = is_search_action and len(unretrieved_sources) > 0 and not has_contra and not has_not_found
            keep_open = False

            # Link claims to the question this action ran for: the asserted claims this
            # observation produced or re-sighted, plus claims already extracted from the
            # same documents. A claim links only if its source is about one of the
            # question's entities (when the question names any) and it states the kind of
            # fact the question type asks for: a question about X is not answered by a
            # claim from a page about Y, nor an infrastructure question by a founding date.
            obs_evidence_ids = {d.get("evidence_id") for d in docs if d.get("evidence_id")}
            regrounded = [c.get("claim_id") for c in state.claims if c.get("evidence_id") in obs_evidence_ids]
            ev_text = {
                e.get("evidence_id"): f"{e.get('title', '')} {e.get('snippet') or e.get('text') or ''}"
                for e in state.evidence
            }

            def _about_question_entity(c: dict[str, Any]) -> bool:
                if not q_entities:
                    return True
                text = f"{c.get('subject', '')} {c.get('object', '')} {ev_text.get(c.get('evidence_id'), '')}"
                return any(term_in_passage(e, text) for e in q_entities)

            index = claims_index(state.claims)
            for cid in dict.fromkeys(new_claims_found + supported_claims_found + regrounded):
                c = index.get(cid) or {}
                if (
                    c.get("status") in POSITIVE_STATUSES
                    and claim_kind_fits_question(c, q.question_type)
                    and _about_question_entity(c)
                    and cid not in q.related_claims
                ):
                    q.related_claims.append(cid)

            if has_contra:
                q.resolve(
                    status=QuestionStatus.CONTRADICTED,
                    reason="Identified substantive contradiction or unresolved conflict across retrieved evidence.",
                    claim_ids=[c.get("claim_id", "") for c in current_contra_claims],
                )
            elif has_not_found:
                q.resolve(
                    status=QuestionStatus.NOT_FOUND,
                    reason="Authoritative documentation confirmed target entity, department, or relationship does not exist or has zero operating records.",
                    claim_ids=[c.get("claim_id", "") for c in current_not_found_claims],
                    evidence_ids=[d.get("evidence_id") for d in docs if d.get("evidence_id")],
                )
            elif has_insufficient:
                q.resolve(
                    status=QuestionStatus.INSUFFICIENT_EVIDENCE,
                    reason=f"Comprehensive literature inspection confirmed evidence is insufficient, preliminary, or unconfirmed: {suff_rationale}",
                    claim_ids=[c.get("claim_id", "") for c in current_insufficient_claims],
                )
            elif has_pending_fetches:
                q.status = QuestionStatus.INVESTIGATING
                q.resolution_reason = f"Discovered {len(unretrieved_sources)} candidate source(s). Pending full content retrieval."
                state.questions[action.question_id] = q.model_dump()
                information_gain += 0.25
                # Keep question open in unresolved_questions for follow-up content retrieval
                return information_gain
            else:
                # A question is SUPPORTED only by claims that passed the shared
                # verification gate; documents arriving is not an answer.
                index = claims_index(state.claims)
                q_view = q.model_dump()
                verified = verified_linked_claims(q_view, index)
                asserted = positive_linked_claims(q_view, index)
                used_queries = {a.get("query", "").strip().lower() for a in state.research_actions}
                pending_queries = [sq for sq in q.search_queries if sq.strip().lower() not in used_queries]

                # A question whose answer is a list (the organizations of an enumeration
                # objective) is not finished by its first verified item: it keeps running
                # its remaining focused queries to find more.
                enum_qids = set(((state.objective_contract.get("enumeration_objective") or {}).get("question_ids") or {}).values())
                collects_list = action.question_id in enum_qids

                if verified and not (collects_list and pending_queries):
                    kinds = ", ".join(sorted({str(c.get("status")) for c in verified}))
                    q.resolve(
                        status=QuestionStatus.SUPPORTED,
                        reason=f"Answered by {len(verified)} verified claim(s) ({kinds}).",
                        claim_ids=[c["claim_id"] for c in verified if c["claim_id"] not in q.resolved_by_claim_ids],
                    )
                    for gap in state.information_gaps:
                        if gap.related_question_id == q.question_id:
                            gap.is_resolved = True
                elif pending_queries:
                    # Not finished: the question still has focused objective queries to
                    # run; keep it open rather than closing it.
                    keep_open = True
                    q.status = QuestionStatus.INVESTIGATING
                    q.resolution_reason = (
                        f"{len(verified)} verified and {len(asserted) - len(verified)} unverified answer(s) so far; "
                        f"{len(pending_queries)} focused query(ies) remain."
                        if verified else
                        f"No verified claim yet ({len(asserted)} unverified assertion(s)); "
                        f"{len(pending_queries)} focused query(ies) remain."
                    )
                elif asserted:
                    kinds = ", ".join(sorted({str(c.get("status")) for c in asserted}))
                    q.resolve(
                        status=QuestionStatus.PARTIALLY_RESOLVED,
                        reason=(
                            f"Only unverified assertions found: {len(asserted)} claim(s) ({kinds}); "
                            "no vendor confirmation or independent corroboration."
                        ),
                        claim_ids=[c["claim_id"] for c in asserted if c["claim_id"] not in q.resolved_by_claim_ids],
                    )
                else:
                    q.resolve(
                        status=QuestionStatus.INSUFFICIENT_EVIDENCE,
                        reason=f"Retrieved {len(docs)} document(s), but none yielded a claim that passed verification.",
                    )

            state.questions[action.question_id] = q.model_dump()
            if not keep_open:
                if action.question_id in state.unresolved_questions:
                    state.unresolved_questions.remove(action.question_id)
                if action.question_id not in state.resolved_questions:
                    state.resolved_questions.append(action.question_id)
                information_gain += 0.40
            else:
                information_gain += 0.25 if (new_claims_found or supported_claims_found) else 0.0

        # A question closed on unverified assertions becomes SUPPORTED once one of its
        # claims is verified later (e.g. a vendor case study confirms a provider row).
        index = claims_index(state.claims)
        for qid, qd in state.questions.items():
            if qd.get("status") != QuestionStatus.PARTIALLY_RESOLVED.value:
                continue
            verified = verified_linked_claims(qd, index)
            if verified:
                qp = InvestigationQuestion.model_validate(qd)
                qp.resolve(
                    status=QuestionStatus.SUPPORTED,
                    reason=f"Answered by {len(verified)} claim(s) verified by later evidence.",
                    claim_ids=[c["claim_id"] for c in verified if c["claim_id"] not in qp.resolved_by_claim_ids],
                )
                state.questions[qid] = qp.model_dump()
                state.record_audit(
                    action_type="QUESTION_UPGRADED",
                    details={"question_id": qid, "claim_ids": [c["claim_id"] for c in verified]},
                    rationale="Previously unverified answer confirmed by a verified claim.",
                )

        # 5. Type-Based Multi-Specialist Chaining (for investigative workflows)
        active_caps = [c.capability_id for c in self.registry.list(include_inactive=False)]

        if not is_exec_goal and in_scope("chaining"):
            # Type 1a: Discovered Technical/Infrastructure Subsidiaries -> Chained to Infrastructure Specialist
            # A subsidiary whose own evidence describes it as technical/infrastructure gets an
            # infrastructure follow-up; the decision comes from the passage, not the name.
            infra_context = re.compile(r"\b(?:infrastructure|network|hosting|cloud|data\s*cent(?:er|re)|telemetry|domains?|servers?)\b", re.I)
            legal_form = re.compile(r"\b(?:Ltd|Limited|LLC|GmbH|Inc|Corp|Corporation|plc|PLC|AG|SA|BV|Pty|LLP|LP)\b\.?")

            def entity_context(name: str) -> str:
                meta_ctx = str(((state.entities.get(name) or {}).get("metadata") or {}).get("context", ""))
                sentence = next((sent for sent in re.split(r"(?<=[.!?\n])\s+", all_text) if name in sent), "")
                return f"{name} {meta_ctx} {sentence}"

            tech_subs = [
                e for e in new_entities_found
                if ((state.entities.get(e) or {}).get("type") == "SUBSIDIARY" or legal_form.search(e))
                and infra_context.search(entity_context(e))
            ]
            for tsub in tech_subs:
                if not any(tsub in str(q) for q in state.questions.values()):
                    q_chain_tsub = InvestigationQuestion(
                        question_text=f"What network infrastructure, domain names, and CT SAN endpoints are registered to {tsub}?",
                        question_type=QuestionType.INFRASTRUCTURE_ATTRIBUTION,
                        priority=0.96,
                        is_critical=False,
                        origin="chained",
                        related_entities=[tsub],
                        specialist_requirements=["infrastructure"],
                        required_evidence=[f"Certificate Transparency log, DNS, or network record for {tsub}"],
                    )
                    state.questions[q_chain_tsub.question_id] = q_chain_tsub.model_dump()
                    state.unresolved_questions.append(q_chain_tsub.question_id)
                    state.record_audit(
                        action_type="SPECIALIST_CHAIN_TRIGGERED",
                        details={
                            "origin_specialist": "corporate",
                            "next_specialist": "infrastructure",
                            "question_id": q_chain_tsub.question_id,
                            "entity": tsub,
                        },
                        rationale=f"Corporate discovery of technical infrastructure subsidiary {tsub} chained to Infrastructure Specialist.",
                    )

            # Type 1b: Discovered Technical Infrastructure Endpoints -> Chained to Infrastructure Specialist
            extracted_domains = set(re.findall(r"\b([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.(?:[a-z0-9-]+\.)+(?:com|org|net|de|co\.uk|io))\b", all_text))
            doc_hosts = {re.sub(r"^https?://([^/]+).*$", r"\1", d.get("url", "")) for d in docs}
            infra_domains = [dom for dom in extracted_domains if dom not in doc_hosts and len(dom) > 5]

            for dom in infra_domains:
                doc_urls = [d.get("url", "") for d in docs if dom in d.get("text", "")]
                primary_doc_url = doc_urls[0] if doc_urls else ""
                if not is_contextually_relevant_host(
                    dom,
                    doc_url=primary_doc_url,
                    target_objective=state.objective,
                    target_entities=list(state.entities.keys()),
                ):
                    continue
                if not any(dom in str(q) for q in state.questions.values()):
                    q_chain_infra = InvestigationQuestion(
                        question_text=f"What network infrastructure and CT SAN endpoints are registered to {dom}?",
                        question_type=QuestionType.INFRASTRUCTURE_ATTRIBUTION,
                        priority=0.95,
                        is_critical=False,
                        origin="chained",
                        related_entities=[dom],
                        specialist_requirements=["infrastructure"],
                        required_evidence=[f"Certificate Transparency log or SAN entry for {dom}"],
                    )
                    state.questions[q_chain_infra.question_id] = q_chain_infra.model_dump()
                    state.unresolved_questions.append(q_chain_infra.question_id)
                    state.record_audit(
                        action_type="SPECIALIST_CHAIN_TRIGGERED",
                        details={
                            "origin_specialist": "corporate",
                            "next_specialist": "infrastructure",
                            "question_id": q_chain_infra.question_id,
                            "domain": dom,
                        },
                        rationale=f"Corporate discovery of technical infrastructure {dom} dynamically chained to Infrastructure Specialist.",
                    )

            # Type 2: Discovered Technical Administrator / Person -> Chained to Identity Specialist
            extracted_emails = set(re.findall(r"\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b", all_text))
            for email in extracted_emails:
                # Associate with person entities in context
                person_candidates = [e for e in new_entities_found if e in state.entities and " " in e]
                for person in person_candidates:
                    if not any(f"identity of {person}".lower() in str(q).lower() for q in state.questions.values()):
                        q_chain_ident = InvestigationQuestion(
                            question_text=f"What is {person}'s professional identity, employment profile, and background?",
                            question_type=QuestionType.IDENTITY_CORRELATION,
                            priority=0.90,
                            is_critical=False,
                            origin="chained",
                            related_entities=[person],
                            specialist_requirements=["identity"],
                            required_evidence=[f"Biographical employment profile for {person}"],
                        )
                        state.questions[q_chain_ident.question_id] = q_chain_ident.model_dump()
                        state.unresolved_questions.append(q_chain_ident.question_id)
                        state.record_audit(
                            action_type="SPECIALIST_CHAIN_TRIGGERED",
                            details={
                                "origin_specialist": "infrastructure",
                                "next_specialist": "identity",
                                "question_id": q_chain_ident.question_id,
                                "person": person,
                            },
                            rationale=f"Infrastructure discovery of admin email {email} chained to Identity Specialist for {person}.",
                        )

            # Type 3: Sanctions, PEP, and Beneficial Ownership Chaining
            is_sanctions_relevant = any(
                k in state.objective.lower()
                for k in ["sanction", "pep", "offshore", "ownership", "beneficial", "compliance", "freeze", "trust"]
            )
            if "sanctions_and_beneficial_ownership" in active_caps and is_sanctions_relevant:
                for ent in new_entities_found:
                    if not any(f"sanctions screening for {ent}".lower() in str(q).lower() for q in state.questions.values()):
                        q_chain_sanc = InvestigationQuestion(
                            question_text=f"Screen consolidated international sanctions, PEP status, and offshore beneficial ownership for {ent}.",
                            question_type=QuestionType.ENTITY_DISCOVERY,
                            priority=0.85,
                            is_critical=False,
                            origin="chained",
                            related_entities=[ent],
                            specialist_requirements=["sanctions_and_offshore"],
                            required_evidence=[f"OFAC SDN, UK OFSI, PEP disclosure, or Offshore Leaks record for {ent}"],
                        )
                        state.questions[q_chain_sanc.question_id] = q_chain_sanc.model_dump()
                        state.unresolved_questions.append(q_chain_sanc.question_id)
                        state.record_audit(
                            action_type="SPECIALIST_CHAIN_TRIGGERED",
                            details={
                                "origin_specialist": "corporate",
                                "next_specialist": "sanctions",
                                "question_id": q_chain_sanc.question_id,
                                "entity": ent,
                            },
                            rationale=f"Corporate discovery of {ent} dynamically chained to Sanctions Specialist.",
                        )

            # Type 4: Discovered Controller Alias or Handle -> Chained to Identity Correlation
            aliases = re.findall(r"(?:^|\s)(0x_[a-zA-Z0-9_]+|@[a-zA-Z0-9_]+)(?:\s|$|[.,])", all_text)
            for alias in aliases:
                if not any(alias.lower() in str(q).lower() for q in state.questions.values()):
                    q_chain_alias = InvestigationQuestion(
                        question_text=f"Resolve developer personas, GitHub handles, and Keybase identity for alias {alias}.",
                        question_type=QuestionType.IDENTITY_CORRELATION,
                        priority=0.80,
                        is_critical=False,
                        origin="chained",
                        related_entities=[alias],
                        specialist_requirements=["identity"],
                        required_evidence=[f"GitHub or Keybase identity record for {alias}"],
                    )
                    state.questions[q_chain_alias.question_id] = q_chain_alias.model_dump()
                    state.unresolved_questions.append(q_chain_alias.question_id)
                    state.record_audit(
                        action_type="SPECIALIST_CHAIN_TRIGGERED",
                        details={
                            "origin_specialist": "sanctions",
                            "next_specialist": "identity",
                            "question_id": q_chain_alias.question_id,
                            "alias": alias,
                        },
                        rationale=f"Sanctions discovery of offshore controller alias {alias} chained to Identity Specialist.",
                    )

        # 6. Update Overall Confidence State
        state.confidence_state.recompute_calibration(state)

        return information_gain
