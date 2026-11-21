"""Company homepages from Common Crawl, for the fields PDL does not have.

For each company website in kb.pdl_company this looks the homepage up in Common Crawl's URL index,
reads that one record from Common Crawl's archive (a byte-range request, so no traffic reaches
the company's site) and keeps what the page says about the company:

- title, meta description and the start of the visible text: input for the micro-sector and
  product-or-service labels;
- the company's general mailboxes (info@, sales@, contact@... on its own domain), never one
  person's address;
- postal addresses the site publishes as schema.org data or in an <address> element.

Every row keeps the page URL, the date Common Crawl fetched it and the crawl it came from.

Domains shared by many PDL rows (business.site, instagram.com, linktr.ee...) are hosting
platforms or directories, not one company's site, so they are skipped: see SHARED_DOMAIN_LIMIT.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import random
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx

from app.extract.deterministic import (
    ROLE_WORD_RE,
    _addresses,
    _description,
    _emails,
    parse_page,
)

INDEX = "https://index.commoncrawl.org"
DATA = "https://data.commoncrawl.org"
# A domain listed by more PDL rows than this is a platform or directory, not a company's own site.
# The first load had 4,925 shared domains; the big ones (business.site 261,829, instagram.com
# 175,609, linktr.ee 50,337...) are all platforms, while company groups share a domain a few times.
SHARED_DOMAIN_LIMIT = 20
TEXT_CHARS = 5000
MAX_RECORD_BYTES = 5_000_000


@dataclass
class Homepage:
    domain: str
    found: bool
    crawl: str = ""
    url: str = ""
    fetched_at: str = ""  # when Common Crawl fetched the page (its WARC date)
    title: str = ""
    description: str = ""
    text: str = ""
    emails: list[dict] = field(default_factory=list)
    addresses: list[dict] = field(default_factory=list)
    error: str = ""


def select_domains(conn, limit: int | None = None, iso2: str | None = None, sample: bool = False) -> list[str]:
    """Distinct company domains to read, without platforms; a random sample for trials."""
    sql = ("SELECT domain FROM (SELECT DISTINCT domain FROM kb.pdl_company "  # noqa: S608 - fixed text, values are parameters
           "WHERE domain IS NOT NULL AND domain_rows <= %s" + (" AND iso2 = %s" if iso2 else "") + ") d")
    params: list = [SHARED_DOMAIN_LIMIT] + ([iso2.upper()] if iso2 else [])
    if sample:
        sql += " ORDER BY random()"
    if limit:
        sql += " LIMIT %s"
        params.append(limit)
    return [r[0] for r in conn.execute(sql, params).fetchall()]


async def latest_crawl(client: httpx.AsyncClient) -> str:
    response = await client.get(f"{INDEX}/collinfo.json")
    response.raise_for_status()
    return response.json()[0]["id"]  # newest first


async def _get(client: httpx.AsyncClient, url: str, headers: dict | None = None, tries: int = 5) -> httpx.Response:
    """Common Crawl asks clients to back off on 503 and 429 rather than retry at once."""
    for attempt in range(tries):
        response = await client.get(url, headers=headers)
        if response.status_code not in (429, 503) or attempt == tries - 1:
            return response
        await asyncio.sleep(min(60, 2 ** attempt + random.random()))  # noqa: S311 - jitter, not security
    return response


async def lookup(client: httpx.AsyncClient, crawl: str, domain: str) -> dict | None:
    """The best homepage capture of `domain` in one crawl: a 200 HTML page with the shortest URL."""
    response = await _get(
        client, f"{INDEX}/{crawl}-index?url={domain}/&output=json&filter=status:200&filter=mime:text/html&limit=20")
    if response.status_code == 404:  # "No Captures found"
        return None
    response.raise_for_status()
    rows = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    rows = [r for r in rows if int(r.get("length", 0)) <= MAX_RECORD_BYTES]
    if not rows:
        return None
    return min(rows, key=lambda r: (len(r["url"]), r["url"].startswith("http://"), r["url"]))


def parse_warc(data: bytes) -> tuple[dict[str, str], str]:
    """(WARC headers, decoded HTML) of one gzipped WARC response record."""
    raw = gzip.decompress(data)
    warc_head, _, rest = raw.partition(b"\r\n\r\n")
    http_head, _, body = rest.partition(b"\r\n\r\n")
    headers = {}
    for line in warc_head.decode("latin-1").split("\r\n")[1:]:
        key, _, value = line.partition(":")
        headers[key.strip().lower()] = value.strip()
    charset = "utf-8"
    match = re.search(rb"charset=([\w-]+)", http_head, re.I) or re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)",
                                                                         body[:4000], re.I)
    if match:
        charset = match.group(1).decode("ascii", "ignore") or "utf-8"
    try:
        html = body.decode(charset, errors="replace")
    except LookupError:
        html = body.decode("utf-8", errors="replace")
    return headers, html


def extract(domain: str, crawl: str, url: str, fetched_at: str, html: str) -> Homepage:
    doc = parse_page(url, html)
    descriptions = _description(doc)
    emails = [{"email": c.value.lower(), "method": c.method} for c in _emails(doc)
              if ROLE_WORD_RE.search(c.value.split("@")[0].lower())]
    addresses = [{"address": c.value, "method": c.method} for c in _addresses(doc, "address")
                 if c.method in ("jsonld", "html_address")]
    return Homepage(
        domain=domain, found=True, crawl=crawl, url=url, fetched_at=fetched_at,
        title=doc.title[:500], description=(descriptions[0].value if descriptions else "")[:2000],
        text=doc.text[:TEXT_CHARS], emails=emails, addresses=addresses,
    )


async def read_homepage(client: httpx.AsyncClient, crawl: str, domain: str) -> Homepage:
    try:
        capture = await lookup(client, crawl, domain)
        if capture is None:
            return Homepage(domain, found=False, crawl=crawl)
        start = int(capture["offset"])
        end = start + int(capture["length"]) - 1
        response = await _get(client, f"{DATA}/{capture['filename']}", headers={"Range": f"bytes={start}-{end}"})
        response.raise_for_status()
        headers, html = parse_warc(response.content)
        return extract(domain, crawl, capture["url"], headers.get("warc-date", capture.get("timestamp", "")), html)
    except (httpx.HTTPError, OSError, ValueError, KeyError) as exc:
        return Homepage(domain, found=False, crawl=crawl, error=f"{type(exc).__name__}: {exc}"[:300])


@dataclass
class Summary:
    domains: int = 0
    found: int = 0
    errors: Counter = field(default_factory=Counter)
    with_description: int = 0
    with_text: int = 0
    with_email: int = 0
    with_address: int = 0

    def add(self, page: Homepage) -> None:
        self.domains += 1
        if page.error:
            self.errors[page.error.split(":")[0]] += 1
        if not page.found:
            return
        self.found += 1
        self.with_description += bool(page.description)
        self.with_text += len(page.text) >= 200
        self.with_email += bool(page.emails)
        self.with_address += bool(page.addresses)

    def report(self) -> str:
        def pct(n: int, of: int) -> str:
            return f"{n:>10,}  {100 * n / of:5.1f}%" if of else f"{n:>10,}"

        lines = [
            f"Domains tried:                {self.domains:>10,}",
            f"Homepage in Common Crawl:     {pct(self.found, self.domains)}",
            f"  with a meta description:    {pct(self.with_description, self.found)}",
            f"  with 200+ chars of text:    {pct(self.with_text, self.found)}",
            f"  with a company mailbox:     {pct(self.with_email, self.found)}",
            f"  with a postal address:      {pct(self.with_address, self.found)}",
        ]
        if self.errors:
            lines += ["Errors:"] + [f"  {k}: {n:,}" for k, n in self.errors.most_common()]
        return "\n".join(lines)


SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS kb;
CREATE TABLE IF NOT EXISTS kb.homepage (
    domain text PRIMARY KEY,
    found boolean NOT NULL,
    crawl text NOT NULL,
    url text,
    fetched_at text,
    title text,
    description text,
    text text,
    emails jsonb NOT NULL DEFAULT '[]',
    addresses jsonb NOT NULL DEFAULT '[]',
    error text,
    collected_at timestamptz NOT NULL DEFAULT now()
);
"""


