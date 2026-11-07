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
