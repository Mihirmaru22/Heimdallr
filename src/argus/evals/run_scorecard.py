"""A numbered scorecard for every question asked, so runs can be compared over time.

Every run of `osint-terminal` appends one row to `exports/evals/runs.csv` and writes the same
numbers as `scorecard.json` beside the run recording. The row holds the question, what came out
(answers and their evidence) and the state of the run (pages, gate, decisions, time), all as
numbers, so two runs of the same question or runs after a change can be compared without reading
the reports.

    python -m argus.evals.run_scorecard                  # the table of every run recorded so far
    python -m argus.evals.run_scorecard --question SAP   # only runs whose question contains "SAP"
    python -m argus.evals.run_scorecard --run exports/runs/<run>   # score a recorded run offline
    python -m argus.evals.run_scorecard --compare        # the same question's runs side by side

Nothing here judges whether an answer is true: that needs a reference list, which
`argus.evals.list_benchmark` scores. These numbers say how much the run found, how well evidenced
it was, and what it cost.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from typing import Any

from argus.export.answer_rows import MODERATE, STRONG, WEAK, build_answer_rows

RUNS_CSV = "runs.csv"
SCORECARD_FILE = "scorecard.json"

# The columns of runs.csv, in order. Every one but the first four is a number.
COLUMNS = [
    "asked_at", "question", "commit", "stop_reason",
    # what came out
    "answers", "answers_strong", "answers_moderate", "answers_weak", "strong_share",
    "answers_with_quote", "quote_share", "sources_per_answer", "attributes_per_answer",
    # the evidence behind it
    "claims_kept", "claims_rejected", "gate_rejection_rate", "pages_read", "sites_read",
    "searches", "steps", "pages_skipped_by_triage", "model_pages_read", "reader",
    # the decisions
    "decisions", "decisions_by_laya", "decisions_by_rule", "laya_differed",
    # what it left open
    "unresolved_questions", "limitations", "seconds",
]


def _git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _share(part: int, whole: int) -> float:
    return round(part / whole, 3) if whole else 0.0


def _int_in(text: str) -> int:
    """The first whole number in a string, or 0. ("openrouter:x (12 pages read, 0 failures)")"""
    digits = ""
    for ch in str(text or ""):
        if ch.isdigit():
            digits += ch
        elif digits:
            break
    return int(digits) if digits else 0


@dataclass
class Scorecard:
    row: dict[str, Any]

    def as_csv_row(self) -> list[Any]:
        return [self.row.get(c, "") for c in COLUMNS]

    def table_lines(self) -> list[str]:
        width = max(len(c) for c in COLUMNS)
        return [f"{c:<{width}}  {self.row.get(c, '')}" for c in COLUMNS]


def score_run(data: dict[str, Any], seconds: float = 0.0) -> Scorecard:
    """The numbers of one run, from the same payload the reports are built from."""
    extra_columns, rows = build_answer_rows(data)
    strengths = [r.evidence_strength for r in rows]
    quoted = sum(1 for r in rows if r.evidence_says.strip())
    kept = len(data.get("claims") or [])
    rejected = len(data.get("rejected_claims") or [])
    evidence = data.get("evidence") or []
    urls = {e.get("url") for e in evidence if e.get("url")}
    sites = {str(u).split("/")[2] for u in urls if str(u).count("/") >= 2}
    actions = data.get("research_actions") or []
    audit = data.get("audit_trail") or []
    decisions = data.get("decisions") or {}

    def action_type(item: Any) -> str:
        value = item.get("action_type") if isinstance(item, dict) else getattr(item, "action_type", "")
        return str(getattr(value, "value", value) or "")

    row = {
        "asked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "question": str(data.get("objective") or data.get("target") or ""),
        "commit": _git_commit(),
        "stop_reason": str(data.get("stop_reason") or "UNKNOWN"),
        "answers": len(rows),
        "answers_strong": strengths.count(STRONG),
        "answers_moderate": strengths.count(MODERATE),
        "answers_weak": strengths.count(WEAK),
        "strong_share": _share(strengths.count(STRONG), len(rows)),
        "answers_with_quote": quoted,
        "quote_share": _share(quoted, len(rows)),
        "sources_per_answer": round(sum(r.sources for r in rows) / len(rows), 2) if rows else 0.0,
        "attributes_per_answer": round(
            sum(len([c for c in extra_columns if r.attributes.get(c)]) for r in rows) / len(rows), 2
        ) if rows else 0.0,
        "claims_kept": kept,
        "claims_rejected": rejected,
        "gate_rejection_rate": _share(rejected, kept + rejected),
        "pages_read": len(urls),
        "sites_read": len(sites),
        "searches": sum(1 for a in actions if action_type(a).upper() == "SEARCH"),
        "steps": len(actions),
        "pages_skipped_by_triage": sum(1 for a in audit if action_type(a) == "PAGE_SKIPPED_BY_TRIAGE"),
        "model_pages_read": _int_in(data.get("page_reader") or ""),
        # Which model read the pages: a run read by the local fallback is not comparable with one
        # read by a free OpenRouter model, so the row says which it was.
        "reader": str(data.get("page_reader") or "off").split(" (")[0],
        "decisions": int(decisions.get("decisions") or 0),
        "decisions_by_laya": int(decisions.get("by_laya") or 0),
        "decisions_by_rule": int(decisions.get("by_rule") or 0),
        "laya_differed": int(decisions.get("laya_disagreed_with_rule") or 0),
        "unresolved_questions": len(data.get("unresolved_questions") or []),
        "limitations": len(data.get("limitations") or []),
        "seconds": round(seconds, 1),
    }
    return Scorecard(row)


def record_run(data: dict[str, Any], seconds: float = 0.0, export_dir: str | Path = "exports") -> Path:
    """Append this run to exports/evals/runs.csv, and save it beside the run recording.

    The CSV is the history: one row per question asked, so a change can be judged by what it did
    to these numbers rather than by one report.
    """
    card = score_run(data, seconds)
    evals_dir = Path(export_dir) / "evals"
    evals_dir.mkdir(parents=True, exist_ok=True)
    csv_path = evals_dir / RUNS_CSV
    is_new = not csv_path.exists()
    with csv_path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(COLUMNS)
        writer.writerow(card.as_csv_row())
    if data.get("run_dir"):
        try:
            (Path(str(data["run_dir"])) / SCORECARD_FILE).write_text(
                json.dumps(card.row, indent=2), encoding="utf-8"
            )
        except OSError:
            pass
    return csv_path


def read_runs(export_dir: str | Path = "exports") -> list[dict[str, str]]:
    """Every run recorded so far, oldest first."""
    csv_path = Path(export_dir) / "evals" / RUNS_CSV
    if not csv_path.exists():
        return []
    with csv_path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# --- command line ------------------------------------------------------------------------------

# The columns worth seeing side by side; the CSV holds all of them.
_SUMMARY = ["asked_at", "commit", "answers", "answers_strong", "strong_share", "quote_share",
            "sources_per_answer", "claims_rejected", "pages_read", "seconds", "stop_reason"]


def _print_table(runs: list[dict[str, str]], columns: list[str]) -> None:
    if not runs:
        print("No runs recorded yet. Ask Heimdallr a question first (uv run osint-terminal).")
        return
    widths = {c: max(len(c), *(len(str(r.get(c, ""))) for r in runs)) for c in columns}
    print("  ".join(c.ljust(widths[c]) for c in columns))
    for r in runs:
        print("  ".join(str(r.get(c, "")).ljust(widths[c]) for c in columns))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", help="score a recorded run folder (exports/runs/<run>) instead of reading the history")
    parser.add_argument("--question", default="", help="only runs whose question contains this text")
    parser.add_argument("--compare", action="store_true", help="group the history by question, newest run last")
    parser.add_argument("--all-columns", action="store_true", help="print every column, not the summary ones")
    parser.add_argument("--export-dir", default=os.environ.get("HEIMDALLR_EXPORT_DIR", "exports"))
    args = parser.parse_args()

    if args.run:
        result = json.loads((Path(args.run) / "result.json").read_text(encoding="utf-8"))
        print("\n".join(score_run(result).table_lines()))
        return

    runs = [r for r in read_runs(args.export_dir) if args.question.lower() in (r.get("question") or "").lower()]
    columns = COLUMNS if args.all_columns else _SUMMARY
    if not args.compare:
        _print_table(runs, columns)
        return
    by_question: dict[str, list[dict[str, str]]] = {}
    for r in runs:
        by_question.setdefault(r.get("question") or "", []).append(r)
    for question, group in by_question.items():
        print(f"\n{question}  ({len(group)} run{'s' if len(group) != 1 else ''})")
        _print_table(group, columns)


if __name__ == "__main__":
    main()
