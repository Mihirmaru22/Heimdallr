"""Load USAspending Prime Contracts bulk archives into kb.usaspending_recipient."""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from app.kb.companies_house import name_key
from app.kb.pdl import SCHEMA_SQL, file_sha256, kb_dsn

LIST_MONTHLY_URL = "https://api.usaspending.gov/api/v2/bulk_download/list_monthly_files/"

COLUMNS = (
    "recipient_uei", "recipient_name", "name_key", "parent_uei", "parent_name",
    "country", "state", "city", "postal_code", "phone",
    "total_obligated", "award_count", "latest_action_date",
    "agencies", "naics_codes", "domain", "link_method", "candidate_domain", "candidate_method",
)

NEEDED_COLS = (
    "recipient_uei", "recipient_name", "recipient_parent_uei", "recipient_parent_name",
    "recipient_country_code", "recipient_state_code", "recipient_city_name",
    "recipient_zip_4_code", "recipient_phone_number",
    "federal_action_obligation", "action_date", "awarding_agency_name", "naics_code",
)


def _norm_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    return digits[-10:] if len(digits) >= 10 else ""


def _parse_date(raw: str) -> date | None:
    s = (raw or "").strip()[:10]
    if len(s) != 10:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _cell(row: list[str], idx: int | None) -> str:
    return row[idx].strip() if idx is not None and idx < len(row) else ""


def _parse_float(raw: str) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


@dataclass
class Coverage:
    transactions: int = 0
    recipients: int = 0
    total_obligated: float = 0.0
    linked_domains: int = 0
    _agencies: set[str] = field(default_factory=set)

    def report(self) -> str:
        return (
            f"USAspending: transactions={self.transactions:,}, recipients={self.recipients:,}, "
            f"obligated=${self.total_obligated:,.0f}, linked_domains={self.linked_domains:,}"
        )


def scan_zip(zip_path: Path, progress: Callable[[int], None] | None = None) -> tuple[dict[str, dict], Coverage]:
    """Stream all CSV entries inside a USAspending contracts archive and aggregate per recipient_uei."""
    agg: dict[str, dict] = {}
    cov = Coverage()
    with zipfile.ZipFile(zip_path) as z:
        for member in sorted(z.infolist(), key=lambda m: m.filename):
            if member.is_dir() or not member.filename.lower().endswith(".csv"):
                continue
            with z.open(member) as raw_f:
                reader = csv.reader(io.TextIOWrapper(raw_f, encoding="utf-8", errors="replace"))
                header = next(reader, None)
                if not header:
                    continue
                idx = {col.strip(): i for i, col in enumerate(header)}
                pos = {col: idx[col] for col in NEEDED_COLS if col in idx}
                if "recipient_uei" not in pos or "recipient_name" not in pos:
                    continue
                i_uei = pos["recipient_uei"]
                i_name = pos["recipient_name"]
                i_puei = pos.get("recipient_parent_uei")
                i_pname = pos.get("recipient_parent_name")
                i_ctry = pos.get("recipient_country_code")
                i_st = pos.get("recipient_state_code")
                i_city = pos.get("recipient_city_name")
                i_zip = pos.get("recipient_zip_4_code")
                i_ph = pos.get("recipient_phone_number")
                i_amt = pos.get("federal_action_obligation")
                i_dt = pos.get("action_date")
                i_ag = pos.get("awarding_agency_name")
                i_naics = pos.get("naics_code")

                for row in reader:
                    cov.transactions += 1
                    if progress and cov.transactions % 250_000 == 0:
                        progress(cov.transactions)
                    if len(row) <= i_uei:
                        continue
                    uei = row[i_uei].strip().upper()
                    if not uei:
                        continue
                    amt = _parse_float(row[i_amt]) if i_amt is not None and i_amt < len(row) else 0.0
                    cov.total_obligated += amt
                    rec = agg.get(uei)
                    if rec is None:
                        nm = row[i_name].strip()[:300]
                        if not nm:
                            continue
                        rec = {
                            "recipient_uei": uei[:20],
                            "recipient_name": nm,
                            "name_key": name_key(nm),
                            "parent_uei": _cell(row, i_puei).upper()[:20] or None,
                            "parent_name": _cell(row, i_pname)[:300] or None,
                            "country": _cell(row, i_ctry).upper()[:10] or None,
                            "state": _cell(row, i_st).upper()[:10] or None,
                            "city": _cell(row, i_city).lower()[:120] or None,
                            "postal_code": _cell(row, i_zip)[:15] or None,
                            "phone": _norm_phone(_cell(row, i_ph)) or None,
                            "total_obligated": amt,
                            "award_count": 1,
                            "latest_action_date": _parse_date(_cell(row, i_dt)),
                            "agencies": set(),
                            "naics_codes": set(),
                        }
                        agg[uei] = rec
                    else:
                        rec["total_obligated"] += amt
                        rec["award_count"] += 1
                        if not rec["phone"] and i_ph is not None and i_ph < len(row):
                            rec["phone"] = _norm_phone(row[i_ph]) or None
                        if i_dt is not None and i_dt < len(row):
                            dt = _parse_date(row[i_dt])
                            if dt and (rec["latest_action_date"] is None or dt > rec["latest_action_date"]):
                                rec["latest_action_date"] = dt
                    if i_ag is not None and i_ag < len(row):
                        ag = row[i_ag].strip()[:120]
                        if ag and len(rec["agencies"]) < 15:
                            rec["agencies"].add(ag)
                    if i_naics is not None and i_naics < len(row):
                        nc = row[i_naics].strip()[:12]
                        if nc and len(rec["naics_codes"]) < 15:
                            rec["naics_codes"].add(nc)
    cov.recipients = len(agg)
    return agg, cov


