"""case_studies: organisations that a vendor's customer story, a partner's case study or a news article shows
using a technology.

Where a company never names its software itself (no SEC filing, nothing on its own site), the maker often does:
"Volkswagen standardised on Teamcenter" is on the vendor's customer stories, an implementation partner's case
studies and the trade press. Those pages are found by web search (the self-hosted SearXNG) for the product's
names next to "case study", "customer story" and "success story"; no list of vendors or sites is kept. Each page
is fetched like any crawled page (robots.txt respected), its sentences naming the product are cut out word for
word, and a sentence that says outright who uses it settles the page; otherwise one free model call says who
published it and which organisations it shows using the product (app.evidence.thirdparty). A page about a company
already known to be outside the countries asked for is not given to the model. Every customer the question can
deliver is then looked up for its website, which is crawled for contact details like any other result. Pages that
show nobody are kept as rejected proof with the reason.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections import Counter
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.config import get_settings
from app.crawl.urlnorm import normalize_url, registered_domain
from app.discovery.providers import NOT_COMPANY_SITES, DiscoveryError, DiscoveryResult
from app.discovery.relevance import CCTLD_TO_ISO
from app.discovery.websites import WebsiteFinder, names_company
from app.evidence.judge import Judge, score
from app.evidence.products import Product, product_for
from app.evidence.quotes import find_mentions, verify_quote
from app.evidence.thirdparty import PAGE_SENTENCES, RULE_STRENGTH, STRENGTH, countries_named, read_page
from app.extract.deterministic import PageDoc
from app.search import EVIDENCE, SearchError, SearchHub, search_configured
from app.spec.models import ExtractionSpec

PHRASES = ("case study", "customer story", "success story")
# Reading stops when new companies stop arriving, judged by their rate, not by one run of empty pages: at least
# MIN_READ pages are read, then reading goes on until no new company the question could deliver came in the last
# QUIET pages and at most MAX_IN_WINDOW in the last WINDOW, or the job's reading budget is spent. Measured
# (2026-10-30): new companies keep arriving at about 1 per 3-6 pages for 200+ pages, so "20 empty pages in a row"
# fired on a chance gap (Windchill US stopped at page 79 in one run; the same question went on to 228 pages and 21
# more companies in another).
MIN_READ = 30
QUIET = 40
WINDOW = 80
MAX_IN_WINDOW = 1


def finds_dried_up(read: int, finds: list[int]) -> bool:
    """Whether new companies have stopped arriving: `finds` are the page counts at which a new deliverable company
    came in, `read` the pages read so far."""
    if read < MIN_READ:
        return False
    recent = [f for f in finds if f > read - WINDOW]
    return read - (finds[-1] if finds else 0) >= QUIET and len(recent) <= MAX_IN_WINDOW
SEARCH_PAGES = 2  # result pages per query
HOST_FAILURES = 2  # pages of one site that could not be read before its other candidates are passed over
CCTLD = {iso: tld for tld, iso in CCTLD_TO_ISO.items()}  # "GB" -> "uk"
MAX_ADOPTION_QUERIES = 4
SOURCE_TYPES = {"vendor": "Vendor case study", "partner": "Partner case study", "customer": "Customer's own page",
                "news": "News article", "other": "Web page"}

FetchPage = Callable[[str], Awaitable[PageDoc | None]]

# Searches for the announcements an organisation in the place makes when it adopts the product, built from fixed
# templates filled from the question (never written by a model, so the same question asks the same searches every
# run: model-written ones gave 270 candidate pages one run and 406 the next, 2026-10-29). English, and the place's
# main business language where it is not: the maker's "case study" pages alone missed Cummins' and Raytheon's
# announcements and most UK customers (measured 2026-10-26).
ADOPTION = ('"{name}" {place} implemented', '"{name}" {place} "went live"', '"{name}" {place} selects',
            '"{name}" {place} customer')
# How an adoption is announced in a few major business languages: case study, customer story, "implements".
LOCAL_PHRASES = {
    "de": ("Fallstudie", "Kundenreferenz", "eingeführt"), "fr": ("étude de cas", "témoignage client", "déploie"),
    "es": ("caso de éxito", "caso de estudio", "implementa"), "it": ("caso di successo", "case history", "adotta"),
    "nl": ("klantcase", "klantverhaal", "implementeert"), "pt": ("caso de sucesso", "estudo de caso", "implementa"),
    "ja": ("導入事例", "事例", "導入"), "sv": ("kundcase", "kundberättelse", "inför"),
    "da": ("kundecase", "kundehistorie", "implementerer"), "pl": ("studium przypadku", "wdrożenie", "wdraża"),
}
LANGUAGE = {"DE": "de", "AT": "de", "CH": "de", "FR": "fr", "BE": "fr", "ES": "es", "MX": "es", "AR": "es",
            "CO": "es", "CL": "es", "IT": "it", "NL": "nl", "PT": "pt", "BR": "pt", "JP": "ja", "SE": "sv",
            "DK": "da", "PL": "pl"}


def adoption_queries(name: str, place: str, country: str = "") -> list[str]:
    """The fixed adoption searches for a product in one place (see ADOPTION and LOCAL_PHRASES)."""
    if not place:
        return []
    out = [t.format(name=name, place=place) for t in ADOPTION]
    out += [f'"{name}" {phrase}' for phrase in LOCAL_PHRASES.get(LANGUAGE.get(country, ""), ())]
    return out


def candidate_key(url: str) -> str:
    """One key for the copies of a page search returns under several addresses (spkaa.com, www.spkaa.com,
    www-stage.spkaa.com; tracking parameters): its site and path."""
    norm = normalize_url(url) or url
    path = norm.split("://", 1)[-1].split("/", 1)[1] if "/" in norm.split("://", 1)[-1] else ""
    return f"{registered_domain(norm)}/{path.split('?', 1)[0].split('#', 1)[0].rstrip('/').lower()}"


def page_date(doc: PageDoc) -> str:
    """The page's own publication date (YYYY-MM-DD) from its metadata, or "" when it gives none."""
    for key in ("article:published_time", "article:modified_time", "date", "dc.date"):
        m = re.match(r"\d{4}-\d{2}-\d{2}", doc.meta.get(key, ""))
        if m:
            return m.group()
    for item in doc.jsonld:
        for key in ("datePublished", "dateModified"):
            value = item.get(key)
            m = re.match(r"\d{4}-\d{2}-\d{2}", value if isinstance(value, str) else "")
            if m:
                return m.group()
    return ""


