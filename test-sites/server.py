"""Local test websites, virtual-hosted by the Host header.

Each directory under sites/ is one website (acme-security.test, globex.test, ...). The crawler
reaches them through a test DNS resolver that maps *.test to 127.0.0.1, so no /etc/hosts edits
are needed. A few routes are special so the safety rules can be tested:

  globex.test/go-internal   302 -> http://169.254.169.254/latest/meta-data/  (cloud metadata)
  globex.test/go-loopback   302 -> http://127.0.0.1:22/                      (loopback port)
  flaky.test/robots.txt     503                                               (robots unavailable)
  acme-old.test/            302 -> http://acme-security.test:PORT/           (a company's old domain)
  loader.test/              a page with no text, like a loader or challenge page

Any other Host (e.g. plain http://127.0.0.1:8765/) gets the acme-security.test site, for manual demos.

Run by hand:  python test-sites/server.py --port 8765
"""

from __future__ import annotations

import argparse
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SITES = Path(__file__).parent / "sites"
REDIRECTS = {
    ("globex.test", "/go-internal"): "http://169.254.169.254/latest/meta-data/",
    ("globex.test", "/go-loopback"): "http://127.0.0.1:22/",
    ("acme-old.test", "/"): "http://acme-security.test:{port}/",
}
DEFAULT_SITE = "acme-security.test"
STATUS = {("flaky.test", "/robots.txt"): 503}


class Handler(BaseHTTPRequestHandler):
    server_version = "TestSites/1.0"
    requests_seen: list[tuple[str, str]] = []

    def log_message(self, *args) -> None:  # keep test output quiet
        pass

    def do_GET(self) -> None:  # noqa: N802
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        path = self.path.split("?")[0]
        Handler.requests_seen.append((host, path))
        port = self.server.server_address[1]
        if (host, path) in REDIRECTS:
            self.send_response(302)
            self.send_header("Location", REDIRECTS[(host, path)].format(port=port))
            self.end_headers()
            return
        if (host, path) in STATUS:
            self.send_error(STATUS[(host, path)])
            return
        if not (SITES / host).is_dir():
            host = DEFAULT_SITE  # plain http://127.0.0.1:PORT/ serves the main demo site
        root = (SITES / host).resolve()
        target = (root / path.lstrip("/")).resolve()
        if target.is_dir():
            target = target / "index.html"
        if not root.is_dir() or not target.is_relative_to(root) or not target.is_file():
            self.send_error(404)
            return
        body = target.read_bytes().replace(b"{port}", str(port).encode())
        ctype = mimetypes.guess_type(target.name)[0] or "text/html"
        if ctype.startswith("text/") or ctype.endswith("xml"):
            ctype += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start(port: int = 0) -> tuple[ThreadingHTTPServer, int]:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    print(f"Test sites on http://{args.host}:{args.port} (send Host: acme-security.test etc.)", flush=True)
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
