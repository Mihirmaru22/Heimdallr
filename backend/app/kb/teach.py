"""Training labels for the homepage classifier, from an open model running on our own server.

Comparing a homepage with short label descriptions (the first kb-classify) measured topic, not
what the company is: an estate agent landed on "proptech", a law firm on "legaltech". A language
model reading the page can tell the two apart, but it is far too slow for millions of pages on a
CPU. So it labels a few thousand pages ("teacher" labels, kept in kb.teach_label with the model's
raw answer), and a small classifier learns from them (app.kb.train) and labels the rest quickly.

The model runs in Ollama on the same machine (http://localhost:11434): no API, no model budget.
Its answer is held to a JSON schema, so micro_sector is always one of MICRO_SECTORS or "none".
"""

from __future__ import annotations

import json
import random
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

from app.kb.classify import MICRO_SECTORS

OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5:7b"
PAGE_CHARS = 1500
OFFERINGS = ("product", "service", "both", "none")

PROMPT = """You label companies from their homepage. Read the page and answer in JSON.

real_page: false if this is not a working company website: a parked or for-sale domain, "coming soon",
  maintenance, a login wall or browser check, an empty or error page, or content unrelated to the
  company (for example gambling spam on a hacked site). Otherwise true.
tech_company: true only if the company's main business is selling technology: software or SaaS,
  apps, online platforms or marketplaces, IT services or software development, cloud or hosting,
  electronics, hardware, semiconductors, robotics. A law firm, estate agent, clinic, school, shop,
  restaurant, builder or marketing agency that simply has a website is false.
micro_sector: when tech_company is true, the one best fit from: {micro}. Otherwise "none".
offering: "product" if they mainly sell things they make or a software product, "service" if they
  mainly sell work done for clients, "both" if both matter, "none" if neither fits (a charity,
  church, school, club or public body).
reason: at most 15 words on what the company does.

Company name: {name}
LinkedIn industry (may be wrong): {industry}
Homepage URL: {url}
Homepage:
{page}"""


def schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "real_page": {"type": "boolean"},
            "tech_company": {"type": "boolean"},
            "micro_sector": {"type": "string", "enum": [*MICRO_SECTORS, "none"]},
            "offering": {"type": "string", "enum": list(OFFERINGS)},
            "reason": {"type": "string"},
        },
        "required": ["real_page", "tech_company", "micro_sector", "offering", "reason"],
    }


def page_for_model(title: str | None, description: str | None, text: str | None) -> str:
    lines = [p.strip() for p in (title or "", description or "") if p and p.strip()]
    body = " ".join((text or "").split())[:PAGE_CHARS]
    return "\n".join(lines + ([body] if body else []))


@dataclass
class TeachLabel:
    domain: str
    real_page: bool
    tech_company: bool
    micro_sector: str | None
    offering: str
    reason: str
    raw: str


def parse(domain: str, raw: str) -> TeachLabel:
    """The model's JSON answer, checked: anything outside the schema becomes an error, not a label."""
    data = json.loads(raw)
    micro = data.get("micro_sector")
    offering = data.get("offering")
    if not isinstance(data.get("real_page"), bool) or not isinstance(data.get("tech_company"), bool):
        raise ValueError("real_page and tech_company must be true or false")
    if micro not in MICRO_SECTORS and micro != "none":
        raise ValueError(f"unknown micro_sector {micro!r}")
    if offering not in OFFERINGS:
        raise ValueError(f"unknown offering {offering!r}")
    real, tech = data["real_page"], data["tech_company"] and data["real_page"]
    return TeachLabel(domain, real, tech, micro if tech and micro != "none" else None,
                      offering if real else "none", str(data.get("reason", ""))[:200], raw)


def ask(client, model: str, prompt: str) -> str:
    """One answer from Ollama, held to the schema; temperature 0 so a rerun gives the same answer."""
    r = client.post(f"{OLLAMA_URL}/api/chat", json={
        "model": model, "stream": False, "format": schema(),
        "messages": [{"role": "user", "content": prompt}],
        "options": {"temperature": 0, "num_ctx": 4096},
    })
    r.raise_for_status()
    return r.json()["message"]["content"]


