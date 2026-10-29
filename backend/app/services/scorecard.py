"""One scorecard per run, the same numbers every time, so changes are judged by what they move.

Read back from what the run stored (proof, pages, records), never from a re-crawl:
- funnel: how many companies each stage kept, and what each stage lost;
- record quality: proof quotes, websites, emails and phones of the included records;
- page budget: where the pages went, and which sites ran out of budget without a contact;
- with an answer key (a JSON file of companies that must and must not appear), recall and wrong rows.

`python -m app.cli score JOB [JOB ...] [--key FILE]` prints several runs side by side.
"""

from __future__ import annotations

import json
import re
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.crawl.urlnorm import registered_domain
from app.evidence.products import product_for
from app.extract.deterministic import NARROW_MAILBOX_RE, NOT_CONTACT_RE, PERSONAL_MAILBOX_RE, ROLE_WORD_RE
from app.extract.records import CONTACT_HINTS
from app.models import CrawlJob, DiscoveredUrl, Evidence, ExtractedRecord, ExtractionSchema, FetchedPage

NAME_NOISE = {"inc", "corp", "corporation", "co", "company", "companies", "holding", "holdings", "group", "ltd",
              "plc", "sa", "nv", "ag", "se", "llc", "lp", "the", "and", "of", "international", "de"}
SENTENCE_START = re.compile(r"^[\"“(]?[A-Z0-9•]")
SENTENCE_END = re.compile(r"[.!?][\"”)]?$")


def name_key(name: str) -> str:
    return "".join(w for w in re.findall(r"[a-z0-9]+", (name or "").lower()) if w not in NAME_NOISE)


def email_kind(email: str) -> str:
    local = email.split("@")[0].lower()
    if local in ("info", "contact", "hello", "sales", "office", "support", "enquiries", "inquiries"):
        return "main"
    if NOT_CONTACT_RE.search(local):
        return "not a contact"  # recruiting, legal, abuse...: the extractor should never have kept it
    if NARROW_MAILBOX_RE.match(local) or re.search(r"investor|^ir[._-]", local):
        return "narrow"
    if PERSONAL_MAILBOX_RE.match(local) and not ROLE_WORD_RE.search(local):
        return "personal"
    return "team" if ROLE_WORD_RE.search(local) else "unclear"


def _pct(n: int, d: int) -> str:
    return f"{n}/{d} ({round(100 * n / d)}%)" if d else "0/0"


