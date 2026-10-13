"""Unit tests for InvestigationPlanner, Action Ranking, Information Gain, Branches, and Stopping Policy."""

import pytest

from argus.investigation.action import ActionType, ResearchAction
from argus.investigation.branch import BranchStatus, InvestigationBranch
from argus.investigation.information_gain import InformationGainEstimator
from argus.investigation.planner import InvestigationPlanner
from argus.investigation.question import InvestigationQuestion, QuestionStatus, QuestionType
from argus.investigation.state import InvestigationState
from argus.investigation.stopping import InvestigationStopReason, InvestigationStoppingPolicy


def test_action_ranking_and_information_gain():
    planner = InvestigationPlanner()
    state = InvestigationState(
        objective="Investigate Apex Technologies Group",
        objective_contract={"target_entities": ["Apex Technologies Group"]},
    )
    state = planner.initialize_investigation(
        objective=state.objective,
        objective_contract=state.objective_contract,
    )

    actions = planner.select_next_actions(state, limit=3)
    assert len(actions) > 0
    # Highest expected information gain should be ranked first
    assert actions[0].expected_information_gain >= actions[-1].expected_information_gain
    assert actions[0].action_type in [ActionType.QUERY_SOURCE, ActionType.SEARCH, ActionType.INVESTIGATE_SPECIALIST]


def test_branch_lifecycle_and_step_budget():
    branch = InvestigationBranch(
        purpose="Investigate Subsidiary Unit A",
        target_entity="Unit A",
        step_budget=2,
    )
    assert branch.can_continue() is True

    # Take step 1
    branch.record_step(cost=0.001, gain=0.4, action_id="act_1")
    assert branch.steps_taken == 1
    assert branch.can_continue() is True

    # Take step 2 -> budget reached
    branch.record_step(cost=0.001, gain=0.2, action_id="act_2")
    assert branch.steps_taken == 2
    assert branch.can_continue() is False

    # Complete branch
    branch.complete()
    assert branch.status == BranchStatus.COMPLETED
    assert branch.completed_at is not None


def test_stopping_policy_all_reasons():
    policy = InvestigationStoppingPolicy(max_consecutive_zero_gains=2)
    state = InvestigationState(objective="Stopping Test")

    # 1. In progress
    should_stop, reason, _ = policy.evaluate(state)
    assert should_stop is False

    # 2. All questions resolved -> OBJECTIVE_SATISFIED
    q = InvestigationQuestion(question_text="Q1", is_critical=True)
    state.questions[q.question_id] = q.model_dump()
    state.resolved_questions.append(q.question_id)
    should_stop, reason, _ = policy.evaluate(state)
    assert should_stop is True
    assert reason == InvestigationStopReason.OBJECTIVE_SATISFIED

    # 3. Consecutive zero gains -> NO_INFORMATION_GAIN
    state_plateau = InvestigationState(objective="Plateau Test")
    q2 = InvestigationQuestion(question_text="Q2", is_critical=True)
    state_plateau.questions[q2.question_id] = q2.model_dump()
    state_plateau.unresolved_questions.append(q2.question_id)
    state_plateau.research_budget["steps_taken"] = 4
    state_plateau.research_budget["consecutive_zero_gains"] = 2
    should_stop, reason, _ = policy.evaluate(state_plateau)
    assert should_stop is True
    assert reason == InvestigationStopReason.NO_INFORMATION_GAIN

    # 4. Budget exhausted with critical missing fields
    state_budget = InvestigationState(objective="Budget Test")
    q3 = InvestigationQuestion(question_text="Critical Q3", is_critical=True)
    state_budget.questions[q3.question_id] = q3.model_dump()
    state_budget.unresolved_questions.append(q3.question_id)
    state_budget.research_budget["steps_taken"] = 15
    state_budget.research_budget["max_steps"] = 15
    should_stop, reason, _ = policy.evaluate(state_budget)
    assert should_stop is True
    assert reason == InvestigationStopReason.BUDGET_EXHAUSTED_WITH_CRITICAL_MISSING_FIELDS
