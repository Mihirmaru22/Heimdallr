"""A company's contact page, careers page and a few job ads, found from its homepage's own links.

The contact page (or Impressum) carries the address, the company phone and mailbox; the careers
page and its job ads name the software the company works with (technographics). For each site:
one fetch of the homepage for its links, then the best contact link, the best careers link (on the
site, or on a known job board such as Greenhouse or Lever) and up to JOB_ADS job ads linked from
the careers page. Same rules as the homepage fetch (app.kb.sitefetch): robots.txt obeyed, one try
per request, refusals never retried. Nothing is guessed: a page is read only if a link points to it.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx

from app.crawl.fetcher import Fetcher, FetchError
from app.crawl.robots import RobotsCache
from app.extract.deterministic import ROLE_WORD_RE, _addresses, _emails, parse_page
from app.kb.homepages import PARSE_CHARS

TEXT_CHARS = 4000
JOB_ADS = 2

CONTACT_WORDS = ("contact", "kontakt", "contacto", "contato", "contatti", "contactez", "impressum", "imprint",
                 "get in touch", "reach us", "nous joindre", "contattaci", "iletisim", "contactenos")
CAREER_WORDS = ("career", "jobs", "job openings", "karriere", "carriere", "carrière", "empleo", "trabaja con",
                "vacatures", "vacanc", "join us", "join our team", "work with us", "work for us", "hiring",
                "recruit", "stellenangebote", "stellen", "lavora con", "opportunit")
JOB_BOARDS = ("greenhouse.io", "lever.co", "myworkdayjobs.com", "smartrecruiters.com", "workable.com",
              "bamboohr.com", "ashbyhq.com", "jobvite.com", "icims.com", "teamtailor.com", "recruitee.com",
              "personio.de", "personio.com", "breezy.hr", "jazzhr.com", "applytojob.com", "successfactors.com",
              "taleo.net", "oraclecloud.com", "zohorecruit.com", "freshteam.com", "darwinbox.in", "keka.com")
JOB_PATH_RE = re.compile(r"/(jobs?|positions?|vacanc(y|ies)|openings?|careers?)/[^/?#]+", re.I)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS kb.company_page (
    domain text NOT NULL,
    kind text NOT NULL,          -- contact, careers, job
    url text NOT NULL,
    title text,
    text text,
    emails jsonb,
    addresses jsonb,
    fetched_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (domain, url)
);
CREATE TABLE IF NOT EXISTS kb.company_page_run (
    domain text PRIMARY KEY,     -- one row per site tried, so a site is not tried again
    found text,                  -- kinds found, e.g. "contact,careers,job"
    miss text,
    tried_at timestamptz NOT NULL DEFAULT now()
);
"""


@dataclass
class CompanyPage:
    domain: str
    kind: str
    url: str
    title: str = ""
    text: str = ""
    emails: list = field(default_factory=list)
    addresses: list = field(default_factory=list)


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _on_site(url: str, domain: str) -> bool:
    host = _host(url)
    return host == domain or host.endswith("." + domain)


def _on_board(url: str) -> bool:
    host = _host(url)
    return any(host == b or host.endswith("." + b) for b in JOB_BOARDS)


def _score(url: str, text: str, words: tuple[str, ...]) -> int:
    """2 for a word in the link text, 1 for one in the address; 0 if neither."""
    text, path = text.lower(), urlsplit(url).path.lower()
    if any(w in text for w in words):
        return 2
    return 1 if any(w.replace(" ", "-") in path or w.replace(" ", "") in path for w in words) else 0


def choose_links(links: list[tuple[str, str]], domain: str) -> dict[str, str]:
    """The best contact and careers link among a homepage's links; shorter paths win ties."""
    best: dict[str, tuple[int, int, str]] = {}
    for url, text in links:
        if not url.startswith(("http://", "https://")):
            continue
        for kind, words, allowed in (("contact", CONTACT_WORDS, _on_site(url, domain)),
                                     ("careers", CAREER_WORDS, _on_site(url, domain) or _on_board(url))):
            score = _score(url, text, words) if allowed else 0
            if kind == "careers" and _on_board(url):
                score = max(score, 2)
            if score and (kind not in best or (score, -len(url)) > best[kind][:2]):
                best[kind] = (score, -len(url), url)
    return {kind: url for kind, (_s, _l, url) in best.items()}


