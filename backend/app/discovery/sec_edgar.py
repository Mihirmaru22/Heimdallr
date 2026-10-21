"""SEC EDGAR discovery: US-listed companies by SIC industry code.

SEC publishes every listed company (company_tickers_exchange.json, largest first) and, per company,
its SIC code and business address (data.sec.gov submissions API). Both are free and need no key,
but SEC asks for at most 10 requests a second and a User-Agent with a contact address. Looking up
~8,000 companies on every job would be far too slow, so a task keeps a local copy in sec_companies
(`python -m app.cli refresh-sec`, then a daily top-up). SEC rarely lists a website, so websites come
from Wikidata items that carry the company's Central Index Key (P5531).
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.crawl.urlnorm import normalize_url, registered_domain
from app.db import session_scope, utcnow
from app.discovery.providers import WIKIDATA_API, DiscoveryError, DiscoveryResult, WikidataProvider, wd_label
from app.models import SecCompany
from app.spec.models import ExtractionSpec
from app.spec.spelling import to_us

log = logging.getLogger("webdata.sec")

TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
REQUESTS_PER_SECOND = 5  # SEC allows 10; staying well under keeps us polite
# Words people use for an industry that SEC's SIC descriptions spell differently.
SYNONYMS = {
    "pharma": ["pharmaceutical"], "biotech": ["biological", "pharmaceutical"],
    "biotechnology": ["biological", "pharmaceutical"], "bank": ["banks"], "banking": ["banks"],
    "software": ["software", "computer programming"], "saas": ["software"],
    "semiconductors": ["semiconductor"], "oil": ["petroleum", "crude"], "gas": ["natural gas"],
    "insurance": ["insurance"],
    # A broad "tech" request: software, computers, chips and internet services (SIC 7370-7374, 3570s, 3670s).
    "tech": ["software", "computer", "semiconductor", "electronic computers"],
    "technology": ["software", "computer", "semiconductor", "electronic computers"],
    "medical devices": ["surgical", "medical", "electromedical"],
    # Defense has no SIC code of its own: weapons, missiles, military electronics, aircraft and warships.
    "defense": ["ordnance", "guided missiles", "search, detection", "aircraft", "ship & boat"],
    "aerospace": ["aircraft", "guided missiles", "search, detection"],
}
# Tech niches newer than SEC's industry codes: SEC files CrowdStrike and Microsoft alike under "Prepackaged
# Software", so for these it cannot say who belongs and is skipped (Wikidata and web search still run).
TECH_NICHES = {"cybersecurity", "computer security", "information security", "security", "saas", "fintech", "ai",
               "artificial intelligence", "machine learning", "edtech", "healthtech", "adtech", "martech",
               "insurtech", "proptech", "regtech", "cleantech", "blockchain", "crypto", "cloud", "devops"}
# SEC's two-letter codes for US states and territories; anything else (V8 = Switzerland, I0 = France) is abroad.
US_STATES = set("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY "
                "NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY PR VI GU AS MP".split())
STOP_WORDS = {"and", "the", "of", "for", "companies", "company", "industry", "sector", "services", "products"}


# --- the local index -------------------------------------------------------------------------------


def _client() -> httpx.Client:
    return httpx.Client(timeout=30, headers={"User-Agent": get_settings().user_agent}, follow_redirects=True)


def _parse_submission(cik: int, body: dict[str, Any]) -> dict[str, Any]:
    business = (body.get("addresses") or {}).get("business") or {}
    # SEC leaves isForeignLocation empty for some foreign filers (Novartis: Basel, "V8").
    foreign = bool(business.get("isForeignLocation")) or (business.get("stateOrCountry") or "") not in US_STATES
    website = normalize_url(body.get("website") or "") or ""
    return {
        "sic": (str(body.get("sic") or "").strip() or None),
        "sic_description": str(body.get("sicDescription") or "")[:200],
        "city": str(business.get("city") or "").title()[:120],
        "state": str((business.get("stateOrCountryDescription") if foreign else business.get("stateOrCountry"))
                     or "")[:60],
        "foreign": foreign,
        "website": website[:500],
        "fetched_at": utcnow(),
    }


def refresh_index(
    client: httpx.Client | None = None, *, max_age_days: int = 30, limit: int | None = None,
    progress: Callable[[int, int], None] | None = None, rate: float = REQUESTS_PER_SECOND,
) -> dict[str, int]:
    """Download SEC's company list, then look up companies not checked in `max_age_days`, largest first."""
    own = client is None
    client = client or _client()
    try:
        resp = client.get(TICKERS_URL)
        resp.raise_for_status()
        payload = resp.json()
        fields = payload["fields"]
        rows: dict[int, dict[str, Any]] = {}
        for i, raw in enumerate(payload["data"]):
            row = dict(zip(fields, raw, strict=False))
            cik = int(row["cik"])
            if cik not in rows:  # one company can have several tickers; the first is its main one
                rows[cik] = {"cik": cik, "name": str(row["name"])[:300], "ticker": str(row.get("ticker") or "")[:20],
                             "exchange": str(row.get("exchange") or "")[:40], "rank": i}
        with session_scope(bypass=True) as db:
            for chunk in range(0, len(rows), 1000):
                batch = list(rows.values())[chunk:chunk + 1000]
                stmt = insert(SecCompany).values([{**r, "sic_description": "", "city": "", "state": "",
                                                   "foreign": False, "website": ""} for r in batch])
                db.execute(stmt.on_conflict_do_update(index_elements=["cik"], set_={
                    "name": stmt.excluded.name, "ticker": stmt.excluded.ticker,
                    "exchange": stmt.excluded.exchange, "rank": stmt.excluded.rank}))
            cutoff = utcnow() - timedelta(days=max_age_days)
            stale = db.execute(select(SecCompany.cik).where(
                SecCompany.cik.in_(list(rows)),
                (SecCompany.fetched_at.is_(None)) | (SecCompany.fetched_at < cutoff),
            ).order_by(SecCompany.rank).limit(limit)).scalars().all()
        done = failed = 0
        pending: list[tuple[int, dict[str, Any]]] = []
        for cik in stale:
            started = time.monotonic()
            try:
                r = client.get(SUBMISSIONS_URL.format(cik=cik))
                if r.status_code == 429:  # back off once, then carry on with the next company
                    time.sleep(10)
                    r = client.get(SUBMISSIONS_URL.format(cik=cik))
                if r.status_code == 200:
                    pending.append((cik, _parse_submission(cik, r.json())))
                    done += 1
                else:
                    failed += 1
            except (httpx.HTTPError, ValueError):
                failed += 1
            if len(pending) >= 100 or cik == stale[-1]:
                with session_scope(bypass=True) as db:
                    for c, values in pending:
                        db.execute(SecCompany.__table__.update().where(SecCompany.cik == c).values(**values))
                pending = []
            if progress:
                progress(done + failed, len(stale))
            time.sleep(max(0.0, 1 / rate - (time.monotonic() - started)) if rate else 0)
        return {"companies": len(rows), "looked_up": done, "failed": failed}
    finally:
        if own:
            client.close()


