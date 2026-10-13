"""Heimdallr V5: Onion & Dark-Web Specialist Unit and Integration Tests.

Validates:
1. Ahmia search discovery specialist
2. TorBot clean-room crawler & extractor specialist
3. Unified coexistence specialist pipeline
4. SecurityGateValidator observation sanitization and is_authoritative=False enforcement
5. Four-way causal execution consistency
6. Blindness test (renamed task IDs and shuffled task order)
"""

from __future__ import annotations

import copy
import random
import pytest

from argus.competition.security_gate import SecurityGateValidator
from argus.evals.onion_specialist_v1.runner import OnionSpecialistV1Runner
from argus.evals.onion_specialist_v1.tasks import build_onion_specialist_v1_tasks
from argus.specialists.onion.adapter import (
    AhmiaSearchAdapter,
    TorBotCleanRoomAdapter,
    UnifiedOnionAdapter,
)
from argus.specialists.onion.ahmia_specialist import AhmiaSearchSpecialist
from argus.specialists.onion.corpus import ONION_CORPUS
from argus.specialists.onion.torbot_specialist import TorBotCrawlerSpecialist
from argus.specialists.onion.unified_specialist import UnifiedOnionSpecialist


def test_ahmia_search_discovery() -> None:
    """Test Ahmia search specialist resolves queries across keywords, entities, and mirrors."""
    ahmia = AhmiaSearchSpecialist()

    # 1. Search by entity keyword
    hits = ahmia.search_onion_index("ALPHV ransomware leak portal")
    assert len(hits) > 0
    assert "alphv" in hits[0]["service_name"].lower()
    assert hits[0]["onion_address"].endswith(".onion")

    # 2. Search by natural language query
    hits_lockbit = ahmia.search_onion_index("Locate the LockBit 3.0 extortion blog")
    assert len(hits_lockbit) > 0
    assert "lockbit" in hits_lockbit[0]["service_name"].lower()

    # 3. Direct address query
    hits_direct = ahmia.search_onion_index("cl0p52gcvho3aveqmg7fvgarqvd2ek2gahqqqll4qjzn2vdre5ph4xqd.onion")
    assert len(hits_direct) > 0
    assert "cl0p" in hits_direct[0]["service_name"].lower()

    # 4. Non-matching query returns empty
    hits_none = ahmia.search_onion_index("nonexistent_random_unindexed_query_99999999")
    assert len(hits_none) == 0


def test_torbot_crawler_and_extraction() -> None:
    """Test clean-room TorBot crawler and cryptographic identity extraction."""
    torbot = TorBotCrawlerSpecialist()

    # 1. Crawl service
    crawl_res = torbot.crawl_onion_service("lockbitapt6vx57t3eeqjofwgcglmutr3a35nygvokja5uuccip4ykyd.onion")
    assert crawl_res["status"] == "SEIZED"
    assert len(crawl_res["crawled_pages"]) > 0
    assert crawl_res["mirror_count"] > 0

    # 2. Extract cryptographic identities
    ident_res = torbot.extract_cryptographic_identities("alphvmmm27yku4xb25v45w3h4vj3lsq4u7z3mefqfx42n3p4a23bfdqd.onion")
    assert "BTC" in ident_res["crypto_addresses"]
    assert len(ident_res["crypto_addresses"]["BTC"]) > 0
    assert len(ident_res["pgp_fingerprints"]) > 0
    assert len(ident_res["contact_identities"]) > 0

    # 3. Phishing mirror detection
    mirror_res = torbot.trace_mirror_clusters("alphvmmm27yku4xb25v45w3h4vj3lsq4u7z3mefqfx42n3p4a23bfdqd.onion")
    assert len(mirror_res["phishing_clones"]) > 0
    assert mirror_res["canonical_address"] == "alphvmmm27yku4xb25v45w3h4vj3lsq4u7z3mefqfx42n3p4a23bfdqd.onion"


def test_unified_specialist_end_to_end() -> None:
    """Test unified coexistence specialist pipeline integrating search and crawling."""
    specialist = UnifiedOnionSpecialist()

    # Investigation by query
    res = specialist.full_onion_investigation("Discover Sandworm C2 relay service")
    assert res["status"] == "RESOLVED"
    assert res["primary_service"] is not None
    assert "sandworm" in res["primary_service"]["service_name"].lower()
    assert res["extracted_intelligence"] is not None

    # Investigation of invalid address returns NOT_FOUND
    res_none = specialist.full_onion_investigation("invalidonionaddressnotreal9999999999999999999999999999999.onion")
    assert res_none["status"] == "NOT_FOUND"


def test_adapter_security_gate_sanitization() -> None:
    """Test that adapter enforces is_authoritative=False and sanitizes payloads."""
    adapter = UnifiedOnionAdapter()
    observations = adapter.execute_query("lockbitapt6vx57t3eeqjofwgcglmutr3a35nygvokja5uuccip4ykyd.onion")

    assert len(observations) > 0
    for obs in observations:
        # Crucial security assertion: dark-web intelligence is NEVER authoritative until verified
        assert obs.is_authoritative is False
        assert obs.source_candidate_id == "impl_onion_integrated_v1"
        assert obs.confidence > 0.0
        assert obs.epistemic_status.startswith("OBSERVED_")


def test_four_way_causal_soundness() -> None:
    """Test four-way benchmark causal integrity: A FAIL -> C PASS -> D FAIL."""
    runner = OnionSpecialistV1Runner()
    results = runner.execute_four_way_suite()

    assert results["total_tasks"] == 100
    assert results["argus_baseline_passed"] == 15
    assert results["candidate_standalone_passed"] == 95
    assert results["heimdallr_integrated_passed"] == 100
    assert results["candidate_disabled_passed"] == 15
    assert results["candidate_attributable_fixes"] == 85
    assert results["coexistence_synergy_wins"] == 4


def test_benchmark_blindness() -> None:
    """Test that the benchmark executes identically under task renaming and order permutation."""
    base_runner = OnionSpecialistV1Runner()
    base_res = base_runner.execute_four_way_suite()

    # Blind tasks: shuffle order and replace IDs with blinded identifiers
    blinded_tasks = copy.deepcopy(base_runner.tasks)
    random.seed(1337)
    random.shuffle(blinded_tasks)
    for i, t in enumerate(blinded_tasks):
        t.task_id = f"BLINDED_V5_{i:04d}"

    blinded_runner = OnionSpecialistV1Runner(tasks=blinded_tasks)
    blinded_res = blinded_runner.execute_four_way_suite()

    assert blinded_res["argus_baseline_passed"] == base_res["argus_baseline_passed"]
    assert blinded_res["candidate_standalone_passed"] == base_res["candidate_standalone_passed"]
    assert blinded_res["heimdallr_integrated_passed"] == base_res["heimdallr_integrated_passed"]
    assert blinded_res["candidate_disabled_passed"] == base_res["candidate_disabled_passed"]
    assert blinded_res["candidate_attributable_fixes"] == base_res["candidate_attributable_fixes"]
    assert blinded_res["coexistence_synergy_wins"] == base_res["coexistence_synergy_wins"]
