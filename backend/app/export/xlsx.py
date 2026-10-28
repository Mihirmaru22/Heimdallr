"""Excel workbook generation: Data, Sources, Evidence, Rejected, Run Summary, Diagnostics and Field Issues sheets.

Uses XlsxWriter in constant-memory mode so large exports stream row by row. Every untrusted
string goes through cell_safety and is written with write_string, never as a formula.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import xlsxwriter

from app.export.cell_safety import cell_value, safe_sheet_name, safe_text
from app.spec.models import ExtractionSpec, FieldType

MAX_ROWS = 1_048_575
MAX_URL_LEN = 2000
MAX_LINKS = 60_000


@dataclass
class ExportRecord:
    id: str
    data: dict[str, Any]
    status: str
    quality: float
    source_urls: list[str]
    field_values: list[dict[str, Any]]  # selected provenance rows


@dataclass
class ExportOptions:
    include_metadata: bool = True
    include_sources: bool = True
    include_issues: bool = True
    columns: list[str] | None = None  # field order; default spec order
    data_sheet_name: str = "Data"


# The proof behind a technology question: kept proof on "Evidence", everything turned down on "Rejected".
EVIDENCE_COLS = [("Company", "company", 30), ("Website", "website", 30), ("Product", "product", 18),
                 ("Verdict", "verdict", 11), ("Relationship", "relationship", 14), ("Quote", "quote", 90),
                 ("Source", "source_type", 22), ("Date", "evidence_date", 11), ("Link", "url", 60),
                 ("Judged by", "judged_by", 26), ("Strength", "strength", 9), ("Note", "reason", 50)]
# Every company the run came across and the one decision about it (app.services.companies): nothing it found is
# dropped without a reason.
COMPANY_COLS = [("Company", "name", 30), ("Website", "website", 30), ("Outcome", "status", 18),
                ("Proof", "proof_verdict", 11), ("Proof link", "proof_url", 60), ("Country", "country", 9),
                ("Country from", "country_by", 50), ("Why", "reasons", 100), ("Found by", "sources", 22)]
REJECTED_COLS = [("Company", "company", 30), ("Product", "product", 18), ("Why rejected", "reason", 60),
                 ("Relationship", "relationship", 14), ("Quote", "quote", 90), ("Source", "source_type", 22),
                 ("Date", "evidence_date", 11), ("Link", "url", 60), ("Judged by", "judged_by", 26)]


@dataclass
class ExportResult:
    path: Path
    rows: int
    bytes: int
    sha256: str


def _write(ws, row: int, col: int, value: Any, fmt=None, url_fmt=None, links: list[int] | None = None) -> None:
    v = cell_value(value)
    if v is None:
        ws.write_blank(row, col, None, fmt)
    elif isinstance(v, (int, float)) and not isinstance(v, bool):
        ws.write_number(row, col, v, fmt)
    elif (url_fmt is not None and links is not None and isinstance(v, str) and v.startswith(("http://", "https://"))
          and len(v) <= MAX_URL_LEN and links[0] < MAX_LINKS):
        links[0] += 1
        ws.write_url(row, col, v, url_fmt, string=v)
    else:
        ws.write_string(row, col, v, fmt)


def build_workbook(path: Path, spec: ExtractionSpec, records: Iterable[ExportRecord],
                   summary: dict[str, Any], options: ExportOptions | None = None,
                   evidence: list[dict[str, Any]] | None = None,
                   diagnostics: list[tuple[str, str, str]] | None = None,
                   companies: list[dict[str, Any]] | None = None) -> ExportResult:
    options = options or ExportOptions()
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = xlsxwriter.Workbook(str(path), {
        "constant_memory": True, "strings_to_formulas": False, "strings_to_urls": False,
        "strings_to_numbers": False, "default_date_format": "yyyy-mm-dd",
    })
    head = wb.add_format({"bold": True, "bg_color": "#E8EEF7", "border": 1, "text_wrap": True, "valign": "top"})
    wrap = wb.add_format({"text_wrap": False, "valign": "top"})
    link = wb.add_format({"font_color": "#1F4E9E", "underline": 1, "valign": "top"})
    used: set[str] = set()
    links = [0]

    fields = {f.name: f for f in spec.fields}
    order = [c for c in (options.columns or list(fields)) if c in fields]
    meta_cols = ["Record status", "Quality", "Source URLs"] if options.include_metadata else []
    headers = [fields[c].label for c in order] + meta_cols

    data_ws = wb.add_worksheet(safe_sheet_name(options.data_sheet_name, used))
    for i, name in enumerate(order):
        width = 48 if fields[name].type in (FieldType.text, FieldType.list, FieldType.url) else 24
        data_ws.set_column(i, i, width)
    if meta_cols:
        data_ws.set_column(len(order), len(order) + 1, 14)
        data_ws.set_column(len(order) + 2, len(order) + 2, 60)
    for c, h in enumerate(headers):
        data_ws.write_string(0, c, safe_text(h), head)
    data_ws.freeze_panes(1, 0)

    sources_rows: list[list[Any]] = []
    issue_rows: list[list[Any]] = []
    row = 0
    for rec in records:
        if row >= MAX_ROWS - 1:
            break
        row += 1
        for c, name in enumerate(order):
            _write(data_ws, row, c, rec.data.get(name), wrap, link if fields[name].type == FieldType.url else None,
                   links)
        if meta_cols:
            base = len(order)
            _write(data_ws, row, base, rec.status, wrap)
            _write(data_ws, row, base + 1, round(rec.quality, 3), wrap)
            _write(data_ws, row, base + 2, "\n".join(rec.source_urls[:10]), wrap)
        for fv in rec.field_values:
            if fv["value_status"] == "found":
                sources_rows.append([row, fv["field_name"], fv["value"], fv["method"], fv.get("source_url"),
                                     fv.get("evidence"), fv.get("confidence")])
            else:
                issue_rows.append([row, fv["field_name"], fv["value_status"], fv.get("error")])
    data_ws.autofilter(0, 0, max(row, 1), max(len(headers) - 1, 0))

    if options.include_sources:
        ws = wb.add_worksheet(safe_sheet_name("Sources", used))
        cols = ["Data row", "Field", "Value", "Method", "Source URL", "Evidence", "Confidence"]
        for c, w in enumerate([10, 22, 40, 14, 60, 80, 12]):
            ws.set_column(c, c, w)
        for c, h in enumerate(cols):
            ws.write_string(0, c, h, head)
        ws.freeze_panes(1, 0)
        for r, values in enumerate(sources_rows[: MAX_ROWS - 1], start=1):
            for c, v in enumerate(values):
                _write(ws, r, c, v, wrap, link if c == 4 else None, links)
        ws.autofilter(0, 0, max(len(sources_rows), 1), len(cols) - 1)

    if companies:
        ws = wb.add_worksheet(safe_sheet_name("Companies", used))
        for c, (h, _key, w) in enumerate(COMPANY_COLS):
            ws.set_column(c, c, w)
            ws.write_string(0, c, h, head)
        ws.freeze_panes(1, 0)
        for r, co in enumerate(companies[: MAX_ROWS - 1], start=1):
            for c, (_h, key, _w) in enumerate(COMPANY_COLS):
                value = co.get(key)
                if isinstance(value, list):
                    value = "; ".join(map(str, value))
                _write(ws, r, c, value, wrap, link if key in ("proof_url", "website") else None, links)
        ws.autofilter(0, 0, max(len(companies), 1), len(COMPANY_COLS) - 1)

    if evidence:
        for title, cols, rows in (("Evidence", EVIDENCE_COLS, [e for e in evidence if e.get("kept")]),
                                  ("Rejected", REJECTED_COLS, [e for e in evidence if not e.get("kept")])):
            ws = wb.add_worksheet(safe_sheet_name(title, used))
            for c, (h, _key, w) in enumerate(cols):
                ws.set_column(c, c, w)
                ws.write_string(0, c, h, head)
            ws.freeze_panes(1, 0)
            for r, e in enumerate(rows[: MAX_ROWS - 1], start=1):
                for c, (_h, key, _w) in enumerate(cols):
                    value = e.get(key)
                    if key == "relationship" and isinstance(value, str):
                        value = value.replace("_", " ")
                    _write(ws, r, c, value, wrap, link if key in ("url", "website") else None, links)
            ws.autofilter(0, 0, max(len(rows), 1), len(cols) - 1)

    ws = wb.add_worksheet(safe_sheet_name("Run Summary", used))
    ws.set_column(0, 0, 32)
    ws.set_column(1, 1, 80)
    ws.write_string(0, 0, "Item", head)
    ws.write_string(0, 1, "Value", head)
    for r, (k, v) in enumerate(summary.items(), start=1):
        ws.write_string(r, 0, safe_text(str(k)))
        if isinstance(v, datetime):
            v = v.isoformat(timespec="seconds")
        _write(ws, r, 1, v)

    if diagnostics:
        # What the run planned and what each source and page really did, so a run can be measured afterwards.
        ws = wb.add_worksheet(safe_sheet_name("Diagnostics", used))
        for c, (h, w) in enumerate([("Section", 22), ("Item", 40), ("Value", 110)]):
            ws.set_column(c, c, w)
            ws.write_string(0, c, h, head)
        ws.freeze_panes(1, 0)
        for r, values in enumerate(diagnostics[: MAX_ROWS - 1], start=1):
            for c, v in enumerate(values):
                _write(ws, r, c, v, wrap)
        ws.autofilter(0, 0, max(len(diagnostics), 1), 2)

    if options.include_issues and issue_rows:
        ws = wb.add_worksheet(safe_sheet_name("Field Issues", used))
        cols = ["Data row", "Field", "Status", "Reason"]
        for c, w in enumerate([10, 22, 16, 90]):
            ws.set_column(c, c, w)
        for c, h in enumerate(cols):
            ws.write_string(0, c, h, head)
        ws.freeze_panes(1, 0)
        for r, values in enumerate(issue_rows[: MAX_ROWS - 1], start=1):
            for c, v in enumerate(values):
                _write(ws, r, c, v, wrap)
        ws.autofilter(0, 0, max(len(issue_rows), 1), len(cols) - 1)

    wb.close()
    blob = path.read_bytes()
    return ExportResult(path, row, len(blob), hashlib.sha256(blob).hexdigest())
