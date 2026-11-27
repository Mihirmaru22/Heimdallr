"""Load UK Companies House Accounts iXBRL bulk archives into kb.uk_financials."""

from __future__ import annotations

import json
import re
import zipfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from selectolax.lexbor import LexborHTMLParser

from app.kb.pdl import SCHEMA_SQL, file_sha256, kb_dsn

ACCOUNTS_INDEX_URL = "https://download.companieshouse.gov.uk/en_accountsdata.html"
ACCOUNTS_BASE_URL = "https://download.companieshouse.gov.uk/"
_FILE_RE = re.compile(r"Prod\d+_\d+_([A-Za-z0-9]{8})_(\d{8})\.html?$", re.I)

COLUMNS = (
    "company_number", "period_end", "currency", "turnover", "net_assets",
    "cash", "employees", "accounts_type", "audited", "dormant", "source_file",
)


def _clean_num(text: str, scale: str | None, sign: str | None, allow_neg_scale: bool = True) -> float | None:
    raw = re.sub(r"[£$€,\s]", "", (text or "").strip())
    if not raw or raw in {"-", "—", "nil"}:
        return None
    neg = False
    if raw.startswith("(") and raw.endswith(")"):
        neg = True
        raw = raw[1:-1]
    if sign == "-":
        neg = not neg
    try:
        val = float(raw)
    except ValueError:
        return None
    if scale:
        try:
            sc = int(scale)
            if sc > 0 or (sc < 0 and allow_neg_scale):
                val *= 10 ** sc
        except ValueError:
            pass
    return -abs(val) if neg else val


