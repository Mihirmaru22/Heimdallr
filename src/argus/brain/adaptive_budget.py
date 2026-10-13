"""Adaptive Research Budget Controller for Argus Brain / Laya Layer.

Replaces static step/task cutoffs with information-theoretic budget management:
Research attempt
      ↓
Information gain
      ↓
Expected value of next action
      ↓
Cost of next action
      ↓
Risk of missing critical information
      ↓
CONTINUE / STOP / CHANGE STRATEGY
"""

from __future__ import annotations

from enum import Enum
import logging
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class BudgetDecision(str, Enum):
    CONTINUE = "CONTINUE"
    STOP = "STOP"
    CHANGE_STRATEGY = "CHANGE_STRATEGY"


class AdaptiveBudgetState(BaseModel):
    """Runtime tracking state for an active investigation budget."""

    base_budget: int = 4
    current_budget: int = 4
    max_adaptive_ceiling: int = 12
    steps_taken: int = 0
    tokens_consumed: int = 0
    cumulative_entities_found: int = 0
    recent_information_gains: list[float] = Field(default_factory=list)
    consecutive_zero_gains: int = 0
    unresolved_critical_hops: int = 0


class AdaptiveBudgetManager:
    """Manages research depth and query allocation based on dynamic marginal information gain."""

    def __init__(
        self,
        base_budget: int = 4,
        max_adaptive_ceiling: int = 12,
        marginal_gain_threshold: float = 0.15,
        risk_tolerance_threshold: float = 0.70,
    ) -> None:
        self.base_budget = base_budget
        self.max_adaptive_ceiling = max_adaptive_ceiling
        self.marginal_gain_threshold = marginal_gain_threshold
        self.risk_tolerance_threshold = risk_tolerance_threshold

    def create_state(self, is_deep_investigation: bool = False, expected_hops: int = 1) -> AdaptiveBudgetState:
        initial = max(self.base_budget, expected_hops + 1)
        ceiling = min(self.max_adaptive_ceiling, initial + 6) if is_deep_investigation else self.base_budget + 2
        return AdaptiveBudgetState(
            base_budget=initial,
            current_budget=initial,
            max_adaptive_ceiling=ceiling,
            unresolved_critical_hops=max(0, expected_hops - 1),
        )

    def evaluate_step(
        self,
        state: AdaptiveBudgetState,
        new_entities_discovered: int,
        new_relationships_discovered: int,
        unresolved_hops_remaining: int,
        tokens_step: int = 250,
    ) -> tuple[BudgetDecision, str]:
        """Evaluates whether to continue, change strategy, or stop research."""
        state.steps_taken += 1
        state.tokens_consumed += tokens_step
        state.unresolved_critical_hops = unresolved_hops_remaining

        # 1. Calculate Information Gain
        raw_gain = (new_entities_discovered * 1.0) + (new_relationships_discovered * 1.5)
        state.recent_information_gains.append(raw_gain)
        state.cumulative_entities_found += new_entities_discovered

        if raw_gain == 0.0:
            state.consecutive_zero_gains += 1
        else:
            state.consecutive_zero_gains = 0

        # 2. Risk of Missing Critical Information
        risk_of_omission = 0.0
        if unresolved_hops_remaining > 0:
            risk_of_omission = 0.85
        elif state.cumulative_entities_found == 0:
            risk_of_omission = 0.50

        # 3. Expected Value of Next Action
        expected_value = 0.0
        if raw_gain > 0.0 and unresolved_hops_remaining > 0:
            # Active discovery on a multi-hop chain has very high expected value
            expected_value = 0.90
        elif raw_gain > 0.0:
            expected_value = 0.60
        elif state.consecutive_zero_gains == 1 and unresolved_hops_remaining > 0:
            # First dry step in an unclosed chain -> pivot query
            expected_value = 0.40

        # 4. Adaptive Budget Expansion (Prevent premature stopping)
        if (
            unresolved_hops_remaining > 0
            and raw_gain > 0.0
            and state.current_budget < state.max_adaptive_ceiling
        ):
            # Fresh anchor found in deep chain: grant adaptive extension
            expansion = min(2, state.max_adaptive_ceiling - state.current_budget)
            state.current_budget += expansion
            logger.info("Adaptive budget expanded by %d steps (new budget: %d)", expansion, state.current_budget)

        # 5. Decision Logic
        if state.steps_taken >= state.current_budget:
            if risk_of_omission >= self.risk_tolerance_threshold and state.current_budget < state.max_adaptive_ceiling:
                state.current_budget = min(state.current_budget + 2, state.max_adaptive_ceiling)
                return BudgetDecision.CONTINUE, "High omission risk with pending hops: extending adaptive budget."
            return BudgetDecision.STOP, f"Budget ceiling reached ({state.steps_taken}/{state.current_budget} steps)."

        if state.consecutive_zero_gains >= 2:
            if unresolved_hops_remaining > 0:
                return BudgetDecision.CHANGE_STRATEGY, "Information gain plateaued with unresolved hops: pivot search entity."
            return BudgetDecision.STOP, "Information gain plateaued and no critical hops pending."

        if unresolved_hops_remaining == 0 and state.steps_taken >= state.base_budget:
            return BudgetDecision.STOP, "All hops resolved and base budget satisfied."

        return BudgetDecision.CONTINUE, f"Information gain positive ({raw_gain:.1f}): continuing exploration."
