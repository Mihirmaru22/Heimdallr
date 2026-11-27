"""Command-line helpers: `python -m app.cli create-admin EMAIL` (prompts for a password) and
`python -m app.cli refresh-sec` (downloads SEC EDGAR's company list for the sec_edgar source) and
`python -m app.cli llm-status | llm-test | llm-enable` (the free OpenRouter models) and
`python -m app.cli job-report JOB_ID` / `sec-check PRODUCT` (what a run planned and what each source answered) and
`python -m app.cli kb-load-pdl FILE` (loads the PDL free company dataset into the company database) and
`python -m app.cli kb-homepages --limit N` (reads company homepages from Common Crawl into kb.homepage) and
`python -m app.cli kb-load-companies-house FILE` (loads the UK register snapshot into kb.uk_company) and
`python -m app.cli kb-teach | kb-train | kb-classify` (homepage labels: teacher model, training, labelling)."""

from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import select

from app.db import session_scope
from app.models import Membership, Organization, Role, User
from app.security import hash_password


def create_admin(email: str, password: str | None) -> None:
    password = password or getpass.getpass("Password (10+ characters): ")
    if len(password) < 10:
        sys.exit("Password must be at least 10 characters")
    with session_scope(bypass=True) as db:
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user is None:
            user = User(email=email, password_hash=hash_password(password), display_name=email.split("@")[0])
            db.add(user)
            db.flush()
            org = Organization(name="Admin workspace", slug=f"admin-{str(user.id)[:8]}")
            db.add(org)
            db.flush()
            db.add(Membership(org_id=org.id, user_id=user.id, role=Role.owner))
        user.is_platform_admin = True
    print(f"{email} is now a platform admin")


def refresh_sec(limit: int | None) -> None:
    from app.discovery.sec_edgar import refresh_index

    def progress(done: int, total: int) -> None:
        if done % 250 == 0 or done == total:
            print(f"  looked up {done}/{total} companies", flush=True)

    print("Downloading SEC EDGAR's company list (about 30 minutes the first time, at 5 requests a second)...")
    result = refresh_index(limit=limit, progress=progress)
    print(f"Done: {result['companies']} companies listed, {result['looked_up']} looked up, {result['failed']} failed")


def llm(cmd: str) -> None:
    import asyncio
    import json

    from app.llm.openrouter import LLMUnavailable, OpenRouter, State

    if cmd == "llm-enable":
        State().enable()
        print("Model use is switched back on.")
        return

    async def run() -> None:
        router = OpenRouter()
        try:
            if cmd == "llm-status":
                print(json.dumps(await router.status(), indent=2))
            else:
                reply = await router.chat([{"role": "user", "content": "Reply with the single word: ready"}],
                                          max_tokens=50)
                tried = f" after trying {', '.join(reply.attempts[:-1])}" if len(reply.attempts) > 1 else ""
                print(f"{reply.model} answered: {reply.text.strip()!r}{tried} (free; "
                      f"{router._state().used_today()} of {router._state().daily_limit()} requests used today)")
        except LLMUnavailable as exc:
            sys.exit(f"Not available: {exc}")
        finally:
            await router.aclose()

    asyncio.run(run())


def job_report(job_id: str) -> None:
    """The plan a job ran with and everything its sources and pages reported: the export's Diagnostics sheet."""
    import uuid

    from app.models import CrawlJob
    from app.services.diagnostics import run_diagnostics

    with session_scope(bypass=True) as db:
        job = db.get(CrawlJob, uuid.UUID(job_id))
        if job is None:
            sys.exit(f"No job {job_id}")
        print(f"State: {job.state}  error: {job.error or '-'}")
        section = None
        for sec, item, value in run_diagnostics(db, job.id):
            if sec != section:
                print(f"\n== {sec}")
                section = sec
            print(f"  {item:32} {value}")


def score(job_ids: list[str], key_path: str | None) -> None:
    """Several runs side by side on the same scorecard."""
    import uuid

    from app.services.scorecard import load_key, score_job

    key = load_key(key_path)
    with session_scope(bypass=True) as db:
        cards = [score_job(db, uuid.UUID(j), key) for j in job_ids]
    names = list(dict.fromkeys(k for c in cards for k in c))
    long = {n for n in names if n == "key: missing" or n.startswith(("key: lost at", "key: candidate stage",
                                                                     "company search note"))}  # under the table
    names = [n for n in names if n not in long]
    width = max(len(n) for n in names)
    print(" " * width + "  " + "  ".join(j[:8].ljust(22) for j in job_ids))
    for n in names:
        print(n.ljust(width) + "  " + "  ".join(str(c.get(n, "")).ljust(22) for c in cards))
    for n in long:
        for j, c in zip(job_ids, cards, strict=True):
            if n in c:
                print(f"{n} ({j[:8]}): {c[n]}")


def candidates(job_id: str, key_path: str) -> None:
    """For every company in the answer key: did any source name it, was its country known, and who named it.
    Read from the finished job; no search or model call is made."""
    import uuid

    from app.services.candidates import ORDER, candidate_recall, scorecard_rows
    from app.services.scorecard import load_key

    key = load_key(key_path)
    with session_scope(bypass=True) as db:
        result = candidate_recall(db, uuid.UUID(job_id), key)
    width = max([len(r["company"]) for r in result["rows"]] + [7])
    print(f"Countries asked: {', '.join(result['countries']) or 'any'}")
    for stage in ORDER:
        for r in (r for r in result["rows"] if r["stage"] == stage):
            print(f"  {r['company'].ljust(width)}  {stage:42}  {', '.join(r['named by']) or '-'}")
    print()
    for name, value in scorecard_rows(result).items():
        if not name.startswith("key: candidate stage"):
            print(f"{name}: {value}")


def _table(rows: list[dict[str, str]]) -> None:
    cols = list(rows[0])
    width = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in cols}
    print("  ".join(c.ljust(width[c]) for c in cols))
    for r in rows:
        print("  ".join(str(r[c]).ljust(width[c]) for c in cols))


def eval_history() -> None:
    """Every finished run of every test question, scored against its key, with the code it ran on."""
    from app.services.evaluation import found, history, load_keys

    with session_scope(bypass=True) as db:
        rows = history(db, load_keys())
    if not rows:
        sys.exit("No finished runs of the test questions")
    rows = [{k.replace("key: ", "").replace("included: ", ""): v for k, v in r.items()} for r in rows]
    _table(rows)
    print("\nFirst run -> latest run, per question:")
    for q in dict.fromkeys(r["question"] for r in rows):
        runs = [r for r in rows if r["question"] == q]
        a, b = runs[0], runs[-1]
        print(f"  {q:34} must-haves {a['must-have companies found']:>12} -> {b['must-have companies found']:<12}"
              f" wrong rows {a['rows that must not be there']} -> {b['rows that must not be there']}"
              f"  ({len(runs)} runs)")
    first = [found(next(r for r in rows if r["question"] == q)["must-have companies found"])
             for q in dict.fromkeys(r["question"] for r in rows)]
    last = [found([r for r in rows if r["question"] == q][-1]["must-have companies found"])
            for q in dict.fromkeys(r["question"] for r in rows)]
    print(f"  {'all questions':34} must-haves {sum(f for f, _ in first)}/{sum(t for _, t in first)} -> "
          f"{sum(f for f, _ in last)}/{sum(t for _, t in last)}")


CALLS_PER_RUN = 40  # free model requests one benchmark run can take (measured: 404 for 12 runs on 8759531)


