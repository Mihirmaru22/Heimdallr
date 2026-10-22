"""URL normalization so the same page is crawled once."""

import hashlib
import re
from urllib.parse import parse_qsl, quote, unquote, urlencode, urljoin, urlsplit, urlunsplit

import tldextract

# Offline suffix list: never fetch the public suffix list at runtime.
_extract = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)

TRACKING_PARAMS = {"gclid", "fbclid", "msclkid", "mc_cid", "mc_eid", "_ga", "ref", "ref_src"}
SKIP_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".css", ".js", ".mjs", ".pdf", ".zip",
    ".gz", ".tar", ".rar", ".7z", ".exe", ".dmg", ".mp3", ".mp4", ".avi", ".mov", ".woff", ".woff2",
    ".ttf", ".eot", ".xml", ".rss", ".json", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
)


def normalize_url(url: str, base: str | None = None) -> str | None:
    """Absolute, lower-case host, no fragment, no default port, sorted query without trackers."""
    if base:
        url = urljoin(base, url.strip())
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https") or not parts.hostname:
        return None
    host = parts.hostname.lower().rstrip(".")
    netloc = host if port is None or (scheme, port) in (("http", 80), ("https", 443)) else f"{host}:{port}"
    path = quote(unquote(_remove_dot_segments(parts.path or "/")), safe="/%:@!$&'()*+,;=-._~")
    query_items = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS and not k.lower().startswith("utm_")
    ]
    query = urlencode(sorted(query_items))
    return urlunsplit((scheme, netloc, path, query, ""))


def _remove_dot_segments(path: str) -> str:
    out: list[str] = []
    for seg in path.split("/"):
        if seg == "..":
            if len(out) > 1:
                out.pop()
        elif seg != ".":
            out.append(seg)
    result = "/".join(out)
    if path.endswith(("/.", "/..")):
        result += "/"
    return result if result.startswith("/") else "/" + result


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def registered_domain(url_or_host: str) -> str:
    host = urlsplit(url_or_host).hostname if "://" in url_or_host else url_or_host
    if not host or not re.fullmatch(r"[A-Za-z0-9.-]+", host):
        return ""  # "javascript:alert(1)", "//x/y" or a mailto: is not a host
    ext = _extract(host or "")
    return ext.top_domain_under_public_suffix or (host or "")


def has_public_suffix(url_or_host: str) -> bool:
    """False for hosts no one can register, such as "www.example" with its ending missing."""
    host = urlsplit(url_or_host).hostname if "://" in url_or_host else url_or_host
    return bool(_extract(host or "").suffix)


def same_site(url: str, allowed_domains: set[str]) -> bool:
    return registered_domain(url) in allowed_domains


def looks_like_page(url: str) -> bool:
    return not urlsplit(url).path.lower().endswith(SKIP_EXTENSIONS)


def homepage(url: str) -> str:
    """A company's website as people write it: "https://oushadhi.org/category.php?slug=x" -> "https://oushadhi.org/".

    A one-segment language or country path is kept ("https://neulandlabs.com/en"); anything deeper, a file
    or a query string means the registry pointed at an inner page, so the site's root is used.
    """
    p = urlsplit(url)
    if not p.scheme or not p.netloc:
        return url
    path = p.path.strip("/")
    if p.query or "/" in path or "." in path or len(path) > 5:
        path = ""
    return urlunsplit((p.scheme, p.netloc, f"/{path}" if path else "/", "", ""))
