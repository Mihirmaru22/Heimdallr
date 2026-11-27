"""Load India MCA / RoC Company Master Data CSV or ZIP into kb.in_company."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from app.kb.companies_house import name_key
from app.kb.pdl import MIN_SHARE_OF_PREVIOUS, SCHEMA_SQL, file_sha256, kb_dsn, read_rows

TABLE = "in_company"
COLUMNS = (
    "cin", "name", "name_key", "status", "company_class", "category", "sub_category",
    "roc", "registered_at", "authorized_capital", "paidup_capital",
    "nic_code", "activity", "state", "address", "email_domain",
)


def _norm_key(k: str) -> str:
    return re.sub(r"[^a-z0-9_]", "", k.lower())


def _pick(row: dict[str, str], *keys: str) -> str:
    for k in keys:
        if val := row.get(k):
            return val.strip()
    return ""


def _parse_date(raw: str) -> date | None:
    s = raw.strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(s[:11], fmt).date()
        except ValueError:
            continue
    return None


def _parse_float(raw: str) -> float | None:
    s = re.sub(r"[^0-9.-]", "", raw or "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def normalise(raw: dict[str, str]) -> tuple | None:
    """Normalize one India MCA RoC row into kb.in_company column order."""
    row = {_norm_key(k): v for k, v in raw.items()}
    cin = _pick(row, "cin", "corporate_identification_number", "llpin").upper()[:25]
    name = _pick(row, "company_name", "companyname", "entity_name")[:300]
    if not cin or not name:
        return None
    email = _pick(row, "email_addr", "email", "email_id").lower()
    email_dom = email.split("@", 1)[1].strip() if "@" in email else ""
    nic = _pick(row, "nic_code", "principal_business_activity_as_per_cin")[:40]
    activity = _pick(row, "principal_business_activity", "principal_business_activity_as_per_cin", "activity")[:240]
    vals = {
        "cin": cin,
        "name": name,
        "name_key": name_key(name),
        "status": _pick(row, "company_status", "status")[:60] or None,
        "company_class": _pick(row, "company_class", "class")[:60] or None,
        "category": _pick(row, "company_category", "category")[:80] or None,
        "sub_category": _pick(row, "company_sub_category", "sub_category")[:80] or None,
        "roc": _pick(row, "registrar_of_companies", "roc_code", "roc")[:80] or None,
        "registered_at": _parse_date(_pick(row, "date_of_registration", "incorporation_date", "date_of_incorporation")),
        "authorized_capital": _parse_float(_pick(row, "authorized_cap", "authorised_capital")),
        "paidup_capital": _parse_float(_pick(row, "paidup_cap", "paid_up_capital")),
        "nic_code": nic or None,
        "activity": activity or None,
        "state": _pick(row, "registered_state", "state", "state_code")[:80] or None,
        "address": _pick(row, "registered_office_address", "address")[:400] or None,
        "email_domain": email_dom[:120] or None,
    }
    return tuple(vals[c] for c in COLUMNS)


def iter_rows(path: Path) -> Iterator[tuple]:
    for raw in read_rows(path):
        row = normalise(raw)
        if row is not None:
            yield row


@dataclass
class Coverage:
    rows: int = 0
    active: int = 0
    with_paidup: int = 0
    latest_registered: date | None = None

    def add(self, row: tuple) -> None:
        self.rows += 1
        if (row[3] or "").lower() == "active":
            self.active += 1
        if row[10] is not None:
            self.with_paidup += 1
        if row[8] is not None and (self.latest_registered is None or row[8] > self.latest_registered):
            self.latest_registered = row[8]

    def report(self) -> str:
        return (
            f"India MCA: rows={self.rows:,}, active={self.active:,}, "
            f"paidup_capital={self.with_paidup:,}, latest_registered={self.latest_registered}"
        )


def load(path: Path, dsn: str | None = None, force: bool = False,
         progress: Callable[[int], None] | None = None) -> Coverage:
    """Atomically load an India MCA CSV or ZIP snapshot into kb.in_company."""
    import psycopg

    sha = file_sha256(path)
    cov = Coverage()
    with psycopg.connect(dsn or kb_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
            cur.execute(f"DROP TABLE IF EXISTS kb.{TABLE}_load")
            cur.execute(f"""
                CREATE TABLE kb.{TABLE}_load (
                    cin text PRIMARY KEY, name text NOT NULL, name_key text,
                    status text, company_class text, category text, sub_category text,
                    roc text, registered_at date, authorized_capital double precision,
                    paidup_capital double precision, nic_code text, activity text,
                    state text, address text, email_domain text
                )""")
            seen: set[str] = set()
            with cur.copy(f"COPY kb.{TABLE}_load ({', '.join(COLUMNS)}) FROM STDIN") as copy:
                for row in iter_rows(path):
                    if row[0] in seen:
                        continue
                    seen.add(row[0])
                    cov.add(row)
                    copy.write_row(row)
                    if progress and cov.rows % 100_000 == 0:
                        progress(cov.rows)
            cur.execute("SELECT to_regclass(%s)", (f"kb.{TABLE}",))
            prev = 0
            if cur.fetchone()[0]:
                cur.execute(f"SELECT count(*) FROM kb.{TABLE}")  # noqa: S608
                prev = cur.fetchone()[0]
            if cov.rows == 0 or (prev and cov.rows < MIN_SHARE_OF_PREVIOUS * prev and not force):
                conn.rollback()
                raise ValueError(f"refused: {cov.rows:,} rows vs current {prev:,}; pass --force")
            cur.execute(f"CREATE INDEX ON kb.{TABLE}_load (name_key)")
            cur.execute(f"CREATE INDEX ON kb.{TABLE}_load (state)")
            cur.execute(f"CREATE INDEX ON kb.{TABLE}_load (email_domain)")
            cur.execute(f"DROP TABLE IF EXISTS kb.{TABLE}")
            cur.execute(f"ALTER TABLE kb.{TABLE}_load RENAME TO {TABLE}")
            cur.execute(
                "INSERT INTO kb.load_log (source, file_name, file_sha256, rows, coverage) "
                "VALUES ('india_mca', %s, %s, %s, %s)",
                (path.name, sha, cov.rows, json.dumps({
                    "rows": cov.rows, "active": cov.active,
                    "paidup_capital": cov.with_paidup,
                    "latest_registered": str(cov.latest_registered) if cov.latest_registered else None,
                })),
            )
        conn.commit()
    return cov