def search_health() -> str:
    """One live website lookup before a benchmark: the benchmark does not start when no search engine answers,
    because every score would then measure the outage."""
    import asyncio

    import httpx

    from app.config import get_settings
    from app.search import LOOKUP, SearchError, SearchHub

    async def probe() -> str:
        async with httpx.AsyncClient(timeout=30, headers={"User-Agent": get_settings().user_agent}) as client:
            hub = SearchHub.from_settings(client)
            if not hub.configured:
                sys.exit("Not started: no web search is configured (a search API key or WEBDATA_SEARXNG_URL).")
            try:
                hits = await hub.search("Ford Motor Company official website", kind=LOOKUP)
            except SearchError as exc:
                sys.exit(f"Not started: {exc}")
            if not hits:
                sys.exit("Not started: web search answered but returned no results for a plain test query.")
            engines = sorted({h.provider for h in hits})
            return f"web search healthy: {len(hits)} results from {', '.join(engines)}" + (
                f"; off: {hub.problems}" if hub.problems else "")

    return asyncio.run(probe())


def eval_run(wait_seconds: int, repeat: int, refresh_sources: bool = False, allow_short: bool = False) -> None:
    """Run every test question again with its latest plan, wait, and score each new run next to the last one.

    Runs that hit the end of the day's free model allowance are judged by rules only, which measures "no model"
    rather than the code, so the benchmark does not start when the allowance left looks too small."""
    import time

    from app.llm.openrouter import FREE_DAILY, State
    from app.services.evaluation import COLUMNS, load_keys, start_runs, starts_of, unfinished
    from app.services.scorecard import score_job
    from app.worker import tasks

    keys = load_keys()
    state = State()
    limit = state.daily_limit() or FREE_DAILY
    used_before = state.used_today()
    need = CALLS_PER_RUN * repeat * len(keys)
    if limit - used_before < need and not allow_short:
        sys.exit(f"Not started: {limit - used_before} of {limit} free model requests are left today and these "
                 f"{repeat * len(keys)} runs can take about {need}. Run it after the daily reset (00:00 UTC), or "
                 "pass --allow-short to run anyway (scores then partly measure rules-only judging).")
    print(search_health())
    with session_scope(bypass=True) as db:
        # Each question more than once shows how much one question's score moves between identical runs.
        started = [(name, prev.id, job.id) for _ in range(repeat)
                   for name, prev, job in start_runs(db, keys, refresh_sources)]
    for name, _prev, job in started:
        tasks.run_job.delay(str(job))
        print(f"started {name}: {str(job)[:8]}")
    deadline = time.monotonic() + wait_seconds
    while True:
        with session_scope(bypass=True) as db:
            left = unfinished(db, [j for _n, _p, j in started])
        if not left:
            break
        if time.monotonic() > deadline:
            sys.exit(f"{left} runs still going after {wait_seconds}s; score them later with eval-history")
        time.sleep(20)
    rows = []
    with session_scope(bypass=True) as db:
        for name, prev, job in started:
            a, b = score_job(db, prev, keys[name]), score_job(db, job, keys[name])
            starts = starts_of(db, job)
            rows.append({"question": name, "runs": f"{str(prev)[:8]} -> {str(job)[:8]}",
                         "clean": "yes" if starts == 1 else f"NO: started {starts} times",
                         **{c.replace("key: ", ""): f"{a.get(c, '')} -> {b.get(c, '')}" for c in COLUMNS}})
            for c in b:
                if c.startswith("key: lost at"):
                    print(f"{name} {str(job)[:8]} {c}: {b[c]}")
    _table(rows)
    used = state.used_today() - used_before  # negative when the day changed during the runs
    print(f"free model requests: {used if used >= 0 else 'n/a (the daily count reset during the runs)'} used by "
          f"{len(started)} runs; {limit - state.used_today()} of {limit} left today"
          + ("; the allowance ran out, so later runs were judged by rules only" if state.exhausted() else ""))


def sec_check(product_name: str, aliases: list[str]) -> None:
    """One SEC full-text search exactly as the sec_filings source sends it, with SEC's raw answer."""
    from datetime import date, timedelta

    import httpx

    from app.config import get_settings
    from app.discovery.sec_filings import SEARCH, SecFilingsProvider
    from app.evidence.products import product_for

    product = product_for(product_name, aliases)
    today = date.today()
    params = {"q": SecFilingsProvider.query(product), "dateRange": "custom",
              "startdt": (today - timedelta(days=365 * 3)).isoformat(), "enddt": today.isoformat()}
    ua = get_settings().user_agent
    print(f"User-Agent: {ua}\nQuery: {params['q']}")
    try:
        resp = httpx.get(SEARCH, params=params, headers={"User-Agent": ua}, timeout=60, follow_redirects=True)
    except httpx.HTTPError as exc:
        sys.exit(f"Request failed: {type(exc).__name__}: {exc}")
    print(f"HTTP {resp.status_code}  {resp.headers.get('content-type')}")
    try:
        hits = resp.json()["hits"]
    except Exception:
        sys.exit("Not the expected JSON. First 500 characters:\n" + resp.text[:500])
    print(f"Filings found: {hits['total']['value']}")
    for h in hits["hits"][:10]:
        src = h["_source"]
        print(f"  {src['display_names'][0][:60]:60} {src.get('form'):6} {src.get('file_type', '')[:10]:10} "
              f"{src.get('file_date')} states={src.get('biz_states')}")


def kb_load_pdl(path: str, report_only: bool, force: bool) -> None:
    from pathlib import Path

    from app.kb import pdl

    file = Path(path)
    if not file.is_file():
        sys.exit(f"No such file: {file}")

    def progress(rows: int) -> None:
        print(f"  {rows:,} rows read", flush=True)

    if report_only:
        coverage = pdl.scan(pdl.read_rows(file), progress=progress)
    else:
        print(f"Loading {file.name} into kb.{pdl.TABLE}...", flush=True)
        try:
            coverage = pdl.load(file, force=force, progress=progress)
        except ValueError as exc:
            sys.exit(str(exc))
    print(coverage.report())


def kb_load_companies_house(path: str, report_only: bool, force: bool) -> None:
    from pathlib import Path

    from app.kb import companies_house, pdl

    file = Path(path)
    if not file.is_file():
        sys.exit(f"No such file: {file}")

    def progress(rows: int) -> None:
        print(f"  {rows:,} rows read", flush=True)

    if report_only:
        coverage = companies_house.scan(pdl.read_rows(file), progress=progress)
    else:
        print(f"Loading {file.name} into kb.{companies_house.TABLE}...", flush=True)
        try:
            coverage = companies_house.load(file, force=force, progress=progress)
        except ValueError as exc:
            sys.exit(str(exc))
    print(coverage.report())


def kb_load_gleif(path: str, report_only: bool, force: bool) -> None:
    from pathlib import Path

    from app.kb import gleif

    file = Path(path)
    if not file.is_file():
        sys.exit(f"No such file: {file}")

    def progress(rows: int) -> None:
        print(f"  {rows:,} rows read", flush=True)

    if report_only:
        coverage = gleif.scan(gleif.iter_rows(file), progress=progress)
    else:
        print(f"Loading {file.name} into kb.{gleif.TABLE}...", flush=True)
        try:
            coverage = gleif.load(file, force=force, progress=progress)
        except ValueError as exc:
            sys.exit(str(exc))
    print(coverage.report())


def kb_load_sec(tickers_path: str, submissions_zip: str, report_only: bool, force: bool) -> None:
    from pathlib import Path

    from app.kb import sec_bulk

    t_file, s_file = Path(tickers_path), Path(submissions_zip)
    for f in (t_file, s_file):
        if not f.is_file():
            sys.exit(f"No such file: {f}")

    def progress(rows: int) -> None:
        print(f"  {rows:,} entities read", flush=True)

    if report_only:
        coverage = sec_bulk.scan(sec_bulk.iter_rows(t_file, s_file), progress=progress)
    else:
        print(f"Loading {s_file.name} into kb.{sec_bulk.TABLE}...", flush=True)
        try:
            coverage = sec_bulk.load(t_file, s_file, force=force, progress=progress)
        except ValueError as exc:
            sys.exit(str(exc))
    print(coverage.report())


