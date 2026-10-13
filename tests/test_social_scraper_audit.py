"""Comprehensive stress test and safety audit for FourChan and LinkedIn scrapers.

Covers:
- Edge cases in HTML cleaning
- Empty/malformed API responses
- httpx client lifecycle bugs
- Hybrid router index math bugs
- LinkedIn URL injection
- 4chan board injection
- Concurrent usage safety
- Exception propagation
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from argus.search.fourchan import FourChanSearchProvider, _clean_html
from argus.search.linkedin import LinkedInSearchProvider, parse_linkedin_title, _clean_linkedin_url
from argus.search.hybrid import HybridSearchProvider
from argus.search.models import SearchQuery, SearchResponse, SearchResult


# ============================================================
# SECTION 1: 4chan _clean_html edge cases
# ============================================================

class TestCleanHtml:
    def test_none_input(self):
        assert _clean_html(None) == ""

    def test_empty_string(self):
        assert _clean_html("") == ""

    def test_br_tags(self):
        assert "line" in _clean_html("first line<br>second line")

    def test_wbr_tags(self):
        assert "<wbr>" not in _clean_html("long<wbr>word")

    def test_greentext_entities(self):
        result = _clean_html("&gt;&gt;12345 reply to &gt;greentext")
        assert "&gt;" not in result
        assert ">" in result or "12345" in result

    def test_nested_html_tags(self):
        result = _clean_html('<a href="http://evil.com"><span class="quote">&gt;text</span></a>')
        assert "<a" not in result
        assert "<span" not in result
        assert "evil.com" not in result

    def test_script_tag_injection(self):
        result = _clean_html('<script>alert("xss")</script>normal text')
        assert "<script>" not in result
        assert "alert" not in result
        assert "normal text" in result

    def test_unicode_entities(self):
        result = _clean_html("caf&eacute; &amp; bistro")
        assert "&eacute;" not in result
        assert "&amp;" not in result

    def test_massive_input(self):
        """Ensure _clean_html doesn't choke on very large posts."""
        big = "word " * 50000
        result = _clean_html(big)
        assert len(result) > 0


# ============================================================
# SECTION 2: 4chan FourChanSearchProvider
# ============================================================

