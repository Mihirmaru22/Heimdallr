"""Reading company homepages from Common Crawl, with Common Crawl replaced by a fake transport."""

from __future__ import annotations

import asyncio
import gzip
import json

import httpx

from app.kb import homepages

HTML = """<html><head><title>Acme Pay | Payments for small shops</title>
<meta name="description" content="Acme Pay builds card terminals and payment software for small shops.">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Organization","name":"Acme Pay",
"address":{"@type":"PostalAddress","streetAddress":"12 MG Road","addressLocality":"Mumbai",
"postalCode":"400001","addressCountry":"IN"}}</script></head>
<body><p>Card terminals and payment software for small shops across India.</p>
<a href="mailto:sales@acmepay.com">Sales</a> <a href="mailto:rahul.sharma@acmepay.com">Rahul</a>
<a href="mailto:hello@otheragency.com">Agency</a></body></html>"""


def _warc(html: str, url: str = "https://acmepay.com/") -> bytes:
    body = html.encode()
    http = b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n\r\n" + body
    warc = (f"WARC/1.0\r\nWARC-Type: response\r\nWARC-Target-URI: {url}\r\n"
            f"WARC-Date: 2026-10-05T10:00:00Z\r\nContent-Length: {len(http)}\r\n\r\n").encode() + http + b"\r\n\r\n"
    return gzip.compress(warc)


def _transport(records: dict[str, bytes], seen: list[httpx.Request]):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/collinfo.json":
            return httpx.Response(200, json=[{"id": "CC-MAIN-2026-44"}, {"id": "CC-MAIN-2026-40"}])
        if request.url.path.endswith("-index"):
            domain = request.url.params["url"].rstrip("/")
            if domain not in records:
                return httpx.Response(404, text="No Captures found")
            data = records[domain]
            rows = [
                {"url": f"https://{domain}/about-us", "filename": "x/other.warc.gz", "offset": "0", "length": "10"},
                {"url": f"https://{domain}/", "filename": "x/home.warc.gz", "offset": "100",
                 "length": str(len(data)), "timestamp": "20261005100000"},
            ]
            return httpx.Response(200, text="\n".join(json.dumps(r) for r in rows))
        if request.url.path == "/x/home.warc.gz":
            assert request.headers["Range"].startswith("bytes=100-")
            return httpx.Response(206, content=records["acmepay.com"])
        return httpx.Response(500)

    return httpx.MockTransport(handler)


def test_reads_the_homepage_record_and_keeps_company_fields():
    seen: list[httpx.Request] = []
    pages: list[homepages.Homepage] = []
    client = httpx.AsyncClient(transport=_transport({"acmepay.com": _warc(HTML)}, seen))
    crawl = asyncio.run(homepages.collect(["acmepay.com", "missing.com"], None, pages.append, 2, client=client))
    assert crawl == "CC-MAIN-2026-44"  # the newest crawl
    by = {p.domain: p for p in pages}
    acme = by["acmepay.com"]
    assert acme.found and acme.url == "https://acmepay.com/"  # the homepage, not /about-us
    assert acme.fetched_at == "2026-10-05T10:00:00Z"
    assert acme.title.startswith("Acme Pay")
    assert "card terminals" in acme.description
    assert "small shops across India" in acme.text
    # Company mailboxes only: no person's address, no other company's address.
    assert [e["email"] for e in acme.emails] == ["sales@acmepay.com"]
    assert acme.addresses and "12 MG Road" in acme.addresses[0]["address"]
    assert not by["missing.com"].found and not by["missing.com"].error
    assert all(r.url.host in ("index.commoncrawl.org", "data.commoncrawl.org") for r in seen)


def test_backs_off_on_503(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503) if len(calls) < 3 else httpx.Response(404)

    async def no_sleep(_):
        return None

    monkeypatch.setattr(homepages.asyncio, "sleep", no_sleep)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    page = asyncio.run(homepages.read_homepage(client, "CC-MAIN-2026-44", "slow.com"))
    assert len(calls) == 3 and not page.found and not page.error


def test_summary_report():
    s = homepages.Summary()
    s.add(homepages.Homepage("a.com", True, text="x" * 300, emails=[{"email": "info@a.com"}]))
    s.add(homepages.Homepage("b.com", False, error="ConnectError: boom"))
    report = s.report()
    assert "Homepage in Common Crawl:              1   50.0%" in report
    assert "ConnectError: 1" in report
