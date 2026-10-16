"""Regression tests for epistemic-status detection (V3 FC1 T07).

Three holdout failures predate the T05 stopping rules:

- A source that says "later analyses contradict the cometary model" produced no
  contradiction: the list of dispute cues in the engine was never used, and the
  value-comparison resolver only sees numeric or categorical conflicts.
- A filing that says "earlier reports ... are outdated" was not recorded either.
  The source resolves that conflict itself, so it must be recorded as resolved.
- The lookalike/phishing rule ran on any document, cited a threat word from the
  title that the cited sentence did not contain, and, when the user asked about the
  malicious package itself, asserted that the package disavows itself.

All entities below are fictional.
"""

from __future__ import annotations

import tempfile
from typing import Any

from argus.investigation.action import ActionType, ResearchAction
from argus.investigation.claim_verification import ground_passage, is_verified
from argus.investigation.orchestrator import InvestigationEngine
from argus.investigation.question import InvestigationQuestion, QuestionStatus, QuestionType
from argus.investigation.state import InvestigationState
from argus.investigation.store import InvestigationStore

from tests.investigation.test_objective_scoped_extraction import FixtureCorpus


def _engine() -> InvestigationEngine:
    return InvestigationEngine(corpus=FixtureCorpus([], {}), store=InvestigationStore(tempfile.mkdtemp()))


def _state_with_question(target: str, text: str = "") -> tuple[InvestigationState, str]:
    state = InvestigationState(objective=text or f"Investigate {target}")
    state.objective_contract["target_entities"] = [target]
    q = InvestigationQuestion(
        question_text=text or f"Investigate {target}",
        question_type=QuestionType.GENERAL,
        related_entities=[target],
        is_critical=True,
    )
    state.questions[q.question_id] = q.model_dump()
    state.unresolved_questions.append(q.question_id)
    return state, q.question_id


def _observe(engine: InvestigationEngine, state: InvestigationState, qid: str, target: str,
             url: str, title: str, text: str) -> None:
    action = ResearchAction(action_type=ActionType.FETCH, rationale="test", query=url,
                            question_id=qid, target_entities=[target])
    engine._apply_observation(state, action, {
        "status": "SUCCESS",
        "documents": [{"url": url, "title": title, "text": text, "source_type": "live_web"}],
        "combined_text": f"{title} {text}",
    })


DISPUTE_TEXT = (
    "Field geologist Mara Ostrova argued the Kessling Crater Event was caused by a volcanic gas release. "
    "However, later isotopic analyses contradict the volcanic model, pointing to a meteoroid airburst. "
    "The competing accounts remain under active debate."
)


def test_source_reported_dispute_is_recorded_as_an_open_contradiction():
    engine = _engine()
    state, qid = _state_with_question("Kessling Crater Event")
    _observe(engine, state, qid, "Kessling Crater Event", "https://geo.example/kessling",
             "The Kessling Crater Event: competing accounts", DISPUTE_TEXT)

    recs = [c for c in state.contradictions if c.get("property_dim") == "reported_dispute"]
    assert len(recs) == 1
    rec = recs[0]
    assert rec["status"] == "UNRESOLVED_CONTRADICTION"
    assert rec["subject"] == "Kessling Crater Event"
    assert "contradict the volcanic model" in rec["claim_b"]
    assert "Mara Ostrova argued" in rec["claim_a"]

    conflict = [c for c in state.claims if c.get("predicate") == "conflict_noted"]
    assert conflict and conflict[0]["status"] == "CONTRADICTED"
    # The conflict claim cites the stating sentence, verbatim from the retrieved source.
    ev = next(e for e in state.evidence if e.get("evidence_id") == conflict[0]["evidence_id"])
    assert conflict[0]["source_passage"] in ev.get("snippet", "") + ev.get("text", "")
    assert state.questions[qid]["status"] == QuestionStatus.CONTRADICTED.value
    assert any(a.action_type == "SOURCE_REPORTED_CONFLICT" for a in state.audit_trail)


SUPERSESSION_TEXT = (
    "Form 8-K for Orvex Bio Labs: On March 3, 2026, the board appointed Lena Carrow as permanent Chief Executive Officer, "
    "succeeding interim CEO Dr. Paul Iver. Earlier reports naming Dr. Paul Iver as current CEO are outdated."
)


def test_source_reported_supersession_is_recorded_as_resolved_and_contradicts_nothing():
    engine = _engine()
    state, qid = _state_with_question("Orvex Bio Labs")
    _observe(engine, state, qid, "Orvex Bio Labs", "https://orvex.example/8k", "Orvex Bio Labs Form 8-K", SUPERSESSION_TEXT)

    recs = [c for c in state.contradictions if c.get("property_dim") == "reported_supersession"]
    assert len(recs) == 1
    assert recs[0]["status"] == "RESOLVED_BY_SUPERSESSION"
    assert recs[0]["discrepancy_type"] == "TEMPORAL_SUPERSEDED"
    assert "outdated" in recs[0]["claim_b"]
    assert not [c for c in state.claims if c.get("status") == "CONTRADICTED"]
    assert state.questions[qid]["status"] != QuestionStatus.CONTRADICTED.value


