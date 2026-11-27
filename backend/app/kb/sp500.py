"""S&P 500 constituent linker and multi-source company profile enricher into Brahman."""

from __future__ import annotations

import asyncio
import csv
import json
import time
from collections import Counter
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from app.crawl.urlnorm import homepage, normalize_url
from app.kb.companies_house import name_key
from app.kb.pdl import _website_domain

DATA = Path(__file__).parent / "data"
CONSTITUENTS_CSV = DATA / "sp500_constituents.csv"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"

# Dual-class S&P 500 shares whose Class A/C sibling holds the SEC company_tickers entry.
CLASS_B_CIK_TICKER: dict[str, str] = {"GOOG": "GOOGL", "FOX": "FOXA", "NWS": "NWSA"}

# Confirmed official corporate domains for constituents lacking P856 on Wikidata or recently rebranded.
OVERRIDES: dict[str, str] = {
    "PYPL": "https://www.paypal.com/",
    "NCLH": "https://www.nclhltd.com/",
    "VYLR": "https://www.vylor.com/",
    "TT": "https://www.tranetechnologies.com/",
    "EXE": "https://www.expandenergy.com/",
    "DOC": "https://www.healthpeak.com/",
    "GL": "https://www.globelifeinsurance.com/",
}

BAD_DOMAINS = {
    "sec.gov", "wikipedia.org", "wikidata.org", "wikimedia.org", "linkedin.com",
    "facebook.com", "twitter.com", "x.com", "instagram.com", "youtube.com",
    "bloomberg.com", "reuters.com", "yahoo.com", "google.com", "nyse.com", "nasdaq.com",
    "com.jp", "co.jp", "com.cn", "co.uk", "com.au",
}