def index_ready() -> bool:
    with session_scope(bypass=True) as db:
        return db.execute(select(SecCompany.cik).where(SecCompany.fetched_at.is_not(None)).limit(1)).first() is not None


# --- matching an industry to SIC codes -------------------------------------------------------------


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]+", text.lower()) if len(w) >= 3 and w not in STOP_WORDS]


def sic_codes_for(industry: str, descriptions: dict[str, str]) -> list[str]:
    """SIC codes whose description mentions the industry ("pharmaceutical" -> 2834 Pharmaceutical Preparations)."""
    term = to_us(industry.lower().strip())
    stems = list(SYNONYMS.get(term, []))
    for w in _words(term):
        stems += SYNONYMS.get(w, [w[:7] if len(w) > 7 else w])
    out = []
    for code, desc in sorted(descriptions.items()):
        d = desc.lower()
        if any(re.search(rf"\b{re.escape(s)}", d) for s in stems):
            out.append(code)
    return out


# --- the provider ----------------------------------------------------------------------------------


class SecEdgarProvider:
    name = "sec_edgar"
    WIKIDATA_BATCH = 15  # CIKs per search; Wikidata search queries are limited to about 300 characters

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self.client = client
        self.notes: list[str] = []

    @staticmethod
    def covers(spec: ExtractionSpec) -> bool:
        d = spec.discovery
        return (not d.countries and not d.region) or "US" in d.countries or d.region == "north_america"

    async def from_wikidata(self, client: httpx.AsyncClient, ciks: list[int]) -> dict[int, dict[str, Any]]:
        """CIK -> website and label of the Wikidata item carrying that CIK."""
        wd = WikidataProvider(client)
        found: dict[int, dict[str, Any]] = {}
        for i in range(0, len(ciks), self.WIKIDATA_BATCH):
            chunk = ciks[i:i + self.WIKIDATA_BATCH]
            query = "haswbstatement:" + "|".join(f"P5531={c:010d}" for c in chunk)
            resp = await client.get(WIKIDATA_API, params={
                "action": "query", "list": "search", "srsearch": query, "srnamespace": 0, "srlimit": 50,
                "srprop": "", "format": "json"})
            resp.raise_for_status()
            qids = [h["title"] for h in resp.json().get("query", {}).get("search", [])]
            if not qids:
                continue
            for e in (await wd._entities(client, qids, "labels|claims")).values():
                info = {"website": next((u for u in (normalize_url(w) for w in wd._claim_ids(e, "P856")) if u), ""),
                        "label": wd_label(e) or ""}
                for raw in wd._claim_ids(e, "P5531"):
                    if raw.isdigit() and int(raw) not in found:
                        found[int(raw)] = info
        return found

    async def discover(self, spec: ExtractionSpec) -> list[DiscoveryResult]:
        d = spec.discovery
        if not self.covers(spec):
            raise DiscoveryError("SEC EDGAR only lists US-listed companies; skipped for this region")
        if not d.industry:
            raise DiscoveryError("SEC EDGAR discovery needs an industry")
        term = d.industry.lower().strip()
        if term in TECH_NICHES or any(w in TECH_NICHES for w in re.findall(r"[a-z]+", term)):
            raise DiscoveryError(f"SEC's industry codes cannot tell which companies are in {d.industry!r} "
                                 "(they predate it); skipped")
        if not index_ready():
            raise DiscoveryError("the SEC company list has not been downloaded yet. Run "
                                 "`python -m app.cli refresh-sec` once (about 30 minutes); skipped")
        with session_scope(bypass=True) as db:
            descriptions = dict(db.execute(select(SecCompany.sic, SecCompany.sic_description).where(
                SecCompany.sic.is_not(None)).distinct()).all())
            codes = sic_codes_for(d.industry, descriptions)
            if not codes:
                raise DiscoveryError(f"no SEC industry code matches {d.industry!r}")
            q = select(SecCompany).where(SecCompany.sic.in_(codes)).order_by(SecCompany.rank)
            if d.countries or d.region:
                # The state check also catches foreign filers saved before `foreign` was fixed.
                q = q.where(SecCompany.foreign.is_(False), SecCompany.state.in_(US_STATES))
            companies = db.execute(q.limit(d.max_results * 4)).scalars().all()
            db.expunge_all()
        if not companies:
            raise DiscoveryError("SEC EDGAR lists no companies for this industry")
        client = self.client or httpx.AsyncClient(timeout=30, headers={"User-Agent": get_settings().user_agent})
        try:
            try:
                wiki = await self.from_wikidata(client, [c.cik for c in companies])
            except httpx.HTTPError as exc:
                wiki = {}
                self.notes.append(f"sec_edgar: Wikidata website lookup failed ({type(exc).__name__}); "
                                  "only companies with a website in SEC's own data were used")
        finally:
            if self.client is None:
                await client.aclose()
        out: list[DiscoveryResult] = []
        seen: set[str] = set()
        missing = 0
        for c in companies:
            info = wiki.get(c.cik)
            site = c.website or (info or {}).get("website", "")
            label = (info or {}).get("label", "")
            if not site:
                missing += 1
                continue
            domain = registered_domain(site) or site
            if domain in seen:
                continue
            seen.add(domain)
            source = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={c.cik:010d}"
            hint = {"company_name": label or None,
                    # "Basel, V8": SEC's code for a foreign country means nothing to a reader, so the city alone.
                    "headquarters": ", ".join(x for x in (c.city, c.state if c.state in US_STATES or c.foreign
                                                          and len(c.state) > 2 else "") if x) or None,
                    "country": "United States" if not c.foreign and c.state in US_STATES else None,
                    "industry": c.sic_description or None, "website_url": site, "_source": source}
            out.append(DiscoveryResult(site, "sec_edgar", {k: v for k, v in hint.items() if v}, referrer=source))
            if len(out) >= d.max_results:
                break
        if missing:
            self.notes.append(f"sec_edgar: {missing} matching companies have no known website and were left out")
        if not out:
            raise DiscoveryError("none of the matching SEC companies has a known website")
        return out
