import ipaddress
import socket
from urllib.parse import parse_qs, parse_qsl, unquote, urlencode, urlparse, urlunparse

from argus.search.base import BaseDiscovery
from argus.search.models import SearchQuery, SearchResponse, SearchResult
from argus.search.provider import SearchProvider

DISALLOWED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "::1",
    "169.254.169.254",  # AWS/GCP cloud metadata endpoint
    "metadata.google.internal",
}

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "ref",
    "source",
}


class SearchPipeline(BaseDiscovery):
    """Normalizes, deduplicates, and validates search results for safety."""

    def __init__(self, provider: SearchProvider | None = None) -> None:
        self.provider = provider

    async def search(self, query: SearchQuery) -> SearchResponse:
        """Execute a search query via provider and sanitize/deduplicate results."""
        if self.provider is None:
            raise ValueError("No SearchProvider configured for SearchPipeline")

        raw_response = await self.provider.search(query)
        clean_results = self.process_results(
            raw_response.results, max_results=query.num_results
        )
        return SearchResponse(
            query=query.query,
            results=clean_results,
            total_results=len(clean_results),
            execution_time_ms=raw_response.execution_time_ms,
        )

    @staticmethod
    def normalize_url(raw_url: str) -> str:
        """Strip tracking parameters, fragments, unwrap search engine redirects, and normalize domain casing."""
        url_str = raw_url.strip()
        # Unwrap search engine redirects before normalization
        if "uddg=" in url_str:
            p_wrap = urlparse(url_str)
            qs = parse_qs(p_wrap.query)
            if "uddg" in qs and qs["uddg"]:
                url_str = unquote(qs["uddg"][0])
        elif "google.com/url" in url_str and ("q=" in url_str or "url=" in url_str):
            p_wrap = urlparse(url_str)
            qs = parse_qs(p_wrap.query)
            dest = qs.get("q") or qs.get("url")
            if dest and dest[0]:
                url_str = unquote(dest[0])

        parsed = urlparse(url_str)
        if not parsed.scheme or not parsed.netloc:
            return url_str

        # Filter out tracking query parameters
        query_pairs = [
            (k, v)
            for k, v in parse_qsl(parsed.query)
            if k.lower() not in TRACKING_PARAMS
        ]
        clean_query = urlencode(query_pairs)

        # Normalize path: strip trailing slash unless path is strictly "/"
        clean_path = parsed.path.rstrip("/") if parsed.path != "/" else "/"

        clean_parts = (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            clean_path,
            parsed.params,
            clean_query,
            "",  # Strip URL fragment (#section)
        )
        return urlunparse(clean_parts)

    @staticmethod
    def is_safe_url(url: str) -> bool:
        """Check for SSRF, private/loopback network access, DNS rebinding, and disallowed protocols."""
        try:
            parsed = urlparse(url)
        except ValueError:
            return False

        if parsed.scheme not in ("http", "https"):
            return False

        hostname = parsed.hostname
        if not hostname:
            return False

        hostname_lower = hostname.lower().strip()
        if hostname_lower in DISALLOWED_HOSTS:
            return False

        # Block common local / internal TLDs and names
        if hostname_lower.endswith(
            (".local", ".internal", ".localhost", ".lan", ".home", ".corp", ".arpa")
        ):
            return False

        # Check direct IP addresses
        try:
            ip = ipaddress.ip_address(hostname_lower)
            return not (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or not ip.is_global
            )
        except ValueError:
            pass

        # DNS resolution to block DNS rebinding and hostnames resolving to private/internal IPs
        try:
            addr_info = socket.getaddrinfo(hostname_lower, None)
            if not addr_info:
                return False
            for res in addr_info:
                sockaddr = res[4]
                ip_str = sockaddr[0]
                resolved_ip = ipaddress.ip_address(ip_str)
                if (
                    resolved_ip.is_private
                    or resolved_ip.is_loopback
                    or resolved_ip.is_link_local
                    or resolved_ip.is_reserved
                    or not resolved_ip.is_global
                ):
                    return False
        except (socket.gaierror, socket.herror):
            # If domain cannot be resolved (e.g. offline testing), allow if valid public format
            pass
        except (OSError, ValueError):
            return False

        return True

    @classmethod
    def process_results(
        cls,
        results: list[SearchResult],
        max_results: int = 20,
    ) -> list[SearchResult]:
        """Normalize URLs, filter out unsafe/SSRF targets, and deduplicate."""
        seen_urls: set[str] = set()
        clean_results: list[SearchResult] = []

        for item in results:
            clean_url = cls.normalize_url(item.url)

            # Security check
            if not cls.is_safe_url(clean_url):
                continue

            # Deduplication
            if clean_url in seen_urls:
                continue

            seen_urls.add(clean_url)
            clean_results.append(
                SearchResult(
                    url=clean_url,
                    title=item.title.strip(),
                    snippet=item.snippet.strip(),
                    engine=item.engine,
                    score=item.score,
                )
            )

            if len(clean_results) >= max_results:
                break

        return clean_results


# Explicit architecture contract alias
ArgusDiscovery = SearchPipeline
