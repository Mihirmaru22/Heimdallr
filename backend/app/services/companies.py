"""One record per company a job came across, and one decision about it, made at the end from every fact.

Sources do not drop companies. The proof readers record proof (the `evidence` table), and the crawler, the
website lookup and the country and industry checks record what they established (`company_facts`). Here those
facts are grouped into one record per company and weighed once:

- delivered: the proof says it uses the product (Confirmed or Likely), it is in the requested country, and the
  question's filters are met (or there are none);
- country unconfirmed: proven, but no evidence settles where it is (shown, never dropped);
- elsewhere: proven, but the evidence puts it in another country;
- filter not met: proven, but a filter the question asked for failed (the reason is kept);
- weak proof: only a mention, or proof without a use;
- no proof: crawled, nothing showed it uses the product.

For a question without a technology the proof part is left out. Country evidence is weighed in this order: a
registry, a clear statement in the proof, the company's own pages (see `COUNTRY_ORDER`). Measured on 2026-10-28:
companies with proof were dropped at the first gate that could not confirm one of its facts, and 1 in 6 survived.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import delete, select

from app.crawl.urlnorm import homepage, registered_domain
from app.db import session_scope
from app.evidence.judge import VERDICT_RANK
from app.models import CompanyFact, DiscoveredUrl, Evidence, ExtractedRecord, JobCompany
from app.spec.models import ExtractionSpec

DELIVERED, UNCONFIRMED, ELSEWHERE, FILTER, WEAK, NO_PROOF = (
    "delivered", "country unconfirmed", "elsewhere", "filter not met", "weak proof", "no proof")
USES = {"Confirmed", "Likely"}
# Which evidence of a company's country counts first (Ronak, 2026-10-28): a registry entry, then a clear statement
# in the proof text, then the company's own pages. The first kind that settles it decides.
COUNTRY_ORDER = ("registry", "proof", "own pages")
PROOF_SOURCES = {"case_studies", "news", "sec_filings"}  # discovery sources that bring proof with the company
# Legal forms and filler that are not part of the name ("Kemwell Biopharma Pvt. Ltd." is Kemwell Biopharma).
NOISE = re.compile(r"\b(inc|incorporated|ltd|limited|llc|llp|lp|plc|pvt|private|gmbh|ag|se|sa|sas|srl|spa|nv|bv|"
                   r"oy|ab|as|kk|corp|corporation|co|company|group|holdings?|the)\b\.?", re.I)


def name_key(name: str) -> str:
    """"Kemwell BioPharma Pvt. Ltd." and "kemwell biopharma" are one company."""
    return "name:" + re.sub(r"[^a-z0-9]+", "", NOISE.sub(" ", name.casefold()))


def country_rank(by: str) -> int:
    head = by.split(":", 1)[0].strip()
    return COUNTRY_ORDER.index(head) if head in COUNTRY_ORDER else len(COUNTRY_ORDER)


@dataclass
class Company:
    key: str
    names: list[str] = field(default_factory=list)
    website: str = ""
    sources: list[str] = field(default_factory=list)
    proof: list[dict[str, Any]] = field(default_factory=list)  # kept evidence
    rejected: list[dict[str, Any]] = field(default_factory=list)  # evidence turned down, for the reasons
    facts: list[dict[str, Any]] = field(default_factory=list)
    record: ExtractedRecord | None = None

    @property
    def name(self) -> str:
        return self.names[0] if self.names else self.key.removeprefix("name:")


def decide(c: Company, spec: ExtractionSpec) -> tuple[str, list[str], dict[str, str]]:
    """(status, reasons, details) for one company. Pure: the same facts always give the same decision."""
    d = spec.discovery
    reasons: list[str] = []
    best = max(c.proof, key=lambda e: (VERDICT_RANK.get(e["verdict"], 0), e["strength"]), default=None)
    record_verdict = (c.record.data.get("uses_technology") if c.record is not None else None) or ""
    verdict = best["verdict"] if best else record_verdict
    details = {"proof_verdict": verdict, "proof_url": best["url"] if best else "",
               "proof_quote": (best["quote"] if best else "")[:1000], "country": "", "country_by": ""}
    if d.technology:
        if best:
            reasons.append(f"proof: {best['verdict']} ({best['source_type'] or 'page'}) {best['url']}")
        elif record_verdict:
            reasons.append(f"proof: {record_verdict} on its own site")
        elif c.rejected:
            reasons.append(f"no proof: {c.rejected[0]['reason']}")
        else:
            reasons.append("no proof found")

    # Country: the strongest kind of evidence that settles it decides; within a kind, several countries settle
    # nothing (a branch office looks like a headquarters).
    country_state = "n/a"
    if d.countries:
        country_state = "unconfirmed"
        facts = sorted((f for f in c.facts if f["kind"] == "country"), key=lambda f: country_rank(f["by"]))
        for rank in sorted({country_rank(f["by"]) for f in facts}):
            settled = {f["value"] for f in facts if country_rank(f["by"]) == rank and f["value"]}
            if len(settled) == 1:
                (iso,) = settled
                how = next(f for f in facts if country_rank(f["by"]) == rank and f["value"] == iso)
                details["country"], details["country_by"] = iso, f"{how['by']}: {how['detail']}"[:500]
                country_state = "in" if iso in d.countries else "out"
                reasons.append(f"country: {iso} ({how['by']}: {how['detail']})"[:400])
                break
        else:
            why = next((f["detail"] for f in facts if f["detail"]), "no registry entry, statement or page settles it")
            reasons.append(f"country not confirmed: {why}"[:400])

    failed = [f for f in c.facts if f["kind"] == "filter" and f["value"] == "not met"]
    reasons += [f"filter not met: {f['detail']}"[:400] for f in failed]
    reasons += [f"not read: {f['detail']}"[:400] for f in c.facts if f["kind"] == "crawl"]
    if not c.website:
        why = next((f["detail"] for f in c.facts if f["kind"] == "website" and not f["value"]), "")
        if why:
            reasons.append(f"no website: {why}"[:400])

    if d.technology:
        if verdict not in USES:
            return (WEAK if verdict else NO_PROOF), reasons, details
    if country_state == "out":
        return ELSEWHERE, reasons, details
    if failed:
        return FILTER, reasons, details
    if country_state == "unconfirmed":
        return UNCONFIRMED, reasons, details
    return DELIVERED, reasons, details


def _evidence_dict(e: Evidence) -> dict[str, Any]:
    return {"company": e.company, "website": e.website, "url": e.url, "quote": e.quote, "verdict": e.verdict,
            "strength": e.strength, "source_type": e.source_type, "reason": e.reason, "kept": e.kept,
            "relationship": e.relationship, "evidence_date": e.evidence_date}


def group_companies(evidence: list[dict[str, Any]], facts: list[dict[str, Any]], seeds: list[dict[str, Any]],
                    records: list[ExtractedRecord]) -> dict[str, Company]:
    """One Company per organisation: keyed by its website's registered domain when one is known, else by its
    normalised name; a name seen with a website anywhere in the job joins that website's company."""
    companies: dict[str, Company] = {}
    alias: dict[str, str] = {}  # name key -> site key

    def get(key: str) -> Company:
        return companies.setdefault(key, Company(key))

    def add_name(c: Company, name: str) -> None:
        name = (name or "").strip()
        if name and name not in c.names and not name.startswith(("http://", "https://")):
            c.names.append(name)

    for s in seeds:
        site = registered_domain(s["url"]) or ""
        if not site:
            continue
        c = get(site)
        c.website = c.website or homepage(s["url"])
        if s["method"] not in c.sources:
            c.sources.append(s["method"])
        if s["name"]:
            add_name(c, s["name"])
            alias.setdefault(name_key(s["name"]), site)
    for e in evidence:
        if e["website"] and e["company"]:
            alias.setdefault(name_key(e["company"]), registered_domain(e["website"]) or name_key(e["company"]))
    for f in facts:
        if f["site"] and f["company"]:
            alias.setdefault(name_key(f["company"]), f["site"])

    def key_of(name: str, website: str = "", site: str = "") -> str:
        if site:
            return site
        if website and registered_domain(website):
            return registered_domain(website)
        return alias.get(name_key(name), name_key(name))

    for e in evidence:
        site_page = e["source_type"] in ("Company website", "Website code") or e["source_type"].startswith("Job ad")
        if not e["company"] or (not e["kept"] and not site_page and not e["website"]):
            continue  # a page that named nobody is not a company
        c = get(key_of(e["company"], e["website"]))
        add_name(c, e["company"])
        c.website = c.website or (homepage(e["website"]) if e["website"] else "")
        (c.proof if e["kept"] else c.rejected).append(e)
    for f in facts:
        c = get(key_of(f["company"], "", f["site"]))
        add_name(c, f["company"])
        if f["kind"] == "website" and f["value"]:
            c.website = c.website or f["value"]
        c.facts.append(f)
    for r in records:
        site = registered_domain(str(r.data.get("website_url") or "")) or (r.source_urls[0] if r.source_urls else "")
        c = get(registered_domain(site) or site)
        c.record = r
        add_name(c, str(r.data.get("company_name") or ""))
        c.website = c.website or str(r.data.get("website_url") or "")
    for s in seeds:
        c = companies.get(registered_domain(s["url"]) or "")
        if c is None or c.record is not None or c.proof or c.rejected or c.facts:
            continue
        if s["status"] == "fetched":
            # Read, yet nothing of its own: its pages were kept under the domain it moved to (a redirect).
            companies.pop(c.key, None)
        elif s["reason"]:
            c.facts.append({"site": c.key, "company": c.name, "kind": "crawl", "value": s["status"], "by": "crawler",
                            "detail": s["reason"], "source_url": s["url"], "quote": ""})
    return companies