def kb_load_sec_facts(path: str | None) -> None:
    import time
    from pathlib import Path

    import httpx

    from app.config import get_settings
    from app.kb import sec_facts

    settings = get_settings()
    if path:
        zpath = Path(path)
        if not zpath.is_file():
            sys.exit(f"File not found: {zpath}")
    else:
        zpath = Path(settings.data_dir) / "sec" / "companyfacts.zip"
        zpath.parent.mkdir(parents=True, exist_ok=True)
        print(f"Downloading {sec_facts.COMPANYFACTS_URL} -> {zpath}...", flush=True)
        ua = {"User-Agent": f"{settings.user_agent} (mailto:research@heimdallr.local)"}
        with httpx.Client(timeout=httpx.Timeout(120, connect=20), follow_redirects=True, headers=ua) as client:
            with client.stream("GET", sec_facts.COMPANYFACTS_URL) as resp:
                resp.raise_for_status()
                tmp = zpath.with_suffix(".zip.part")
                with open(tmp, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=1 << 20):
                        f.write(chunk)
                tmp.replace(zpath)

    t0 = time.monotonic()

    def progress(n: int) -> None:
        print(f"  {n:,} SEC filers processed", flush=True)

    cov = sec_facts.load(zpath, progress=progress)
    print(f"Loaded in {time.monotonic() - t0:.1f}s: {cov.report()}")


def kb_load_uk_accounts(paths: list[str] | None, latest_n: int) -> None:
    import re
    import time
    from pathlib import Path

    import httpx

    from app.config import get_settings
    from app.kb import uk_accounts

    settings = get_settings()
    files: list[Path] = []
    if paths:
        for p in paths:
            path = Path(p)
            if path.is_dir():
                files.extend(sorted(path.glob("*.zip")))
            elif path.is_file():
                files.append(path)
            else:
                sys.exit(f"Path not found: {p}")
    else:
        dest = Path(settings.data_dir) / "uk_accounts"
        dest.mkdir(parents=True, exist_ok=True)
        with httpx.Client(timeout=httpx.Timeout(120, connect=20), follow_redirects=True) as client:
            r = client.get(uk_accounts.ACCOUNTS_INDEX_URL)
            r.raise_for_status()
            zips = re.findall(r"href=['\"]([^'\"]*Accounts_Bulk_Data-[^'\"]*\.zip)", r.text, re.I)
            for rel in zips[-latest_n:]:
                name = Path(rel).name
                zpath = dest / name
                if not zpath.is_file():
                    print(f"Downloading {name}...", flush=True)
                    with client.stream("GET", uk_accounts.ACCOUNTS_BASE_URL + rel.lstrip("/")) as resp:
                        resp.raise_for_status()
                        tmp = zpath.with_suffix(".zip.part")
                        with open(tmp, "wb") as f:
                            for ch in resp.iter_bytes(1 << 20):
                                f.write(ch)
                        tmp.replace(zpath)
                files.append(zpath)

    if not files:
        sys.exit("No UK Accounts ZIP files found.")
    t0 = time.monotonic()
    cov = uk_accounts.load(files, progress=lambda n: print(f"  {n:,} UK accounts parsed", flush=True))
    print(f"Loaded {len(files)} file(s) in {time.monotonic() - t0:.1f}s: {cov.report()}")


def kb_load_usaspending(path: str | None, fiscal_year: int) -> None:
    import time
    from pathlib import Path

    import httpx

    from app.config import get_settings
    from app.kb import usaspending_bulk

    settings = get_settings()
    if path:
        zpath = Path(path)
        if not zpath.is_file():
            sys.exit(f"File not found: {zpath}")
    else:
        name, url = usaspending_bulk.latest_full_contracts_url(fiscal_year)
        zpath = Path(settings.data_dir) / "usaspending" / name
        zpath.parent.mkdir(parents=True, exist_ok=True)
        if not zpath.is_file():
            print(f"Downloading {url} -> {zpath}...", flush=True)
            tmp = zpath.with_suffix(".zip.part")
            with httpx.Client(timeout=httpx.Timeout(120, connect=20), follow_redirects=True) as client:
                for attempt in range(10):
                    pos = tmp.stat().st_size if tmp.exists() else 0
                    headers = {"Range": f"bytes={pos}-"} if pos else {}
                    try:
                        with client.stream("GET", url, headers=headers) as resp:
                            if resp.status_code == 416:
                                break
                            resp.raise_for_status()
                            mode = "ab" if (pos and resp.status_code == 206) else "wb"
                            with open(tmp, mode) as f:
                                for ch in resp.iter_bytes(1 << 20):
                                    f.write(ch)
                        break
                    except httpx.HTTPError as exc:
                        if attempt == 9:
                            raise
                        print(f"  download interrupted ({type(exc).__name__}), retrying...", flush=True)
                        time.sleep(3)
                tmp.replace(zpath)

    t0 = time.monotonic()
    cov = usaspending_bulk.load(
        zpath, progress=lambda n: print(f"  {n:,} USAspending transactions read", flush=True)
    )
    print(f"Loaded in {time.monotonic() - t0:.1f}s: {cov.report()}")


def kb_load_mca(path: str, force: bool) -> None:
    import time
    from pathlib import Path

    from app.kb import india_mca

    f = Path(path)
    if not f.is_file():
        sys.exit(f"File not found: {f}")
    t0 = time.monotonic()
    cov = india_mca.load(f, force=force, progress=lambda n: print(f"  {n:,} MCA rows read", flush=True))
    print(f"Loaded in {time.monotonic() - t0:.1f}s: {cov.report()}")


def kb_load_people(refresh: bool) -> None:
    import time
    from pathlib import Path

    import psycopg

    from app.config import get_settings
    from app.kb import people
    from app.kb.pdl import kb_dsn

    settings = get_settings()
    t0 = time.monotonic()
    with psycopg.connect(kb_dsn(), autocommit=True) as conn:
        n = people.load_wikidata_people(
            conn, data_dir=Path(settings.data_dir), user_agent=settings.user_agent, refresh=refresh
        )
    print(f"Loaded {n:,} Wikidata leadership rows into kb.company_person in {time.monotonic() - t0:.1f}s.")


def kb_link_sec(refresh: bool) -> None:
    import time
    from pathlib import Path

    import psycopg

    from app.config import get_settings
    from app.kb import sp500
    from app.kb.pdl import kb_dsn

    settings = get_settings()
    t0 = time.monotonic()
    with psycopg.connect(kb_dsn(), autocommit=True) as conn:
        checked, linked, qids = sp500.link_sec_domains(
            conn, data_dir=Path(settings.data_dir), user_agent=settings.user_agent, refresh=refresh
        )
    print(
        f"Linked SEC issuers in {time.monotonic() - t0:.1f}s: "
        f"checked={checked:,}, linked_domains={linked:,}, wikidata_qids={qids:,}"
    )


def kb_load_sp500(skip_crawl: bool = False, refresh: bool = False, js_fallback: bool = True,
                  homepages_only: bool = False) -> None:
    import time
    from pathlib import Path

    import psycopg

    from app.config import get_settings
    from app.kb import sp500
    from app.kb.pdl import kb_dsn

    settings = get_settings()
    data_dir = Path(settings.data_dir)
    t0 = time.monotonic()
    with psycopg.connect(kb_dsn(), autocommit=True) as conn:
        records = sp500.sync_sp500(conn, data_dir=data_dir, user_agent=settings.user_agent, refresh=refresh)
        resolved = [r["domain"] for r in records if r["domain"]]
        unique = sorted(set(resolved))
        print(
            f"Synced {len(records):,} S&P 500 symbols ({len(unique):,} unique domains) "
            f"in {time.monotonic() - t0:.1f}s.",
            flush=True,
        )
        if not skip_crawl:
            stats = sp500.enrich_sp500_domains(
                conn, unique, data_dir=data_dir, user_agent=settings.user_agent,
                model_path=_label_model_path(), js_fallback=js_fallback, subpages=not homepages_only,
            )
            print(
                f"Enriched S&P 500 in {time.monotonic() - t0:.1f}s: "
                f"domains={stats['unique_domains']}, homepage_found={stats['homepage_found']} "
                f"(+{stats['homepage_new']} new), pages={stats['pages_domains']}, "
                f"branches={stats['branches_domains']}, tech={stats['tech_domains']}, "
                f"labels={stats['label_domains']} (+{stats['labelled_new']} new)",
                flush=True,
            )