def _iter_tuples(agg: dict[str, dict]) -> Iterator[tuple]:
    for r in agg.values():
        yield (
            r["recipient_uei"], r["recipient_name"], r["name_key"], r["parent_uei"], r["parent_name"],
            r["country"], r["state"], r["city"], r["postal_code"], r["phone"],
            round(r["total_obligated"], 2), r["award_count"], r["latest_action_date"],
            sorted(r["agencies"])[:10], sorted(r["naics_codes"])[:10], None, None, None, None,
        )


def link_domains(conn) -> int:
    """Two-signal domain linking: phone agreement promotes `domain`; name+state is kept as candidate only."""
    # Candidate only (never promoted to `domain` on name+state without phone confirmation):
    conn.execute("""
        WITH m AS (
            SELECT DISTINCT ON (u.recipient_uei) u.recipient_uei, s.domain
            FROM kb.usaspending_recipient u
            JOIN kb.sec_company s ON s.name_key = u.name_key AND s.state = u.state
            WHERE u.candidate_domain IS NULL AND s.domain IS NOT NULL
              AND u.name_key <> '' AND u.state IS NOT NULL
        )
        UPDATE kb.usaspending_recipient r
        SET candidate_domain = m.domain, candidate_method = 'sec_name_state'
        FROM m WHERE r.recipient_uei = m.recipient_uei
    """)
    # Verified link: exact last-10-digit phone agreement against unique domain in kb.company_branch.
    if conn.execute("SELECT to_regclass('kb.company_branch')").fetchone()[0]:
        conn.execute("""
            WITH b AS (
                SELECT regexp_replace(phone, '[^0-9]', '', 'g') AS digits, min(domain) AS dom
                FROM kb.company_branch
                WHERE phone IS NOT NULL AND length(regexp_replace(phone, '[^0-9]', '', 'g')) >= 10
                GROUP BY 1
                HAVING count(DISTINCT domain) = 1
            )
            UPDATE kb.usaspending_recipient r
            SET domain = b.dom,
                link_method = CASE WHEN r.candidate_domain = b.dom THEN 'sec_name_state+phone'
                                   ELSE 'branch_phone' END
            FROM b
            WHERE r.domain IS NULL AND r.phone IS NOT NULL AND right(b.digits, 10) = r.phone
        """)
    return conn.execute("SELECT count(*) FROM kb.usaspending_recipient WHERE domain IS NOT NULL").fetchone()[0]


def latest_full_contracts_url(fiscal_year: int = 2026) -> tuple[str, str]:
    """Query USAspending bulk_download API for the latest full Prime Contracts ZIP URL."""
    import httpx

    with httpx.Client(timeout=30) as c:
        resp = c.post(LIST_MONTHLY_URL, json={"agency": "all", "fiscal_year": fiscal_year, "type": "contracts"})
        resp.raise_for_status()
        for entry in resp.json().get("monthly_files") or []:
            if "Full_" in (entry.get("file_name") or ""):
                return entry["file_name"], entry["url"]
    raise ValueError(f"No Full contracts archive found for FY{fiscal_year}")


def load(zip_path: Path, dsn: str | None = None,
         progress: Callable[[int], None] | None = None) -> Coverage:
    """Atomically aggregate USAspending contracts archive into kb.usaspending_recipient."""
    import psycopg

    sha = file_sha256(zip_path)
    agg, cov = scan_zip(zip_path, progress=progress)
    with psycopg.connect(dsn or kb_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
            cur.execute("DROP TABLE IF EXISTS kb.usaspending_recipient_load")
            cur.execute("""
                CREATE TABLE kb.usaspending_recipient_load (
                    recipient_uei text PRIMARY KEY, recipient_name text NOT NULL, name_key text,
                    parent_uei text, parent_name text, country text, state text, city text,
                    postal_code text, phone text, total_obligated double precision NOT NULL,
                    award_count integer NOT NULL, latest_action_date date,
                    agencies text[], naics_codes text[], domain text, link_method text,
                    candidate_domain text, candidate_method text
                )""")
            with cur.copy(
                f"COPY kb.usaspending_recipient_load ({', '.join(COLUMNS)}) FROM STDIN"
            ) as copy:
                for row in _iter_tuples(agg):
                    copy.write_row(row)
            cur.execute("CREATE INDEX ON kb.usaspending_recipient_load (name_key, state)")
            cur.execute("CREATE INDEX ON kb.usaspending_recipient_load (domain)")
            cur.execute("CREATE INDEX ON kb.usaspending_recipient_load (total_obligated DESC)")
            cur.execute("DROP TABLE IF EXISTS kb.usaspending_recipient")
            cur.execute("ALTER TABLE kb.usaspending_recipient_load RENAME TO usaspending_recipient")
            cov.linked_domains = link_domains(conn)
            cur.execute(
                "INSERT INTO kb.load_log (source, file_name, file_sha256, rows, coverage) "
                "VALUES ('usaspending_contracts', %s, %s, %s, %s)",
                (zip_path.name, sha, cov.recipients, json.dumps({
                    "transactions": cov.transactions, "recipients": cov.recipients,
                    "total_obligated": cov.total_obligated, "linked_domains": cov.linked_domains,
                })),
            )
        conn.commit()
    return cov
