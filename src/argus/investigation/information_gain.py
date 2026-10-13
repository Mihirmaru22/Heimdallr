"""Heimdallr V2: Information Gain Estimation & Action Value Ranking.

Implements practical information-theoretic heuristic for action selection:
expected_value = (relevance * unresolved_need * evidence_value * discovery_prob * contradiction_mult) / cost

Ensures the research engine prioritizes actions that resolve critical gaps rather than
blindly maximizing query or document volume.
"""

from __future__ import annotations

import logging
from typing import Any

from argus.investigation.action import ActionType, ResearchAction
from argus.investigation.question import InvestigationQuestion, QuestionStatus
from argus.investigation.state import InvestigationState

logger = logging.getLogger(__name__)


class InformationGainEstimator:
    """Estimates expected marginal information gain for proposed research actions."""

    def __init__(
        self,
        base_cost: float = 0.0015,
        contradiction_bonus_multiplier: float = 2.0,
        unresolved_weight: float = 1.5,
    ) -> None:
        self.base_cost = base_cost
        self.contradiction_bonus_multiplier = contradiction_bonus_multiplier
        self.unresolved_weight = unresolved_weight

    def estimate_action_value(
        self,
        action: ResearchAction,
        state: InvestigationState,
        question: InvestigationQuestion | None = None,
    ) -> float:
        """Compute structured expected value for a candidate research action."""
        # 1. Relevance: alignment with top-level objective
        relevance = 0.5
        obj_lower = state.objective.lower()
        if any(ent.lower() in obj_lower for ent in action.target_entities):
            relevance = 0.95
        elif action.query and any(w in action.query.lower() for w in obj_lower.split() if len(w) > 3):
            relevance = 0.80

        # 2. Unresolved Need: priority and criticality of target question
        if question:
            if question.is_critical:
                unresolved_need = 1.0 * self.unresolved_weight
            else:
                unresolved_need = max(0.2, question.priority)
        else:
            unresolved_need = 0.5

        # 3. Evidence Value: number and importance of unmet evidence requirements
        ev_req_count = len(action.evidence_requirements)
        evidence_value = min(1.0, 0.4 + (0.2 * ev_req_count))

        # 4. Discovery Probability based on specialist match and action type
        if action.specialist and action.specialist != "none":
            discovery_prob = 0.85
        elif action.action_type in (ActionType.SEEK_PRIMARY_SOURCE, ActionType.QUERY_SOURCE):
            discovery_prob = 0.80
        elif action.action_type == ActionType.SEARCH:
            discovery_prob = 0.70
        else:
            discovery_prob = 0.60

        # 5. Contradiction Value Multiplier
        contradiction_mult = 1.0
        if action.action_type == ActionType.SEEK_CONTRADICTION or (
            question and question.question_type.value == "CONTRADICTION_RESOLUTION"
        ):
            contradiction_mult = self.contradiction_bonus_multiplier

        # 6. Cost penalty (tokens + search overhead)
        cost = max(0.05, action.estimated_cost / self.base_cost)

        # 7. Redundancy penalty for repeated queries on same question
        redundancy_mult = 1.0
        prior_same_actions = sum(
            1 for a in state.research_actions
            if a.get("question_id") == action.question_id
            and a.get("query", "").strip().lower() == (action.query or "").strip().lower()
        )
        if prior_same_actions > 0:
            redundancy_mult = 0.05 ** prior_same_actions
        else:
            prior_question_attempts = sum(1 for a in state.research_actions if a.get("question_id") == action.question_id)
            if prior_question_attempts > 0:
                redundancy_mult = 0.7 ** prior_question_attempts

        # Expected value synthesis
        numerator = relevance * unresolved_need * evidence_value * discovery_prob * contradiction_mult * redundancy_mult
        expected_value = numerator / cost

        # Normalize to 0.0 - 1.0 range for action field
        action.expected_information_gain = min(1.0, max(0.01, expected_value / 5.0))
        return expected_value