def kb_homepages(limit: int | None, iso2: str | None, crawl: list[str] | None, concurrency: int, sample: bool,
                 crawl_count: int, again: bool, own_fetch: bool, biggest_first: bool = False,
                 own_lanes: int = 128) -> None:
    import asyncio
    import time
    from pathlib import Path

    import httpx
    import psycopg

    from app.config import get_settings
    from app.kb import homepages
    from app.kb.pdl import kb_dsn

    with psycopg.connect(kb_dsn(), autocommit=True) as conn:
        conn.execute(homepages.SCHEMA_SQL)
        if again:  # the same domains as the last run, to compare like with like
            domains = [r[0] for r in conn.execute("SELECT domain FROM kb.homepage ORDER BY domain").fetchall()]
            domains = domains[:limit] if limit else domains
        else:
            domains = homepages.select_domains(conn, limit=limit, iso2=iso2, sample=sample, biggest_first=biggest_first)
        print(f"Reading {len(domains):,} homepages from Common Crawl, {concurrency} at a time...", flush=True)
        summary = homepages.Summary()
        started = time.monotonic()
        window = {"start": started, "stall": 0.0}
        status: dict = {}

        def on_page(page) -> None:
            homepages.save(conn, page)
            summary.add(page)
            if summary.domains % 500 == 0:  # speed over the last 500 sites, so start-up time does not count
                now = time.monotonic()
                rate = 500 / max(0.1, now - window["start"])
                waiting = status["cc_waiting"]() if "cc_waiting" in status else 0
                print(f"  {summary.domains:,} done, {summary.found:,} found, {rate:.1f} sites/s; "
                      f"event loop stalled up to {window['stall']:.1f} s; {waiting:,} waiting for Common Crawl",
                      flush=True)
                window.update(start=now, stall=0.0)

        async def watch_loop() -> None:
            """How long the event loop was blocked (0 = never): a long stall means something
            synchronous is holding every fetch, not that the sites are slow."""
            loop = asyncio.get_running_loop()
            while True:
                before = loop.time()
                await asyncio.sleep(0.5)
                window["stall"] = max(window["stall"], loop.time() - before - 0.5)

        def on_crawl(name: str) -> None:
            print(f"Crawl {name}: getting its index map (cluster.idx, downloaded once, a few hundred MB)...",
                  flush=True)

        async def run() -> list[str]:
            settings = get_settings()
            fetch_own = None
            site_client = None
            if own_fetch:
                from concurrent.futures import ThreadPoolExecutor

                from app.kb.sitefetch import own_fetcher

                # DNS lookups run in the default thread pool (about 14 threads); with many sites at a time
                # they would queue there and run into dns_alive's timeout, reading live sites as dead.
                asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(2 * own_lanes))

                site_client = httpx.AsyncClient(  # short: one try per site, a slow site is recorded as slow
                    timeout=httpx.Timeout(10.0, connect=5.0),
                    headers={"User-Agent": settings.user_agent}, follow_redirects=False)
                fetch_own = own_fetcher(site_client, settings.user_agent, concurrency=own_lanes)
            watcher = asyncio.create_task(watch_loop())
            try:
                return await homepages.collect(
                    domains, crawl, on_page, Path(settings.data_dir), concurrency, user_agent=settings.user_agent,
                    on_crawl=on_crawl, crawl_count=crawl_count, own_fetch=fetch_own,
                    own_lanes=own_lanes, status=status)
            finally:
                watcher.cancel()
                if site_client is not None:
                    await site_client.aclose()

        try:
            used = asyncio.run(run())
        except httpx.HTTPError as exc:
            sys.exit(f"Common Crawl did not answer ({exc}). If index.commoncrawl.org is down, pass the crawl id, "
                     "e.g. --crawl CC-MAIN-2026-44 (the newest is listed at commoncrawl.org/latest-crawl).")
        seconds = time.monotonic() - started
    print(f"\nCrawls {', '.join(used)}, {seconds / 60:.1f} minutes, {summary.domains / max(1.0, seconds):.2f} sites/s")
    print(summary.report())


def _label_model_path():
    from pathlib import Path

    from app.config import get_settings

    return Path(get_settings().data_dir) / "kb" / "label_model.npz"


def kb_teach(model: str, limit: int, export_sample: int, export_path: str | None, same_as: str | None,
             export_pages: int = 0, import_file: str | None = None, tech_share: float = 0.5,
             uncertain: bool = False, biggest_first: bool = False, countries: str | None = None,
             export_contacts: int = 0) -> None:
    import time
    from pathlib import Path

    import httpx
    import psycopg

    from app.kb import teach
    from app.kb.pdl import kb_dsn

    with psycopg.connect(kb_dsn(), autocommit=True) as conn:
        conn.execute(teach.SCHEMA_SQL)
        if export_sample:
            path = Path(export_path or "teach_sample.csv")
            print(f"Wrote the teacher labels of {teach.export_sample(conn, path, export_sample):,} pages "
                  f"(one row per model) to {path}.")
            return
        if export_contacts:
            from app.kb import pages

            conn.execute(pages.SCHEMA_SQL)
            path = Path(export_path or "contact_pages.csv")
            print(f"Wrote the contact/careers pages of {teach.export_contacts(conn, path, export_contacts, model):,} "
                  f"sites to {path}.")
            return
        if export_pages:
            path = Path(export_path or "teach_pages.csv")
            n = teach.export_pages(conn, path, export_pages, model, tech_share, uncertain, biggest_first, countries)
            print(f"Wrote {n:,} pages to {path} "
                  f"(not yet labelled by {model}).")
            return
        if import_file:
            with open(import_file, encoding="utf-8") as f:
                header = f.readline()
            if "real_page" not in header:  # what was read on the contact and careers pages
                merged, waiting = teach.import_profile(conn, Path(import_file), model)
                print(f"Contact/careers details: {merged:,} merged into labels, {waiting:,} waiting for one.")
                return
            summary = teach.import_labels(conn, Path(import_file), model)
            print(summary.report())
            return
        rows = teach.select_pages(conn, limit, model, same_as)
        if not rows:
            print("No unlabelled homepages (kb-homepages fills kb.homepage).")
            return
        with httpx.Client(timeout=600) as client:
            try:
                client.get(f"{teach.OLLAMA_URL}/api/tags").raise_for_status()
            except httpx.HTTPError as exc:
                sys.exit(f"Ollama is not answering at {teach.OLLAMA_URL} ({exc}). Start it with: ollama serve")
            print(f"Labelling {len(rows):,} homepages with {model} (one at a time; Ctrl-C is safe, "
                  "labels so far are kept and a rerun continues)...", flush=True)
            started = time.monotonic()

            def progress(summary) -> None:
                if summary.rows % 25 == 0:
                    left = (len(rows) - summary.rows) * summary.seconds / summary.rows
                    print(f"  {summary.rows:,} done, {summary.seconds / summary.rows:.1f} s per page, "
                          f"about {left / 3600:.1f} h left", flush=True)

            summary = teach.run(conn, client, model, rows, progress)
    print(f"\n{(time.monotonic() - started) / 60:.1f} minutes")
    print(summary.report())