class CaseStudiesProvider:
    name = "case_studies"
    what = "case studies and customer stories"  # what the pages are, in notes and the live feed
    publisher = "other"  # who publishes this source's pages, when nothing on the page says otherwise
    # Its candidates are open-ended (web search gives hundreds): it reads until coverage or the budget stops it,
    # so it reads after the sources whose candidates are bounded and takes whatever time they leave.
    open_ended = True

    def __init__(self, client: httpx.AsyncClient | None = None, judge: Judge | None = None,
                 searxng_url: str | None = None) -> None:
        self.client = client
        self.judge = judge or Judge()
        self.searxng_url = (searxng_url if searxng_url is not None else get_settings().searxng_url).rstrip("/")
        self.hub: SearchHub | None = None  # made with the client, in search()
        self.notes: list[str] = []
        self.evidence: list[dict[str, Any]] = []
        self.facts: list[dict[str, Any]] = []  # what the website lookup established, for the final decision
        self.on_note: Callable[..., None] | None = None
        self.fetch_page: FetchPage | None = None  # set by the crawler: robots.txt respected, network rules checked
        self.dates: dict[str, str] = {}  # url -> date the search source gives, when the page itself gives none
        self.context: list[str] = []  # searches naming the question's industry and place, asked first
        self.place = ""  # the one place asked for, written out ("United Kingdom"), or ""
        self.meta: dict[str, tuple[str, str]] = {}  # url -> (title, snippet) search gave
        self.order: dict[str, int] = {}  # url -> when search first gave it
        self.resolver = None  # the job's EntityResolver (set by the crawler, so names are matched once per job)
        self.countries: list[str] = []  # the countries asked for (ISO), set in discover()
        # site -> product sentence -> pages of that site it was on, this job only: a sentence on several pages of
        # one site is its navigation (a sidebar of other case studies), not what any one page says.
        self.site_sentences: dict[str, dict[str, set[str]]] = {}
        self.deadline: float | None = None  # monotonic time the job's reading budget ends (set by the crawler)
        self.read = 0  # pages read
        self.unanswered: list[str] = []  # pages no free model answered, asked again at the end

    def _say(self, kind: str, message: str, url: str | None = None) -> None:
        if self.on_note is not None:
            self.on_note(kind, message, url, source=self.name)

    @staticmethod
    def queries(product: Product, place: str = "") -> list[str]:
        """The product's names next to the kinds of page that name customers. With a place, the first name's
        searches carry it, so most results are about the companies asked for, not everyone else's."""
        names = [n for n in product.names if len(n) > 4][:2] or product.names[:1]
        out = [f'"{n}" "{p}" {place}'.strip() if i == 0 else f'"{n}" "{p}"'
               for i, n in enumerate(names) for p in PHRASES]
        return list(dict.fromkeys(out))

    @staticmethod
    def context_queries(product: Product, industry: str, places: list[str], local: list[str]) -> list[str]:
        """The product with the question's own industry and place, so stories about the companies asked for come
        before stories about everyone else's; `local` adds searches in the place's own words."""
        name = ([n for n in product.names if len(n) > 4] or product.names)[0]
        out = []
        for place in places[:2] or [""]:
            if industry:
                out.append(f'"{name}" {industry} {place}'.strip())
                out.append(f'"{name}" {industry} {place} case study'.replace("  ", " ").strip())
            elif place:
                out.append(f'"{name}" {place} case study')
        out += [f'"{name}" {term}' for term in local]
        return list(dict.fromkeys(out))

    async def search(self, client: httpx.AsyncClient, product: Product) -> list[str]:
        hub = self.hub = self.hub or SearchHub.from_settings(client, self.searxng_url)
        urls: list[str] = []
        for query in list(dict.fromkeys([*self.context, *self.queries(product, self.place)])):
            for page in range(1, SEARCH_PAGES + 1):
                try:
                    hits = await hub.search(query, page=page, kind=EVIDENCE)
                except SearchError as exc:
                    if urls:
                        return urls
                    raise DiscoveryError(str(exc)) from None
                if not hits:
                    break
                for hit in hits:
                    url = normalize_url(hit.url)
                    site = registered_domain(url) if url else ""
                    if url and site and site not in NOT_COMPANY_SITES and url not in urls:
                        urls.append(url)
                        self.meta.setdefault(url, (hit.title or "", hit.snippet or ""))
                        self.order.setdefault(url, len(self.order))
                await asyncio.sleep(1.0 if get_settings().env != "test" and page < SEARCH_PAGES else 0)
        return urls

    def rank(self, url: str, product: Product, countries: list[str]) -> tuple:
        """A page's place in the reading order, from what search said about it: pages whose title, snippet or
        domain is about the place asked for first, then pages naming the product; within one score, the order
        search found them in (the place-specific searches are asked first, and each engine ranks its own
        results), which a job keeps fixed. Breaking ties by address instead read domains alphabetically and lost
        the engines' relevance (2026-10-29)."""
        title, snippet = self.meta.get(url, ("", ""))
        text = f"{title} {snippet}"
        score = product.mentioned_in(text)
        if countries:
            site = registered_domain(url) or ""
            tlds = {CCTLD.get(c, c.lower()) for c in countries}
            score += 2 * bool(countries_named(text) & set(countries) or site.rsplit(".", 1)[-1] in tlds)
        return (-score, self.order.get(url, len(self.order)))

    def _repeated(self, url: str, sentences: list[str]) -> set[str]:
        """The page's product sentences already seen on another page of the same site in this job, and records
        this page's."""
        seen = self.site_sentences.setdefault(registered_domain(url) or "", {})
        out = set()
        for sentence in sentences:
            key = " ".join(sentence.split()).casefold()
            pages = seen.setdefault(key, set())
            if pages - {url}:
                out.add(key)
            pages.add(url)
        return out

    def _elsewhere(self, company: str) -> str:
        """Why the question cannot deliver this company, when a fact already places it outside the countries
        asked for (a registry match, or a proof page saying where it is based); "" when unknown or inside."""
        if not self.countries:
            return ""
        key = company.casefold()
        for f in self.facts:
            if f["kind"] == "country" and f["value"] and f["company"].casefold() == key \
                    and f["value"] not in self.countries:
                return f"{company} is in {f['value']} ({f['by']}), not in {', '.join(self.countries)}"
        return ""

    def _page_elsewhere(self, url: str) -> str:
        """Why a page need not be given to the model: its title or address is about a company already known to be
        outside the countries asked for, or the page is on that company's own website. A page about a company
        whose country is unknown is read."""
        if not self.countries:
            return ""
        title = self.meta.get(url, ("", ""))[0]
        site = registered_domain(url) or ""
        about = f"{title} {url.split('://', 1)[-1].replace('-', ' ').replace('/', ' ')}"
        for company in {f["company"] for f in self.facts if f["kind"] == "country" and f["value"]}:
            why = self._elsewhere(company)
            if not why:
                continue
            own = any(f["kind"] == "website" and f["company"].casefold() == company.casefold() and f["value"]
                      and registered_domain(f["value"]) == site for f in self.facts)
            if own or names_company(about, company):
                return why
        return ""

    async def _could_deliver(self, client: httpx.AsyncClient, row: dict[str, Any], d) -> bool:
        """Whether a newly named company could be delivered: not when the evidence puts it outside the countries
        asked for (a UK question once spent its reading on US and Australian companies a page happened to name).
        Where it is comes from what the proof page itself
        said, else from a registry, matched once per job; unknown counts as deliverable."""
        if not d.countries:
            return True
        said = next((f["value"] for f in self.facts if f["kind"] == "country" and f["company"] == row["company"]
                     and f["value"]), "")
        if said:
            return said in d.countries
        from app.discovery.entities import EntityResolver, resolution_facts

        self.resolver = self.resolver or EntityResolver(client)
        res = await self.resolver.resolve(row["company"])
        self.facts += resolution_facts(row["company"], "", res)
        if res.country and res.country not in d.countries:
            self._say("skipped", f"{row['company']} is not counted: {res.by} places it in {res.country}")
            return False
        return True

    def _record(self, **kw: Any) -> dict[str, Any]:
        self.evidence.append(kw)
        if kw["kept"]:
            self._say("kept", f"Proof: {kw['source_type'].lower()} shows {kw['company']} "
                              f"{kw['relationship'].replace('_', ' ')} {kw['product']} ({kw['verdict']}): "
                              f"\"{kw['quote'][:160]}\"", kw["url"])
        else:
            self._say("dropped", f"Rejected {kw['url']}: {kw['reason']}", kw["url"])
        return kw

    async def discover(self, spec: ExtractionSpec) -> list[DiscoveryResult]:
        d = spec.discovery
        if not d.technology:
            raise DiscoveryError(f"{self.what} are searched for a technology")
        if not search_configured(self.searxng_url):
            raise DiscoveryError(f"{self.what} need web search (to find each customer's website); none is "
                                 "configured, skipped")
        if self.fetch_page is None:
            raise DiscoveryError(f"{self.what} are read by the crawler; skipped outside a crawl")
        product = product_for(d.technology, d.technology_aliases)
        self.countries = list(d.countries)
        client = self.client or httpx.AsyncClient(timeout=30, headers={"User-Agent": get_settings().user_agent})
        users: dict[str, dict[str, Any]] = {}
        elsewhere = 0
        try:
            self.context = await self._context(product, d)
            urls = await self.search(client, product)
            self.hub = self.hub or SearchHub.from_settings(client, self.searxng_url)
            self._say("search", f"{len(urls)} page(s) found among {product.name} {self.what}; reading until new "
                                f"companies stop arriving (none in {QUIET} pages; at least {MIN_READ} pages)")
            pending = list(dict.fromkeys(urls))
            stop = await self._read_loop(client, product, d, pending, users)
            self.notes.append(f"{self.name}: {len(urls)} candidate page(s); {self.read} read; stopped: {stop}")
            finder = WebsiteFinder(client, self.searxng_url, self._text, hub=self.hub)
            results: list[DiscoveryResult] = []
            seen: set[str] = set()
            deliverable = []
            for ev in sorted(users.values(), key=lambda e: -e["strength"]):
                why = self._elsewhere(ev["company"])
                if why:
                    # Its proof stays on the Evidence sheet; its website is not looked up nor its site crawled.
                    elsewhere += 1
                    self._say("skipped", f"Not looking up {ev['company']}'s website: {why}")
                    continue
                deliverable.append(ev)
            for ev in deliverable[:d.max_results]:
                site, how = await finder.find(ev["company"], context=self.place, unverified_ok=True)
                ev["website"] = site
                self._say("search" if site else "skipped", f"Website of {ev['company']}: "
                          + (f"{site} ({how})" if site else f"none taken ({how})"), site or None)
                self.facts.append({"site": registered_domain(site) if site else "", "company": ev["company"],
                                   "kind": "website", "value": site, "by": "web search", "detail": how,
                                   "source_url": ev["url"], "quote": ""})
                domain = registered_domain(site) if site else ""
                if not domain or domain in seen:
                    continue
                seen.add(domain)
                hint = {"company_name": ev["company"], "website_url": site, "uses_technology": ev["verdict"],
                        "evidence": ev["quote"], "evidence_url": ev["url"], "evidence_date": ev["evidence_date"],
                        "evidence_type": ev["source_type"], "_source": ev["url"], "_strength": ev["strength"]}
                results.append(DiscoveryResult(site, self.name, {k: v for k, v in hint.items() if v},
                                               referrer=ev["url"]))
        finally:
            await self.judge.aclose()
            if self.client is None:
                await client.aclose()
        for backend, why in (self.hub.problems if self.hub else {}).items():
            self.notes.append(f"{self.name}: search backend {backend} was switched off ({why})")
        if elsewhere:
            self.notes.append(f"{self.name}: {elsewhere} customer(s) with proof are outside the countries asked "
                              "for; their websites were not looked up")
        missing = len(users) - elsewhere - len(results)
        if missing > 0:
            self.notes.append(f"{self.name}: {missing} customer(s) with proof have no confirmed website; they "
                              "are on the Evidence sheet only")
        if not results:
            raise DiscoveryError(f"none of the {self.what} showed an organisation using {product.name}")
        return results

    def _over_budget(self) -> bool:
        return self.deadline is not None and time.monotonic() > self.deadline

    async def _read_one(self, url: str, product: Product, step: str = "proof_read") -> tuple[list[Any], bool]:
        """Read one candidate page: (proof rows kept from it, whether the page could be fetched)."""
        base = dict(company=registered_domain(url), product=product.name, url=url, evidence_date="",
                    source_type="Web page", website="", quote="", relationship="", judged_by="",
                    strength=0.0, verdict="")
        self._say("read", f"Reading {url}", url)
        doc = await self.fetch_page(url)
        if doc is None:
            self._record(**base, kept=False, reason="page could not be read (robots.txt, error or no text)")
            return [], False
        self.read += 1
        text = f"{doc.title} {doc.text}"
        sentences = [q for q in find_mentions(doc.text, product, limit=PAGE_SENTENCES) if verify_quote(q, doc.text)]
        boilerplate = self._repeated(url, sentences)
        if not sentences:
            self._record(**base, kept=False, reason="the product's name is not on the page")
            return [], True
        found, why = await read_page(self.judge, product, doc.title, sentences, text, url,
                                     skip_model=self._page_elsewhere(url), step=step,
                                     default_publisher=self.publisher, boilerplate=boilerplate)
        day = page_date(doc) or self.dates.get(url, "")
        if not found:
            if why.startswith("not read: no free model") and url not in self.unanswered:
                self.unanswered.append(url)  # no model answered: the page is asked again later, not judged
                self.read -= 1
                return [], True
            self._record(**{**base, "evidence_date": day, "quote": sentences[0]}, kept=False, reason=why)
            return [], True
        kept_rows = []
        for f in found:
            # First-hand pages (the maker's case study, the company's own page) keep the proof's strength, so a
            # recent one is Confirmed; on any other page a use is at most Likely: a rule sentence there counts as
            # Likely, and one model reading as well. Two model readings that agree keep its strength; readings that
            # disagree leave a mention, kept and visible, never a use.
            relationship = "unreviewed" if f.agreement == "disagree" else f.relationship
            first_hand = f.publisher in ("vendor", "customer")
            # One fact, one weight, whoever read it: a rule sentence and a sure model reading of the same kind of
            # page count the same. A model's single reading of a generic page once counted 0.3 (Mentioned) where a
            # rule sentence on it counted Likely (12 companies held back that way, 2026-10-30).
            weight = STRENGTH[f.publisher] if first_hand else max(STRENGTH[f.publisher], RULE_STRENGTH)
            if f.agreement == "rules":
                verdict, strength = score(relationship, weight, day)
                judged = f.judged_by
            else:
                verdict, strength = score(relationship, weight, day,
                                          one_reading=f.agreement == "single" and not first_hand)
                second = "agrees" if f.agreement == "agree" else "disagrees"
                judged = f.judged_by + (f"; second reading {f.second_by} {second}" if f.second_by
                                        else "; one reading")
            row = {**base, "company": f.customer, "evidence_date": day, "quote": f.quote,
                   "source_type": SOURCE_TYPES[f.publisher], "relationship": f.relationship,
                   "judged_by": judged[:120], "strength": strength, "verdict": verdict}
            if not verdict:
                self._record(**row, kept=False, reason=f.relationship.replace("_", " "))
                continue
            note = {"agree": "two readings agree", "single": "one reading", "disagree": "readings disagree",
                    "rules": "a sentence on it says so"}
            kept_rows.append(self._record(**row, kept=True,
                                          reason=f"named by a {f.publisher} page; {note[f.agreement]}"))
            if f.country:
                self.facts.append({"site": "", "company": f.customer, "kind": "country", "value": f.country,
                                   "by": f"proof: {SOURCE_TYPES[f.publisher].lower()}",
                                   "detail": f"the page says so: \"{f.country_quote[:200]}\"",
                                   "source_url": url, "quote": f.country_quote})
        return kept_rows, True

    async def _read_loop(self, client: httpx.AsyncClient, product: Product, d, pending: list[str],
                         users: dict[str, dict[str, Any]]) -> str:
        """Read candidates best first; reading stops when new companies the question could deliver stop arriving
        (finds_dried_up), or at the reading budget. Returns why it stopped. Pages left unread are listed on the
        Rejected sheet with that reason."""
        failures: Counter = Counter()
        seen_keys: set[str] = set()
        finds: list[int] = []  # pages read when a new deliverable company came in
        stop = "every candidate page was read"
        while pending:
            if self._over_budget():
                stop = "the reading budget was reached"
                break
            if finds_dried_up(self.read, finds):
                stop = (f"coverage: no new company that could be delivered in the last {QUIET} pages read, and at most "
                        f"{MAX_IN_WINDOW} in the last {WINDOW}")
                break
            if self.judge.unavailable:
                stop = f"no model to read pages ({self.judge.unavailable})"
                self.notes.append(f"{self.name}: stopped reading pages ({self.judge.unavailable})")
                break
            pending.sort(key=lambda u: self.rank(u, product, d.countries))
            url = pending.pop(0)
            key, host = candidate_key(url), registered_domain(url) or ""
            if key in seen_keys:
                continue  # another address of a page already taken
            seen_keys.add(key)
            if failures[host] >= HOST_FAILURES:
                self._unread(url, product, f"not read: {host} refused or gave no text {HOST_FAILURES} times")
                continue
            kept_rows, fetched = await self._read_one(url, product)
            if not fetched:
                failures[host] += 1
                continue
            new = [r for r in kept_rows if r["company"].casefold() not in users]
            for row in kept_rows:
                k = row["company"].casefold()
                if k not in users or row["strength"] > users[k]["strength"]:
                    users[k] = row
            deliverable = [r for r in new if await self._could_deliver(client, r, d)]
            # Coverage is measured on companies the question could deliver: a company elsewhere does not answer it.
            if deliverable:
                finds.append(self.read)
        # Pages no free model answered are asked once more, now that the busy moment has likely passed.
        retry, self.unanswered = self.unanswered, []
        for url in retry:
            if self._over_budget() or self.judge.unavailable:
                pending.append(url)
                continue
            kept_rows, _fetched = await self._read_one(url, product, step="reask")
            for row in kept_rows:
                k = row["company"].casefold()
                if k not in users or row["strength"] > users[k]["strength"]:
                    users[k] = row
        for url in self.unanswered:  # still no answer: kept visible with that reason
            self._unread(url, product, "not read: no free model answered, twice")
        for url in pending:
            self._unread(url, product, f"not read: {stop}")
        if pending:
            self.notes.append(f"{self.name}: {len(pending)} candidate page(s) not read ({stop}; listed on the "
                              "Rejected sheet)")
        return stop

    def _unread(self, url: str, product: Product, why: str) -> None:
        self.evidence.append(dict(company=registered_domain(url) or "", product=product.name, url=url,
                                  evidence_date="", source_type="Web page", website="", quote="", relationship="",
                                  judged_by="", strength=0.0, verdict="", kept=False, reason=why))

    async def _context(self, product: Product, d) -> list[str]:
        from app.discovery.providers import COUNTRY_QIDS

        # Each country's standard name from the country table ("United Kingdom"), not whichever spelling the
        # question parser last lists for it ("Britain" was searched for GB, a weak term).
        places = [COUNTRY_QIDS.get(c, ("", c))[1] for c in d.countries]
        industry = (d.industry or "").strip()
        self.place = places[0] if len(places) == 1 else ""
        name = ([n for n in product.names if len(n) > 4] or product.names)[0]
        adoption = adoption_queries(name, self.place, d.countries[0] if len(d.countries) == 1 else "")
        queries = list(dict.fromkeys([*self.context_queries(product, industry, places, []), *adoption]))
        self.notes.append(f"{self.name}: searches: " + " | ".join([*queries, *self.queries(product, self.place)]))
        return queries

    async def _text(self, url: str) -> str | None:
        doc = await self.fetch_page(url) if self.fetch_page else None
        return f"{doc.title} {doc.text}" if doc else None
