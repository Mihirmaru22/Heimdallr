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


def _cdx_line(surt, url, filename, offset, length, status="200", mime="text/html"):
    return f"{surt} 20261005100000 " + json.dumps({"url": url, "mime": mime, "status": status,
                                                    "filename": filename, "offset": str(offset),
                                                    "length": str(length)})


def _setup(warc: bytes):
    block0 = "\n".join([
        _cdx_line("com,aaa)/", "https://aaa.com/", "x/a.warc.gz", 0, 10),
        _cdx_line("com,acmepay)/", "http://acmepay.com/", "x/old.warc.gz", 0, 10),
        _cdx_line("com,acmepay)/", "https://www.acmepay.com/", "x/home.warc.gz", 100, len(warc)),
        _cdx_line("com,acmepay)/", "https://acmepay.com/", "x/err.warc.gz", 0, 10, status="404"),
        _cdx_line("com,acmepay)/about", "https://acmepay.com/about", "x/about.warc.gz", 0, 10),
    ]).encode()
    block1 = _cdx_line("com,zzz)/", "https://zzz.com/", "x/z.warc.gz", 0, 10).encode()
    gz0, gz1 = gzip.compress(block0), gzip.compress(block1)
    cdx = gz0 + gz1
    cluster = (f"com,aaa)/ 20261005100000\tcdx-00000.gz\t0\t{len(gz0)}\t1\n"
               f"com,zzz)/ 20261005100000\tcdx-00000.gz\t{len(gz0)}\t{len(gz1)}\t2\n")
    return cluster, cdx


def _transport(warc: bytes, seen: list[httpx.Request]):
    cluster, cdx = _setup(warc)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        if path == "/collinfo.json":
            return httpx.Response(200, json=[{"id": "CC-MAIN-2026-44"}, {"id": "CC-MAIN-2026-40"}])
        if path.endswith("/cluster.idx"):
            return httpx.Response(200, text=cluster)
        if path.endswith("/cdx-00000.gz"):
            start, end = map(int, request.headers["Range"].removeprefix("bytes=").split("-"))
            return httpx.Response(206, content=cdx[start:end + 1])
        if path == "/x/home.warc.gz":
            assert request.headers["Range"].startswith("bytes=100-")
            return httpx.Response(206, content=warc)
        return httpx.Response(500)

    return httpx.MockTransport(handler)


def test_reads_the_homepage_record_and_keeps_company_fields(tmp_path):
    seen: list[httpx.Request] = []
    pages: list[homepages.Homepage] = []
    client = httpx.AsyncClient(transport=_transport(_warc(HTML), seen))
    crawl = asyncio.run(homepages.collect(["acmepay.com", "missing.com"], None, pages.append, tmp_path, 2,
                                          client=client))
    assert crawl == "CC-MAIN-2026-44"  # the newest crawl
    assert (tmp_path / "commoncrawl" / crawl / "cluster.idx").exists()
    by = {p.domain: p for p in pages}
    acme = by["acmepay.com"]
    assert acme.found and acme.url == "https://www.acmepay.com/"  # https homepage, not /about or a 404
    assert acme.fetched_at == "2026-10-05T10:00:00Z"
    assert acme.title.startswith("Acme Pay")
    assert "card terminals" in acme.description
    assert "small shops across India" in acme.text
    # Company mailboxes only: no person's address, no other company's address.
    assert [e["email"] for e in acme.emails] == ["sales@acmepay.com"]
    assert acme.addresses and "12 MG Road" in acme.addresses[0]["address"]
    assert not by["missing.com"].found and not by["missing.com"].error
    assert all(r.url.host in ("index.commoncrawl.org", "data.commoncrawl.org") for r in seen)
    # Both domains sit in the first block: it was fetched once.
    assert sum(r.url.path.endswith("cdx-00000.gz") for r in seen) == 1


def test_blocks_for_includes_blocks_that_start_with_the_key():
    index = homepages.ClusterIndex([
        "com,a)/ 1\tcdx-0.gz\t0\t10\t1",
        "com,b)/ 1\tcdx-0.gz\t10\t10\t2",
        "com,b)/ 2\tcdx-0.gz\t20\t10\t3",
        "com,c)/ 1\tcdx-0.gz\t30\t10\t4",
    ])
    assert [b[1] for b in index.blocks_for("com,b)/")] == [0, 10, 20]
    assert [b[1] for b in index.blocks_for("com,bb)/")] == [20]
    assert [b[1] for b in index.blocks_for("aaa)/")] == [0]
    assert homepages.surt_key("www.Acme.co.uk") == "uk,co,acme,www)/"
    assert homepages.surt_key("acme.co.uk") == "uk,co,acme)/"


def test_backs_off_on_503_and_timeouts(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectTimeout("slow")
        return httpx.Response(503) if len(calls) < 3 else httpx.Response(200, text="ok")

    async def no_sleep(_):
        return None

    monkeypatch.setattr(homepages.asyncio, "sleep", no_sleep)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    response = asyncio.run(homepages._get(client, "https://data.commoncrawl.org/x"))
    assert len(calls) == 3 and response.status_code == 200


def test_summary_report():
    s = homepages.Summary()
    s.add(homepages.Homepage("a.com", True, text="x" * 300, emails=[{"email": "info@a.com"}]))
    s.add(homepages.Homepage("b.com", False, error="ConnectError: boom"))
    report = s.report()
    assert "Homepage in Common Crawl:              1   50.0%" in report
    assert "ConnectError: 1" in report


def test_latest_crawl_falls_back_when_the_index_server_is_down(monkeypatch):
    async def no_sleep(_):
        return None

    monkeypatch.setattr(homepages.asyncio, "sleep", no_sleep)

    def handler(request):
        if request.url.host == "index.commoncrawl.org":
            return httpx.Response(504)
        return httpx.Response(200, text="<a>CC-MAIN-2026-40</a><a>CC-MAIN-2026-44</a><a>CC-MAIN-2025-51</a>")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    assert asyncio.run(homepages.latest_crawl(client)) == "CC-MAIN-2026-44"
