"""Reading company homepages from Common Crawl, with Common Crawl replaced by a fake transport."""

from __future__ import annotations

import asyncio
import gzip
import json

import httpx
import pytest

from app.kb import homepages


@pytest.fixture(autouse=True)
def _no_pause_left_over(monkeypatch):
    """A slow-down pause set by one test must not hold up the next."""
    monkeypatch.setattr(homepages, "_pause_until", 0.0)

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
    crawls = asyncio.run(homepages.collect(["acmepay.com", "missing.com"], None, pages.append, tmp_path, 2,
                                           client=client))
    assert crawls == ["CC-MAIN-2026-44"]  # the newest crawl
    crawl = crawls[0]
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
    assert by["missing.com"].miss == "no_capture"
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
    assert "Homepage found:                        1   50.0%" in report
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
    assert asyncio.run(homepages.latest_crawls(client, 2)) == ["CC-MAIN-2026-44", "CC-MAIN-2026-40"]


class _FakeReader(homepages.IndexReader):
    def __init__(self, crawl, lines):
        self.crawl = crawl
        self.index = homepages.ClusterIndex(["a)/ 1\tcdx.gz\t0\t1\t1"])
        self.lines = sorted(lines)
        self.blocks = {}

    async def _block(self, block):
        return self.lines


def test_lookup_follows_redirects_and_explains_misses():
    lines = [
        _cdx_line("com,moved)/", "https://moved.com/", "f", 0, 1, status="301"),
        _cdx_line("com,moved)/en/", "https://moved.com/en/", "f", 5, 1),
        _cdx_line("com,gone)/", "https://gone.com/", "f", 0, 1, status="404"),
        _cdx_line("com,stand)/", "https://stand.com/", "f", 0, 1, status="500"),
        _cdx_line("com,stand)/index.html", "https://stand.com/index.html", "f", 9, 1),
        _cdx_line("com,pdf)/", "https://pdf.com/", "f", 0, 1, mime="application/pdf"),
    ]
    lines = [ln.replace('"status": "301"', '"status": "301", "redirect": "/en/"') for ln in lines]
    reader = _FakeReader("CC-MAIN-2026-44", lines)
    capture, miss, moved = asyncio.run(reader.lookup("moved.com"))
    assert capture["url"] == "https://moved.com/en/" and moved == "https://moved.com/en/" and not miss
    assert asyncio.run(reader.lookup("gone.com"))[:2] == (None, "error_status_404")
    assert asyncio.run(reader.lookup("stand.com"))[0]["url"] == "https://stand.com/index.html"
    assert asyncio.run(reader.lookup("pdf.com"))[:2] == (None, "not_html")
    assert asyncio.run(reader.lookup("never.com"))[:2] == (None, "no_capture")
    assert homepages.url_key("https://www.Acme.com/En/?a=1") == "com,acme)/en/?a=1"


def test_older_crawl_is_tried_when_the_newest_lacks_the_homepage():
    new = _FakeReader("CC-MAIN-2026-44", [])
    old = _FakeReader("CC-MAIN-2026-40", [_cdx_line("com,acmepay)/", "https://acmepay.com/", "x/home.warc.gz",
                                                     100, len(_warc(HTML)))])
    seen = []
    client = httpx.AsyncClient(transport=_transport(_warc(HTML), seen))
    page = asyncio.run(homepages.read_homepage(client, [new, old], "acmepay.com"))
    assert page.found and page.crawl == "CC-MAIN-2026-40"
    miss = asyncio.run(homepages.read_homepage(client, [new, old], "nobody.com"))
    assert not miss.found and miss.miss == "no_capture" and miss.crawl == "CC-MAIN-2026-44"