_LOW_VALUE_HOST_WORDS = ("investor", "investors", "foundation", "charity", "zerowaste", "advisors", "careers")
_LOW_VALUE_HOST_PREFIXES = ("ir.", "investor.", "investors.")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS kb.sp500_member (
    symbol text PRIMARY KEY,
    rank integer NOT NULL,
    name text NOT NULL,
    cik integer,
    website text,
    domain text,
    wikidata_qid text,
    wikidata_description text,
    wikidata_industry text,
    employees integer,
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS sp500_member_domain_idx ON kb.sp500_member (domain);
CREATE INDEX IF NOT EXISTS sp500_member_cik_idx ON kb.sp500_member (cik);
"""


def load_constituents(path: Path = CONSTITUENTS_CSV) -> list[dict]:
    """Load canonical S&P 500 constituents (rank, symbol, name) from package CSV."""
    with open(path, newline="", encoding="utf-8") as f:
        return [
            {"rank": int(r["rank"]), "symbol": r["symbol"].strip().upper(), "name": r["name"].strip()}
            for r in csv.DictReader(f)
        ]


def pick_primary_website(urls: Sequence[str], company_name: str,
                         known_domains: set[str] | None = None) -> tuple[str, str]:
    """Choose the primary corporate (website, domain) from Wikidata P856 candidates."""
    known = known_domains or set()
    stop = {
        "inc", "corp", "corporation", "company", "co", "holdings",
        "group", "ltd", "plc", "class", "common", "stock",
    }
    tokens = [w for w in name_key(company_name).split() if len(w) >= 3 and w not in stop]

    scored: list[tuple[tuple, str, str]] = []
    seen_urls: set[str] = set()
    for raw in urls:
        norm = normalize_url(raw if "://" in raw else f"https://{raw}")
        if not norm or norm in seen_urls:
            continue
        seen_urls.add(norm)
        dom = _website_domain(norm)
        if not dom or (dom in BAD_DOMAINS and not any(t in dom.split(".", 1)[0] for t in tokens)):
            continue
        parts = urlsplit(norm)
        host = (parts.hostname or "").lower()
        stem = dom.split(".", 1)[0]
        tld = "." + dom.split(".", 1)[1] if "." in dom else ""

        non_sub = 0 if (
            host.startswith(_LOW_VALUE_HOST_PREFIXES)
            or any(w in host for w in _LOW_VALUE_HOST_WORDS)
        ) else 1
        root_host = 1 if host in (dom, f"www.{dom}") else 0
        tld_score = 3 if tld == ".com" else (2 if tld in {".org", ".io", ".co", ".net", ".ai", ".xyz"} else 0)
        name_score = 3 if tokens and tokens[0] in stem else (2 if any(t in stem for t in tokens) else 0)
        known_score = 1 if dom in known else 0
        https_score = 1 if parts.scheme == "https" else 0
        root_score = 1 if parts.path in ("", "/") else 0
        score = (non_sub, tld_score, name_score, root_host, known_score, https_score, root_score, -len(dom), -len(norm))
        clean_url = f"{parts.scheme}://{parts.netloc}/" if parts.path in ("", "/") else homepage(norm)
        scored.append((score, clean_url, dom))

    if not scored:
        return "", ""
    _, best_url, best_dom = max(scored, key=lambda x: x[0])
    # If all P856 URLs on the winning domain point to regional paths (e.g. apple.com/az/), use root.
    if len(urlsplit(best_url).path.strip("/")) == 2:
        parts = urlsplit(best_url)
        best_url = f"{parts.scheme}://{parts.netloc}/"
    return best_url, best_dom


def parse_sparql_cik_rows(bindings: Sequence[dict]) -> dict[int, dict]:
    """Aggregate Wikidata P5531 SPARQL JSON bindings into cik -> company facts."""
    out: dict[int, dict] = {}
    for row in bindings:
        raw_cik = row.get("cik", {}).get("value", "")
        if not raw_cik.isdigit():
            continue
        cik = int(raw_cik)
        rec = out.setdefault(cik, {
            "qid": "",
            "label": "",
            "description": "",
            "websites": [],
            "industries": [],
            "employees": None,
        })
        item_url = row.get("item", {}).get("value", "")
        if not rec["qid"] and item_url.rsplit("/", 1)[-1].startswith("Q"):
            rec["qid"] = item_url.rsplit("/", 1)[-1]
        for key, dst in (("itemLabel", "label"), ("desc", "description")):
            val = row.get(key, {}).get("value", "").strip()
            if val and not rec[dst] and not (dst == "label" and val.startswith("Q") and val[1:].isdigit()):
                rec[dst] = val
        site = row.get("website", {}).get("value", "").strip()
        if site and site not in rec["websites"]:
            rec["websites"].append(site)
        ind = row.get("industryLabel", {}).get("value", "").strip()
        if ind and not (ind.startswith("Q") and ind[1:].isdigit()) and ind not in rec["industries"]:
            rec["industries"].append(ind)
        emp_raw = row.get("emp", {}).get("value", "")
        if rec["employees"] is None and emp_raw.isdigit():
            rec["employees"] = int(emp_raw)
    return out


def parse_sparql_ticker_rows(bindings: Sequence[dict]) -> dict[str, list[dict]]:
    """Aggregate Wikidata NYSE/NASDAQ P414/P249 SPARQL JSON bindings into ticker -> candidates."""
    out: dict[str, list[dict]] = {}
    for row in bindings:
        ticker = row.get("ticker", {}).get("value", "").strip().upper()
        site = row.get("website", {}).get("value", "").strip()
        if not ticker or not site:
            continue
        item_url = row.get("item", {}).get("value", "")
        qid = item_url.rsplit("/", 1)[-1] if item_url.rsplit("/", 1)[-1].startswith("Q") else ""
        out.setdefault(ticker, []).append({
            "qid": qid,
            "website": site,
            "description": row.get("desc", {}).get("value", "").strip(),
            "industry": row.get("industryLabel", {}).get("value", "").strip(),
        })
    return out


def _sparql_post(client: httpx.Client, query: str) -> list[dict]:
    for attempt in range(3):
        resp = client.post(
            WIKIDATA_SPARQL,
            data={"query": query},
            headers={"Accept": "application/sparql-results+json"},
        )
        if resp.status_code in (429, 502, 503, 504) and attempt < 2:
            time.sleep(2.0 * (attempt + 1))
            continue
        resp.raise_for_status()
        return resp.json().get("results", {}).get("bindings", [])
    return []


def fetch_wikidata(ciks: Sequence[int], user_agent: str, cache_path: Path | None = None,
                   refresh: bool = False) -> tuple[dict[int, dict], dict[str, list[dict]]]:
    """Fetch Wikidata P5531 CIK records and NYSE/NASDAQ P414/P249 fallback records, with local cache."""
    if cache_path and cache_path.is_file() and not refresh:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        return {int(k): v for k, v in cached["by_cik"].items()}, cached["by_ticker"]

    by_cik: dict[int, dict] = {}
    headers = {"User-Agent": f"{user_agent} (mailto:research@heimdallr.local)"}
    with httpx.Client(timeout=60, headers=headers) as client:
        for i in range(0, len(ciks), 200):
            chunk = ciks[i:i + 200]
            vals = " ".join(f'"{cik:010d}"' for cik in chunk)
            q_cik = (
                "SELECT ?cik ?item ?itemLabel ?desc ?website ?industryLabel ?emp WHERE {"
                f" VALUES ?cik {{ {vals} }} ?item wdt:P5531 ?cik ."
                " OPTIONAL { ?item wdt:P856 ?website }"
                ' OPTIONAL { ?item schema:description ?desc . FILTER(LANG(?desc) = "en") }'
                " OPTIONAL { ?item wdt:P452 ?industry }"
                " OPTIONAL { ?item wdt:P1128 ?emp }"
                ' SERVICE wikibase:label { bd:serviceParam wikibase:language "en". } }'
            )
            by_cik.update(parse_sparql_cik_rows(_sparql_post(client, q_cik)))
            if i + 200 < len(ciks):
                time.sleep(1.0)

        q_ex = (
            "SELECT ?ticker ?item ?website WHERE {"
            " VALUES ?ex { wd:Q13677 wd:Q82059 }"
            " ?item p:P414 ?st . ?st ps:P414 ?ex ; pq:P249 ?ticker ."
            " ?item wdt:P856 ?website . }"
        )
        by_ticker = parse_sparql_ticker_rows(_sparql_post(client, q_ex))

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps({"by_cik": {str(k): v for k, v in by_cik.items()}, "by_ticker": by_ticker}, indent=2),
            encoding="utf-8",
        )
    return by_cik, by_ticker


def sec_lookup_map(conn, symbols: Sequence[str]) -> dict[str, tuple[int, str]]:
    """Map S&P 500 symbol -> (cik, official_sec_name) from kb.sec_company."""
    candidates: set[str] = set()
    for sym in symbols:
        s = sym.upper()
        candidates.add(s)
        candidates.add(s.replace(".", "-"))
        if s in CLASS_B_CIK_TICKER:
            candidates.add(CLASS_B_CIK_TICKER[s])
    rows = conn.execute(
        "SELECT ticker, cik, name FROM kb.sec_company WHERE ticker = ANY(%s)",
        (sorted(candidates),),
    ).fetchall()
    by_tk = {r[0].upper(): (int(r[1]), r[2]) for r in rows}
    out: dict[str, tuple[int, str]] = {}
    for sym in symbols:
        s = sym.upper()
        hit = by_tk.get(s) or by_tk.get(s.replace(".", "-"))
        if not hit and s in CLASS_B_CIK_TICKER:
            hit = by_tk.get(CLASS_B_CIK_TICKER[s])
        if hit:
            out[s] = hit
    return out


def sync_sp500(conn, data_dir: Path, user_agent: str = "HeimdallrKB/1.0",
               refresh: bool = False) -> list[dict]:
    """Resolve websites for all S&P 500 companies via SEC + Wikidata and upsert kb.sp500_member + sec_company."""
    conn.execute(SCHEMA_SQL)
    items = load_constituents()
    sec_map = sec_lookup_map(conn, [x["symbol"] for x in items])
    ciks = sorted({cik for cik, _ in sec_map.values()})
    cache_path = data_dir / "sp500" / "wikidata_cache.json"
    by_cik, by_ticker = fetch_wikidata(ciks, user_agent=user_agent, cache_path=cache_path, refresh=refresh)

    # Known found domains in kb.homepage help break multi-domain ties cleanly.
    all_urls = [u for rec in by_cik.values() for u in rec["websites"]]
    all_urls.extend(c["website"] for rows in by_ticker.values() for c in rows)
    all_urls.extend(OVERRIDES.values())
    cand_domains = sorted({d for d in (_website_domain(u) for u in all_urls) if d})
    known_domains = (
        {r[0] for r in conn.execute(
            "SELECT domain FROM kb.homepage WHERE found AND domain = ANY(%s)", (cand_domains,)
        ).fetchall()}
        if cand_domains and conn.execute("SELECT to_regclass('kb.homepage')").fetchone()[0]
        else set()
    )

    records: list[dict] = []
    sec_updates: list[tuple[str, str, int]] = []
    seen_cik_updates: set[int] = set()
    for item in items:
        sym = item["symbol"]
        cik, sec_name = sec_map.get(sym, (None, item["name"]))
        wd = by_cik.get(cik, {}) if cik is not None else {}
        urls = list(wd.get("websites") or [])
        qid = wd.get("qid") or ""
        # Use P414/P249 only when P5531 lacked websites (prevents single-letter historical ticker collisions like P).
        if not urls:
            tk_rows = by_ticker.get(sym, []) + by_ticker.get(sym.replace(".", "-"), [])
            if sym in CLASS_B_CIK_TICKER:
                tk_rows.extend(by_ticker.get(CLASS_B_CIK_TICKER[sym], []))
            urls = [c["website"] for c in tk_rows]
            if not qid and tk_rows:
                qid = tk_rows[0].get("qid") or ""
        if sym in OVERRIDES:
            urls = [OVERRIDES[sym], *urls]
        website, domain = pick_primary_website(urls, sec_name or item["name"], known_domains)
        ind = ", ".join(wd.get("industries") or [])[:300] or None
        desc = (wd.get("description") or "")[:500] or None
        records.append({
            **item,
            "cik": cik,
            "website": website or None,
            "domain": domain or None,
            "wikidata_qid": qid or None,
            "wikidata_description": desc,
            "wikidata_industry": ind,
            "employees": wd.get("employees"),
        })
        if cik is not None and domain and cik not in seen_cik_updates:
            seen_cik_updates.add(cik)
            sec_updates.append((website, domain, cik, domain))

    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO kb.sp500_member (symbol, rank, name, cik, website, domain,
                   wikidata_qid, wikidata_description, wikidata_industry, employees, updated_at)
               VALUES (%(symbol)s, %(rank)s, %(name)s, %(cik)s, %(website)s, %(domain)s,
                   %(wikidata_qid)s, %(wikidata_description)s, %(wikidata_industry)s, %(employees)s, now())
               ON CONFLICT (symbol) DO UPDATE SET
                   rank = EXCLUDED.rank, name = EXCLUDED.name, cik = EXCLUDED.cik,
                   website = EXCLUDED.website, domain = EXCLUDED.domain,
                   wikidata_qid = EXCLUDED.wikidata_qid,
                   wikidata_description = EXCLUDED.wikidata_description,
                   wikidata_industry = EXCLUDED.wikidata_industry,
                   employees = EXCLUDED.employees, updated_at = now()""",
            records,
        )
        if sec_updates:
            cur.executemany(
                "UPDATE kb.sec_company SET website = %s, domain = %s "
                "WHERE cik = %s AND (domain IS NULL OR domain = '' OR domain <> %s)",
                sec_updates,
            )
            if conn.execute("SELECT to_regclass('public.sec_companies')").fetchone()[0]:
                cur.executemany(
                    "UPDATE public.sec_companies SET website = %s "
                    "WHERE cik = %s AND (website IS NULL OR website = '' OR website <> %s)",
                    [(w, cik, w) for w, _, cik, _ in sec_updates],
                )
    return records


