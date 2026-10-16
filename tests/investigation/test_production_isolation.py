"""Production isolation: live runs never read the frozen benchmark registries (V3 FC1 T08).

The corporate, infrastructure and identity specialists, and the sanctions and onion
specialists, ship with invented benchmark records ("AutoTech Corporation", "Apex Cyber
Ltd", fictional onion services). Those records are for offline benchmark runs only. A
live investigation (any supplied corpus, and always the CLI) gets real connectors with
empty registries, and a capability that has no live source says so in the limitations.
"""

from __future__ import annotations

import tempfile
from typing import Any

from argus.capability_registry.adapters import (
    CorporateSpecialistAdapter,
    IdentitySpecialistAdapter,
    InfrastructureSpecialistAdapter,
    NoLiveSourceAdapter,
    get_adapter_for_implementation,
)
from argus.investigation.action import ActionType, ResearchAction
from argus.investigation.orchestrator import InvestigationEngine
from argus.investigation.store import InvestigationStore

SIMULATED_ONLY = (
    "impl_opensanctions_probe_v1",
    "impl_onion_integrated_v1",
    "impl_ahmia_search_v1",
    "impl_torbot_crawler_v1",
)


class EmptyCorpus:
    """Stand-in for the live retriever that returns nothing."""

    def __init__(self) -> None:
        self.documents: dict[str, Any] = {}

    def search(self, query: str, limit: int = 5) -> list[Any]:
        return []

    def get_discoverable_entities(self) -> set[str]:
        return set()


def _engine(corpus: Any = None, **kwargs: Any) -> InvestigationEngine:
    return InvestigationEngine(corpus=corpus, store=InvestigationStore(tempfile.mkdtemp()), **kwargs)


def test_engine_with_supplied_corpus_uses_no_simulated_registries():
    engine = _engine(EmptyCorpus())
    assert engine.simulated_registries is False
    assert engine.identity_specialist.platform_registry == {}
    assert engine.infra_specialist.registry == {}
    assert engine.corp_specialist.db == {}


def test_offline_benchmark_engine_keeps_simulated_registries():
    engine = _engine()
    assert engine.simulated_registries is True
    assert "autotech_corporation" in engine.corp_specialist.db


def test_cli_engine_never_uses_simulated_registries():
    from argus.terminal import OSINTTerminal

    term = OSINTTerminal(export_dir=tempfile.mkdtemp(), corpus=EmptyCorpus())
    assert term.engine.simulated_registries is False
    assert term.engine.corp_specialist.db == {}


def test_live_adapters_have_empty_registries_and_benchmark_adapters_do_not():
    assert CorporateSpecialistAdapter().specialist.db == {}
    assert InfrastructureSpecialistAdapter().specialist.registry == {}
    assert IdentitySpecialistAdapter().specialist.platform_registry == {}
    assert "autotech_corporation" in CorporateSpecialistAdapter(simulated=True).specialist.db
    assert get_adapter_for_implementation("impl_corporate_registry_specialist_v1").specialist.db == {}
    assert get_adapter_for_implementation("impl_corporate_registry_specialist_v1", simulated=True).specialist.db


def test_corpus_only_specialists_report_no_live_source():
    for impl_id in SIMULATED_ONLY:
        live = get_adapter_for_implementation(impl_id)
        assert isinstance(live, NoLiveSourceAdapter)
        res = live.execute({"query": "Apex Cyber Ltd"})
        assert res["status"] == "FAILED"
        assert res["documents"] == []
        assert "No live data source" in res["error"]
        assert not isinstance(get_adapter_for_implementation(impl_id, simulated=True), NoLiveSourceAdapter)


def test_live_sanctions_action_returns_no_invented_record_and_reports_the_gap():
    engine = _engine(EmptyCorpus())
    state = engine.start_investigation(objective="Is Apex Cyber Ltd sanctioned?")
    action = ResearchAction(
        action_type=ActionType.INVESTIGATE_SPECIALIST,
        query="Apex Cyber Ltd",
        specialist="sanctions",
        implementation_id="impl_opensanctions_probe_v1",
        target_entities=["Apex Cyber Ltd"],
        rationale="Screen the entity against sanctions lists.",
    )

    obs = engine._dispatch_action(action, state)

    assert obs["documents"] == []
    assert "Victor Kroll" not in str(obs) and "EO14024" not in str(obs)
    assert any("No live data source is configured for sanctions screening" in lim for lim in state.generate_limitations())
