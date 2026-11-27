"""Load SEC EDGAR bulk XBRL companyfacts.zip into kb.sec_financial_fact and kb.sec_financial_latest."""

from __future__ import annotations

import json
import re
import zipfile
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from app.kb.pdl import SCHEMA_SQL, file_sha256, kb_dsn

COMPANYFACTS_URL = "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip"
ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}
QUARTERLY_FORMS = {"10-Q", "10-Q/A"}
ALLOWED_FORMS = ANNUAL_FORMS | QUARTERLY_FORMS

_CIK_RE = re.compile(r"(?:^|/)CIK(\d+)\.json$", re.I)

# Priority-ordered XBRL tags for canonical metrics across us-gaap, ifrs-full, and dei.
METRIC_CONCEPTS: dict[str, tuple[tuple[str, str], ...]] = {
    "revenue": (
        ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
        ("us-gaap", "Revenues"),
        ("us-gaap", "SalesRevenueNet"),
        ("us-gaap", "RevenueFromContractWithCustomerIncludingAssessedTax"),
        ("us-gaap", "SalesRevenueGoodsNet"),
        ("us-gaap", "SalesRevenueServicesNet"),
        ("us-gaap", "RevenuesNetOfInterestExpense"),
        ("us-gaap", "InterestAndDividendIncomeOperating"),
        ("us-gaap", "TotalRevenuesAndOtherIncome"),
        ("ifrs-full", "Revenue"),
    ),
    "net_income": (
        ("us-gaap", "NetIncomeLoss"),
        ("us-gaap", "ProfitLoss"),
        ("ifrs-full", "ProfitLoss"),
    ),
    "operating_income": (
        ("us-gaap", "OperatingIncomeLoss"),
        ("ifrs-full", "ProfitLossFromOperatingActivities"),
    ),
    "rd_expense": (
        ("us-gaap", "ResearchAndDevelopmentExpense"),
        ("us-gaap", "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost"),
        ("ifrs-full", "ResearchAndDevelopmentExpense"),
    ),
    "assets": (
        ("us-gaap", "Assets"),
        ("ifrs-full", "Assets"),
    ),
    "cash": (
        ("us-gaap", "CashAndCashEquivalentsAtCarryingValue"),
        ("us-gaap", "CashCashEquivalentsAndShortTermInvestments"),
        ("us-gaap", "Cash"),
        ("ifrs-full", "CashAndCashEquivalents"),
    ),
    "equity": (
        ("us-gaap", "StockholdersEquity"),
        ("us-gaap", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
        ("ifrs-full", "Equity"),
    ),
    "debt": (
        ("us-gaap", "LongTermDebt"),
        ("us-gaap", "LongTermDebtAndCapitalLeaseObligations"),
        ("us-gaap", "DebtCurrent"),
        ("ifrs-full", "NoncurrentFinancialLiabilities"),
    ),
    "employees": (
        ("dei", "EntityNumberOfEmployees"),
        ("us-gaap", "NumberOfEmployees"),
    ),
}

FLOW_METRICS = {"revenue", "net_income", "operating_income", "rd_expense"}
FACT_COLUMNS = (
    "cik", "metric", "concept", "taxonomy", "form", "audited", "fy", "fp",
    "start_date", "end_date", "filed", "accn", "unit", "val",
)
LATEST_COLUMNS = (
    "cik", "entity_name", "annual_revenue", "prior_annual_revenue", "revenue_yoy_pct",
    "revenue_form", "revenue_fy", "revenue_end", "revenue_filed", "revenue_currency",
    "net_income", "operating_income", "rd_expense", "assets", "cash", "equity", "debt",
    "employees", "balance_form", "balance_end", "audited",
)


def _parse_date(raw: object) -> date | None:
    if not raw or not isinstance(raw, str):
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _is_valid_period(metric: str, form: str, start_d: date | None, end_d: date | None) -> bool:
    if end_d is None:
        return False
    if metric not in FLOW_METRICS:
        return True
    if start_d is None:
        return False
    days = (end_d - start_d).days
    if form in ANNUAL_FORMS:
        return 300 <= days <= 400  # reject 3-month Q4 slices filed under 10-K/FY
    return 60 <= days <= 115  # quarterly 10-Q single-quarter duration


def extract_company_facts(payload: dict, fallback_cik: int | None = None) -> tuple[list[tuple], tuple | None]:
    """Extract canonical annual/quarterly facts and a latest-metrics summary row for one CIK JSON."""
    raw_cik = payload.get("cik") or fallback_cik
    if not raw_cik:
        return [], None
    cik = int(raw_cik)
    entity_name = str(payload.get("entityName") or "")[:300] or None
    facts = payload.get("facts") or {}

    picked_facts: list[tuple] = []
    # metric -> list of candidate dicts ordered for summary selection
    by_metric: dict[str, list[dict]] = {}

    for metric, concept_list in METRIC_CONCEPTS.items():
        # Collect best matching concepts; merge annual+quarterly records avoiding duplicate periods.
        seen_periods: dict[tuple[str, date, str], tuple[int, dict]] = {}
        for prio, (tax, concept) in enumerate(concept_list):
            unit_map = ((facts.get(tax) or {}).get(concept) or {}).get("units") or {}
            if not unit_map:
                continue
            preferred_units = (
                ("pure", "persons")
                if metric == "employees"
                else ("USD", "EUR", "GBP", "CAD", "JPY", "INR", "CHF")
            )
            unit_name = next((u for u in preferred_units if u in unit_map), next(iter(unit_map), None))
            if not unit_name:
                continue
            for item in unit_map[unit_name]:
                form = str(item.get("form") or "").upper()
                if form not in ALLOWED_FORMS:
                    continue
                val = item.get("val")
                if not isinstance(val, (int, float)):
                    continue
                end_d = _parse_date(item.get("end"))
                start_d = _parse_date(item.get("start"))
                filed_d = _parse_date(item.get("filed"))
                if not _is_valid_period(metric, form, start_d, end_d):
                    continue
                fp = str(item.get("fp") or "")[:10]
                fy = int(item["fy"]) if isinstance(item.get("fy"), int) else None
                accn = str(item.get("accn") or "")[:30]
                audited = form in ANNUAL_FORMS
                pkey = (form, end_d, unit_name)
                cand_rank = (-prio, str(filed_d or ""))
                cand = {
                    "cik": cik,
                    "metric": metric,
                    "concept": concept,
                    "taxonomy": tax,
                    "form": form,
                    "audited": audited,
                    "fy": fy,
                    "fp": fp or None,
                    "start_date": start_d,
                    "end_date": end_d,
                    "filed": filed_d,
                    "accn": accn or None,
                    "unit": unit_name[:12],
                    "val": float(val),
                    "_prio": prio,
                    "_rank": cand_rank,
                }
                prev = seen_periods.get(pkey)
                if prev is None or cand_rank > prev["_rank"]:
                    seen_periods[pkey] = cand

        if seen_periods:
            ordered = sorted(
                seen_periods.values(),
                key=lambda r: (r["end_date"], str(r["filed"] or ""), -r["_prio"]),
                reverse=True,
            )
            by_metric[metric] = ordered
            # Keep last ~12 filings per metric to keep DB compact and queryable.
            for rec in ordered[:12]:
                picked_facts.append(tuple(rec[c] for c in FACT_COLUMNS))

    if not picked_facts:
        return [], None

    def pick_latest(metric: str, prefer_annual: bool = True) -> dict | None:
        cands = by_metric.get(metric) or []
        if not cands:
            return None
        if prefer_annual:
            annual = [c for c in cands if c["audited"]]
            if annual:
                return annual[0]
        return cands[0]

    # Revenue: strictly audited annual first + prior year (~1 year earlier) for YoY growth.
    rev_list = [c for c in (by_metric.get("revenue") or []) if c["audited"]]
    rev_latest = rev_list[0] if rev_list else pick_latest("revenue", prefer_annual=False)
    rev_prior = None
    if rev_latest and rev_latest["audited"]:
        for c in rev_list[1:]:
            gap = (rev_latest["end_date"] - c["end_date"]).days
            if 300 <= gap <= 430 and c["unit"] == rev_latest["unit"]:
                rev_prior = c
                break
    yoy = None
    if rev_latest and rev_prior and rev_prior["val"]:
        yoy = round(100.0 * (rev_latest["val"] - rev_prior["val"]) / abs(rev_prior["val"]), 2)

    ni = pick_latest("net_income")
    oi = pick_latest("operating_income")
    rd = pick_latest("rd_expense")
    assets = pick_latest("assets", prefer_annual=False)
    cash = pick_latest("cash", prefer_annual=False)
    eq = pick_latest("equity", prefer_annual=False)
    debt = pick_latest("debt", prefer_annual=False)
    emp = pick_latest("employees", prefer_annual=False)

    latest_row = (
        cik,
        entity_name,
        rev_latest["val"] if rev_latest else None,
        rev_prior["val"] if rev_prior else None,
        yoy,
        rev_latest["form"] if rev_latest else None,
        rev_latest["fy"] if rev_latest else None,
        rev_latest["end_date"] if rev_latest else None,
        rev_latest["filed"] if rev_latest else None,
        rev_latest["unit"] if rev_latest else None,
        ni["val"] if ni else None,
        oi["val"] if oi else None,
        rd["val"] if rd else None,
        assets["val"] if assets else None,
        cash["val"] if cash else None,
        eq["val"] if eq else None,
        debt["val"] if debt else None,
        int(emp["val"]) if emp and emp["val"] >= 0 else None,
        assets["form"] if assets else (rev_latest["form"] if rev_latest else None),
        assets["end_date"] if assets else (rev_latest["end_date"] if rev_latest else None),
        bool((rev_latest and rev_latest["audited"]) or (assets and assets["audited"])),
    )
    return picked_facts, latest_row


@dataclass
class Coverage:
    companies: int = 0
    facts: int = 0
    with_revenue: int = 0
    audited_revenue: int = 0
    with_assets: int = 0
    with_cash: int = 0
    with_employees: int = 0
    _forms: Counter = field(default_factory=Counter)

    def add(self, facts: list[tuple], latest: tuple | None) -> None:
        if latest is None:
            return
        self.companies += 1
        self.facts += len(facts)
        if latest[2] is not None:
            self.with_revenue += 1
            self._forms[latest[5] or "unknown"] += 1
            if latest[5] in ANNUAL_FORMS:
                self.audited_revenue += 1
        if latest[13] is not None:
            self.with_assets += 1
        if latest[14] is not None:
            self.with_cash += 1
        if latest[17] is not None:
            self.with_employees += 1

    def report(self) -> str:
        return (
            f"SEC companyfacts: companies={self.companies:,}, facts={self.facts:,}, "
            f"with_revenue={self.with_revenue:,} (audited_annual={self.audited_revenue:,}), "
            f"with_assets={self.with_assets:,}, with_cash={self.with_cash:,}, "
            f"with_employees={self.with_employees:,}, forms={dict(self._forms)}"
        )


def iter_zip(zip_path: Path) -> Iterator[tuple[list[tuple], tuple | None]]:
    """Stream extracted (facts_rows, latest_row) tuples from companyfacts.zip."""
    with zipfile.ZipFile(zip_path) as z:
        for member in z.infolist():
            m = _CIK_RE.search(member.filename)
            if not m or member.is_dir():
                continue
            cik = int(m.group(1))
            with z.open(member) as f:
                try:
                    payload = json.loads(f.read().decode("utf-8", "replace"))
                except ValueError:
                    continue
            yield extract_company_facts(payload, fallback_cik=cik)


def load(zip_path: Path, dsn: str | None = None,
         progress: Callable[[int], None] | None = None) -> Coverage:
    """Atomically load SEC XBRL companyfacts into kb.sec_financial_fact and kb.sec_financial_latest."""
    import psycopg

    sha = file_sha256(zip_path)
    cov = Coverage()
    with psycopg.connect(dsn or kb_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
            cur.execute("DROP TABLE IF EXISTS kb.sec_financial_fact_load")
            cur.execute("DROP TABLE IF EXISTS kb.sec_financial_latest_load")
            cur.execute("""
                CREATE TABLE kb.sec_financial_fact_load (
                    cik integer NOT NULL, metric text NOT NULL, concept text NOT NULL,
                    taxonomy text NOT NULL, form text NOT NULL, audited boolean NOT NULL,
                    fy integer, fp text, start_date date, end_date date NOT NULL,
                    filed date, accn text, unit text, val double precision NOT NULL
                )""")
            cur.execute("""
                CREATE TABLE kb.sec_financial_latest_load (
                    cik integer PRIMARY KEY, entity_name text,
                    annual_revenue double precision, prior_annual_revenue double precision,
                    revenue_yoy_pct real, revenue_form text, revenue_fy integer,
                    revenue_end date, revenue_filed date, revenue_currency text,
                    net_income double precision, operating_income double precision,
                    rd_expense double precision, assets double precision, cash double precision,
                    equity double precision, debt double precision, employees integer,
                    balance_form text, balance_end date, audited boolean NOT NULL
                )""")

            batch_latest: list[tuple] = []
            with cur.copy(
                f"COPY kb.sec_financial_fact_load ({', '.join(FACT_COLUMNS)}) FROM STDIN"
            ) as fact_copy:
                for facts, latest in iter_zip(zip_path):
                    if latest is None:
                        continue
                    cov.add(facts, latest)
                    for row in facts:
                        fact_copy.write_row(row)
                    batch_latest.append(latest)
                    if progress and cov.companies % 1000 == 0:
                        progress(cov.companies)

            with cur.copy(
                f"COPY kb.sec_financial_latest_load ({', '.join(LATEST_COLUMNS)}) FROM STDIN"
            ) as latest_copy:
                for row in batch_latest:
                    latest_copy.write_row(row)

            cur.execute("CREATE INDEX ON kb.sec_financial_fact_load (cik, metric, end_date DESC)")
            cur.execute("CREATE INDEX ON kb.sec_financial_fact_load (form)")
            cur.execute("CREATE INDEX ON kb.sec_financial_latest_load (annual_revenue DESC NULLS LAST)")
            cur.execute("DROP TABLE IF EXISTS kb.sec_financial_fact")
            cur.execute("DROP TABLE IF EXISTS kb.sec_financial_latest")
            cur.execute("ALTER TABLE kb.sec_financial_fact_load RENAME TO sec_financial_fact")
            cur.execute("ALTER TABLE kb.sec_financial_latest_load RENAME TO sec_financial_latest")

            cur.execute(
                "INSERT INTO kb.load_log (source, file_name, file_sha256, rows, coverage) "
                "VALUES ('sec_companyfacts', %s, %s, %s, %s)",
                (zip_path.name, sha, cov.companies, json.dumps({
                    "companies": cov.companies, "facts": cov.facts,
                    "with_revenue": cov.with_revenue, "audited_revenue": cov.audited_revenue,
                    "with_assets": cov.with_assets, "with_cash": cov.with_cash,
                    "with_employees": cov.with_employees,
                })),
            )
        conn.commit()
    return cov