def _parse_any_date(raw: str) -> date | None:
    s = " ".join((raw or "").split()).strip()
    if not s:
        return None
    if re.fullmatch(r"\d{8}", s):
        try:
            return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        except ValueError:
            return None
    for fmt in ("%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=UTC).date()
        except ValueError:
            continue
    return None


def _tag_local(name: str | None) -> str:
    return (name or "").split(":", 1)[-1]


def parse_ixbrl(html: str, filename: str = "") -> tuple | None:
    """Parse one Companies House iXBRL HTML filing into a kb.uk_financials row tuple."""
    tree = LexborHTMLParser(html)

    file_co, file_dt = "", None
    if m := _FILE_RE.search(filename):
        file_co = m.group(1).upper()
        file_dt = _parse_any_date(m.group(2))

    # Build context id -> (end_date, is_segmented)
    ctx_info: dict[str, tuple[date | None, bool]] = {}
    for ctx in tree.css("xbrli\\:context, context"):
        cid = ctx.attributes.get("id") or ""
        if not cid:
            continue
        inst = ctx.css_first("xbrli\\:instant, instant, xbrli\\:enddate, enddate")
        dt = _parse_any_date(inst.text(strip=True)) if inst else None
        has_seg = bool(
            ctx.css_first("xbrli\\:segment, segment")
            or "segment" in cid.lower()
            or ("_" in cid and "share" in cid.lower())
        )
        ctx_info[cid] = (dt, has_seg)

    currency = "GBP"
    for unit in tree.css("xbrli\\:unit, unit"):
        meas = unit.css_first("xbrli\\:measure, measure")
        if meas:
            mtxt = meas.text(strip=True)
            if ":" in mtxt:
                code = mtxt.split(":", 1)[1].strip().upper()
                if len(code) == 3 and code.isalpha():
                    currency = code
                    break

    company_number = file_co
    period_end = file_dt
    accounts_type = ""
    audited: bool | None = None
    dormant: bool | None = None

    # tag -> list of (date, unsegmented, value)
    candidates: dict[str, list[tuple[date, bool, float]]] = {}

    for node in tree.css("*[name]"):
        tag = _tag_local(node.attributes.get("name"))
        if not tag:
            continue
        cid = node.attributes.get("contextref") or ""
        dt, seg = ctx_info.get(cid, (None, False))
        text = node.text(strip=True)

        if tag == "UKCompaniesHouseRegisteredNumber" and text:
            cleaned = re.sub(r"[^A-Za-z0-9]", "", text).upper().zfill(8)
            if len(cleaned) == 8:
                company_number = cleaned
        elif tag == "BalanceSheetDate" and text and not period_end:
            period_end = _parse_any_date(text) or dt
        elif tag == "EntityDormantTruefalse" and text:
            dormant = text.lower() == "true"
        elif tag == "AccountsType":
            for part in cid.split("_"):
                if any(k in part for k in ("AccountsType", "Filleted", "Micro", "Full", "Abridged")):
                    accounts_type = part.replace("AccountsType", "").strip() or accounts_type
            if not accounts_type and "bus-" in cid:
                accounts_type = cid.rsplit("bus-", 1)[-1]
        elif tag == "AccountsStatusAuditedOrUnaudited":
            low = f"{cid} {text}".lower()
            if "auditexempt" in low or "unaudited" in low:
                audited = False
            elif "audited" in low:
                audited = True
        elif tag in (
            "TurnoverRevenue", "TurnoverGrossOperatingRevenue",
            "NetAssetsLiabilities", "NetCurrentAssetsLiabilities", "TotalAssetsLessCurrentLiabilities", "Equity",
            "CashBankOnHand", "CashBankInHand", "AverageNumberEmployeesDuringPeriod",
        ):
            is_emp = tag == "AverageNumberEmployeesDuringPeriod"
            val = _clean_num(
                text,
                node.attributes.get("scale"),
                node.attributes.get("sign"),
                allow_neg_scale=not is_emp,
            )
            if val is not None:
                use_dt = dt or period_end or date.min
                # Prefer exact period_end or latest date, and prefer unsegmented rows over equity sub-lines.
                exact_end = period_end is not None and dt == period_end
                candidates.setdefault(tag, []).append((use_dt, not seg and (exact_end or dt is None), val))

    if not company_number:
        return None

    def pick_metric(*tags: str) -> float | None:
        for t in tags:
            rows = candidates.get(t)
            if not rows:
                continue
            # Prefer unsegmented latest date (exact period_end first).
            best = max(rows, key=lambda r: (r[1], r[0]))
            return best[2]
        return None

    turnover = pick_metric("TurnoverRevenue", "TurnoverGrossOperatingRevenue")
    net_assets = pick_metric(
        "NetAssetsLiabilities", "TotalAssetsLessCurrentLiabilities", "NetCurrentAssetsLiabilities", "Equity"
    )
    cash = pick_metric("CashBankOnHand", "CashBankInHand")
    emp_raw = pick_metric("AverageNumberEmployeesDuringPeriod")
    employees = int(round(emp_raw)) if emp_raw is not None and 0 <= emp_raw <= 2_000_000 else None

    if turnover is None and net_assets is None and cash is None and employees is None:
        return None

    return (
        company_number,
        period_end,
        currency,
        turnover,
        net_assets,
        cash,
        employees,
        accounts_type[:80] or None,
        audited,
        dormant,
        Path(filename).name[:120] or None,
    )


@dataclass
class Coverage:
    files: int = 0
    rows: int = 0
    with_turnover: int = 0
    with_net_assets: int = 0
    with_cash: int = 0
    with_employees: int = 0

    def add(self, row: tuple | None) -> None:
        self.files += 1
        if row is None:
            return
        self.rows += 1
        if row[3] is not None:
            self.with_turnover += 1
        if row[4] is not None:
            self.with_net_assets += 1
        if row[5] is not None:
            self.with_cash += 1
        if row[6] is not None:
            self.with_employees += 1

    def report(self) -> str:
        return (
            f"UK Accounts: files={self.files:,}, loaded={self.rows:,}, "
            f"net_assets={self.with_net_assets:,}, cash={self.with_cash:,}, "
            f"turnover={self.with_turnover:,}, employees={self.with_employees:,}"
        )


def iter_zip(zip_path: Path) -> Iterator[tuple]:
    """Yield parsed kb.uk_financials tuples from a Companies House Accounts Bulk Data ZIP."""
    with zipfile.ZipFile(zip_path) as z:
        for member in z.infolist():
            if member.is_dir() or not member.filename.lower().endswith((".html", ".htm")):
                continue
            with z.open(member) as f:
                html = f.read().decode("utf-8", "replace")
            row = parse_ixbrl(html, member.filename)
            if row is not None:
                yield row


def load(paths: list[Path], dsn: str | None = None,
         progress: Callable[[int], None] | None = None) -> Coverage:
    """Upsert parsed UK Companies House iXBRL accounts into kb.uk_financials."""
    import psycopg

    cov = Coverage()
    with psycopg.connect(dsn or kb_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kb.uk_financials (
                    company_number text PRIMARY KEY,
                    period_end date,
                    currency text,
                    turnover double precision,
                    net_assets double precision,
                    cash double precision,
                    employees integer,
                    accounts_type text,
                    audited boolean,
                    dormant boolean,
                    source_file text,
                    loaded_at timestamptz NOT NULL DEFAULT now()
                )""")
            cur.execute(
                "CREATE INDEX IF NOT EXISTS uk_financials_net_assets_idx "
                "ON kb.uk_financials (net_assets DESC NULLS LAST)"
            )

            for zpath in paths:
                sha = file_sha256(zpath)
                dedup: dict[str, tuple] = {}
                for row in iter_zip(zpath):
                    cov.add(row)
                    dedup[row[0]] = row
                    if progress and cov.rows % 2000 == 0:
                        progress(cov.rows)
                if dedup:
                    cur.executemany(
                        """INSERT INTO kb.uk_financials (
                               company_number, period_end, currency, turnover, net_assets,
                               cash, employees, accounts_type, audited, dormant, source_file, loaded_at
                           ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                           ON CONFLICT (company_number) DO UPDATE SET
                               period_end = EXCLUDED.period_end,
                               currency = EXCLUDED.currency,
                               turnover = COALESCE(EXCLUDED.turnover, kb.uk_financials.turnover),
                               net_assets = COALESCE(EXCLUDED.net_assets, kb.uk_financials.net_assets),
                               cash = COALESCE(EXCLUDED.cash, kb.uk_financials.cash),
                               employees = COALESCE(EXCLUDED.employees, kb.uk_financials.employees),
                               accounts_type = COALESCE(EXCLUDED.accounts_type, kb.uk_financials.accounts_type),
                               audited = COALESCE(EXCLUDED.audited, kb.uk_financials.audited),
                               dormant = COALESCE(EXCLUDED.dormant, kb.uk_financials.dormant),
                               source_file = EXCLUDED.source_file,
                               loaded_at = now()
                           WHERE kb.uk_financials.period_end IS NULL
                              OR EXCLUDED.period_end >= kb.uk_financials.period_end""",
                        list(dedup.values()),
                    )
                cur.execute(
                    "INSERT INTO kb.load_log (source, file_name, file_sha256, rows, coverage) "
                    "VALUES ('uk_accounts_ixbrl', %s, %s, %s, %s)",
                    (zpath.name, sha, len(dedup), json.dumps({
                        "rows": len(dedup), "net_assets": cov.with_net_assets,
                        "turnover": cov.with_turnover, "employees": cov.with_employees,
                    })),
                )
        conn.commit()
    return cov
