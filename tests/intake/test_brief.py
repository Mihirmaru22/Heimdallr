"""The research brief: what the form collects, what it compiles to, what it changes."""

import json

import pytest

from argus.export.answer_rows import build_answer_rows, excluded_by_brief
from argus.intake.brief import FIELDS, ResearchBrief, brief_from_data

FILLED = {
    "looking_for": "hospitals", "criterion": "use Epic", "where": "Ohio",
    "attributes": ["website", "approximate size"], "evidence_floor": "quoted",
    "evidence_kinds": ["Job post", "Case study"], "exclude_answers": "Epic Systems\nAccenture",
    "exclude_sites": "aggregator.example", "seed_urls": "https://trusted.example/list",
    "known_examples": "Mercy General", "how_many": "25", "depth": "quick", "notes": "state hospitals count too",
}


def test_a_form_run_lists_the_subjects_without_depending_on_the_phrasing():
    """The form says what it is looking for, so the answers do not hinge on parsing the sentence."""
    data = run_with(FILLED, [claim("Lakeside Clinic")])
    data.pop("enumeration_objective", None)
    _, rows = build_answer_rows(data)
    assert [r.answer for r in rows] == ["Lakeside Clinic"]


def test_the_form_compiles_to_a_question_in_the_users_words():
    brief = ResearchBrief.from_answers(FILLED)
    question = brief.to_objective()
    assert question.startswith("Which hospitals use Epic in Ohio?")
    assert "Include each one's website and approximate size." in question
    assert "state hospitals count too." in question
    assert "https://trusted.example/list" in question  # fetched first, by the existing link path


def test_the_contract_carries_the_budget_the_count_and_the_brief():
    contract = ResearchBrief.from_answers(FILLED).to_contract()
    assert contract["max_steps"] == 15                      # quick
    assert contract["target_answer_count"] == 25
    assert contract["known_context"] == {"known_answers": ["Mercy General"]}
    assert contract["brief"]["criterion"] == "use Epic"


def test_the_two_needed_answers_are_the_only_required_ones():
    with pytest.raises(ValueError, match="What are you looking for"):
        ResearchBrief.from_answers({"criterion": "use Epic"})
    with pytest.raises(ValueError, match="What must be true"):
        ResearchBrief.from_answers({"looking_for": "hospitals"})
    brief = ResearchBrief.from_answers({"looking_for": "hospitals", "criterion": "use Epic"})
    assert brief.to_objective() == "Which hospitals use Epic?"


@pytest.mark.parametrize("bad,message", [
    ({"evidence_floor": "whatever"}, "Minimum evidence"),
    ({"depth": "forever"}, "Depth"),
    ({"how_many": "lots"}, "whole number"),
    ({"how_many": "0"}, "whole number"),
    ({"seed_urls": "trusted.example/list"}, "http"),
    ({"evidence_kinds": ["Tweet"]}, "Unknown evidence kind"),
])
def test_unusable_answers_are_refused_with_a_reason(bad, message):
    with pytest.raises(ValueError, match=message):
        ResearchBrief.from_answers({**FILLED, **bad})


def test_a_brief_is_saved_and_reloaded_so_a_run_can_be_repeated(tmp_path):
    brief = ResearchBrief.from_answers(FILLED)
    path = brief.save(tmp_path)
    assert json.loads(path.read_text())["looking_for"] == "hospitals"
    assert ResearchBrief.load(path).to_objective() == brief.to_objective()


def test_every_field_says_what_it_changes():
    for f in FIELDS:
        assert f.effect and f.help and f.label
        assert f.kind in ("text", "long_text", "choice", "multi_choice", "number")


# --- what the brief does to the answers --------------------------------------------------------

def claim(subject, obj="Epic", status="SUPPORTED", url="https://jobs.lever.co/x", quote="Epic analyst.", eid="e1",
          predicate="uses_software"):
    return {"subject": subject, "predicate": predicate, "object": obj, "status": status,
            "citation": url, "evidence_id": eid, "source_passage": quote}


def run_with(brief_answers, claims):
    brief = ResearchBrief.from_answers(brief_answers)
    return {
        "objective": brief.to_objective(), "brief": brief.as_dict(), "claims": claims,
        "evidence": [{"evidence_id": c["evidence_id"], "url": c["citation"]} for c in claims],
        "rejected_claims": [], "research_actions": [], "audit_trail": [],
    }


def test_the_answer_column_is_named_by_the_form():
    data = run_with(FILLED, [claim("Lakeside Clinic")])
    from argus.export.answer_rows import answer_noun

    assert answer_noun(data) == "hospitals"


def test_an_excluded_name_never_reaches_the_answers():
    data = run_with(FILLED, [claim("Lakeside Clinic"), claim("Accenture", eid="e2")])
    _, rows = build_answer_rows(data)
    assert [r.answer for r in rows] == ["Lakeside Clinic"]
    assert excluded_by_brief(data) == {"you asked to leave it out": 1}


def test_an_excluded_site_cannot_support_an_answer():
    data = run_with(FILLED, [claim("Lakeside Clinic", url="https://aggregator.example/list")])
    _, rows = build_answer_rows(data)
    assert rows == []
    assert excluded_by_brief(data) == {"its only evidence was on a site you excluded": 1}


def test_the_evidence_floor_leaves_weak_answers_out_and_counts_them():
    quoted_only = {**FILLED, "evidence_floor": "quoted"}
    data = run_with(quoted_only, [claim("Lakeside Clinic", quote=""), claim("Mercy General", eid="e2")])
    _, rows = build_answer_rows(data)
    assert [r.answer for r in rows] == ["Mercy General"]
    assert excluded_by_brief(data) == {"below your evidence floor (quoted)": 1}

    two_sites = {**FILLED, "evidence_floor": "two_sources"}
    data = run_with(two_sites, [claim("Mercy General", eid="e2")])
    assert build_answer_rows(data)[1] == []


def test_only_the_evidence_kinds_asked_for_are_accepted():
    news_only = {**FILLED, "evidence_kinds": ["News"]}
    data = run_with(news_only, [claim("Lakeside Clinic", url="https://jobs.lever.co/x")])
    _, rows = build_answer_rows(data)
    assert rows == []
    assert "did not accept" in next(iter(excluded_by_brief(data)))


def test_answers_already_on_the_users_list_are_marked_not_hidden():
    data = run_with(FILLED, [claim("Mercy General"), claim("Lakeside Clinic", eid="e2")])
    _, rows = build_answer_rows(data)
    known = {r.answer: r.known_to_user for r in rows}
    assert known == {"Mercy General": True, "Lakeside Clinic": False}


def test_a_plain_question_is_unaffected_by_any_of_this():
    data = {"objective": "Which hospitals use Epic?", "claims": [claim("Accenture")],
            "enumeration_objective": {"raw": "Which hospitals use Epic?", "answer_type": "ORGANIZATION",
                                      "answer_noun": "hospitals", "relation": "uses",
                                      "relation_phrase": "use", "object": "Epic"},
            "evidence": [{"evidence_id": "e1", "url": "https://jobs.lever.co/x"}]}
    assert brief_from_data(data) is None
    _, rows = build_answer_rows(data)
    assert [r.answer for r in rows] == ["Accenture"]
    assert excluded_by_brief(data) == {}
