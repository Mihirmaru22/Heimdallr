"""Compliant company leadership / people layer (kb.company_person): Wikidata first + strict provenance."""

from __future__ import annotations

import json
import time
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
