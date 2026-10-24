"""Company names read off list pages ("Top 10 ... companies"), each kept only once its own website checks out."""

import json

import httpx

from app.discovery.lists import looks_like_list, names_on_list, short_lines
from app.discovery.providers import SearxngProvider
from app.evidence.judge import Judge
from app.extract.deterministic import parse_page
from app.llm.openrouter import LLMUnavailable, Reply
from app.search import SearchHub, SearxngBackend, TavilyBackend, Usage
from app.spec.models import ExtractionSpec

LIST = ("<html><head><title>Top 3 cybersecurity companies in the UK</title></head><body>"
        "<h1>Top 3 cybersecurity companies in the UK</h1><ol><li>1. Sophos</li><li>2. NCC Group</li>"
        "<li>3. Egress Software</li></ol><p>This guide is sponsored by Acme Ads. Read our long introduction to "
        "the cybersecurity market in Britain, which has grown a lot in recent years.</p></body></html>")
HOMES = {"https://www.sophos.com/": "Sophos | Cybersecurity as a service",
         "https://www.nccgroup.com/": "NCC Group | Cyber security consultancy"}


class Router:
    def __init__(self, names=None, error=None):
        self.names, self.error, self.calls = names, error, 0

    async def chat(self, messages, **_kw):
        self.calls += 1
        if self.error:
            raise self.error
        return Reply(json.dumps({"names": self.names}), "m:free")

    async def aclose(self):
        pass


def test_a_list_page_is_known_by_its_shape_not_its_site():
    assert looks_like_list("https://news.example/top-uk-cyber", "Top 20 Cybersecurity Companies in the UK", "companies")
    assert not looks_like_list("https://www.sophos.com/", "Sophos companies", "companies")  # a homepage
    assert not looks_like_list("https://blog.example/post", "How to choose a firewall", "companies")


async def test_the_model_only_points_at_names_written_on_the_page():
    doc = parse_page("https://news.example/top-uk-cyber", LIST)
    assert "Sophos" in short_lines(doc) and not any("introduction" in ln for ln in short_lines(doc))
    names, why = await names_on_list(Judge(Router(["Sophos", "NCC Group", "Darktrace"])), "cyber UK", doc)
    assert names == ["Sophos", "NCC Group"] and why == ""  # Darktrace is not on the page
    names, why = await names_on_list(Judge(Router(error=LLMUnavailable("no OpenRouter key is configured"))),
                                     "cyber UK", doc)
    assert names == [] and "no OpenRouter key" in why


async def test_discovery_reads_list_pages_and_keeps_only_names_whose_website_checks_out(tmp_path, monkeypatch):
    def handler(request):
        if request.url.host == "api.tavily.com":
            return httpx.Response(200, json={"results": [
                {"url": "https://news.example/top-uk-cyber", "title": "Top 3 cybersecurity companies in the UK"}]})
        q = request.url.params["q"]
        site = {"Sophos": "https://www.sophos.com/", "NCC Group": "https://www.nccgroup.com/"}
        for name, home in site.items():
            if q.startswith(name):
                return httpx.Response(200, json={"results": [{"url": home}] * 5})
        return httpx.Response(200, json={"results": []})  # Egress: search finds nothing

    async def fetch_page(url):
        if url == "https://news.example/top-uk-cyber":
            return parse_page(url, LIST)
        return parse_page(url, f"<html><head><title>{HOMES[url]}</title></head><body>x</body></html>") \
            if url in HOMES else None

    monkeypatch.setattr(SearchHub, "from_settings", classmethod(lambda cls, c, url=None: cls(
        c, [TavilyBackend("t-key"), SearxngBackend("http://searx")], Usage(tmp_path / "u.json"))))
    spec = ExtractionSpec.model_validate({"entity": "company", "fields": [
        {"name": "company_name", "type": "string", "semantic": "company_name", "required": True}],
        "discovery": {"providers": ["searxng"], "industry": "cybersecurity", "countries": ["GB"]}})
    router = Router(["Sophos", "NCC Group", "Egress Software"])
    p = SearxngProvider(httpx.AsyncClient(transport=httpx.MockTransport(handler)), base_url="",
                        judge=Judge(router))
    p.fetch_page = fetch_page
    found = await p.discover(spec)
    assert [(r.url, r.hint["company_name"]) for r in found] == [
        ("https://www.sophos.com/", "Sophos"), ("https://www.nccgroup.com/", "NCC Group")]
    assert all(r.referrer == "list page: https://news.example/top-uk-cyber" for r in found)
    assert router.calls == 1  # one model call for the one list page
