"""Browser SSRF and Network Boundary Protection Proxy.

Enforces network-level destination policies for headless Chromium sessions:
- Intercepts all browser HTTP and HTTPS (CONNECT) traffic at the socket boundary.
- Resolves DNS and validates all candidate IP addresses against private, loopback,
  link-local, cloud metadata, carrier-grade NAT, and documentation subnets.
- Enforces post-connection socket peer IP verification to neutralize DNS rebinding.
- Preserves end-to-end TLS certificate and hostname verification for HTTPS.
- Revalidates redirect hops and subsequent subresource requests.
- Fails closed if the security boundary cannot be reliably established.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from typing import Any
from urllib.parse import urljoin, urlparse

from argus.search.pipeline import SearchPipeline, _is_safe_ip

logger = logging.getLogger(__name__)


class BrowserSSRFProxy:
    """Local async proxy enforcing SSRF and DNS-rebinding countermeasures for browser traffic."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.host = host
        self.port = port
        self.server: asyncio.Server | None = None
        self.blocked_attempts: list[dict[str, Any]] = []
        self._is_running = False

    async def start(self) -> int:
        """Bind and start proxy server on local loopback interface.
        
        Returns:
            Bound ephemeral TCP port number.
        Raises:
            RuntimeError: If proxy fails to bind, enforcing fail-closed posture.
        """
        try:
            self.server = await asyncio.start_server(self.handle_client, self.host, self.port)
            self.port = self.server.sockets[0].getsockname()[1]
            self._is_running = True
            logger.info("BrowserSSRFProxy bound successfully on %s:%d", self.host, self.port)
            return self.port
        except Exception as e:
            self._is_running = False
            logger.error("Failed to bind BrowserSSRFProxy: %s", e)
            raise RuntimeError(f"Browser security boundary failure: unable to start safe proxy: {e}") from e

    async def stop(self) -> None:
        """Gracefully stop proxy server and close open sockets."""
        self._is_running = False
        if self.server:
            self.server.close()
            try:
                await self.server.wait_closed()
            except Exception:
                pass
            self.server = None

    async def __aenter__(self) -> BrowserSSRFProxy:
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.stop()

    def _block_connection(
        self,
        writer: asyncio.StreamWriter,
        target: str,
        reason: str,
        status_code: int = 403,
    ) -> None:
        """Record security violation and write HTTP rejection response."""
        self.blocked_attempts.append({
            "target": target,
            "reason": reason,
            "status_code": status_code,
        })
        logger.warning("BrowserSSRFProxy BLOCKED connection to %s: %s", target, reason)
        body = f"SSRF Blocked: {reason}\r\n"
        resp = (
            f"HTTP/1.1 {status_code} Forbidden\r\n"
            "Content-Type: text/plain\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n\r\n"
            f"{body}"
        )
        try:
            writer.write(resp.encode("utf-8"))
        except Exception:
            pass

    async def handle_client(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        """Handle individual HTTP / CONNECT proxy request from Chromium."""
        try:
            line = await client_reader.readline()
            if not line:
                client_writer.close()
                await client_writer.wait_closed()
                return

            req_line = line.decode("utf-8", errors="replace").strip()
            parts = req_line.split()
            if len(parts) < 2:
                client_writer.close()
                await client_writer.wait_closed()
                return

            method, target = parts[0], parts[1]

            # Read request headers
            headers: dict[str, str] = {}
            raw_headers: list[bytes] = []
            while True:
                h_line = await client_reader.readline()
                if not h_line or h_line in (b"\r\n", b"\n"):
                    break
                raw_headers.append(h_line)
                h_str = h_line.decode("utf-8", errors="replace").strip()
                if ":" in h_str:
                    k, v = h_str.split(":", 1)
                    headers[k.strip().lower()] = v.strip()

            if method.upper() == "CONNECT":
                await self._handle_connect(client_reader, client_writer, target)
            else:
                await self._handle_http(client_reader, client_writer, method, target, headers, raw_headers)
        except Exception as e:
            logger.debug("Proxy client handling error: %s", e)
        finally:
            try:
                client_writer.close()
                await client_writer.wait_closed()
            except Exception:
                pass

    async def _handle_connect(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        target: str,
    ) -> None:
        """Handle HTTPS CONNECT tunnel with anti-DNS-rebinding and socket peer verification."""
        host_port = target.split(":")
        host = host_port[0]
        try:
            port = int(host_port[1]) if len(host_port) > 1 else 443
        except ValueError:
            self._block_connection(client_writer, target, "Invalid port specification", 400)
            return

        # 1. URL / Host policy check
        if not SearchPipeline.is_safe_url(f"http://{host}:{port}"):
            self._block_connection(client_writer, target, "Disallowed target hostname or IP format")
            return

        # 2. DNS Resolution and IP validation
        loop = asyncio.get_event_loop()
        try:
            addr_info = await loop.getaddrinfo(host, port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
        except Exception as e:
            self._block_connection(client_writer, target, f"DNS resolution failed: {e}", 502)
            return

        if not addr_info:
            self._block_connection(client_writer, target, "No DNS records resolved", 502)
            return

        # Enforce that ALL resolved IPs are safe
        safe_candidates: list[tuple[str, int]] = []
        for res in addr_info:
            sockaddr = res[4]
            ip_str = sockaddr[0]
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                self._block_connection(client_writer, target, f"Invalid resolved IP: {ip_str}")
                return

            if not _is_safe_ip(ip):
                self._block_connection(client_writer, target, f"Resolved IP {ip} is restricted")
                return
            safe_candidates.append((ip_str, sockaddr[1]))

        if not safe_candidates:
            self._block_connection(client_writer, target, "No safe destination addresses found")
            return

        # 3. Connect TCP socket to remote destination
        remote_ip, remote_port = safe_candidates[0]
        try:
            remote_reader, remote_writer = await asyncio.open_connection(
                remote_ip,
                remote_port,
                server_hostname=None,  # Plain TCP tunnel; TLS is negotiated by Chromium
            )
        except Exception as e:
            self._block_connection(client_writer, target, f"Remote connection failed: {e}", 502)
            return

        # 4. Crucial: Post-connection socket peer IP verification (anti-DNS-rebinding)
        try:
            sock = remote_writer.get_extra_info("socket")
            if not sock:
                remote_writer.close()
                await remote_writer.wait_closed()
                self._block_connection(client_writer, target, "Socket handle unavailable for verification")
                return

            peer_tuple = sock.getpeername()
            peer_ip = ipaddress.ip_address(peer_tuple[0])
            if not _is_safe_ip(peer_ip):
                remote_writer.close()
                await remote_writer.wait_closed()
                self._block_connection(client_writer, target, f"Connected peer IP {peer_ip} violates policy")
                return
        except Exception as e:
            remote_writer.close()
            await remote_writer.wait_closed()
            self._block_connection(client_writer, target, f"Failed peer IP verification: {e}")
            return

        # 5. Established tunnel - notify Chromium
        client_writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await client_writer.drain()

        # 6. Bidirectional data piping
        async def pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
            try:
                while True:
                    buf = await src.read(65536)
                    if not buf:
                        break
                    dst.write(buf)
                    await dst.drain()
            except Exception:
                pass
            finally:
                try:
                    dst.close()
                except Exception:
                    pass

        try:
            await asyncio.gather(
                pipe(client_reader, remote_writer),
                pipe(remote_reader, client_writer),
            )
        finally:
            try:
                remote_writer.close()
                await remote_writer.wait_closed()
            except Exception:
                pass

    async def _handle_http(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        method: str,
        target: str,
        headers: dict[str, str],
        raw_headers: list[bytes],
    ) -> None:
        """Handle standard HTTP request with hop-by-hop SSRF validation and redirect revalidation."""
        if target.startswith("http://") or target.startswith("https://"):
            full_url = target
        else:
            host_hdr = headers.get("host")
            if not host_hdr:
                self._block_connection(client_writer, target, "Missing Host header", 400)
                return
            full_url = f"http://{host_hdr}{target}"

        # 1. URL policy check
        if not SearchPipeline.is_safe_url(full_url):
            self._block_connection(client_writer, full_url, "Disallowed destination URL")
            return

        parsed = urlparse(full_url)
        hostname = parsed.hostname
        if not hostname:
            self._block_connection(client_writer, full_url, "Missing hostname in URL", 400)
            return
        port = parsed.port or (443 if parsed.scheme == "https" else 80)

        # 2. DNS check
        loop = asyncio.get_event_loop()
        try:
            addr_info = await loop.getaddrinfo(hostname, port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
        except Exception as e:
            self._block_connection(client_writer, full_url, f"DNS error: {e}", 502)
            return

        for res in addr_info:
            ip_str = res[4][0]
            ip = ipaddress.ip_address(ip_str)
            if not _is_safe_ip(ip):
                self._block_connection(client_writer, full_url, f"Resolved IP {ip} is restricted")
                return

        remote_ip = addr_info[0][4][0]
        try:
            remote_reader, remote_writer = await asyncio.open_connection(remote_ip, port)
        except Exception as e:
            self._block_connection(client_writer, full_url, f"Connection failed: {e}", 502)
            return

        # 3. Post-connect socket peer verification
        try:
            sock = remote_writer.get_extra_info("socket")
            peer_ip = ipaddress.ip_address(sock.getpeername()[0])
            if not _is_safe_ip(peer_ip):
                remote_writer.close()
                await remote_writer.wait_closed()
                self._block_connection(client_writer, full_url, f"Connected peer IP {peer_ip} violates policy")
                return
        except Exception as e:
            remote_writer.close()
            await remote_writer.wait_closed()
            self._block_connection(client_writer, full_url, f"Peer verification error: {e}")
            return

        # 4. Forward HTTP request
        path = parsed.path or "/"
        if parsed.query:
            path += f"?{parsed.query}"

        fwd_req = f"{method} {path} HTTP/1.1\r\n"
        remote_writer.write(fwd_req.encode("utf-8"))
        for h in raw_headers:
            remote_writer.write(h)
        remote_writer.write(b"\r\n")
        await remote_writer.drain()

        # 5. Read response and inspect redirect Location header
        resp_status_line = await remote_reader.readline()
        if not resp_status_line:
            remote_writer.close()
            return

        client_writer.write(resp_status_line)
        status_parts = resp_status_line.decode("utf-8", errors="replace").split()
        status_code = int(status_parts[1]) if len(status_parts) > 1 and status_parts[1].isdigit() else 200

        is_redirect = status_code in (301, 302, 303, 307, 308)
        location_header: str | None = None

        while True:
            resp_h = await remote_reader.readline()
            if not resp_h or resp_h in (b"\r\n", b"\n"):
                break
            h_decoded = resp_h.decode("utf-8", errors="replace").strip()
            if ":" in h_decoded:
                k, v = h_decoded.split(":", 1)
                if k.strip().lower() == "location":
                    location_header = v.strip()
            client_writer.write(resp_h)

        # Revalidate redirect destination before streaming body
        if is_redirect and location_header:
            redirect_dest = urljoin(full_url, location_header)
            if not SearchPipeline.is_safe_url(redirect_dest):
                remote_writer.close()
                self._block_connection(client_writer, redirect_dest, "Redirect destination violates policy")
                return

        client_writer.write(b"\r\n")
        await client_writer.drain()

        # Stream body
        while True:
            chunk = await remote_reader.read(65536)
            if not chunk:
                break
            client_writer.write(chunk)
            await client_writer.drain()

        remote_writer.close()
        await remote_writer.wait_closed()
