"""Heimdallr V2: Investigation Planner.

Translates objectives into dynamic question topologies, forms testable hypotheses,
defines evidentiary requirements, and plans ranked research actions:
- Decomposes broad objectives (e.g. executive mapping, M&A tracing) into actionable questions
- Prioritizes actions by expected information gain rather than static FIFO order
- Coordinates multi-specialist activation and contradiction-resolution branches
"""

from __future__ import annotations

import logging
import re
from typing import Any
import uuid

from argus.investigation.action import ActionType, ResearchAction
from argus.investigation.branch import BranchStatus, InvestigationBranch
from argus.investigation.evidence import EvidenceRequirement, EvidenceStatus
from argus.investigation.hypothesis import HypothesisStatus, InvestigationHypothesis
from argus.investigation.information_gain import InformationGainEstimator
from argus.investigation.question import InvestigationQuestion, QuestionStatus, QuestionType
from argus.investigation.state import InformationGap, InvestigationState
from argus.capability_registry.registry import CapabilityRegistry
from argus.capability_registry.matcher import CapabilityMatcher
from argus.capability_registry.defaults import get_default_capabilities

logger = logging.getLogger(__name__)


class InvestigationPlanner:
    """Plans research trajectories, manages question graphs, and selects high-value actions."""

    def __init__(
        self,
        estimator: InformationGainEstimator | None = None,
        registry: CapabilityRegistry | None = None,
        matcher: CapabilityMatcher | None = None,
    ) -> None:
        self.estimator = estimator or InformationGainEstimator()
        self.registry = registry or CapabilityRegistry()
        if not self.registry.list():
            for cap in get_default_capabilities():
                self.registry.register(cap, overwrite=True)
        self.matcher = matcher or CapabilityMatcher()

    @classmethod
    def _detect_domain(cls, objective: str, contract: dict[str, Any]) -> str:
        """Detect investigation domain from explicit hint or semantic keywords."""
        if "domain_hint" in contract and contract["domain_hint"]:
            return str(contract["domain_hint"]).lower().strip()

        if "starting_platform" in contract or "username" in contract:
            return "identity"

        obj_lower = (objective or "").lower()

        if any(
            k in obj_lower
            for k in [
                "investigate username",
                "starting platform",
                "candidate accounts",
                "identity probe",
                "identity investigation",
                "cross-platform identity",
                "social profile",
                "account existence",
                "unacceptable merges",
            ]
        ):
            return "identity"
        if any(
            k in obj_lower
            for k in [
                "vector database",
                "database",
                "databases",
                "software",
                "api",
                "open-source",
                "licensing",
                "performance evidence",
                "filtering capabilities",
                "operational complexity",
                "query engine",
            ]
        ):
            return "technical"

        if any(
            k in obj_lower
            for k in [
                "historical",
                "history",
                "historical decision",
                "sequence of events",
                "major participants",
                "established facts",
                "disputed interpretations",
                "treaty",
                "century",
            ]
        ):
            return "historical"

        if any(
            k in obj_lower
            for k in [
                "scientific",
                "public-policy",
                "policy question",
                "competing explanations",
                "unresolved uncertainties",
                "methodological",
                "epidemiology",
            ]
        ):
            return "scientific_policy"

        if any(
            k in obj_lower
            for k in [
                "unfamiliar organization",
                "public products, leadership, partnerships",
                "strategic changes",
                "non-profit",
                "foundation",
                "ngo",
            ]
        ):
            return "organization"

        if any(
            k in obj_lower
            for k in [
                "corporate",
                "company",
                "subsidiary",
                "subsidiaries",
                "sec",
                "10-k",
                "filing",
                "filings",
                "commercial registry",
                "conglomerate",
                "acquisition",
                "holding",
                "holdings",
                "incorporat",
                "executive officers",
                "ownership disclosure",
                "jurisdiction",
                "business inquiries",
                "director",
                "c-suite",
                "officer tenure",
                "ciso",
                "svp",
                "vp ",
            ]
        ):
            return "corporate"

        return "generic"

    def initialize_investigation(
        self,
        objective: str,
        objective_contract: dict[str, Any] | None = None,
        as_of_date: str | None = None,
    ) -> InvestigationState:
        """Decompose objective into initial state, questions, hypotheses, and evidence requirements."""
        if not objective or not isinstance(objective, str) or not objective.strip():
            raise ValueError("Investigation objective must be a non-empty string.")

        contract = objective_contract or {}
        if not isinstance(contract, dict):
            raise ValueError("Objective contract must be a dictionary.")

        max_steps = contract.get("max_steps", 15)
        if not isinstance(max_steps, int) or max_steps <= 0:
            raise ValueError("Contract max_steps must be a positive integer.")

        state = InvestigationState(objective=objective, objective_contract=contract)
        state.research_budget["max_steps"] = max_steps

        # 1. Create root investigation branch
        root_branch = InvestigationBranch(
            purpose="Root Investigation Line",
            step_budget=max_steps,
        )
        state.active_branches.append(root_branch.branch_id)
        state.record_audit(
            action_type="BRANCH_INITIALIZED",
            details={"branch_id": root_branch.branch_id, "purpose": root_branch.purpose},
            rationale="Initialized primary investigation tree branch.",
        )

        domain = self._detect_domain(objective, contract)

        # 2. Deconstruct objective into core entity targets and questions
        target_entities = contract.get("target_entities") or []
        if not isinstance(target_entities, list):
            raise ValueError("Contract target_entities must be a list.")

        if not target_entities:
            # Extract distinctive capitalized multi-word phrases from objective
            words = objective.split()
            candidates = []
            for i, w in enumerate(words):
                if w and w[0].isupper() and w not in {
                    "Identify", "Trace", "Investigate", "Verify", "Disambiguate",
                    "Parse", "Compare", "Research", "Evaluate",
                }:
                    candidates.append(w.strip(".,;:\"'"))
            if candidates:
                target_entities = [" ".join(candidates[:3])]

        entity_type_map = {
            "technical": "TECHNICAL_SYSTEM",
            "historical": "HISTORICAL_SUBJECT",
            "scientific_policy": "SCIENTIFIC_TOPIC",
            "organization": "ORGANIZATION",
            "corporate": "TARGET_ORGANIZATION",
            "identity": "IDENTITY_HANDLE",
        }
        ent_type = entity_type_map.get(domain, "CONCEPT")

        # Register target entities
        for ent in target_entities:
            state.register_entity(name=ent, entity_type=ent_type)

        primary_entity = target_entities[0] if target_entities else ("Target Entity" if domain in ("corporate", "organization") else "Research Subject")

        # 3. Formulate foundational investigation questions
        # Check if caller supplied validated custom initial questions
        custom_q_list = contract.get("initial_questions")
        if custom_q_list is not None:
            if not isinstance(custom_q_list, list):
                raise ValueError("Contract initial_questions must be a list.")
            initial_questions: list[InvestigationQuestion] = []
            for item in custom_q_list:
                if isinstance(item, InvestigationQuestion):
                    initial_questions.append(item)
                elif isinstance(item, dict):
                    if not item.get("question_text"):
                        raise ValueError(f"Malformed initial question dictionary: missing question_text ({item})")
                    initial_questions.append(InvestigationQuestion.model_validate(item))
                else:
                    raise ValueError(f"Malformed initial question item: {type(item).__name__}")

            for q in initial_questions:
                state.questions[q.question_id] = q.model_dump()
                state.unresolved_questions.append(q.question_id)
                root_branch.questions.append(q.question_id)

            hyp_custom = InvestigationHypothesis(
                proposition=f"Initial research hypotheses formulated for {primary_entity}.",
                related_question_id=initial_questions[0].question_id if initial_questions else None,
                related_entities=[primary_entity],
                supporting_evidence_requirements=[f"Authoritative evidence addressing: {objective}"],
                refuting_evidence_requirements=[f"Contradictory evidence refuting: {objective}"],
            )
            state.hypotheses[hyp_custom.hypothesis_id] = hyp_custom.model_dump()

            state.record_audit(
                action_type="INVESTIGATION_INITIALIZED",
                details={
                    "objective": objective,
                    "domain": domain,
                    "initial_questions_count": len(state.questions),
                    "primary_entity": primary_entity,
                },
                rationale=f"Initialized custom question topology for {domain} domain.",
            )
            return state

        # Domain-driven decomposition
        if domain == "technical":
            q_obj = InvestigationQuestion(
                question_text=objective,
                question_type=QuestionType.ENTITY_DISCOVERY,
                priority=1.0,
                is_critical=True,
                related_entities=target_entities,
                specialist_requirements=["none"],
                required_evidence=[f"Technical specifications and empirical benchmarks addressing: {objective}"],
            )
            q_filter = InvestigationQuestion(
                question_text=f"What are the metadata filtering capabilities, indexing structures, and query constraints of {primary_entity}?",
                question_type=QuestionType.ENTITY_DISCOVERY,
                priority=0.95,
                is_critical=True,
                related_entities=[primary_entity],
                specialist_requirements=["none"],
                required_evidence=[f"Official technical documentation or benchmark evaluating filtering capabilities of {primary_entity}"],
            )
            q_ops = InvestigationQuestion(
                question_text=f"What is the operational complexity, deployment footprint, and resource requirements of {primary_entity}?",
                question_type=QuestionType.RELATIONSHIP_VERIFICATION,
                priority=0.90,
                is_critical=False,
                dependencies=[q_filter.question_id],
                related_entities=[primary_entity],
                specialist_requirements=["none"],
                required_evidence=[f"Operational deployment guides and maintenance documentation for {primary_entity}"],
            )
            q_lic = InvestigationQuestion(
                question_text=f"What open-source software license, governance terms, and commercial constraints govern {primary_entity}?",
                question_type=QuestionType.RELATIONSHIP_VERIFICATION,
                priority=0.85,
                is_critical=False,
                dependencies=[q_filter.question_id],
                related_entities=[primary_entity],
                specialist_requirements=["none"],
                required_evidence=[f"Software license file (e.g. Apache-2.0, AGPL, MIT) or repository license declaration for {primary_entity}"],
            )
            q_perf = InvestigationQuestion(
                question_text=f"What empirical performance evidence, throughput, and query latency benchmarks are documented for {primary_entity}?",
                question_type=QuestionType.RELATIONSHIP_VERIFICATION,
                priority=0.85,
                is_critical=False,
                dependencies=[q_filter.question_id],
                related_entities=[primary_entity],
                specialist_requirements=["none"],
                required_evidence=[f"Empirical benchmark results or reproducible performance metrics for {primary_entity}"],
            )

            for q in [q_obj, q_filter, q_ops, q_lic, q_perf]:
                state.questions[q.question_id] = q.model_dump()
                state.unresolved_questions.append(q.question_id)
                root_branch.questions.append(q.question_id)

            hyp_tech = InvestigationHypothesis(
                proposition=f"{primary_entity} supports flexible metadata filtering with manageable operational complexity under an open license.",
                related_question_id=q_filter.question_id,
                related_entities=[primary_entity],
                supporting_evidence_requirements=[f"Technical benchmark or documentation confirming filtering capabilities of {primary_entity}"],
                refuting_evidence_requirements=[f"Documentation demonstrating severe filtering limits or restrictive licensing in {primary_entity}"],
            )
            state.hypotheses[hyp_tech.hypothesis_id] = hyp_tech.model_dump()

            state.information_gaps.append(
                InformationGap(
                    description=f"Filtering capability matrix for {primary_entity}",
                    target_entity=primary_entity,
                    target_attribute="filtering_capabilities",
                    priority=1.0,
                    is_critical=True,
                    related_question_id=q_filter.question_id,
                )
            )
            state.information_gaps.append(
                InformationGap(
                    description=f"Licensing model for {primary_entity}",
                    target_entity=primary_entity,
                    target_attribute="software_license",
                    priority=0.85,
                    is_critical=False,
                    related_question_id=q_lic.question_id,
                )
            )

        elif domain == "historical":
            q_obj = InvestigationQuestion(
                question_text=objective,
                question_type=QuestionType.ENTITY_DISCOVERY,
                priority=1.0,
                is_critical=True,
                related_entities=target_entities,
                specialist_requirements=["none"],
                required_evidence=[f"Primary historical records and scholarly accounts addressing: {objective}"],
            )
            q_seq = InvestigationQuestion(
                question_text=f"What is the chronological sequence of events and pivotal milestones leading to the decision regarding {primary_entity}?",
                question_type=QuestionType.ENTITY_DISCOVERY,
                priority=0.95,
                is_critical=True,
                related_entities=[primary_entity],
                specialist_requirements=["none"],
                required_evidence=[f"Documented chronological event timeline or contemporary institutional records for {primary_entity}"],
            )
            q_parts = InvestigationQuestion(
                question_text=f"Who were the key historical participants, decision-makers, and institutional actors in {primary_entity}?",
                question_type=QuestionType.RELATIONSHIP_VERIFICATION,
                priority=0.90,
                is_critical=True,
                dependencies=[q_seq.question_id],
                related_entities=[primary_entity],
                specialist_requirements=["none"],
                required_evidence=[f"Primary meeting records, official memos, or participant memoirs for {primary_entity}"],
            )
            q_facts = InvestigationQuestion(
                question_text=f"Which core facts are established by historical consensus versus remaining disputed among conflicting accounts for {primary_entity}?",
                question_type=QuestionType.CONTRADICTION_RESOLUTION,
                priority=0.85,
                is_critical=False,
                dependencies=[q_seq.question_id],
                related_entities=[primary_entity],
                specialist_requirements=["none"],
                required_evidence=[f"Scholarly historical analyses or primary source records distinguishing factual consensus from interpretation for {primary_entity}"],
            )

            for q in [q_obj, q_seq, q_parts, q_facts]:
                state.questions[q.question_id] = q.model_dump()
                state.unresolved_questions.append(q.question_id)
                root_branch.questions.append(q.question_id)

            hyp_hist = InvestigationHypothesis(
                proposition=f"The historical trajectory and primary participants of {primary_entity} can be definitively established from primary records.",
                related_question_id=q_seq.question_id,
                related_entities=[primary_entity],
                supporting_evidence_requirements=[f"Primary source documentation confirming sequence of events for {primary_entity}"],
                refuting_evidence_requirements=[f"Contemporaneous contradictory records challenging the sequence of events for {primary_entity}"],
            )
            state.hypotheses[hyp_hist.hypothesis_id] = hyp_hist.model_dump()

            state.information_gaps.append(
                InformationGap(
                    description=f"Chronological event sequence for {primary_entity}",
                    target_entity=primary_entity,
                    target_attribute="event_sequence",
                    priority=1.0,
                    is_critical=True,
                    related_question_id=q_seq.question_id,
                )
            )

        elif domain == "scientific_policy":
            q_obj = InvestigationQuestion(
                question_text=objective,
                question_type=QuestionType.ENTITY_DISCOVERY,
                priority=1.0,
                is_critical=True,
                related_entities=target_entities,
                specialist_requirements=["none"],
                required_evidence=[f"Empirical scientific studies or policy analyses addressing: {objective}"],
            )
            q_comp = InvestigationQuestion(
                question_text=f"What are the competing scientific or policy explanations and models formulated regarding {primary_entity}?",
                question_type=QuestionType.ENTITY_DISCOVERY,
                priority=0.95,
                is_critical=True,
                related_entities=[primary_entity],
                specialist_requirements=["none"],
                required_evidence=[f"Peer-reviewed studies or authoritative policy reviews detailing competing explanations for {primary_entity}"],
            )
            q_ev = InvestigationQuestion(
                question_text=f"What empirical evidence, data quality, and methodology support each competing explanation for {primary_entity}?",
                question_type=QuestionType.RELATIONSHIP_VERIFICATION,
                priority=0.90,
                is_critical=True,
                dependencies=[q_comp.question_id],
                related_entities=[primary_entity],
                specialist_requirements=["none"],
                required_evidence=[f"Empirical datasets, systematic reviews, or clinical/policy evaluations regarding {primary_entity}"],
            )
            q_unc = InvestigationQuestion(
                question_text=f"What unresolved uncertainties, methodological limitations, and evidence gaps remain regarding {primary_entity}?",
                question_type=QuestionType.CONTRADICTION_RESOLUTION,
                priority=0.85,
                is_critical=False,
                dependencies=[q_comp.question_id],
                related_entities=[primary_entity],
                specialist_requirements=["none"],
                required_evidence=[f"Documented sensitivity bounds, conflicting study results, or consensus gap statements regarding {primary_entity}"],
            )

            for q in [q_obj, q_comp, q_ev, q_unc]:
                state.questions[q.question_id] = q.model_dump()
                state.unresolved_questions.append(q.question_id)
                root_branch.questions.append(q.question_id)

            hyp_sci = InvestigationHypothesis(
                proposition=f"Available empirical evidence differentiates the validity of competing models for {primary_entity} while identifying unresolved uncertainties.",
                related_question_id=q_comp.question_id,
                related_entities=[primary_entity],
                supporting_evidence_requirements=[f"Peer-reviewed empirical findings supporting primary explanation for {primary_entity}"],
                refuting_evidence_requirements=[f"Replication failures or contradictory findings regarding {primary_entity}"],
            )
            state.hypotheses[hyp_sci.hypothesis_id] = hyp_sci.model_dump()

            state.information_gaps.append(
                InformationGap(
                    description=f"Competing theoretical models for {primary_entity}",
                    target_entity=primary_entity,
                    target_attribute="competing_models",
                    priority=1.0,
                    is_critical=True,
                    related_question_id=q_comp.question_id,
                )
            )

        elif domain == "organization":
            q_obj = InvestigationQuestion(
                question_text=objective,
                question_type=QuestionType.ENTITY_DISCOVERY,
                priority=1.0,
                is_critical=True,
                related_entities=target_entities,
                specialist_requirements=["none"],
                required_evidence=[f"Official organization publications and verified public records addressing: {objective}"],
            )
            q_prod = InvestigationQuestion(
                question_text=f"What are the public products, programs, and strategic offerings of {primary_entity}?",
                question_type=QuestionType.ENTITY_DISCOVERY,
                priority=0.95,
                is_critical=True,
                related_entities=[primary_entity],
                specialist_requirements=["none"],
                required_evidence=[f"Official product catalogs, program brochures, or public releases for {primary_entity}"],
            )
            q_lead = InvestigationQuestion(
                question_text=f"Who are the key executive leaders, governing board members, and directors of {primary_entity}?",
                question_type=QuestionType.OFFICER_TENURE,
                priority=0.90,
                is_critical=True,
                dependencies=[q_prod.question_id],
                related_entities=[primary_entity],
                specialist_requirements=["none"],
                required_evidence=[f"Official governance directory or leadership roster for {primary_entity}"],
            )
            q_part = InvestigationQuestion(
                question_text=f"What strategic partnerships, alliances, and stakeholder relationships are documented for {primary_entity}?",
                question_type=QuestionType.RELATIONSHIP_VERIFICATION,
                priority=0.85,
                is_critical=False,
                dependencies=[q_prod.question_id],
                related_entities=[primary_entity],
                specialist_requirements=["none"],
                required_evidence=[f"Documented partnership agreements or public alliance disclosures for {primary_entity}"],
            )
            q_strat = InvestigationQuestion(
                question_text=f"What documented strategic changes, mission pivots, and organizational shifts have occurred at {primary_entity}?",
                question_type=QuestionType.ENTITY_DISCOVERY,
                priority=0.80,
                is_critical=False,
                dependencies=[q_prod.question_id],
                related_entities=[primary_entity],
                specialist_requirements=["none"],
                required_evidence=[f"Strategic announcements, annual reviews, or governance filings for {primary_entity}"],
            )

            for q in [q_obj, q_prod, q_lead, q_part, q_strat]:
                state.questions[q.question_id] = q.model_dump()
                state.unresolved_questions.append(q.question_id)
                root_branch.questions.append(q.question_id)

            hyp_org = InvestigationHypothesis(
                proposition=f"{primary_entity} operates active public programs and documented strategic partnerships.",
                related_question_id=q_prod.question_id,
                related_entities=[primary_entity],
                supporting_evidence_requirements=[f"Official documentation of programs and alliances for {primary_entity}"],
                refuting_evidence_requirements=[f"Evidence of discontinued operations or dissolved partnerships for {primary_entity}"],
            )
            state.hypotheses[hyp_org.hypothesis_id] = hyp_org.model_dump(            )
            state.information_gaps.append(
                InformationGap(
                    description=f"Public products and programs for {primary_entity}",
                    target_entity=primary_entity,
                    target_attribute="products_and_programs",
                    priority=1.0,
                    is_critical=True,
                    related_question_id=q_prod.question_id,
                )
            )

        elif domain == "identity":
            username = contract.get("username") or primary_entity
            starting_plat = contract.get("starting_platform", "github")

            q_starting = InvestigationQuestion(
                question_text=f"Does account '{username}' exist on starting platform '{starting_plat}', and what public profile information is available?",
                question_type=QuestionType.ENTITY_DISCOVERY,
                priority=1.0,
                is_critical=True,
                related_entities=[username],
                specialist_requirements=["identity"],
                required_evidence=[f"Public profile data or 404 confirmation for '{username}' on '{starting_plat}'"],
            )
            q_candidates = InvestigationQuestion(
                question_text=f"What candidate accounts or public references exist for identifier '{username}' across external platforms?",
                question_type=QuestionType.ENTITY_DISCOVERY,
                priority=0.90,
                is_critical=True,
                dependencies=[q_starting.question_id],
                related_entities=[username],
                specialist_requirements=["identity"],
                required_evidence=[f"External platform discovery records and provenance for '{username}'"],
            )
            q_equiv = InvestigationQuestion(
                question_text=f"Which candidate accounts correlate to target identity '{username}' versus representing ambiguous collisions or distinct individuals?",
                question_type=QuestionType.RELATIONSHIP_VERIFICATION,
                priority=0.85,
                is_critical=False,
                dependencies=[q_candidates.question_id],
                related_entities=[username],
                specialist_requirements=["identity"],
                required_evidence=[f"Corroborating biographical, project, or contextual evidence for '{username}'"],
            )
            q_privacy = InvestigationQuestion(
                question_text=f"What access boundaries apply to discovered accounts of '{username}' (e.g. private Instagram profile), and was private content accessed?",
                question_type=QuestionType.CONTRADICTION_RESOLUTION,
                priority=0.80,
                is_critical=False,
                dependencies=[q_starting.question_id],
                related_entities=[username],
                specialist_requirements=["identity"],
                required_evidence=[f"Access control classification distinguishing public metadata from private content for '{username}'"],
            )

            for q in [q_starting, q_candidates, q_equiv, q_privacy]:
                state.questions[q.question_id] = q.model_dump()
                state.unresolved_questions.append(q.question_id)
                root_branch.questions.append(q.question_id)

            hyp_ident = InvestigationHypothesis(
                proposition=f"Discovered candidate accounts for '{username}' represent public-source identity hypotheses without assuming identity equivalence across platforms or bypassing access controls.",
                related_question_id=q_starting.question_id,
                related_entities=[username],
                supporting_evidence_requirements=[f"Public source profile records with cryptographic provenance for '{username}'"],
                refuting_evidence_requirements=[f"Confirmed non-existence, conflicting biographical data, or access restrictions for '{username}'"],
            )
            state.hypotheses[hyp_ident.hypothesis_id] = hyp_ident.model_dump()

            state.information_gaps.append(
                InformationGap(
                    description=f"Starting account profile for '{username}' on '{starting_plat}'",
                    target_entity=username,
                    target_attribute="starting_account_profile",
                    priority=1.0,
                    is_critical=True,
                    related_question_id=q_starting.question_id,
                )
            )
            state.information_gaps.append(
                InformationGap(
                    description=f"Cross-platform candidate profile links for '{username}'",
                    target_entity=username,
                    target_attribute="cross_platform_candidates",
                    priority=0.90,
                    is_critical=True,
                    related_question_id=q_candidates.question_id,
                )
            )

        elif domain == "corporate":
            # Corporate / Default Benchmark Domain
            q_corp = InvestigationQuestion(
                question_text=f"What is the registered legal entity, jurisdiction, and regulatory standing of {primary_entity}?",
                question_type=QuestionType.ENTITY_DISCOVERY,
                priority=1.0,
                is_critical=True,
                related_entities=[primary_entity],
                specialist_requirements=["corporate"],
                temporal_context={"as_of_date": as_of_date} if as_of_date else None,
                required_evidence=[
                    f"Official commercial registry or regulatory filing confirming {primary_entity}"
                ],
            )
            q_subs = InvestigationQuestion(
                question_text=f"What active operating subsidiaries or corporate vehicles are controlled by {primary_entity}?",
                question_type=QuestionType.RELATIONSHIP_VERIFICATION,
                priority=0.85,
                is_critical=False,
                dependencies=[q_corp.question_id],
                related_entities=[primary_entity],
                specialist_requirements=["corporate"],
                required_evidence=[
                    f"SEC Exhibit 21 schedule or Companies House ownership disclosure for {primary_entity}"
                ],
            )
            q_exec = InvestigationQuestion(
                question_text=f"Who are the key executive officers and operational leaders of {primary_entity}?",
                question_type=QuestionType.OFFICER_TENURE,
                priority=0.90,
                is_critical=True,
                dependencies=[q_corp.question_id],
                related_entities=[primary_entity],
                specialist_requirements=["corporate", "identity"],
                temporal_context={"as_of_date": as_of_date} if as_of_date else None,
                required_evidence=[
                    f"Regulatory leadership disclosure or statutory officer filing for {primary_entity}"
                ],
            )
            q_infra = InvestigationQuestion(
                question_text=f"What public infrastructure domains, SAN certificates, and network assets are registered to {primary_entity}?",
                question_type=QuestionType.INFRASTRUCTURE_ATTRIBUTION,
                priority=0.75,
                is_critical=False,
                dependencies=[q_corp.question_id],
                related_entities=[primary_entity],
                specialist_requirements=["infrastructure"],
                required_evidence=[
                    f"DNS zone, Certificate Transparency log, or WHOIS record for {primary_entity}"
                ],
            )
            q_obj = InvestigationQuestion(
                question_text=objective,
                question_type=QuestionType.ENTITY_DISCOVERY,
                priority=1.0,
                is_critical=True,
                related_entities=target_entities,
                specialist_requirements=["corporate"],
                temporal_context={"as_of_date": as_of_date} if as_of_date else None,
                required_evidence=[
                    f"Authoritative regulatory or technical records addressing: {objective}"
                ],
            )

            for q in [q_obj, q_corp, q_subs, q_exec, q_infra]:
                state.questions[q.question_id] = q.model_dump()
                state.unresolved_questions.append(q.question_id)
                root_branch.questions.append(q.question_id)

            hyp_legal = InvestigationHypothesis(
                proposition=f"{primary_entity} exists as an active legitimate legal entity in its primary jurisdiction.",
                related_question_id=q_corp.question_id,
                related_entities=[primary_entity],
                supporting_evidence_requirements=[
                    f"Authoritative registry filing (SEC, Companies House, or state registry) for {primary_entity}"
                ],
                refuting_evidence_requirements=[
                    f"Certificate of dissolution, revocation, or confirmed lookalike status for {primary_entity}"
                ],
            )
            state.hypotheses[hyp_legal.hypothesis_id] = hyp_legal.model_dump()

            state.information_gaps.append(
                InformationGap(
                    description=f"Jurisdictional legal entity status of {primary_entity}",
                    target_entity=primary_entity,
                    target_attribute="legal_entity_bounds",
                    priority=1.0,
                    is_critical=True,
                    related_question_id=q_corp.question_id,
                )
            )
            state.information_gaps.append(
                InformationGap(
                    description=f"Executive leadership roster for {primary_entity}",
                    target_entity=primary_entity,
                    target_attribute="executive_officers",
                    priority=0.9,
                    is_critical=True,
                    related_question_id=q_exec.question_id,
                )
            )

        else:
            # Generic / Unrecognized / Interdisciplinary Domain Decomposition
            q_obj = InvestigationQuestion(
                question_text=objective,
                question_type=QuestionType.ENTITY_DISCOVERY,
                priority=1.0,
                is_critical=True,
                related_entities=target_entities,
                specialist_requirements=["none"],
                required_evidence=[f"Authoritative published sources and empirical documentation addressing: {objective}"],
            )
            q_core = InvestigationQuestion(
                question_text=f"What are the foundational concepts, core mechanisms, and defining principles of {primary_entity}?",
                question_type=QuestionType.ENTITY_DISCOVERY,
                priority=0.95,
                is_critical=True,
                related_entities=[primary_entity],
                specialist_requirements=["none"],
                required_evidence=[f"Authoritative reference documentation or foundational analyses regarding {primary_entity}"],
            )
            q_rel = InvestigationQuestion(
                question_text=f"What contextual relationships, observed effects, and dependencies connect {primary_entity} with its operating environment?",
                question_type=QuestionType.RELATIONSHIP_VERIFICATION,
                priority=0.90,
                is_critical=False,
                dependencies=[q_core.question_id],
                related_entities=[primary_entity],
                specialist_requirements=["none"],
                required_evidence=[f"Empirical observations, documented case studies, or field analyses regarding {primary_entity}"],
            )
            q_ev = InvestigationQuestion(
                question_text=f"What documented findings, empirical data, and consensus outcomes are established regarding {primary_entity}?",
                question_type=QuestionType.RELATIONSHIP_VERIFICATION,
                priority=0.85,
                is_critical=False,
                dependencies=[q_core.question_id],
                related_entities=[primary_entity],
                specialist_requirements=["none"],
                required_evidence=[f"Documented studies, data reports, or authoritative reviews regarding {primary_entity}"],
            )
            q_lim = InvestigationQuestion(
                question_text=f"What unresolved uncertainties, contradictory evidence, and boundary conditions remain for {primary_entity}?",
                question_type=QuestionType.CONTRADICTION_RESOLUTION,
                priority=0.80,
                is_critical=False,
                dependencies=[q_core.question_id],
                related_entities=[primary_entity],
                specialist_requirements=["none"],
                required_evidence=[f"Critical evaluations, boundary condition analyses, or identified evidence gaps regarding {primary_entity}"],
            )

            for q in [q_obj, q_core, q_rel, q_ev, q_lim]:
                state.questions[q.question_id] = q.model_dump()
                state.unresolved_questions.append(q.question_id)
                root_branch.questions.append(q.question_id)

            hyp_gen = InvestigationHypothesis(
                proposition=f"The primary mechanisms and empirical effects of {primary_entity} can be identified and substantiated through documented evidence.",
                related_question_id=q_core.question_id,
                related_entities=[primary_entity],
                supporting_evidence_requirements=[f"Authoritative documentation or empirical findings substantiating {primary_entity}"],
                refuting_evidence_requirements=[f"Contradictory findings or lack of empirical substantiation regarding {primary_entity}"],
            )
            state.hypotheses[hyp_gen.hypothesis_id] = hyp_gen.model_dump()

            state.information_gaps.append(
                InformationGap(
                    description=f"Core mechanisms and principles of {primary_entity}",
                    target_entity=primary_entity,
                    target_attribute="core_mechanisms",
                    priority=1.0,
                    is_critical=True,
                    related_question_id=q_core.question_id,
                )
            )
            state.information_gaps.append(
                InformationGap(
                    description=f"Empirical outcomes and documented findings for {primary_entity}",
                    target_entity=primary_entity,
                    target_attribute="empirical_outcomes",
                    priority=0.85,
                    is_critical=False,
                    related_question_id=q_ev.question_id,
                )
            )

        state.record_audit(
            action_type="INVESTIGATION_INITIALIZED",
            details={
                "objective": objective,
                "domain": domain,
                "initial_questions_count": len(state.questions),
                "initial_hypotheses_count": len(state.hypotheses),
                "primary_entity": primary_entity,
            },
            rationale=f"Decomposed objective into initial question topology for {domain} domain.",
        )
        return state

    def select_next_actions(
        self,
        state: InvestigationState,
        limit: int = 3,
    ) -> list[ResearchAction]:
        """Identify unresolved questions with satisfied dependencies and plan ranked actions."""
        resolved_ids = set(state.resolved_questions)
        candidate_actions: list[ResearchAction] = []

        # Iterate over open questions
        for q_id in state.unresolved_questions:
            q_dict = state.questions.get(q_id)
            if not q_dict:
                continue
            q = InvestigationQuestion.model_validate(q_dict)

            # Check dependencies
            if q.is_blocked(resolved_ids):
                continue

            # Requirement-based capability matching
            cap_candidates = self.matcher.match(
                question=q,
                state=state,
                capabilities=self.registry.list(include_inactive=False),
                max_candidates=4,
            )
            attempted_impls = {
                a.get("implementation_id")
                for a in state.research_actions
                if a.get("question_id") == q.question_id and a.get("implementation_id")
            }
            top_cand = None
            for cand in cap_candidates:
                if cand.implementation_id not in attempted_impls:
                    top_cand = cand
                    break
            if not top_cand and cap_candidates:
                top_cand = cap_candidates[0]

            cap_id = top_cand.capability_id if top_cand else None
            impl_id = top_cand.implementation_id if top_cand else None

            # Resolve implementation through ImplementationSelector
            if top_cand:
                cap_def = self.registry.get(top_cand.capability_id)
                if cap_def:
                    from argus.competition.implementation_selector import ImplementationSelector
                    selector = ImplementationSelector(self.registry)
                    selected_impl = selector.select_implementation(cap_def, question=q)
                    impl_id = selected_impl.implementation_id

            # Determine specialist (mapping from capability category or fallback)
            if top_cand:
                if top_cand.category.value == "CORPORATE":
                    spec = "corporate"
                elif top_cand.category.value == "INFRASTRUCTURE":
                    spec = "infrastructure"
                elif top_cand.category.value == "IDENTITY":
                    spec = "identity"
                elif top_cand.category.value == "SANCTIONS_AND_OFFSHORE":
                    spec = "sanctions"
                elif top_cand.category.value == "GENERAL_RESEARCH":
                    spec = "none"
                else:
                    spec = q.specialist_requirements[0] if q.specialist_requirements else "none"
            else:
                spec = q.specialist_requirements[0] if q.specialist_requirements else "none"

            # Determine query text
            ents = q.related_entities or list(state.entities.keys())
            ent_str = " ".join(ents[:2]) if ents else state.objective

            # Check if there are discovered candidate sources awaiting content retrieval
            unretrieved = [
                s for s in getattr(state, "discovered_sources", [])
                if s.get("status") == "DISCOVERED"
            ]
            fetched_urls = {
                (a.get("parameters", {}).get("url") or a.get("query"))
                for a in state.research_actions
                if a.get("action_type") == ActionType.FETCH
            }
            unfetched_for_q = [
                s for s in unretrieved
                if s.get("url") and s["url"] not in fetched_urls
                and (
                    not q.related_entities
                    or any(re.search(rf"\b{re.escape(e)}\b", f"{s.get('title', '')} {s.get('snippet', '')}", re.IGNORECASE) for e in q.related_entities)
                    or not any(re.search(rf"\b{re.escape(e)}\b", f"{s2.get('title', '')} {s2.get('snippet', '')}", re.IGNORECASE) for s2 in unretrieved for e in q.related_entities)
                )
            ]

            if unfetched_for_q and spec in ("none", ""):
                cand_source = unfetched_for_q[0]
                fetch_url = cand_source["url"]
                fetch_action = ResearchAction(
                    question_id=q.question_id,
                    action_type=ActionType.FETCH,
                    rationale=f"Retrieve full source content from candidate source '{cand_source.get('title', fetch_url)}' ({fetch_url}) to evaluate evidence requirements for Question: {q.question_text}",
                    specialist="none",
                    capability_id="general_web_research",
                    implementation_id="impl_argus_generalist_v1",
                    target_entities=q.related_entities,
                    query=fetch_url,
                    parameters={"url": fetch_url, "doc_id": cand_source.get("doc_id")},
                    priority=min(1.0, q.priority + 0.05),
                    expected_information_gain=0.80,
                    evidence_requirements=q.required_evidence,
                )
                candidate_actions.append(fetch_action)
                continue

            # Extract distinctive key terms from objective to keep research tightly focused
            stop_words = {
                "the", "a", "an", "per", "what", "which", "who", "identify", "determine", "investigate",
                "verify", "active", "current", "their", "from", "with", "that", "when", "for", "and",
                "or", "to", "in", "of", "at", "is", "was", "by", "as", "how", "does", "did", "this"
            }
            obj_words = [
                w.strip(".,;:\"'?") for w in state.objective.split()
                if len(w) > 1 and w.lower() not in stop_words
            ]
            distinctive_terms = " ".join(obj_words[:8])

            if spec == "identity":
                action_type = ActionType.INVESTIGATE_SPECIALIST
                clean_target = (q.related_entities[0] if q.related_entities else ent_str).strip()
                query_str = clean_target
                cap_id = "identity_resolution"
                impl_id = "impl_identity_probe_specialist_v1"
            elif spec == "sanctions":
                action_type = ActionType.QUERY_SOURCE
                query_str = f"{ent_str} sanctions screening beneficial ownership PEP offshore"
            elif q.question_type == QuestionType.ENTITY_DISCOVERY:
                action_type = ActionType.QUERY_SOURCE if spec == "corporate" else ActionType.SEARCH
                if spec == "corporate":
                    query_str = f"{ent_str} {distinctive_terms} commercial registry legal entity"
                else:
                    query_str = f"{ent_str} {distinctive_terms} {q.question_text}"
            elif q.question_type == QuestionType.OFFICER_TENURE:
                action_type = ActionType.INVESTIGATE_SPECIALIST if "corporate" in q.specialist_requirements else ActionType.SEARCH
                query_str = f"{ent_str} {distinctive_terms} executive officers leadership"
            elif q.question_type == QuestionType.RELATIONSHIP_VERIFICATION:
                action_type = ActionType.INVESTIGATE_RELATIONSHIP
                if spec == "corporate":
                    query_str = f"{ent_str} {distinctive_terms} subsidiaries schedule"
                else:
                    query_str = f"{ent_str} {distinctive_terms} {q.question_text}"
            elif q.question_type == QuestionType.INFRASTRUCTURE_ATTRIBUTION:
                action_type = ActionType.INVESTIGATE_SPECIALIST
                spec = "infrastructure"
                clean_infra = (q.related_entities[0] if q.related_entities else ent_str).strip()
                query_str = clean_infra
                cap_id = "infrastructure_discovery"
                impl_id = "impl_infrastructure_probe_specialist_v1"
            elif q.question_type == QuestionType.CONTRADICTION_RESOLUTION:
                action_type = ActionType.SEEK_CONTRADICTION
                if spec == "corporate":
                    query_str = f"{ent_str} {distinctive_terms} restatement amendment filing correction"
                else:
                    query_str = f"{ent_str} {q.question_text}"
            else:
                action_type = ActionType.SEARCH
                query_str = f"{ent_str} {q.question_text}"

            # Query diversification: adapt search if primary query was already executed
            prior_queries = {
                a.get("query", "").strip().lower()
                for a in state.research_actions
                if a.get("question_id") == q.question_id
            }
            if query_str.strip().lower() in prior_queries:
                alt_candidates = [
                    f"{q.question_text}",
                    f"{ent_str} {' '.join(q.required_evidence[:2])}" if q.required_evidence else "",
                    f"{ent_str} {' '.join(distinctive_terms.split()[:4])}",
                    f"{q.question_text} {state.objective[:40]}",
                ]
                for alt_q in alt_candidates:
                    if alt_q and alt_q.strip().lower() not in prior_queries:
                        query_str = alt_q
                        break

            action_params = {}
            if spec == "identity":
                clean_target = (q.related_entities[0] if q.related_entities else ent_str).strip()
                action_params = {
                    "identifier": clean_target,
                    "username": state.objective_contract.get("username") or clean_target,
                    "starting_platform": state.objective_contract.get("starting_platform"),
                    "target_entity_context": state.objective_contract.get("known_context", {}),
                }
            elif spec == "infrastructure":
                clean_infra = (q.related_entities[0] if q.related_entities else ent_str).strip()
                action_params = {
                    "domain": clean_infra,
                    "target_domain": clean_infra,
                    "query": clean_infra,
                }

            action = ResearchAction(
                question_id=q.question_id,
                action_type=action_type,
                rationale=f"Capability '{cap_id or spec}' selected to resolve Question: {q.question_text}",
                specialist=spec,
                capability_id=cap_id,
                implementation_id=impl_id,
                estimated_cost=top_cand.estimated_cost if top_cand else 0.0015,
                target_entities=q.related_entities,
                query=query_str,
                parameters=action_params,
                priority=q.priority,
                evidence_requirements=q.required_evidence,
            )

            # Estimate expected value
            self.estimator.estimate_action_value(action, state, q)
            candidate_actions.append(action)

        # Sort candidate actions by expected gain descending
        candidate_actions.sort(key=lambda a: a.expected_information_gain, reverse=True)
        return candidate_actions[:limit]

    def handle_contradiction(
        self,
        state: InvestigationState,
        claim_a: dict[str, Any],
        claim_b: dict[str, Any],
    ) -> InvestigationQuestion:
        """Create a contradiction record and spawn a targeted resolution question."""
        conflict_id = f"contra_{uuid.uuid4().hex[:8]}"
        conflict_record = {
            "contradiction_id": conflict_id,
            "claim_a": claim_a,
            "claim_b": claim_b,
            "status": "UNRESOLVED",
        }
        state.contradictions.append(conflict_record)

        # Spawn targeted resolution question
        subj = claim_a.get("subject", "Entity")
        pred = claim_a.get("predicate", "attribute")
        contra_spec = "corporate" if "corporate" in state.objective.lower() or "inc" in state.objective.lower() else "none"
        contra_q = InvestigationQuestion(
            question_text=f"Resolve contradictory claims regarding {subj} [{pred}]: '{claim_a.get('object')}' vs '{claim_b.get('object')}'. Which claim is authoritatively valid?",
            question_type=QuestionType.CONTRADICTION_RESOLUTION,
            priority=1.0,
            is_critical=True,
            related_entities=[subj],
            specialist_requirements=[contra_spec] if contra_spec != "none" else [],
            required_evidence=[
                f"Authoritative primary records or superseding official statement resolving conflict on {subj} [{pred}]"
            ],
        )

        state.questions[contra_q.question_id] = contra_q.model_dump()
        state.unresolved_questions.append(contra_q.question_id)

        state.record_audit(
            action_type="CONTRADICTION_DETECTED",
            details={
                "contradiction_id": conflict_id,
                "question_id": contra_q.question_id,
                "claim_a_id": claim_a.get("claim_id"),
                "claim_b_id": claim_b.get("claim_id"),
            },
            rationale=f"Contradiction identified on {subj} [{pred}]; spawned targeted resolution question.",
        )
        return contra_q
