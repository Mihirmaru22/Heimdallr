"""Load the UK Companies House free company snapshot into kb.uk_company.

The snapshot (download.companieshouse.gov.uk/en_output.html) is a monthly CSV of every company on
the register: name, number, registered office address, category, status, incorporation and
dissolution dates, up to four SIC codes and previous names. It is free to use: Companies House
puts no rules on re-use of register data.

The header spelling varies a little between releases (dots, spaces), so columns are found by a
normalised name. After the load, a report compares the register with PDL's UK companies by
normalised name and town: a first count of how many register companies PDL lacks. That count is
an estimate (two companies can share a name; one company can trade under another), not a merge.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from app.kb.pdl import MIN_SHARE_OF_PREVIOUS, SCHEMA_SQL, file_sha256, kb_dsn, read_rows

TABLE = "uk_company"
COLUMNS = (
    "company_number", "name", "name_key", "status", "category", "incorporated", "dissolved",
    "address_line1", "address_line2", "post_town", "county", "country", "postcode",
    "sic_codes", "sic_text", "previous_names", "uri",
)
LEGAL_SUFFIX_RE = re.compile(
    r"\b(limited|ltd|plc|llp|lp|public limited company|limited liability partnership|cic|c\.i\.c|"
    r"company|co|uk|the|and|&)\b")


def name_key(name: str) -> str:
    """'ACME (UK) LIMITED' and 'acme uk ltd' both become 'acme': for comparing names, not storing."""
    text = re.sub(r"[^\w ]+", " ", name.lower().replace("&", " and "))
    text = LEGAL_SUFFIX_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _norm(header: str) -> str:
    return re.sub(r"[^a-z0-9_]", "", header.lower())


def _pick(row: dict[str, str], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value:
            return value.strip()
    return ""


def _date(value: str) -> date | None:
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", value.strip())
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def normalise(raw: dict[str, str]) -> tuple:
    row = {_norm(k): v for k, v in raw.items()}
    sic_text = [s for s in (_pick(row, f"siccodesictext_{i}", f"siccode{i}") for i in range(1, 5))
                if s and s.lower() != "none supplied"]
    sic_codes = [m.group(1) for s in sic_text if (m := re.match(r"(\d{4,5})\b", s))]
    previous = [p for p in (_pick(row, f"previousname_{i}companyname") for i in range(1, 11)) if p]
    name = _pick(row, "companyname")
    values = {
        "company_number": _pick(row, "companynumber"),
        "name": name,
        "name_key": name_key(name),
        "status": _pick(row, "companystatus"),
        "category": _pick(row, "companycategory"),
        "incorporated": _date(_pick(row, "incorporationdate")),
        "dissolved": _date(_pick(row, "dissolutiondate")),
        "address_line1": _pick(row, "regaddressaddressline1", "addressline1"),
        "address_line2": _pick(row, "regaddressaddressline2", "addressline2"),
        "post_town": _pick(row, "regaddressposttown", "posttown").lower(),
        "county": _pick(row, "regaddresscounty", "county"),
        "country": _pick(row, "regaddresscountry", "country"),
        "postcode": _pick(row, "regaddresspostcode", "postcode").upper(),
        "sic_codes": sic_codes,
        "sic_text": sic_text,
        "previous_names": previous,
        "uri": _pick(row, "uri"),
    }
    return tuple(values[c] if values[c] not in ("", []) else None for c in COLUMNS)


@dataclass
class Coverage:
    rows: int = 0
    filled: Counter = field(default_factory=Counter)
    by_status: Counter = field(default_factory=Counter)
    by_category: Counter = field(default_factory=Counter)
    headers: list[str] = field(default_factory=list)
    overlap: dict = field(default_factory=dict)

    def add(self, raw: dict[str, str], row: tuple) -> None:
        if not self.headers:
            self.headers = list(raw)
        self.rows += 1
        values = dict(zip(COLUMNS, row, strict=True))
        for column, value in values.items():
            if value is not None:
                self.filled[column] += 1
        self.by_status[values["status"] or "(none)"] += 1
        self.by_category[values["category"] or "(none)"] += 1

    def report(self, top: int = 15) -> str:
        def pct(n: int, of: int | None = None) -> str:
            of = self.rows if of is None else of
            return f"{n:>12,}  {100 * n / of:5.1f}%" if of else f"{n:>12,}"

        lines = [f"Rows: {self.rows:,}", "", "Field coverage:"]
        lines += [f"  {c:<15} {pct(self.filled[c])}" for c in COLUMNS]
        lines += ["", "By status:"] + [f"  {s:<40} {pct(n)}" for s, n in self.by_status.most_common(top)]
        lines += ["", "By category:"] + [f"  {s:<40} {pct(n)}" for s, n in self.by_category.most_common(top)]
        if self.filled["company_number"] < self.rows:
            lines += ["", f"Header as read (check the column names): {self.headers}"]
        if self.overlap:
            o = self.overlap
            lines += [
                "", "Compared with PDL's UK companies (normalised name; estimate, not a merge):",
                f"  Active register companies:             {o['active']:>12,}",
                f"  ... same name as a PDL UK company:     {pct(o['name_match'], o['active'])}",
                f"  ... same name and same town:           {pct(o['name_town_match'], o['active'])}",
                f"  ... no PDL company with that name:     {pct(o['active'] - o['name_match'], o['active'])}",
                f"  PDL UK companies:                      {o['pdl_uk']:>12,}",
            ]
        return "\n".join(lines)


def scan(rows: Iterable[dict[str, str]], sink: Callable[[tuple], None] | None = None,
         progress: Callable[[int], None] | None = None) -> Coverage:
    coverage = Coverage()
    for raw in rows:
        row = normalise(raw)
        if row[0] is None:  # no company number: a broken line
            continue
        coverage.add(raw, row)
        if sink is not None:
            sink(row)
        if progress is not None and coverage.rows % 1_000_000 == 0:
            progress(coverage.rows)
    return coverage


def _create(cur, name: str) -> None:
    cur.execute(f"""
        CREATE TABLE kb.{name} (
            company_number text, name text, name_key text, status text, category text,
            incorporated date, dissolved date, address_line1 text, address_line2 text, post_town text,
            county text, country text, postcode text, sic_codes text[], sic_text text[],
            previous_names text[], uri text
        )""")


OVERLAP_SQL = """
WITH pdl AS (SELECT DISTINCT name_key, city FROM kb.pdl_uk_keys),
     reg AS (SELECT name_key, post_town FROM kb.uk_company WHERE status = 'Active' AND name_key <> '')
