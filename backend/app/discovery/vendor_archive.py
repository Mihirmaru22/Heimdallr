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

from app.crawl.urlnorm import normalize_url, public_suffix, registered_domain
from app.discovery.case_studies import CaseStudiesProvider
from app.discovery.page_yield import page_kind
from app.evidence.judge import makes_product
from app.evidence.products import Product
from app.search import EVIDENCE, SearchError, SearchHub

MAX_HOSTS = 6  # maker hosts whose sitemaps are read
MAX_SITEMAP_FILES = 25  # sitemap files fetched per job, indexes included
MAX_CANDIDATES = 400  # pages handed to the reading loop, best first
SITE_SEARCH_PAGES = 3  # result pages of the one site search per maker host
SEARCHED_KINDS = ("story", "news", "article", "other")  # not product, service or job pages
# Some sitemaps wrap each address in CDATA (<loc><![CDATA[https://...]]></loc>; Veeva's do): read through it.
LOC = re.compile(r"<loc>\s*(?:<!\[CDATA\[)?\s*([^<\s\]]+)\s*(?:\]\]>)?\s*</loc>", re.I)
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


def country_tld(iso: str) -> str:
    """The country-code domain ending for an ISO country: "uk" for GB, else the code itself."""
    return "uk" if iso.upper() == "GB" else iso.lower()


def host_country(host: str) -> str:
    """The two-letter country ending of a host ("uk" for www.netsuite.co.uk, "cn" for www.netsuite.cn), "" for a
    generic one (.com, .org)."""
    last = public_suffix(host).rsplit(".", 1)[-1]
    return last if len(last) == 2 else ""


def for_countries(hosts: list[str], countries: list[str]) -> list[str]:
    """Maker hosts for the countries asked, in order: the maker's site for an asked country first; its site for
    another country is dropped when the maker also has a generic or asked-country one (a UK question once read
    www.netsuite.cn and never reached www.netsuite.co.uk's sitemap, 2026-11-26); a bare host is dropped when its
    www. twin is there (one site, one sitemap)."""
    wanted = {country_tld(c) for c in countries}

    def brand(h: str) -> str:
        return (registered_domain(h) or h).split(".")[0]

    home = {brand(h) for h in hosts if not host_country(h) or host_country(h) in wanted}
    out = [h for h in hosts if f"www.{h}" not in hosts
           and not (wanted and host_country(h) and host_country(h) not in wanted and brand(h) in home)]
    return sorted(out, key=lambda h: host_country(h) not in wanted) if wanted else out


def names_product(url: str, product: Product) -> bool:
    """The page's address names the product ("...cummins-selects-ptcs-windchill..."); hyphens and case aside."""
    path = slug(urlsplit(url).path)
    return any(len(s) > 3 and s in path for s in (slug(n) for n in product.names))


def product_site(url: str, product: Product) -> bool:
    """The site is named after the product itself ("netsuite.co.uk" for Oracle NetSuite), not just its maker
    ("oracle.com", "ptc.com"): everything it publishes is about that product."""
    label = (registered_domain(url) or "").split(".")[0]
    return len(label) > 3 and label in {slug(n) for n in product.names}


def release(url: str, product: Product) -> bool:
    """A news or release page about the product: its address names it, or it is in the newsroom of a site named
    after the product. netsuite.co.uk's releases say "NS" or nothing ("oliver-bonas-sees-ns-as-the-perfect-fit",
    "daring-foods-takes-on-the-meat-industry"), so an address test alone dropped two UK customers (2026-11-27)."""
    kind = page_kind(url)
    return (kind in ("news", "article", "other") and names_product(url, product)) \
        or (kind == "news" and product_site(url, product))


def keep(url: str, product: Product) -> bool:
    """A customer story, or a news or release page about the product, judged from the address alone."""
    return page_kind(url) == "story" or release(url, product)


def page_key(url: str) -> str:
    """One key for a page and its copies in other languages: host plus path without a leading locale."""
    parts = urlsplit(url)
    return f"{parts.netloc.lower().removeprefix('www.')}{LOCALE.sub('', parts.path).rstrip('/').lower()}"


def choose(urls: list[str], product: Product, limit: int = MAX_CANDIDATES,
           searched: list[str] | tuple[str, ...] = ()) -> list[str]:
    """Pages worth reading, best first: pages a site search shows naming the product, stories whose address names
    it, releases about it (see `release`), then the other stories (mostly about the maker's other products). Within each, the
    shortest address of a page's language copies, in search or sitemap order."""
    best: dict[str, str] = {}
    hit = {page_key(u) for u in searched}
    for url in [*searched, *urls]:
        key = page_key(url)
        if key not in hit and not keep(url, product):
            continue
        if key not in best or len(url) < len(best[key]):
            best[key] = url
    order = {u: i for i, u in enumerate(best.values())}

    def rank(u: str) -> tuple:
        story, named = page_kind(u) == "story", names_product(u, product)
        tier = 0 if page_key(u) in hit else 1 if story and named else 2 if named or release(u, product) else 3
        return (tier, order[u])

    return sorted(best.values(), key=rank)[:limit]


