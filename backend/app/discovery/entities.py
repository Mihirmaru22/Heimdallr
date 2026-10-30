"""Which registered organisation a name stands for, and so where it is based and what its website is.

A company's country and website were guessed from its marketing site (phone formats, a country-code domain, three
of five search results agreeing). That failed on .com brands, multinationals and parent vs subsidiary: run 2
(2026-10-28) lost EnerSys, CONMED, Nationwide, Lick, Bharat Serums and others at the country check, and passed a US
company as Indian. Registries record these facts about legal entities:

- Wikidata: country (P17), headquarters (P159), official website (P856);
- GLEIF: legal and headquarters address of every entity with an LEI;
- SEC EDGAR (the local `sec_companies` copy): business address of US-listed companies.

A name is matched to an entity only by rules: the entity's official website is the company's website, or the names
are the same once legal forms are set aside (a one-word name must be exactly the same). When the matching entities
disagree on the country ("Emerald Technology" in the UK and in the US), nothing is settled and the reason says
which entities disagreed. Nothing here guesses.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlalchemy import select

from app.crawl.netguard import BlockedDestination
from app.crawl.urlnorm import homepage, normalize_url, registered_domain
from app.db import session_scope
from app.discovery.gleif import API as GLEIF_API
from app.discovery.gleif import REQUEST_GAP as GLEIF_GAP
from app.discovery.gleif import _entity as gleif_entity
from app.discovery.providers import COUNTRY_QIDS, WIKIDATA_API, WikidataProvider, wd_label
from app.models import SecCompany

QID_ISO = {qid: iso for iso, (qid, _name) in COUNTRY_QIDS.items()}
# Legal forms and filler that are not part of what a name identifies.
NOISE = re.compile(r"\b(inc|incorporated|ltd|limited|llc|llp|lp|plc|pvt|private|pty|gmbh|ag|aktiengesellschaft|kgaa|kg|"
                   r"se|sa|sas|sarl|srl|spa|sl|nv|bv|oy|oyj|ab|asa|as|kk|bhd|sdn|ltda|corp|corporation|co|company|"
                   r"group|holdings?|the|and|of)\b\.?", re.I)
# A Wikidata item stands for a business only when it carries a business's properties: industry, LEI, stock
# exchange, number of employees, revenue, headquarters, legal form or parent organisation. "Lick" the observatory
# has none of them; Lick the paint brand would.
BUSINESS_PROPERTIES = ("P452", "P1278", "P414", "P1128", "P2139", "P159", "P1454", "P749")
WIKIDATA_CANDIDATES = 7
WIKIDATA_RETRY_WAIT = 5.0
# A registry that times out or answers 5xx is asked again after these pauses (seconds): a busy moment lost GLEIF
# matches for several companies in one run (NetSuite UK, 2026-10-29), and each became "country unconfirmed".
REGISTRY_RETRY_WAITS = (2.0, 8.0)


def transient(exc: BaseException) -> bool:
    """A failure that a later request may not have: a timeout, a dropped connection, a server error."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return isinstance(exc, httpx.TransportError)
GLEIF_CANDIDATES = 10


def words(name: str) -> list[str]:
    """The words of a name that identify it: legal forms and bracketed notes ("(BSV)", "(Darmstadt, Germany)")
    are left out."""
    return re.findall(r"[a-z0-9]+", NOISE.sub(" ", re.sub(r"\([^)]*\)", " ", name.casefold())))


def search_name(company: str) -> str:
    """The name as registries index it: "Bharat Serums and Vaccines Limited (BSV)" -> "Bharat Serums and Vaccines"."""
    cleaned = re.sub(r"\s+", " ", NOISE.sub(" ", re.sub(r"\([^)]*\)", " ", company))).strip(" ,.-")
    return cleaned if len(cleaned) >= 2 else company.strip()


