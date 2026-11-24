"""vendor_archive: the product maker's own customer stories and press releases, listed from its sitemaps.

Most proof of who uses a business product is published by its maker: in set 1, 18 of the 32 solid expected users
had their proof on the vendor's own site (customer stories on ptc.com, press releases on investor.ptc.com and
netsuite.com, Veeva announcements). Web search reaches those pages only when it happens to rank them, so the
case-study source saw a few of them and missed the rest. A site's sitemap lists all of its pages, so reading it
turns "hope search ranks it" into "every story the maker published is a candidate".

How, with no list of vendors or sites kept:
1. The maker's sites are the hosts in web search results for the product whose domain is the product's maker
   (the same test the proof reader uses: "ptc.com" makes "PTC Windchill"). Subdomains count separately
   (investor.ptc.com has its own sitemap).
2. Each host's sitemaps (named in its robots.txt, else /sitemap.xml) are read; a sitemap index is followed to
   the child sitemaps most likely to hold stories and releases first, within a fixed number of files.
3. Pages are kept by their address alone: a customer story or case study, or a news or release page whose
   address names the product. Copies of one page in several languages are kept once.
4. The kept pages are read exactly like the case-study source's (robots.txt respected; rule sentences first, a
   free model only when the rules cannot decide; every quote verbatim), in the order their kind of page has
   proven to pay, within this source's share of the reading budget.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

import httpx

from app.crawl.urlnorm import normalize_url, registered_domain
from app.discovery.case_studies import CaseStudiesProvider
from app.discovery.page_yield import page_kind
from app.evidence.judge import makes_product
from app.evidence.products import Product
from app.search import EVIDENCE, SearchError, SearchHub

MAX_HOSTS = 6  # maker hosts whose sitemaps are read
MAX_SITEMAP_FILES = 25  # sitemap files fetched per job, indexes included
MAX_CANDIDATES = 400  # pages handed to the reading loop, best first
LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)
# Child sitemaps whose name suggests stories or releases are read first ("sitemap-case-studies.xml").
STORY_SITEMAP = re.compile(r"case|stor|customer|success|press|news|release|blog|resource", re.I)
LOCALE = re.compile(r"^/(?:[a-z]{2}(?:[-_][a-z]{2})?)(?=/)", re.I)  # "/en/", "/de-de/", "/ja_jp/"

FetchXml = Callable[[str], Awaitable[str | None]]
Sitemaps = Callable[[str], Awaitable[list[str]]]


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def maker_site(site: str, product: Product) -> bool:
    """The domain is the product's maker: the proof reader's test ("oracle.com" makes Oracle NetSuite), or the
    domain's name is a word of one of the product's names ("ptc.com" for "PTC Windchill", "veeva.com" for "Veeva
    Vault")."""
    label = site.split(".")[0].lower()
    words = {w for n in product.names for w in re.findall(r"[a-z0-9]+", n.lower())}
    return makes_product(label, product) or (len(label) > 2 and label in words)


def names_product(url: str, product: Product) -> bool:
    """The page's address names the product ("...cummins-selects-ptcs-windchill..."); hyphens and case aside."""
    path = slug(urlsplit(url).path)
    return any(len(s) > 3 and s in path for s in (slug(n) for n in product.names))


def keep(url: str, product: Product) -> bool:
    """A customer story, or a news or release page about the product, judged from the address alone."""
    kind = page_kind(url)
    return kind == "story" or (kind in ("news", "article", "other") and names_product(url, product))


def page_key(url: str) -> str:
    """One key for a page and its copies in other languages: host plus path without a leading locale."""
    parts = urlsplit(url)
    return f"{parts.netloc.lower().removeprefix('www.')}{LOCALE.sub('', parts.path).rstrip('/').lower()}"


def choose(urls: list[str], product: Product, limit: int = MAX_CANDIDATES) -> list[str]:
    """Pages worth reading, best first: stories naming the product, other stories, then releases naming it.
    Within each, the shortest address of a page's language copies, in sitemap order."""
    best: dict[str, str] = {}
    for url in urls:
        if not keep(url, product):
            continue
        key = page_key(url)
        if key not in best or len(url) < len(best[key]):
            best[key] = url
    order = {u: i for i, u in enumerate(best.values())}

    def rank(u: str) -> tuple:
        story, named = page_kind(u) == "story", names_product(u, product)
        return (0 if story and named else 1 if story else 2, order[u])

    return sorted(best.values(), key=rank)[:limit]


class VendorArchiveProvider(CaseStudiesProvider):
    name = "vendor_archive"
    what = "the maker's customer stories and press releases"
    publisher = "vendor"
    open_ended = False  # its candidates are bounded (MAX_CANDIDATES), so it reads before the open-ended sources

    def __init__(self, client: httpx.AsyncClient | None = None, judge=None, searxng_url: str | None = None) -> None:
        super().__init__(client, judge, searxng_url)
        self.fetch_xml: FetchXml | None = None  # set by the crawler: a sitemap file's text, or None
        self.sitemaps_of: Sitemaps | None = None  # set by the crawler: sitemaps a host's robots.txt names
        self.hosts: list[str] = []
        self.files_read = 0

    async def _context(self, product: Product, d) -> list[str]:
        """The place written out, for the website lookup; this source makes no context searches."""
        from app.discovery.providers import COUNTRY_QIDS

        places = [COUNTRY_QIDS.get(c, ("", c))[1] for c in d.countries]
        self.place = places[0] if len(places) == 1 else ""
        return []

    async def maker_hosts(self, client: httpx.AsyncClient, product: Product) -> list[str]:
        """Hosts in search results for the product whose domain is the product's maker, most often seen first."""
        hub = self.hub = self.hub or SearchHub.from_settings(client, self.searxng_url)
        seen: dict[str, int] = {}
        names = [n for n in product.names if len(n) > 4][:2] or product.names[:1]
        for query in [f'"{n}"' for n in names] + [f'"{names[0]}" customer story']:
            try:
                hits = await hub.search(query, kind=EVIDENCE)
            except SearchError:
                continue
            for hit in hits:
                url = normalize_url(hit.url)
                site = registered_domain(url) if url else ""
                if site and maker_site(site, product):
                    host = urlsplit(url).netloc.lower()
                    seen[host] = seen.get(host, 0) + 1
                    seen.setdefault(f"www.{site}", 0)  # the maker's main site, even when search showed a subdomain
        return sorted(seen, key=lambda h: -seen[h])[:MAX_HOSTS]

    async def sitemap_pages(self, host: str) -> list[str]:
        """Page addresses a host's sitemaps list, story-like child sitemaps first, within the file budget."""
        if self.fetch_xml is None:
            return []
        origin = f"https://{host}"
        queue = (await self.sitemaps_of(origin) if self.sitemaps_of else []) or [f"{origin}/sitemap.xml"]
        pages: list[str] = []
        done: set[str] = set()
        while queue and self.files_read < MAX_SITEMAP_FILES:
            sm = queue.pop(0)
            if sm in done:
                continue
            done.add(sm)
            self.files_read += 1
            text = await self.fetch_xml(sm)
            if not text:
                continue
            locs = LOC.findall(text[:20_000_000])
            # A compressed sitemap (.xml.gz) is not read: the fetcher hands back text, not bytes.
            children = [u for u in locs if u.lower().split("?")[0].endswith(".xml")]
            pages += [u for u in locs if u not in children and not u.lower().split("?")[0].endswith(".gz")]
            queue += sorted(children, key=lambda u: not STORY_SITEMAP.search(u))
            queue.sort(key=lambda u: not STORY_SITEMAP.search(u))
        return pages

    async def search(self, client: httpx.AsyncClient, product: Product) -> list[str]:
        """Candidate pages: the maker's stories and product releases from its sitemaps (no search for pages)."""
        self.hosts = await self.maker_hosts(client, product)
        if not self.hosts:
            self.notes.append(f"{self.name}: no site of {product.name}'s maker came up in web search")
            return []
        found: list[str] = []
        for host in self.hosts:
            pages = await self.sitemap_pages(host)
            self._say("search", f"{host}: its sitemaps list {len(pages)} page(s)")
            found += pages
        urls = [u for u in (normalize_url(p) for p in choose(found, product)) if u]
        for url in urls:
            self.meta.setdefault(url, ("", ""))
            self.order.setdefault(url, len(self.order))
        self.notes.append(f"{self.name}: maker sites {', '.join(self.hosts)}; {self.files_read} sitemap file(s), "
                          f"{len(found)} page(s) listed, {len(urls)} kept as stories or product releases")
        return urls
