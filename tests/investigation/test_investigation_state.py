"""Unit tests for InvestigationState, Serialization, Audit Trail, and Persistence Store."""

import json
from pathlib import Path
import tempfile
import pytest

from argus.investigation.state import AuditTrailEntry, InformationGap, InvestigationState, StopState
from argus.investigation.store import InvestigationStore


def test_investigation_state_creation():
    state = InvestigationState(
        objective="Investigate Apex Technologies Group leadership",
        objective_contract={"target_entities": ["Apex Technologies Group"]},
    )
    assert state.investigation_id.startswith("inv_")
    assert state.objective == "Investigate Apex Technologies Group leadership"
    assert len(state.entities) == 0
    assert len(state.claims) == 0
    assert len(state.evidence) == 0
    assert not state.stop_state.is_stopped


def test_investigation_state_serialization_roundtrip():
    state = InvestigationState(
        objective="Test serialization",
        objective_contract={"target": "TestCorp"},
    )
    state.register_entity(name="TestCorp", entity_type="ORGANIZATION", metadata={"jurisdiction": "DE"})
    cid = state.add_claim({"subject": "TestCorp", "predicate": "status", "object": "ACTIVE"})
    eid = state.add_evidence({"url": "https://sec.gov/test", "source_type": "regulatory_filing", "title": "Test Filing", "snippet": "TestCorp is active"})
    state.record_audit(action_type="TEST_ACTION", rationale="Verifying serialization")

    json_str = state.to_json(indent=2)
    assert "TestCorp" in json_str
    assert cid in json_str
    assert eid in json_str

    restored = InvestigationState.from_json(json_str)
    assert restored.investigation_id == state.investigation_id
    assert "TestCorp" in restored.entities
    assert restored.entities["TestCorp"]["metadata"]["jurisdiction"] == "DE"
    assert len(restored.claims) == 1
    assert len(restored.evidence) == 1
    assert len(restored.audit_trail) == 1


def test_investigation_store_save_and_load():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = InvestigationStore(storage_dir=tmpdir)
        state = InvestigationState(
            objective="Persistent Store Check",
            objective_contract={},
        )
        state.register_entity(name="Alpha LLC")
        state.record_audit(action_type="INITIALIZE", rationale="Created for store test")

        saved_path = store.save_state(state)
        assert Path(saved_path).exists()

        # Verify audit log JSONL exists
        audit_path = Path(tmpdir) / f"{state.investigation_id}_audit.jsonl"
        assert audit_path.exists()

        loaded_state = store.load_state(state.investigation_id)
        assert loaded_state.investigation_id == state.investigation_id
        assert "Alpha LLC" in loaded_state.entities
        assert len(loaded_state.audit_trail) == 1


def test_investigation_store_crash_and_resume():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = InvestigationStore(storage_dir=tmpdir)
        state = InvestigationState(
            objective="Crash Recovery Test",
            objective_contract={"max_steps": 10},
        )
        state.research_budget["steps_taken"] = 4
        state.stop_state.is_stopped = True
        store.save_state(state)

        # Simulate process restart and reload
        fresh_store = InvestigationStore(storage_dir=tmpdir)
        assert state.investigation_id in fresh_store.list_investigations()

        resumed = fresh_store.load_state(state.investigation_id)
        assert resumed.research_budget["steps_taken"] == 4
        assert resumed.stop_state.is_stopped is True
