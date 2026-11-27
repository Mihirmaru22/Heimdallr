"""Compliant company leadership / people layer (kb.company_person): Wikidata first + strict provenance."""

from __future__ import annotations

import asyncio
import json
import time
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from pathlib import Path

import httpx

from app.kb.sp500 import WIKIDATA_SPARQL

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS kb.company_person (
    id bigserial PRIMARY KEY,
    domain text,
    cik integer,
    company_number text,
    full_name text NOT NULL,
    raw_role text NOT NULL,
    person_qid text,
    officer_id text,
    start_date text,
    end_date text,
    source text NOT NULL,
    source_url text NOT NULL,
    seen_at timestamptz NOT NULL DEFAULT now(),
    suppressed boolean NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS company_person_domain_idx ON kb.company_person (domain);
CREATE INDEX IF NOT EXISTS company_person_cik_idx ON kb.company_person (cik);
CREATE INDEX IF NOT EXISTS company_person_qid_idx ON kb.company_person (person_qid);
"""

_ROLE_LABELS = {
    "P169": "chief executive officer",
    "P112": "founder",
    "P488": "chairperson",
}


def parse_wikidata_leadership_rows(
    bindings: Sequence[dict], qid_to_meta: dict[str, tuple[str | None, int | None]]
) -> list[dict]:
    """Parse Wikidata SPARQL P169/P112/P488 rows into normalized kb.company_person records."""
    dedup: dict[tuple[str, str, str], dict] = {}
    for row in bindings:
        item_url = row.get("item", {}).get("value", "")
        comp_qid = item_url.rsplit("/", 1)[-1]
        if comp_qid not in qid_to_meta:
            continue
        domain, cik = qid_to_meta[comp_qid]
        person_url = row.get("person", {}).get("value", "")
        person_qid = person_url.rsplit("/", 1)[-1]
        if not (person_qid.startswith("Q") and person_qid[1:].isdigit()):
            continue
        full_name = (row.get("personLabel", {}).get("value") or "").strip()
        if not full_name or (full_name.startswith("Q") and full_name[1:].isdigit()):
            continue
        prop = (row.get("prop", {}).get("value") or "").rsplit("/", 1)[-1]
        raw_role = _ROLE_LABELS.get(prop)
        if not raw_role:
            continue
        start = (row.get("start", {}).get("value") or "")[:10] or None
        end = (row.get("end", {}).get("value") or "")[:10] or None
        key = (comp_qid, person_qid, raw_role)
        if key not in dedup:
            dedup[key] = {
                "domain": domain,
                "cik": cik,
                "company_number": None,
                "full_name": full_name[:200],
                "raw_role": raw_role,
                "person_qid": person_qid,
                "officer_id": None,
                "start_date": start,
                "end_date": end,
                "source": "wikidata",
                "source_url": f"https://www.wikidata.org/wiki/{comp_qid}",
            }
    return list(dedup.values())


def load_wikidata_people(conn, data_dir: Path | None = None, user_agent: str = "HeimdallrKB/1.0",
                         refresh: bool = False) -> int:
    """Populate kb.company_person from Wikidata P169 (CEO), P112 (founder), P488 (chair) for linked QIDs."""
    conn.execute(SCHEMA_SQL)
    qid_to_meta: dict[str, tuple[str | None, int | None]] = {}
    for tbl in ("kb.sp500_member", "kb.sec_wikidata"):
        if conn.execute("SELECT to_regclass(%s)", (tbl,)).fetchone()[0]:
            for dom, cik, qid in conn.execute(
                f"SELECT domain, cik, wikidata_qid FROM {tbl} WHERE wikidata_qid IS NOT NULL"  # noqa: S608
            ).fetchall():
                qid_to_meta.setdefault(qid, (dom, cik))
    if not qid_to_meta:
        return 0

    cache_path = (data_dir / "sp500" / "wikidata_people.json") if data_dir else None
    if cache_path and cache_path.is_file() and not refresh:
        records = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        qids = sorted(qid_to_meta)
        bindings: list[dict] = []
        headers = {"User-Agent": f"{user_agent} (mailto:research@heimdallr.local)"}
        with httpx.Client(timeout=60, headers=headers) as client:
            for i in range(0, len(qids), 150):
                vals = " ".join(f"wd:{q}" for q in qids[i:i + 150])
                query = (
                    "SELECT ?item ?prop ?person ?personLabel ?start ?end WHERE {"
                    f" VALUES ?item {{ {vals} }}"
                    ' { ?item p:P169 ?st . ?st ps:P169 ?person . BIND("P169" AS ?prop) }'
                    ' UNION { ?item p:P112 ?st . ?st ps:P112 ?person . BIND("P112" AS ?prop) }'
                    ' UNION { ?item p:P488 ?st . ?st ps:P488 ?person . BIND("P488" AS ?prop) }'
                    " OPTIONAL { ?st pq:P580 ?start }"
                    " OPTIONAL { ?st pq:P582 ?end }"
                    ' SERVICE wikibase:label { bd:serviceParam wikibase:language "en". } }'
                )
                for attempt in range(3):
                    resp = client.post(
                        WIKIDATA_SPARQL, data={"query": query},
                        headers={"Accept": "application/sparql-results+json"},
                    )
                    if resp.status_code in (429, 502, 503, 504) and attempt < 2:
                        time.sleep(2.0 * (attempt + 1))
                        continue
                    resp.raise_for_status()
                    bindings.extend(resp.json().get("results", {}).get("bindings", []))
                    break
                if i + 150 < len(qids):
                    time.sleep(1.0)
        records = parse_wikidata_leadership_rows(bindings, qid_to_meta)
        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(records, indent=2), encoding="utf-8")

    with conn.cursor() as cur:
        cur.execute("DELETE FROM kb.company_person WHERE source = 'wikidata'")
        cur.executemany(
            """INSERT INTO kb.company_person (
                   domain, cik, company_number, full_name, raw_role,
                   person_qid, officer_id, start_date, end_date, source, source_url
               ) VALUES (
                   %(domain)s, %(cik)s, %(company_number)s, %(full_name)s, %(raw_role)s,
                   %(person_qid)s, %(officer_id)s, %(start_date)s, %(end_date)s, %(source)s, %(source_url)s
               )""",
            records,
        )
    return len(records)


def parse_form4_xml(xml_text: str, domain: str | None, cik: int, filing_date: str | None,
                    source_url: str) -> list[dict]:
    """Parse reportingOwner officers and directors from one SEC Form 4 XML filing."""
    if not xml_text or "<" not in xml_text:
        return []
    try:
        root = ET.fromstring(xml_text.encode("utf-8", "replace"))  # noqa: S314 - official SEC EDGAR XML
    except ET.ParseError:
        return []
    out: list[dict] = []
    for owner in root.findall(".//reportingOwner"):
        oid_el = owner.find("reportingOwnerId")
        rel_el = owner.find("reportingOwnerRelationship")
        if oid_el is None or rel_el is None:
            continue
        name = " ".join((oid_el.findtext("rptOwnerName") or "").split()).strip()
        if not name or len(name) < 3:
            continue
        rpt_cik = (oid_el.findtext("rptOwnerCik") or "").strip()
        is_off = (rel_el.findtext("isOfficer") or "").strip().lower() in ("1", "true")
        is_dir = (rel_el.findtext("isDirector") or "").strip().lower() in ("1", "true")
        title = " ".join((rel_el.findtext("officerTitle") or "").split()).strip()
        if is_off and title:
            role = title[:120]
        elif is_off:
            role = "officer"
        elif is_dir:
            role = "director"
        else:
            continue
        out.append({
            "domain": domain,
            "cik": cik,
            "company_number": None,
            "full_name": name[:200],
            "raw_role": role,
            "person_qid": None,
            "officer_id": f"sec:{int(rpt_cik)}" if rpt_cik.isdigit() else None,
            "start_date": filing_date,
            "end_date": None,
            "source": "sec_form4",
            "source_url": source_url,
        })
    return out


async def _fetch_sec_officers_batch(ciks_doms: list[tuple[int, str | None]],
                                    user_agent: str) -> list[dict]:
    headers = {"User-Agent": f"{user_agent} (mailto:research@heimdallr.local)"}
    slots = asyncio.Semaphore(8)
    pace = asyncio.Lock()
    out: list[dict] = []

    async def get_limited(client: httpx.AsyncClient, url: str) -> httpx.Response | None:
        async with slots:
            async with pace:
                await asyncio.sleep(0.11)  # stay cleanly under SEC 10 req/s limit
            try:
                resp = await client.get(url)
                return resp if resp.status_code == 200 else None
            except httpx.HTTPError:
                return None

    async def one_cik(client: httpx.AsyncClient, cik: int, dom: str | None) -> None:
        sub = await get_limited(client, f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
        if sub is None:
            return
        try:
            recent = sub.json().get("filings", {}).get("recent", {})
        except ValueError:
            return
        forms = recent.get("form") or []
        acns = recent.get("accessionNumber") or []
        docs = recent.get("primaryDocument") or []
        fdates = recent.get("filingDate") or []
        picked = 0
        for fm, acn, doc, fdt in zip(forms, acns, docs, fdates, strict=False):
            if fm not in ("4", "4/A"):
                continue
            fname = str(doc or "").rsplit("/", 1)[-1]
            if not fname.lower().endswith(".xml"):
                continue
            xml_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{str(acn).replace('-', '')}/{fname}"
            resp = await get_limited(client, xml_url)
            if resp is not None:
                out.extend(parse_form4_xml(resp.text, dom, cik, str(fdt)[:10] or None, xml_url))
            picked += 1
            if picked >= 4:
                break

    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=6.0), headers=headers) as client:
        for i in range(0, len(ciks_doms), 25):
            await asyncio.gather(*(one_cik(client, c, d) for c, d in ciks_doms[i:i + 25]))
    return out


def load_sec_officers(conn, limit: int = 550, user_agent: str = "HeimdallrKB/1.0") -> int:
    """Populate named executive officers & directors from latest SEC Form 4 filings for linked issuers."""
    conn.execute(SCHEMA_SQL)
    rows = conn.execute(
        """SELECT DISTINCT ON (s.cik) s.cik, s.domain
           FROM kb.sec_company s
           LEFT JOIN kb.sp500_member m ON m.cik = s.cik
           LEFT JOIN kb.sec_financial_latest f ON f.cik = s.cik
           WHERE s.domain IS NOT NULL AND s.cik IS NOT NULL
             AND NOT EXISTS (
                 SELECT 1 FROM kb.company_person p WHERE p.cik = s.cik AND p.source = 'sec_form4'
             )
           ORDER BY s.cik, (m.symbol IS NOT NULL) DESC, f.annual_revenue DESC NULLS LAST"""
    ).fetchall()
    # Sort prioritized companies cleanly before applying limit.
    if limit:
        prio = conn.execute(
            """SELECT cik, domain FROM (
                   SELECT DISTINCT ON (s.cik) s.cik, s.domain,
                          (m.symbol IS NOT NULL) AS is_sp, f.annual_revenue AS rev
                   FROM kb.sec_company s
                   LEFT JOIN kb.sp500_member m ON m.cik = s.cik
                   LEFT JOIN kb.sec_financial_latest f ON f.cik = s.cik
                   WHERE s.domain IS NOT NULL AND s.cik IS NOT NULL
                     AND NOT EXISTS (
                         SELECT 1 FROM kb.company_person p WHERE p.cik = s.cik AND p.source = 'sec_form4'
                     )
               ) t ORDER BY is_sp DESC, rev DESC NULLS LAST, cik LIMIT %s""",
            (limit,),
        ).fetchall()
        rows = prio
    if not rows:
        return 0
    raw_records = asyncio.run(_fetch_sec_officers_batch([(int(c), d) for c, d in rows], user_agent=user_agent))
    dedup: dict[tuple[int, str, str], dict] = {}
    for rec in raw_records:
        key = (rec["cik"], rec["officer_id"] or rec["full_name"], rec["raw_role"])
        prev = dedup.get(key)
        if prev is None or (rec["start_date"] or "") > (prev["start_date"] or ""):
            dedup[key] = rec
    clean = list(dedup.values())
    if clean:
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO kb.company_person (
                       domain, cik, company_number, full_name, raw_role,
                       person_qid, officer_id, start_date, end_date, source, source_url
                   ) VALUES (
                       %(domain)s, %(cik)s, %(company_number)s, %(full_name)s, %(raw_role)s,
                       %(person_qid)s, %(officer_id)s, %(start_date)s, %(end_date)s, %(source)s, %(source_url)s
                   )""",
                clean,
            )
    return len(clean)
