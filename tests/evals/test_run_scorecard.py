"""Every question asked records one row of numbers, so runs can be compared."""

import csv
import json

from argus.evals.run_scorecard import COLUMNS, read_runs, record_run, score_run

RUN = {
    "objective": "Which hospitals in Ohio use Epic?",
    "enumeration_objective": {"raw": "Which hospitals in Ohio use Epic?", "answer_type": "ORGANIZATION",
                              "answer_noun": "hospitals", "relation": "uses", "relation_phrase": "use",
                              "object": "Epic", "geography": "Ohio"},
    "stop_reason": "OBJECTIVE_SATISFIED",
    "claims": [
        {"subject": "Mercy General", "predicate": "uses_software", "object": "Epic", "status": "CORROBORATED",
         "citation": "https://jobs.lever.co/mercy/a", "evidence_id": "e1", "source_passage": "Epic analyst, Columbus."},
        {"subject": "Mercy General", "predicate": "uses_software", "object": "Epic", "status": "SUPPORTED",
         "citation": "https://mercy.example/it", "evidence_id": "e2", "source_passage": "Our Epic rollout."},
        {"subject": "Mercy General", "predicate": "website", "object": "https://mercy.example/", "status": "SUPPORTED",
         "evidence_id": "e2"},
        {"subject": "Lakeside Clinic", "predicate": "uses_software", "object": "Epic", "status": "SUPPORTED",
         "citation": "https://lakeside.example/jobs", "evidence_id": "e3", "source_passage": "Epic MyChart support."},
    ],
    "rejected_claims": [{"subject": "Nope Ltd", "predicate": "uses_software", "object": "Epic"}],
    "evidence": [{"evidence_id": "e1", "url": "https://jobs.lever.co/mercy/a"},
                 {"evidence_id": "e2", "url": "https://mercy.example/it"},
                 {"evidence_id": "e3", "url": "https://lakeside.example/jobs"}],
    "research_actions": [{"action_type": "SEARCH", "query": "ohio hospital epic"},
                         {"action_type": "SEARCH", "query": "epic mychart ohio"},
                         {"action_type": "FETCH", "query": "https://mercy.example/it"}],
    "audit_trail": [{"action_type": "PAGE_SKIPPED_BY_TRIAGE"}, {"action_type": "SEARCH_EXECUTED"}],
    "decisions": {"decisions": 40, "by_laya": 12, "by_rule": 28, "laya_disagreed_with_rule": 5},
    "unresolved_questions": ["Employee counts not found"],
    "limitations": ["Indeed was not read."],
    "page_reader": "openrouter:qwen:free (12 pages read, 0 failures)",
    "decision_engine": "Laya",
}


def test_the_numbers_describe_the_output_and_the_run():
    row = score_run(RUN, seconds=42.4).row
    assert row["question"] == "Which hospitals in Ohio use Epic?"
    assert (row["answers"], row["answers_strong"], row["answers_moderate"], row["answers_weak"]) == (2, 1, 1, 0)
    assert row["strong_share"] == 0.5 and row["quote_share"] == 1.0
    assert row["sources_per_answer"] == 1.5           # Mercy on two sites, Lakeside on one
    assert row["attributes_per_answer"] == 0.5        # one of two answers has a website
    assert (row["claims_kept"], row["claims_rejected"]) == (4, 1)
    assert row["gate_rejection_rate"] == 0.2
    assert (row["pages_read"], row["sites_read"], row["searches"], row["steps"]) == (3, 3, 2, 3)
    assert row["pages_skipped_by_triage"] == 1
    assert row["model_pages_read"] == 12
    assert (row["decisions"], row["decisions_by_laya"], row["laya_differed"]) == (40, 12, 5)
    assert (row["unresolved_questions"], row["limitations"], row["seconds"]) == (1, 1, 42.4)
    assert row["stop_reason"] == "OBJECTIVE_SATISFIED"


def test_a_run_that_found_nothing_scores_zero_without_dividing_by_zero():
    row = score_run({"objective": "anything", "claims": [], "rejected_claims": []}).row
    assert row["answers"] == 0 and row["strong_share"] == 0.0 and row["sources_per_answer"] == 0.0
    assert row["gate_rejection_rate"] == 0.0


def test_every_question_appends_one_row_to_one_history(tmp_path):
    record_run(RUN, seconds=10.0, export_dir=tmp_path)
    record_run(RUN, seconds=11.0, export_dir=tmp_path)
    csv_path = tmp_path / "evals" / "runs.csv"
    with csv_path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == COLUMNS and len(rows) == 3
    history = read_runs(tmp_path)
    assert [r["seconds"] for r in history] == ["10.0", "11.0"]
    assert history[0]["question"] == "Which hospitals in Ohio use Epic?"


def test_the_numbers_are_saved_beside_the_run_recording(tmp_path):
    run_dir = tmp_path / "runs" / "a_run"
    run_dir.mkdir(parents=True)
    record_run({**RUN, "run_dir": str(run_dir)}, seconds=5.0, export_dir=tmp_path)
    saved = json.loads((run_dir / "scorecard.json").read_text(encoding="utf-8"))
    assert saved["answers"] == 2 and saved["seconds"] == 5.0


def test_reading_an_empty_history_is_not_an_error(tmp_path):
    assert read_runs(tmp_path) == []


def test_the_command_line_prints_the_history_and_groups_it_by_question(tmp_path, capsys, monkeypatch):
    import sys

    from argus.evals import run_scorecard

    record_run(RUN, seconds=10.0, export_dir=tmp_path)
    record_run({**RUN, "objective": "Which vineyards in Oregon grow Pinot Noir?"}, seconds=20.0, export_dir=tmp_path)
    monkeypatch.setattr(sys, "argv", ["run_scorecard", "--export-dir", str(tmp_path), "--compare"])
    run_scorecard.main()
    out = capsys.readouterr().out
    assert "Which hospitals in Ohio use Epic?  (1 run)" in out
    assert "Which vineyards in Oregon grow Pinot Noir?  (1 run)" in out
    assert "answers_strong" in out


def test_a_recorded_run_can_be_scored_offline(tmp_path, capsys, monkeypatch):
    import sys

    from argus.evals import run_scorecard

    run_dir = tmp_path / "runs" / "a_run"
    run_dir.mkdir(parents=True)
    (run_dir / "result.json").write_text(json.dumps(RUN), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["run_scorecard", "--run", str(run_dir)])
    run_scorecard.main()
    assert "answers" in capsys.readouterr().out
