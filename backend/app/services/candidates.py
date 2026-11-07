"""Candidate recall: did the companies a question should find ever reach a list, before any page is read?

Per-company search ('"<company>" "<product>"') proves most companies it is asked about, but it can only ask about
companies some source named first. This reads back what a finished job stored and answers, for every company in
an answer key, the first place it fell out of that list:

1. not named by any source: no source listed it, so nothing could search for it;
2. named, country not known: listed, but no source said where it is, so a search limited to the asked
   countries skips it;
3. named, placed in another country: a source put it outside the countries asked for;
4. named and in the asked country: it could be searched by name (or was already proven).

Read from the job's own rows (starting URLs and their hints, proof rows, company facts), never from a new crawl,
so it costs no search and no model call. A source's list that was never stored (for example a list a source
fetched only to search from it) cannot be counted here; such a source must store its list to be measured.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select

from app.crawl.urlnorm import registered_domain
from app.discovery.relevance import country_iso
from app.models import CompanyFact, CrawlJob, CrawlJobEvent, DiscoveredUrl, Evidence, ExtractionSchema

PROVEN = ("Confirmed", "Likely")
NOT_NAMED = "not named by any source"
NO_COUNTRY = "named, country not known"
ELSEWHERE = "named, placed in another country"
SEARCHABLE = "named, in the asked country, not proven"
PROVEN_ALREADY = "named, in the asked country, proven"
ORDER = (NOT_NAMED, NO_COUNTRY, ELSEWHERE, SEARCHABLE, PROVEN_ALREADY)


@dataclass
class Listed:
    """One company as the job's sources named it."""

    name: str
    sites: set[str] = field(default_factory=set)
    sources: set[str] = field(default_factory=set)
    countries: set[str] = field(default_factory=set)
    proven: bool = False


def _iso(value: Any) -> str:
    return country_iso(str(value or "")) or ""


def listed_companies(db, job_id: uuid.UUID) -> list[Listed]:
    """Every company a source of this job named, with who named it, the countries sources gave it and whether
    proof was kept for it. Names are kept as given; matching to a key is done by the caller."""
    out: list[Listed] = []

    def add(name: str, site: str, source: str, country: str = "", proven: bool = False) -> None:
        name = (name or "").strip()
        if not name:
            return
        item = Listed(name=name)
        if site:
            item.sites.add(site)
        item.sources.add(source)
        if country:
            item.countries.add(country)
        item.proven = proven
        out.append(item)

    for url, method, hint in db.execute(select(DiscoveredUrl.url, DiscoveredUrl.method, DiscoveredUrl.hint).where(
            DiscoveredUrl.job_id == job_id, DiscoveredUrl.depth == 0)).all():
        hint = hint or {}
        add(str(hint.get("company_name") or ""), registered_domain(url) or "", method or "?",
            _iso(hint.get("country")), str(hint.get("uses_technology") or "") in PROVEN)
    for e in db.execute(select(Evidence).where(Evidence.job_id == job_id)).scalars():
        add(e.company, registered_domain(e.website) or "" if e.website else "", "proof pages", "",
            e.kept and e.verdict in PROVEN)
    for f in db.execute(select(CompanyFact).where(CompanyFact.job_id == job_id)).scalars():
        add(f.company, f.site, f"fact: {f.by.split(':')[0].strip() or f.kind}",
            _iso(f.value) if f.kind == "country" else "")
    return out


def _matches(entry: dict[str, Any], item: Listed) -> bool:
    from app.services.scorecard import name_key

    if entry.get("website") and registered_domain(entry["website"]) in item.sites:
        return True
    want, have = name_key(entry.get("company", "")), name_key(item.name)
    return bool(want and have and (want in have or have in want))


def stage_of(entry: dict[str, Any], listed: list[Listed], countries: list[str]) -> tuple[str, list[str]]:
    """The first stage of the list this expected company fell out of, and the sources that named it."""
    mine = [item for item in listed if _matches(entry, item)]
    if not mine:
        return NOT_NAMED, []
    sources = sorted({s for item in mine for s in item.sources})
    known = {c for item in mine for c in item.countries}
    asked = {c.upper() for c in countries}
    if asked and not known:
        return NO_COUNTRY, sources
    if asked and not known & asked:
        return ELSEWHERE, sources
    return (PROVEN_ALREADY if any(item.proven for item in mine) else SEARCHABLE), sources


def company_search_notes(db, job_id: uuid.UUID) -> list[str]:
    """What a per-company search pass logged about itself ("X of Y listed companies searched ..."), when the job
    ran one."""
    rows = db.execute(select(CrawlJobEvent.message).where(
        CrawlJobEvent.job_id == job_id, CrawlJobEvent.message.like("Discovery note: company_search:%"))).scalars()
    return [m.removeprefix("Discovery note: ") for m in rows]


def candidate_recall(db, job_id: uuid.UUID, key: dict[str, Any]) -> dict[str, Any]:
    """Per expected company: its stage and who named it; plus the totals the scorecard prints."""
    job = db.get(CrawlJob, job_id)
    d = (db.get(ExtractionSchema, job.schema_id).spec or {}).get("discovery") or {}
    countries = [c for c in (_iso(c) for c in d.get("countries") or []) if c]
    listed = listed_companies(db, job_id)
    must = key.get("must_include") or []
    rows = []
    for entry in must:
        stage, sources = stage_of(entry, listed, countries)
        rows.append({"company": entry.get("company", ""), "stage": stage, "named by": sources})
    names = {item.name.casefold() for item in listed}
    in_country = {item.name.casefold() for item in listed
                  if not countries or item.countries & set(countries)}
    return {"rows": rows, "countries": countries, "listed": len(names), "listed in asked country": len(in_country),
            "company search": company_search_notes(db, job_id)}


def scorecard_rows(result: dict[str, Any]) -> dict[str, str]:
    """The candidate-recall lines of a scorecard, with the same "n/d (p%)" form as its other key lines."""
    from app.services.scorecard import _pct

    rows = result["rows"]
    total = len(rows)
    named = [r for r in rows if r["stage"] != NOT_NAMED]
    in_country = [r for r in rows if r["stage"] in (SEARCHABLE, PROVEN_ALREADY)]
    out = {"candidates: companies any source named": str(result["listed"]),
           "candidates: named and in the asked country": str(result["listed in asked country"]),
           "key: candidate recall (named by a source)": _pct(len(named), total),
           "key: candidate recall (named, in the asked country)": _pct(len(in_country), total)}
    for stage in ORDER:
        who = [r["company"] for r in rows if r["stage"] == stage]
        if who:
            out[f"key: candidate stage: {stage}"] = f"{len(who)} ({', '.join(who)})"
    for i, note in enumerate(result["company search"], 1):
        out[f"company search note {i}"] = note
    return out
