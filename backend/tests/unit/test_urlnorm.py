from app.crawl.urlnorm import looks_like_page, normalize_url, registered_domain, url_hash


def test_normalize_basics():
    assert normalize_url("HTTP://Example.com:80/a/../b/./c?utm_source=x&b=2&a=1#frag") == "http://example.com/b/c?a=1&b=2"
    assert normalize_url("https://example.com:443") == "https://example.com/"
    assert normalize_url("/contact", base="https://example.com/about/") == "https://example.com/contact"


def test_normalize_rejects_non_http():
    assert normalize_url("mailto:a@b.com") is None
    assert normalize_url("javascript:void(0)") is None


def test_hash_stable_for_equivalent_urls():
    a = normalize_url("https://example.com/x?b=1&a=2")
    b = normalize_url("https://EXAMPLE.com/x?a=2&b=1#top")
    assert url_hash(a) == url_hash(b)


def test_registered_domain_uses_public_suffix_list():
    assert registered_domain("https://shop.example.co.uk/x") == "example.co.uk"
    assert registered_domain("www.example.com") == "example.com"


def test_looks_like_page():
    assert looks_like_page("https://example.com/about")
    assert not looks_like_page("https://example.com/brochure.pdf")