def score_job(db, job_id: uuid.UUID, key: dict[str, Any] | None = None) -> dict[str, str]:
    """Metric name -> value, in reading order."""
    job = db.get(CrawlJob, job_id)
    spec = (db.get(ExtractionSchema, job.schema_id).spec or {})
    d = spec.get("discovery") or {}
    product = product_for(d["technology"], d.get("technology_aliases") or []) if d.get("technology") else None
    out: dict[str, str] = {}
    if job.finished_at:  # from the job's creation, so source searches before the crawl are counted
        out["time (s)"] = str(round((job.finished_at - (job.created_at or job.started_at)).total_seconds()))

    # --- funnel ---------------------------------------------------------------------------------------
    ev = db.execute(select(Evidence).where(Evidence.job_id == job_id)).scalars().all()
    if ev:
        out["proof: pieces looked at"] = str(len(ev))
        lost = Counter(_loss(e.reason, e.relationship) for e in ev if not e.kept)
        for reason, n in lost.most_common():
            out[f"proof lost: {reason}"] = str(n)
        kept_companies = {name_key(e.company) for e in ev if e.kept}
        with_site = {name_key(e.company) for e in ev if e.kept and e.website}
        out["proof: companies kept"] = str(len(kept_companies))
        out["proof: kept, with a website"] = _pct(len(with_site), len(kept_companies))

    urls = db.execute(select(DiscoveredUrl.host, DiscoveredUrl.url, DiscoveredUrl.depth, DiscoveredUrl.status,
                             DiscoveredUrl.status_reason, DiscoveredUrl.method).where(
        DiscoveredUrl.job_id == job_id)).all()
    seeds = {registered_domain(u.url) for u in urls if u.depth == 0}
    # A page read only to check a dropped site's country does not make the site read.
    fetched_sites = {registered_domain(u.url) for u in urls if u.status == "fetched" and u.method != "country_check"}
    out["sites queued"] = str(len(seeds))
    out["sites read (1+ page)"] = _pct(len(seeds & fetched_sites), len(seeds))
    unread = Counter((u.status_reason or u.status)[:60] for u in urls
                     if u.depth == 0 and registered_domain(u.url) not in fetched_sites)
    for reason, n in unread.most_common(5):
        out[f"site unread: {reason}"] = str(n)

    recs = db.execute(select(ExtractedRecord).where(ExtractedRecord.job_id == job_id)).scalars().all()
    included = [r for r in recs if not r.excluded]
    out["records"] = str(len(recs))
    out["records included"] = str(len(included))

    # --- record quality --------------------------------------------------------------------------------
    n = len(included)
    emails = [str(r.data.get("contact_email") or "") for r in included]
    phones = [r.data.get("phone") for r in included]
    asked = {f.get("semantic") or f.get("name") for f in spec.get("fields", [])}
    na = "n/a (not asked for)"
    out["included: email"] = _pct(sum(bool(e) for e in emails), n) if "contact_email" in asked else na
    out["included: phone"] = _pct(sum(bool(p) for p in phones), n) if "phone" in asked else na
    out["included: email or phone"] = _pct(sum(bool(e) or bool(p) for e, p in zip(emails, phones, strict=True)), n)
    out["included: neither"] = _pct(sum(not e and not p for e, p in zip(emails, phones, strict=True)), n)
    kinds = Counter(email_kind(e) for e in emails if e)
    out["emails by kind"] = ", ".join(f"{k} {v}" for k, v in kinds.most_common()) or "-"
    if product is not None:
        quotes = [str(r.data.get("evidence") or "") for r in included]
        out["quote names the product"] = _pct(sum(product.mentioned_in(q) for q in quotes), n)
        out["quote starts a sentence"] = _pct(sum(bool(SENTENCE_START.match(q)) for q in quotes), n)
        out["quote ends a sentence"] = _pct(sum(bool(SENTENCE_END.search(q.strip())) for q in quotes), n)
        out["verdicts"] = ", ".join(f"{k} {v}" for k, v in Counter(
            str(r.data.get("uses_technology") or "-") for r in included).most_common())

    # --- page budget -----------------------------------------------------------------------------------
    pages = db.execute(select(FetchedPage.final_url, FetchedPage.candidates).where(
        FetchedPage.job_id == job_id)).all()
    out["pages read"] = str(len(pages))
    if included:
        out["pages per included record"] = str(round(len(pages) / len(included), 1))
    contact_pages = sum(any(h in p.final_url.lower() for h in CONTACT_HINTS) for p in pages)
    out["pages that are contact/about"] = _pct(contact_pages, len(pages))
    per_site: dict[str, dict[str, Any]] = {}
    for p in pages:
        s = per_site.setdefault(registered_domain(p.final_url), {"pages": 0, "contact_page": False})
        s["pages"] += 1
        s["contact_page"] |= any(h in p.final_url.lower() for h in CONTACT_HINTS)
    no_contact_read = [site for site, s in per_site.items() if not s["contact_page"]]
    out["sites where no contact page was read"] = _pct(len(no_contact_read), len(per_site))
    budget = int((spec.get("crawl") or {}).get("max_pages_per_site") or 0)
    if budget:
        hit = [site for site, s in per_site.items() if s["pages"] >= budget]
        out["sites that used the whole page budget"] = _pct(len(hit), len(per_site))

    # --- model calls -----------------------------------------------------------------------------------
    from app.services.common import model_call_lines

    out.update(dict(model_call_lines(job)))

    # --- answer key ------------------------------------------------------------------------------------
    if key:
        out.update(_against_key(included, key))
        out.update(_where_lost(db, job_id, recs, ev, key, out))
    return out