def job_links(links: list[tuple[str, str]], careers_url: str, limit: int = JOB_ADS) -> list[str]:
    """Links on a careers page that look like single job ads (on its site or a job board)."""
    site = _host(careers_url)
    out: list[str] = []
    for url, _text in links:
        if url.rstrip("/") == careers_url.rstrip("/") or url in out:
            continue
        if (_host(url) == site or _on_board(url)) and JOB_PATH_RE.search(urlsplit(url).path):
            out.append(url)
        if len(out) >= limit:
            break
    return out


def page_from(domain: str, kind: str, url: str, html: str) -> tuple[CompanyPage, list[tuple[str, str]]]:
    doc = parse_page(url, html[:PARSE_CHARS])
    emails = [{"email": c.value.lower(), "method": c.method} for c in _emails(doc)
              if ROLE_WORD_RE.search(c.value.split("@")[0].lower())]
    addresses = [{"address": c.value, "method": c.method} for c in _addresses(doc, "address")
                 if c.method in ("jsonld", "html_address")]
    return CompanyPage(domain, kind, url, doc.title[:500], doc.text[:TEXT_CHARS], emails, addresses), doc.links


def page_reader(client: httpx.AsyncClient, user_agent: str, concurrency: int = 128,
                resolver=None) -> Callable[[str, str], Awaitable[tuple[list[CompanyPage], str]]]:
    fetcher = Fetcher(client, resolver=resolver)
    robots = RobotsCache(fetcher, user_agent, attempts=1)
    slots = asyncio.Semaphore(concurrency)

    async def get(url: str) -> str | None:
        try:
            if not (await robots.check(url)).allowed:
                return None
            result = await fetcher.fetch(url, attempts=1)
        except FetchError:
            return None
        return result.text if result.is_html else None

    async def read(domain: str, home_url: str) -> tuple[list[CompanyPage], str]:
        async with slots:
            html = await get(home_url)
            if html is None:
                return [], "home_unreadable"
            _home, links = await asyncio.to_thread(page_from, domain, "home", home_url, html)
            chosen = choose_links(links, domain)
            if not chosen:
                return [], "no_contact_or_careers_link"
            pages: list[CompanyPage] = []
            for kind, url in chosen.items():
                body = await get(url)
                if body is None:
                    continue
                page, page_links = await asyncio.to_thread(page_from, domain, kind, url, body)
                pages.append(page)
                if kind == "careers":
                    for job_url in job_links(page_links, url):
                        job = await get(job_url)
                        if job is not None:
                            pages.append((await asyncio.to_thread(page_from, domain, "job", job_url, job))[0])
            return pages, "" if pages else "linked_pages_unreadable"

    return read


def save(conn, domain: str, pages: list[CompanyPage], miss: str) -> None:
    now = datetime.now(UTC)
    for p in pages:
        conn.execute(
            """INSERT INTO kb.company_page (domain, kind, url, title, text, emails, addresses, fetched_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (domain, url) DO UPDATE SET kind = EXCLUDED.kind, title = EXCLUDED.title,
                   text = EXCLUDED.text, emails = EXCLUDED.emails, addresses = EXCLUDED.addresses,
                   fetched_at = EXCLUDED.fetched_at""",
            (domain, p.kind, p.url, p.title, p.text.replace("\x00", ""), json.dumps(p.emails),
             json.dumps(p.addresses), now))
    conn.execute(
        """INSERT INTO kb.company_page_run (domain, found, miss, tried_at) VALUES (%s, %s, %s, %s)
           ON CONFLICT (domain) DO UPDATE SET found = EXCLUDED.found, miss = EXCLUDED.miss,
               tried_at = EXCLUDED.tried_at""",
        (domain, ",".join(sorted({p.kind for p in pages})) or None, miss or None, now))


def select_sites(conn, limit: int, countries: str | None = None) -> list[tuple[str, str]]:
    """(domain, homepage url) of found homepages not yet tried, biggest companies first."""
    from app.kb.teach import size_rank

    wanted = [c.strip().upper() for c in (countries or "").split(",") if c.strip()]
    rows = conn.execute(
        """SELECT h.domain, h.url, array_agg(p.size), bool_or(p.iso2 = ANY(%s))
           FROM kb.homepage h JOIN kb.pdl_company p ON p.domain = h.domain
           WHERE h.found AND h.url IS NOT NULL
             AND NOT EXISTS (SELECT 1 FROM kb.company_page_run r WHERE r.domain = h.domain)
           GROUP BY h.domain, h.url""", (wanted,)).fetchall()
    rows = [r for r in rows if not wanted or r[3]]
    rows.sort(key=lambda r: (-max(size_rank(x) for x in r[2]), r[0]))
    return [(r[0], r[1]) for r in rows[:limit]]