def enrich_sp500_domains(conn, domains: Sequence[str], data_dir: Path, user_agent: str,
                         model_path: Path, js_fallback: bool = True, subpages: bool = True) -> dict[str, int]:
    """Fetch missing homepages, subpages, DNS tech, and classifier labels for S&P 500 domains."""
    from app.extract.deterministic import phones_from_text
    from app.kb import branches, classify, homepages, pages, sitefetch, tech, train

    unique = sorted({d for d in domains if d})
    conn.execute(homepages.SCHEMA_SQL)
    conn.execute(pages.SCHEMA_SQL)
    conn.execute(branches.SCHEMA_SQL)
    conn.execute(tech.SCHEMA_SQL)
    conn.execute(classify.SCHEMA_SQL)

    already_found = {
        r[0] for r in conn.execute(
            "SELECT domain FROM kb.homepage WHERE found AND domain = ANY(%s)", (unique,)
        ).fetchall()
    }
    need_hp = [d for d in unique if d not in already_found]
    hp_new = 0

    async def _run_crawl() -> None:
        nonlocal hp_new
        if need_hp:
            own_lanes = 32
            asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(2 * own_lanes))
            site_client = httpx.AsyncClient(
                timeout=httpx.Timeout(12.0, connect=5.0),
                headers={"User-Agent": user_agent},
                follow_redirects=False,
            )
            try:
                own_fetch = sitefetch.own_fetcher(site_client, user_agent, concurrency=own_lanes)
                summary = homepages.Summary()

                def on_page(page) -> None:
                    nonlocal hp_new
                    if page.found and page.text and not page.phones:
                        page.phones = phones_from_text(page.text, ["US"])
                    summary.add(page)
                    homepages.save(conn, page)
                    if page.found:
                        hp_new += 1

                await homepages.collect(
                    need_hp, None, on_page, data_dir, concurrency=4, user_agent=user_agent,
                    crawl_count=4, own_fetch=own_fetch, own_lanes=own_lanes,
                )
            finally:
                await site_client.aclose()

        # Subpages (contact, locations, careers, jobs, security) for found homepages lacking pages.
        sub_sites = (
            conn.execute(
                "SELECT h.domain, h.url FROM kb.homepage h "
                "WHERE h.found AND h.domain = ANY(%s) "
                "  AND NOT EXISTS (SELECT 1 FROM kb.company_page_run r WHERE r.domain = h.domain AND r.miss IS NULL) "
                "ORDER BY h.domain",
                (unique,),
            ).fetchall()
            if subpages
            else []
        )
        if sub_sites:
            tech_index = tech.TechIndex.load()
            countries_map = homepages.country_map(conn, [d for d, _ in sub_sites])
            pending_tech: dict[str, list[tech.TechMatch]] = {}

            async def on_fetch(domain: str, kind: str, url: str, html: str, headers: list[tuple[str, str]]) -> None:
                if kind == "home":
                    found_tech = await asyncio.to_thread(tech_index.scan_page, url, html[:pages.PARSE_CHARS], headers)
                    if found_tech:
                        pending_tech.setdefault(domain, []).extend(found_tech)

            pw = browser = ctx = None
            js_render = None
            shell = pages._playwright_shell() if js_fallback else None
            if js_fallback and shell:
                from playwright.async_api import async_playwright

                js_sem = asyncio.Semaphore(4)
                pw = await async_playwright().start()
                browser = await pw.chromium.launch(headless=True, executable_path=shell)
                ctx = await browser.new_context(ignore_https_errors=True)

                async def render_js(target_url: str) -> str | None:
                    async with js_sem:
                        pg = await asyncio.wait_for(ctx.new_page(), timeout=5.0)
                        try:
                            await asyncio.wait_for(
                                pg.goto(target_url, wait_until="domcontentloaded", timeout=10_000),
                                timeout=12.0,
                            )
                            await pg.wait_for_timeout(1200)
                            return await asyncio.wait_for(pg.content(), timeout=5.0)
                        except Exception:  # noqa: BLE001, S110
                            return None
                        finally:
                            try:
                                await asyncio.wait_for(pg.close(), timeout=3.0)
                            except Exception:  # noqa: BLE001, S110
                                pass

                js_render = render_js

            limits = httpx.Limits(max_connections=64, max_keepalive_connections=32)
            client = httpx.AsyncClient(
                timeout=httpx.Timeout(15.0, connect=6.0), limits=limits,
                headers={"User-Agent": user_agent}, follow_redirects=False,
            )
            try:
                read = pages.page_reader(
                    client, user_agent, 16, on_fetch=on_fetch,
                    countries_by_domain=countries_map, js_render=js_render,
                )
                sem = asyncio.Semaphore(16)

                async def do_one(domain: str, url: str) -> None:
                    async with sem:
                        try:
                            found, miss = await read(domain, url)
                        except Exception as exc:  # noqa: BLE001, S110
                            found, miss = [], f"error_{type(exc).__name__}"
                        pages.save(conn, domain, found, miss)
                        matches = pending_tech.pop(domain, [])
                        for p in found:
                            matches.extend(tech.detect_compliance(f"{p.title}\n{p.text}"))
                            if p.kind in ("careers", "job"):
                                matches.extend(tech_index.scan_job_text(f"{p.title}\n{p.text}"))
                        if matches:
                            tech.save_matches(conn, domain, matches)

                await asyncio.gather(*(do_one(d, u) for d, u in sub_sites))
            finally:
                await client.aclose()
                if ctx is not None:
                    await ctx.close()
                if browser is not None:
                    await browser.close()
                if pw is not None:
                    await pw.stop()

        # DNS MX/TXT for ALL S&P 500 domains (including HTTP 403 WAF-protected ones!).
        dns_done = {
            r[0] for r in conn.execute(
                "SELECT domain FROM kb.company_dns_run WHERE domain = ANY(%s)", (unique,)
            ).fetchall()
        }
        need_dns = [d for d in unique if d not in dns_done]
        if need_dns:
            def on_dns(domain: str, mx_hosts: list[str], matches: list[tech.TechMatch]) -> None:
                if matches:
                    tech.save_matches(conn, domain, matches)
                conn.execute(
                    "INSERT INTO kb.company_dns_run (domain, mx_hosts) VALUES (%s, %s) "
                    "ON CONFLICT (domain) DO UPDATE SET mx_hosts = EXCLUDED.mx_hosts, checked_at = now()",
                    (domain, ",".join(mx_hosts)[:300] or None),
                )

            await tech.scan_dns_domains(need_dns, concurrency=128, on_result=on_dns)

    asyncio.run(_run_crawl())

    # Compliance backfill for fetched S&P homepages (detect_compliance needs no TechIndex load).
    for dom, title, desc, text in conn.execute(
        "SELECT domain, title, description, text FROM kb.homepage WHERE found AND domain = ANY(%s)",
        (unique,),
    ).fetchall():
        m = tech.detect_compliance(" ".join(x for x in (title, desc, text) if x))
        if m:
            tech.save_matches(conn, dom, m)

    # Classify found unlabelled S&P 500 homepages if the model is present.
    labelled_new = 0
    if model_path.is_file():
        to_label = conn.execute(
            """SELECT h.domain, h.url, h.title, h.description, h.text,
                      (SELECT industry FROM kb.pdl_company c WHERE c.domain = h.domain
                       ORDER BY c.industry IS NULL LIMIT 1)
               FROM kb.homepage h
               LEFT JOIN kb.company_label l USING (domain)
               WHERE h.found AND l.domain IS NULL AND h.domain = ANY(%s)""",
            (unique,),
        ).fetchall()
        to_label = [r for r in to_label if classify.page_text(r[2], r[3], r[4])]
        if to_label:
            model = train.LabelModel.load(model_path)
            labeller = classify.Classifier(classify.Embedder(model.embed_model), model)
            labels = labeller.label([r[0] for r in to_label], [r[2:5] for r in to_label], [r[5] for r in to_label])
            with conn.transaction():
                for row, label in zip(to_label, labels, strict=True):
                    classify.save(conn, label, f"{model.embed_model}+{model_path.name}", row[1])
                    labelled_new += 1

    # Gather final S&P 500 domain coverage stats cleanly.
    stats = Counter()
    stats["unique_domains"] = len(unique)
    stats["homepage_found"] = conn.execute(
        "SELECT count(*) FROM kb.homepage WHERE found AND domain = ANY(%s)", (unique,)
    ).fetchone()[0]
    stats["homepage_new"] = hp_new
    stats["pages_domains"] = conn.execute(
        "SELECT count(DISTINCT domain) FROM kb.company_page WHERE domain = ANY(%s)", (unique,)
    ).fetchone()[0]
    stats["branches_domains"] = conn.execute(
        "SELECT count(DISTINCT domain) FROM kb.company_branch WHERE domain = ANY(%s)", (unique,)
    ).fetchone()[0]
    stats["tech_domains"] = conn.execute(
        "SELECT count(DISTINCT domain) FROM kb.company_tech WHERE domain = ANY(%s)", (unique,)
    ).fetchone()[0]
    stats["label_domains"] = conn.execute(
        "SELECT count(*) FROM kb.company_label WHERE domain = ANY(%s)", (unique,)
    ).fetchone()[0]
    stats["labelled_new"] = labelled_new
    return dict(stats)


