"""Discovery providers: where the first URLs of a job come from.

- seeds: URLs and domains the user typed (always available).
- wikidata: organizations from Wikidata (CC0) with an official website (P856), filtered by
  industry (P452) and country (P17). Free, no key. The search index (haswbstatement) answers in about a
  second; the SPARQL query service is only a fallback because it often times out under load.
- searxng: a self-hosted SearXNG metasearch instance (WEBDATA_SEARXNG_URL). Search results are
  reduced to company homepages; directories, social networks and news sites are dropped.
Each result is a URL plus optional hints (name, headquarters...) that become candidate values
with method "wikidata", so the record shows where they came from.
"""

from __future__ import annotations

import asyncio
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.config import get_settings
from app.crawl.urlnorm import normalize_url, registered_domain
from app.search import SearchError, SearchHub
from app.spec.models import ExtractionSpec

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
CONTINENTS = {"europe": "Q46", "north_america": "Q49", "asia": "Q48", "africa": "Q15", "south_america": "Q18",
              "oceania": "Q55643"}
# Wikidata items for the countries the request parser knows, plus the larger economies of each continent,
# so a region becomes a list of countries without asking the (often overloaded) query service.
COUNTRY_QIDS = {
    "GB": ("Q145", "United Kingdom"), "DE": ("Q183", "Germany"), "FR": ("Q142", "France"), "ES": ("Q29", "Spain"),
    "IT": ("Q38", "Italy"), "NL": ("Q55", "Netherlands"), "BE": ("Q31", "Belgium"), "SE": ("Q34", "Sweden"),
    "NO": ("Q20", "Norway"), "DK": ("Q35", "Denmark"), "FI": ("Q33", "Finland"), "PL": ("Q36", "Poland"),
    "IE": ("Q27", "Ireland"), "CH": ("Q39", "Switzerland"), "AT": ("Q40", "Austria"), "PT": ("Q45", "Portugal"),
    "EE": ("Q191", "Estonia"), "LU": ("Q32", "Luxembourg"), "CZ": ("Q213", "Czech Republic"),
    "HU": ("Q28", "Hungary"), "GR": ("Q41", "Greece"), "RO": ("Q218", "Romania"), "IL": ("Q801", "Israel"),
    "US": ("Q30", "United States"), "CA": ("Q16", "Canada"), "MX": ("Q96", "Mexico"), "IN": ("Q668", "India"),
    "JP": ("Q17", "Japan"), "CN": ("Q148", "China"), "KR": ("Q884", "South Korea"), "TW": ("Q865", "Taiwan"),
    "SG": ("Q334", "Singapore"), "HK": ("Q8646", "Hong Kong"), "AE": ("Q878", "United Arab Emirates"),
    "ID": ("Q252", "Indonesia"), "MY": ("Q833", "Malaysia"), "TH": ("Q869", "Thailand"), "VN": ("Q881", "Vietnam"),
    "PH": ("Q928", "Philippines"), "BR": ("Q155", "Brazil"), "AR": ("Q414", "Argentina"), "CL": ("Q298", "Chile"),
    "CO": ("Q739", "Colombia"), "PE": ("Q419", "Peru"), "ZA": ("Q258", "South Africa"), "NG": ("Q1033", "Nigeria"),
    "EG": ("Q79", "Egypt"), "KE": ("Q114", "Kenya"), "MA": ("Q1028", "Morocco"), "AU": ("Q408", "Australia"),
    "NZ": ("Q664", "New Zealand"),
}
REGION_COUNTRIES = {
    "europe": ["GB", "DE", "FR", "ES", "IT", "NL", "BE", "SE", "NO", "DK", "FI", "PL", "IE", "CH", "AT", "PT", "EE",
               "LU", "CZ", "HU", "GR", "RO"],
    "north_america": ["US", "CA", "MX"],
    "asia": ["IN", "JP", "CN", "KR", "TW", "SG", "HK", "AE", "IL", "ID", "MY", "TH", "VN", "PH"],
    "africa": ["ZA", "NG", "EG", "KE", "MA"],
    "south_america": ["BR", "AR", "CL", "CO", "PE"],
    "oceania": ["AU", "NZ"],
}
# business, enterprise, company, public company, organization: used when no industry narrows the search.
ORG_CLASSES = ["Q4830453", "Q6881511", "Q783794", "Q891723", "Q43229"]
ISO2_RE = re.compile(r"^[A-Z]{2}$")
QID_RE = re.compile(r"^Q\d{1,12}$")