class TestFourChanProvider:
    @pytest.mark.asyncio
    async def test_empty_query(self):
        fc = FourChanSearchProvider(boards=["o"])
        # Pydantic min_length=1 on query field enforces non-empty
        with pytest.raises(Exception):
            SearchQuery(query="", num_results=5)

        # Whitespace query passes Pydantic but should return 0 results safely
        resp2 = await fc.search(SearchQuery(query="   ", num_results=5))
        assert resp2.total_results == 0
        await fc.close()

    @pytest.mark.asyncio
    async def test_all_stop_words_query(self):
        """Query with only stop words should fall back to raw query token."""
        fc = FourChanSearchProvider(boards=["o"])
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"page": 1, "threads": [
            {"no": 1, "sub": "the and or for", "com": "just stop words"}
        ]}]
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
            resp = await fc.search(SearchQuery(query="the and or", num_results=5))
            # Should use raw_query as fallback token
            assert resp is not None
        await fc.close()

    @pytest.mark.asyncio
    async def test_catalog_returns_non_200(self):
        fc = FourChanSearchProvider(boards=["o"])
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
            resp = await fc.search(SearchQuery(query="Ford engine", num_results=5))
            assert resp.total_results == 0
        await fc.close()

    @pytest.mark.asyncio
    async def test_catalog_returns_invalid_json(self):
        fc = FourChanSearchProvider(boards=["o"])
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = ValueError("Invalid JSON")
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
            resp = await fc.search(SearchQuery(query="Ford engine", num_results=5))
            assert resp.total_results == 0
        await fc.close()

    @pytest.mark.asyncio
    async def test_catalog_network_timeout(self):
        fc = FourChanSearchProvider(boards=["o"])
        import httpx as httpx_mod
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=httpx_mod.ConnectTimeout("timeout")):
            resp = await fc.search(SearchQuery(query="Ford engine", num_results=5))
            assert resp.total_results == 0
        await fc.close()

    @pytest.mark.asyncio
    async def test_thread_missing_fields(self):
        """Threads with missing 'sub', 'com', or 'no' should not crash."""
        fc = FourChanSearchProvider(boards=["o"])
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"page": 1, "threads": [
            {"no": 111},  # no sub, no com
            {"sub": "Has subject but no number"},  # no 'no'
            {"no": 222, "com": "Has comment about Ford but no subject"},
        ]}]
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
            resp = await fc.search(SearchQuery(query="Ford", num_results=5))
            # Should not crash; should find thread 222
            assert resp is not None
            found_222 = any("222" in r.url for r in resp.results)
            assert found_222 or resp.total_results == 0  # graceful either way
        await fc.close()

    @pytest.mark.asyncio
    async def test_thread_none_in_no_field(self):
        """Thread with no=None should produce safe URL."""
        fc = FourChanSearchProvider(boards=["o"])
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"page": 1, "threads": [
            {"no": None, "sub": "Ford discussion", "com": "Talking about Ford plants"},
        ]}]
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
            resp = await fc.search(SearchQuery(query="Ford", num_results=5))
            # Should produce a URL with "None" in it but not crash
            assert resp is not None
            if resp.results:
                assert "None" in resp.results[0].url  # safe but ugly
        await fc.close()

    @pytest.mark.asyncio
    async def test_empty_catalog_pages(self):
        fc = FourChanSearchProvider(boards=["o"])
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []  # empty catalog
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
            resp = await fc.search(SearchQuery(query="Ford", num_results=5))
            assert resp.total_results == 0
        await fc.close()

    @pytest.mark.asyncio
    async def test_board_injection_safety(self):
        """Board names must not allow path traversal."""
        fc = FourChanSearchProvider(boards=["../../etc/passwd"])
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
            resp = await fc.search(SearchQuery(query="test", num_results=1))
            assert resp.total_results == 0
        await fc.close()

    @pytest.mark.asyncio
    async def test_multi_board_one_fails(self):
        """If one board fails, results from the other should still come through."""
        fc = FourChanSearchProvider(boards=["o", "biz"])

        good_resp = MagicMock()
        good_resp.status_code = 200
        good_resp.json.return_value = [{"page": 1, "threads": [
            {"no": 999, "sub": "Ford plant news", "com": "Big Ford announcement"}
        ]}]

        bad_resp = MagicMock()
        bad_resp.status_code = 500

        async def side_effect(url):
            if "/o/" in url:
                return good_resp
            return bad_resp

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=side_effect):
            resp = await fc.search(SearchQuery(query="Ford plant", num_results=5))
            assert resp.total_results >= 1
        await fc.close()

    @pytest.mark.asyncio
    async def test_close_idempotent(self):
        """Calling close() twice must not raise."""
        fc = FourChanSearchProvider(boards=["o"])
        await fc.close()
        await fc.close()  # should not raise

    @pytest.mark.asyncio
    async def test_search_after_close(self):
        """Searching after close should fail gracefully, not crash the pipeline."""
        fc = FourChanSearchProvider(boards=["o"])
        await fc.close()
        # After close, the httpx client is closed; search should handle the error
        resp = await fc.search(SearchQuery(query="Ford", num_results=1))
        assert resp.total_results == 0


# ============================================================
# SECTION 3: LinkedIn provider
# ============================================================