def select_pages(conn, limit: int, tech_share: float = 0.5, seed: int = 7) -> list[tuple]:
    """Homepages not yet labelled: half from companies PDL files under Technology (tech companies
    are rare, and the classifier needs examples of every micro-sector), half from all the rest."""
    rows = conn.execute(
        """SELECT h.domain, h.url, h.title, h.description, h.text, p.name, p.industry, p.sector
           FROM kb.homepage h
           LEFT JOIN kb.teach_label t USING (domain)
           LEFT JOIN LATERAL (SELECT name, industry, sector FROM kb.pdl_company c WHERE c.domain = h.domain
                              ORDER BY c.sector IS NULL LIMIT 1) p ON true
           WHERE h.found AND t.domain IS NULL"""
    ).fetchall()
    rows = [r for r in rows if page_for_model(r[2], r[3], r[4])]
    rng = random.Random(seed)
    rng.shuffle(rows)
    tech = [r for r in rows if r[7] == "Technology"]
    rest = [r for r in rows if r[7] != "Technology"]
    want_tech = min(len(tech), int(limit * tech_share))
    picked = tech[:want_tech] + rest[:limit - want_tech]
    rng.shuffle(picked)
    return picked


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS kb.teach_label (
    domain text PRIMARY KEY,
    real_page boolean,
    tech_company boolean,
    micro_sector text,
    offering text,
    reason text,
    raw text,
    error text,
    model text NOT NULL,
    seconds real,
    labelled_at timestamptz NOT NULL DEFAULT now()
);
"""


def save(conn, domain: str, label: TeachLabel | None, model: str, seconds: float, error: str | None) -> None:
    values = (label.real_page, label.tech_company, label.micro_sector, label.offering, label.reason,
              label.raw) if label else (None,) * 6
    conn.execute(
        """INSERT INTO kb.teach_label (domain, real_page, tech_company, micro_sector, offering, reason, raw,
                                       error, model, seconds, labelled_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
           ON CONFLICT (domain) DO UPDATE SET real_page = EXCLUDED.real_page,
               tech_company = EXCLUDED.tech_company, micro_sector = EXCLUDED.micro_sector,
               offering = EXCLUDED.offering, reason = EXCLUDED.reason, raw = EXCLUDED.raw,
               error = EXCLUDED.error, model = EXCLUDED.model, seconds = EXCLUDED.seconds, labelled_at = now()""",
        (domain, *values, error, model, round(seconds, 2)),
    )


@dataclass
class Summary:
    rows: int = 0
    errors: Counter = field(default_factory=Counter)
    real: int = 0
    tech: int = 0
    micro: Counter = field(default_factory=Counter)
    offering: Counter = field(default_factory=Counter)
    seconds: float = 0.0

    def add(self, label: TeachLabel | None, seconds: float, error: str | None = None) -> None:
        self.rows += 1
        self.seconds += seconds
        if label is None:
            self.errors[error or "error"] += 1
            return
        self.real += label.real_page
        self.tech += label.tech_company
        if label.micro_sector:
            self.micro[label.micro_sector] += 1
        self.offering[label.offering] += 1

    def report(self) -> str:
        def pct(n: int, of: int) -> str:
            return f"{n:>7,}  {100 * n / of:5.1f}%" if of else f"{n:>7,}"

        lines = [f"Pages labelled:   {self.rows:,} ({self.seconds / max(1, self.rows):.1f} s per page)",
                 f"Real company page: {pct(self.real, self.rows)}",
                 f"Tech company:      {pct(self.tech, self.rows)}", "", "Micro-sector (tech companies):"]
        lines += [f"  {k:<28} {pct(n, self.tech)}" for k, n in self.micro.most_common()]
        lines += ["", "Offering:"] + [f"  {k:<28} {pct(n, self.rows)}" for k, n in self.offering.most_common()]
        if self.errors:
            lines += ["", "Errors:"] + [f"  {k}: {n:,}" for k, n in self.errors.most_common()]
        return "\n".join(lines)


def run(conn, client, model: str, rows: list[tuple], progress: Callable[[Summary], None] | None = None,
        clock: Callable[[], float] | None = None) -> Summary:
    import time

    clock = clock or time.monotonic
    summary = Summary()
    for domain, url, title, description, text, name, industry, _sector in rows:
        prompt = PROMPT.format(micro=", ".join(MICRO_SECTORS), name=name or domain, industry=industry or "unknown",
                               url=url or domain, page=page_for_model(title, description, text))
        started = clock()
        label, error = None, None
        try:
            label = parse(domain, ask(client, model, prompt))
        except Exception as exc:  # noqa: BLE001 - a bad answer fails its page only, and is recorded
            error = f"{type(exc).__name__}: {str(exc)[:120]}"
        seconds = clock() - started
        save(conn, domain, label, model, seconds, error)
        summary.add(label, seconds, error.split(":")[0] if error else None)
        if progress is not None:
            progress(summary)
    return summary


def export_sample(conn, path, size: int, seed: int = 7) -> int:
    """Teacher labels next to the page, for checking the teacher by hand before training on it."""
    import csv

    rows = conn.execute(
        """SELECT t.domain, h.url, h.title, h.description, left(h.text, 300), t.real_page, t.tech_company,
                  t.micro_sector, t.offering, t.reason
           FROM kb.teach_label t JOIN kb.homepage h USING (domain) WHERE t.error IS NULL"""
    ).fetchall()
    random.Random(seed).shuffle(rows)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["domain", "url", "title", "description", "text_start", "real_page", "tech_company",
                    "micro_sector", "offering", "reason"])
        w.writerows(rows[:size])
    return min(size, len(rows))
