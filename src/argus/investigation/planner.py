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
from argus.investigation.objective_parser import (
    EnumerationObjective,
    parse_enumeration_objective,
    refine_object_from_evidence,
)
from argus.investigation.question import InvestigationQuestion, QuestionStatus, QuestionType
from argus.investigation.question_intent import ObjectiveIntent, classify_intent, topic_phrase
from argus.investigation.state import InformationGap, InvestigationState
from argus.capability_registry.registry import CapabilityRegistry
from argus.capability_registry.matcher import CapabilityMatcher
from argus.capability_registry.defaults import get_default_capabilities

logger = logging.getLogger(__name__)


def _has_term(text: str, term: str) -> bool:
    """Whole-word match ("api" is not found in "capital"); a trailing * matches a word prefix."""
    if term.endswith("*"):
        return re.search(rf"(?<!\w){re.escape(term[:-1])}", text) is not None
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text) is not None


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
            _has_term(obj_lower, k)
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
        is_entity_inquiry = any(
            _has_term(obj_lower, k)
            for k in [
                "find everything about",
                "who is",
                "background on",
                "tell me about",
                "profile of",
                "executive",
                "founder",
                "leadership",
            ]
        )

        technical_keywords = [
            "database", "databases", "api", "apis", "sdk", "open-source", "open source", "licensing",
            "framework", "programming language", "query engine", "latency", "throughput",
            "performance evidence", "operational complexity", "source code",
        ]
        if is_entity_inquiry and not any(_has_term(obj_lower, k) for k in technical_keywords + ["benchmark"]):
            return "corporate"
        if not is_entity_inquiry:
            technical_keywords.extend(["software", "benchmark", "benchmarks"])

        if any(_has_term(obj_lower, k) for k in technical_keywords):
            return "technical"

        if any(
            _has_term(obj_lower, k)
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
            _has_term(obj_lower, k)
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
            _has_term(obj_lower, k)
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
            _has_term(obj_lower, k)
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
                "incorporat*",
                "executive officers",
                "ownership disclosure",
                "jurisdiction",
                "business inquiries",
                "director",
                "c-suite",
                "officer tenure",
                "ciso",
                "svp",
                "vp",
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

        # List-style objectives ("organizations that use X in Y") get an explicit
        # structured interpretation instead of capitalized-word entity guessing.
        # Explicit caller hints (target entities, domain, custom questions) take precedence.
        if not (
            contract.get("target_entities")
            or contract.get("domain_hint")
            or contract.get("initial_questions") is not None
            or domain == "identity"
        ):
            enumeration = parse_enumeration_objective(objective)
            if enumeration is not None:
                return self._initialize_enumeration(state, root_branch, enumeration)

        # 2. Deconstruct objective into core entity targets and questions
        target_entities = contract.get("target_entities") or []
        if not isinstance(target_entities, list):
            raise ValueError("Contract target_entities must be a list.")

        intent = classify_intent(objective)
        if not target_entities:
            # Subjects are the objective's proper-noun names (question words, roles and
            # places excluded); with none, the subject is the objective's topic phrase.
            target_entities = list(intent.subjects)
            if not target_entities:
                clean_target = re.sub(
                    r"^(?:find\s+(?:everything|out|all)?\s*(?:about)?|tell\s+me\s+about|who\s+is|background\s+on|investigate|research|trace|verify|search\s+for)\s+",
                    "",
                    objective.strip(),
                    flags=re.IGNORECASE,
                ).strip()
                clean_target = topic_phrase(clean_target)
                if clean_target:
                    target_entities = [clean_target.title()]

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

        subject_list = " and ".join(target_entities[:3]) if target_entities else primary_entity

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
            # One question per facet the objective names ("compare A and B on X, Y and Z"),
            # plus the standard technical facets; the objective itself stays the critical question.
            named = [f for f in intent.facets if f]
            facet_questions: list[InvestigationQuestion] = []
            for facet in named:
                facet_questions.append(InvestigationQuestion(
                    question_text=f"What do documentation and independent sources report about the {facet} of {subject_list}?",
                    question_type=QuestionType.ENTITY_DISCOVERY,
                    priority=0.9,
                    is_critical=False,
                    related_entities=list(target_entities),
                    specialist_requirements=["none"],
                    required_evidence=[f"Official documentation or reproducible evaluation covering the {facet} of {subject_list}"],
                ))
            standard = [
                ("capabilities", f"What capabilities, interfaces and documented limits does {subject_list} have?", "Official technical documentation"),
                ("complex", f"What deployment footprint and operational complexity does {subject_list} involve?", "Deployment guides and operations documentation"),
                ("licens", f"What license and usage terms govern {subject_list}?", "License file or repository license declaration"),
                ("perform", f"What performance evidence (benchmarks, throughput, latency) is documented for {subject_list}?", "Reproducible benchmark results"),
            ]
            for _stem, text, evidence in standard:
                facet_questions.append(InvestigationQuestion(
                    question_text=text,
                    question_type=QuestionType.RELATIONSHIP_VERIFICATION,
                    priority=0.85,
                    is_critical=False,
                    related_entities=list(target_entities),
                    specialist_requirements=["none"],
                    required_evidence=[f"{evidence} for {subject_list}"],
                ))

            for q in [q_obj, *facet_questions]:
                state.questions[q.question_id] = q.model_dump()
                state.unresolved_questions.append(q.question_id)
                root_branch.questions.append(q.question_id)

            first = facet_questions[0]
            hyp_tech = InvestigationHypothesis(
                proposition=f"Documented evidence describes {subject_list} on the requested technical facets.",
                related_question_id=first.question_id,
                related_entities=list(target_entities),
                supporting_evidence_requirements=[f"Technical documentation or benchmark covering {subject_list}"],
                refuting_evidence_requirements=[f"Documentation showing {subject_list} lacks the described capabilities"],
            )
            state.hypotheses[hyp_tech.hypothesis_id] = hyp_tech.model_dump()

            state.information_gaps.append(
                InformationGap(
                    description=f"Requested technical facets for {subject_list}",
                    target_entity=primary_entity,
                    target_attribute="technical_facets",
                    priority=1.0,
                    is_critical=True,
                    related_question_id=first.question_id,
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

        elif domain == "generic" and intent.kind in self._DIRECT_QUESTION_KINDS:
            # A direct question (why / how / who / compare / what changed / is-it / find the X of)
            # is decomposed by what it asks, not by a fixed topic template.
            q_obj = InvestigationQuestion(
                question_text=objective,
                question_type=QuestionType.GENERAL,
                priority=1.0,
                is_critical=True,
                related_entities=list(target_entities),
                specialist_requirements=["none"],
                search_queries=self._intent_queries(intent, target_entities, objective)[:2],
                required_evidence=[f"Published sources that directly answer: {objective}"],
            )
            sub_questions = self._intent_questions(intent, target_entities, objective)
            for q in [q_obj, *sub_questions]:
                state.questions[q.question_id] = q.model_dump()
                state.unresolved_questions.append(q.question_id)
                root_branch.questions.append(q.question_id)

            hyp_direct = InvestigationHypothesis(
                proposition=f"Published sources answer the question: {objective}",
                related_question_id=q_obj.question_id,
                related_entities=list(target_entities),
                supporting_evidence_requirements=[f"Sources that directly state an answer to: {objective}"],
                refuting_evidence_requirements=[f"Sources that contradict the answer or show it is not publicly documented: {objective}"],
            )
            state.hypotheses[hyp_direct.hypothesis_id] = hyp_direct.model_dump()
            state.information_gaps.append(
                InformationGap(
                    description=f"Direct answer ({intent.kind}) for: {objective}",
                    target_entity=primary_entity,
                    target_attribute=f"{intent.kind}_answer",
                    priority=1.0,
                    is_critical=True,
                    related_question_id=q_obj.question_id,
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

        self._scope_template_criticality(state, objective, target_entities)

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

    _DIRECT_QUESTION_KINDS = frozenset({
        "causal", "mechanism", "comparison", "change", "yes_no", "role", "attribute", "summary", "listing",
    })

    @staticmethod
    def _intent_queries(intent: ObjectiveIntent, subjects: list[str], objective: str) -> list[str]:
        """Short web queries built from the subjects and the words the objective asks about."""
        base = " ".join([*subjects[:2], intent.focus, *intent.periods]).strip() or topic_phrase(objective)
        extra = {
            "causal": ["cause", "investigation findings"],
            "mechanism": ["how it works", "explained"],
            "comparison": ["comparison", "vs"],
            "change": ["changes", "amendments"],
            "yes_no": ["", "confirmed"],
            "role": ["", "announced"],
            "attribute": ["", "official"],
            "summary": ["", "latest"],
            "listing": ["", "list"],
        }.get(intent.kind, [""])
        out: list[str] = []
        for word in extra:
            q = re.sub(r"\s+", " ", f"{base} {word}").strip()
            if q and q not in out:
                out.append(q)
        return out

    def _intent_questions(self, intent: ObjectiveIntent, subjects: list[str], objective: str) -> list[InvestigationQuestion]:
        """Sub-questions that follow from the form of a direct question."""
        topic = " ".join([*subjects[:3], intent.focus]).strip() or topic_phrase(objective)
        subject_text = " and ".join(subjects[:3]) or topic
        when = f" ({' to '.join(intent.periods)})" if intent.periods else ""
        specs: list[tuple[str, QuestionType, list[str]]] = []
        if intent.kind == "causal":
            event = intent.scope or topic
            bare_event = re.sub(r"^the\s+", "", event)
            specs = [
                (f"What causes or reasons do official investigations and reliable sources give for {event}?", QuestionType.GENERAL, [f"{bare_event} cause", f"{bare_event} investigation report"]),
                (f"What sequence of events led to {event}?", QuestionType.TEMPORAL_STATE, [f"{bare_event} timeline"]),
                (f"Which explanations for {event} are disputed between sources?", QuestionType.CONTRADICTION_RESOLUTION, [f"{bare_event} disputed cause"]),
            ]
        elif intent.kind == "mechanism":
            specs = [
                (f"What are the main components or steps of {subject_text}?", QuestionType.GENERAL, [f"{subject_text} how it works"]),
                (f"What limitations or open questions are documented for {subject_text}?", QuestionType.GENERAL, [f"{subject_text} limitations"]),
            ]
        elif intent.kind == "comparison":
            facets = intent.facets or ["capabilities and documented limits"]
            for_context = f" for {intent.context}" if intent.context else ""
            for subject in subjects[:3] or [topic]:
                for facet in facets:
                    specs.append((f"What do sources report about the {facet} of {subject}{for_context}?", QuestionType.GENERAL, [f"{subject} {facet} {intent.context}".strip()]))
            specs.append((f"Which sources compare {subject_text} directly, and what differences do they report?", QuestionType.GENERAL, [f"{' vs '.join(subjects[:3]) or topic} {' '.join(facets)}".strip()]))
        elif intent.kind == "change":
            specs = [
                (f"What specific provisions or elements of {subject_text} changed{when}, and when?", QuestionType.TEMPORAL_STATE, [f"{subject_text} changes {' '.join(intent.periods)}".strip()]),
                (f"What did the earlier and later versions of {subject_text} each say on the changed points?", QuestionType.TEMPORAL_STATE, [f"{subject_text} final text vs draft"]),
            ]
        elif intent.kind == "yes_no":
            question = objective.strip().rstrip("?")
            specs = [
                (f"What evidence supports a yes answer to \"{question}?\"", QuestionType.GENERAL, [f"{topic}"]),
                (f"What evidence supports a no answer to \"{question}?\"", QuestionType.NEGATIVE_VERIFICATION, [f"{topic} denied"]),
            ]
        elif intent.kind == "role":
            role = " ".join(intent.facets) or intent.focus or "role"
            specs = [
                (f"Who is named as {role} of {subject_text} in official or recent sources?", QuestionType.OFFICER_TENURE, [f"{subject_text} {role}"]),
                (f"When did each named person take or leave that role at {subject_text}?", QuestionType.TEMPORAL_STATE, [f"{subject_text} {role} appointed"]),
            ]
        elif intent.kind == "attribute":
            scope = intent.scope or subject_text
            for facet in intent.facets or [intent.focus]:
                verb = "are" if facet.endswith("s") and not facet.endswith("ss") else "is"
                specs.append((f"What {verb} the {facet} of {scope}, and as of what date?", QuestionType.GENERAL, [f"{scope} {facet}"]))
        elif intent.kind == "summary":
            specs = [
                (f"Which {intent.scope or topic} are documented, with dates and parties?", QuestionType.GENERAL, [intent.scope or topic]),
                (f"What is the current status or outcome of each of the {intent.scope or topic}?", QuestionType.TEMPORAL_STATE, [f"{intent.scope or topic} status outcome"]),
            ]
        elif intent.kind == "listing":
            specs = [
                (f"Which {intent.scope or 'items'} do sources name for \"{objective.strip().rstrip('?')}?\", each with its source?", QuestionType.GENERAL, [topic]),
                (f"Which of the named {intent.scope or 'items'} are confirmed by more than one independent source?", QuestionType.GENERAL, []),
            ]
        out = []
        for text, qtype, queries in specs:
            out.append(InvestigationQuestion(
                question_text=text,
                question_type=qtype,
                priority=0.9,
                is_critical=False,
                related_entities=list(subjects),
                specialist_requirements=["none"],
                search_queries=[q for q in queries if q],
                required_evidence=[f"Published sources addressing: {text}"],
            ))
        return out

    # Words that carry no topic: question scaffolding shared by every template.
    _CRITICALITY_STOPWORDS = frozenset({
        "what", "which", "who", "whom", "whose", "when", "where", "does", "have", "with", "that",
        "this", "these", "those", "from", "into", "regarding", "about", "their", "there", "each",
        "remain", "remaining", "documented", "established", "public", "known", "investigate",
        "identify", "determine", "analyze", "analyse", "examine", "verify", "trace", "conduct",
        "research", "evaluate", "resolve", "reconstruct", "find", "list", "held", "during",
        "between", "against", "under", "over", "whether", "including", "include", "starting",
    })

    @classmethod
    def _topic_terms(cls, text: str, exclude: set[str]) -> set[str]:
        """Content-word stems of ``text`` (5-char prefixes), minus scaffolding and entity names."""
        out = set()
        for w in re.findall(r"[a-z][a-z\-]{3,}", text.lower()):
            if w in cls._CRITICALITY_STOPWORDS or w in exclude:
                continue
            out.add(w[:5])
        return out

    def _scope_template_criticality(self, state: InvestigationState, objective: str, target_entities: list[str]) -> None:
        """Keep a template sub-question critical only if it overlaps the user's objective.

        Domain templates add generic sub-questions (e.g. "Who are the key executive officers
        of X?") and mark several critical. A question the user never asked must not decide
        whether the objective is satisfied. The objective's own question stays critical;
        another critical question stays critical only when it shares at least two topic
        terms with the objective (entity names excluded, since every template repeats them).
        The questions themselves are kept and still researched.
        """
        entity_words = {
            w for e in target_entities for w in re.findall(r"[a-z][a-z\-]{3,}", str(e).lower())
        }
        objective_terms = self._topic_terms(objective, entity_words)
        demoted: list[dict[str, Any]] = []
        for qid, q in state.questions.items():
            if not q.get("is_critical"):
                continue
            text = q.get("question_text", "")
            if text.strip() == objective.strip():
                continue
            shared = self._topic_terms(text, entity_words) & objective_terms
            if len(shared) >= 2:
                continue
            q["is_critical"] = False
            demoted.append({"question_id": qid, "question_text": text, "shared_terms": sorted(shared)})
        if not demoted:
            return
        demoted_ids = {d["question_id"] for d in demoted}
        for gap in state.information_gaps:
            if gap.related_question_id in demoted_ids:
                gap.is_critical = False
        state.record_audit(
            action_type="TEMPLATE_CRITICALITY_SCOPED",
            details={"demoted": demoted},
            rationale=(
                f"{len(demoted)} template question(s) do not share the objective's topic and are "
                "researched as non-critical."
            ),
        )

    def _initialize_enumeration(
        self,
        state: InvestigationState,
        root_branch: InvestigationBranch,
        enum: EnumerationObjective,
    ) -> InvestigationState:
        """Build the question topology for an 'organizations that <relation> <object>' objective."""
        obj = enum.object
        label = enum.answer_label
        geo = f" {enum.geo_phrase()}" if enum.geography else ""

        state.register_entity(name=obj, entity_type="TARGET_OBJECT", metadata={"role": "enumeration_object"})

        q_enum = InvestigationQuestion(
            question_text=enum.question_text(),
            question_type=QuestionType.ENTITY_DISCOVERY,
            priority=1.0,
            is_critical=True,
            related_entities=[obj],
            specialist_requirements=["none"],
            required_evidence=[
                f"Sources naming specific {label}{geo} that use {obj} "
                "(vendor customer disclosures, technographic providers, independent reporting, job postings)"
            ],
            search_queries=enum.discovery_queries() + enum.job_post_queries(),
        )
        q_corr = InvestigationQuestion(
            question_text=self._corroboration_question_text(enum),
            question_type=QuestionType.RELATIONSHIP_VERIFICATION,
            priority=0.85,
            is_critical=False,
            dependencies=[q_enum.question_id],
            related_entities=[obj],
            specialist_requirements=["none"],
            required_evidence=[f"Vendor case studies or independent reporting that name {label} using {obj}"],
            search_queries=enum.corroboration_queries(),
        )
        for q in (q_enum, q_corr):
            state.questions[q.question_id] = q.model_dump()
            state.unresolved_questions.append(q.question_id)
            root_branch.questions.append(q.question_id)

        enum_dict = enum.to_dict()
        enum_dict["question_ids"] = {"discovery": q_enum.question_id, "corroboration": q_corr.question_id}
        state.objective_contract["enumeration_objective"] = enum_dict

        hyp = InvestigationHypothesis(
            proposition=f"{label.capitalize()}{geo} that use {obj} can be named from attributable public sources.",
            related_question_id=q_enum.question_id,
            related_entities=[obj],
            supporting_evidence_requirements=[f"Attributable sources naming {label} that use {obj}{geo}"],
            refuting_evidence_requirements=[f"Sources stating named {label} do not use, or no longer use, {obj}"],
        )
        state.hypotheses[hyp.hypothesis_id] = hyp.model_dump()
        state.information_gaps.append(
            InformationGap(
                description=f"Named {label}{geo} using {obj}",
                target_entity=obj,
                target_attribute="enumerated_organizations",
                priority=1.0,
                is_critical=True,
                related_question_id=q_enum.question_id,
            )
        )

        state.record_audit(
            action_type="OBJECTIVE_INTERPRETED",
            details=enum_dict,
            rationale=(
                f"Interpreted objective as: answer type {enum.answer_type} ({enum.answer_noun}), relation "
                f"{enum.relation}, object '{obj}', geography '{enum.geography or 'unconstrained'}'."
            ),
        )
        state.record_audit(
            action_type="INVESTIGATION_INITIALIZED",
            details={
                "objective": state.objective,
                "domain": "enumeration",
                "initial_questions_count": len(state.questions),
                "initial_hypotheses_count": len(state.hypotheses),
                "primary_entity": obj,
            },
            rationale="Decomposed enumeration objective into discovery and corroboration questions.",
        )
        return state

    @staticmethod
    def _corroboration_question_text(enum: EnumerationObjective) -> str:
        return (
            f"Which of the reported {enum.answer_label} using {enum.object_name} are confirmed by the vendor "
            "or an independent publisher, rather than only by technographic aggregators?"
        )

    def refine_objective_from_evidence(self, state: InvestigationState) -> bool:
        """Qualify an enumeration object with the vendor name retrieved sources attach to it.

        Updates pending questions' search queries so later searches use the
        qualified name. Returns True when the objective changed.
        """
        enum_dict = state.objective_contract.get("enumeration_objective")
        if not enum_dict or enum_dict.get("object_qualified"):
            return False
        enum = EnumerationObjective.from_dict(enum_dict)
        texts = [(str(e.get("url") or ""), f"{e.get('title') or ''} {e.get('snippet') or ''}") for e in state.evidence]
        if not refine_object_from_evidence(enum, texts):
            return False
        new_dict = enum.to_dict()
        new_dict["question_ids"] = enum_dict.get("question_ids", {})
        state.objective_contract["enumeration_objective"] = new_dict
        qids = new_dict["question_ids"]
        for role, text, queries in (
            ("discovery", enum.question_text(), enum.discovery_queries()),
            ("corroboration", self._corroboration_question_text(enum), enum.corroboration_queries()),
        ):
            q_dict = state.questions.get(qids.get(role, ""))
            if q_dict and q_dict.get("question_id") in state.unresolved_questions:
                q_dict["question_text"] = text
                q_dict["search_queries"] = queries
        state.record_audit(
            action_type="OBJECTIVE_REFINED",
            details={"object": enum.object, "object_qualified": enum.object_qualified, "sources": enum.object_qualifier_evidence},
            rationale=f"Retrieved sources consistently name the object '{enum.object_qualified}'.",
        )
        return True

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

            # Questions carrying objective-derived queries are answered by web research,
            # not by registry specialists matched on incidental keywords.
            if q.search_queries:
                spec = "none"
                cap_id = "general_web_research"
                impl_id = "impl_argus_generalist_v1"

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
                # Links the user gave come first, then pages Laya scored as most relevant
                # (unscored pages keep their discovery order).
                def _fetch_rank(src: dict[str, Any]) -> float:
                    if src.get("source_type") == "user_link":
                        return -2.0
                    score = src.get("triage_score")
                    return -(score if isinstance(score, (int, float)) else 0.5)

                cand_source = sorted(unfetched_for_q, key=_fetch_rank)[0]
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

            if q.search_queries:
                used_queries = {a.get("query", "").strip().lower() for a in state.research_actions}
                pending_queries = [sq for sq in q.search_queries if sq.strip().lower() not in used_queries]
                if not pending_queries:
                    # Every focused query has run; do not spend budget on boilerplate variants.
                    continue
                action_type = ActionType.SEARCH
                query_str = pending_queries[0]
            elif spec == "identity":
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
            if query_str.strip().lower() in prior_queries and not q.search_queries:
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