def kb_train(teacher: str) -> None:
    import psycopg

    from app.kb import classify, train
    from app.kb.pdl import kb_dsn

    with psycopg.connect(kb_dsn()) as conn:
        rows = conn.execute(
            """SELECT h.title, h.description, h.text, t.real_page, t.tech_company, t.micro_sector, t.offering,
                      (SELECT industry FROM kb.pdl_company c WHERE c.domain = t.domain
                       ORDER BY c.industry IS NULL LIMIT 1)
               FROM kb.teach_label t JOIN kb.homepage h USING (domain)
               WHERE t.error IS NULL AND t.real_page IS NOT NULL AND t.model = %s""", (teacher,)
        ).fetchall()
    rows = [r for r in rows if classify.page_text(r[0], r[1], r[2])]
    if len(rows) < 100:
        sys.exit(f"Only {len(rows)} teacher labels from {teacher}; run kb-teach first (a few thousand pages).")
    chunks = 2
    print(f"Embedding {len(rows):,} labelled homepages with {classify.MODEL} ({chunks} parts each)...", flush=True)
    embedder = classify.Embedder()
    vectors = classify.embed_pages(embedder, [r[:3] for r in rows], chunks)
    labels = [{"real_page": r[3], "tech_company": r[4], "micro_sector": r[5], "offering": r[6], "industry": r[7]}
              for r in rows]
    print("Training: each head is cross-validated with and without the page's words...", flush=True)
    model = train.train(list(zip(vectors, labels, strict=True)), embedder.name,
                        texts=[classify.word_text(*r[:3]) for r in rows], chunks=chunks)
    path = _label_model_path()
    model.save(path)
    print(f"Saved {path}\n")
    for report in model.reports:
        print("\n".join(report.lines()) + "\n")


def kb_pages(limit: int, countries: str | None, lanes: int, with_tech: bool = True,
             retry_misses: bool = False, js_fallback: bool = False) -> None:
    import asyncio
    import multiprocessing
    import os
    import time
    from collections import Counter
    from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

    import httpx
    import psycopg

    from app.config import get_settings
    from app.kb import homepages, pages, tech
    from app.kb.pdl import kb_dsn

    settings = get_settings()
    tech_index = tech.TechIndex.load() if with_tech else None
    with psycopg.connect(kb_dsn(), autocommit=True) as conn:
        conn.execute(pages.SCHEMA_SQL)
        if with_tech:
            conn.execute(tech.SCHEMA_SQL)
        sites = pages.select_sites(conn, limit, countries, retry_misses=retry_misses)
        countries_by_domain = homepages.country_map(conn, [d for d, _u in sites])
        print(f"Reading contact and careers pages of {len(sites):,} sites, {lanes} at a time...", flush=True)
        done, kinds, misses = 0, Counter(), Counter()
        tech_hits = 0
        pending_tech: dict[str, list[tech.TechMatch]] = {}
        started = window = time.monotonic()
        workers = min(6, max(2, (os.cpu_count() or 4) - 2)) if with_tech else 0
        tech_pool = (
            ProcessPoolExecutor(
                max_workers=workers,
                mp_context=multiprocessing.get_context("spawn"),
                initializer=tech._pool_init,
                max_tasks_per_child=1000,
            )
            if with_tech
            else None
        )

        async def on_fetch(domain: str, kind: str, url: str, html: str, headers: list[tuple[str, str]]) -> None:
            if tech_pool is None or kind != "home":
                return
            loop = asyncio.get_running_loop()
            found_tech = await loop.run_in_executor(
                tech_pool, tech._pool_scan, url, html[:pages.PARSE_CHARS], headers
            )
            if found_tech:
                pending_tech.setdefault(domain, []).extend(found_tech)

        async def run_batch(batch: list[tuple[str, str]], js_render=None) -> None:
            nonlocal done, window, tech_hits
            limits = httpx.Limits(max_connections=max(200, lanes * 2), max_keepalive_connections=lanes)
            client = httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=6.0), limits=limits,
                                       headers={"User-Agent": settings.user_agent}, follow_redirects=False)
            read = pages.page_reader(
                client,
                settings.user_agent,
                lanes,
                on_fetch=on_fetch if with_tech else None,
                countries_by_domain=countries_by_domain,
                js_render=js_render,
            )
            queue: asyncio.Queue = asyncio.Queue()
            for site in batch:
                queue.put_nowait(site)

            async def worker() -> None:
                nonlocal done, window, tech_hits
                while not queue.empty():
                    domain, url = queue.get_nowait()
                    try:
                        found, miss = await read(domain, url)
                        pages.save(conn, domain, found, miss)
                        matches = pending_tech.pop(domain, [])
                        if tech_index is not None:
                            for p in found:
                                matches.extend(tech.detect_compliance(f"{p.title}\n{p.text}"))
                                if p.kind in ("careers", "job"):
                                    matches.extend(tech_index.scan_job_text(f"{p.title}\n{p.text}"))
                            if matches:
                                tech_hits += tech.save_matches(conn, domain, matches)
                    except Exception as exc:  # noqa: BLE001 - isolate bad site from sibling workers
                        pending_tech.pop(domain, None)
                        found, miss = [], f"error_{type(exc).__name__}"
                        pages.save(conn, domain, [], miss)
                        print(f"  skip {domain}: {type(exc).__name__}: {str(exc)[:120]}", flush=True)
                    done += 1
                    kinds.update({p.kind for p in found})
                    misses.update([miss] if miss else [])
                    if done % 500 == 0:
                        now = time.monotonic()
                        print(f"  {done:,} sites, {500 / max(0.1, now - window):.1f} sites/s; with contact page "
                              f"{kinds['contact']:,}, locations {kinds['locations']:,}, careers {kinds['careers']:,}, "
                              f"job ads {kinds['job']:,}, security {kinds['security']:,}, tech rows {tech_hits:,}",
                              flush=True)
                        window = now

            try:
                await asyncio.gather(*(worker() for _ in range(lanes)))
            finally:
                await client.aclose()

        async def run() -> None:
            asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(2 * lanes))
            pw = browser = ctx = None
            js_sem = asyncio.Semaphore(4)
            js_render = None
            shell = pages._playwright_shell() if js_fallback else None
            if js_fallback:
                from playwright.async_api import async_playwright

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
                        except Exception:  # noqa: BLE001 - one broken JS page never stops crawl
                            return None
                        finally:
                            try:
                                await asyncio.wait_for(pg.close(), timeout=3.0)
                            except Exception:  # noqa: BLE001, S110
                                pass

                js_render = render_js
            try:
                for i in range(0, len(sites), 5000):
                    await run_batch(sites[i:i + 5000], js_render=js_render)
            finally:
                if ctx is not None:
                    await ctx.close()
                if browser is not None:
                    await browser.close()
                if pw is not None:
                    await pw.stop()

        try:
            asyncio.run(run())
        finally:
            if tech_pool is not None:
                tech_pool.shutdown()
    print(f"\n{done:,} sites in {(time.monotonic() - started) / 60:.1f} minutes: contact page {kinds['contact']:,}, "
          f"locations {kinds['locations']:,}, careers page {kinds['careers']:,}, sites with job ads {kinds['job']:,}, "
          f"security page {kinds['security']:,}")
    print("Not found: " + ", ".join(f"{k} {n:,}" for k, n in misses.most_common()))


def kb_branches(limit: int | None) -> None:
    import time

    import psycopg

    from app.kb import branches
    from app.kb.pdl import kb_dsn

    t0 = time.monotonic()
    with psycopg.connect(kb_dsn(), autocommit=True) as conn:
        hp_up, cp_up, saved = branches.backfill_branches(conn, limit)
    print(f"Backfilled kb.company_branch in {time.monotonic() - t0:.1f}s: "
          f"homepages_updated={hp_up:,}, company_pages_updated={cp_up:,}, branch_rows={saved:,}")


def kb_load_overture(release: str | None, parts: int | None, local_dir: str | None,
                     homepages_only: bool) -> None:
    import time

    import psycopg

    from app.kb import branches
    from app.kb.pdl import kb_dsn

    t0 = time.monotonic()
    with psycopg.connect(kb_dsn(), autocommit=True) as conn:
        rel, matched, saved = branches.load_overture(conn, release=release, parts=parts,
                                                    local_dir=local_dir, homepages_only=homepages_only)
    print(f"Loaded Overture {rel} in {time.monotonic() - t0:.1f}s: matched={matched:,}, branch_rows={saved:,}")


