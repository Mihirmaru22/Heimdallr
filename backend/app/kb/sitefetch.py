"""For homepages Common Crawl does not have: is the domain alive, and if so, one polite fetch.

1. DNS: a domain with no address (expired, never set up) is dead; nothing is sent to anyone.
2. robots.txt is read and obeyed (the app's RobotsCache: unreachable robots.txt = disallowed).
3. One GET of the homepage (https, then www., then http), through the app's SSRF-checked Fetcher.
   A 403, 429 or other refusal is recorded and left alone: blocks are never bypassed.

One try per request, no retries: this reads millions of small sites once each, and a site that
does not answer in time is recorded as such. Retries with backoff (the research crawler's
setting) made a dead site cost about two minutes and held the whole run to 0.2 sites a second.

Each step's outcome is kept as the miss reason, so the report shows where the rest of the
"no capture" sites went: dns_dead, robots_disallowed, site_http_403, site_timeout...
"""

from __future__ import annotations

import asyncio
import socket
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import httpx

from app.crawl.fetcher import Fetcher, FetchError
from app.crawl.robots import RobotsCache
from app.kb.homepages import Homepage, extract

OWN = "own"
OWN_CONCURRENCY = 64  # different sites at a time; each site still gets one request at a time


async def dns_alive(domain: str, timeout: float = 5.0) -> bool:
    loop = asyncio.get_running_loop()
    for host in (domain, f"www.{domain}"):
        try:
            if await asyncio.wait_for(loop.getaddrinfo(host, 443, type=socket.SOCK_STREAM), timeout):
                return True
        except (OSError, TimeoutError, UnicodeError):
            continue
    return False


def own_fetcher(client: httpx.AsyncClient, user_agent: str, concurrency: int = OWN_CONCURRENCY,
                alive: Callable[[str], Awaitable[bool]] = dns_alive,
                resolver=None) -> Callable[[str], Awaitable[Homepage]]:
    fetcher = Fetcher(client, resolver=resolver)
    robots = RobotsCache(fetcher, user_agent, attempts=1)
    slots = asyncio.Semaphore(concurrency)

    async def fetch(domain: str) -> Homepage:
        async with slots:
            if not await alive(domain):
                return Homepage(domain, found=False, crawl=OWN, miss="dns_dead")
            last = "site_unreachable"
            for url in (f"https://{domain}/", f"https://www.{domain}/", f"http://{domain}/"):
                try:
                    decision = await robots.check(url)
                    if not decision.allowed:
                        last = "robots_disallowed" if "disallowed by" in decision.reason else "robots_unreachable"
                        continue
                    result = await fetcher.fetch(url, attempts=1)
                except FetchError as exc:
                    last = f"site_{exc.kind}"
                    if exc.kind.startswith("http_4") or exc.kind == "blocked":
                        break  # the site answered "no": do not try other doors
                    continue
                if not result.is_html:
                    last = "site_not_html"
                    continue
                page = extract(domain, OWN, result.final_url, datetime.now(UTC).isoformat(timespec="seconds"),
                               result.text)
                if result.final_url.rstrip("/") != url.rstrip("/"):
                    page.redirected_to = result.final_url
                return page
            return Homepage(domain, found=False, crawl=OWN, miss=last)

    return fetch
