"""Regression tests for structured objective interpretation (V3 FC1 T03).

The planner used to take the first three capitalized words as the subject
("Search Companies TEAMCENTER") and ask encyclopedia questions about it. These
tests check that list-style objectives are represented as answer type +
relation + object + geography, for products that appear nowhere in the code.
"""

from __future__ import annotations

import pytest

from argus.investigation.action import ActionType
from argus.investigation.objective_parser import (
    ANSWER_TYPE_ORGANIZATION,
    RELATION_USES,
    EnumerationObjective,
    parse_enumeration_objective,
    refine_object_from_evidence,
)
from argus.investigation.planner import InvestigationPlanner


@pytest.mark.parametrize(
    "objective, noun, obj, geography",
    [
        ("Search Companies who are using TEAMCENTER in usa", "companies", "Teamcenter", "United States"),
        ("banks in Australia using Temenos core banking", "banks", "Temenos core banking", "Australia"),
        ("list companies in India which use SAP ERP", "companies", "SAP ERP", "India"),
        ("Which hospitals in Germany use Epic?", "hospitals", "Epic", "Germany"),
        ("US manufacturers that use Siemens NX", "manufacturers", "Siemens NX", "United States"),
        ("Find organizations that have deployed ServiceNow in the United Kingdom", "organizations", "ServiceNow", "United Kingdom"),
        ("customers of Zephyrix Quantum Ledger in Canada", "customers", "Zephyrix Quantum Ledger", "Canada"),
        ("companies using Quorvane Flux", "companies", "Quorvane Flux", ""),
    ],
)
def test_enumeration_objectives_are_parsed_into_structure(objective, noun, obj, geography):
    enum = parse_enumeration_objective(objective)
    assert enum is not None
    assert enum.answer_type == ANSWER_TYPE_ORGANIZATION
    assert enum.answer_noun == noun
    assert enum.relation == RELATION_USES
    assert enum.object == obj
    assert enum.geography == geography


def test_non_location_context_is_not_mistaken_for_geography():
    enum = parse_enumeration_objective("companies using Microsoft Dynamics in retail")
    assert enum is not None
    assert enum.object == "Microsoft Dynamics"
    assert enum.geography == ""
    assert enum.context_constraints == ["retail"]


@pytest.mark.parametrize(
    "objective",
    [
        "Who is Ronak Raiyani",
        "Identify the executive officers of Helix Corp",
        "What are the operational characteristics of pgvector",
        "Which companies acquired Slack",
        "Find everything about Param Software company",
    ],
)
def test_non_enumeration_objectives_are_left_to_existing_planning(objective):
    assert parse_enumeration_objective(objective) is None


@pytest.mark.parametrize(
    "objective, product, region",
    [
        ("Search Companies who are using TEAMCENTER in usa", "Teamcenter", "United States"),
        ("banks in Australia using Temenos core banking", "Temenos core banking", "Australia"),
        ("list companies in India which use SAP ERP", "SAP ERP", "India"),
        ("Which retailers in Brazil use Quorvane Flux?", "Quorvane Flux", "Brazil"),
    ],
)
def test_planner_targets_the_product_and_plans_focused_queries(objective, product, region):
    planner = InvestigationPlanner()
    state = planner.initialize_investigation(objective, {"max_steps": 15})

    enum = state.objective_contract["enumeration_objective"]
    assert enum["object"] == product
    assert enum["geography"] == region
    assert enum["answer_type"] == ANSWER_TYPE_ORGANIZATION

    for name in state.entities:
        assert not any(w in name.split() for w in ("Search", "List", "Companies", "Which")), name
    assert product in state.entities

    texts = [q["question_text"] for q in state.questions.values()]
    assert not any("foundational concepts" in t for t in texts)
    assert any(product in t and region in t for t in texts)

    actions = planner.select_next_actions(state, limit=3)
    assert actions
    first = actions[0]
    assert first.action_type == ActionType.SEARCH
    assert first.specialist == "none"
    assert product in first.query and region in first.query
    for a in actions:
        assert product in a.query
        assert "registry legal entity" not in a.query and "subsidiaries schedule" not in a.query

    interp = [e for e in state.audit_trail if e.action_type == "OBJECTIVE_INTERPRETED"]
    assert interp and interp[0].details["object"] == product


