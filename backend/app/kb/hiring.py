"""Structured hiring & department counts from ATS job boards (Greenhouse, Lever, Ashby)."""

from __future__ import annotations

import asyncio
import json
import re
from collections import Counter
from urllib.parse import urlsplit

import httpx

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS kb.company_hiring (
    domain text PRIMARY KEY,
    ats text NOT NULL,
    board_slug text NOT NULL,
    total_open_jobs integer NOT NULL,
    departments jsonb NOT NULL DEFAULT '{}'::jsonb,
    source_url text NOT NULL,
    fetched_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS company_hiring_jobs_idx ON kb.company_hiring (total_open_jobs DESC);
"""

_BAD_SLUGS = {"", "jobs", "apply", "internal", "embed", "v0", "v1", "careers"}


def parse_ats_board(url: str) -> tuple[str, str, str] | None:
    """Return (ats, slug, api_url) for a Greenhouse, Lever, or Ashby board URL."""
    parts = urlsplit((url or "").strip())
    host = (parts.hostname or "").lower()
    segs = [s for s in parts.path.split("/") if s]
    if not segs:
        return None
    slug = re.sub(r"[^A-Za-z0-9_.-]", "", segs[0])
    if not slug or slug.lower() in _BAD_SLUGS:
        return None
    if host in ("boards.greenhouse.io", "job-boards.greenhouse.io"):
        return ("greenhouse", slug, f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=false")
    if host in ("boards.eu.greenhouse.io", "job-boards.eu.greenhouse.io"):
        return ("greenhouse", slug, f"https://boards-api.eu.greenhouse.io/v1/boards/{slug}/jobs?content=false")
    if host == "jobs.lever.co":
        return ("lever", slug, f"https://api.lever.co/v0/postings/{slug}?mode=json")
    if host == "jobs.ashbyhq.com":
        return ("ashby", slug, f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    return None


def extract_department_counts(ats: str, payload: object) -> tuple[int, dict[str, int]]:
    """Aggregate structured department -> open job count from official ATS JSON responses."""
    depts: Counter[str] = Counter()
    total = 0
    if ats == "greenhouse" and isinstance(payload, dict):
        jobs = payload.get("jobs") or []
        total = len(jobs)
        for job in jobs:
            for d in job.get("departments") or ():
                name = str(d.get("name") or "").strip()
                if name:
                    depts[name] += 1
                    break
            else:
                depts["Unspecified"] += 1
    elif ats == "lever" and isinstance(payload, list):
        total = len(payload)
        for job in payload:
            cats = job.get("categories") or {}
            name = str(cats.get("department") or cats.get("team") or "").strip() or "Unspecified"
            depts[name] += 1
    elif ats == "ashby" and isinstance(payload, dict):
        jobs = payload.get("jobs") or []
        total = len(jobs)
        for job in jobs:
            name = str(job.get("department") or job.get("team") or "").strip() or "Unspecified"
            depts[name] += 1
    return total, dict(depts.most_common())


async def fetch_ats_hiring(boards: list[tuple[str, str, str, str]], concurrency: int = 16,
                           user_agent: str = "HeimdallrKB/1.0") -> list[tuple]:
    """Fetch official ATS job counts & departments asynchronously for (domain, ats, slug, api_url)."""
    slots = asyncio.Semaphore(concurrency)
    results: list[tuple] = []

    async def worker(client: httpx.AsyncClient, domain: str, ats: str, slug: str, api_url: str) -> None:
        async with slots:
            try:
                resp = await client.get(api_url)
                if resp.status_code != 200:
                    return
                total, depts = extract_department_counts(ats, resp.json())
            except (httpx.HTTPError, ValueError):
                return
        results.append((domain, ats, slug, total, json.dumps(depts), api_url))

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(15.0, connect=6.0),
        headers={"User-Agent": user_agent},
        follow_redirects=True,
    ) as client:
        await asyncio.gather(*(worker(client, d, a, s, u) for d, a, s, u in boards))
    return results


def load_from_company_pages(conn, user_agent: str = "HeimdallrKB/1.0") -> tuple[int, int]:
    """Discover Greenhouse/Lever/Ashby boards from kb.company_page and populate kb.company_hiring."""
    conn.execute(SCHEMA_SQL)
    rows = conn.execute(
        "SELECT DISTINCT domain, url FROM kb.company_page "
        "WHERE url ILIKE '%greenhouse.io%' OR url ILIKE '%jobs.lever.co%' OR url ILIKE '%jobs.ashbyhq.com%'"
    ).fetchall()
    by_dom: dict[str, tuple[str, str, str, str]] = {}
    for dom, url in rows:
        parsed = parse_ats_board(url)
        if parsed and dom not in by_dom:
            ats, slug, api_url = parsed
            by_dom[dom] = (dom, ats, slug, api_url)
    boards = sorted(by_dom.values())
    if not boards:
        return 0, 0
    out = asyncio.run(fetch_ats_hiring(boards, user_agent=user_agent))
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO kb.company_hiring (
                   domain, ats, board_slug, total_open_jobs, departments, source_url, fetched_at
               )
               VALUES (%s, %s, %s, %s, %s::jsonb, %s, now())
               ON CONFLICT (domain) DO UPDATE SET
                   ats = EXCLUDED.ats, board_slug = EXCLUDED.board_slug,
                   total_open_jobs = EXCLUDED.total_open_jobs, departments = EXCLUDED.departments,
                   source_url = EXCLUDED.source_url, fetched_at = now()""",
            out,
        )
    return len(boards), len(out)
