import ipaddress
import socket
from typing import Any
from urllib.parse import parse_qs, parse_qsl, unquote, urlencode, urlparse, urlunparse

import httpcore
import httpx

from argus.search.base import BaseDiscovery
from argus.search.models import SearchQuery, SearchResponse, SearchResult
from argus.search.provider import SearchProvider

import re

DISALLOWED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "::1",
    "0.0.0.0",
    "::",
    "169.254.169.254",  # AWS/GCP cloud metadata endpoint
    "169.254.169.253",  # AWS DNS / NTP
    "169.254.170.2",    # AWS ECS metadata endpoint
    "168.63.129.16",    # Azure Wireserver / IMDS
    "100.100.100.200",  # Alibaba Cloud IMDS
    "metadata.google.internal",
    "instance-data",
    "metadata",
    "vault",
    "consul",
    "kubernetes",
    "kubernetes.default",
    "kubernetes.default.svc",
    "kubernetes.default.svc.cluster.local",
}

DISALLOWED_TLDS = (
    ".local",
    ".internal",
    ".localhost",
    ".lan",
    ".home",
    ".corp",
    ".arpa",
    ".invalid",
    ".test",
    ".example",
    ".onion",
    ".i2p",
    ".intranet",
    ".private",
)


def _is_safe_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Validate that an IP is globally routable and not in private, loopback, link-local, or cloud metadata ranges."""
    # Handle IPv4-mapped IPv6 address (e.g. ::ffff:127.0.0.1)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped

    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_unspecified
        or ip.is_multicast
        or not ip.is_global
    ):
        return False

    ip_str = str(ip)
    # Explicit cloud metadata IPs
    if ip_str in ("168.63.129.16", "100.100.100.200", "fd00:ec2::254"):
        return False

    # Check Carrier-Grade NAT 100.64.0.0/10 (RFC 6598)
    if isinstance(ip, ipaddress.IPv4Address) and ip in ipaddress.IPv4Network("100.64.0.0/10"):
        return False

    # Check documentation and benchmarking subnets (RFC 5737, RFC 2544)
    if isinstance(ip, ipaddress.IPv4Address):
        if (
            ip in ipaddress.IPv4Network("192.0.2.0/24")
            or ip in ipaddress.IPv4Network("198.51.100.0/24")
            or ip in ipaddress.IPv4Network("203.0.113.0/24")
            or ip in ipaddress.IPv4Network("198.18.0.0/15")
        ):
            return False

    return True

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "ref",
    "source",
}


class SearchPipeline(BaseDiscovery):
    """Normalizes, deduplicates, and validates search results for safety."""

    def __init__(self, provider: SearchProvider | None = None) -> None:
        self.provider = provider

    async def search(self, query: SearchQuery) -> SearchResponse:
        """Execute a search query via provider and sanitize/deduplicate results."""
        if self.provider is None:
            raise ValueError("No SearchProvider configured for SearchPipeline")

        raw_response = await self.provider.search(query)
        clean_results = self.process_results(
            raw_response.results, max_results=query.num_results
        )
        return SearchResponse(
            query=query.query,
            results=clean_results,
            total_results=len(clean_results),
            execution_time_ms=raw_response.execution_time_ms,
        )

    @staticmethod
    def normalize_url(raw_url: str) -> str:
        """Strip tracking parameters, fragments, unwrap search engine redirects, and normalize domain casing."""
        url_str = raw_url.strip()
        # Unwrap search engine redirects before normalization
        if "uddg=" in url_str:
            p_wrap = urlparse(url_str)
            qs = parse_qs(p_wrap.query)
            if "uddg" in qs and qs["uddg"]:
                url_str = unquote(qs["uddg"][0])
        elif "google.com/url" in url_str and ("q=" in url_str or "url=" in url_str):
            p_wrap = urlparse(url_str)
            qs = parse_qs(p_wrap.query)
            dest = qs.get("q") or qs.get("url")
            if dest and dest[0]:
                url_str = unquote(dest[0])

        parsed = urlparse(url_str)
        if not parsed.scheme or not parsed.netloc:
            return url_str

        # Filter out tracking query parameters
        query_pairs = [
            (k, v)
            for k, v in parse_qsl(parsed.query)
            if k.lower() not in TRACKING_PARAMS
        ]
        clean_query = urlencode(query_pairs)

        # Normalize path: strip trailing slash unless path is strictly "/"
        clean_path = parsed.path.rstrip("/") if parsed.path != "/" else "/"

        clean_parts = (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            clean_path,
            parsed.params,
            clean_query,
            "",  # Strip URL fragment (#section)
        )
        return urlunparse(clean_parts)

    @staticmethod
    def is_safe_url(url: str) -> bool:
        """Check for SSRF, private/loopback network access, DNS rebinding, and disallowed protocols."""
        try:
            parsed = urlparse(url)
        except ValueError:
            return False

        if parsed.scheme not in ("http", "https"):
            return False

        hostname = parsed.hostname
        if not hostname:
            return False

        # Strip whitespace and trailing dots (prevent FQDN dot bypass e.g. metadata.google.internal.)
        hostname_clean = hostname.lower().strip().rstrip(".")
        if not hostname_clean:
            return False

        if hostname_clean in DISALLOWED_HOSTS:
            return False

        if hostname_clean.endswith(DISALLOWED_TLDS):
            return False

        # Check direct IP addresses (supports dotted decimal, int, hex, etc.)
        try:
            ip = ipaddress.ip_address(hostname_clean)
            return _is_safe_ip(ip)
        except ValueError:
            pass

        # Disallow single-label hostnames without any dot (e.g. "instance-data", "metadata", "vault", "intranet")
        if "." not in hostname_clean:
            return False

        # DNS resolution to block DNS rebinding and hostnames resolving to private/internal IPs
        try:
            addr_info = socket.getaddrinfo(hostname_clean, None)
            if not addr_info:
                return False
            for res in addr_info:
                sockaddr = res[4]
                ip_str = sockaddr[0]
                resolved_ip = ipaddress.ip_address(ip_str)
                if not _is_safe_ip(resolved_ip):
                    return False
        except (socket.gaierror, socket.herror):
            # If domain cannot be resolved (e.g. offline testing), allow ONLY if valid public domain structure
            parts = hostname_clean.split(".")
            if len(parts) < 2 or not all(p and re.match(r"^[a-z0-9]([a-z0-9\-]*[a-z0-9])?$", p) for p in parts):
                return False
            tld = parts[-1]
            if len(tld) < 2 or not tld.isalpha():
                return False
        except (OSError, ValueError):
            return False

        return True

    @classmethod
    def process_results(
        cls,
        results: list[SearchResult],
        max_results: int = 20,
    ) -> list[SearchResult]:
        """Normalize URLs, filter out unsafe/SSRF targets, and deduplicate."""
        seen_urls: set[str] = set()
        clean_results: list[SearchResult] = []

        for item in results:
            clean_url = cls.normalize_url(item.url)

            # Security check
            if not cls.is_safe_url(clean_url):
                continue

            # Deduplication
            if clean_url in seen_urls:
                continue

            seen_urls.add(clean_url)
            clean_results.append(
                SearchResult(
                    url=clean_url,
                    title=item.title.strip(),
                    snippet=item.snippet.strip(),
                    engine=item.engine,
                    score=item.score,
                )
            )

            if len(clean_results) >= max_results:
                break

        return clean_results


# Explicit architecture contract alias
ArgusDiscovery = SearchPipeline


class SSRFSafeNetworkBackend(httpcore.AnyIOBackend):
    """Network backend enforcing strict SSRF and DNS-rebinding countermeasures on socket connections.

    Compatibility Notice:
    Requires HTTPcore >= 1.0.0 (pinned to 1.0.9). Intercepts socket connection creation and
    verifies the actual connected socket peer IP before any HTTP payloads are transmitted.
    """

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        clean_host = host.lower().strip().rstrip(".")
        if not SearchPipeline.is_safe_url(f"http://{clean_host}:{port}"):
            raise httpcore.ConnectError(f"SSRF blocked: Destination host '{host}' is disallowed")

        # Pre-connection DNS inspection
        try:
            addr_info = socket.getaddrinfo(clean_host, port)
            for res in addr_info:
                ip = ipaddress.ip_address(res[4][0])
                if not _is_safe_ip(ip):
                    raise httpcore.ConnectError(f"SSRF blocked: Host '{host}' resolves to restricted IP {ip}")
        except socket.gaierror:
            # If domain fails local resolution (e.g. offline unit test), proceed to socket connection
            # where the actual transport resolver or post-connect peer IP check enforces safety
            pass

        # Connect socket
        stream = await super().connect_tcp(
            host=host,
            port=port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

        # Post-connection socket peer IP verification (anti-DNS-rebinding protection at socket boundary)
        try:
            peer_ip_str: str | None = None
            raw_sock = getattr(stream, "_raw_socket", None)
            if raw_sock is None:
                inner = getattr(stream, "_stream", None)
                if inner is not None:
                    raw_sock = getattr(inner, "_raw_socket", None)

            if raw_sock is not None and hasattr(raw_sock, "getpeername"):
                res = raw_sock.getpeername()
                if isinstance(res, (tuple, list)) and len(res) > 0 and isinstance(res[0], str):
                    peer_ip_str = res[0]

            if not peer_ip_str and hasattr(stream, "get_extra_info"):
                server_addr = stream.get_extra_info("server_addr")
                if isinstance(server_addr, (tuple, list)) and len(server_addr) > 0 and isinstance(server_addr[0], str):
                    peer_ip_str = server_addr[0]
                else:
                    sock = stream.get_extra_info("socket")
                    if sock is not None and hasattr(sock, "getpeername"):
                        res = sock.getpeername()
                        if isinstance(res, (tuple, list)) and len(res) > 0 and isinstance(res[0], str):
                            peer_ip_str = res[0]

            if not peer_ip_str:
                await stream.aclose()
                raise httpcore.ConnectError(
                    "SSRF / DNS-Rebinding blocked: Unable to determine connected socket peer IP"
                )

            peer_ip = ipaddress.ip_address(peer_ip_str)
            if not _is_safe_ip(peer_ip):
                await stream.aclose()
                raise httpcore.ConnectError(
                    f"SSRF / DNS-Rebinding blocked: Connected socket peer IP {peer_ip} is restricted"
                )
        except Exception as e:
            if isinstance(e, httpcore.ConnectError):
                raise
            await stream.aclose()
            raise httpcore.ConnectError(f"Failed to verify socket peer IP: {e}")

        return stream


class SSRFSafeAsyncTransport(httpx.AsyncHTTPTransport):
    """HTTPX Transport backed by SSRFSafeNetworkBackend to neutralize SSRF and DNS rebinding.

    Compatibility Notice & Private API Dependencies:
    - Pinned dependencies: HTTPX 0.28.1 and HTTPcore 1.0.9.
    - Relies on httpx.AsyncHTTPTransport._pool (AsyncConnectionPool or AsyncHTTPProxy).
    - Relies on httpcore.AsyncConnectionPool._network_backend.
    Injects SSRFSafeNetworkBackend directly into the underlying HTTPcore connection pool,
    preserving all TLS certificate verification, hostname checking, proxy, and connection limit configurations.
    Fails closed with RuntimeError if runtime environment violates these expectations.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if not hasattr(self, "_pool"):
            raise RuntimeError(
                "Incompatible HTTPX version: '_pool' attribute missing on AsyncHTTPTransport. "
                "SSRFSafeAsyncTransport requires HTTPX with HTTPcore connection pooling (pinned httpx==0.28.1)."
            )
        if not hasattr(self._pool, "_network_backend"):
            raise RuntimeError(
                "Incompatible HTTPcore version: '_network_backend' attribute missing on connection pool. "
                "SSRFSafeAsyncTransport requires HTTPcore >= 1.0.0 (pinned httpcore==1.0.9)."
            )
        self._pool._network_backend = SSRFSafeNetworkBackend()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Enforce destination policy on every request dispatched through this transport.

        Guarantees that direct requests, requests routed through forward proxies,
        and redirected requests cannot reach prohibited or internal destinations.
        """
        url_str = str(request.url)
        if not SearchPipeline.is_safe_url(url_str):
            raise httpx.ConnectError(
                f"SSRF blocked: Target URL '{url_str}' violates destination security policy",
                request=request,
            )
        return await super().handle_async_request(request)


async def _validate_redirect_hook(response: httpx.Response) -> None:
    """Validate that every redirect hop destination satisfies SSRF safety policies."""
    if response.is_redirect:
        loc = response.headers.get("Location")
        if loc:
            from urllib.parse import urljoin
            target = urljoin(str(response.url), loc)
            if not SearchPipeline.is_safe_url(target):
                raise httpx.RequestError(
                    f"SSRF blocked: Redirect hop destination '{target}' is disallowed",
                    request=response.request,
                )


def create_safe_async_client(
    timeout: float | httpx.Timeout | None = 15.0,
    headers: dict[str, str] | None = None,
    follow_redirects: bool = False,
    verify: Any = True,
    limits: httpx.Limits | None = None,
    proxy: Any = None,
    trust_env: bool = True,
    http1: bool = True,
    http2: bool = False,
    transport: httpx.AsyncBaseTransport | None = None,
    mounts: dict[str, httpx.AsyncBaseTransport | None] | None = None,
    event_hooks: dict[str, list[Any]] | None = None,
    **kwargs: Any,
) -> httpx.AsyncClient:
    """Create an HTTPX AsyncClient with unified destination policy, DNS rebinding defense, and redirect validation.

    Preserves:
    - TLS certificate verification and HTTPS hostname verification
    - Connect, read, write, and pool timeouts
    - Connection limits (max_connections, max_keepalive_connections, keepalive_expiry)
    - Proxy configuration and environment-derived proxy settings (ALL_PROXY, HTTP_PROXY, HTTPS_PROXY)
    - Hop-by-hop redirect destination verification
    - DNS rebinding prevention via socket-layer verification
    """
    effective_limits = limits or httpx.Limits(max_connections=100, max_keepalive_connections=20)

    if transport is None:
        transport = SSRFSafeAsyncTransport(
            verify=verify,
            limits=effective_limits,
            proxy=proxy,
            trust_env=trust_env,
            http1=http1,
            http2=http2,
        )

    # Prepare mounts for environment-derived or custom proxies
    client_mounts: dict[str, httpx.AsyncBaseTransport | None] = {}
    if mounts is not None:
        client_mounts.update(mounts)

    # If trust_env is enabled and no explicit proxy was passed, preserve environment proxies safely
    if proxy is None and trust_env:
        try:
            from httpx._utils import get_environment_proxies
            env_proxies = get_environment_proxies()
            for pattern, env_proxy_url in env_proxies.items():
                if env_proxy_url and pattern not in client_mounts:
                    client_mounts[pattern] = SSRFSafeAsyncTransport(
                        verify=verify,
                        limits=effective_limits,
                        proxy=env_proxy_url,
                        trust_env=trust_env,
                        http1=http1,
                        http2=http2,
                    )
        except Exception:
            pass

    # Configure event hooks for hop-by-hop redirect verification
    merged_hooks: dict[str, list[Any]] = {"response": [_validate_redirect_hook]}
    if event_hooks:
        for k, hook_list in event_hooks.items():
            if k in merged_hooks:
                merged_hooks[k].extend(hook_list)
            else:
                merged_hooks[k] = list(hook_list)

    return httpx.AsyncClient(
        transport=transport,
        mounts=client_mounts or None,
        timeout=timeout,
        headers=headers,
        follow_redirects=follow_redirects,
        verify=verify,
        trust_env=trust_env,
        event_hooks=merged_hooks,
        **kwargs,
    )