@dataclass
class DiscoveryResult:
    url: str
    method: str
    hint: dict[str, Any] = field(default_factory=dict)
    referrer: str | None = None


class DiscoveryError(Exception):
    pass


class DiscoveryProvider(Protocol):
    name: str

    async def discover(self, spec: ExtractionSpec) -> list[DiscoveryResult]: ...


class SeedProvider:
    name = "seeds"

    async def discover(self, spec: ExtractionSpec) -> list[DiscoveryResult]:
        out: list[DiscoveryResult] = []
        for raw in spec.crawl.start_urls + [f"https://{d}/" for d in spec.crawl.allowed_domains]:
            url = normalize_url(raw if "://" in raw else f"https://{raw}")
            if url and all(r.url != url for r in out):
                out.append(DiscoveryResult(url, "seed"))
        return out


def wd_founded(entity: dict[str, Any]) -> str | None:
    """The year of the item's inception (P571), e.g. "1916"; None when Wikidata has none."""
    inception = next((c.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("time", "")
                      for c in entity.get("claims", {}).get("P571", []) if c.get("rank") != "deprecated"), "")
    m = re.match(r"^\+(\d{4})-", inception or "")
    return m.group(1) if m else None


def wd_label(entity: dict[str, Any]) -> str | None:
    """English label, else the language-neutral ("mul") label Wikidata uses for many company names."""
    labels = entity.get("labels", {})
    label = (labels.get("en") or labels.get("mul") or {}).get("value") or ""
    # "Tango Therapeutics (United States)": a disambiguation note, not part of the name.
    return re.sub(r"\s*\([^()]*\)$", "", label).strip() or None


