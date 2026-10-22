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


def sec_check(product_name: str) -> None:
    """One SEC full-text search exactly as the sec_filings source sends it, with SEC's raw answer."""
    from datetime import date, timedelta

    import httpx

    from app.config import get_settings
    from app.discovery.sec_filings import SEARCH
    from app.evidence.products import product_for

    product = product_for(product_name)
    today = date.today()
    params = {"q": " ".join(f'"{n}"' for n in product.names), "dateRange": "custom",
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
    p = sub.add_parser("sec-check", help="send one SEC full-text search and print SEC's answer")
    p.add_argument("product")
    args = parser.parse_args()
    if args.cmd == "job-report":
        return job_report(args.job_id)
    if args.cmd == "sec-check":
        return sec_check(args.product)
    if args.cmd.startswith("llm-"):
        llm(args.cmd)
    elif args.cmd == "refresh-sec":
        refresh_sec(args.limit)
    elif args.cmd == "create-admin":
        create_admin(args.email.lower(), sys.stdin.readline().strip() if args.password_stdin else None)


if __name__ == "__main__":
    main()
