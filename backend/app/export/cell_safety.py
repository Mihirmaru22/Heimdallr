"""Neutralize spreadsheet formula injection in untrusted cell values.

A cell whose text starts with = + - @ (or tab / carriage return, or their full-width forms) can
be evaluated as a formula by Excel, LibreOffice or Google Sheets. Such values are prefixed with
an apostrophe and always written as strings, never as formulas. The original value stays in
the database.
"""

from __future__ import annotations

import math
import re
from typing import Any

DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n", "＝", "＋", "－", "＠")
EXCEL_MAX_CELL = 32_767
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
# Numbers and phone numbers ("+1 866 300 1261") hold only digits and arithmetic, so even evaluated they
# cannot call a function or reach another cell; an apostrophe would only corrupt them.
NUMERIC_RE = re.compile(r"^[+-]?\d[\d ().-]*$")


def safe_text(value: str) -> str:
    text = CONTROL_RE.sub("", value)
    stripped = text.lstrip(" ")
    if stripped.startswith(DANGEROUS_PREFIXES) and not NUMERIC_RE.match(stripped):
        text = "'" + text
    if len(text) > EXCEL_MAX_CELL:
        text = text[: EXCEL_MAX_CELL - 15] + "…[truncated]"
    return text


def cell_value(value: Any) -> Any:
    """Convert a stored value to something safe to write into a cell."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return value if not (isinstance(value, float) and (math.isnan(value) or math.isinf(value))) else None
    if isinstance(value, list):
        return safe_text("; ".join(str(v) for v in value))
    if isinstance(value, dict):
        return safe_text(", ".join(f"{k}: {v}" for k, v in value.items()))
    return safe_text(str(value))


def safe_sheet_name(name: str, used: set[str]) -> str:
    cleaned = re.sub(r"[\[\]:*?/\\']", " ", name).strip()[:31] or "Sheet"
    candidate, n = cleaned, 2
    while candidate.lower() in used:
        suffix = f" ({n})"
        candidate = cleaned[: 31 - len(suffix)] + suffix
        n += 1
    used.add(candidate.lower())
    return candidate
