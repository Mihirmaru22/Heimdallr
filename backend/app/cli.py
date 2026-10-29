"""Command-line helpers: `python -m app.cli create-admin EMAIL` (prompts for a password) and
`python -m app.cli refresh-sec` (downloads SEC EDGAR's company list for the sec_edgar source) and
`python -m app.cli llm-status | llm-test | llm-enable` (the free OpenRouter models) and
`python -m app.cli job-report JOB_ID` / `sec-check PRODUCT` (what a run planned and what each source answered)."""

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
    args = parser.parse_args()
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
