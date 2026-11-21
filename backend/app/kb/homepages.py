"""Company homepages from Common Crawl, for the fields PDL does not have.

For each company website in kb.pdl_company this finds the homepage in Common Crawl's URL index
and reads that one record from Common Crawl's archive (byte-range requests, so no traffic reaches
the company's site), then keeps what the page says about the company:

- title, meta description and the start of the visible text: input for the micro-sector and
  product-or-service labels;
- the company's general mailboxes (info@, sales@, contact@... on its own domain), never one
  person's address;
- postal addresses the site publishes as schema.org data or in an <address> element.

Every row keeps the page URL, the date Common Crawl fetched it and the crawl it came from.

The index is read from Common Crawl's own files, not its index server (index.commoncrawl.org,
which is often overloaded): the small cluster.idx file is downloaded once per crawl and searched
locally, and only the index block holding a domain is fetched, by byte range, from
data.commoncrawl.org. Domains are processed in index order, so neighbours share a block.

Domains shared by many PDL rows (business.site, instagram.com, linktr.ee...) are hosting
platforms or directories, not one company's site, so they are skipped: see SHARED_DOMAIN_LIMIT.
"""

from __future__ import annotations

import asyncio
import bisect
import gzip
import json
import random
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit

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
    miss: str = ""  # why no homepage was found: no_capture, redirect_unfollowed, error_status, not_html
    redirected_to: str = ""  # the homepage moved here (another path or another domain)


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


async def latest_crawls(client: httpx.AsyncClient, count: int = 1) -> list[str]:
    """The newest `count` crawl ids, newest first, from the index server's list or, when that server
    is down, the crawl list on data.commoncrawl.org."""
    try:
        response = await _get(client, f"{INDEX}/collinfo.json", tries=2)
        response.raise_for_status()
        ids = [c["id"] for c in response.json()]  # newest first
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        response = await _get(client, f"{DATA}/crawl-data/index.html")
        response.raise_for_status()
        ids = sorted(set(re.findall(r"CC-MAIN-\d{4}-\d{2}", response.text)), reverse=True)
    if not ids:
        raise ValueError("no crawl ids found")
    return ids[:count]


# When Common Crawl pushes back (403 "Request blocked" from its CDN, 429, 503), every worker pauses,
# not just the one that was refused: slowing down is what the server is asking for.
_pause_until = 0.0
SLOW_DOWN = (403, 429, 503)
RETRY = (502, 504)


async def _get(client: httpx.AsyncClient, url: str, headers: dict | None = None, tries: int = 5) -> httpx.Response:
    """GET with back-off: on 403/429/503 all requests pause (30 s, doubling); on 502/504 and timeouts
    this request retries after a short wait."""
    global _pause_until
    loop = asyncio.get_running_loop()
    for attempt in range(tries):
        wait = _pause_until - loop.time()
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            response = await client.get(url, headers=headers)
        except httpx.TimeoutException:
            if attempt == tries - 1:
                raise
            await asyncio.sleep(min(60, 2 ** attempt + random.random()))  # noqa: S311 - jitter, not security
            continue
        if response.status_code in SLOW_DOWN and attempt < tries - 1:
            _pause_until = max(_pause_until, loop.time() + min(300, 30 * 2 ** attempt))
            continue
        if response.status_code in RETRY and attempt < tries - 1:
            await asyncio.sleep(min(60, 2 ** attempt + random.random()))  # noqa: S311 - jitter, not security
            continue
        return response
    return response


def surt_key(domain: str) -> str:
    """Common Crawl's sort key for a site's homepage: www.acme.co.uk/ -> uk,co,acme)/"""
    return ",".join(reversed(domain.lower().strip(".").split("."))) + ")/"


def url_key(url: str) -> str:
    """Common Crawl's sort key for any URL: https://www.acme.com/En/?a=1 -> com,acme)/en/?a=1"""
    parts = urlsplit(url if "://" in url else f"http://{url}")
    host = re.sub(r"^www\d*\.", "", (parts.hostname or "").lower().strip("."))
    key = ",".join(reversed(host.split("."))) + ")" + ((parts.path or "/").lower())
    return key + (f"?{parts.query.lower()}" if parts.query else "")


class ClusterIndex:
    """cluster.idx: one line per block of about 3,000 index lines, giving the first key of the block
    and where the block sits (file, offset, length). Searching it locally tells which block to read."""

    def __init__(self, lines: list[str]):
        self.keys: list[str] = []
        self.blocks: list[tuple[str, int, int]] = []
        for line in lines:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 4:
                continue
            self.keys.append(parts[0].split(" ")[0])
            self.blocks.append((parts[1], int(parts[2]), int(parts[3])))

    @classmethod
    def from_file(cls, path: Path) -> ClusterIndex:
        with open(path, encoding="utf-8") as f:
            return cls(f.readlines())

    def blocks_for(self, key: str) -> list[tuple[str, int, int]]:
        i = bisect.bisect_left(self.keys, key) - 1  # the block whose first key is before ours
        i = max(i, 0)
        out = [self.blocks[i]]
        j = i + 1  # captures of one URL can run on into the next blocks
        while j < len(self.keys) and self.keys[j] <= key:
            out.append(self.blocks[j])
            j += 1
        return out


