"""SSRF protection: decide where the crawler may connect, and make sure it connects only there.

URL strings are never trusted. A destination is allowed only after its host has been resolved
here and every resolved address is public. The HTTP client then connects to that exact,
already-validated IP (the "pinned" address) while keeping the original host name for the Host
header, SNI and certificate checks, so a DNS answer that changes between check and connect
(DNS rebinding) cannot redirect the request. Redirects are followed by the fetcher one hop at a
time, and each hop goes through the same check.
"""

from __future__ import annotations

import ipaddress
import socket
import ssl
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpcore
import httpx

from app.config import get_settings

# Cloud metadata endpoints are covered by link-local / unique-local ranges, listed for clarity.
METADATA_ADDRESSES = {
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("169.254.170.2"),
    ipaddress.ip_address("fd00:ec2::254"),
    ipaddress.ip_address("100.100.100.200"),  # Alibaba Cloud metadata (inside CGNAT range)
}
_EXTRA_BLOCKED = [
    ipaddress.ip_network("100.64.0.0/10"),  # carrier-grade NAT, not "private" in Python < 3.13
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("198.18.0.0/15"),  # benchmarking
    ipaddress.ip_network("64:ff9b:1::/48"),  # local-use NAT64
]


class BlockedDestination(Exception):
    """The URL or the address it resolves to is not allowed."""


@dataclass(frozen=True)
class Destination:
    scheme: str
    host: str
    port: int
    addresses: tuple[str, ...]  # validated IPs, in resolver order


def _embedded_v4(ip: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    if ip.ipv4_mapped:
        return ip.ipv4_mapped
    if ip.sixtofour:
        return ip.sixtofour
    if ip.teredo:
        return ip.teredo[1]
    if ip in ipaddress.ip_network("64:ff9b::/96"):  # NAT64 well-known prefix
        return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return None


def ip_is_public(ip_text: str) -> bool:
    ip = ipaddress.ip_address(ip_text.split("%")[0])
    if isinstance(ip, ipaddress.IPv6Address):
        inner = _embedded_v4(ip)
        if inner is not None and not ip_is_public(str(inner)):
            return False
    if ip in METADATA_ADDRESSES:
        return False
    if any(ip in net for net in _EXTRA_BLOCKED):
        return False
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or (isinstance(ip, ipaddress.IPv6Address) and ip.is_site_local)
    ) and ip.is_global


def _private_exception(host: str, port: int, allow: Iterable[str]) -> bool:
    return f"{host}:{port}" in set(allow)


def parse_target(url: str) -> tuple[str, str, int]:
    """Return (scheme, host, port) or raise BlockedDestination for anything unusual."""
    if len(url) > 2048:
        raise BlockedDestination("URL is too long")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise BlockedDestination(f"unparseable URL: {exc}") from None
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise BlockedDestination(f"scheme {scheme!r} is not allowed")
    if parts.username or parts.password:
        raise BlockedDestination("URLs with credentials are not allowed")
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise BlockedDestination("URL has no host")
    try:
        host = host.encode("idna").decode("ascii") if not host.isascii() else host
    except UnicodeError:
        raise BlockedDestination("invalid international domain name") from None
    return scheme, host, port or (443 if scheme == "https" else 80)