def save(conn, page: Homepage) -> None:
    conn.execute(
        """INSERT INTO kb.homepage (domain, found, crawl, url, fetched_at, title, description, text, emails,
                                    addresses, error, collected_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (domain) DO UPDATE SET found = EXCLUDED.found, crawl = EXCLUDED.crawl, url = EXCLUDED.url,
               fetched_at = EXCLUDED.fetched_at, title = EXCLUDED.title, description = EXCLUDED.description,
               text = EXCLUDED.text, emails = EXCLUDED.emails, addresses = EXCLUDED.addresses,
               error = EXCLUDED.error, collected_at = EXCLUDED.collected_at""",
        (page.domain, page.found, page.crawl, page.url or None, page.fetched_at or None, page.title or None,
         page.description or None, (page.text or None) and page.text.replace("\x00", ""),
         json.dumps(page.emails), json.dumps(page.addresses), page.error or None, datetime.now(UTC)),
    )


async def collect(domains: list[str], crawl: str | None, on_page: Callable[[Homepage], None],
                  concurrency: int = 4, client: httpx.AsyncClient | None = None,
                  user_agent: str = "heimdallr-kb") -> str:
    """Read every domain's homepage, `concurrency` at a time, handing each result to `on_page`."""
    own = client is None
    client = client or httpx.AsyncClient(timeout=60, headers={"User-Agent": user_agent}, follow_redirects=True)
    try:
        crawl = crawl or await latest_crawl(client)
        queue: asyncio.Queue[str] = asyncio.Queue()
        for d in domains:
            queue.put_nowait(d)

        async def worker() -> None:
            while not queue.empty():
                on_page(await read_homepage(client, crawl, queue.get_nowait()))

        await asyncio.gather(*(worker() for _ in range(concurrency)))
        return crawl
    finally:
        if own:
            await client.aclose()