async def cluster_index(client: httpx.AsyncClient, crawl: str, data_dir: Path) -> ClusterIndex:
    path = data_dir / "commoncrawl" / crawl / "cluster.idx"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_suffix(".part")
        async with client.stream("GET", f"{DATA}/cc-index/collections/{crawl}/indexes/cluster.idx") as response:
            response.raise_for_status()
            with open(part, "wb") as f:
                async for chunk in response.aiter_bytes(1 << 20):
                    f.write(chunk)
        part.rename(path)
    return ClusterIndex.from_file(path)


class IndexReader:
    """Finds a domain's homepage captures by reading only the index blocks that can hold it."""

    def __init__(self, client: httpx.AsyncClient, crawl: str, index: ClusterIndex, keep_blocks: int = 64):
        self.client, self.crawl, self.index = client, crawl, index
        self.blocks: dict[tuple[str, int, int], asyncio.Future] = {}
        self.keep_blocks = keep_blocks

    async def _block(self, block: tuple[str, int, int]) -> list[str]:
        future = self.blocks.get(block)
        if future is None:  # neighbouring domains share blocks; fetch each once
            future = asyncio.get_running_loop().create_future()
            self.blocks[block] = future
            while len(self.blocks) > self.keep_blocks:
                self.blocks.pop(next(iter(self.blocks)))
            try:
                name, offset, length = block
                response = await _get(self.client, f"{DATA}/cc-index/collections/{self.crawl}/indexes/{name}",
                                      headers={"Range": f"bytes={offset}-{offset + length - 1}"})
                response.raise_for_status()
                future.set_result(gzip.decompress(response.content).decode("utf-8", "replace").splitlines())
            except Exception as exc:  # noqa: BLE001 - every waiter gets the same failure
                self.blocks.pop(block, None)  # a later domain tries this block again
                future.set_exception(exc)
        return await future

    async def _records(self, key: str, host_prefix: str) -> tuple[list[dict], list[dict]]:
        """(captures of exactly `key`, captures of other pages on the same host) in the blocks for `key`."""
        exact, same_host = [], []
        for block in self.index.blocks_for(key):
            for line in await self._block(block):
                surt, _, rest = line.partition(" ")
                if surt != key and not surt.startswith(host_prefix):
                    continue
                try:
                    record = json.loads(rest.partition(" ")[2])
                except ValueError:
                    continue
                (exact if surt == key else same_host).append(record)
        return exact, same_host

    @staticmethod
    def _good(record: dict) -> bool:
        mime = record.get("mime-detected") or record.get("mime") or ""
        return (record.get("status") == "200" and "html" in mime
                and int(record.get("length", 0)) <= MAX_RECORD_BYTES)

    @staticmethod
    def _best(records: list[dict]) -> dict:
        return max(records, key=lambda r: (r["url"].startswith("https://"), r.get("timestamp", "")))

    async def lookup(self, domain: str) -> tuple[dict | None, str, str]:
        """(best homepage capture, why none was found, where the homepage redirected to).

        A homepage that redirects (/ -> /en/, or to a new domain) is followed for up to two hops.
        With no usable capture of the homepage itself, the shortest page captured on the same host
        (/index.html, /home) stands in for it."""
        key = surt_key(domain)
        redirected_to = ""
        for _hop in range(3):
            host_prefix = key.split(")", 1)[0] + ")"
            exact, same_host = await self._records(key, host_prefix)
            good = [r for r in exact if self._good(r)]
            if good:
                return self._best(good), "", redirected_to
            moves = [r for r in exact if str(r.get("status", "")).startswith("3") and r.get("redirect")]
            if moves:
                move = self._best(moves)
                redirected_to = urljoin(move["url"], move["redirect"])
                key = url_key(redirected_to)
                continue
            stand_in = [r for r in same_host if self._good(r) and urlsplit(r["url"]).path.count("/") <= 1]
            if stand_in:
                return min(stand_in, key=lambda r: len(r["url"])), "", redirected_to
            if not exact and not same_host:
                return None, "no_capture", redirected_to
            if any(str(r.get("status", "")).startswith("3") for r in exact):
                return None, "redirect_unfollowed", redirected_to
            if any(r.get("status") == "200" for r in exact):
                return None, "not_html", redirected_to
            return None, "error_status", redirected_to
        return None, "redirect_unfollowed", redirected_to


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


