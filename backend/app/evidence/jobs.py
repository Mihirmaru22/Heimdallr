"""Proof in a company's own job ads: "Teamcenter administrator", "experience with our SAP S/4HANA landscape".

Many companies publish their openings on a hosted board (Greenhouse, Lever, Ashby, SmartRecruiters, Workable),
each with a free public API meant for showing jobs on the company's site. A board is used only when the company's
own website links to it or embeds it, so the board is known to be theirs; board names are never guessed. Robots
rules of the API hosts are respected like any other page.
"""

from __future__ import annotations

import html
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.evidence.quotes import document_text

MAX_JOBS = 200  # openings read per board
MAX_DETAILS = 15  # SmartRecruiters needs one request per opening for its text

# (board, pattern of a link or embed on the company's site); the first group is the board's name.
BOARD_LINKS = [
    ("Greenhouse", re.compile(r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board(?:/js)?\?for=)?"
                              r"([A-Za-z0-9_-]+)")),
    ("Lever", re.compile(r"jobs\.lever\.co/([A-Za-z0-9_.-]+)")),
    ("Lever EU", re.compile(r"jobs\.eu\.lever\.co/([A-Za-z0-9_.-]+)")),
    ("Ashby", re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_.%-]+)")),
    ("SmartRecruiters", re.compile(r"(?:careers|jobs)\.smartrecruiters\.com/([A-Za-z0-9_-]+)")),
    ("Workable", re.compile(r"apply\.workable\.com/([A-Za-z0-9_-]+)")),
]
NOT_BOARDS = {"embed", "api", "j", "jobs", "v1", "js", "static", "assets", "careers", "oneclick-ui"}


@dataclass(frozen=True)
class Board:
    ats: str
    name: str

    @property
    def label(self) -> str:
        return f"{self.ats} board \"{self.name}\""


@dataclass
class Job:
    title: str
    text: str  # title and description as plain text
    url: str
    date: str  # YYYY-MM-DD or ""


def find_boards(page_html: str) -> list[Board]:
    """Job boards a company's page links to or embeds, in page order, one per board."""
    out: list[Board] = []
    for ats, pattern in BOARD_LINKS:
        for m in pattern.finditer(page_html):
            name = m.group(1).strip(".-")
            board = Board(ats, name)
            if name and name.lower() not in NOT_BOARDS and board not in out:
                out.append(board)
    return out


def _day(value: Any) -> str:
    if isinstance(value, (int, float)) and value > 10**11:  # Lever: milliseconds since 1970
        return datetime.fromtimestamp(value / 1000, UTC).date().isoformat()
    if isinstance(value, str) and re.match(r"^\d{4}-\d{2}-\d{2}", value):
        return value[:10]
    return ""


def _text(title: str, *parts: Any) -> str:
    body = " ".join(document_text(html.unescape(p)) for p in parts if isinstance(p, str) and p)
    return f"{title.strip()}. {body}".strip()


FetchJson = Callable[[str], Awaitable[Any]]


async def read_board(board: Board, fetch_json: FetchJson) -> list[Job]:
    """The board's open jobs. Raises whatever fetch_json raises when the board cannot be read."""
    n = board.name
    jobs: list[Job] = []
    if board.ats == "Greenhouse":
        body = await fetch_json(f"https://boards-api.greenhouse.io/v1/boards/{n}/jobs?content=true")
        for j in (body or {}).get("jobs", [])[:MAX_JOBS]:
            jobs.append(Job(j.get("title", ""), _text(j.get("title", ""), j.get("content")),
                            j.get("absolute_url") or f"https://boards.greenhouse.io/{n}", _day(j.get("updated_at"))))
    elif board.ats in ("Lever", "Lever EU"):
        api = "api.eu.lever.co" if board.ats == "Lever EU" else "api.lever.co"
        body = await fetch_json(f"https://{api}/v0/postings/{n}?mode=json&limit={MAX_JOBS}")
        for j in (body if isinstance(body, list) else [])[:MAX_JOBS]:
            lists = [f"{x.get('text', '')}: {x.get('content', '')}" for x in j.get("lists") or []
                     if isinstance(x, dict)]
            jobs.append(Job(j.get("text", ""), _text(j.get("text", ""), j.get("descriptionPlain"), *lists,
                                                     j.get("additionalPlain")),
                            j.get("hostedUrl") or f"https://jobs.lever.co/{n}", _day(j.get("createdAt"))))
    elif board.ats == "Ashby":
        body = await fetch_json(f"https://api.ashbyhq.com/posting-api/job-board/{n}")
        for j in (body or {}).get("jobs", [])[:MAX_JOBS]:
            jobs.append(Job(j.get("title", ""), _text(j.get("title", ""), j.get("descriptionPlain")
                                                      or j.get("descriptionHtml")),
                            j.get("jobUrl") or j.get("applyUrl") or f"https://jobs.ashbyhq.com/{n}",
                            _day(j.get("publishedAt"))))
    elif board.ats == "SmartRecruiters":
        base = f"https://api.smartrecruiters.com/v1/companies/{n}/postings"
        listing = await fetch_json(f"{base}?limit=100")
        for p in (listing or {}).get("content", [])[:MAX_DETAILS]:
            d = await fetch_json(f"{base}/{p.get('id')}")
            sections = ((d or {}).get("jobAd") or {}).get("sections") or {}
            texts = [s.get("text") for s in sections.values() if isinstance(s, dict)]
            jobs.append(Job(p.get("name", ""), _text(p.get("name", ""), *texts),
                            (d or {}).get("postingUrl") or f"https://jobs.smartrecruiters.com/{n}",
                            _day(p.get("releasedDate"))))
    elif board.ats == "Workable":
        body = await fetch_json(f"https://apply.workable.com/api/v1/widget/accounts/{n}?details=true")
        for j in (body or {}).get("jobs", [])[:MAX_JOBS]:
            jobs.append(Job(j.get("title", ""), _text(j.get("title", ""), j.get("description"),
                                                      j.get("full_description")),
                            j.get("url") or f"https://apply.workable.com/{n}",
                            _day(j.get("published_on") or j.get("created_at"))))
    return [j for j in jobs if j.title or j.text]