def test_a_refused_index_block_fails_only_its_domain_and_is_retried_later(tmp_path, monkeypatch):
    async def no_sleep(_):
        return None

    monkeypatch.setattr(homepages.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(homepages, "_pause_until", 0.0)
    warc = _warc(HTML)
    cluster, cdx = _setup(warc)
    refused = {"left": 5}  # the CDN refuses the block for one domain's whole retry budget

    def handler(request):
        path = request.url.path
        if path == "/collinfo.json":
            return httpx.Response(200, json=[{"id": "CC-MAIN-2026-44"}])
        if path.endswith("/cluster.idx"):
            return httpx.Response(200, text=cluster)
        if path.endswith("/cdx-00000.gz"):
            if refused["left"]:
                refused["left"] -= 1
                return httpx.Response(403, text="Request blocked")
            start, end = map(int, request.headers["Range"].removeprefix("bytes=").split("-"))
            return httpx.Response(206, content=cdx[start:end + 1])
        if path == "/x/home.warc.gz":
            return httpx.Response(206, content=warc)
        return httpx.Response(500)

    pages: list[homepages.Homepage] = []
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    asyncio.run(homepages.collect(["aaa.com", "acmepay.com"], None, pages.append, tmp_path, 1, client=client))
    by = {p.domain: p for p in pages}
    assert by["aaa.com"].error.startswith("HTTPStatusError")  # refused five times: recorded, not a crash
    assert by["acmepay.com"].found  # the block was fetched again for the next domain
    assert homepages._pause_until > 0  # the 403s paused everyone


def test_own_fetch_first_and_common_crawl_only_for_live_sites_it_missed():
    new = _FakeReader("CC-MAIN-2026-44", [_cdx_line("com,gone)/", "https://gone.com/", "f", 0, 1, status="404"),
                                          _cdx_line("com,acmepay)/", "https://acmepay.com/", "x/home.warc.gz",
                                                    100, len(_warc(HTML)))])
    calls = []
    misses = {"gone.com": "site_timeout", "dead.com": "dns_dead", "acmepay.com": "site_http_403"}

    async def own(domain):
        calls.append(domain)
        if domain == "mine.com":
            return homepages.Homepage(domain, found=True, crawl="own", url="https://mine.com/")
        return homepages.Homepage(domain, found=False, crawl="own", miss=misses[domain])

    seen = []
    client = httpx.AsyncClient(transport=_transport(_warc(HTML), seen))
    read = lambda d: asyncio.run(homepages.read_homepage(client, [new], d, own))  # noqa: E731
    assert read("mine.com").crawl == "own" and not seen  # found by our fetch: Common Crawl not asked
    assert read("dead.com").miss == "dns_dead" and not seen  # dead domain: Common Crawl not asked
    assert read("gone.com").miss == "error_status_404+site_timeout"
    page = read("acmepay.com")  # our fetch was refused; Common Crawl's copy is used
    assert page.found and page.crawl == "CC-MAIN-2026-44"
    assert calls == ["mine.com", "dead.com", "gone.com", "acmepay.com"]


def test_a_common_crawl_pause_does_not_hold_up_the_own_fetch(tmp_path, monkeypatch):
    """The two lanes: every own fetch finishes while Common Crawl's lane is still waiting."""
    order = []
    released = asyncio.Event()

    async def slow_cc(client, readers, domain, slots):
        await released.wait()
        order.append(f"cc:{domain}")
        return homepages.Homepage(domain, found=False, crawl="CC", miss="no_capture")

    async def own(domain):
        order.append(f"own:{domain}")
        if domain == "d9.com":
            released.set()  # Common Crawl answers only once the last own fetch has run
        return homepages.Homepage(domain, found=False, crawl="own", miss="site_timeout")

    async def no_index(client, crawl, data_dir):
        return homepages.ClusterIndex(["a)/ 1\tcdx.gz\t0\t1\t1"])

    monkeypatch.setattr(homepages, "common_crawl_page", slow_cc)
    monkeypatch.setattr(homepages, "cluster_index", no_index)
    monkeypatch.setattr(homepages, "OWN_WORKERS", 2)
    pages = []
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    domains = [f"d{i}.com" for i in range(10)]
    asyncio.run(homepages.collect(domains, ["CC-MAIN-2026-44"], pages.append, tmp_path, 1, client=client,
                                  own_fetch=own))
    assert len(pages) == 10 and all(p.miss == "no_capture+site_timeout" for p in pages)
    assert all(o.startswith("own:") for o in order[:10])  # no own fetch waited for Common Crawl
