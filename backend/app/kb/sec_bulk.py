"""Load SEC EDGAR bulk company metadata (company_tickers_exchange.json + submissions.zip) into kb.sec_company."""

from __future__ import annotations

import json
import re
import zipfile
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from app.kb.companies_house import name_key
from app.kb.pdl import MIN_SHARE_OF_PREVIOUS, SCHEMA_SQL, _website_domain, file_sha256, kb_dsn

TABLE = "sec_company"
COLUMNS = (
    "cik", "name", "name_key", "ticker", "exchange", "rank", "sic", "sic_description",
    "ein", "entity_type", "website", "domain", "city", "state", "foreign_filer", "address",
)
_MAIN_JSON_RE = re.compile(r"(?:^|/)CIK(\d+)\.json$", re.I)


def _clean(val: object, limit: int = 300) -> str | None:
    s = " ".join(str(val or "").replace("\x00", "").split()).strip()
    return s[:limit] if s else None


def load_tickers(path: Path) -> dict[int, tuple[str, str, int]]:
    """Map CIK -> (primary_ticker, exchange, rank) from company_tickers_exchange.json."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    fields = payload["fields"]
    idx_cik = fields.index("cik")
    idx_tk = fields.index("ticker")
    idx_ex = fields.index("exchange")
    out: dict[int, tuple[str, str, int]] = {}
    for rank, raw in enumerate(payload["data"]):
        cik = int(raw[idx_cik])
        if cik not in out:
            out[cik] = (str(raw[idx_tk] or "")[:20], str(raw[idx_ex] or "")[:40], rank)
    return out


def iter_rows(tickers_path: Path, submissions_zip: Path) -> Iterator[tuple]:
    """Stream SEC EDGAR entity records from submissions.zip (skipping paginated filing chunks)."""
    tickers = load_tickers(tickers_path)
    with zipfile.ZipFile(submissions_zip) as z:
        for member in z.infolist():
            m = _MAIN_JSON_RE.search(member.filename)
            if not m or member.is_dir():
                continue
            cik = int(m.group(1))
            with z.open(member) as f:
                body = json.loads(f.read().decode("utf-8", "replace"))
            name = _clean(body.get("name"), 300)
            if not name:
                continue
            tk_list = body.get("tickers") or []
            ex_list = body.get("exchanges") or []
            t_info = tickers.get(cik)
            ticker = (t_info[0] if t_info else (str(tk_list[0])[:20] if tk_list else "")) or None
            exchange = (t_info[1] if t_info else (str(ex_list[0])[:40] if ex_list else "")) or None
            rank = t_info[2] if t_info else None
            website = _clean(body.get("website"), 500)
            domain = _website_domain(website or "") or None
            biz = (body.get("addresses") or {}).get("business") or {}
            mail = (body.get("addresses") or {}).get("mailing") or {}
            addr_obj = biz if any(biz.get(k) for k in ("street1", "city", "stateOrCountry")) else mail
            city = (_clean(addr_obj.get("city"), 120) or "").lower() or None
            state_raw = _clean(addr_obj.get("stateOrCountryDescription") or addr_obj.get("stateOrCountry"), 80)
            addr_parts = [addr_obj.get(k) for k in ("street1", "street2", "city", "stateOrCountry", "zipCode")]
            address = _clean(", ".join(str(p).strip() for p in addr_parts if p and str(p).strip()), 300)
            sic = _clean(body.get("sic"), 10)
            sic_desc = _clean(body.get("sicDescription"), 200)
            ein = _clean(body.get("ein"), 20)
            etype = _clean(body.get("entityType"), 40)
            nk = name_key(name) or None
            is_foreign = bool(addr_obj.get("isForeignLocation"))
            yield (
                cik, name, nk, ticker, exchange, rank, sic, sic_desc,
                ein, etype, website, domain, city, state_raw, is_foreign, address,
            )


@dataclass
class Coverage:
    rows: int = 0
    filled: Counter = field(default_factory=Counter)
    by_exchange: Counter = field(default_factory=Counter)
    by_type: Counter = field(default_factory=Counter)
    overlap: dict = field(default_factory=dict)

    def add(self, row: tuple) -> None:
        self.rows += 1
        for col, val in zip(COLUMNS, row, strict=True):
            if val is not None:
                self.filled[col] += 1
        self.by_exchange[row[4] or "(unlisted)"] += 1
        self.by_type[row[9] or "(unknown)"] += 1

    def report(self) -> str:
        def pct(n: int, of: int | None = None) -> str:
            of = self.rows if of is None else of
            return f"{n:>10,}  {100 * n / of:5.1f}%" if of else f"{n:>10,}"

        lines = [f"Rows: {self.rows:,}", "", "Field coverage:"]
        lines += [f"  {c:<18} {pct(self.filled[c])}" for c in COLUMNS]
        lines += ["", "By exchange:"] + [f"  {k:<18} {pct(n)}" for k, n in self.by_exchange.most_common(10)]
        lines += ["", "By entity_type:"] + [f"  {k:<18} {pct(n)}" for k, n in self.by_type.most_common(10)]
        if self.overlap:
            o = self.overlap
            lines += [
                "", "Compared with PDL US companies:",
                f"  SEC entities with ticker:              {o['listed']:>10,}",
                f"  SEC entities with domain:              {o['with_domain']:>10,}",
                f"  ... domain also in PDL:                {o['domain_match']:>10,}",
            ]
        return "\n".join(lines)


def scan(rows: Iterable[tuple], sink: Callable[[tuple], None] | None = None,
         progress: Callable[[int], None] | None = None) -> Coverage:
    cov = Coverage()
    for row in rows:
        cov.add(row)
        if sink is not None:
            sink(row)
        if progress is not None and cov.rows % 100_000 == 0:
            progress(cov.rows)
    return cov


def _create(cur, name: str) -> None:
    cur.execute(f"""
        CREATE TABLE kb.{name} (
            cik integer, name text, name_key text, ticker text, exchange text, rank integer,
            sic text, sic_description text, ein text, entity_type text, website text, domain text,
            city text, state text, foreign_filer boolean, address text
        )""")


def load(tickers_path: Path, submissions_zip: Path, dsn: str | None = None, force: bool = False,
         progress: Callable[[int], None] | None = None) -> Coverage:
    """Load SEC bulk submissions into kb.sec_company and sync listed issuers into public.sec_companies."""
    import psycopg

    sha = file_sha256(submissions_zip)
    with psycopg.connect(dsn or kb_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
            cur.execute(f"DROP TABLE IF EXISTS kb.{TABLE}_load")
            _create(cur, f"{TABLE}_load")
            with cur.copy(f"COPY kb.{TABLE}_load ({', '.join(COLUMNS)}) FROM STDIN") as copy:
                cov = scan(iter_rows(tickers_path, submissions_zip), copy.write_row, progress)
            cur.execute("SELECT to_regclass(%s)", (f"kb.{TABLE}",))
            previous = 0
            if cur.fetchone()[0]:
                cur.execute(f"SELECT count(*) FROM kb.{TABLE}")  # noqa: S608
                previous = cur.fetchone()[0]
            if cov.rows == 0 or (previous and cov.rows < MIN_SHARE_OF_PREVIOUS * previous and not force):
                conn.rollback()
                raise ValueError(f"refused: {cov.rows:,} rows vs current {previous:,}; pass --force")
            cur.execute(f"CREATE INDEX ON kb.{TABLE}_load (cik)")
            cur.execute(f"CREATE INDEX ON kb.{TABLE}_load (domain)")
            cur.execute(f"CREATE INDEX ON kb.{TABLE}_load (name_key)")
            cur.execute(f"CREATE INDEX ON kb.{TABLE}_load (ticker)")
            cur.execute(f"DROP TABLE IF EXISTS kb.{TABLE}")
            cur.execute(f"ALTER TABLE kb.{TABLE}_load RENAME TO {TABLE}")

            # Overlap vs PDL domains
            cur.execute("""
                SELECT count(*) FILTER (WHERE ticker IS NOT NULL),
                       count(*) FILTER (WHERE domain IS NOT NULL),
                       count(*) FILTER (WHERE domain IS NOT NULL
                                          AND EXISTS (SELECT 1 FROM kb.pdl_company p WHERE p.domain = s.domain))
                FROM kb.sec_company s
            """)
            listed, with_dom, dom_match = cur.fetchone()
            cov.overlap = {"listed": listed, "with_domain": with_dom, "domain_match": dom_match}
            cur.execute(
                "INSERT INTO kb.load_log (source, file_name, file_sha256, rows, coverage) "
                "VALUES ('sec_edgar_bulk', %s, %s, %s, %s)",
                (submissions_zip.name, sha, cov.rows, json.dumps({
                    "rows": cov.rows, "filled": dict(cov.filled), "overlap": cov.overlap})),
            )
            # Also populate public.sec_companies if present (for per-job discovery)
            cur.execute("SELECT to_regclass('public.sec_companies')")
            if cur.fetchone()[0]:
                cur.execute("""
                    INSERT INTO public.sec_companies (cik, name, ticker, exchange, rank, sic, sic_description,
                                                      city, state, "foreign", website, fetched_at)
                    SELECT cik, left(name, 300), coalesce(ticker, ''), coalesce(exchange, ''),
                           coalesce(rank, 1000000), left(sic, 4), coalesce(left(sic_description, 200), ''),
                           coalesce(left(initcap(city), 120), ''), coalesce(left(state, 60), ''),
                           coalesce(foreign_filer, false), coalesce(left(website, 500), ''), now()
                    FROM kb.sec_company
                    WHERE ticker IS NOT NULL
                    ON CONFLICT (cik) DO UPDATE SET
                        name = EXCLUDED.name, ticker = EXCLUDED.ticker, exchange = EXCLUDED.exchange,
                        rank = EXCLUDED.rank, sic = EXCLUDED.sic, sic_description = EXCLUDED.sic_description,
                        city = EXCLUDED.city, state = EXCLUDED.state, "foreign" = EXCLUDED."foreign",
                        website = EXCLUDED.website, fetched_at = EXCLUDED.fetched_at
                """)
        conn.commit()
    return cov
