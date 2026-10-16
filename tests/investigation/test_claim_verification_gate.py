"""Regression tests for the shared claim verification boundary (V3 FC1 T02).

These drive the production observation path (``InvestigationEngine._apply_observation``)
and ``InvestigationState.add_claim`` with offline documents. They check that
claim status comes from verification against the claim's own cited evidence,
not from the extractor that produced it.
"""

from __future__ import annotations

from typing import Any

import pytest

from argus.investigation.action import ActionType, ResearchAction
from argus.investigation.claim_verification import (
    add_support,
    is_verified,
    registrable_domain,
    verify_claim,
)
from argus.investigation.orchestrator import InvestigationEngine
from argus.investigation.state import InvestigationState
from argus.investigation.store import InvestigationStore


OBJECTIVE = "Search Companies who are using TEAMCENTER in usa"
PROVIDER_URL = "https://theirstack.com/en/technology/siemens-teamcenter/us"
SECOND_PROVIDER_URL = "https://data.landbase.com/technology/siemens-teamcenter-plm-software/"
PRESS_URL = "https://www.manufacturing-weekly.example/2026/ford-plm-rollout"
ROW = "Ford Motor Company United States Motor Vehicle Manufacturing 177k $176B Siemens Teamcenter"


class _NoCorpus:
    """Offline stand-in: no discoverable vocabulary and no retrieval, like an exhausted live retriever."""

    def get_discoverable_entities(self) -> set[str]:
        return set()

    def search(self, query: str, limit: int = 5) -> list[Any]:
        return []

    def get_by_url(self, url: str) -> None:
        return None


@pytest.fixture()
def engine(tmp_path) -> InvestigationEngine:
    return InvestigationEngine(corpus=_NoCorpus(), store=InvestigationStore(tmp_path))


def _apply(engine: InvestigationEngine, state: InvestigationState, docs: list[tuple[str, str, str]]) -> None:
    documents = [
        {"url": url, "title": title, "text": text, "source_type": "live_web", "is_full_content": True}
        for url, title, text in docs
    ]
    action = ResearchAction(action_type=ActionType.FETCH, rationale="test", query=docs[0][0])
    engine._apply_observation(
        state,
        action,
        # Same shape as InvestigationEngine._execute_action builds it: "title text" joined by spaces.
        {"status": "SUCCESS", "documents": documents, "combined_text": " ".join(f"{d['title']} {d['text']}" for d in documents)},
    )


def _deployment_claims(state: InvestigationState, company: str) -> list[dict[str, Any]]:
    return [c for c in state.claims if c.get("subject") == company and str(c.get("predicate", "")).startswith("USES_")]


def test_cross_document_text_cannot_invent_a_finding(engine):
    """A pass over concatenated documents once invented 'News Our partners include Acme Widgets'."""
    state = InvestigationState(objective=OBJECTIVE)
    _apply(engine, state, [
        ("https://news.example.org/partners", "Partners", "Company News Our partners include Acme Widgets"),
        ("https://directory.example.net/listing", "United States Industrial Machinery 5k $1B Siemens Teamcenter", "Directory listing page."),
    ])
    assert not [c for c in state.claims if "Acme" in str(c.get("subject"))]
    assert not [e for e in state.entities if "Acme" in e]


def test_two_technographic_aggregators_do_not_corroborate(engine):
    state = InvestigationState(objective=OBJECTIVE)
    _apply(engine, state, [
        (PROVIDER_URL, "Companies that use Siemens Teamcenter", ROW),
        (SECOND_PROVIDER_URL, "Companies using Siemens Teamcenter", ROW),
    ])
    claims = _deployment_claims(state, "Ford Motor Company")
    assert len(claims) == 1
    claim = claims[0]
    assert claim["status"] == "TECHNOGRAPHIC_PROVIDER_ASSERTION"
    assert claim["confidence"] is None
    assert claim["verification"]["independent_voices"] == 1
    assert not is_verified(claim)


def test_aggregator_plus_independent_publisher_corroborates(engine):
    state = InvestigationState(objective=OBJECTIVE)
    _apply(engine, state, [
        (PROVIDER_URL, "Companies that use Siemens Teamcenter", ROW),
        (PRESS_URL, "Ford PLM rollout", "Ford Motor Company uses Siemens Teamcenter across its vehicle programs."),
    ])
    claims = _deployment_claims(state, "Ford Motor Company")
    assert len(claims) == 1
    assert claims[0]["status"] == "CORROBORATED"
    assert claims[0]["confidence"] is None
    assert is_verified(claims[0])


