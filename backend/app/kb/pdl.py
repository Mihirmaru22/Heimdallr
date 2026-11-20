"""Load the People Data Labs free company dataset (CC BY 4.0, about 22M companies) into kb.pdl_company.

PDL's file has 10 fields: id, name, website, industry, size, founded, country, region (state),
locality (city) and linkedin_url (https://docs.peopledatalabs.com/docs/free-company-dataset).
This loader keeps them as given and adds what follows directly from them:

- domain: the registered domain of the website, the key the rest of the database joins on;
- sector: PDL's industry (LinkedIn's 147 standard industries) mapped to our sectors by
  data/pdl_industry_sector.csv;
- iso2, region, sub_region: from the country, by data/pdl_country_region.csv (UN M49 regions).

Micro-sector, product or service, street address and email are not in PDL; later steps fill them
from the company's own website and from national registers.

The load is all or nothing: rows go into a fresh table, the checks run, and only then does the new
table replace the old one in a single transaction. A load that fails its checks leaves the old
table in place.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import zipfile
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import cache
from pathlib import Path

import tldextract

DATA = Path(__file__).parent / "data"
TABLE = "pdl_company"
COLUMNS = (
    "pdl_id", "name", "website", "domain", "linkedin_url", "industry", "sector", "size", "founded",
    "country", "iso2", "region", "sub_region", "state", "city",
)
# The public suffix list including its private section, so a site on a shared host keeps its own
# key ("acme.wixsite.com", "acme.github.io") instead of collapsing into the host's domain.
_extract = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None, include_psl_private_domains=True)
# A new file must hold at least this share of the rows already loaded, or the swap is refused:
# a truncated download must never replace a good table.
MIN_SHARE_OF_PREVIOUS = 0.9


@cache
def industry_sectors() -> dict[str, str]:
    with open(DATA / "pdl_industry_sector.csv", newline="", encoding="utf-8") as f:
        return {r["industry"]: r["sector"] for r in csv.DictReader(f)}


@cache
def country_regions() -> dict[str, tuple[str, str, str]]:
    with open(DATA / "pdl_country_region.csv", newline="", encoding="utf-8") as f:
        return {r["country"]: (r["iso2"], r["region"], r["sub_region"]) for r in csv.DictReader(f)}


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _open_text(path: Path) -> Iterator[io.TextIOBase]:
    """Yield a text stream for each data file in `path` (plain, .gz, or every member of a .zip)."""
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as z:
            for name in sorted(z.namelist()):
                if name.endswith("/") or Path(name).name.startswith("."):
                    continue
                with z.open(name) as raw:
                    yield io.TextIOWrapper(raw, encoding="utf-8", newline="")
    elif path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
            yield f
    else:
        with open(path, encoding="utf-8", newline="") as f:
            yield f


def read_rows(path: Path) -> Iterator[dict[str, str]]:
    """PDL ships CSV, pipe-delimited and JSON (one object per line); all three are read the same way."""
    for stream in _open_text(path):
        first = stream.readline()
        if not first.strip():
            continue
        if first.lstrip().startswith("{"):
            for line in [first, *stream]:
                if line.strip():
                    yield {k: _text(v) for k, v in json.loads(line).items()}
            continue
        delimiter = "|" if first.count("|") > first.count(",") else ","
        reader = csv.reader([first], delimiter=delimiter)
        header = [h.strip().lower() for h in next(reader)]
        for values in csv.reader(stream, delimiter=delimiter):
            if values:
                yield {k: _text(v) for k, v in zip(header, values, strict=False)}


def _website_domain(website: str) -> str:
    if not website:
        return ""
    host = website.split("://", 1)[-1].split("/", 1)[0].split("?", 1)[0].split(":", 1)[0].strip(".").lower()
    if not host or " " in host:
        return ""
    domain = _extract(host).top_domain_under_public_suffix
    return "" if domain in ("linkedin.com", "facebook.com") else domain


def _founded(value: str) -> int | None:
    try:
        year = int(float(value))
    except ValueError:
        return None
    return year if 1000 <= year <= datetime.now(UTC).year else None


def normalise(row: dict[str, str]) -> tuple:
    industry = row.get("industry", "").lower()
    country = row.get("country", "").lower()
    iso2, region, sub_region = country_regions().get(country, ("", "", ""))
    website = row.get("website", "")
    values = {
        "pdl_id": row.get("id", ""),
        "name": row.get("name", ""),
        "website": website,
        "domain": _website_domain(website),
        "linkedin_url": row.get("linkedin_url", ""),
        "industry": industry,
        "sector": industry_sectors().get(industry, ""),
        "size": row.get("size", ""),
        "founded": _founded(row.get("founded", "")),
        "country": country,
        "iso2": iso2,
        "region": region,
        "sub_region": sub_region,
        "state": row.get("region", "").lower(),
        "city": row.get("locality", "").lower(),
    }
    return tuple(values[c] or None for c in COLUMNS)


@dataclass
class Coverage:
    """How many rows have each field, and which PDL values the mapping tables do not know yet."""

    rows: int = 0
    filled: Counter = field(default_factory=Counter)
    by_country: Counter = field(default_factory=Counter)
    by_sector: Counter = field(default_factory=Counter)
    unknown_industries: Counter = field(default_factory=Counter)
    unknown_countries: Counter = field(default_factory=Counter)
    domains: Counter = field(default_factory=Counter)

    def add(self, raw: dict[str, str], row: tuple) -> None:
        self.rows += 1
        values = dict(zip(COLUMNS, row, strict=True))
        for column, value in values.items():
            if value is not None:
                self.filled[column] += 1
        self.by_country[values["country"] or "(none)"] += 1
        self.by_sector[values["sector"] or "(none)"] += 1
        if raw.get("industry") and not values["sector"]:
            self.unknown_industries[raw["industry"].lower()] += 1
        if raw.get("country") and not values["iso2"]:
            self.unknown_countries[raw["country"].lower()] += 1
        if values["domain"]:
            self.domains[values["domain"]] += 1

    def shared_domains(self) -> int:
        """Domains that more than one PDL row claims (subsidiaries, regional pages, bad data)."""
        return sum(1 for n in self.domains.values() if n > 1)

    def report(self, top: int = 25) -> str:
        def pct(n: int) -> str:
            return f"{100 * n / self.rows:5.1f}%" if self.rows else "   - "

        lines = [f"Rows: {self.rows:,}", "", "Field coverage:"]
        lines += [f"  {c:<13} {self.filled[c]:>12,}  {pct(self.filled[c])}" for c in COLUMNS]
        lines += ["", f"Distinct domains: {len(self.domains):,} (claimed by more than one row: "
                      f"{self.shared_domains():,})", "", "Rows by sector:"]
        lines += [f"  {s:<32} {n:>12,}  {pct(n)}" for s, n in self.by_sector.most_common()]
        shared = [(d, n) for d, n in self.domains.most_common(top) if n > 1]
        if shared:
            lines += ["", "Domains claimed by the most rows (hosting platforms, groups, bad data):"]
            lines += [f"  {d:<32} {n:>12,}" for d, n in shared]
        lines += ["", f"Top {top} countries:"]
        lines += [f"  {c:<32} {n:>12,}  {pct(n)}" for c, n in self.by_country.most_common(top)]
        for title, counter in (("Industries with no sector", self.unknown_industries),
                               ("Countries with no region", self.unknown_countries)):
            if counter:
                lines += ["", f"{title} (add them to the mapping table):"]
                lines += [f"  {v!r}: {n:,}" for v, n in counter.most_common(top)]
        return "\n".join(lines)


def scan(rows: Iterable[dict[str, str]], sink: Callable[[tuple], None] | None = None,
         progress: Callable[[int], None] | None = None) -> Coverage:
    coverage = Coverage()
    for raw in rows:
        row = normalise(raw)
        coverage.add(raw, row)
        if sink is not None:
            sink(row)
        if progress is not None and coverage.rows % 1_000_000 == 0:
            progress(coverage.rows)
    return coverage


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def kb_dsn() -> str:
    from app.config import get_settings

    settings = get_settings()
    url = settings.kb_database_url or settings.database_url
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS kb;
CREATE TABLE IF NOT EXISTS kb.load_log (
    id bigserial PRIMARY KEY,
    source text NOT NULL,
    file_name text NOT NULL,
    file_sha256 text NOT NULL,
    rows bigint NOT NULL,
    loaded_at timestamptz NOT NULL DEFAULT now(),
    coverage jsonb NOT NULL
);
"""


