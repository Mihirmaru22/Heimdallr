"""Two-signal linking of UK Companies House, India CIN, and GLEIF entities to canonical domains.

Links are never created on normalized company name alone:
1. Exact registration number extracted from crawled homepage/contact/security pages (UK Co No or Indian CIN).
2. Normalized legal name_key + normalized postcode agreement (where unique to 1 legal entity).
3. Authoritative Wikidata LEI (P1278) claim on linked entity QIDs -> kb.gleif_company.
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path

import httpx

from app.kb.companies_house import name_key
from app.kb.sp500 import WIKIDATA_SPARQL

UK_REG_RE = re.compile(
    r"(?:(?:company|co\.?)(?:\s+reg(?:istration)?\.?)?\s+(?:no\.?|number)|registered\s+(?:company\s+)?(?:no\.?|number)|"
    r"registered\s+in\s+(?:england(?:\s+and\s+wales)?|scotland|wales|northern\s+ireland|the\s+uk|uk)"
    r"[^0-9A-Z]{0,35}(?:company\s+)?(?:no\.?|number|with\s+number|registration)?)\s*[:.#-]?\s*"
    r"((?:SC|NI|OC|SO|NC|R0)\d{6}|\d{7,8})\b",
    re.I,
)
CIN_RE = re.compile(r"\b([LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6})\b")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS kb.domain_register_link (
    domain text NOT NULL,
    registry text NOT NULL,       -- uk_company, gleif, india_cin
    reg_id text NOT NULL,         -- UK company_number, LEI, or Indian CIN
    link_method text NOT NULL,    -- reg_number_on_site, name_key+postcode, wikidata_lei
    evidence text,
    source_url text NOT NULL,
    linked_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (domain, registry, reg_id)
);
CREATE INDEX IF NOT EXISTS domain_register_link_reg_idx ON kb.domain_register_link (registry, reg_id);
"""


def norm_uk_number(raw: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9]", "", raw or "").upper()
    return clean.zfill(8) if clean.isdigit() and 6 <= len(clean) <= 8 else (clean if len(clean) == 8 else "")


def norm_postcode(raw: str | None) -> str:
    clean = re.sub(r"[^A-Z0-9]", "", (raw or "").upper())
    return clean if len(clean) >= 4 else ""


def extract_register_ids(text: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Return ([(uk_number, snippet)], [(cin, snippet)]) found explicitly in page text."""
    uk_out: list[tuple[str, str]] = []
    seen_uk: set[str] = set()
    for m in UK_REG_RE.finditer(text or ""):
        num = norm_uk_number(m.group(1))
        if num and num not in seen_uk:
            seen_uk.add(num)
            uk_out.append((num, " ".join(m.group(0).split())[:140]))

    cin_out: list[tuple[str, str]] = []
    seen_cin: set[str] = set()
    for m in CIN_RE.finditer(text or ""):
        cin = m.group(1).upper()
        if cin not in seen_cin:
            seen_cin.add(cin)
            cin_out.append((cin, cin))
    return uk_out, cin_out


def parse_wikidata_lei_rows(bindings: Sequence[dict]) -> dict[str, str]:
    """Map Wikidata company QID -> 20-char LEI (P1278)."""
    out: dict[str, str] = {}
    for row in bindings:
        qid = (row.get("item", {}).get("value") or "").rsplit("/", 1)[-1]
        lei = re.sub(r"[^A-Z0-9]", "", (row.get("lei", {}).get("value") or "").upper())
        if qid.startswith("Q") and len(lei) == 20 and qid not in out:
            out[qid] = lei
    return out


def _save_links(conn, rows: Sequence[tuple]) -> int:
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO kb.domain_register_link (domain, registry, reg_id, link_method, evidence, source_url)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (domain, registry, reg_id) DO UPDATE SET
                   link_method = EXCLUDED.link_method,
                   evidence = EXCLUDED.evidence,
                   source_url = EXCLUDED.source_url,
                   linked_at = now()""",
            rows,
        )
    return len(rows)


