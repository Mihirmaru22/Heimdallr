import pytest

from app.crawl.netguard import BlockedDestination, check_url, ip_is_public, parse_target


def public(host, port):
    return ["93.184.215.14"]


@pytest.mark.parametrize("ip", [
    "127.0.0.1", "10.0.0.1", "172.16.5.4", "192.168.1.1", "169.254.169.254", "100.64.0.1", "0.0.0.0",
    "::1", "fe80::1", "fc00::1", "::ffff:127.0.0.1", "2002:7f00:1::", "64:ff9b::a9fe:a9fe", "224.0.0.1",
    "255.255.255.255", "198.18.0.1",
])
def test_non_public_addresses(ip):
    assert not ip_is_public(ip)


@pytest.mark.parametrize("ip", ["93.184.215.14", "8.8.8.8", "2606:4700:4700::1111"])
def test_public_addresses(ip):
    assert ip_is_public(ip)


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/", "http://localhost/", "http://foo.localhost/", "http://169.254.169.254/latest/meta-data/",
    "http://[::1]/", "http://0x7f.1/", "http://2130706433/", "http://017700000001/", "http://10.1/",
    "http://metadata.google.internal/", "http://printer.local/", "http://[::ffff:169.254.169.254]/",
])
def test_internal_targets_blocked(url):
    with pytest.raises(BlockedDestination):
        check_url(url, resolver=public, allow_private=[])


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "ftp://example.com/", "gopher://example.com/", "javascript:alert(1)",
    "http://user:pw@example.com/", "http://example.com:22/", "http://example.com:6379/",
])
def test_bad_schemes_ports_and_credentials(url):
    with pytest.raises(BlockedDestination):
        check_url(url, resolver=public, allow_private=[])


def test_dns_answer_with_any_private_address_is_blocked():
    def mixed(host, port):
        return ["93.184.215.14", "10.0.0.5"]

    with pytest.raises(BlockedDestination, match="non-public"):
        check_url("https://rebind.example/", resolver=mixed, allow_private=[])


def test_public_host_allowed_and_addresses_returned():
    dest = check_url("https://example.com/path", resolver=public, allow_private=[])
    assert dest.host == "example.com" and dest.port == 443 and dest.addresses == ("93.184.215.14",)


def test_private_exception_needs_exact_host_and_port():
    def local(host, port):
        return ["127.0.0.1"]

    assert check_url("http://site.test:8765/", resolver=local, allow_private=["site.test:8765"])
    with pytest.raises(BlockedDestination):
        check_url("http://site.test:8766/", resolver=local, allow_private=["site.test:8765"])
    with pytest.raises(BlockedDestination):
        check_url("http://other.test:8765/", resolver=local, allow_private=["site.test:8765"])


def test_parse_target_defaults_ports_and_idna():
    assert parse_target("https://Example.COM./") == ("https", "example.com", 443)
    assert parse_target("http://bücher.example/")[1] == "xn--bcher-kva.example"