def test_independent_single_source_is_supported_without_fabricated_confidence(engine):
    state = InvestigationState(objective=OBJECTIVE)
    _apply(engine, state, [(PRESS_URL, "Boeing PLM", "Boeing uses Siemens Teamcenter for aircraft configuration.")])
    claims = _deployment_claims(state, "Boeing")
    assert len(claims) == 1
    assert claims[0]["status"] == "SUPPORTED"
    assert claims[0]["confidence"] is None


def test_incidental_hosts_and_emails_are_never_verified_findings(engine):
    state = InvestigationState(objective=OBJECTIVE)
    page = (
        "Companies that use Siemens Teamcenter in United States | TheirStack. "
        "Use our API at https://api.theirstack.com/v1/companies/search or status.theirstack.com. "
        "Payments secured by js.stripe.com. Widgets load from cdn.jsdelivr.net. "
        "API Export Company Country Industry Employees Revenue Technologies " + ROW + " "
        "Contact support@theirstack.com."
    )
    _apply(engine, state, [(PROVIDER_URL, "Companies that use Siemens Teamcenter in United States", page)])
    incidental = [c for c in state.claims if c.get("predicate") in ("infrastructure", "admin_contact")]
    for c in incidental:
        assert c["status"] == "UNVERIFIED", c
        assert not is_verified(c)
    assert not [c for c in state.claims if is_verified(c) and any(h in str(c.get("object")) for h in ("stripe", "jsdelivr", "support@"))]


def test_every_claim_cites_evidence_that_contains_its_passage(engine):
    state = InvestigationState(objective=OBJECTIVE)
    _apply(engine, state, [
        (PROVIDER_URL, "Companies that use Siemens Teamcenter", "Pricing. Contact support@theirstack.com. " + ROW),
        (PRESS_URL, "Ford PLM rollout", "Ford Motor Company uses Siemens Teamcenter across its vehicle programs."),
        ("https://example.org/about", "About", "Chief Executive Officer: Jane Doe. Our offices are in Ohio."),
    ])
    ev_by_id = {e["evidence_id"]: e for e in state.evidence}
    assert state.claims
    for c in state.claims:
        if not is_verified(c) and c.get("status") != "TECHNOGRAPHIC_PROVIDER_ASSERTION":
            continue
        ev = ev_by_id[c["evidence_id"]]
        assert c["source_url"] == ev["url"]
        assert " ".join(c["source_passage"].split()) in " ".join(ev["snippet"].split())


def test_gate_rejects_regex_style_claims_that_the_cited_passage_does_not_state():
    state = InvestigationState(objective="test")
    ev_id = state.add_evidence({"url": "https://example.org/a", "snippet": "Acme Corp announced record revenue this quarter."})

    # Proposed SUPPORTED, but the passage never mentions the object.
    c1 = {"subject": "Acme Corp", "predicate": "officer", "object": "John Smith", "status": "SUPPORTED",
          "evidence_id": ev_id, "source_passage": "Acme Corp announced record revenue this quarter."}
    state.add_claim(c1)
    assert c1["status"] == "UNVERIFIED"
    assert c1["verification"]["reason"] == "passage_does_not_mention_claim_terms"

    # Proposed SUPPORTED with no evidence at all.
    c2 = {"subject": "Acme Corp", "predicate": "finding", "object": "x", "status": "SUPPORTED", "confidence": 0.9}
    state.add_claim(c2)
    assert c2["status"] == "UNVERIFIED" and c2["confidence"] is None

    # Passage that is not in the cited evidence.
    c3 = {"subject": "Acme Corp", "predicate": "finding", "object": "revenue", "status": "SUPPORTED",
          "evidence_id": ev_id, "source_passage": "Acme Corp revenue fell sharply."}
    state.add_claim(c3)
    assert c3["verification"]["reason"] == "passage_not_in_cited_evidence"

    # Citation URL that is not the cited evidence's URL.
    c4 = {"subject": "Acme Corp", "predicate": "finding", "object": "revenue", "status": "SUPPORTED",
          "evidence_id": ev_id, "source_url": "https://other.example/b",
          "source_passage": "Acme Corp announced record revenue this quarter."}
    state.add_claim(c4)
    assert c4["verification"]["reason"] == "citation_url_mismatch"

    # Negated passage cannot support.
    ev2 = state.add_evidence({"url": "https://example.org/b", "snippet": "Globex does not use Siemens Teamcenter."})
    c5 = {"subject": "Globex", "predicate": "USES_SOFTWARE", "object": "Siemens Teamcenter", "status": "SUPPORTED",
          "evidence_id": ev2, "source_passage": "Globex does not use Siemens Teamcenter."}
    state.add_claim(c5)
    assert c5["status"] == "INSUFFICIENT_EVIDENCE"
    assert not any(is_verified(c) for c in (c1, c2, c3, c4, c5))


