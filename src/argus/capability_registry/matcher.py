"""Heimdallr V3.1: Requirement-Based Capability Matcher.

Matches investigation questions against registered capabilities:
- Evaluates evidence requirements, question types, entity types, jurisdictions, and temporal needs
- Excludes UNAVAILABLE, DISABLED, and QUARANTINED implementations
- Penalizes and flags DEGRADED implementations
- Produces deterministically ranked CapabilityCandidate recommendations
- NEVER executes capabilities autonomously (planner remains the authority)
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, List, Optional

from argus.capability_registry.models import (
    CapabilityCandidate,
    CapabilityDefinition,
    HealthStatus,
)

if TYPE_CHECKING:
    from argus.investigation.question import InvestigationQuestion
    from argus.investigation.state import InvestigationState

logger = logging.getLogger(__name__)


class CapabilityMatcher:
    """Evaluates question requirements against capabilities and computes ranked recommendations."""

    def __init__(self, fallback_to_general_research: bool = True) -> None:
        self.fallback_to_general_research = fallback_to_general_research

    _JURISDICTIONS = {
        "US": "the United States (US states, SEC, federal agencies)",
        "GB": "the United Kingdom (England, Scotland, Wales, Companies House)",
        "DE": "Germany (GmbH, German registers)",
        "GLOBAL": "no particular country, or a country other than these",
    }

    @staticmethod
    def jurisdiction_rule(text: str) -> str:
        """Whole-word cues only: "us" inside "status" or "sec" inside "second" is not the US."""
        low = text.lower()

        def has(*terms: str) -> bool:
            return any(re.search(rf"(?<![a-z]){re.escape(t)}(?![a-z])", low) for t in terms)

        if has("delaware", "united states", "u.s.", "usa", "sec") or re.search(r"(?<![A-Za-z])US(?![A-Za-z])", text):
            return "US"
        if has("uk", "united kingdom", "companies house", "england", "britain", "scotland", "wales"):
            return "GB"
        if has("gmbh", "germany", "german"):
            return "DE"
        return "GLOBAL"

    def jurisdiction_of(self, text: str) -> str:
        """The country a question concerns, decided by Laya (the whole-word rule without Laya)."""
        from argus.brain.decisions import get_decisions

        return get_decisions().choose(
            "question_jurisdiction", text, "Which country's records does this question concern?",
            self._JURISDICTIONS, self.jurisdiction_rule(text),
        ).answer

    def match(
        self,
        question: InvestigationQuestion,
        state: Optional[InvestigationState] = None,
        capabilities: Optional[List[CapabilityDefinition]] = None,
        max_candidates: int = 5,
    ) -> List[CapabilityCandidate]:
        """Evaluate requirements and return ranked candidate capabilities for an investigation question."""
        if not capabilities:
            return []

        candidates: List[CapabilityCandidate] = []
        q_text = question.question_text.lower()
        q_type_str = question.question_type.value if hasattr(question.question_type, "value") else str(question.question_type)
        required_ev = [r.lower() for r in question.required_evidence]
        temporal_context = question.temporal_context or {}
        has_temporal_req = bool(temporal_context.get("as_of_date") or re.search(r"\b(19\d\d|20\d\d)\b", q_text))
        related_entities = question.related_entities or []

        jurisdiction = self.jurisdiction_of(question.question_text)

        for cap in capabilities:
            # 1. Health & Availability Filter (Fail closed on unhealthy states)
            if cap.status in (HealthStatus.UNAVAILABLE, HealthStatus.DISABLED, HealthStatus.QUARANTINED):
                continue

            matched_reqs: List[str] = []
            unmet_reqs: List[str] = []
            risk_flags: List[str] = []

            if cap.status == HealthStatus.DEGRADED:
                risk_flags.append("CAPABILITY_DEGRADED: Reduced throughput or transient upstream rate-limits.")

            # 2. Evidence Requirement Matching
            ev_score = 0.0
            if required_ev:
                matches_found = 0
                for req in required_ev:
                    if self._cap_satisfies_evidence(cap, req):
                        matches_found += 1
                        matched_reqs.append(f"Evidence: {req}")
                    else:
                        unmet_reqs.append(f"Evidence: {req}")
                ev_score = matches_found / len(required_ev)
            else:
                ev_score = 0.7  # Default neutral score when no explicit evidence requirement declared

            # 3. Question Type & Operation Taxonomy Matching
            q_score = 0.0
            for qt in cap.question_types:
                if self._question_type_matches(qt, q_type_str, cap):
                    q_score = 1.0
                    matched_reqs.append(f"QuestionType: {qt}")
                    break
            if q_score == 0.0:
                # Check semantic alignment between question text and capability operations
                op_hits = sum(1 for op in cap.supported_operations if op.lower().replace("_", " ") in q_text)
                if op_hits > 0:
                    q_score = 0.75
                    matched_reqs.append(f"OperationAlignment: {op_hits} matching operations")
                elif cap.category.value == "GENERAL_RESEARCH":
                    q_score = 0.5  # General research can answer any general question
                else:
                    q_score = 0.1

            # 4. Entity Type Fit
            ent_score = 0.8
            if related_entities:
                # If entities look like domains
                if any("." in ent for ent in related_entities) and "DOMAIN" in cap.entity_types:
                    ent_score = 1.0
                    matched_reqs.append("EntityType: DOMAIN")
                elif any(" " in ent or "corp" in ent.lower() or "ltd" in ent.lower() for ent in related_entities) and "ORGANIZATION" in cap.entity_types:
                    ent_score = 1.0
                    matched_reqs.append("EntityType: ORGANIZATION")
                elif any("dr." in ent.lower() or "mr." in ent.lower() for ent in related_entities) and "PERSON" in cap.entity_types:
                    ent_score = 1.0
                    matched_reqs.append("EntityType: PERSON")

            # 5. Temporal Fit
            temporal_score = 1.0
            if has_temporal_req:
                if "POINT_IN_TIME" in cap.temporal_behavior.upper():
                    temporal_score = 1.0
                    matched_reqs.append("Temporal: Point-in-time restatement aware")
                elif "TIMESTAMP" in cap.temporal_behavior.upper():
                    temporal_score = 0.8
                else:
                    temporal_score = 0.5
                    risk_flags.append("TEMPORAL_LIMITATION: Capability lacks explicit point-in-time restatement reasoning.")

            # 6. Jurisdiction Fit
            jurisdiction_score = 1.0
            if jurisdiction != "GLOBAL":
                if jurisdiction in cap.jurisdictions or "GLOBAL" in cap.jurisdictions:
                    jurisdiction_score = 1.0
                    matched_reqs.append(f"Jurisdiction: {jurisdiction}")
                else:
                    jurisdiction_score = 0.2
                    unmet_reqs.append(f"Jurisdiction: Lacks coverage for {jurisdiction}")

            # 7. Category Specialist Bonus (Align explicit question specialist requirements)
            spec_bonus = 0.0
            if question.specialist_requirements:
                req_specs = [s.lower() for s in question.specialist_requirements]
                if cap.category.value.lower() in req_specs:
                    spec_bonus = 0.2
                    matched_reqs.append(f"SpecialistCategory: {cap.category.value}")

            # 8. Compute Aggregate Match Score
            raw_score = (
                (ev_score * 0.35)
                + (q_score * 0.25)
                + (ent_score * 0.15)
                + (temporal_score * 0.10)
                + (jurisdiction_score * 0.15)
                + spec_bonus
            )

            # Strict evidence gating: if explicit evidence is required and a domain specialist satisfies NONE of it, penalize
            if required_ev and matches_found == 0 and cap.category.value != "GENERAL_RESEARCH":
                raw_score = min(raw_score * 0.25, 0.20)

            # Apply health penalty for DEGRADED
            if cap.status == HealthStatus.DEGRADED:
                raw_score *= 0.85

            match_score = min(max(raw_score, 0.0), 1.0)

            # Only include candidates meeting threshold
            if match_score >= 0.35 or (cap.category.value == "GENERAL_RESEARCH" and self.fallback_to_general_research):
                # Calculate expected information gain
                perf_f1 = cap.performance_profile.f1
                expected_gain = min(1.0, match_score * perf_f1)

                rationale = (
                    f"Matched {len(matched_reqs)} requirements. "
                    f"F1={perf_f1:.3f}, Category={cap.category.value}. "
                    f"{'Risk: ' + '; '.join(risk_flags) if risk_flags else 'Clean fit.'}"
                )

                candidate = CapabilityCandidate(
                    capability_id=cap.capability_id,
                    implementation_id=cap.implementation_id,
                    category=cap.category,
                    match_score=round(match_score, 4),
                    matched_requirements=matched_reqs,
                    unmet_requirements=unmet_reqs,
                    expected_information_gain=round(expected_gain, 4),
                    estimated_cost=cap.cost_model.cost_per_query_usd,
                    evidence_strength=round(cap.performance_profile.evidence_correctness, 4),
                    scope_fit=round(ent_score, 4),
                    temporal_fit=round(temporal_score, 4),
                    jurisdiction_fit=round(jurisdiction_score, 4),
                    health_status=cap.status,
                    risk_flags=risk_flags,
                    rationale=rationale,
                )
                candidates.append(candidate)

        # 9. Deterministic Multi-Tier Ranking:
        # Tier 1: match_score descending
        # Tier 2: expected_information_gain descending
        # Tier 3: estimated_cost ascending
        # Tier 4: implementation_id ascending (lexicographical tie-breaker)
        candidates.sort(
            key=lambda c: (
                -c.match_score,
                -c.expected_information_gain,
                c.estimated_cost,
                c.implementation_id,
            )
        )

        return candidates[:max_candidates]

    def select_minimum_sufficient_set(
        self,
        question: InvestigationQuestion,
        state: Optional[InvestigationState] = None,
        capabilities: Optional[List[CapabilityDefinition]] = None,
        max_candidates: int = 5,
    ) -> List[CapabilityCandidate]:
        """Select the minimum sufficient capability set to satisfy evidence requirements.

        Finds the smallest set of capabilities that covers the question's required evidence,
        avoiding unnecessary capability invocations and minimizing capability tax.
        """
        all_candidates = self.match(
            question=question,
            state=state,
            capabilities=capabilities,
            max_candidates=max_candidates,
        )
        if not all_candidates:
            return []

        # Deduplicate candidates to the best implementation per capability
        best_per_capability: dict[str, CapabilityCandidate] = {}
        for cand in all_candidates:
            if cand.capability_id not in best_per_capability:
                best_per_capability[cand.capability_id] = cand

        cap_dict = {c.capability_id: c for c in (capabilities or [])}

        required_ev = [r.lower() for r in question.required_evidence]
        if not required_ev:
            # When no explicit evidence is required, return the single highest-scoring candidate
            return [all_candidates[0]]

        # Build set cover over evidence requirements
        uncovered = set(required_ev)
        selected_candidates: List[CapabilityCandidate] = []
        selected_cap_ids: set[str] = set()

        # Sort candidate capability IDs by their best candidate's match score
        ranked_caps = sorted(
            best_per_capability.values(),
            key=lambda c: (-c.match_score, -c.expected_information_gain, c.estimated_cost),
        )

        for cand in ranked_caps:
            cap_def = cap_dict.get(cand.capability_id)
            if not cap_def:
                continue

            # Check which remaining requirements this capability satisfies
            satisfies_any = False
            for req in list(uncovered):
                if self._cap_satisfies_evidence(cap_def, req):
                    uncovered.remove(req)
                    satisfies_any = True

            if satisfies_any and cand.capability_id not in selected_cap_ids:
                selected_candidates.append(cand)
                selected_cap_ids.add(cand.capability_id)

            if not uncovered:
                break

        # Fallback if no candidate covered the explicit requirements (e.g. general questions or degraded states)
        if not selected_candidates and all_candidates:
            selected_candidates = [all_candidates[0]]

        return selected_candidates

    # Verbs a capability may prefix to a shared question type ("VERIFY_OFFICER_TENURE").
    _QUESTION_TYPE_VERBS = ("VERIFY", "FIND", "CHECK", "RESOLVE")

    @classmethod
    def _question_type_matches(cls, cap_qt: str, q_type: str, cap: CapabilityDefinition) -> bool:
        """Whole question-type match. A domain-qualified type such as ONION_ENTITY_DISCOVERY
        or OFAC_GENERAL_LICENSE_VERIFICATION is not the generic ENTITY_DISCOVERY / GENERAL."""
        a, b = cap_qt.upper(), q_type.upper()
        if a == b:
            return True
        if cap.category.value == "GENERAL_RESEARCH" and (b in a or a in b):
            return True
        return any(a == f"{verb}_{b}" for verb in cls._QUESTION_TYPE_VERBS)

    # Specialist domains whose evidence is only relevant when the requirement names that
    # domain. Mirrors the dark-web boundary below in the other direction.
    _DOMAIN_REQUIREMENT_TERMS = {
        "ONION_AND_DARKWEB": ("onion", "dark web", "darknet", "hidden service", "ahmia", "tor v3", "tor hidden"),
        "EMAIL_AND_ACCOUNT": ("email", "e-mail", "mailbox", "account", "username", "handle", "profile", "phone"),
    }

    @staticmethod
    def _cap_satisfies_evidence(cap: CapabilityDefinition, req: str) -> bool:
        """Check if capability declared evidence types satisfy an evidence requirement."""
        req_lower = req.lower()
        req_phrase = req_lower.replace("-", " ").replace("_", " ")
        req_squashed = req_lower.replace("-", "").replace("_", "").replace(" ", "")

        # Domain boundary: non-onion capabilities cannot satisfy dark-web or Tor hidden service evidence
        is_darkweb_req = (
            "onion" in req_phrase
            or "dark web" in req_phrase
            or "darknet" in req_phrase
            or "hidden service" in req_phrase
            or "ahmia" in req_phrase
            or "tor v3" in req_phrase
            or "tor hidden" in req_phrase
        )
        if is_darkweb_req and cap.category.value != "ONION_AND_DARKWEB":
            return False
        domain_terms = CapabilityMatcher._DOMAIN_REQUIREMENT_TERMS.get(cap.category.value)
        if domain_terms and not any(t in req_phrase for t in domain_terms):
            return False

        for et in cap.evidence_types:
            et_lower = et.lower()
            if et_lower == req_lower:
                return True
            et_phrase = et_lower.replace("_", " ")
            if et_phrase in req_phrase or et_phrase in req_lower:
                return True
            et_squashed = et_lower.replace("_", "")
            if et_squashed in req_squashed:
                return True

            tokens = [
                tok for tok in et_lower.split("_")
                if len(tok) >= 3 and tok not in (
                    "entry", "record", "file", "data", "info", "form",
                    "statement", "registration", "status", "anchor",
                    "schedule", "disclosure", "notice", "annex", "registry",
                    "archive", "archives", "public", "general", "block",
                    "contact", "listing", "history", "handle", "source", "review"
                )
            ]
            for tok in tokens:
                if re.search(r'\b' + re.escape(tok) + r'\b', req_phrase):
                    return True
                # Match common linguistic stems (e.g. register / registry, filing / filings, sanction / sanctions)
                if len(tok) >= 5 and tok not in ("commit", "match"):
                    for w in re.findall(r'\b[a-z]{5,}\b', req_phrase):
                        if (w.startswith(tok) or tok.startswith(w) or
                            w.rstrip('s') == tok.rstrip('s') or
                            w.rstrip('es') == tok.rstrip('es') or
                            (len(tok) >= 6 and len(w) >= 6 and w[:6] == tok[:6])):
                            return True
        return False

