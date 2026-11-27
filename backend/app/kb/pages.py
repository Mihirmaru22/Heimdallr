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
import inspect
import json
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from app.crawl.fetcher import Fetcher, FetchError, FetchResult
from app.crawl.robots import RobotsCache
from app.extract.deterministic import extract_leadership, parse_page
from app.kb.homepages import PARSE_CHARS, contacts_from

TEXT_CHARS = 4000
CONTACT_TEXT_CHARS = 16000
SECURITY_TEXT_CHARS = 12000
JOB_ADS = 2

CONTACT_WORDS = ("contact", "kontakt", "contacto", "contato", "contatti", "contactez", "impressum", "imprint",
                 "get in touch", "reach us", "nous joindre", "contattaci", "iletisim", "contactenos")
CAREER_WORDS = ("career", "jobs", "job openings", "karriere", "carriere", "carrière", "empleo", "trabaja con",
                "vacatures", "vacanc", "join us", "join our team", "work with us", "work for us", "hiring",
                "recruit", "stellenangebote", "stellen", "lavora con", "opportunit")
LOCATION_WORDS = ("locations", "our locations", "offices", "our offices", "global offices", "regional offices",
                  "branches", "our branches", "find us", "where to find", "where we are", "store locator",
                  "showrooms", "campuses")
LEADERSHIP_WORDS = ("leadership", "executive team", "management team", "our team",
                    "board of directors", "founders", "executives")
SECURITY_WORDS = ("security", "trust center", "trust-center", "trust centre", "compliance",
                  "certifications", "infosec", "soc 2", "soc2", "iso 27001", "hipaa")
JOB_BOARDS = ("greenhouse.io", "lever.co", "myworkdayjobs.com", "smartrecruiters.com", "workable.com",
              "bamboohr.com", "ashbyhq.com", "jobvite.com", "icims.com", "teamtailor.com", "recruitee.com",
              "personio.de", "personio.com", "breezy.hr", "jazzhr.com", "applytojob.com", "successfactors.com",
              "taleo.net", "oraclecloud.com", "zohorecruit.com", "freshteam.com", "darwinbox.in", "keka.com")
TRUST_CENTERS = ("vanta.com", "drata.com", "safebase.io", "secureframe.com", "conveyor.com", "whistic.com")
JOB_PATH_RE = re.compile(r"/(jobs?|positions?|vacanc(y|ies)|openings?|careers?)/[^/?#]+", re.I)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS kb.company_page (
    domain text NOT NULL,
    kind text NOT NULL,          -- contact, careers, job, security
    url text NOT NULL,
    title text,
    text text,
    emails jsonb,
    addresses jsonb,
    phones jsonb NOT NULL DEFAULT '[]',
    fetched_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (domain, url)
);
ALTER TABLE kb.company_page ADD COLUMN IF NOT EXISTS phones jsonb NOT NULL DEFAULT '[]';
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
    phones: list = field(default_factory=list)
    people: list = field(default_factory=list)


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _on_site(url: str, domain: str) -> bool:
    host = _host(url)
    return host == domain or host.endswith("." + domain)


def _in_hosts(url: str, hosts: tuple[str, ...]) -> bool:
    host = _host(url)
    return any(host == h or host.endswith("." + h) for h in hosts)


def _on_board(url: str) -> bool:
    return _in_hosts(url, JOB_BOARDS)


def _score(url: str, text: str, words: tuple[str, ...]) -> int:
    """2 for a word in the link text, 1 for one in the address; 0 if neither."""
    text, path = text.lower(), urlsplit(url).path.lower()
    if any(w in text for w in words):
        return 2
    return 1 if any(w.replace(" ", "-") in path or w.replace(" ", "") in path for w in words) else 0


def _security_score(url: str, text: str, domain: str) -> int:
    if _in_hosts(url, TRUST_CENTERS):
        low = f"{url} {text}".lower()
        return 2 if ("trust" in low or "security" in low or "compliance" in low) else 0
    if not _on_site(url, domain):
        return 0
    score = _score(url, text, SECURITY_WORDS)
    if score:
        return score
    host, path = _host(url), urlsplit(url).path.rstrip("/").lower()
    return 1 if host.startswith(("security.", "trust.")) or path == "/trust" else 0


def choose_links(links: list[tuple[str, str]], domain: str) -> dict[str, str]:
    """The best contact, careers and security/trust links on a homepage; shorter paths win ties."""
    best: dict[str, tuple[int, int, str]] = {}
    for url, text in links:
        if not url.startswith(("http://", "https://")):
            continue
        candidates = (
            ("contact", _score(url, text, CONTACT_WORDS) if _on_site(url, domain) else 0),
            ("locations", _score(url, text, LOCATION_WORDS) if _on_site(url, domain) else 0),
            ("careers", 2 if _on_board(url) else (_score(url, text, CAREER_WORDS) if _on_site(url, domain) else 0)),
            ("security", _security_score(url, text, domain)),
            ("leadership", _score(url, text, LEADERSHIP_WORDS) if _on_site(url, domain) else 0),
        )
        for kind, score in candidates:
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