def _loss(reason: str, relationship: str) -> str:
    r = (reason or "").lower()
    if "outside the us" in r:
        return "outside the requested country"
    if "not found in the document" in r:
        return "product not named in the document"
    if "none of the" in r and "page" in r:
        return "no page of the site names it"
    if "could not be fetched" in r:
        return "document could not be fetched"
    if relationship:
        return relationship.replace("_", " ")
    return r.split(":")[0][:50] or "other"


def _match(rec: ExtractedRecord, entry: dict[str, Any]) -> bool:
    site = registered_domain(str(rec.data.get("website_url") or "")) if rec.data.get("website_url") else ""
    if entry.get("website") and site and registered_domain(entry["website"]) == site:
        return True
    want = name_key(entry.get("company", ""))
    have = name_key(str(rec.data.get("company_name") or ""))
    return bool(want and have and (want in have or have in want))


def _against_key(included: list[ExtractedRecord], key: dict[str, Any]) -> dict[str, str]:
    must = key.get("must_include") or []
    must_not = key.get("must_exclude") or []
    found = [(e, next((r for r in included if _match(r, e)), None)) for e in must]
    hits = [(e, r) for e, r in found if r is not None]
    out = {"key: must-have companies found": _pct(len(hits), len(must)),
           "key: missing": ", ".join(e["company"] for e, r in found if r is None) or "-"}
    wrong = [r for r in included if any(_match(r, e) for e in must_not)]
    out["key: rows that must not be there"] = str(len(wrong))
    with_site = [(e, r) for e, r in hits if e.get("website")]
    right_site = sum(registered_domain(str(r.data.get("website_url") or "")) == registered_domain(e["website"])
                     for e, r in with_site)
    out["key: website correct"] = _pct(right_site, len(with_site))
    return out


def _same(entry: dict[str, Any], name: str, url: str) -> bool:
    if entry.get("website") and url and registered_domain(entry["website"]) == registered_domain(url):
        return True
    want, have = name_key(entry.get("company", "")), name_key(name)
    return bool(want and have and (want in have or have in want))


def _where_lost(db, job_id: uuid.UUID, recs: list[ExtractedRecord], ev: list[Evidence], key: dict[str, Any],
                out: dict[str, str]) -> dict[str, str]:
    """For every must-have company that is missing, the stage that lost it, so losses can be counted by stage
    across questions: never found by a source, found but its site not read (and why), read but excluded, or
    its proof rejected."""
    missing = [e for e in key.get("must_include") or [] if e["company"] in out.get("key: missing", "").split(", ")]
    seeds = db.execute(select(DiscoveredUrl.url, DiscoveredUrl.method, DiscoveredUrl.status,
                              DiscoveredUrl.status_reason, DiscoveredUrl.hint).where(
        DiscoveredUrl.job_id == job_id, DiscoveredUrl.depth == 0)).all()
    stages: dict[str, str] = {}
    for e in missing:
        rec = next((r for r in recs if _same(e, str(r.data.get("company_name") or ""),
                                             str(r.data.get("website_url") or ""))), None)
        proof = [x for x in ev if _same(e, x.company, x.website)]
        seed = next((u for u in seeds if _same(e, str((u.hint or {}).get("company_name") or ""), u.url)), None)
        if rec is not None:
            stage = "read, but left out (no confirmed proof)" if rec.excluded else "found under another name"
        elif proof and not any(x.kept for x in proof):
            stage = f"proof rejected: {_loss(proof[0].reason, proof[0].relationship)}"
        elif proof and not any(x.website for x in proof if x.kept):
            stage = "proof kept, no website known"
        elif seed is not None:
            stage = f"found by {seed.method}, site not read: {(seed.status_reason or seed.status)[:70]}"
        else:
            stage = "not found by any source"
        stages[e["company"]] = stage
    rows = {f"key: lost at: {stage}": [] for stage in stages.values()}
    for company, stage in stages.items():
        rows[f"key: lost at: {stage}"].append(company)
    return {k: f"{len(v)} ({', '.join(v)})" for k, v in rows.items()}


def load_key(path: str | None) -> dict[str, Any] | None:
    return json.loads(Path(path).read_text()) if path else None