def link_from_crawled_pages(conn) -> dict[str, int]:
    """Extract explicit UK company numbers & Indian CINs from homepage & subpage text and validate vs registers."""
    conn.execute(SCHEMA_SQL)
    uk_cands: dict[tuple[str, str], tuple[str, str]] = {}
    cin_cands: dict[tuple[str, str], tuple[str, str]] = {}

    for dom, url, text in conn.execute(
        "SELECT domain, url, text FROM kb.homepage WHERE found AND text IS NOT NULL"
    ).fetchall():
        uk_hits, cin_hits = extract_register_ids(text)
        for num, ev in uk_hits:
            uk_cands.setdefault((dom, num), (ev, url or f"https://{dom}/"))
        for cin, ev in cin_hits:
            cin_cands.setdefault((dom, cin), (ev, url or f"https://{dom}/"))

    if conn.execute("SELECT to_regclass('kb.company_page')").fetchone()[0]:
        for dom, url, text in conn.execute(
            "SELECT domain, url, text FROM kb.company_page WHERE text IS NOT NULL"
        ).fetchall():
            uk_hits, cin_hits = extract_register_ids(text)
            for num, ev in uk_hits:
                uk_cands.setdefault((dom, num), (ev, url))
            for cin, ev in cin_hits:
                cin_cands.setdefault((dom, cin), (ev, url))

    # Validate UK numbers strictly against kb.uk_company so random 8-digit numbers never enter links.
    uk_nums = sorted({num for _, num in uk_cands})
    has_uk = bool(conn.execute("SELECT to_regclass('kb.uk_company')").fetchone()[0])
    valid_uk = (
        {
            r[0]
            for r in conn.execute(
                "SELECT company_number FROM kb.uk_company WHERE company_number = ANY(%s)", (uk_nums,)
            ).fetchall()
        }
        if uk_nums and has_uk
        else set()
    )
    uk_rows = [
        (dom, "uk_company", num, "reg_number_on_site", ev, url)
        for (dom, num), (ev, url) in uk_cands.items()
        if num in valid_uk
    ]
    cin_rows = [
        (dom, "india_cin", cin, "reg_number_on_site", ev, url)
        for (dom, cin), (ev, url) in cin_cands.items()
    ]
    return {
        "uk_from_pages": _save_links(conn, uk_rows),
        "cin_from_pages": _save_links(conn, cin_rows),
    }


def link_via_name_and_postcode(conn) -> dict[str, int]:
    """Two-signal (name_key + normalized postcode) exact unique match via indexed register lookups."""
    conn.execute(SCHEMA_SQL)
    counts = Counter()

    # Gather distinct (domain, clean_pc, src_url) across existing branch addresses (~42k domains).
    br_rows = conn.execute(
        "SELECT DISTINCT ON (domain, regexp_replace(upper(postal_code), '[^A-Z0-9]', '', 'g')) "
        "domain, regexp_replace(upper(postal_code), '[^A-Z0-9]', '', 'g') AS pc, "
        "coalesce(url, 'https://' || domain || '/') "
        "FROM kb.company_branch "
        "WHERE postal_code IS NOT NULL AND length(regexp_replace(upper(postal_code), '[^A-Z0-9]', '', 'g')) >= 4"
    ).fetchall()
    dom_pcs: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for dom, pc, u in br_rows:
        dom_pcs[dom].append((pc, u))
    if not dom_pcs:
        return {}

    dom_list = sorted(dom_pcs)
    pdl_rows = conn.execute(
        "SELECT DISTINCT domain, name, iso2 FROM kb.pdl_company "
        "WHERE domain = ANY(%s) AND domain_rows <= 20 AND name IS NOT NULL",
        (dom_list,),
    ).fetchall()
    # Map (domain) -> set of (nk, iso2)
    dom_names: dict[str, set[tuple[str, str]]] = defaultdict(set)
    all_nks: set[str] = set()
    for dom, raw_name, iso2 in pdl_rows:
        nk = name_key(raw_name)
        if len(nk) >= 4:
            dom_names[dom].add((nk, iso2 or ""))
            all_nks.add(nk)
    # Also include official SEC company names for all linked SEC domains.
    if conn.execute("SELECT to_regclass('kb.sec_company')").fetchone()[0]:
        for dom, sec_nk in conn.execute(
            "SELECT DISTINCT domain, name_key FROM kb.sec_company WHERE domain = ANY(%s) AND name_key IS NOT NULL",
            (dom_list,),
        ).fetchall():
            if len(sec_nk) >= 4:
                dom_names[dom].add((sec_nk, "US"))
                all_nks.add(sec_nk)
    nk_list = sorted(all_nks)
    if not nk_list:
        return {}

    # 1. UK Companies House lookup via indexed name_key.
    if conn.execute("SELECT to_regclass('kb.uk_company')").fetchone()[0]:
        uk_buckets: dict[tuple[str, str], list[str]] = defaultdict(list)
        for cnum, uk_nk, uk_pc in conn.execute(
            "SELECT company_number, name_key, postcode FROM kb.uk_company "
            "WHERE name_key = ANY(%s) AND postcode IS NOT NULL",
            (nk_list,),
        ).fetchall():
            cpc = norm_postcode(uk_pc)
            if len(cpc) >= 5:
                uk_buckets[(uk_nk, cpc)].append(cnum)
        uk_rows = []
        for dom, pcs in dom_pcs.items():
            for nk, _iso in dom_names.get(dom, ()):
                for pc, u in pcs:
                    hits = uk_buckets.get((nk, pc), ())
                    if len(hits) == 1:
                        uk_rows.append((dom, "uk_company", hits[0], "name_key+postcode", f"{nk} @ {pc}", u))
        counts["uk_postcode"] = _save_links(conn, uk_rows)

    # 2. GLEIF lookup via indexed name_key.
    if conn.execute("SELECT to_regclass('kb.gleif_company')").fetchone()[0]:
        gl_buckets: dict[tuple[str, str, str], list[str]] = defaultdict(list)
        for lei, gl_nk, gl_iso, gl_pc in conn.execute(
            "SELECT lei, name_key, iso2, postcode FROM kb.gleif_company "
            "WHERE name_key = ANY(%s) AND postcode IS NOT NULL AND iso2 IS NOT NULL",
            (nk_list,),
        ).fetchall():
            cpc = norm_postcode(gl_pc)
            if cpc:
                gl_buckets[(gl_nk, gl_iso, cpc)].append(lei)
        gl_rows = []
        for dom, pcs in dom_pcs.items():
            for nk, iso in dom_names.get(dom, ()):
                if not iso:
                    continue
                for pc, u in pcs:
                    hits = gl_buckets.get((nk, iso, pc), ())
                    if len(hits) == 1:
                        gl_rows.append((dom, "gleif", hits[0], "name_key+postcode", f"{nk} @ {pc}", u))
        counts["gleif_postcode"] = _save_links(conn, gl_rows)

    return dict(counts)