async def read_homepage(client: httpx.AsyncClient, readers: list[IndexReader], domain: str) -> Homepage:
    """Try the newest crawl first, then older ones, until one has the homepage."""
    misses: list[str] = []
    redirected_to = ""
    for reader in readers:
        try:
            capture, miss, moved = await reader.lookup(domain)
            redirected_to = redirected_to or moved
            if capture is None:
                misses.append(miss)
                continue
            start = int(capture["offset"])
            end = start + int(capture["length"]) - 1
            response = await _get(client, f"{DATA}/{capture['filename']}", headers={"Range": f"bytes={start}-{end}"})
            response.raise_for_status()
            headers, html = parse_warc(response.content)
            page = extract(domain, reader.crawl, capture["url"],
                           headers.get("warc-date", capture.get("timestamp", "")), html)
            page.redirected_to = redirected_to
            return page
        except (httpx.HTTPError, OSError, ValueError, KeyError, EOFError) as exc:
            return Homepage(domain, found=False, crawl=reader.crawl, error=f"{type(exc).__name__}: {exc}"[:300])
    # The most telling reason: any crawl that saw the site beats "never captured".
    miss = next((m for m in misses if m != "no_capture"), "no_capture")
    return Homepage(domain, found=False, crawl=readers[0].crawl, miss=miss, redirected_to=redirected_to)


@dataclass
class Summary:
    domains: int = 0
    found: int = 0
    errors: Counter = field(default_factory=Counter)
    misses: Counter = field(default_factory=Counter)
    by_crawl: Counter = field(default_factory=Counter)
    redirected: int = 0
    with_description: int = 0
    with_text: int = 0
    with_email: int = 0
    with_address: int = 0

    def add(self, page: Homepage) -> None:
        self.domains += 1
        if page.error:
            self.errors[page.error.split(":")[0]] += 1
        if page.miss:
            self.misses[page.miss] += 1
        if not page.found:
            return
        self.found += 1
        self.by_crawl[page.crawl] += 1
        self.redirected += bool(page.redirected_to)
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
        if self.by_crawl:
            lines += ["Found in crawl:"] + [f"  {c}: {n:,}" for c, n in sorted(self.by_crawl.items(), reverse=True)]
        if self.redirected:
            lines += [f"Found after following a redirect: {self.redirected:,}"]
        if self.misses:
            lines += ["Why the rest were not found:"] + [f"  {k}: {pct(n, self.domains)}"
                                                        for k, n in self.misses.most_common()]
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
ALTER TABLE kb.homepage ADD COLUMN IF NOT EXISTS miss text;
ALTER TABLE kb.homepage ADD COLUMN IF NOT EXISTS redirected_to text;
"""


def save(conn, page: Homepage) -> None:
    conn.execute(
        """INSERT INTO kb.homepage (domain, found, crawl, url, fetched_at, title, description, text, emails,
                                    addresses, error, collected_at, miss, redirected_to)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (domain) DO UPDATE SET found = EXCLUDED.found, crawl = EXCLUDED.crawl, url = EXCLUDED.url,
               fetched_at = EXCLUDED.fetched_at, title = EXCLUDED.title, description = EXCLUDED.description,
               text = EXCLUDED.text, emails = EXCLUDED.emails, addresses = EXCLUDED.addresses,
               error = EXCLUDED.error, collected_at = EXCLUDED.collected_at, miss = EXCLUDED.miss,
               redirected_to = EXCLUDED.redirected_to""",
        (page.domain, page.found, page.crawl, page.url or None, page.fetched_at or None, page.title or None,
         page.description or None, (page.text or None) and page.text.replace("\x00", ""),
         json.dumps(page.emails), json.dumps(page.addresses), page.error or None, datetime.now(UTC),
         page.miss or None, page.redirected_to or None),
    )


async def collect(domains: list[str], crawls: list[str] | None, on_page: Callable[[Homepage], None],
                  data_dir: Path, concurrency: int = 4, client: httpx.AsyncClient | None = None,
                  user_agent: str = "heimdallr-kb", on_crawl: Callable[[str], None] | None = None,
                  crawl_count: int = 1) -> list[str]:
    """Read every domain's homepage, `concurrency` at a time, handing each result to `on_page`.
    Each domain is looked up in the given crawls (or the newest `crawl_count`), newest first."""
    own = client is None
    client = client or httpx.AsyncClient(timeout=httpx.Timeout(60, connect=20), headers={"User-Agent": user_agent},
                                         follow_redirects=True)
    try:
        crawls = crawls or await latest_crawls(client, crawl_count)
        readers = []
        for crawl in crawls:
            if on_crawl:
                on_crawl(crawl)
            readers.append(IndexReader(client, crawl, await cluster_index(client, crawl, data_dir)))
        queue: asyncio.Queue[str] = asyncio.Queue()
        for d in sorted(domains, key=surt_key):  # index order: neighbours share index blocks
            queue.put_nowait(d)

        async def worker() -> None:
            while not queue.empty():
                on_page(await read_homepage(client, readers, queue.get_nowait()))

        await asyncio.gather(*(worker() for _ in range(concurrency)))
        return crawls
    finally:
        if own:
            await client.aclose()