def build_companies(job_id: uuid.UUID, org_id: uuid.UUID, spec: ExtractionSpec) -> dict[str, int]:
    """Group everything the job found into companies, decide each once, and mark the records: only delivered
    companies are rows of the Data sheet; every company, with its outcome and reasons, is on the Companies sheet.
    Idempotent. Returns the count per outcome."""
    with session_scope(org_id) as db:
        evidence = [_evidence_dict(e) for e in db.execute(
            select(Evidence).where(Evidence.job_id == job_id)).scalars()]
        facts = [{"site": f.site, "company": f.company, "kind": f.kind, "value": f.value, "by": f.by,
                  "detail": f.detail, "source_url": f.source_url, "quote": f.quote}
                 for f in db.execute(select(CompanyFact).where(CompanyFact.job_id == job_id)
                                     .order_by(CompanyFact.created_at)).scalars()]
        seeds = [{"url": u.url, "method": u.method, "name": str((u.hint or {}).get("company_name") or ""),
                  "status": u.status, "reason": u.status_reason or ""}
                 for u in db.execute(select(DiscoveredUrl).where(DiscoveredUrl.job_id == job_id,
                                                                 DiscoveredUrl.depth == 0)).scalars()]
        records = db.execute(select(ExtractedRecord).where(ExtractedRecord.job_id == job_id)).scalars().all()
        companies = group_companies(evidence, facts, seeds, records)
        db.execute(delete(JobCompany).where(JobCompany.job_id == job_id))
        counts: dict[str, int] = {}
        for c in companies.values():
            status, reasons, details = decide(c, spec)
            counts[status] = counts.get(status, 0) + 1
            if c.record is not None and not c.record.user_edited:
                c.record.excluded = status != DELIVERED
            elif c.record is None and status == DELIVERED and c.proof:
                c.record = _record_from_proof(db, org_id, job_id, c, spec)
            db.add(JobCompany(org_id=org_id, job_id=job_id, key=c.key[:320], name=c.name[:300], website=c.website,
                              status=status, reasons=reasons, sources=c.sources, record_id=c.record.id if c.record
                              else None, **details))
        return counts


def _record_from_proof(db, org_id: uuid.UUID, job_id: uuid.UUID, c: Company, spec: ExtractionSpec) -> ExtractedRecord:
    """A row for a delivered company no page of which was crawled (its website could not be read, or none is
    known): its name, website and proof, each traced to the source that gave it."""
    best = max(c.proof, key=lambda e: (VERDICT_RANK.get(e["verdict"], 0), e["strength"]), default=None) or {}
    values = {"company_name": c.name, "website_url": c.website, "uses_technology": best.get("verdict", ""),
              "evidence": best.get("quote", ""), "evidence_url": best.get("url", ""),
              "evidence_date": best.get("evidence_date") or None, "evidence_type": best.get("source_type", "")}
    data = {f.name: values.get(f.name) or values.get(f.semantic.value) for f in spec.fields}
    record = ExtractedRecord(org_id=org_id, job_id=job_id, dedupe_key=f"company:{c.key}"[:512], data=data,
                             status="partial", quality_score=0.0, excluded=False,
                             source_urls=[u for u in (best.get("url"), c.website) if u])
    db.add(record)
    db.flush()
    return record


def is_proof_source(method: str) -> bool:
    return method in PROOF_SOURCES