def link_gleif_via_wikidata(conn, data_dir: Path | None = None,
                            user_agent: str = "HeimdallrKB/1.0", refresh: bool = False) -> int:
    """Resolve LEIs (P1278) for linked Wikidata entity QIDs and verify against kb.gleif_company."""
    conn.execute(SCHEMA_SQL)
    qid_to_dom: dict[str, str] = {}
    for tbl in ("kb.sp500_member", "kb.sec_wikidata"):
        if conn.execute("SELECT to_regclass(%s)", (tbl,)).fetchone()[0]:
            for dom, qid in conn.execute(
                f"SELECT domain, wikidata_qid FROM {tbl} WHERE domain IS NOT NULL AND wikidata_qid IS NOT NULL"  # noqa: S608
            ).fetchall():
                qid_to_dom.setdefault(qid, dom)
    if not qid_to_dom:
        return 0

    cache_path = (data_dir / "sec" / "wikidata_lei_cache.json") if data_dir else None
    if cache_path and cache_path.is_file() and not refresh:
        qid_lei = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        qids = sorted(qid_to_dom)
        bindings: list[dict] = []
        headers = {"User-Agent": f"{user_agent} (mailto:research@heimdallr.local)"}
        with httpx.Client(timeout=60, headers=headers) as client:
            for i in range(0, len(qids), 250):
                vals = " ".join(f"wd:{q}" for q in qids[i:i + 250])
                q = f"SELECT ?item ?lei WHERE {{ VALUES ?item {{ {vals} }} ?item wdt:P1278 ?lei . }}"
                for attempt in range(3):
                    resp = client.post(
                        WIKIDATA_SPARQL, data={"query": q},
                        headers={"Accept": "application/sparql-results+json"},
                    )
                    if resp.status_code in (429, 502, 503, 504) and attempt < 2:
                        time.sleep(2.0 * (attempt + 1))
                        continue
                    resp.raise_for_status()
                    bindings.extend(resp.json().get("results", {}).get("bindings", []))
                    break
                if i + 250 < len(qids):
                    time.sleep(0.8)
        qid_lei = parse_wikidata_lei_rows(bindings)
        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(qid_lei, indent=2), encoding="utf-8")

    leis = sorted(set(qid_lei.values()))
    has_gl = bool(conn.execute("SELECT to_regclass('kb.gleif_company')").fetchone()[0])
    valid_lei = (
        {r[0] for r in conn.execute("SELECT lei FROM kb.gleif_company WHERE lei = ANY(%s)", (leis,)).fetchall()}
        if leis and has_gl
        else set()
    )
    rows = [
        (qid_to_dom[qid], "gleif", lei, "wikidata_lei", f"P1278={lei}", f"https://www.wikidata.org/wiki/{qid}")
        for qid, lei in qid_lei.items()
        if lei in valid_lei and qid in qid_to_dom
    ]
    return _save_links(conn, rows)
