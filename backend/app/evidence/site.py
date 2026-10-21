"""Proof on the company's own website: pages the crawl already reads (careers, customers, news, technology)
that name the product. The page is the company speaking about itself, so a judged "uses" counts as first-party
proof. Rules and the free model tell a user from the product's maker, a reseller or a competitor, exactly as
for filings.
"""

from __future__ import annotations

import re
from typing import Any

from app.evidence.judge import KEEP, Judge, score
from app.evidence.products import Product, product_for
from app.evidence.quotes import find_mentions, verify_quote
from app.extract.deterministic import PageDoc
from app.spec.models import ExtractionSpec

SITE_STRENGTH = 0.8  # the company's own page: first-party, but often undated
MAX_JUDGED_PER_SITE = 3  # pages per site sent to the judge; a site rarely needs more
DATE_META = ("article:published_time", "article:modified_time", "og:updated_time", "date", "dc.date",
             "datepublished")
DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
# Pages where words about the company's own systems are likely (read first by the crawl).
PROOF_PAGES = ["career", "jobs", "customer", "case-stud", "success", "technolog", "digital", "engineering",
               "news", "press", "partner"]


def page_date(doc: PageDoc) -> str:
    """The page's own publication date (meta tags, then JSON-LD), as YYYY-MM-DD, or "" when it has none."""
    for key in DATE_META:
        m = DATE_RE.match(doc.meta.get(key, "") or "")
        if m:
            return m.group(1)
    for item in doc.jsonld:
        for key in ("datePublished", "dateModified", "uploadDate"):
            value = item.get(key) if isinstance(item, dict) else None
            m = DATE_RE.match(value) if isinstance(value, str) else None
            if m:
                return m.group(1)
    return ""


class SiteProof:
    def __init__(self, spec: ExtractionSpec, judge: Judge | None = None) -> None:
        d = spec.discovery
        self.product: Product = product_for(d.technology or "", d.technology_aliases)
        self.judge = judge or Judge()
        self.judged: dict[str, int] = {}  # site -> pages sent to the judge
        self.proven: set[str] = set()  # sites with confirmed proof on their own pages
        self.has_proof: set[str] = set()  # sites with any kept proof, here or from their source
        self.pages_read: dict[str, int] = {}

    async def check(self, doc: PageDoc, site: str, company: str) -> dict[str, Any] | None:
        """One piece of proof (kept or rejected) for a page that names the product, else None."""
        self.pages_read[site] = self.pages_read.get(site, 0) + 1
        if site in self.proven or self.judged.get(site, 0) >= MAX_JUDGED_PER_SITE:
            return None
        if not self.product.mentioned_in(doc.text):
            return None
        quotes = [q for q in find_mentions(doc.text, self.product) if verify_quote(q, doc.text)]
        if not quotes:
            return None
        self.judged[site] = self.judged.get(site, 0) + 1
        day = page_date(doc)
        who = company or site
        j = await self.judge.judge(who, self.product, quotes, f"{site}'s own website, page {doc.url}")
        verdict, strength = score(j.relationship, SITE_STRENGTH, day)
        kept = j.relationship in KEEP and bool(verdict)
        if kept:
            self.has_proof.add(site)
        if kept and verdict == "Confirmed":
            self.proven.add(site)
        reason = j.reason if kept else (j.relationship.replace("_", " ") + (f": {j.reason}" if j.reason else ""))
        return {"company": who, "website": f"https://{site}/", "product": self.product.name, "quote": j.quote,
                "url": doc.url, "evidence_date": day, "source_type": "Company website",
                "relationship": j.relationship, "judged_by": j.judged_by, "strength": strength,
                "verdict": verdict, "kept": kept, "reason": reason}

    def without_proof(self, names: dict[str, str]) -> list[dict[str, Any]]:
        """A Rejected row for each company whose pages were read and none showed use, so nothing goes unseen."""
        out = []
        for site, n in sorted(self.pages_read.items()):
            if site in self.has_proof:
                continue
            judged = self.judged.get(site, 0)
            why = (f"{judged} of {n} page(s) read name {self.product.name}, none showing the company uses it"
                   if judged else f"none of the {n} page(s) read names {self.product.name}")
            out.append({"company": names.get(site, site), "website": f"https://{site}/", "product": self.product.name,
                        "url": f"https://{site}/", "source_type": "Company website", "kept": False, "reason": why})
        self.pages_read.clear()
        return out

    async def aclose(self) -> None:
        await self.judge.aclose()