def test_used_queries_are_not_replaced_by_boilerplate_variants():
    planner = InvestigationPlanner()
    state = planner.initialize_investigation("companies using Quorvane Flux in Japan", {"max_steps": 15})
    disc_id = state.objective_contract["enumeration_objective"]["question_ids"]["discovery"]
    for sq in state.questions[disc_id]["search_queries"]:
        state.research_actions.append({"question_id": disc_id, "query": sq, "action_type": ActionType.SEARCH})
    actions = planner.select_next_actions(state, limit=5)
    assert not [a for a in actions if a.question_id == disc_id]


def test_explicit_contract_targets_bypass_the_enumeration_parser():
    planner = InvestigationPlanner()
    state = planner.initialize_investigation(
        "Search Companies who are using TEAMCENTER in usa",
        {"max_steps": 5, "target_entities": ["Siemens AG"]},
    )
    assert "enumeration_objective" not in state.objective_contract
    assert "Siemens AG" in state.entities


def test_command_verbs_are_not_taken_as_entity_names():
    planner = InvestigationPlanner()
    state = planner.initialize_investigation("Search Acme Robotics history", {"max_steps": 5})
    assert "Acme Robotics" in state.entities


# Real DuckDuckGo snippets recorded in the 2026-10-14 Teamcenter export (git 93eb9de).
RECORDED_SNIPPETS = [
    ("https://theirstack.com/en/technology/siemens-teamcenter/us",
     "Companies that use Siemens Teamcenter in United States Download a list of 592 companies that use Siemens Teamcenter in United States with enriched data including industry, company size, location, funding rounds, and revenue figures."),
    ("https://theirstack.com/en/technology/siemens-teamcenter",
     "Companies that use Siemens Teamcenter - theirstack.com Download a list of 2,604 companies that use Siemens Teamcenter with enriched data including industry, company size, location, funding rounds, and revenue figures."),
    ("https://data.landbase.com/technology/siemens-teamcenter-plm-software/",
     "Companies using Siemens Teamcenter PLM Software in 2026 | Landbase Siemens Teamcenter PLM Software by Siemens is a comprehensive Product Lifecycle Management (PLM) platform."),
]


def test_object_is_qualified_from_consistent_evidence():
    enum = parse_enumeration_objective("Search Companies who are using TEAMCENTER in usa")
    assert refine_object_from_evidence(enum, RECORDED_SNIPPETS)
    assert enum.object_qualified == "Siemens Teamcenter"
    assert enum.object_name == "Siemens Teamcenter"
    assert all("Siemens Teamcenter" in q for q in enum.search_queries())


def test_object_is_not_qualified_from_a_single_source_or_inconsistent_names():
    enum = parse_enumeration_objective("companies using Quorvane Flux")
    assert not refine_object_from_evidence(enum, [("https://a.example/x", "Brightwell Quorvane Flux rollout.")])
    assert not refine_object_from_evidence(enum, [
        ("https://a.example/x", "Brightwell Quorvane Flux rollout."),
        ("https://b.example/y", "Northgate Quorvane Flux rollout."),
        ("https://c.example/z", "Quorvane Flux adoption grows."),
    ])
    assert enum.object_qualified == ""


def test_planner_refinement_updates_pending_question_queries():
    planner = InvestigationPlanner()
    state = planner.initialize_investigation("Search Companies who are using TEAMCENTER in usa", {"max_steps": 15})
    for url, text in RECORDED_SNIPPETS:
        state.add_evidence({"url": url, "title": "", "snippet": text})
    assert planner.refine_objective_from_evidence(state)
    enum = EnumerationObjective.from_dict(state.objective_contract["enumeration_objective"])
    assert enum.object_name == "Siemens Teamcenter"
    disc_id = state.objective_contract["enumeration_objective"]["question_ids"]["discovery"]
    assert state.questions[disc_id]["question_text"] == "Which organizations in the United States use Siemens Teamcenter?"
    assert all("Siemens Teamcenter" in q for q in state.questions[disc_id]["search_queries"])
    assert any(e.action_type == "OBJECTIVE_REFINED" for e in state.audit_trail)
