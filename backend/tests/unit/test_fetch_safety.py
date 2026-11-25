"""One page that cannot be fetched is that page's failure, never the job's; the crawler keeps no cookies."""

import httpx
import pytest

from app.crawl.fetcher import Fetcher, FetchError
from app.crawl.netguard import NoCookies, make_client


async def test_an_error_the_http_library_raises_for_one_page_marks_only_that_page_unreadable():
    def handler(request):
        raise UnicodeEncodeError("ascii", "ā", 0, 1, "ordinal not in range(128)")  # a header it cannot encode

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    fetcher = Fetcher(client, resolver=lambda host, port: ["93.184.216.34"])
    with pytest.raises(FetchError) as exc:
        await fetcher.fetch("https://news.example/article", attempts=1)
    assert exc.value.kind == "request" and not exc.value.retryable


async def test_the_crawler_keeps_no_cookie_a_site_sets():
    client = make_client()
    try:
        assert isinstance(client.cookies.jar, NoCookies)
        client.cookies.set("session", "ā-value", domain="news.example")  # what a response would store
        assert list(client.cookies.jar) == []
    finally:
        await client.aclose()


async def test_a_host_that_refuses_the_crawler_user_agent_is_read_with_the_fallback_one():
    from app.config import get_settings
    from app.crawl import fetcher as fetcher_mod

    fetcher_mod.FALLBACK_HOSTS.discard("walled.example")
    ours, browser = get_settings().user_agent, get_settings().fallback_user_agent
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        ua = request.headers["user-agent"]
        seen.append(ua)
        if ua != browser:
            return httpx.Response(403, text="Access Denied")
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<p>ok</p>")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), headers={"User-Agent": ours})
    fetcher = Fetcher(client, resolver=lambda host, port: ["93.184.216.34"])
    assert (await fetcher.fetch("https://walled.example/a")).status == 200
    assert (await fetcher.fetch("https://walled.example/b")).status == 200
    assert seen == [ours, browser, browser]  # one refused request for the host, then the fallback directly
    fetcher_mod.FALLBACK_HOSTS.discard("walled.example")


async def test_a_403_stays_a_403_when_the_fallback_user_agent_is_off(monkeypatch):
    from app.config import get_settings
    from app.crawl.fetcher import FetchError

    monkeypatch.setattr(get_settings(), "fallback_user_agent", "")
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(403)))
    fetcher = Fetcher(client, resolver=lambda host, port: ["93.184.216.34"])
    try:
        await fetcher.fetch("https://walled-off.example/a")
    except FetchError as exc:
        assert exc.kind == "http_403"
    else:
        raise AssertionError("expected a 403")