def name_match(company: str, entity: str) -> str:
    """"exact" when the names are the same once legal forms are set aside, "words" when every word of the company's
    name is in the entity's and at most one is added ("Nationwide Insurance" / "Nationwide Mutual Insurance
    Company"), else "". A one-word name only ever matches exactly: "Lick" is not "Lick Sweets". A "words" match
    alone never settles a country ("Emerald Technology" is not "Emerald Technology Ventures AG")."""
    a, b = words(company), words(entity)
    if not a or not b:
        return ""
    if a == b or "".join(a) == "".join(b):
        return "exact"
    if len(a) >= 2 and set(a) <= set(b) and len(set(b) - set(a)) <= 1:
        return "words"
    return ""


@dataclass
class Candidate:
    registry: str  # wikidata | gleif | sec
    ident: str  # Q-id, LEI or CIK
    name: str
    country: str  # ISO code, or ""
    place: str = ""
    website: str = ""
    how: str = ""  # website | exact | words


@dataclass
class Resolution:
    country: str = ""  # settled ISO code, or ""
    website: str = ""  # an official website from a registry, or ""
    by: str = ""  # "registry: wikidata", ...
    detail: str = ""  # which entity and how it matched, or why nothing was settled
    candidates: list[Candidate] = field(default_factory=list)


def settle(company: str, website: str, candidates: list[Candidate]) -> Resolution:
    """The strongest matches decide: an entity whose official website is the company's, else exact name matches,
    else word matches; within the strongest kind every entity must agree on the country."""
    site = registered_domain(website) if website else ""
    for c in candidates:
        c.how = "website" if site and c.website and registered_domain(c.website) == site else name_match(company,
                                                                                                         c.name)
    for kind in ("website", "exact"):
        group = [c for c in candidates if c.how == kind and c.country]
        if not group:
            continue
        countries = {c.country for c in group}
        names = "; ".join(f"{c.name} ({c.registry} {c.ident}, {c.country})" for c in group[:4])
        if len(countries) > 1:
            return Resolution(detail=f"registries disagree on {company!r}: {names}", candidates=candidates)
        c = group[0]
        sites = {registered_domain(x.website) for x in group if x.website}
        return Resolution(country=c.country, website=homepage(c.website) if c.website and len(sites) == 1 else "",
                          by=f"registry: {c.registry}",
                          detail=f"{c.name} ({c.registry} {c.ident}{', ' + c.place if c.place else ''}), "
                                 f"matched by {kind}"
                                 + (f"; {len(group)} entities agree" if len(group) > 1 else ""),
                          candidates=candidates)
    return Resolution(detail=f"no registry entity matches {company!r}", candidates=candidates)