def _create_load_table(cur, name: str) -> None:
    cur.execute(f"""
        CREATE TABLE kb.{name} (
            pdl_id text, name text, website text, domain text, linkedin_url text,
            industry text, sector text, size text, founded integer,
            country text, iso2 text, region text, sub_region text, state text, city text
        )""")


def _index(cur, name: str) -> None:
    cur.execute(f"CREATE INDEX ON kb.{name} (domain)")
    cur.execute(f"CREATE INDEX ON kb.{name} (iso2, sector)")
    cur.execute(f"CREATE INDEX ON kb.{name} (pdl_id)")
    cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")
    if cur.fetchone():  # fuzzy name search; the extension needs a superuser to install once
        cur.execute(f"CREATE INDEX ON kb.{name} USING gin (lower(name) gin_trgm_ops)")


def load(path: Path, dsn: str | None = None, force: bool = False,
         progress: Callable[[int], None] | None = None) -> Coverage:
    """Copy the file into kb.pdl_company_load, check it, then swap it in as kb.pdl_company."""
    import psycopg

    sha = file_sha256(path)
    with psycopg.connect(dsn or kb_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
            cur.execute(f"DROP TABLE IF EXISTS kb.{TABLE}_load")
            _create_load_table(cur, f"{TABLE}_load")
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
            # How many rows share each domain: 1 is a company's own site; hundreds is a hosting
            # platform or directory, which later steps must not treat as one company's website.
            cur.execute(f"ALTER TABLE kb.{TABLE}_load ADD COLUMN domain_rows integer")
            cur.execute(f"""
                UPDATE kb.{TABLE}_load t SET domain_rows = d.n
                FROM (SELECT domain, count(*) AS n FROM kb.{TABLE}_load
                      WHERE domain IS NOT NULL GROUP BY domain) d
                WHERE t.domain = d.domain""")  # noqa: S608 - TABLE is a constant
            _index(cur, f"{TABLE}_load")
            cur.execute(f"DROP TABLE IF EXISTS kb.{TABLE}")
            cur.execute(f"ALTER TABLE kb.{TABLE}_load RENAME TO {TABLE}")
            summary = {
                "rows": coverage.rows,
                "filled": dict(coverage.filled),
                "distinct_domains": len(coverage.domains),
                "shared_domains": coverage.shared_domains(),
                "unknown_industries": dict(coverage.unknown_industries),
                "unknown_countries": dict(coverage.unknown_countries),
            }
            cur.execute(
                "INSERT INTO kb.load_log (source, file_name, file_sha256, rows, coverage) "
                "VALUES ('pdl_free_company', %s, %s, %s, %s)",
                (path.name, sha, coverage.rows, json.dumps(summary)),
            )
        conn.commit()
    return coverage