SELECT (SELECT count(*) FROM reg),
       (SELECT count(*) FROM reg WHERE name_key IN (SELECT name_key FROM pdl)),
       (SELECT count(*) FROM reg r WHERE EXISTS (SELECT 1 FROM pdl p WHERE p.name_key = r.name_key
                                                 AND p.city = r.post_town)),
       (SELECT count(*) FROM kb.pdl_uk_keys)
"""


def overlap_with_pdl(cur) -> dict:
    """A first estimate of how many active register companies PDL already has, by name (and town)."""
    cur.execute("SELECT to_regclass('kb.pdl_company')")
    if not cur.fetchone()[0]:
        return {}
    cur.execute("DROP TABLE IF EXISTS kb.pdl_uk_keys")
    cur.execute("CREATE UNLOGGED TABLE kb.pdl_uk_keys (name_key text, city text)")
    cur.execute("SELECT name, city FROM kb.pdl_company WHERE iso2 = 'GB' AND name IS NOT NULL")
    rows = [(name_key(n), c) for n, c in cur.fetchall()]
    with cur.copy("COPY kb.pdl_uk_keys (name_key, city) FROM STDIN") as copy:
        for r in rows:
            copy.write_row(r)
    cur.execute("CREATE INDEX ON kb.pdl_uk_keys (name_key, city)")
    cur.execute(OVERLAP_SQL)
    active, name_match, name_town, pdl_uk = cur.fetchone()
    cur.execute("DROP TABLE kb.pdl_uk_keys")
    return {"active": active, "name_match": name_match, "name_town_match": name_town, "pdl_uk": pdl_uk}


def load(path: Path, dsn: str | None = None, force: bool = False,
         progress: Callable[[int], None] | None = None) -> Coverage:
    """Copy into kb.uk_company_load, check, swap in as kb.uk_company, then compare with PDL."""
    import psycopg

    sha = file_sha256(path)
    with psycopg.connect(dsn or kb_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
            cur.execute(f"DROP TABLE IF EXISTS kb.{TABLE}_load")
            _create(cur, f"{TABLE}_load")
            with cur.copy(f"COPY kb.{TABLE}_load ({', '.join(COLUMNS)}) FROM STDIN") as copy:
                coverage = scan(read_rows(path), copy.write_row, progress)
            cur.execute("SELECT to_regclass(%s)", (f"kb.{TABLE}",))
            previous = 0
            if cur.fetchone()[0]:
                cur.execute(f"SELECT count(*) FROM kb.{TABLE}")  # noqa: S608 - TABLE is a constant
                previous = cur.fetchone()[0]
            if coverage.rows == 0 or (previous and coverage.rows < MIN_SHARE_OF_PREVIOUS * previous
                                      and not force):
                conn.rollback()
                raise ValueError(f"refused: the file has {coverage.rows:,} rows, the current table "
                                 f"{previous:,}; pass force to load it anyway")
            cur.execute(f"CREATE INDEX ON kb.{TABLE}_load (company_number)")
            cur.execute(f"CREATE INDEX ON kb.{TABLE}_load (name_key)")
            cur.execute(f"CREATE INDEX ON kb.{TABLE}_load (postcode)")
            cur.execute(f"DROP TABLE IF EXISTS kb.{TABLE}")
            cur.execute(f"ALTER TABLE kb.{TABLE}_load RENAME TO {TABLE}")
            coverage.overlap = overlap_with_pdl(cur)
            cur.execute(
                "INSERT INTO kb.load_log (source, file_name, file_sha256, rows, coverage) "
                "VALUES ('companies_house_basic', %s, %s, %s, %s)",
                (path.name, sha, coverage.rows, json.dumps({
                    "rows": coverage.rows, "filled": dict(coverage.filled),
                    "by_status": dict(coverage.by_status), "overlap": coverage.overlap})),
            )
        conn.commit()
    return coverage