class VendorArchiveProvider(CaseStudiesProvider):
    name = "vendor_archive"
    what = "the maker's customer stories and press releases"
    publisher = "vendor"
    open_ended = False  # its candidates are bounded (MAX_CANDIDATES), so it reads before the open-ended sources
    # At most a third of the reading time: a maker's site holds hundreds of stories about its other products, and
    # reading them once left the third-party pages that found SRAM, EnerSys and Lick unread (2026-11-25).
    max_share = 1 / 3

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
        return for_countries(sorted(seen, key=lambda h: -seen[h]), self.countries)[:MAX_HOSTS]

    async def sitemap_pages(self, host: str, budget: int = MAX_SITEMAP_FILES) -> list[str]:
        """Page addresses a host's sitemaps list, story-like child sitemaps first, within this host's file budget.
        Child sitemaps for another country's locale ("/ae/sitemap-wcs.xml" on a UK question) come last: oracle.com's
        regional sitemaps once used up every file before netsuite.co.uk's was read (2026-11-26)."""
        if self.fetch_xml is None:
            return []
        wanted = {country_tld(c) for c in self.countries} | {"en"}

        def later(u: str) -> tuple[bool, bool]:
            m = LOCALE.match(urlsplit(u).path)
            elsewhere = bool(self.countries and m and m.group(0)[1:3].lower() not in wanted)
            return elsewhere, not STORY_SITEMAP.search(u)

        origin = f"https://{host}"
        queue = (await self.sitemaps_of(origin) if self.sitemaps_of else []) or [f"{origin}/sitemap.xml"]
        pages: list[str] = []
        done: set[str] = set()
        read = 0
        while queue and read < budget:
            sm = queue.pop(0)
            if sm in done:
                continue
            done.add(sm)
            self.files_read += 1
            read += 1
            text = await self.fetch_xml(sm)
            if not text:
                continue
            locs = LOC.findall(text[:20_000_000])
            # A compressed sitemap (.xml.gz) is not read: the fetcher hands back text, not bytes.
            children = [u for u in locs if u.lower().split("?")[0].endswith(".xml")]
            pages += [u for u in locs if u not in children and not u.lower().split("?")[0].endswith(".gz")]
            queue += children
            queue.sort(key=later)
        return pages

    async def site_pages(self, host: str, product: Product) -> list[str]:
        """Pages of a maker host that web search shows naming the product (`site:host "name"`). The sitemap lists
        every page the maker published, mostly about its other products: of 331 PTC pages read once, 240 never
        named Windchill (2026-11-25). Search engines index the text, so they know which pages name it."""
        if self.hub is None:
            return []
        names = sorted((n for n in product.names if len(n) > 4), key=len) or product.names
        query = f'site:{host} "{names[0]}"'
        out: list[str] = []
        for page in range(1, SITE_SEARCH_PAGES + 1):
            try:
                hits = await self.hub.search(query, page=page, kind=EVIDENCE)
            except SearchError:
                break
            new = 0
            for h in hits:
                url = normalize_url(h.url)
                if url and urlsplit(url).netloc.lower() == host and url not in out \
                        and page_kind(url, h.title) in SEARCHED_KINDS:
                    out.append(url)
                    new += 1
            if not new:
                break
        return out

    async def search(self, client: httpx.AsyncClient, product: Product) -> list[str]:
        """Candidate pages: the maker's stories and product releases from its sitemaps (no search for pages)."""
        self.hosts = await self.maker_hosts(client, product)
        if not self.hosts:
            self.notes.append(f"{self.name}: no site of {product.name}'s maker came up in web search")
            return []
        found: list[str] = []
        searched: list[str] = []
        budget = max(4, MAX_SITEMAP_FILES // len(self.hosts))  # each maker host gets its share of sitemap files
        for host in self.hosts:
            pages = await self.sitemap_pages(host, budget)
            named = await self.site_pages(host, product)
            self._say("search", f"{host}: its sitemaps list {len(pages)} page(s); a site search shows "
                                f"{len(named)} naming {product.name}")
            found += pages
            searched += named
        urls = [u for u in (normalize_url(p) for p in choose(found, product, searched=searched)) if u]
        for url in urls:
            self.meta.setdefault(url, ("", ""))
            self.order.setdefault(url, len(self.order))
        self.notes.append(f"{self.name}: maker sites {', '.join(self.hosts)}; {self.files_read} sitemap file(s), "
                          f"{len(found)} page(s) listed, {len(searched)} named the product in a site search, "
                          f"{len(urls)} kept as stories or product releases")
        return urls