def link_sec_domains(conn, data_dir: Path, user_agent: str = "HeimdallrKB/1.0",
                     refresh: bool = False) -> tuple[int, int, int]:
    """Resolve domains for all listed kb.sec_company rows missing domain via Wikidata P5531 + P414/P249."""
    rows = conn.execute(
        "SELECT DISTINCT ON (cik) cik, ticker, name FROM kb.sec_company "
        "WHERE ticker IS NOT NULL AND (domain IS NULL OR domain = '') ORDER BY cik, rank NULLS LAST"
    ).fetchall()
    if not rows:
        return 0, 0, 0
    ciks = [int(r[0]) for r in rows]
    cache_path = data_dir / "sec" / "wikidata_sec_cache.json"
    by_cik, by_ticker = fetch_wikidata(ciks, user_agent=user_agent, cache_path=cache_path, refresh=refresh)

    updates: list[tuple[str, str, int]] = []
    qid_rows: list[tuple[int, str, str | None]] = []
    conn.execute('''
        CREATE TABLE IF NOT EXISTS kb.sec_wikidata (
            cik integer PRIMARY KEY,
            wikidata_qid text NOT NULL,
            domain text,
            description text,
            industry text,
            employees integer
        )''')
    for cik, ticker, name in rows:
        tk = (ticker or "").upper()
        wd = by_cik.get(cik, {})
        urls = list(wd.get("websites") or [])
        qid = wd.get("qid") or ""
        if not urls and tk:
            tk_rows = by_ticker.get(tk, []) + by_ticker.get(tk.replace(".", "-"), [])
            urls = [c["website"] for c in tk_rows]
            if not qid and tk_rows:
                qid = tk_rows[0].get("qid") or ""
        website, domain = pick_primary_website(urls, name)
        if domain:
            updates.append((website, domain, cik))
        if qid:
            qid_rows.append((cik, qid, domain or None))

    # Also store QIDs for S&P 500 members so kb.sec_wikidata covers all linked SEC issuers.
    if conn.execute("SELECT to_regclass('kb.sp500_member')").fetchone()[0]:
        conn.execute('''
            INSERT INTO kb.sec_wikidata (cik, wikidata_qid, domain, description, industry, employees)
            SELECT DISTINCT ON (cik) cik, wikidata_qid, domain, wikidata_description, wikidata_industry, employees
            FROM kb.sp500_member
            WHERE cik IS NOT NULL AND wikidata_qid IS NOT NULL
            ON CONFLICT (cik) DO NOTHING
        ''')

    with conn.cursor() as cur:
        if updates:
            cur.executemany(
                "UPDATE kb.sec_company SET website = %s, domain = %s "
                "WHERE cik = %s AND (domain IS NULL OR domain = '')",
                updates,
            )
            if conn.execute("SELECT to_regclass('public.sec_companies')").fetchone()[0]:
                cur.executemany(
                    "UPDATE public.sec_companies SET website = %s "
                    "WHERE cik = %s AND (website IS NULL OR website = '')",
                    [(w, cik) for w, _, cik in updates],
                )
        if qid_rows:
            cur.executemany(
                "INSERT INTO kb.sec_wikidata (cik, wikidata_qid, domain) VALUES (%s, %s, %s) "
                "ON CONFLICT (cik) DO UPDATE SET wikidata_qid = EXCLUDED.wikidata_qid, "
                "domain = COALESCE(EXCLUDED.domain, kb.sec_wikidata.domain)",
                qid_rows,
            )
    return len(rows), len(updates), len(qid_rows)