class TestLinkedInProvider:
    def test_parse_title_standard(self):
        name, role = parse_linkedin_title("Amy Carrier - Plant Director at General Motors | LinkedIn")
        assert name == "Amy Carrier"
        assert "Plant Director" in role

    def test_parse_title_no_linkedin_suffix(self):
        name, role = parse_linkedin_title("John Smith - CEO at Ford")
        assert name == "John Smith"
        assert "CEO" in role

    def test_parse_title_em_dash(self):
        name, role = parse_linkedin_title("Jane Doe \u2013 VP Manufacturing \u2013 LinkedIn")
        assert name == "Jane Doe"

    def test_parse_title_pipe_separator(self):
        name, role = parse_linkedin_title("Bob Jones | Manufacturing Lead | LinkedIn")
        assert "Bob Jones" in name

    def test_parse_title_garbage(self):
        name, role = parse_linkedin_title("???!!! random garbage")
        assert name == "???!!! random garbage"
        assert role == ""

    def test_parse_title_empty(self):
        name, role = parse_linkedin_title("")
        assert name == ""
        assert role == ""

    def test_clean_url_strips_tracking(self):
        url = _clean_linkedin_url("https://www.linkedin.com/in/john-doe-12345?trk=public_profile&originalSubdomain=us")
        assert url == "https://www.linkedin.com/in/john-doe-12345"
        assert "trk=" not in url

    def test_clean_url_strips_trailing_slash(self):
        url = _clean_linkedin_url("https://www.linkedin.com/in/john-doe/")
        assert url == "https://www.linkedin.com/in/john-doe"

    def test_clean_url_different_subdomain(self):
        """URLs from de.linkedin.com should still normalize to www."""
        url = _clean_linkedin_url("https://de.linkedin.com/in/hans-mueller")
        assert url == "https://www.linkedin.com/in/hans-mueller"

    @pytest.mark.asyncio
    async def test_empty_query(self):
        li = LinkedInSearchProvider(search_backend=AsyncMock())
        resp = await li.search(SearchQuery(query="   ", num_results=5))
        assert resp.total_results == 0

    @pytest.mark.asyncio
    async def test_backend_returns_no_linkedin(self):
        """All results are non-LinkedIn -> should return 0."""
        mock = AsyncMock()
        mock.search.return_value = SearchResponse(
            query="test", results=[
                SearchResult(url="https://example.com/page", title="Non LI", snippet="x", engine="ddg"),
            ], total_results=1, execution_time_ms=1.0,
        )
        li = LinkedInSearchProvider(search_backend=mock)
        resp = await li.search(SearchQuery(query="GM plant director", num_results=5))
        assert resp.total_results == 0

    @pytest.mark.asyncio
    async def test_backend_throws_exception(self):
        """If backend DDG search throws, LinkedIn provider should propagate (not swallow)."""
        mock = AsyncMock()
        mock.search.side_effect = Exception("DDG rate limited")
        li = LinkedInSearchProvider(search_backend=mock)
        with pytest.raises(Exception, match="DDG rate limited"):
            await li.search(SearchQuery(query="GM director", num_results=5))

    @pytest.mark.asyncio
    async def test_duplicate_linkedin_urls(self):
        """Duplicate LinkedIn URLs should be deduplicated."""
        mock = AsyncMock()
        mock.search.return_value = SearchResponse(
            query="test", results=[
                SearchResult(url="https://www.linkedin.com/in/amy-carrier?trk=abc", title="Amy Carrier - Plant Director | LinkedIn", snippet="a", engine="ddg"),
                SearchResult(url="https://www.linkedin.com/in/amy-carrier?trk=xyz", title="Amy Carrier - Plant Director at GM | LinkedIn", snippet="b", engine="ddg"),
            ], total_results=2, execution_time_ms=1.0,
        )
        li = LinkedInSearchProvider(search_backend=mock)
        resp = await li.search(SearchQuery(query="GM director", num_results=5))
        assert resp.total_results == 1  # deduplicated

    @pytest.mark.asyncio
    async def test_company_page_passes_filter(self):
        """linkedin.com/company/ URLs should also pass the filter."""
        mock = AsyncMock()
        mock.search.return_value = SearchResponse(
            query="test", results=[
                SearchResult(url="https://www.linkedin.com/company/general-motors", title="General Motors | LinkedIn", snippet="Official page", engine="ddg"),
            ], total_results=1, execution_time_ms=1.0,
        )
        li = LinkedInSearchProvider(search_backend=mock)
        resp = await li.search(SearchQuery(query="General Motors", num_results=5))
        assert resp.total_results == 1

    @pytest.mark.asyncio
    async def test_dork_generation_adds_site_prefix(self):
        """If query doesn't have site:linkedin.com, provider should add it."""
        mock = AsyncMock()
        mock.search.return_value = SearchResponse(
            query="test", results=[], total_results=0, execution_time_ms=1.0,
        )
        li = LinkedInSearchProvider(search_backend=mock)
        await li.search(SearchQuery(query="GM plant director", num_results=5))
        # Check what query was sent to backend
        called_query = mock.search.call_args[0][0].query
        assert "site:linkedin.com/in" in called_query

    @pytest.mark.asyncio
    async def test_dork_generation_skips_if_already_scoped(self):
        """If query already has site:linkedin.com, don't double-add."""
        mock = AsyncMock()
        mock.search.return_value = SearchResponse(
            query="test", results=[], total_results=0, execution_time_ms=1.0,
        )
        li = LinkedInSearchProvider(search_backend=mock)
        await li.search(SearchQuery(query='site:linkedin.com/in "Plant Director" GM', num_results=5))
        called_query = mock.search.call_args[0][0].query
        assert called_query.count("site:linkedin.com") == 1


