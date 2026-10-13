"""Tests for Failure-Driven Architectural Upgrades.

Verifies:
1. Adaptive budget manager expands on unresolved hops and stops on zero-gain plateau.
2. Jurisdiction-aware entity graph distinguishes same-named entities across jurisdictions.
3. Temporal state reasoner evaluates state at time T and respects restatements.
4. Syndication intelligence enforces 3 copies != 3 sources.
"""

import pytest

from argus.brain.adaptive_budget import AdaptiveBudgetManager, BudgetDecision
from argus.domain.jurisdiction_graph import JurisdictionEntityGraph
from argus.verifier.syndication_intelligence import SyndicationIntelligence
from argus.verifier.temporal_reasoner import (
    LifecycleState,
    TemporalRecord,
    TemporalStateReasoner,
)


def test_adaptive_budget_expands_on_pending_hops():
    manager = AdaptiveBudgetManager(base_budget=3, max_adaptive_ceiling=8)
    state = manager.create_state(is_deep_investigation=True, expected_hops=4)
    assert state.current_budget >= 4

    # Step 1: Found 1 entity and 1 relationship, 3 hops remaining
    dec, msg = manager.evaluate_step(
        state=state,
        new_entities_discovered=1,
        new_relationships_discovered=1,
        unresolved_hops_remaining=3,
    )
    assert dec == BudgetDecision.CONTINUE
    assert state.current_budget > 4  # Expanded dynamically!


def test_adaptive_budget_stops_on_zero_gain_plateau():
    manager = AdaptiveBudgetManager(base_budget=3, max_adaptive_ceiling=6)
    state = manager.create_state(is_deep_investigation=False, expected_hops=1)

    # Step 1: Zero gain
    dec, _ = manager.evaluate_step(state, 0, 0, 0)
    assert dec == BudgetDecision.CONTINUE

    # Step 2: Zero gain
    dec, _ = manager.evaluate_step(state, 0, 0, 0)
    assert dec == BudgetDecision.STOP


def test_jurisdiction_graph_distinguishes_same_name():
    graph = JurisdictionEntityGraph()

    us_node = graph.register_entity(
        name="AeroDynamics Corp",
        jurisdiction="US-DE",
        source_registry="SEC EDGAR",
        legal_identifier="0001899120",
    )
    uk_node = graph.register_entity(
        name="AeroDynamics UK Limited",
        jurisdiction="GB",
        source_registry="Companies House",
        legal_identifier="09923841",
    )

    assert us_node.node_id != uk_node.node_id
    assert graph.are_same_legal_entity("AeroDynamics Corp", "US-DE", "AeroDynamics Corp", "GB") is False

    # Link parent to subsidiary
    graph.link_parent_subsidiary(us_node.node_id, uk_node.node_id)
    hierarchy = graph.get_affiliate_hierarchy(us_node.node_id)
    assert len(hierarchy) == 2
    assert hierarchy[0].node_id == us_node.node_id
    assert hierarchy[1].node_id == uk_node.node_id


def test_temporal_reasoner_evaluates_at_time_t():
    reasoner = TemporalStateReasoner()

    records = [
        TemporalRecord(
            record_id="rec_01",
            lifecycle_state=LifecycleState.EFFECTIVE,
            subject="AeroDynamics Corp",
            predicate="officer",
            object="Arthur Sterling",
            filing_date="2018-05-01",
            effective_start="2018-05-01",
            effective_end="2022-01-15",
        ),
        TemporalRecord(
            record_id="rec_02",
            lifecycle_state=LifecycleState.EFFECTIVE,
            subject="AeroDynamics Corp",
            predicate="officer",
            object="Rachel Adams",
            filing_date="2022-01-16",
            effective_start="2022-01-16",
            effective_end=None,
        ),
    ]

    # At 2021-06-30: Arthur Sterling was active
    v1 = reasoner.resolve_at_date("2021-06-30", "AeroDynamics Corp", "officer", records)
    assert v1.is_active_at_time_t is True
    assert v1.active_object == "Arthur Sterling"

    # At 2023-01-01: Rachel Adams is active
    v2 = reasoner.resolve_at_date("2023-01-01", "AeroDynamics Corp", "officer", records)
    assert v2.is_active_at_time_t is True
    assert v2.active_object == "Rachel Adams"


def test_temporal_reasoner_respects_amended_restatement():
    reasoner = TemporalStateReasoner()

    records = [
        TemporalRecord(
            record_id="10-K_original",
            lifecycle_state=LifecycleState.SUPERSEDED,
            subject="CyberShield Inc",
            predicate="officer",
            object="Donald Vance",
            filing_date="2021-03-15",
            effective_start="2020-01-01",
            effective_end="2020-12-31",
        ),
        TemporalRecord(
            record_id="10-K_amended_A",
            lifecycle_state=LifecycleState.RESTATED,
            subject="CyberShield Inc",
            predicate="officer",
            object="Rachel Adams",
            filing_date="2021-09-10",
            effective_start="2020-01-01",
            effective_end="2020-12-31",
            supersedes_record_id="10-K_original",
            is_restatement=True,
        ),
    ]

    verdict = reasoner.resolve_at_date("2020-06-30", "CyberShield Inc", "officer", records)
    assert verdict.active_object == "Rachel Adams"
    assert "10-K_original" in verdict.superseded_records


def test_syndication_intelligence_discounts_mirrors():
    intelligence = SyndicationIntelligence()

    # 3 PR wire mirrors with the same syndication cluster ID
    evidence = [
        {"url": "https://prnewswire.com/news/1", "snippet": "Text 1", "syndication_cluster_id": "cluster_pr_01"},
        {"url": "https://marketwatch.com/news/1", "snippet": "Text 1", "syndication_cluster_id": "cluster_pr_01"},
        {"url": "https://yahoo.com/news/1", "snippet": "Text 1", "syndication_cluster_id": "cluster_pr_01"},
    ]

    verdict = intelligence.evaluate(evidence, min_independent_sources_required=3)
    assert verdict.raw_evidence_count == 3
    assert verdict.independent_clusters_count == 1  # 3 copies = 1 source!
    assert verdict.is_sufficiently_independent is False
    assert len(verdict.discounted_duplicate_urls) == 2
