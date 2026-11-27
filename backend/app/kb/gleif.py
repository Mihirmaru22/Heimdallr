"""Load the GLEIF Golden Copy LEI2 snapshot into kb.gleif_company."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from app.kb.companies_house import name_key
from app.kb.pdl import MIN_SHARE_OF_PREVIOUS, SCHEMA_SQL, file_sha256, kb_dsn

TABLE = "gleif_company"
COLUMNS = (
    "lei", "legal_name", "name_key", "entity_status", "registration_status",
    "entity_category", "legal_form_code", "legal_form", "jurisdiction",
    "iso2", "region", "city", "postcode", "address_line1",
    "hq_iso2", "hq_city", "hq_postcode", "hq_address_line1",
    "registered_at", "next_renewal",
)

SOURCE_HEADERS = (
    ("lei", "LEI"),
    ("legal_name", "Entity.LegalName"),
    ("entity_status", "Entity.EntityStatus"),
    ("registration_status", "Registration.RegistrationStatus"),
    ("entity_category", "Entity.EntityCategory"),
    ("legal_form_code", "Entity.LegalForm.EntityLegalFormCode"),
    ("legal_form", "Entity.LegalForm.OtherLegalForm"),
    ("jurisdiction", "Entity.LegalJurisdiction"),
    ("iso2", "Entity.LegalAddress.Country"),
    ("region", "Entity.LegalAddress.Region"),
    ("city", "Entity.LegalAddress.City"),
    ("postcode", "Entity.LegalAddress.PostalCode"),
    ("address_line1", "Entity.LegalAddress.FirstAddressLine"),
    ("hq_iso2", "Entity.HeadquartersAddress.Country"),
    ("hq_city", "Entity.HeadquartersAddress.City"),
    ("hq_postcode", "Entity.HeadquartersAddress.PostalCode"),
    ("hq_address_line1", "Entity.HeadquartersAddress.FirstAddressLine"),
    ("registered_at", "Registration.InitialRegistrationDate"),
    ("next_renewal", "Registration.NextRenewalDate"),
)


def _iso_date(value: str) -> date | None:
    s = (value or "").strip()[:10]
    if len(s) != 10:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _clean(value: str, limit: int = 300) -> str | None:
    s = " ".join((value or "").replace("\x00", "").split()).strip()
    return s[:limit] if s else None


def iter_rows(path: Path) -> Iterator[tuple]:
    """Stream normalised tuples directly from a GLEIF .zip or .csv without materialising wide dicts."""
    want_names = [src for _, src in SOURCE_HEADERS]

    def stream_file(text_stream: io.TextIOBase) -> Iterator[tuple]:
        reader = csv.reader(text_stream)
        header = next(reader, None)
        if not header:
            return
        idx = {h.strip(): i for i, h in enumerate(header)}
        col_pos = [idx.get(name, -1) for name in want_names]
        p_lei, p_name, p_es, p_rs, p_ec, p_lfc, p_lf, p_jur, p_c, p_r, p_city, p_pc, p_a1, \
            p_hc, p_hcity, p_hpc, p_ha1, p_reg, p_ren = col_pos

        def get(row: list[str], p: int) -> str:
            return row[p] if 0 <= p < len(row) else ""

        for raw in reader:
            if not raw or p_lei < 0 or p_lei >= len(raw):
                continue
            lei = raw[p_lei].strip()
            if not lei:
                continue
            lname = _clean(get(raw, p_name), 400) or ""
            nk = name_key(lname) if lname else None
            iso2 = (_clean(get(raw, p_c), 8) or "").upper() or None
            hq_iso2 = (_clean(get(raw, p_hc), 8) or "").upper() or None
            yield (
                lei,
                lname or None,
                nk or None,
                _clean(get(raw, p_es), 40),
                _clean(get(raw, p_rs), 40),
                _clean(get(raw, p_ec), 40),
                _clean(get(raw, p_lfc), 40),
                _clean(get(raw, p_lf), 120),
                _clean(get(raw, p_jur), 20),
                iso2,
                _clean(get(raw, p_r), 80),
                (_clean(get(raw, p_city), 120) or "").lower() or None,
                (_clean(get(raw, p_pc), 40) or "").upper() or None,
                _clean(get(raw, p_a1), 300),
                hq_iso2,
                (_clean(get(raw, p_hcity), 120) or "").lower() or None,
                (_clean(get(raw, p_hpc), 40) or "").upper() or None,
                _clean(get(raw, p_ha1), 300),
                _iso_date(get(raw, p_reg)),
                _iso_date(get(raw, p_ren)),
            )

    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as z:
            for name in sorted(z.namelist()):
                if name.endswith("/") or Path(name).name.startswith("."):
                    continue
                with z.open(name) as raw:
                    yield from stream_file(io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline=""))
    else:
        with open(path, encoding="utf-8", errors="replace", newline="") as f:
            yield from stream_file(f)


@dataclass
class Coverage:
    rows: int = 0
    filled: Counter = field(default_factory=Counter)
    by_status: Counter = field(default_factory=Counter)
    by_country: Counter = field(default_factory=Counter)
    overlap: dict = field(default_factory=dict)

    def add(self, row: tuple) -> None:
        self.rows += 1
        for col, val in zip(COLUMNS, row, strict=True):
            if val is not None:
                self.filled[col] += 1
        self.by_status[row[3] or "(none)"] += 1
        self.by_country[row[9] or "--"] += 1

    def report(self, top: int = 15) -> str:
        def pct(n: int, of: int | None = None) -> str:
            of = self.rows if of is None else of
            return f"{n:>12,}  {100 * n / of:5.1f}%" if of else f"{n:>12,}"

        lines = [f"Rows: {self.rows:,}", "", "Field coverage:"]
        lines += [f"  {c:<20} {pct(self.filled[c])}" for c in COLUMNS]
        lines += ["", "By entity_status:"] + [f"  {s:<24} {pct(n)}" for s, n in self.by_status.most_common(10)]
        lines += ["", f"Top {top} legal countries:"] + [
            f"  {c:<6} {pct(n)}" for c, n in self.by_country.most_common(top)
        ]
        if self.overlap:
            o = self.overlap
            lines += [
                "", "Compared with PDL companies (normalised name + iso2):",
                f"  Active GLEIF entities:                 {o['active']:>12,}",
                f"  ... same name + country in PDL:        {pct(o['matched'], o['active'])}",
            ]
        return "\n".join(lines)


def scan(rows: Iterable[tuple], sink: Callable[[tuple], None] | None = None,
         progress: Callable[[int], None] | None = None) -> Coverage:
    cov = Coverage()
    for row in rows:
        cov.add(row)
        if sink is not None:
            sink(row)
        if progress is not None and cov.rows % 500_000 == 0:
            progress(cov.rows)
    return cov


def _create(cur, name: str) -> None:
    cur.execute(f"""
        CREATE TABLE kb.{name} (
            lei text, legal_name text, name_key text, entity_status text, registration_status text,
            entity_category text, legal_form_code text, legal_form text, jurisdiction text,
            iso2 text, region text, city text, postcode text, address_line1 text,
            hq_iso2 text, hq_city text, hq_postcode text, hq_address_line1 text,
            registered_at date, next_renewal date
        )""")


def overlap_with_pdl(conn, dsn: str | None = None) -> dict:
    import psycopg

    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('kb.pdl_company')")
        if not cur.fetchone()[0]:
            return {}
        cur.execute("DROP TABLE IF EXISTS kb.pdl_gleif_keys")
        cur.execute("CREATE UNLOGGED TABLE kb.pdl_gleif_keys (iso2 text, name_key text)")
    with psycopg.connect(dsn or kb_dsn()) as rconn, rconn.cursor(name="pdl_gleif_stream") as src:
        with conn.cursor() as dst, dst.copy("COPY kb.pdl_gleif_keys (iso2, name_key) FROM STDIN") as copy:
            src.execute("SELECT iso2, name FROM kb.pdl_company WHERE iso2 IS NOT NULL AND name IS NOT NULL")
            while batch := src.fetchmany(100_000):
                for iso, n in batch:
                    if len(n) <= 500 and (nk := name_key(n)[:300]):
                        copy.write_row((iso, nk))
    with conn.cursor() as cur:
        cur.execute("CREATE INDEX ON kb.pdl_gleif_keys (iso2, name_key)")
        cur.execute("""
            WITH pdl AS (SELECT DISTINCT iso2, name_key FROM kb.pdl_gleif_keys)
            SELECT count(*) FILTER (WHERE entity_status = 'ACTIVE'),
                   count(*) FILTER (
                       WHERE entity_status = 'ACTIVE' AND name_key IS NOT NULL
                         AND EXISTS (SELECT 1 FROM pdl p WHERE p.iso2 = g.iso2 AND p.name_key = g.name_key)
                   )
            FROM kb.gleif_company g
        """)
        active, matched = cur.fetchone()
        cur.execute("DROP TABLE kb.pdl_gleif_keys")
    return {"active": active, "matched": matched}


def load(path: Path, dsn: str | None = None, force: bool = False,
         progress: Callable[[int], None] | None = None) -> Coverage:
    """Copy into kb.gleif_company_load, verify row share, swap in as kb.gleif_company."""
    import psycopg

    sha = file_sha256(path)
    with psycopg.connect(dsn or kb_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
            cur.execute(f"DROP TABLE IF EXISTS kb.{TABLE}_load")
            _create(cur, f"{TABLE}_load")
            with cur.copy(f"COPY kb.{TABLE}_load ({', '.join(COLUMNS)}) FROM STDIN") as copy:
                cov = scan(iter_rows(path), copy.write_row, progress)
            cur.execute("SELECT to_regclass(%s)", (f"kb.{TABLE}",))
            previous = 0
            if cur.fetchone()[0]:
                cur.execute(f"SELECT count(*) FROM kb.{TABLE}")  # noqa: S608
                previous = cur.fetchone()[0]
            if cov.rows == 0 or (previous and cov.rows < MIN_SHARE_OF_PREVIOUS * previous and not force):
                conn.rollback()
                raise ValueError(f"refused: the file has {cov.rows:,} rows, current table {previous:,}; pass --force")
            cur.execute(f"CREATE INDEX ON kb.{TABLE}_load (lei)")
            cur.execute(f"CREATE INDEX ON kb.{TABLE}_load (name_key)")
            cur.execute(f"CREATE INDEX ON kb.{TABLE}_load (iso2, name_key)")
            cur.execute(f"DROP TABLE IF EXISTS kb.{TABLE}")
            cur.execute(f"ALTER TABLE kb.{TABLE}_load RENAME TO {TABLE}")
        cov.overlap = overlap_with_pdl(conn, dsn)
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO kb.load_log (source, file_name, file_sha256, rows, coverage) "
                "VALUES ('gleif_lei2', %s, %s, %s, %s)",
                (path.name, sha, cov.rows, json.dumps({
                    "rows": cov.rows, "filled": dict(cov.filled),
                    "by_status": dict(cov.by_status), "overlap": cov.overlap})),
            )
        conn.commit()
    return cov


PARENT_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS kb.gleif_parent (
    lei text PRIMARY KEY,
    direct_parent_lei text,
    ultimate_parent_lei text,
    branch_of_lei text
);
CREATE INDEX IF NOT EXISTS gleif_parent_direct_idx ON kb.gleif_parent (direct_parent_lei);
CREATE INDEX IF NOT EXISTS gleif_parent_ult_idx ON kb.gleif_parent (ultimate_parent_lei);
"""


