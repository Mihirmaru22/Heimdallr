"""Integration test for the Flagship Apple-Style 20-Executive Leadership Investigation Scenario.

Tests Section 17 requirements:
- Decompose objective into executive research branches
- Maintain state across 20 branches
- Resolve identities and handle missing contact info without hallucination
- Distinguish SUPPORTED vs NOT_FOUND
- Stop individual branches independently and stop overall investigation intelligently
- Produce an auditable final dossier
"""

import pytest

from argus.investigation.benchmark.corpus import APEX_20_EXECUTIVES, INVESTIGATION_CORPUS_REGISTRY
from argus.investigation.orchestrator import InvestigationEngine
from argus.investigation.stopping import InvestigationStopReason


def test_apple_style_20_executives_investigation():
    engine = InvestigationEngine(corpus=INVESTIGATION_CORPUS_REGISTRY)
    objective = (
        "Research Apex Technologies Group. Identify 20 current VP/SVP-level executives. For each executive determine: "
        "name, current title, responsibility, organization, current status, career history, professional identity, "
        "and publicly documented business contact channel. Do NOT invent contact information. Distinguish SUPPORTED, "
        "UNKNOWN, and NOT_FOUND."
    )
    contract = {
        "target_entities": ["Apex Technologies Group"],
        "expected_executive_count": 20,
        "max_steps": 12,
    }

    state = engine.run_to_completion(
        objective=objective,
        contract=contract,
        max_steps=12,
    )

    # 1. Verify Stopping Decision
    assert state.stop_state.is_stopped is True
    assert state.stop_state.stop_reason in [
        InvestigationStopReason.OBJECTIVE_SATISFIED.value,
        InvestigationStopReason.SUFFICIENT_EVIDENCE.value,
    ]

    # 2. Verify all 20 executives are registered as entities
    for ex in APEX_20_EXECUTIVES:
        assert ex["name"] in state.entities, f"Executive {ex['name']} missing from registered entities."

    # 3. Verify exactly 20 executive branches were completed
    assert len(state.completed_branches) >= 20

    # 4. Verify Contact Channel Scrutiny: No invented emails!
    # Executives with known public emails (e.g. Sarah Lin, David Marcus) -> marked SUPPORTED
    # Executives with no public emails (e.g. Elena Rostova, Chloe Bennett) -> marked NOT_FOUND
    contacts_found = {
        c["subject"]: c["object"]
        for c in state.claims
        if c.get("predicate") == "contact_channel"
    }

    assert contacts_found.get("Sarah Lin") == "slin-ops@apex-tech.com"
    assert contacts_found.get("David Marcus") == "dmarcus-research@apex-tech.com"
    assert contacts_found.get("Elena Rostova") == "NOT_FOUND"
    assert contacts_found.get("Chloe Bennett") == "NOT_FOUND"

    # 5. Verify Claims Count and Evidence Provenance
    assert len(state.claims) >= 100
    assert len(state.evidence) >= 6
    for ev in state.evidence:
        assert "url" in ev
        assert "title" in ev
        assert "source_type" in ev

    # 6. Verify Full Auditable Dossier
    assert len(state.audit_trail) >= 20
    summary = state.summary()
    assert summary["entities_count"] >= 20
    assert summary["is_stopped"] is True
    assert summary["stop_reason"] in ["OBJECTIVE_SATISFIED", "SUFFICIENT_EVIDENCE"]
