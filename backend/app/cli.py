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
    long = {n for n in names if n == "key: missing" or n.startswith("key: lost at")}  # printed under the table
    names = [n for n in names if n not in long]
    width = max(len(n) for n in names)
    print(" " * width + "  " + "  ".join(j[:8].ljust(22) for j in job_ids))
    for n in names:
        print(n.ljust(width) + "  " + "  ".join(str(c.get(n, "")).ljust(22) for c in cards))
    for n in long:
        for j, c in zip(job_ids, cards, strict=True):
            if n in c:
                print(f"{n} ({j[:8]}): {c[n]}")


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


def kb_homepages(limit: int | None, iso2: str | None, crawl: list[str] | None, concurrency: int, sample: bool,
                 crawl_count: int, again: bool, own_fetch: bool, biggest_first: bool = False) -> None:
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

        def on_page(page) -> None:
            homepages.save(conn, page)
            summary.add(page)
            if summary.domains % 500 == 0:
                rate = summary.domains / max(1.0, time.monotonic() - started)
                print(f"  {summary.domains:,} done, {summary.found:,} found, {rate:.1f} sites/s", flush=True)

        def on_crawl(name: str) -> None:
            print(f"Crawl {name}: getting its index map (cluster.idx, downloaded once, a few hundred MB)...",
                  flush=True)

        async def run() -> list[str]:
            settings = get_settings()
            fetch_own = None
            site_client = None
            if own_fetch:
                from concurrent.futures import ThreadPoolExecutor

                from app.kb.sitefetch import OWN_CONCURRENCY, own_fetcher

                # DNS lookups run in the default thread pool (about 14 threads); with 64 sites at a time
                # they would queue there and run into dns_alive's timeout, reading live sites as dead.
                asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(2 * OWN_CONCURRENCY))

                site_client = httpx.AsyncClient(  # short: one try per site, a slow site is recorded as slow
                    timeout=httpx.Timeout(10.0, connect=5.0),
                    headers={"User-Agent": settings.user_agent}, follow_redirects=False)
                fetch_own = own_fetcher(site_client, settings.user_agent)
            try:
                return await homepages.collect(
                    domains, crawl, on_page, Path(settings.data_dir), concurrency, user_agent=settings.user_agent,
                    on_crawl=on_crawl, crawl_count=crawl_count, own_fetch=fetch_own)
            finally:
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
             uncertain: bool = False) -> None:
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
        if export_pages:
            path = Path(export_path or "teach_pages.csv")
            n = teach.export_pages(conn, path, export_pages, model, tech_share, uncertain)
            print(f"Wrote {n:,} pages to {path} "
                  f"(not yet labelled by {model}).")
            return
        if import_file:
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
               WHERE t.error IS NULL AND t.model = %s""", (teacher,)
        ).fetchall()
    rows = [r for r in rows if classify.page_text(r[0], r[1], r[2])]
    if len(rows) < 100:
        sys.exit(f"Only {len(rows)} teacher labels from {teacher}; run kb-teach first (a few thousand pages).")
    print(f"Embedding {len(rows):,} labelled homepages with {classify.MODEL}...", flush=True)
    embedder = classify.Embedder()
    vectors = embedder([classify.page_text(r[0], r[1], r[2]) for r in rows])
    labels = [{"real_page": r[3], "tech_company": r[4], "micro_sector": r[5], "offering": r[6], "industry": r[7]}
              for r in rows]
    model = train.train(list(zip(vectors, labels, strict=True)), embedder.name)
    path = _label_model_path()
    model.save(path)
    print(f"Saved {path}\n")
    for report in model.reports:
        print("\n".join(report.lines()) + "\n")


def kb_classify(limit: int | None, again: bool, export_sample: int, export_path: str | None) -> None:
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
            labels = labeller.label([r[0] for r in chunk], [classify.page_text(r[2], r[3], r[4]) for r in chunk],
                                    [r[5] for r in chunk])
            with conn.transaction():
                for row, label in zip(chunk, labels, strict=True):
                    classify.save(conn, label, f"{embedder.name}+{model_path.name}", row[1])
                    summary.add(label)
            rate = summary.rows / max(1.0, time.monotonic() - started)
            print(f"  {summary.rows:,} labelled, {rate:.0f} pages/s", flush=True)
    print(f"\n{(time.monotonic() - started) / 60:.1f} minutes")
    print(summary.report())


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
    p.add_argument("--import", dest="import_file", default=None, metavar="FILE",
                   help="read labels filled into an --export-pages CSV, saved under --model (e.g. claude)")
    p.add_argument("--same-pages-as", default=None, metavar="MODEL",
                   help="label only pages MODEL already labelled, to compare two models on the same pages")
    p = sub.add_parser("kb-train", help="train the homepage classifier on the teacher labels and report its quality")
    p.add_argument("--teacher", default="qwen2.5:7b", help="whose labels to learn from (default qwen2.5:7b)")
    p = sub.add_parser("kb-classify", help="label homepages with the trained classifier")
    p.add_argument("--limit", type=int, default=None, help="at most this many homepages")
    p.add_argument("--again", action="store_true", help="relabel homepages that already have a label")
    p.add_argument("--export-sample", type=int, default=0, metavar="N",
                   help="write N random labelled homepages to a CSV for checking by hand, label nothing")
    p.add_argument("--out", default=None, help="the CSV for --export-sample (default label_sample.csv)")
    args = parser.parse_args()
    if args.cmd == "kb-teach":
        return kb_teach(args.model, args.limit, args.export_sample, args.out, args.same_pages_as, args.export_pages,
                        args.import_file, args.tech_share, args.uncertain)
    if args.cmd == "kb-train":
        return kb_train(args.teacher)
    if args.cmd == "kb-classify":
        return kb_classify(args.limit, args.again, args.export_sample, args.out)
    if args.cmd == "kb-load-companies-house":
        return kb_load_companies_house(args.file, args.report_only, args.force)
    if args.cmd == "kb-homepages":
        return kb_homepages(args.limit, args.country, args.crawl, args.concurrency, args.sample, args.crawls,
                            args.again, args.own_fetch, args.biggest_first)
    if args.cmd == "kb-load-pdl":
        return kb_load_pdl(args.file, args.report_only, args.force)
    if args.cmd == "job-report":
        return job_report(args.job_id)
    if args.cmd == "score":
        return score(args.job_ids, args.key)
    if args.cmd == "sec-check":
        return sec_check(args.product, args.aliases)
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


if __name__ == "__main__":
    main()
