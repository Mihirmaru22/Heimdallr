"""robots.txt handling (RFC 9309), cached per host for the life of a job.

- 2xx: parse and obey, including Crawl-delay.
- 4xx: no restrictions (the site has no robots.txt).
- 5xx, timeouts, network errors: treat the whole site as disallowed, as RFC 9309 requires.
Passing robots.txt is not a statement that crawling is legally permitted.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from protego import Protego

from app.crawl.fetcher import Fetcher, FetchError

TEXT_PLAIN = ("text/plain", "text/html", "application/octet-stream", "")


@dataclass
class RobotsDecision:
    allowed: bool
    reason: str


class RobotsCache:
    def __init__(self, fetcher: Fetcher, user_agent: str, enabled: bool = True) -> None:
        self.fetcher = fetcher
        self.user_agent = user_agent
        self.enabled = enabled
        self._rules: dict[str, Protego | str] = {}

    def _token(self) -> str:
        return self.user_agent.split("/")[0]

    async def _load(self, origin: str) -> Protego | str:
        robots_fetcher = Fetcher(self.fetcher.client, self.fetcher.politeness, self.fetcher.resolver,
                                 allowed_types=TEXT_PLAIN)
        try:
            result = await robots_fetcher.fetch(origin + "/robots.txt", attempts=2)
        except FetchError as exc:
            if exc.kind.startswith("http_4") and exc.kind != "http_429":
                return "allow_all"
            if exc.kind == "content_type":
                return "allow_all"
            return "disallow_all"
        return Protego.parse(result.body[:500_000].decode("utf-8", errors="replace"))

    async def check(self, url: str) -> RobotsDecision:
        if not self.enabled:
            return RobotsDecision(True, "robots checks disabled by administrator")
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._rules:
            self._rules[origin] = await self._load(origin)
        rules = self._rules[origin]
        if rules == "allow_all":
            return RobotsDecision(True, "no robots.txt")
        if rules == "disallow_all":
            return RobotsDecision(False, "robots.txt unreachable; treated as disallow")
        assert isinstance(rules, Protego)
        ok = rules.can_fetch(url, self._token())
        return RobotsDecision(ok, "allowed by robots.txt" if ok else "disallowed by robots.txt")

    def crawl_delay(self, url: str) -> float | None:
        parts = urlsplit(url)
        rules = self._rules.get(f"{parts.scheme}://{parts.netloc}")
        if isinstance(rules, Protego):
            delay = rules.crawl_delay(self._token())
            return float(delay) if delay else None
        return None

    def sitemaps(self, url: str) -> list[str]:
        parts = urlsplit(url)
        rules = self._rules.get(f"{parts.scheme}://{parts.netloc}")
        return list(rules.sitemaps) if isinstance(rules, Protego) else []