class WikidataProvider:
    name = "wikidata"
    # The public query service stops any query at 60 s, so waiting longer than that is pointless.
    SPARQL_TIMEOUT = httpx.Timeout(65.0, connect=10.0)

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self.client = client

    def _client(self) -> httpx.AsyncClient:
        return self.client or httpx.AsyncClient(
            timeout=30, headers={"User-Agent": get_settings().user_agent}, follow_redirects=False
        )

    async def _search(self, client: httpx.AsyncClient, text: str) -> list[dict[str, Any]]:
        resp = await client.get(WIKIDATA_API, params={
            "action": "wbsearchentities", "search": text[:100], "language": "en", "type": "item",
            "limit": 7, "format": "json",
        })
        resp.raise_for_status()
        return [r for r in resp.json().get("search", []) if QID_RE.match(r.get("id", ""))]

    async def industry_ids(self, client: httpx.AsyncClient, industry: str) -> list[str]:
        """Items companies use as their industry (P452). "pharmaceutical" on its own finds the drug
        ("medication"), not the sector, so "<x> industry" is searched first and preferred."""
        term = industry.strip().lower()
        hits = await self._search(client, term if term.endswith("industry") else f"{term} industry")
        hits += await self._search(client, term)

        def score(hit: dict[str, Any]) -> int:
            text = f"{hit.get('label', '')} {hit.get('description', '')}".lower()
            return 2 * ("industry" in text) + ("sector" in text or "business" in text or "economic" in text)

        ranked = sorted(dict((h["id"], h) for h in hits).values(), key=score, reverse=True)
        return [h["id"] for h in ranked if score(h) > 0][:4] or [h["id"] for h in ranked][:2]

    @staticmethod
    def build_query(industry_ids: list[str], countries: list[str], region: str | None, limit: int,
                    lean: bool = False) -> str:
        """`lean` drops the headquarters lookup and the dissolved filter, for a retry after a timeout."""
        lines = ["SELECT DISTINCT ?org ?orgLabel ?website ?hqLabel ?countryLabel WHERE {"]
        if industry_ids:
            values = " ".join(f"wd:{q}" for q in industry_ids if QID_RE.match(q))
            lines.append(f"  VALUES ?industry {{ {values} }}")
            lines.append("  ?org wdt:P452 ?industry .")
        lines.append("  ?org wdt:P856 ?website .")
        lines.append("  ?org wdt:P17 ?country .")
        isos = [c for c in countries if ISO2_RE.match(c)]
        if isos:
            lines.append("  ?country wdt:P297 ?iso .")
            lines.append("  VALUES ?iso { " + " ".join(f'"{c}"' for c in isos) + " }")
        elif region in CONTINENTS:
            lines.append(f"  ?country wdt:P30 wd:{CONTINENTS[region]} .")
        if not lean:
            lines.append("  OPTIONAL { ?org wdt:P159 ?hq . }")
            lines.append("  FILTER NOT EXISTS { ?org wdt:P576 ?dissolved . }")
        lines.append('  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }')
        lines.append(f"}} LIMIT {int(limit)}")
        return "\n".join(lines)

    async def _sparql(self, client: httpx.AsyncClient, query: str) -> list[dict[str, Any]]:
        resp = await client.post(WIKIDATA_SPARQL, data={"query": query},
                                 headers={"Accept": "application/sparql-results+json"}, timeout=self.SPARQL_TIMEOUT)
        if resp.status_code == 429:
            raise DiscoveryError("Wikidata rate limit reached; try again in a minute")
        resp.raise_for_status()
        return resp.json()["results"]["bindings"]

    @staticmethod
    def search_query(industry_ids: list[str], countries: list[str], region: str | None) -> str:
        """A CirrusSearch query: items with one of the industries, in one of the countries."""
        parts = []
        inds = [q for q in industry_ids if QID_RE.match(q)]
        parts.append("haswbstatement:" + "|".join(f"P452={q}" for q in inds) if inds
                     else "haswbstatement:" + "|".join(f"P31={q}" for q in ORG_CLASSES))
        isos = [c for c in countries if c in COUNTRY_QIDS] or REGION_COUNTRIES.get(region or "", [])
        while isos:
            # Wikidata rejects search queries over 300 characters; the country lists are largest economy first.
            query = " ".join([*parts, "haswbstatement:" + "|".join(f"P17={COUNTRY_QIDS[c][0]}" for c in isos)])
            if len(query) <= 290:
                return query
            isos = isos[:-1]
        return " ".join(parts)

    @staticmethod
    def _claim_ids(entity: dict[str, Any], prop: str) -> list[str]:
        out = []
        for claim in entity.get("claims", {}).get(prop, []):
            if claim.get("rank") == "deprecated":
                continue
            value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
            if isinstance(value, dict) and QID_RE.match(str(value.get("id", ""))):
                out.append(value["id"])
            elif isinstance(value, str):
                out.append(value)
        return out

    async def _entities(self, client: httpx.AsyncClient, ids: list[str], props: str) -> dict[str, Any]:
        found: dict[str, Any] = {}
        for i in range(0, len(ids), 50):
            resp = await client.get(WIKIDATA_API, params={
                "action": "wbgetentities", "ids": "|".join(ids[i:i + 50]), "props": props, "languages": "en|mul",
                "format": "json"})
            resp.raise_for_status()
            found.update(resp.json().get("entities", {}))
        return found

    async def _via_search(
        self, client: httpx.AsyncClient, ids: list[str], spec: ExtractionSpec
    ) -> list[DiscoveryResult]:
        d = spec.discovery
        query = self.search_query(ids, d.countries, d.region)
        out: list[DiscoveryResult] = []
        seen: set[str] = set()
        country_names = {qid: name for qid, name in COUNTRY_QIDS.values()}
        for page in range(3):
            params = {"action": "query", "list": "search", "srsearch": query, "srnamespace": 0, "srlimit": 200,
                      "sroffset": page * 200, "srprop": "", "srsort": "incoming_links_desc", "format": "json"}
            resp = await client.get(WIKIDATA_API, params=params)
            resp.raise_for_status()
            body = resp.json()
            if "error" in body:  # most-linked-first ordering is a nicety; retry with plain relevance
                params.pop("srsort")
                resp = await client.get(WIKIDATA_API, params=params)
                resp.raise_for_status()
                body = resp.json()
            if "error" in body:
                raise DiscoveryError(f"Wikidata search rejected the query: {body['error'].get('code', 'error')}")
            hits = [h["title"] for h in body.get("query", {}).get("search", []) if QID_RE.match(h.get("title", ""))]
            if not hits:
                break
            entities = await self._entities(client, hits, "labels|claims")
            wanted = set(ids)
            # Labels for each company's headquarters and the industry it matched on.
            hq_ids = sorted({q for e in entities.values() for q in self._claim_ids(e, "P159")[:1]}
                            | {q for e in entities.values() for q in self._claim_ids(e, "P452") if q in wanted})
            hq_labels = {k: wd_label(v)
                         for k, v in (await self._entities(client, hq_ids, "labels")).items()} if hq_ids else {}
            for qid in hits:
                e = entities.get(qid) or {}
                if any(c.get("rank") != "deprecated" for c in e.get("claims", {}).get("P576", [])):  # dissolved
                    continue
                url = next((u for u in (normalize_url(w) for w in self._claim_ids(e, "P856")) if u), None)
                site = registered_domain(url) if url else None
                if not url or (site or url) in seen:
                    continue
                seen.add(site or url)
                country = next((country_names[c] for c in self._claim_ids(e, "P17") if c in country_names), None)
                hq = next((hq_labels.get(q) for q in self._claim_ids(e, "P159")[:1]), None)
                industry = next((hq_labels.get(q) for q in self._claim_ids(e, "P452") if q in wanted), None)
                hint = {"company_name": wd_label(e), "headquarters": hq,
                        "country": country, "industry": industry, "website_url": url,
                        "founded_year": wd_founded(e),
                        "_source": f"http://www.wikidata.org/entity/{qid}"}
                out.append(DiscoveryResult(url, "wikidata", {k: v for k, v in hint.items() if v},
                                           referrer=hint["_source"]))
                if len(out) >= d.max_results:
                    return out
            if len(hits) < 200:
                break
        return out

    def _rows_to_results(self, rows: list[dict[str, Any]], max_results: int) -> list[DiscoveryResult]:
        out: list[DiscoveryResult] = []
        seen: set[str] = set()
        for row in rows:
            url = normalize_url(row.get("website", {}).get("value", ""))
            if not url or url in seen:
                continue
            seen.add(url)
            org = row.get("org", {}).get("value", "")
            hint = {
                "company_name": row.get("orgLabel", {}).get("value"),
                "headquarters": row.get("hqLabel", {}).get("value"),
                "country": row.get("countryLabel", {}).get("value"),
                "website_url": url,
                "_source": org,
            }
            # The label service falls back to the bare Q-id when an item has no English label.
            if hint["company_name"] and QID_RE.match(hint["company_name"]):
                hint.pop("company_name")
            out.append(DiscoveryResult(url, "wikidata", {k: v for k, v in hint.items() if v}, referrer=org))
            if len(out) >= max_results:
                break
        return out

    async def _via_sparql(
        self, client: httpx.AsyncClient, ids: list[str], spec: ExtractionSpec
    ) -> list[DiscoveryResult]:
        d = spec.discovery
        try:
            rows = await self._sparql(client, self.build_query(ids, d.countries, d.region, d.max_results * 2,
                                                               lean=True))
        except httpx.TimeoutException:
            raise DiscoveryError("Wikidata did not answer within 60 seconds; the public query service is busy. "
                                 "Retry the job later or add start URLs.") from None
        except httpx.HTTPStatusError as exc:
            raise DiscoveryError(f"Wikidata query failed (HTTP {exc.response.status_code})") from None
        return self._rows_to_results(rows, d.max_results)

    async def discover(self, spec: ExtractionSpec) -> list[DiscoveryResult]:
        d = spec.discovery
        if not (d.industry or d.countries or d.region):
            raise DiscoveryError("Wikidata discovery needs an industry, countries or a region")
        client = self._client()
        try:
            try:
                ids = await self.industry_ids(client, d.industry) if d.industry else []
            except httpx.HTTPError as exc:
                raise DiscoveryError(f"Wikidata search failed: {type(exc).__name__}") from None
            if d.industry and not ids:
                raise DiscoveryError(f"Wikidata has no industry matching {d.industry!r}")
            try:
                out = await self._via_search(client, ids, spec)
            except httpx.HTTPError:
                # The search index is down or rate limited; the query service is slower but independent.
                out = await self._via_sparql(client, ids, spec)
        except httpx.HTTPError as exc:
            raise DiscoveryError(f"Wikidata request failed: {type(exc).__name__}") from None
        finally:
            if self.client is None:
                await client.aclose()
        if not out:
            raise DiscoveryError("Wikidata returned no companies with a website for this industry and region; "
                                 "try a broader region or add start URLs")
        return out