def kb_tech(limit: int | None, dns: bool, from_db: bool, concurrency: int) -> None:
    import asyncio
    import time

    import psycopg

    from app.kb import tech
    from app.kb.pdl import kb_dsn

    if not dns and not from_db:
        dns = from_db = True
    with psycopg.connect(kb_dsn(), autocommit=True) as conn:
        conn.execute(tech.SCHEMA_SQL)
        if from_db:
            t0 = time.monotonic()
            from app.kb import branches, homepages

            bp_rows, bp_nums = homepages.backfill_phones(conn, limit)
            be_rows, be_cnt = homepages.backfill_emails(conn, limit)
            bh_rows, bc_rows, br_saved = branches.backfill_branches(conn, limit)
            idx = tech.TechIndex.load()
            h_rows = conn.execute(
                "SELECT domain, title, description, text FROM kb.homepage WHERE found LIMIT %s",
                (limit,),
            ).fetchall()
            saved_c = 0
            for dom, title, desc, text in h_rows:
                m = tech.detect_compliance(" ".join(x for x in (title, desc, text) if x))
                if m:
                    saved_c += tech.save_matches(conn, dom, m)
            p_saved = 0
            if conn.execute("SELECT to_regclass('kb.company_page')").fetchone()[0]:
                p_rows = conn.execute(
                    "SELECT domain, kind, title, text FROM kb.company_page LIMIT %s",
                    (limit * 3 if limit else None,),
                ).fetchall()
                for dom, kind, title, text in p_rows:
                    body = f"{title or ''}\n{text or ''}"
                    m = tech.detect_compliance(body)
                    if kind in ("careers", "job"):
                        m.extend(idx.scan_job_text(body))
                    if m:
                        p_saved += tech.save_matches(conn, dom, m)
            print(f"DB scan ({len(h_rows):,} homepages + company_pages) in {time.monotonic() - t0:.1f}s: "
                  f"phones={bp_rows:,} ({bp_nums:,} numbers), emails={be_rows:,} ({be_cnt:,} addresses), "
                  f"branches={br_saved:,} (hp+{bh_rows:,}, cp+{bc_rows:,}), "
                  f"homepage compliance={saved_c:,}, subpage tech/compliance={p_saved:,}", flush=True)
        if dns:
            t0 = time.monotonic()
            domains = [r[0] for r in conn.execute(
                "SELECT domain FROM kb.homepage WHERE found "
                "AND NOT EXISTS (SELECT 1 FROM kb.company_dns_run r WHERE r.domain = kb.homepage.domain) "
                "ORDER BY domain LIMIT %s",
                (limit,),
            ).fetchall()]
            print(f"Checking DNS MX/TXT for {len(domains):,} found domains ({concurrency} concurrent)...", flush=True)
            saved_dns = 0
            done_dns = 0

            def on_dns(domain: str, mx_hosts: list[str], matches: list[tech.TechMatch]) -> None:
                nonlocal saved_dns, done_dns
                done_dns += 1
                if matches:
                    saved_dns += tech.save_matches(conn, domain, matches)
                conn.execute(
                    "INSERT INTO kb.company_dns_run (domain, mx_hosts) VALUES (%s, %s) "
                    "ON CONFLICT (domain) DO UPDATE SET mx_hosts = EXCLUDED.mx_hosts, checked_at = now()",
                    (domain, ",".join(mx_hosts)[:300] or None),
                )
                if done_dns % 5000 == 0:
                    print(f"  DNS {done_dns:,}/{len(domains):,} checked, {saved_dns:,} tech rows saved", flush=True)

            checked, hits = asyncio.run(tech.scan_dns_domains(domains, concurrency=concurrency, on_result=on_dns))
            print(f"DNS scan finished in {time.monotonic() - t0:.1f}s: "
                  f"{checked:,} domains, {hits:,} matched ({saved_dns:,} rows)", flush=True)


def kb_classify(limit: int | None, again: bool, export_sample: int, export_path: str | None,
                teacher: str = "claude") -> None:
    import time
    from pathlib import Path

    import psycopg

    from app.kb import classify, train
    from app.kb.pdl import kb_dsn

    with psycopg.connect(kb_dsn(), autocommit=True) as conn:
        conn.execute(classify.SCHEMA_SQL)
        if export_sample:
            path = Path(export_path or "label_sample.csv")
            n = classify.export_sample(conn, path, export_sample)
            print(f"Wrote {n:,} labelled homepages to {path}.")
            return
        model_path = _label_model_path()
        if not model_path.is_file():
            sys.exit(f"No trained model at {model_path}: run kb-teach, then kb-train.")
        model = train.LabelModel.load(model_path)
        where = "h.found" + ("" if again else " AND l.domain IS NULL")
        rows = conn.execute(
            f"""SELECT h.domain, h.url, h.title, h.description, h.text,
                       (SELECT industry FROM kb.pdl_company c WHERE c.domain = h.domain
                        ORDER BY c.industry IS NULL LIMIT 1)
                FROM kb.homepage h
                LEFT JOIN kb.company_label l USING (domain) WHERE {where} ORDER BY h.domain"""  # noqa: S608
            + (" LIMIT %s" if limit else ""), (limit,) if limit else ()).fetchall()
        rows = [r for r in rows if classify.page_text(r[2], r[3], r[4])]
        if not rows:
            print("No homepages to label (kb-homepages fills kb.homepage; --again relabels).")
            if teacher:
                print(f"Pages labelled by {teacher} itself: {classify.apply_teacher(conn, teacher):,}")
            return
        print(f"Loading the model {model.embed_model} (downloaded once, about 250 MB)...", flush=True)
        embedder = classify.Embedder(model.embed_model)
        labeller = classify.Classifier(embedder, model)
        print(f"Labelling {len(rows):,} homepages...", flush=True)
        summary = classify.Summary()
        started = time.monotonic()
        batch = 256
        for i in range(0, len(rows), batch):
            chunk = rows[i:i + batch]
            labels = labeller.label([r[0] for r in chunk], [r[2:5] for r in chunk], [r[5] for r in chunk])
            with conn.transaction():
                for row, label in zip(chunk, labels, strict=True):
                    classify.save(conn, label, f"{embedder.name}+{model_path.name}", row[1])
                    summary.add(label)
            rate = summary.rows / max(1.0, time.monotonic() - started)
            print(f"  {summary.rows:,} labelled, {rate:.0f} pages/s", flush=True)
        taught = classify.apply_teacher(conn, teacher) if teacher else 0
    print(f"\n{(time.monotonic() - started) / 60:.1f} minutes")
    print(summary.report())
    if teacher:
        print(f"\nPages labelled by {teacher} itself (its label replaces the classifier's): {taught:,}")


def catalog_companies_house(org_id: str, name: str) -> None:
    import uuid

    from app.catalog_sources.companies_house import ingest_company

    with session_scope(uuid.UUID(org_id)) as db:
        result = ingest_company(db, uuid.UUID(org_id), name)
    print(f"Companies House: {result['companies']} company, {result['claims']} claims")


def catalog_usaspending(org_id: str, name: str, limit: int) -> None:
    import uuid

    from app.catalog_sources.usaspending import ingest_awards

    with session_scope(uuid.UUID(org_id)) as db:
        result = ingest_awards(db, uuid.UUID(org_id), name, limit=limit)
    print(f"USAspending: {result['companies']} exact recipient matches, {result['claims']} award claims")