def test_ordinary_wording_is_not_read_as_a_dispute():
    from argus.investigation.reported_disputes import classify_sentence

    assert classify_sentence("The new measurement does not contradict earlier findings.") is None
    assert classify_sentence("The board adopted a conflict of interest policy in 2024.") is None
    assert classify_sentence("Customers can dispute a charge through the portal.") is None
    assert classify_sentence("Two teams published differing estimates of the blast yield.") == "dispute"
    assert classify_sentence("The 2019 guidance is superseded by the 2024 rule.") == "supersession"


def test_dispute_in_a_document_about_another_subject_is_not_attributed_to_the_target():
    engine = _engine()
    state, qid = _state_with_question("Orvex Bio Labs")
    _observe(engine, state, qid, "Orvex Bio Labs", "https://geo.example/kessling",
             "The Kessling Crater Event: competing accounts", DISPUTE_TEXT)
    assert not state.contradictions
    assert state.questions[qid]["status"] != QuestionStatus.CONTRADICTED.value


def test_open_contradiction_about_another_subject_does_not_contradict_this_question():
    engine = _engine()
    state, qid = _state_with_question("Veltrano Robotics")
    state.contradictions.append({
        "topic": "Kessling Crater Event: dispute reported by source", "subject": "Kessling Crater Event",
        "property_dim": "reported_dispute", "status": "UNRESOLVED_CONTRADICTION",
    })
    _observe(engine, state, qid, "Veltrano Robotics", "https://veltrano.example/about", "About Veltrano Robotics",
             "Veltrano Robotics was founded in 2020 by Dr. Ines Marlow in Turin.")
    assert state.questions[qid]["status"] != QuestionStatus.CONTRADICTED.value


MALWARE_TEXT = (
    "Security researchers discovered a malicious typosquatted package named 'pyyamle-utils' published to public repositories. "
    "The package exfiltrates SSH keys to a remote host and is unrelated to the legitimate PyYAML project."
)


def test_malicious_package_that_is_the_target_is_confirmed_not_disavowed():
    engine = _engine()
    state, qid = _state_with_question("pyyamle-utils")
    _observe(engine, state, qid, "pyyamle-utils", "https://advisories.example/pyyamle-utils",
             "Advisory: Malicious Typosquatting of PyYAML", MALWARE_TEXT)

    assert not [c for c in state.claims if c.get("predicate") == "affiliation"]
    assert not [c for c in state.claims if c.get("status") == "CONTRADICTED"]
    sec = [c for c in state.claims if c.get("predicate") == "security_assessment"]
    assert len(sec) == 1 and is_verified(sec[0]), sec
    assert "pyyamle-utils" in sec[0]["source_passage"] and "malicious" in sec[0]["source_passage"].lower()
    assert state.questions[qid]["status"] != QuestionStatus.CONTRADICTED.value


def test_lookalike_rule_ignores_documents_about_other_targets():
    engine = _engine()
    state, qid = _state_with_question("Veltrano Robotics")
    _observe(engine, state, qid, "Veltrano Robotics", "https://advisories.example/pyyamle-utils",
             "Advisory: Malicious Typosquatting of PyYAML", MALWARE_TEXT)
    assert not [c for c in state.claims if c.get("predicate") in ("affiliation", "security_assessment")]


def test_phishing_domain_impersonating_the_target_is_disavowed_with_a_grounded_finding():
    engine = _engine()
    state, qid = _state_with_question("Brindle Pay")
    text = ("Brindle Pay warned customers on May 2, 2026. "
            "The domain brindle-pay-login.com is a phishing site that imitates the Brindle Pay sign-in page.")
    _observe(engine, state, qid, "Brindle Pay", "https://brindlepay.example/security", "Brindle Pay security notice", text)

    aff = [c for c in state.claims if c.get("predicate") == "affiliation"]
    assert aff and aff[0]["subject"] == "brindle-pay-login.com" and aff[0]["status"] == "CONTRADICTED"
    sec = next(c for c in state.claims if c.get("predicate") == "security_assessment")
    assert is_verified(sec) and "phishing" in sec["source_passage"]


def test_resignation_names_the_person_not_the_surrounding_role_words():
    engine = _engine()
    state, qid = _state_with_question("Orvex Bio Labs")
    text = ("Orvex Bio Labs announced that founder and Chief Executive Officer Dr. Paul Iver has stepped down "
            "from executive duties effective July 15, 2025.")
    _observe(engine, state, qid, "Orvex Bio Labs", "https://orvex.example/news", "Orvex Bio Labs press release", text)

    tenure = [c for c in state.claims if c.get("predicate") == "tenure_status"]
    assert [c["subject"] for c in tenure] == ["Dr. Paul Iver"]
    assert is_verified(tenure[0]) and "stepped down" in tenure[0]["source_passage"]


def test_honorific_does_not_split_a_cited_sentence():
    text = "The board named Dr. Paul Iver chair. He served until 2024."
    assert ground_passage(text, ["Dr. Paul Iver", "chair"]) == "The board named Dr. Paul Iver chair."