_SITEMAP_LOC_RE = re.compile(r"<loc>\s*(https?://[^<\s]+)\s*</loc>", re.I)
_SPA_HINT_RE = re.compile(r'(?:__NEXT_DATA__|data-reactroot|ng-version|id=["\'](?:root|app|__next)["\'])', re.I)


def _playwright_shell() -> str | None:
    root = Path.home() / ".cache" / "ms-playwright"
    if not root.is_dir():
        return None
    for match in sorted(root.glob("chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell"),
                        reverse=True):
        if match.is_file():
            return str(match)
    return None


def page_from(domain: str, kind: str, url: str, html: str,
              countries: Sequence[str] | None = None) -> tuple[CompanyPage, list[tuple[str, str]]]:
    doc = parse_page(url, html[:PARSE_CHARS])
    emails, addresses, phones = contacts_from(doc, countries=countries)
    if kind in ("contact", "locations"):
        limit = CONTACT_TEXT_CHARS
    elif kind == "security":
        limit = SECURITY_TEXT_CHARS
    else:
        limit = TEXT_CHARS
    ppl = extract_leadership(doc) if kind == "leadership" else []
    return (
        CompanyPage(domain, kind, url, doc.title[:500], doc.text[:limit], emails, addresses, phones, ppl),
        doc.links,
    )


def page_reader(
    client: httpx.AsyncClient,
    user_agent: str,
    concurrency: int = 128,
    resolver=None,
    on_fetch: Callable[[str, str, str, str, list[tuple[str, str]]], Awaitable[None] | None] | None = None,
    countries_by_domain: dict[str, list[str]] | None = None,
    js_render: Callable[[str], Awaitable[str | None]] | None = None,
) -> Callable[[str, str], Awaitable[tuple[list[CompanyPage], str]]]:
    fetcher = Fetcher(client, resolver=resolver)
    robots = RobotsCache(fetcher, user_agent, attempts=2)
    xml_fetcher = Fetcher(client, resolver=resolver, allowed_types=("application/xml", "text/xml", "text/plain"))
    slots = asyncio.Semaphore(concurrency)

    async def emit(domain: str, kind: str, url: str, html: str, headers: list[tuple[str, str]]) -> None:
        if on_fetch is None:
            return
        if inspect.iscoroutinefunction(on_fetch):
            await on_fetch(domain, kind, url, html, headers)
        else:
            await asyncio.to_thread(on_fetch, domain, kind, url, html, headers)

    async def get(url: str) -> FetchResult | None:
        try:
            if not (await robots.check(url)).allowed:
                return None
            result = await fetcher.fetch(url, attempts=2)
        except FetchError:
            return None
        return result if result.is_html else None

    async def sitemap_links(home_url: str, domain: str) -> dict[str, str]:
        parts = urlsplit(home_url)
        candidates = robots.sitemaps(home_url)[:2] or [f"{parts.scheme}://{parts.netloc}/sitemap.xml"]
        for sm_url in candidates:
            try:
                if not (await robots.check(sm_url)).allowed:
                    continue
                res = await xml_fetcher.fetch(sm_url, attempts=1)
            except FetchError:
                continue
            locs = _SITEMAP_LOC_RE.findall(res.text[:1_000_000])
            if locs:
                found = choose_links([(loc, "") for loc in locs[:2500]], domain)
                if found:
                    return found
        return {}

    async def read(domain: str, home_url: str) -> tuple[list[CompanyPage], str]:
        countries = (countries_by_domain or {}).get(domain)
        async with slots:
            home_res = await get(home_url)
            if home_res is None:
                return [], "home_unreadable"
            home_html = home_res.text
            await emit(domain, "home", home_res.final_url, home_html, home_res.headers)
            _home, links = await asyncio.to_thread(page_from, domain, "home", home_url, home_html, countries)
            chosen = choose_links(links, domain)
            if not chosen:
                chosen = await sitemap_links(home_res.final_url or home_url, domain)
            spa_candidate = len(links) < 10 or _SPA_HINT_RE.search(home_html[:50_000])
            if not chosen and js_render is not None and spa_candidate:
                rendered = await js_render(home_res.final_url or home_url)
                if rendered:
                    _rhome, rlinks = await asyncio.to_thread(page_from, domain, "home", home_url, rendered, countries)
                    chosen = choose_links(rlinks, domain)
            elif "contact" not in chosen and chosen:
                extra = await sitemap_links(home_res.final_url or home_url, domain)
                if "contact" in extra:
                    chosen["contact"] = extra["contact"]
            if not chosen:
                return [], "no_contact_or_careers_link"
            pages: list[CompanyPage] = []
            seen_urls: set[str] = set()
            for kind, url in chosen.items():
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                sub_res = await get(url)
                if sub_res is None:
                    continue
                body = sub_res.text
                await emit(domain, kind, sub_res.final_url, body, sub_res.headers)
                page, page_links = await asyncio.to_thread(page_from, domain, kind, url, body, countries)
                pages.append(page)
                if kind == "careers":
                    for job_url in job_links(page_links, url):
                        job_res = await get(job_url)
                        if job_res is not None:
                            job = job_res.text
                            await emit(domain, "job", job_res.final_url, job, job_res.headers)
                            pages.append(
                                (await asyncio.to_thread(page_from, domain, "job", job_url, job, countries))[0]
                            )
            return pages, "" if pages else "linked_pages_unreadable"

    return read