MAX_HITS_KEPT = 5  # search hits remembered per site: which engines found it, for which wording, and what they said


def hit_context(hit, query: str) -> dict[str, str]:
    """What one search hit said about a site, kept with the site so a drop or a record can be traced to it."""
    return {"provider": hit.provider or "web search", "query": query, "url": hit.url, "title": (hit.title or "")[:200],
            "snippet": " ".join((hit.snippet or "").split())[:300]}


REGION_NAMES = {"europe": "Europe", "north_america": "North America", "asia": "Asia", "africa": "Africa",
                "south_america": "South America", "oceania": "Australia"}
# Sites that list or talk about companies rather than being one. A result on these is never a homepage.
NOT_COMPANY_SITES = {
    "wikipedia.org", "wikidata.org", "wikimedia.org", "linkedin.com", "facebook.com", "instagram.com", "x.com",
    "twitter.com", "youtube.com", "tiktok.com", "reddit.com", "quora.com", "medium.com", "github.com",
    "crunchbase.com", "zoominfo.com", "dnb.com", "bloomberg.com", "reuters.com", "forbes.com", "statista.com",
    "glassdoor.com", "indeed.com", "yelp.com", "tracxn.com", "cbinsights.com", "owler.com", "craft.co",
    "pitchbook.com", "g2.com", "capterra.com", "gartner.com", "clutch.co", "yellowpages.com", "kompass.com",
    "europages.co.uk", "europages.com", "amazon.com", "google.com", "bing.com", "duckduckgo.com", "apple.com",
    "fiercepharma.com", "fiercebiotech.com", "businesswire.com", "prnewswire.com", "globenewswire.com",
    "marketsandmarkets.com", "grandviewresearch.com", "mordorintelligence.com", "ibisworld.com",
}