def resolve(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise BlockedDestination(f"DNS lookup failed for {host}: {exc.strerror}") from None
    seen: list[str] = []
    for info in infos:
        addr = str(info[4][0])
        if addr not in seen:
            seen.append(addr)
    return seen


def _legacy_ipv4(host: str) -> ipaddress.IPv4Address | None:
    """Shorthand IPv4 forms such as 0x7f.1 or 2130706433, which resolvers accept as addresses."""
    if not all(c in "0123456789abcdefx." for c in host) or not any(c.isdigit() for c in host):
        return None
    try:
        return ipaddress.IPv4Address(socket.inet_aton(host))
    except OSError:
        return None


def check_url(url: str, *, resolver=resolve, allow_private: Iterable[str] | None = None) -> Destination:
    """Validate a URL and its DNS answers. Every resolved address must be public."""
    settings = get_settings()
    allow = settings.allow_private_targets if allow_private is None else list(allow_private)
    scheme, host, port = parse_target(url)
    exception = _private_exception(host, port, allow)
    if port not in settings.allowed_ports and not exception:
        raise BlockedDestination(f"port {port} is not allowed")
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
        addresses = [str(literal)]
    except ValueError:
        literal = _legacy_ipv4(host)
    if literal is not None:
        addresses = [str(literal)]
    else:
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".home.arpa")):
            if not exception:
                raise BlockedDestination(f"host {host} is internal") from None
        addresses = resolver(host, port)
    if not addresses:
        raise BlockedDestination(f"no addresses for {host}")
    if not exception:
        bad = [a for a in addresses if not ip_is_public(a)]
        if bad:
            raise BlockedDestination(f"{host} resolves to a non-public address ({bad[0]})")
    return Destination(scheme, host, port, tuple(addresses))


# --- the pinned connection -------------------------------------------------------------------


class _PinnedBackend(httpcore.AsyncNetworkBackend):
    """Connects only to addresses that check_url approved, re-resolving at connect time."""

    def __init__(self, resolver=resolve) -> None:
        self._inner = httpcore.AnyIOBackend()
        self._resolver = resolver

    async def connect_tcp(self, host: str, port: int, timeout: float | None = None,
                          local_address: str | None = None,
                          socket_options: Iterable[Any] | None = None) -> httpcore.AsyncNetworkStream:
        scheme = "https" if port == 443 else "http"
        dest = check_url(f"{scheme}://{_bracket(host)}:{port}/", resolver=self._resolver)
        last_exc: Exception | None = None
        for address in dest.addresses:  # every address was validated; try them in order
            try:
                return await self._inner.connect_tcp(address, port, timeout=timeout,
                                                     local_address=local_address,
                                                     socket_options=socket_options)
            except (httpcore.ConnectError, httpcore.ConnectTimeout, OSError) as exc:
                last_exc = exc
        raise httpcore.ConnectError(str(last_exc) if last_exc else "connection failed")

    async def connect_unix_socket(self, *args, **kwargs):  # pragma: no cover
        raise BlockedDestination("unix sockets are not allowed")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


def _bracket(host: str) -> str:
    return f"[{host}]" if ":" in host and not host.startswith("[") else host


class PinnedTransport(httpx.AsyncHTTPTransport):
    """httpx transport whose sockets go only to validated public addresses."""

    def __init__(self, resolver=resolve, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        ssl_context = ssl.create_default_context()
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=ssl_context,
            max_connections=kwargs.get("limits", httpx.Limits()).max_connections,
            network_backend=_PinnedBackend(resolver),
            http1=True,
            http2=False,
        )


def make_client(resolver=resolve, proxy: str | None = None) -> httpx.AsyncClient:
    settings = get_settings()
    timeout = httpx.Timeout(settings.read_timeout, connect=settings.connect_timeout)
    # Ask for the English page: many sites otherwise pick a language and local office from the visitor's
    # location (a run from India got +91 numbers). This is a normal browser preference, not disguise.
    headers = {"User-Agent": settings.user_agent, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
               "Accept-Language": "en-US,en;q=0.8"}
    proxy = proxy if proxy is not None else settings.crawl_proxy
    if proxy:
        # Egress proxy mode (sandboxes): destinations are still checked by the fetcher before
        # each hop, but the proxy performs the final DNS lookup. Not for production use.
        transport: httpx.AsyncBaseTransport = httpx.AsyncHTTPTransport(proxy=proxy)
    else:
        transport = PinnedTransport(resolver=resolver)
    return httpx.AsyncClient(transport=transport, timeout=timeout, headers=headers,
                             follow_redirects=False, trust_env=False)