def parse_parent_rows(path: Path) -> list[tuple[str, str | None, str | None, str | None]]:
    """Extract ACTIVE direct parent, ultimate parent, and branch-of LEI links from GLEIF RR CSV/ZIP."""
    parents: dict[str, list[str | None]] = {}

    def read_stream(stream: io.TextIOBase) -> None:
        reader = csv.reader(stream)
        header = next(reader, None)
        if not header:
            return
        idx = {h.strip(): i for i, h in enumerate(header)}
        p_child = idx.get("Relationship.StartNode.NodeID", 0)
        p_parent = idx.get("Relationship.EndNode.NodeID", 2)
        p_type = idx.get("Relationship.RelationshipType", 4)
        p_stat = idx.get("Relationship.RelationshipStatus", 5)
        for raw in reader:
            if len(raw) <= max(p_child, p_parent, p_type, p_stat):
                continue
            if raw[p_stat].strip() != "ACTIVE":
                continue
            rel = raw[p_type].strip()
            slot = 0 if rel == "IS_DIRECTLY_CONSOLIDATED_BY" else (
                1 if rel == "IS_ULTIMATELY_CONSOLIDATED_BY" else (
                    2 if rel == "IS_INTERNATIONAL_BRANCH_OF" else -1
                )
            )
            if slot < 0:
                continue
            child = raw[p_child].strip()
            parent = raw[p_parent].strip()
            if not child or not parent or child == parent:
                continue
            cur = parents.setdefault(child, [None, None, None])
            if cur[slot] is None:
                cur[slot] = parent

    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            with io.TextIOWrapper(zf.open(names[0]), encoding="utf-8", errors="replace", newline="") as f:
                read_stream(f)
    else:
        with path.open(encoding="utf-8", errors="replace", newline="") as f:
            read_stream(f)
    return [(lei, vals[0], vals[1], vals[2]) for lei, vals in parents.items()]


def load_parents(path: Path, dsn: str | None = None) -> int:
    """Copy GLEIF Level 2 parent links atomically into kb.gleif_parent."""
    import psycopg

    rows = parse_parent_rows(path)
    with psycopg.connect(dsn or kb_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
            cur.execute(PARENT_SCHEMA_SQL)
            cur.execute("DROP TABLE IF EXISTS kb.gleif_parent_load")
            cur.execute(
                "CREATE TABLE kb.gleif_parent_load "
                "(lei text PRIMARY KEY, direct_parent_lei text, ultimate_parent_lei text, branch_of_lei text)"
            )
            with cur.copy(
                "COPY kb.gleif_parent_load (lei, direct_parent_lei, ultimate_parent_lei, branch_of_lei) FROM STDIN"
            ) as copy:
                for row in rows:
                    copy.write_row(row)
            cur.execute("CREATE INDEX ON kb.gleif_parent_load (direct_parent_lei)")
            cur.execute("CREATE INDEX ON kb.gleif_parent_load (ultimate_parent_lei)")
            cur.execute("DROP TABLE IF EXISTS kb.gleif_parent")
            cur.execute("ALTER TABLE kb.gleif_parent_load RENAME TO gleif_parent")
        conn.commit()
    return len(rows)
