"""Own homepage fetch for sites Common Crawl lacks: DNS first, robots.txt obeyed, refusals left alone."""

from __future__ import annotations

import asyncio

import httpx

from app.kb.sitefetch import own_fetcher

PAGE = ("<html><head><title>Bolt Tools</title><meta name='description' content='Industrial bolts.'></head>"
        "<body><p>We make industrial bolts.</p><a href='mailto:info@bolt.com'>info</a></body></html>")


def _public(host, port):
    return ["93.184.216.34"]


def _run(domain, handler, alive=True):
    async def is_alive(_):
        return alive

    async def go():
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        fetch = own_fetcher(client, "TestBot/1.0", alive=is_alive, resolver=_public)
        return await fetch(domain)

    return asyncio.run(go())


def test_dead_domain_sends_nothing():
    seen = []
    page = _run("dead.com", lambda r: seen.append(r) or httpx.Response(200), alive=False)
    assert not page.found and page.miss == "dns_dead" and seen == []


def test_fetches_the_homepage_when_robots_allows():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private\n",
                                  headers={"content-type": "text/plain"})
        return httpx.Response(200, text=PAGE, headers={"content-type": "text/html"})

    page = _run("bolt.com", handler)
    assert page.found and page.crawl == "own" and page.url == "https://bolt.com/"
    assert page.description == "Industrial bolts."
    assert [e["email"] for e in page.emails] == ["info@bolt.com"]


def test_robots_disallow_is_obeyed():
    seen = []

    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(200, text="User-agent: *\nDisallow: /\n", headers={"content-type": "text/plain"})

    page = _run("private.com", handler)
    assert not page.found and page.miss == "robots_disallowed"
    assert "/" not in seen  # only robots.txt was ever requested


def test_a_403_is_left_alone():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(403)

    page = _run("guarded.com", handler)
    assert not page.found and page.miss == "site_http_403"
    assert seen.count("https://guarded.com/") == 1 and not any("www." in u or "http://" in u for u in seen)
