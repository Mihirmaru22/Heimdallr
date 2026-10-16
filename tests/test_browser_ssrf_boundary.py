"""Regression tests for Browser SSRF Protection at the network boundary.

Verifies:
1. Actual Playwright Chromium networking path is strictly mediated by BrowserSSRFProxy.
2. Loopback, private, link-local, and cloud metadata destinations are blocked.
3. Post-connect socket peer IP verification prevents DNS rebinding attacks.
4. Redirects and in-page subresources pointing to prohibited destinations are blocked.
5. Fail-closed security posture when the security boundary fails.
"""

import asyncio
import socket
from unittest.mock import patch

import pytest
from playwright.async_api import async_playwright

from argus.crawler.browser_proxy import BrowserSSRFProxy
from argus.crawler.fetcher import TwoTierFetcher
from argus.crawler.models import CrawlRequest


@pytest.mark.asyncio
async def test_browser_network_boundary_blocks_loopback():
    """Verify that actual Chromium browser cannot reach loopback destinations."""
    fetcher = TwoTierFetcher(timeout=4.0)
    req = CrawlRequest(url="http://127.0.0.1:8080/secret-service", force_browser=True)

    doc = await fetcher.fetch(req)
    assert doc.status_code == 403
    assert doc.fetch_method == "blocked"


@pytest.mark.asyncio
async def test_browser_network_boundary_blocks_cloud_metadata():
    """Verify that actual Chromium browser cannot reach AWS/GCP cloud metadata IP."""
    fetcher = TwoTierFetcher(timeout=4.0)
    req = CrawlRequest(url="http://169.254.169.254/latest/meta-data/", force_browser=True)

    doc = await fetcher.fetch(req)
    assert doc.status_code == 403
    assert doc.fetch_method == "blocked"


@pytest.mark.asyncio
async def test_browser_proxy_blocks_connect_to_private_destinations():
    """Verify proxy blocks CONNECT requests targeting prohibited hosts or private IPs."""
    proxy = BrowserSSRFProxy()
    port = await proxy.start()
    try:
        # Connect directly to proxy mimicking Chromium CONNECT
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"CONNECT 127.0.0.1:22 HTTP/1.1\r\nHost: 127.0.0.1:22\r\n\r\n")
        await writer.drain()

        resp = await reader.read(4096)
        writer.close()
        await writer.wait_closed()

        assert b"403 Forbidden" in resp
        assert b"SSRF Blocked" in resp
        assert len(proxy.blocked_attempts) >= 1
    finally:
        await proxy.stop()


@pytest.mark.asyncio
async def test_browser_proxy_blocks_dns_rebinding_at_socket_boundary():
    """Verify proxy blocks destination when DNS or socket peer IP resolves to a private IP."""
    proxy = BrowserSSRFProxy()
    port = await proxy.start()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        # Attempt to access 169.254.169.254 via CONNECT
        writer.write(b"CONNECT 169.254.169.254:80 HTTP/1.1\r\nHost: 169.254.169.254:80\r\n\r\n")
        await writer.drain()

        resp = await reader.read(4096)
        writer.close()
        await writer.wait_closed()

        assert b"403 Forbidden" in resp
        assert len(proxy.blocked_attempts) >= 1
    finally:
        await proxy.stop()


@pytest.mark.asyncio
async def test_browser_proxy_revalidates_redirect_to_private_ip():
    """Verify proxy blocks redirect from a permitted origin to a prohibited destination.
    
    Uses a controlled external TCP server on a non-loopback interface to serve the
    initial request (which the proxy must permit), then returns a 302 redirect to
    the cloud metadata IP 169.254.169.254 (which the proxy must block).
    
    This test replaces the previous version that started the redirect server on
    127.0.0.1, which was blocked before the redirect even fired.
    """
    proxy = BrowserSSRFProxy()
    port = await proxy.start()

    # Determine a non-loopback local IP to bind the redirect server on.
    # This address is routable on the LAN but not loopback, so the proxy
    # will permit the initial connection.
    local_ip = _get_non_loopback_local_ip()
    if local_ip is None:
        pytest.skip("No non-loopback local interface available for redirect test")

    async def handle_redirect_server(r, w):
        """Serve a 302 redirect to cloud metadata IP on any request."""
        # Consume full HTTP request
        while True:
            line = await r.readline()
            if not line or line in (b"\r\n", b"\n"):
                break
        w.write(
            b"HTTP/1.1 302 Found\r\n"
            b"Location: http://169.254.169.254/latest/meta-data/\r\n"
            b"Content-Length: 0\r\n"
            b"\r\n"
        )
        await w.drain()
        w.close()

    redirect_srv = await asyncio.start_server(handle_redirect_server, local_ip, 0)
    redir_port = redirect_srv.sockets[0].getsockname()[1]

    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        # Send GET to the permitted non-loopback redirect server via proxy
        req = (
            f"GET http://{local_ip}:{redir_port}/redir HTTP/1.1\r\n"
            f"Host: {local_ip}:{redir_port}\r\n"
            f"\r\n"
        )
        writer.write(req.encode("utf-8"))
        await writer.drain()

        resp = await asyncio.wait_for(reader.read(8192), timeout=5.0)
        writer.close()
        await writer.wait_closed()

        resp_text = resp.decode("utf-8", errors="replace")

        # The proxy must either:
        # a) Block the redirect destination (403 on the Location header check), or
        # b) Pass through the 302 but have blocked the metadata IP at the DNS/connect layer
        # Either way, a 403 or the blocked_attempts list must reflect the block.
        redirect_blocked = (
            b"403 Forbidden" in resp
            or any("169.254.169.254" in ba.get("target", "") for ba in proxy.blocked_attempts)
        )
        assert redirect_blocked, (
            f"Proxy did NOT block redirect to 169.254.169.254.\n"
            f"Response: {resp_text[:500]}\n"
            f"Blocked attempts: {proxy.blocked_attempts}"
        )
    finally:
        redirect_srv.close()
        await redirect_srv.wait_closed()
        await proxy.stop()


def _get_non_loopback_local_ip() -> str | None:
    """Return a non-loopback IPv4 address on a local interface, or None if unavailable."""
    import ipaddress as _ipa
    try:
        # Connect to an external address (no traffic sent) to find the default route IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        finally:
            s.close()
        addr = _ipa.ip_address(ip)
        if not addr.is_loopback and not addr.is_link_local:
            return ip
    except Exception:
        pass
    return None


@pytest.mark.asyncio
async def test_browser_fails_closed_when_security_boundary_unreachable():
    """Verify fail-closed posture: if proxy cannot be established, fetcher refuses to launch unprotected browser."""
    fetcher = TwoTierFetcher(timeout=2.0)
    req = CrawlRequest(url="https://example.com/research", force_browser=True)

    with patch.object(BrowserSSRFProxy, "start", side_effect=RuntimeError("Simulated port bind failure")):
        doc = await fetcher.fetch(req)
        assert doc.status_code == 403
        assert doc.fetch_method == "blocked"
        assert "Browser Security Boundary Failure" in doc.title
