"""Free-form objectives are read by their form, for any topic (V3 FC1 T10)."""

from __future__ import annotations

import pytest

from argus.investigation.planner import InvestigationPlanner
from argus.investigation.question_intent import classify_intent, extract_subjects


@pytest.mark.parametrize(
    "objective, subjects",
    [
        ("Who is the current CEO of Halvorsen Maritime?", ["Halvorsen Maritime"]),
        ("Why did Kestrel Air's K-200 get grounded?", ["Kestrel Air K-200"]),
        ("Compare Orbitra and Lumenfold for shipyards", ["Orbitra", "Lumenfold"]),
        ("Which clinics in Peru use Vantiq Health?", ["Vantiq Health"]),
        ("Does Norvale use Quillstack for payroll?", ["Norvale", "Quillstack"]),
        ("Which bakeries in Ohio sell Brindle Rye?", ["Brindle Rye"]),
    ],
)
def test_subjects_exclude_question_words_roles_and_places(objective, subjects):
    assert extract_subjects(objective) == subjects


@pytest.mark.parametrize(
    "objective, kind",
    [
        ("Why did the Tarrow bridge close?", "causal"),
        ("What are the main causes of the 2029 Velmar blackout?", "causal"),
        ("How does solid-state refrigeration work?", "mechanism"),
        ("Compare Orbitra and Lumenfold on pricing and support", "comparison"),
        ("What changed in the Dalven Data Act between 2027 and 2028?", "change"),
        ("Is Brightwater Ltd a sanctioned entity?", "yes_no"),
        ("Who founded Quillstack?", "role"),
        ("Find the headquarters address and employee count of Norvale", "attribute"),
        ("Summarize recent recalls of Kestrel scooters", "summary"),
    ],
)
def test_question_form_is_recognised(objective, kind):
    assert classify_intent(objective).kind == kind


def test_capital_is_not_read_as_api():
    planner = InvestigationPlanner()
    state = planner.initialize_investigation("What capital requirements apply to lenders in Kenya?")
    audit = next(a for a in state.audit_trail if a.action_type == "INVESTIGATION_INITIALIZED")
    assert audit.details["domain"] != "technical"
    texts = " ".join(q["question_text"] for q in state.questions.values()).lower()
    assert "metadata filtering" not in texts and "capital requirements" in texts


@pytest.mark.parametrize(
    "objective, expected_entity, expected_phrase",
    [
        ("Why did Kestrel Air's K-200 get grounded?", "Kestrel Air K-200", "causes or reasons"),
        ("Find the headquarters address and employee count of Norvale Group", "Norvale Group", "employee count of Norvale Group"),
        ("Who founded Quillstack and when?", "Quillstack", "founder of Quillstack"),
        ("Compare Orbitra and Lumenfold for shipyards", "Orbitra", "compare Orbitra and Lumenfold directly"),
    ],
)
def test_direct_questions_get_questions_about_what_was_asked(objective, expected_entity, expected_phrase):
    state = InvestigationPlanner().initialize_investigation(objective)
    assert expected_entity in state.entities
    texts = [q["question_text"] for q in state.questions.values()]
    assert any(expected_phrase.lower() in t.lower() for t in texts), texts
    assert not any("foundational concepts" in t for t in texts)
    assert all(q["search_queries"] for q in state.questions.values() if q["question_text"] != objective and "confirmed by more" not in q["question_text"])