def catalog_overture(org_id: str, path: str, bbox: list[float], release: str) -> None:
    import uuid
    from pathlib import Path

    from app.catalog_sources.overture import ingest_extract

    with session_scope(uuid.UUID(org_id)) as db:
        result = ingest_extract(db, uuid.UUID(org_id), Path(path), bbox=tuple(bbox), release=release)
    print(f"Overture Places: {result['records_read']} rows read, {result['companies']} candidate companies, "
          f"{result['claims']} claims placed in review")


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("create-admin", help="create or promote a platform admin")
    p.add_argument("email")
    p.add_argument("--password-stdin", action="store_true", help="read the password from stdin")
    p = sub.add_parser("refresh-sec", help="download or top up the local copy of SEC EDGAR's company list")
    p.add_argument("--limit", type=int, default=None, help="look up at most this many companies (largest first)")
    sub.add_parser("llm-status", help="show the OpenRouter key's free allowance, today's use and the free models")
    sub.add_parser("llm-test", help="send one tiny request to the best free model")
    sub.add_parser("llm-enable", help="switch model use back on after the cost guard switched it off")
    p = sub.add_parser("job-report", help="print a job's plan, warnings and what each source reported")
    p.add_argument("job_id")
    p = sub.add_parser("score", help="print the scorecard of one or more jobs side by side")
    p.add_argument("job_ids", nargs="+")
    p.add_argument("--key", help="answer key JSON: must_include / must_exclude companies")
    p = sub.add_parser("candidates", help="for each answer-key company: did a source name it, with its country")
    p.add_argument("job_id")
    p.add_argument("--key", required=True)
    sub.add_parser("eval-history", help="score every finished run of the test questions in eval/keys")
    p = sub.add_parser("eval-run", help="run every test question again with its latest plan and score it")
    p.add_argument("--wait", type=int, default=3600, help="seconds to wait for the runs (default 3600)")
    p.add_argument("--repeat", type=int, default=1, help="runs of each question, to see run-to-run noise")
    p.add_argument("--refresh-sources", action="store_true",
                   help="same plan, but with the sources today's planner rules pick (to measure a new source)")
    p.add_argument("--allow-short", action="store_true",
                   help="start even when today's free model allowance looks too small for the runs")
    p = sub.add_parser("sec-check", help="send one SEC full-text search and print SEC's answer")
    p.add_argument("product")
    p.add_argument("aliases", nargs="*", help="other names, as the planner's technology_aliases")
    p = sub.add_parser("kb-load-pdl", help="load the PDL free company dataset into kb.pdl_company and report coverage")
    p.add_argument("file", help="the downloaded file: CSV, pipe-delimited or JSON lines; .gz or .zip is fine")
    p.add_argument("--report-only", action="store_true", help="read the file and print coverage, load nothing")
    p.add_argument("--force", action="store_true", help="load even if the file has far fewer rows than the table")
    p = sub.add_parser("kb-load-companies-house", help="load the UK Companies House snapshot into kb.uk_company")
    p.add_argument("file", help="BasicCompanyDataAsOneFile-YYYY-MM-DD.zip (or the CSV inside it)")
    p.add_argument("--report-only", action="store_true", help="read the file and print coverage, load nothing")
    p.add_argument("--force", action="store_true", help="load even if the file has far fewer rows than the table")
    p = sub.add_parser("kb-homepages", help="read company homepages from Common Crawl into kb.homepage")
    p.add_argument("--limit", type=int, default=None, help="at most this many domains")
    p.add_argument("--country", default=None, help="only companies in these countries (ISO codes, e.g. IN or GB,IN,US)")
    p.add_argument("--biggest-first", action="store_true",
                   help="largest companies (PDL size) first, skipping domains already read")
    p.add_argument("--crawl", action="append", default=None,
                   help="Common Crawl crawl id; repeat for several (default: the newest --crawls)")
    p.add_argument("--crawls", type=int, default=3,
                   help="look in the newest N crawls, newest first, until one has the homepage (default 3)")
    p.add_argument("--concurrency", type=int, default=4, help="requests at a time (default 4; be gentle)")
    p.add_argument("--sample", action="store_true", help="a random sample of domains (for trials)")
    p.add_argument("--again", action="store_true", help="re-read the domains already in kb.homepage")
    p.add_argument("--own-lanes", type=int, default=128,
                   help="with --own-fetch: different sites fetched at a time (default 128)")
    p.add_argument("--own-fetch", action="store_true",
                   help="for homepages Common Crawl lacks: DNS check, then one robots-respecting fetch of the site")
    p = sub.add_parser("kb-teach", help="teacher labels for kb-train from a local open model (Ollama)")
    p.add_argument("--model", default="qwen2.5:7b", help="Ollama model (default qwen2.5:7b)")
    p.add_argument("--limit", type=int, default=200, help="homepages to label this run (default 200)")
    p.add_argument("--export-sample", type=int, default=0, metavar="N",
                   help="write N random teacher labels to a CSV for checking by hand, label nothing")
    p.add_argument("--out", default=None, help="the CSV for --export-sample (default teach_sample.csv)")
    p.add_argument("--export-pages", type=int, default=0, metavar="N",
                   help="write N pages not yet labelled by --model to a CSV, for labelling outside Ollama")
    p.add_argument("--tech-share", type=float, default=0.5,
                   help="share of exported pages from companies PDL files under Technology (default 0.5)")
    p.add_argument("--uncertain", action="store_true",
                   help="with --export-pages: the pages the trained classifier is least sure about first")
    p.add_argument("--biggest-first", action="store_true",
                   help="with --export-pages: the largest companies first (PDL size), for labelling them directly")
    p.add_argument("--country", default=None, help="with --biggest-first: only these countries, e.g. GB,IN,US")
    p.add_argument("--export-contacts", type=int, default=0, metavar="N",
                   help="write the contact/careers pages (kb-pages) of N sites --model has not read yet")
    p.add_argument("--import", dest="import_file", default=None, metavar="FILE",
                   help="read labels filled into an --export-pages CSV, saved under --model (e.g. claude)")
    p.add_argument("--same-pages-as", default=None, metavar="MODEL",
                   help="label only pages MODEL already labelled, to compare two models on the same pages")
    p = sub.add_parser("kb-train", help="train the homepage classifier on the teacher labels and report its quality")
    p.add_argument("--teacher", default="qwen2.5:7b", help="whose labels to learn from (default qwen2.5:7b)")
    p = sub.add_parser("kb-load-gleif", help="load the GLEIF Golden Copy LEI2 snapshot into kb.gleif_company")
    p.add_argument("file", help="GLEIF golden-copy CSV or .zip")
    p.add_argument("--report-only", action="store_true", help="scan the file and report coverage, load nothing")
    p.add_argument("--force", action="store_true", help="load even if the file has far fewer rows than the table")
    p = sub.add_parser("kb-load-sec", help="load SEC EDGAR bulk company metadata into kb.sec_company")
    p.add_argument("tickers", help="company_tickers_exchange.json")
    p.add_argument("submissions", help="submissions.zip")
    p.add_argument("--report-only", action="store_true", help="scan the files and report coverage, load nothing")
    p.add_argument("--force", action="store_true", help="load even if the file has far fewer rows than the table")
    p = sub.add_parser("kb-load-sec-facts", help="load SEC EDGAR companyfacts.zip XBRL financials")
    p.add_argument("file", nargs="?", default=None, help="optional local companyfacts.zip path")
    p = sub.add_parser("kb-load-uk-accounts", help="load UK Companies House Accounts iXBRL archives")
    p.add_argument("paths", nargs="*", help="optional local ZIP file(s) or folder")
    p.add_argument("--latest", type=int, default=1, help="download latest N daily archives if no paths given")
    p = sub.add_parser("kb-load-usaspending", help="load USAspending Prime Contracts bulk archive")
    p.add_argument("file", nargs="?", default=None, help="optional local contracts ZIP path")
    p.add_argument("--fy", type=int, default=2026, help="fiscal year archive (default 2026)")
    p = sub.add_parser("kb-load-mca", help="load India MCA / RoC company master CSV or ZIP")
    p.add_argument("file", help="India MCA CSV or .zip path")
    p.add_argument("--force", action="store_true", help="load even if fewer rows than existing table")
    p = sub.add_parser("kb-load-people", help="load Wikidata corporate leadership into kb.company_person")
    p.add_argument("--refresh", action="store_true", help="refetch Wikidata SPARQL instead of using cache")
    p = sub.add_parser("kb-link-sec", help="resolve domains/QIDs for all listed SEC issuers via Wikidata")
    p.add_argument("--refresh", action="store_true", help="ignore cached Wikidata SPARQL JSON")
    p = sub.add_parser("kb-load-sp500", help="link S&P 500 constituents via SEC+Wikidata and enrich into Brahman")
    p.add_argument("--skip-crawl", action="store_true", help="only update kb.sp500_member and sec_company websites")
    p.add_argument("--refresh", action="store_true", help="ignore cached Wikidata SPARQL JSON and refetch")
    p.add_argument("--no-js", action="store_true", help="skip Playwright SPA rendering fallback")
    p.add_argument("--homepages-only", action="store_true",
                   help="fetch missing homepages, DNS, and labels without crawling subpages")
    p = sub.add_parser("kb-pages", help="read each company's contact page, careers page and a few job ads")
    p.add_argument("--limit", type=int, default=10000, help="at most this many sites (default 10000)")
    p.add_argument("--country", default=None, help="only companies in these countries, e.g. GB,IN,US")
    p.add_argument("--lanes", type=int, default=128, help="different sites at a time (default 128)")
    p.add_argument("--no-tech", action="store_true", help="skip webappanalyzer and job-ad tech extraction")
    p.add_argument("--retry-misses", action="store_true",
                   help="retry prior home_unreadable, no_contact_or_careers_link, and linked_pages_unreadable sites")
    p.add_argument("--js-fallback", action="store_true",
                   help="use headless Chromium when static HTML looks like an empty JS SPA")
    p = sub.add_parser("kb-branches", help="extract plain-text addresses and populate kb.company_branch from DB")
    p.add_argument("--limit", type=int, default=None, help="at most this many homepages")
    p = sub.add_parser("kb-load-overture", help="load physical branch addresses from Overture Maps Places")
    p.add_argument("--release", default=None, help="Overture release tag (default latest from STAC)")
    p.add_argument("--parts", type=int, default=None, help="only read the first N Parquet shards")
    p.add_argument("--local-dir", default=None, help="read downloaded *.parquet files from this folder")
    p.add_argument("--homepages-only", action="store_true", help="match only against kb.homepage domains")
    p = sub.add_parser("kb-tech", help="populate kb.company_tech from DNS MX/TXT and existing crawled pages")
    p.add_argument("--limit", type=int, default=None, help="at most this many domains")
    p.add_argument("--dns", action="store_true", help="run async DNS MX and TXT checks")
    p.add_argument("--from-db", action="store_true", help="scan existing kb.homepage and kb.company_page rows")
    p.add_argument("--concurrency", type=int, default=256, help="concurrent DNS queries (default 256)")
    p = sub.add_parser("kb-classify", help="label homepages with the trained classifier")
    p.add_argument("--limit", type=int, default=None, help="at most this many homepages")
    p.add_argument("--again", action="store_true", help="relabel homepages that already have a label")
    p.add_argument("--export-sample", type=int, default=0, metavar="N",
                   help="write N random labelled homepages to a CSV for checking by hand, label nothing")
    p.add_argument("--out", default=None, help="the CSV for --export-sample (default label_sample.csv)")
    p.add_argument("--teacher", default="claude",
                   help="pages this teacher labelled keep its label, not the classifier's (default claude; '' = none)")
    p = sub.add_parser("catalog-companies-house", help="import exact-match UK legal facts from Companies House")
    p.add_argument("org_id")
    p.add_argument("company_name")
    p = sub.add_parser("catalog-usaspending", help="import exact federal award-recipient signals by company name")
    p.add_argument("org_id")
    p.add_argument("company_name")
    p.add_argument("--limit", type=int, default=20)
    p = sub.add_parser(
        "catalog-overture", help="import a bounded Overture Places extract as review-only location claims"
    )
    p.add_argument("org_id")
    p.add_argument("geojson")
    p.add_argument("--bbox", nargs=4, required=True, type=float, metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    p.add_argument("--release", default="latest")
    args = parser.parse_args()
    if args.cmd == "kb-teach":
        return kb_teach(args.model, args.limit, args.export_sample, args.out, args.same_pages_as, args.export_pages,
                        args.import_file, args.tech_share, args.uncertain, args.biggest_first, args.country,
                        args.export_contacts)
    if args.cmd == "kb-train":
        return kb_train(args.teacher)
    if args.cmd == "kb-load-gleif":
        return kb_load_gleif(args.file, args.report_only, args.force)
    if args.cmd == "kb-load-sec":
        return kb_load_sec(args.tickers, args.submissions, args.report_only, args.force)
    if args.cmd == "kb-load-sec-facts":
        return kb_load_sec_facts(args.file)
    if args.cmd == "kb-load-uk-accounts":
        return kb_load_uk_accounts(args.paths or None, args.latest)
    if args.cmd == "kb-load-usaspending":
        return kb_load_usaspending(args.file, args.fy)
    if args.cmd == "kb-load-mca":
        return kb_load_mca(args.file, args.force)
    if args.cmd == "kb-load-people":
        return kb_load_people(args.refresh)
    if args.cmd == "kb-link-sec":
        return kb_link_sec(args.refresh)
    if args.cmd == "kb-load-sp500":
        return kb_load_sp500(args.skip_crawl, args.refresh, not args.no_js, args.homepages_only)
    if args.cmd == "kb-pages":
        return kb_pages(args.limit, args.country, args.lanes, with_tech=not args.no_tech,
                        retry_misses=args.retry_misses, js_fallback=args.js_fallback)
    if args.cmd == "kb-branches":
        return kb_branches(args.limit)
    if args.cmd == "kb-load-overture":
        return kb_load_overture(args.release, args.parts, args.local_dir, args.homepages_only)
    if args.cmd == "kb-tech":
        return kb_tech(args.limit, args.dns, args.from_db, args.concurrency)
    if args.cmd == "kb-classify":
        return kb_classify(args.limit, args.again, args.export_sample, args.out, args.teacher)
    if args.cmd == "kb-load-companies-house":
        return kb_load_companies_house(args.file, args.report_only, args.force)
    if args.cmd == "kb-homepages":
        return kb_homepages(args.limit, args.country, args.crawl, args.concurrency, args.sample, args.crawls,
                            args.again, args.own_fetch, args.biggest_first, args.own_lanes)
    if args.cmd == "kb-load-pdl":
        return kb_load_pdl(args.file, args.report_only, args.force)
    if args.cmd == "job-report":
        return job_report(args.job_id)
    if args.cmd == "score":
        return score(args.job_ids, args.key)
    if args.cmd == "sec-check":
        return sec_check(args.product, args.aliases)
    if args.cmd == "candidates":
        return candidates(args.job_id, args.key)
    if args.cmd == "eval-history":
        return eval_history()
    if args.cmd == "eval-run":
        return eval_run(args.wait, args.repeat, args.refresh_sources, args.allow_short)
    if args.cmd.startswith("llm-"):
        llm(args.cmd)
    elif args.cmd == "refresh-sec":
        refresh_sec(args.limit)
    elif args.cmd == "create-admin":
        create_admin(args.email.lower(), sys.stdin.readline().strip() if args.password_stdin else None)
    elif args.cmd == "catalog-companies-house":
        return catalog_companies_house(args.org_id, args.company_name)
    elif args.cmd == "catalog-usaspending":
        return catalog_usaspending(args.org_id, args.company_name, args.limit)
    elif args.cmd == "catalog-overture":
        return catalog_overture(args.org_id, args.geojson, args.bbox, args.release)


if __name__ == "__main__":
    main()
