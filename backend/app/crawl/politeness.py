"""Per-host politeness shared by every worker: at most one request per host per delay window.

The gate is a Redis key per host set with NX and a TTL equal to the delay, so two workers
crawling the same site still space their requests. Without Redis (unit tests) an in-process
gate does the same for one process.
"""

from __future__ import annotations

import asyncio
import time
from urllib.parse import urlsplit


class LocalPoliteness:
    def __init__(self, delay: float) -> None:
        self.delay = delay
        self._next: dict[str, float] = {}
        self._lock = asyncio.Lock()
        self.host_delay: dict[str, float] = {}

    async def wait(self, url: str) -> None:
        host = urlsplit(url).hostname or ""
        delay = max(self.delay, self.host_delay.get(host, 0.0))
        async with self._lock:
            now = time.monotonic()
            slot = max(now, self._next.get(host, 0.0))
            self._next[host] = slot + delay
        if slot > now:
            await asyncio.sleep(slot - now)


class RedisPoliteness:
    def __init__(self, redis, delay: float) -> None:
        self.redis = redis
        self.delay = delay
        self.host_delay: dict[str, float] = {}

    async def wait(self, url: str) -> None:
        host = urlsplit(url).hostname or ""
        delay = max(self.delay, self.host_delay.get(host, 0.0))
        if delay <= 0:
            return
        key = f"polite:{host}"
        while not await self.redis.set(key, "1", nx=True, px=int(delay * 1000)):
            ttl = await self.redis.pttl(key)
            await asyncio.sleep(max(ttl, 50) / 1000)