class SearxngProvider:
    """Company homepages from a self-hosted SearXNG instance's JSON API."""

    name = "searxng"
    MAX_PAGES = 5
    MAX_QUERIES = 6
    MAX_LIST_PAGES = 3  # list pages read per question (one free model call each)
    MAX_LIST_LOOKUPS = 30  # names from those pages looked up
    MAX_PER_LIST = 6  # sites one list page may add: one off-topic list (a jobs board) once crowded out the rest

    def __init__(self, client: httpx.AsyncClient | None = None, base_url: str | None = None,
                 judge=None) -> None:
        self.client = client
        self.base_url = (base_url if base_url is not None else get_settings().searxng_url).rstrip("/")
        self.judge = judge
        self.fetch_page = None  # set by the crawler: robots.txt respected, network rules checked
        self.on_note = None
        self.notes: list[str] = []

    def _say(self, kind: str, message: str, url: str | None = None) -> None:
        if self.on_note is not None:
            self.on_note(kind, message, url, source=self.name)

    async def _from_lists(self, client, hub, question: str, pages: list[str], sites: set[str], room: int
                          ) -> list[DiscoveryResult]:
        """Companies named on list pages, each kept only when its own website is found and confirmed."""
        from app.discovery.lists import names_on_list
        from app.discovery.websites import WebsiteFinder
        from app.evidence.judge import Judge

        if self.fetch_page is None or not pages or room <= 0:
            return []
        judge = self.judge or Judge()

        async def text(url: str) -> str | None:
            doc = await self.fetch_page(url)
            return f"{doc.title} {doc.text}" if doc else None

        finder = WebsiteFinder(client, self.base_url, text, hub=hub)
        out: list[DiscoveryResult] = []
        lookups = 0
        try:
            for url in pages[:self.MAX_LIST_PAGES]:
                doc = await self.fetch_page(url)
                if doc is None:
                    self._say("skipped", f"List page could not be read: {url}", url)
                    continue
                names, why = await names_on_list(judge, question, doc)
                self._say("read" if names else "skipped", f"List page {url}: "
                          + (f"{len(names)} name(s)" if names else why), url)
                if not names and judge.unavailable:
                    self.notes.append(f"web search: list pages not read ({judge.unavailable})")
                    break
                added = 0
                for name in names:
                    if len(out) >= room or lookups >= self.MAX_LIST_LOOKUPS:
                        return out
                    if added >= self.MAX_PER_LIST:
                        break
                    lookups += 1
                    site, how = await finder.find(name)
                    domain = registered_domain(site) if site else ""
                    if not domain or domain in sites:
                        continue
                    sites.add(domain)
                    self._say("search", f"Website of {name} (from a list page): {site} ({how})", site)
                    out.append(DiscoveryResult(site, "searxng", {"company_name": name, "_source": url},
                                               referrer=f"list page: {url}"))
                    added += 1
        finally:
            if self.judge is None:
                await judge.aclose()
        return out

    @staticmethod
    def queries(spec: ExtractionSpec) -> list[str]:
        from app.spec.interpret import COUNTRIES

        d = spec.discovery
        noun = "companies" if spec.entity in ("company", "record") else f"{spec.entity}s"
        names = {iso: name.title() for name, iso in COUNTRIES.items() if len(name) > 3}
        places = [names.get(c, c) for c in d.countries] or ([REGION_NAMES[d.region]] if d.region else [""])
        subject = " ".join(x for x in [d.industry or "", *d.keywords[:3]] if x).strip()
        if not subject:
            return []
        return [f"{subject} {noun} {place}".strip() for place in places[:10]]

    @staticmethod
    def homepage(url: str) -> str | None:
        norm = normalize_url(url)
        if not norm:
            return None
        site = registered_domain(norm)
        if not site or site in NOT_COMPANY_SITES or any(site.endswith("." + s) for s in NOT_COMPANY_SITES):
            return None
        scheme, rest = norm.split("://", 1)
        return f"{scheme}://{rest.split('/', 1)[0]}/"

    @staticmethod
    def wordings(spec: ExtractionSpec) -> list[str]:
        """The searches discovery sends: for each place the plain wording, then a list-style and a where-based
        one (engines answer each differently, so each finds companies the others miss), at most MAX_QUERIES so
        a many-country question does not spend a month's free searches at once."""
        from app.spec.interpret import COUNTRIES

        d = spec.discovery
        noun = "companies" if spec.entity in ("company", "record") else f"{spec.entity}s"
        names = {iso: name.title() for name, iso in COUNTRIES.items() if len(name) > 3}
        places = [names.get(c, c) for c in d.countries] or ([REGION_NAMES[d.region]] if d.region else [""])
        subject = " ".join(x for x in [d.industry or "", *d.keywords[:3]] if x).strip()
        if not subject:
            return []
        out: list[str] = []
        for place in places:
            out.append(f"{subject} {noun} {place}".strip())
            out.append(f"largest {subject} {noun} in {place}" if place else f"largest {subject} {noun}")
            if place:
                out.append(f"{subject} {noun} headquartered in {place}")
        return out[:SearxngProvider.MAX_QUERIES]

    async def discover(self, spec: ExtractionSpec) -> list[DiscoveryResult]:
        client = self.client or httpx.AsyncClient(timeout=30, headers={"User-Agent": get_settings().user_agent})
        hub = SearchHub.from_settings(client, self.base_url)
        if not hub.configured:
            if self.client is None:
                await client.aclose()
            raise DiscoveryError("web search is not configured (set a search API key or WEBDATA_SEARXNG_URL); skipped")
        queries = self.wordings(spec)
        if not queries:
            if self.client is None:
                await client.aclose()
            raise DiscoveryError("web search discovery needs an industry or keywords")
        want = spec.discovery.max_results
        out: list[DiscoveryResult] = []
        sites: set[str] = set()

        from app.discovery.lists import looks_like_list

        noun = "companies" if spec.entity in ("company", "record") else f"{spec.entity}s"
        lists: list[str] = []

        by_site: dict[str, DiscoveryResult] = {}

        def take(hits, query: str, limit: int) -> list:
            """Adds up to `limit` new company homepages; returns the hits not taken. Every hit is kept with the
            site it points to, so several engines finding one company stay visible."""
            left = []
            count = {"new": 0, "list": 0, "not a company site": 0, "repeat": 0, "held back": 0}
            for r in hits:
                if looks_like_list(r.url, r.title, noun):  # a page about many companies is no company's site
                    count["list"] += 1
                    if r.url not in lists:
                        lists.append(r.url)
                    continue
                home = self.homepage(r.url)
                if not home:
                    count["not a company site"] += 1
                    continue
                site = registered_domain(home)
                if site in sites:
                    count["repeat"] += 1
                    seen = by_site.get(site)
                    if seen is not None and len(seen.hint["_search"]) < MAX_HITS_KEPT:
                        seen.hint["_search"].append(hit_context(r, query))
                    continue
                if len(out) >= want or limit <= 0:
                    count["held back"] += 1
                    left.append((r, query))
                    continue
                sites.add(site)
                out.append(DiscoveryResult(home, "searxng", {"_source": r.url, "_search": [hit_context(r, query)]},
                                           referrer=f"{r.provider}: {query}"))
                by_site[site] = out[-1]
                count["new"] += 1
                limit -= 1
            if len(hits) > 1:  # a single leftover taken later is not a search of its own
                engines = Counter(r.provider or "web search" for r in hits)
                self._say("search", f"Search {query!r}: {len(hits)} result(s) ("
                          + ", ".join(f"{e} {n}" for e, n in engines.most_common()) + "): "
                          + ", ".join(f"{n} {k}" for k, n in count.items() if n))
            return left

        # Every wording gets its share of the first page before any wording's leftovers or later pages, so the
        # first wording alone no longer fills the list.
        share = max(1, -(-want // len(queries)))
        leftovers: list = []
        exhausted: set[str] = set()
        try:
            for query in queries:
                try:
                    hits = await hub.search(query)
                except SearchError as exc:
                    if out:
                        break
                    raise DiscoveryError(str(exc)) from None
                if not hits:
                    exhausted.add(query)
                leftovers += take(hits, query, share)
            # Names read off list pages and the leftover search results share what room is left: a ranking that
            # answers the question is a good lead, but so is a company search found directly, and a list's names
            # once took every remaining place. Up to half the room is kept for the direct results waiting.
            room = want - len(out)
            waiting = {registered_domain(self.homepage(r.url)) for r, _q in leftovers} - sites
            out += await self._from_lists(client, hub, queries[0], lists, sites, room - min(len(waiting), room // 2))
            for r, query in leftovers:
                take([r], query, 1)
            for page in range(2, self.MAX_PAGES + 1):
                for query in queries:
                    if len(out) >= want:
                        return out[:want]
                    if query in exhausted:
                        continue
                    try:
                        hits = await hub.search(query, page=page)
                    except SearchError:
                        hits = []
                    if not hits:
                        exhausted.add(query)
                    take(hits, query, want)
                    await asyncio.sleep(1.0 if get_settings().env != "test" else 0)
        finally:
            if self.client is None:
                await client.aclose()
        if not out:
            raise DiscoveryError(hub.explain() if hub.problems
                                 else "web search found no company websites for this query")
        return out[:want]


def providers_for(spec: ExtractionSpec) -> list[DiscoveryProvider]:
    from app.discovery.case_studies import CaseStudiesProvider
    from app.discovery.gleif import GleifProvider
    from app.discovery.news import NewsProvider
    from app.discovery.sec_edgar import SecEdgarProvider
    from app.discovery.sec_filings import SecFilingsProvider

    registry: dict[str, DiscoveryProvider] = {"seeds": SeedProvider(), "wikidata": WikidataProvider(),
                                              "searxng": SearxngProvider(), "sec_edgar": SecEdgarProvider(),
                                              "gleif": GleifProvider(), "sec_filings": SecFilingsProvider(),
                                              "case_studies": CaseStudiesProvider(),
                                              "news": NewsProvider()}
    return [registry[name] for name in spec.discovery.providers if name in registry]
