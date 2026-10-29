"""Proof on the company's own website: pages the crawl already reads (careers, customers, news, technology)
that name the product. The page is the company speaking about itself, so a judged "uses" counts as first-party
proof. Rules and the free model tell a user from the product's maker, a reseller or a competitor, exactly as
for filings.
"""

from __future__ import annotations

import re
from datetime import date
from types import SimpleNamespace
from typing import Any

from app.evidence.fingerprints import Fingerprints, Rule, detect
from app.evidence.jobs import FetchJson, find_boards, read_board
from app.evidence.judge import KEEP, Judge, score
from app.evidence.products import Product, product_for
from app.evidence.quotes import find_mentions, verify_quote
from app.extract.deterministic import PageDoc
from app.spec.models import ExtractionSpec

SITE_STRENGTH = 0.8  # the company's own page: first-party, but often undated
FINGERPRINT_STRENGTH = 0.85  # the product's own code on the company's live site: seen today
MAX_FINGERPRINTED = 3  # pages per site whose code is checked; a product's scripts are usually on every page
JOB_STRENGTH = 0.75  # the company's own job ad: first-party and dated, but may describe a wish
MAX_JUDGED_JOBS = 2  # job ads naming the product sent to the judge per company
MAX_BOARDS = 2
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
    def __init__(self, spec: ExtractionSpec, judge: Judge | None = None,
                 fingerprints: Fingerprints | None = None) -> None:
        d = spec.discovery
        self.product: Product = product_for(d.technology or "", d.technology_aliases)
        self.judge = judge or Judge()
        self.judged: dict[str, int] = {}  # site -> pages sent to the judge
        self.proven: set[str] = set()  # sites with confirmed proof on their own pages
        self.has_proof: set[str] = set()  # sites with any kept proof, here or from their source
        self.hint_confirmed: set[str] = set()  # sites whose source brought confirmed proof
        self.pages_read: dict[str, int] = {}
        self.boards_read: set[str] = set()  # sites whose job boards were read
        self.board_notes: dict[str, str] = {}  # site -> what its job boards showed
        self.fingerprints = fingerprints or Fingerprints()
        self.rules: list[Rule] | None = None  # loaded on the first page
        self.fingerprinted: dict[str, int] = {}  # site -> pages whose code was checked

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
        return self._piece(who, site, j, doc.url, day, "Company website", SITE_STRENGTH)

    async def check_code(self, doc: PageDoc, headers: list[tuple[str, str]], site: str, company: str
                         ) -> dict[str, Any] | None:
        """Kept proof when the page's code carries the product's fingerprint, else None. No model call."""
        if self.rules is None:
            self.rules = await self.fingerprints.rules_for(self.product)
        if not self.rules or site in self.proven or self.fingerprinted.get(site, 0) >= MAX_FINGERPRINTED:
            return None
        self.fingerprinted[site] = self.fingerprinted.get(site, 0) + 1
        for rule in self.rules:
            seen = detect(rule, doc, headers)
            if seen:
                who = company or site
                j = SimpleNamespace(relationship="uses", quote=seen, judged_by=f"fingerprint:{rule.name}",
                                    reason=f"webappanalyzer's {rule.name} fingerprint matches the site's code")
                return self._piece(who, site, j, doc.url, date.today().isoformat(), "Website code",
                                   FINGERPRINT_STRENGTH)
        return None

    def _piece(self, who: str, site: str, j: Any, url: str, day: str, source_type: str, strength: float
               ) -> dict[str, Any]:
        verdict, strength = score(j.relationship, strength, day, one_reading=getattr(j, "one_reading", False))
        kept = j.relationship in KEEP and bool(verdict)
        if kept:
            self.has_proof.add(site)
        if kept and verdict == "Confirmed":
            self.proven.add(site)
        reason = j.reason if kept else (j.relationship.replace("_", " ") + (f": {j.reason}" if j.reason else ""))
        return {"company": who, "website": f"https://{site}/", "product": self.product.name, "quote": j.quote,
                "url": url, "evidence_date": day, "source_type": source_type, "relationship": j.relationship,
                "judged_by": j.judged_by, "strength": strength, "verdict": verdict, "kept": kept, "reason": reason}

    async def check_jobs(self, page_html: str, site: str, company: str, fetch_json: FetchJson,
                         say: Any = None) -> list[dict[str, Any]]:
        """Proof in the job ads of the boards this page links to (read once per company)."""
        if site in self.boards_read or site in self.proven:
            return []
        boards = find_boards(page_html)[:MAX_BOARDS]
        if not boards:
            return []
        self.boards_read.add(site)
        who = company or site
        pieces: list[dict[str, Any]] = []
        notes = []
        for board in boards:
            try:
                jobs = await read_board(board, fetch_json)
            except Exception as exc:  # noqa: BLE001 - a board that cannot be read is reported, not fatal
                notes.append(f"{board.label} could not be read ({type(exc).__name__}: {str(exc)[:80]})")
                if say:
                    say("failed", f"Could not read {who}'s {board.label}: {type(exc).__name__}")
                continue
            matching = [job for job in jobs if self.product.mentioned_in(job.text)]
            notes.append(f"{board.label}: {len(jobs)} open job(s), {len(matching)} naming {self.product.name}")
            if say:
                say("read", f"Read {len(jobs)} open job(s) on {who}'s {board.label}: {len(matching)} name "
                            f"{self.product.name}")
            for job in matching[:MAX_JUDGED_JOBS]:
                quotes = [q for q in find_mentions(job.text, self.product) if verify_quote(q, job.text)]
                if not quotes:
                    continue
                j = await self.judge.judge(who, self.product, quotes, f"job ad \"{job.title}\" on {who}'s "
                                                                      f"{board.ats} job board")
                piece = self._piece(who, site, j, job.url, job.date, f"Job ad ({board.ats})", JOB_STRENGTH)
                pieces.append(piece)
                if piece["kept"]:
                    break
            if site in self.has_proof:
                break
        self.board_notes[site] = "; ".join(notes)
        return pieces

    def without_proof(self, names: dict[str, str]) -> list[dict[str, Any]]:
        """A Rejected row for each company whose pages were read and none showed use, so nothing goes unseen."""
        out = []
        for site, n in sorted(self.pages_read.items()):
            if site in self.has_proof:
                continue
            judged = self.judged.get(site, 0)
            why = (f"{judged} of {n} page(s) read name {self.product.name}, none showing the company uses it"
                   if judged else f"none of the {n} page(s) read names {self.product.name}")
            why += f"; {self.board_notes[site]}" if site in self.board_notes else "; no job board linked from the site"
            out.append({"company": names.get(site, site), "website": f"https://{site}/", "product": self.product.name,
                        "url": f"https://{site}/", "source_type": "Company website", "kept": False, "reason": why})
        self.pages_read.clear()
        return out

    async def aclose(self) -> None:
        await self.judge.aclose()