class EntityResolver:
    def __init__(self, client: httpx.AsyncClient, gleif_gap: float = GLEIF_GAP,
                 retry_waits: tuple[float, ...] = REGISTRY_RETRY_WAITS) -> None:
        self.client = client
        self.gleif_gap = gleif_gap
        self.retry_waits = retry_waits
        self.cache: dict[str, Resolution] = {}  # per job: one lookup per name
        self.wd = WikidataProvider(client)
        self.problems: list[str] = []

    async def resolve(self, company: str, website: str = "") -> Resolution:
        key = f"{' '.join(words(company))}|{registered_domain(website) if website else ''}"
        if key in self.cache:
            return self.cache[key]
        candidates: list[Candidate] = []
        failed: list[str] = []
        for source in (self._wikidata, self._gleif, self._sec):
            for wait in (*self.retry_waits, None):
                try:
                    candidates += await source(company)
                    break
                except (httpx.HTTPError, ValueError, KeyError, BlockedDestination) as exc:
                    if wait is not None and transient(exc):
                        await asyncio.sleep(wait)  # a busy moment: asked again, not given up on
                        continue
                    name = source.__name__.strip("_")
                    problem = f"{name}: {type(exc).__name__}"
                    if problem not in self.problems:
                        self.problems.append(problem)
                    failed.append(name)
                    break
        result = settle(company, website, candidates)
        if failed and not result.country:
            # Not "no entity matches": a registry could not be asked. Kept out of the job's record of answers, so
            # the next step that needs this name asks again.
            result.detail = f"registry lookup failed ({', '.join(failed)}); {result.detail}"
            return result
        self.cache[key] = result
        return result

    async def _wikidata(self, company: str) -> list[Candidate]:
        params = {"action": "wbsearchentities", "search": search_name(company)[:100], "language": "en", "type": "item",
                  "limit": WIKIDATA_CANDIDATES, "format": "json"}
        for attempt in range(2):
            resp = await self.client.get(WIKIDATA_API, params=params)
            body = resp.json() if resp.status_code == 200 else {}
            # Wikidata throttles bursts with HTTP 429 or an "error" body: that is no answer, not "no entity".
            if resp.status_code == 200 and "error" not in body:
                break
            if attempt == 0:
                await asyncio.sleep(WIKIDATA_RETRY_WAIT)
        else:
            raise ValueError(f"Wikidata did not answer ({resp.status_code} {str(body.get('error', ''))[:80]})")
        ids = [h["id"] for h in body.get("search", []) if re.fullmatch(r"Q\d+", h.get("id", ""))]
        if not ids:
            return []
        entities = await self.wd._entities(self.client, ids, "labels|claims|aliases")
        out = []
        for qid in ids:
            e = entities.get(qid) or {}
            claims = e.get("claims", {})
            if not any(claims.get(p) for p in BUSINESS_PROPERTIES):
                continue
            if any(c.get("rank") != "deprecated" for c in e.get("claims", {}).get("P576", [])):  # dissolved
                continue
            label = wd_label(e) or ""
            aliases = [a.get("value", "") for a in (e.get("aliases") or {}).get("en", [])]
            name = next((n for n in [label, *aliases] if name_match(company, n)), label)
            country = next((QID_ISO[q] for q in self.wd._claim_ids(e, "P17") if q in QID_ISO), "")
            site = next((u for u in (normalize_url(w) for w in self.wd._claim_ids(e, "P856")) if u), "")
            out.append(Candidate("wikidata", qid, name, country, website=site))
        return out

    async def _gleif(self, company: str) -> list[Candidate]:
        await asyncio.sleep(self.gleif_gap)
        resp = await self.client.get(GLEIF_API, params={
            "filter[fulltext]": search_name(company)[:100], "filter[entity.status]": "ACTIVE",
            "page[size]": GLEIF_CANDIDATES},
            headers={"Accept": "application/vnd.api+json"})
        if resp.status_code == 429:
            await asyncio.sleep(60)
            return await self._gleif(company)
        resp.raise_for_status()
        out = []
        for record in resp.json().get("data") or []:
            ent = gleif_entity(record)
            if ent and ent["country"]:
                out.append(Candidate("gleif", ent["lei"], ent["name"], ent["country"], place=ent["headquarters"]))
        return out

    async def _sec(self, company: str) -> list[Candidate]:
        first = (words(company) or [""])[0]
        if len(first) < 2:
            return []
        with session_scope(bypass=True) as db:
            rows = db.execute(select(SecCompany).where(SecCompany.name.ilike(f"{first}%")).limit(50)).scalars().all()
            found = [(r.cik, r.name, r.state, r.foreign, r.website) for r in rows]
        return [Candidate("sec", str(cik), name, "" if foreign else "US", place=state, website=site or "")
                for cik, name, state, foreign, site in found if name_match(company, name)]


def resolution_facts(company: str, site: str, res: Resolution) -> list[dict[str, Any]]:
    """The facts a resolution establishes, for company_facts."""
    facts = [{"site": site, "company": company, "kind": "country", "value": res.country, "by": res.by or "registry",
              "detail": res.detail, "source_url": "", "quote": ""}]
    if res.website:
        facts.append({"site": registered_domain(res.website) or site, "company": company, "kind": "website",
                      "value": res.website, "by": res.by, "detail": res.detail, "source_url": "", "quote": ""})
    return facts