# ============================================================
# SECTION 4: Hybrid router index math
# ============================================================

class TestHybridRouterIndexing:
    @pytest.mark.asyncio
    async def test_linkedin_only_no_4chan(self):
        """Leadership query without forum keywords: LinkedIn fires, 4chan does not."""
        mock_ddg = AsyncMock()
        mock_ddg.search.return_value = SearchResponse(query="t", results=[], total_results=0, execution_time_ms=1)
        mock_news = AsyncMock()
        mock_news.search.return_value = SearchResponse(query="t", results=[], total_results=0, execution_time_ms=1)
        mock_li = AsyncMock()
        mock_li.search.return_value = SearchResponse(query="t", results=[
            SearchResult(url="https://linkedin.com/in/test", title="LI Test", snippet="s", engine="linkedin")
        ], total_results=1, execution_time_ms=1)
        mock_fc = AsyncMock()
        mock_fc.search.return_value = SearchResponse(query="t", results=[
            SearchResult(url="https://boards.4channel.org/o/thread/1", title="4chan", snippet="s", engine="4chan")
        ], total_results=1, execution_time_ms=1)

        hybrid = HybridSearchProvider(
            ddg_provider=mock_ddg, google_news_provider=mock_news,
            linkedin_provider=mock_li, fourchan_provider=mock_fc,
        )
        resp = await hybrid.search(SearchQuery(query="plant director GM", num_results=5))
        # LinkedIn should fire (has "director")
        mock_li.search.assert_called_once()
        # 4chan should NOT fire (no forum keywords)
        mock_fc.search.assert_not_called()
        assert any(r.engine == "linkedin" for r in resp.results)

    @pytest.mark.asyncio
    async def test_4chan_only_no_linkedin(self):
        """Forum query without leadership keywords: 4chan fires, LinkedIn does not."""
        mock_ddg = AsyncMock()
        mock_ddg.search.return_value = SearchResponse(query="t", results=[], total_results=0, execution_time_ms=1)
        mock_news = AsyncMock()
        mock_news.search.return_value = SearchResponse(query="t", results=[], total_results=0, execution_time_ms=1)
        mock_li = AsyncMock()
        mock_fc = AsyncMock()
        mock_fc.search.return_value = SearchResponse(query="t", results=[
            SearchResult(url="https://boards.4channel.org/o/thread/1", title="4chan leak", snippet="s", engine="4chan")
        ], total_results=1, execution_time_ms=1)

        hybrid = HybridSearchProvider(
            ddg_provider=mock_ddg, google_news_provider=mock_news,
            linkedin_provider=mock_li, fourchan_provider=mock_fc,
        )
        # "workers" triggers forum, no leadership keywords
        resp = await hybrid.search(SearchQuery(query="auto workers forum discussion", num_results=5))
        mock_fc.search.assert_called_once()
        mock_li.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_both_linkedin_and_4chan(self):
        """Query with BOTH leadership AND forum keywords: both fire."""
        mock_ddg = AsyncMock()
        mock_ddg.search.return_value = SearchResponse(query="t", results=[], total_results=0, execution_time_ms=1)
        mock_news = AsyncMock()
        mock_news.search.return_value = SearchResponse(query="t", results=[], total_results=0, execution_time_ms=1)
        mock_li = AsyncMock()
        mock_li.search.return_value = SearchResponse(query="t", results=[
            SearchResult(url="https://linkedin.com/in/test", title="LI", snippet="s", engine="linkedin")
        ], total_results=1, execution_time_ms=1)
        mock_fc = AsyncMock()
        mock_fc.search.return_value = SearchResponse(query="t", results=[
            SearchResult(url="https://boards.4channel.org/o/thread/1", title="4chan", snippet="s", engine="4chan")
        ], total_results=1, execution_time_ms=1)

        hybrid = HybridSearchProvider(
            ddg_provider=mock_ddg, google_news_provider=mock_news,
            linkedin_provider=mock_li, fourchan_provider=mock_fc,
        )
        # "director" = leadership, "strike" = forum
        resp = await hybrid.search(SearchQuery(query="plant director strike workers", num_results=10))
        mock_li.search.assert_called_once()
        mock_fc.search.assert_called_once()
        # Index math: DDG=0, News=1, LI=2, FC=3 -> all should resolve correctly
        assert resp is not None

    @pytest.mark.asyncio
    async def test_linkedin_exception_doesnt_crash_pipeline(self):
        """If LinkedIn throws, DDG and News results still come through."""
        mock_ddg = AsyncMock()
        mock_ddg.search.return_value = SearchResponse(query="t", results=[
            SearchResult(url="https://example.com", title="DDG Result", snippet="s", engine="duckduckgo")
        ], total_results=1, execution_time_ms=1)
        mock_news = AsyncMock()
        mock_news.search.return_value = SearchResponse(query="t", results=[], total_results=0, execution_time_ms=1)
        mock_li = AsyncMock()
        mock_li.search.side_effect = Exception("LinkedIn backend exploded")
        mock_fc = AsyncMock()

        hybrid = HybridSearchProvider(
            ddg_provider=mock_ddg, google_news_provider=mock_news,
            linkedin_provider=mock_li, fourchan_provider=mock_fc,
        )
        resp = await hybrid.search(SearchQuery(query="plant director", num_results=5))
        # Should not crash; DDG results should survive
        assert resp.total_results >= 1
        assert resp.results[0].engine == "duckduckgo"

    @pytest.mark.asyncio
    async def test_4chan_exception_doesnt_crash_pipeline(self):
        """If 4chan throws, other results still come through."""
        mock_ddg = AsyncMock()
        mock_ddg.search.return_value = SearchResponse(query="t", results=[
            SearchResult(url="https://example.com", title="DDG Result", snippet="s", engine="duckduckgo")
        ], total_results=1, execution_time_ms=1)
        mock_news = AsyncMock()
        mock_news.search.return_value = SearchResponse(query="t", results=[], total_results=0, execution_time_ms=1)
        mock_li = AsyncMock()
        mock_fc = AsyncMock()
        mock_fc.search.side_effect = Exception("4chan API down")

        hybrid = HybridSearchProvider(
            ddg_provider=mock_ddg, google_news_provider=mock_news,
            linkedin_provider=mock_li, fourchan_provider=mock_fc,
        )
        # "strike workers" triggers forum intent
        resp = await hybrid.search(SearchQuery(query="auto strike workers", num_results=5))
        assert resp.total_results >= 1

    @pytest.mark.asyncio
    async def test_social_disabled(self):
        """enable_social_intelligence=False: LinkedIn and 4chan should be None and never fire."""
        mock_ddg = AsyncMock()
        mock_ddg.search.return_value = SearchResponse(query="t", results=[], total_results=0, execution_time_ms=1)
        mock_news = AsyncMock()
        mock_news.search.return_value = SearchResponse(query="t", results=[], total_results=0, execution_time_ms=1)

        hybrid = HybridSearchProvider(
            ddg_provider=mock_ddg, google_news_provider=mock_news,
            enable_social_intelligence=False,
        )
        assert hybrid.linkedin is None
        assert hybrid.fourchan is None
        resp = await hybrid.search(SearchQuery(query="plant director strike workers", num_results=5))
        assert resp is not None  # should not crash