def test_vendor_confirmation_requires_the_vendors_own_site():
    evidence = [
        {"evidence_id": "e1", "url": "https://news.siemens.com/en/ford", "snippet": "Ford Motor Company standardizes on Siemens Teamcenter."},
        {"evidence_id": "e2", "url": "https://www.oracle.com/blog/x", "snippet": "Ford Motor Company standardizes on Siemens Teamcenter."},
    ]
    base = {"subject": "Ford Motor Company", "predicate": "USES_SOFTWARE", "object": "Siemens Teamcenter",
            "status": "VENDOR_CONFIRMED", "source_passage": "Ford Motor Company standardizes on Siemens Teamcenter."}
    vendor = verify_claim(dict(base, evidence_id="e1"), evidence)
    other = verify_claim(dict(base, evidence_id="e2"), evidence)
    assert vendor["status"] == "VENDOR_CONFIRMED"
    assert other["status"] == "SUPPORTED"
    assert registrable_domain("https://news.siemens.com/x") == "siemens.com"


def test_unverified_candidate_cannot_upgrade_a_claim():
    evidence = [
        {"evidence_id": "e1", "url": PROVIDER_URL, "snippet": ROW},
        {"evidence_id": "e2", "url": PRESS_URL, "snippet": "Unrelated article about trucks."},
    ]
    claim = verify_claim({"subject": "Ford Motor Company", "predicate": "USES_PLM_SOFTWARE", "object": "Siemens Teamcenter",
                          "status": "TECHNOGRAPHIC_PROVIDER_ASSERTION", "evidence_id": "e1", "source_passage": ROW}, evidence)
    bogus = verify_claim({"subject": "Ford Motor Company", "predicate": "USES_PLM_SOFTWARE", "object": "Siemens Teamcenter",
                          "status": "SUPPORTED", "evidence_id": "e2", "source_passage": "Unrelated article about trucks."}, evidence)
    add_support(claim, bogus)
    assert claim["status"] == "TECHNOGRAPHIC_PROVIDER_ASSERTION"


def test_terminal_verified_count_excludes_provider_assertions_and_unverified():
    from argus.terminal import OSINTTerminal

    claims = [
        {"status": "TECHNOGRAPHIC_PROVIDER_ASSERTION", "verification": {"passed": True}},
        {"status": "SUPPORTED", "verification": {"passed": False}},
        {"status": "SUPPORTED"},
        {"status": "SUPPORTED", "verification": {"passed": True}},
        {"status": "CORROBORATED", "verification": {"passed": True}},
    ]
    assert sum(1 for c in claims if is_verified(c)) == 2
    # The summary panel uses the same predicate.
    import inspect

    src = inspect.getsource(OSINTTerminal._display_summary_panel)
    assert "is_verified(c)" in src


def test_confidence_state_counts_only_gate_verified_claims():
    state = InvestigationState(objective="test")
    ev_id = state.add_evidence({"url": "https://example.org/a", "snippet": "Acme Corp announced record revenue."})
    state.add_claim({"subject": "Acme Corp", "predicate": "infrastructure", "object": "cdn.example.net", "status": "SUPPORTED",
                     "evidence_id": ev_id, "source_passage": "Acme Corp announced record revenue."})
    state.confidence_state.recompute_calibration(state)
    assert state.confidence_state.confirmed_claims_count == 0
