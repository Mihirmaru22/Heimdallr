"""Heimdallr V3.1: Generate Capability Match V2 Trajectory Samples.

Executes real investigations through the Investigation Engine:
Investigation Engine -> Question -> Requirements -> Registry -> Matcher ->
Ranked Capabilities -> Planner -> Research Action -> Observation ->
New Question -> Capability Registry.

Captures all 10 required trajectory dimensions:
- question
- requirements
- candidate capabilities
- ranking
- selected capability
- reason
- action
- result
- next question
- next capability
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from argus.capability_registry.registry import CapabilityRegistry
from argus.capability_registry.defaults import get_default_capabilities
from argus.capability_registry.matcher import CapabilityMatcher
from argus.investigation.benchmark.corpus import INVESTIGATION_CORPUS_REGISTRY
from argus.investigation.orchestrator import InvestigationEngine
from argus.investigation.planner import InvestigationPlanner
from argus.investigation.question import InvestigationQuestion


def generate_trajectory_samples(output_paths: List[Path | str]) -> List[Dict[str, Any]]:
    """Execute real multi-step investigations and generate auditable trajectory traces."""
    registry = CapabilityRegistry()
    for cap in get_default_capabilities():
        registry.register(cap, overwrite=True)

    matcher = CapabilityMatcher()
    planner = InvestigationPlanner(registry=registry, matcher=matcher)
    engine = InvestigationEngine(planner=planner, registry=registry, corpus=INVESTIGATION_CORPUS_REGISTRY)

    objectives = [
        {
            "trajectory_id": "traj_01_cross_specialist_corporate_infra_identity",
            "objective": (
                "Starting from Apex Technologies Group, discover its UK subsidiary, "
                "the telemetry domain SAN, and verify the administrative contact CISO."
            ),
            "contract": {"target_entities": ["Apex Technologies Group"]},
            "max_steps": 6,
        },
        {
            "trajectory_id": "traj_02_contradiction_succession_reconciliation",
            "objective": (
                "Form 10-K from 2020 lists Donald Vance as SVP of AI, while current report lists David Marcus. "
                "Resolve which individual is currently authoritative."
            ),
            "contract": {"target_entities": ["Apex Technologies Group"]},
            "max_steps": 5,
        },
        {
            "trajectory_id": "traj_03_temporal_historical_board_reconstruction",
            "objective": (
                "What individual authoritatively served as SVP of Machine Learning & AI at Apex Technologies as of December 31, 2020?"
            ),
            "contract": {"target_entities": ["Apex Technologies Group"], "as_of_date": "2020-12-31"},
            "max_steps": 5,
        },
    ]

    all_trajectories: List[Dict[str, Any]] = []

    for obj in objectives:
        state = engine.start_investigation(
            objective=obj["objective"],
            contract=obj["contract"],
            as_of_date=obj.get("contract", {}).get("as_of_date"),
        )

        steps_trace: List[Dict[str, Any]] = []
        step_idx = 1

        while not state.stop_state.is_stopped and step_idx <= obj["max_steps"]:
            # 1. Identify open question
            unresolved = state.unresolved_questions
            if not unresolved:
                break

            current_q_id = unresolved[0]
            q_dict = state.questions.get(current_q_id)
            if not q_dict:
                break
            q = InvestigationQuestion.model_validate(q_dict)

            # 2. Query capability matcher
            candidates = matcher.match(
                question=q,
                state=state,
                capabilities=registry.list(include_inactive=False),
                max_candidates=4,
            )

            # 3. Minimum sufficient set selection
            min_set = matcher.select_minimum_sufficient_set(
                question=q,
                state=state,
                capabilities=registry.list(include_inactive=False),
                max_candidates=4,
            )
            top_cand = min_set[0] if min_set else (candidates[0] if candidates else None)

            # 4. Plan action
            planned_actions = planner.select_next_actions(state, limit=1)
            if not planned_actions:
                break
            action = planned_actions[0]

            # 5. Execute step in InvestigationEngine
            state, finished = engine.execute_step(state)

            # Extract latest observation and gain
            latest_obs = state.observations[-1] if state.observations else {}
            latest_gain = (
                state.information_gain_history[-1].get("information_gain", 0.0)
                if state.information_gain_history
                else 0.0
            )

            # 6. Lookahead to next question and capability
            next_unresolved = state.unresolved_questions
            if next_unresolved:
                next_q_dict = state.questions.get(next_unresolved[0], {})
                next_q_text = next_q_dict.get("question_text", "None")
                next_cands = matcher.match(
                    question=InvestigationQuestion.model_validate(next_q_dict),
                    state=state,
                    capabilities=registry.list(include_inactive=False),
                    max_candidates=1,
                )
                next_cap = next_cands[0].capability_id if next_cands else "general_web_research"
            else:
                next_q_text = "All questions resolved."
                next_cap = "None"

            # 7. Record full trace step
            step_record = {
                "step_number": step_idx,
                "question": q.question_text,
                "question_id": q.question_id,
                "requirements": q.required_evidence,
                "candidate_capabilities": [c.capability_id for c in candidates],
                "ranking": [
                    {
                        "capability_id": c.capability_id,
                        "implementation_id": c.implementation_id,
                        "match_score": c.match_score,
                        "expected_gain": c.expected_information_gain,
                        "cost_usd": c.estimated_cost,
                    }
                    for c in candidates
                ],
                "selected_capability": top_cand.capability_id if top_cand else action.capability_id,
                "selected_implementation": top_cand.implementation_id if top_cand else action.implementation_id,
                "reason": top_cand.rationale if top_cand else "Heuristic action fallback",
                "action": {
                    "action_id": action.action_id,
                    "action_type": action.action_type.value if hasattr(action.action_type, "value") else str(action.action_type),
                    "query": action.query,
                    "specialist": action.specialist,
                    "capability_id": action.capability_id,
                    "implementation_id": action.implementation_id,
                },
                "result": {
                    "observation_id": latest_obs.get("observation_id"),
                    "documents_count": latest_obs.get("documents_count", 0),
                    "information_gain": latest_gain,
                    "new_entities": list(state.entities.keys())[-3:],
                },
                "next_question": next_q_text,
                "next_capability": next_cap,
            }
            steps_trace.append(step_record)
            step_idx += 1
            if finished:
                break

        traj_record = {
            "trajectory_id": obj["trajectory_id"],
            "objective": obj["objective"],
            "total_steps": len(steps_trace),
            "final_status": state.stop_state.stop_reason or "COMPLETED",
            "specialist_invocations": state.specialist_invocations,
            "steps": steps_trace,
        }
        all_trajectories.append(traj_record)

    for p in output_paths:
        target = Path(p)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            json.dump(all_trajectories, f, indent=2)

    return all_trajectories


if __name__ == "__main__":
    generate_trajectory_samples([
        "/data/shared/project/PlayGround/Argus/proofs/capability_match_v2_trajectory_samples.json",
        "/data/shared/project/PlayGround/Argus/evals/results/capability_match_v2_trajectory_samples.json",
    ])
    print("Trajectory samples successfully generated.")