def save(conn, domain: str, pages: list[CompanyPage], miss: str) -> None:
    now = datetime.now(UTC)
    for p in pages:
        conn.execute(
            """INSERT INTO kb.company_page (domain, kind, url, title, text, emails, addresses, phones, fetched_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (domain, url) DO UPDATE SET kind = EXCLUDED.kind, title = EXCLUDED.title,
                   text = EXCLUDED.text, emails = EXCLUDED.emails, addresses = EXCLUDED.addresses,
                   phones = EXCLUDED.phones, fetched_at = EXCLUDED.fetched_at""",
            (domain, p.kind, p.url.replace("\x00", ""), p.title.replace("\x00", ""), p.text.replace("\x00", ""),
             json.dumps(p.emails).replace("\\u0000", ""), json.dumps(p.addresses).replace("\\u0000", ""),
             json.dumps(p.phones).replace("\\u0000", ""), now))
    conn.execute(
        """INSERT INTO kb.company_page_run (domain, found, miss, tried_at) VALUES (%s, %s, %s, %s)
           ON CONFLICT (domain) DO UPDATE SET found = EXCLUDED.found, miss = EXCLUDED.miss,
               tried_at = EXCLUDED.tried_at""",
        (domain, ",".join(sorted({p.kind for p in pages})) or None, miss or None, now))
    if pages:
        from app.kb import branches

        branches.save_pages(conn, domain, pages)
        lead_rows = [
            (domain, None, None, name, role, None, None, None, None, "website_leadership", p.url)
            for p in pages if getattr(p, "people", None)
            for name, role in p.people
        ]
        if lead_rows and conn.execute("SELECT to_regclass('kb.company_person')").fetchone()[0]:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM kb.company_person WHERE domain = %s AND source = 'website_leadership'",
                    (domain,),
                )
                cur.executemany(
                    """INSERT INTO kb.company_person (
                           domain, cik, company_number, full_name, raw_role,
                           person_qid, officer_id, start_date, end_date, source, source_url
                       ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    lead_rows,
                )


def select_sites(conn, limit: int, countries: str | None = None,
                 retry_misses: bool = False) -> list[tuple[str, str]]:
    """(domain, homepage url) of found homepages not yet tried (or missed when retry_misses=True)."""
    from app.kb.teach import size_rank

    wanted = [c.strip().upper() for c in (countries or "").split(",") if c.strip()]
    if retry_misses:
        rows = conn.execute(
            """SELECT h.domain, h.url, array_agg(p.size), bool_or(p.iso2 = ANY(%s)), bool_or(h.crawl = %s)
               FROM kb.homepage h JOIN kb.pdl_company p ON p.domain = h.domain
               WHERE h.found AND h.url IS NOT NULL
                 AND EXISTS (SELECT 1 FROM kb.company_page_run r WHERE r.domain = h.domain
                             AND r.miss IN ('home_unreadable', 'no_contact_or_careers_link',
                                            'linked_pages_unreadable'))
               GROUP BY h.domain, h.url""",
            (wanted, "own"),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT h.domain, h.url, array_agg(p.size), bool_or(p.iso2 = ANY(%s)), bool_or(h.crawl = %s)
               FROM kb.homepage h JOIN kb.pdl_company p ON p.domain = h.domain
               WHERE h.found AND h.url IS NOT NULL
                 AND NOT EXISTS (SELECT 1 FROM kb.company_page_run r WHERE r.domain = h.domain)
               GROUP BY h.domain, h.url""",
            (wanted, "own"),
        ).fetchall()
    rows = [r for r in rows if not wanted or r[3]]
    rows.sort(key=lambda r: (not r[4], -max(size_rank(x) for x in r[2]), r[0]))
    return [(r[0], r[1]) for r in rows[:limit]]
