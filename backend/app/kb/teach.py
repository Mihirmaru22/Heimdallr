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
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

from app.kb.classify import MICRO_SECTORS

OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5:7b"
PAGE_CHARS = 1500
TAIL_CHARS = 600  # the end of the stored text, where footers put the address and contact details
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
    text = raw.strip()
    if text.startswith("```"):  # some models wrap the JSON in a markdown fence
        text = text.strip("`").removeprefix("json").strip()
    data = json.loads(text)
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
    """One answer from Ollama, held to the schema; temperature 0 so a rerun gives the same answer.

    Thinking is switched off: a reasoning model would otherwise spend hundreds of tokens (minutes on
    a CPU) before the JSON. A model that does not think rejects the switch, so it is sent once
    and dropped if refused."""
    body = {
        "model": model, "stream": False, "format": schema(), "think": False,
        "messages": [{"role": "user", "content": prompt}],
        "options": {"temperature": 0, "num_ctx": 4096},
    }
    r = client.post(f"{OLLAMA_URL}/api/chat", json=body)
    if r.status_code == 400 and "think" in r.text:
        body.pop("think")
        r = client.post(f"{OLLAMA_URL}/api/chat", json=body)
    r.raise_for_status()
    return r.json()["message"]["content"]


def select_pages(conn, limit: int, model: str, same_as: str | None = None, tech_share: float = 0.5,
                 seed: int = 7, uncertain: bool = False, biggest_first: bool = False,
                 countries: str | None = None) -> list[tuple]:
    """Homepages this model has not labelled yet: half from companies PDL files under Technology
    (tech companies are rare, and the classifier needs examples of every micro-sector), half from
    the rest. With same_as, only pages that model labelled, so two models are compared on the
    same pages.

    With uncertain, the pages the trained classifier (kb.company_label) is least sure about come
    first, taken in turn from two lists: pages nearest the real/not-real or tech/not-tech line, and
    tech pages whose micro-sector it left unsure. Labelling those teaches it most per page; random
    pages mostly repeat what it already gets right.

    With biggest_first, the largest companies (PDL size band) come first, in that order, optionally
    only in `countries` ("GB,IN,US"): for a teacher that labels the companies that matter most
    directly, not only as examples."""
    has_labels = uncertain and conn.execute("SELECT to_regclass('kb.company_label')").fetchone()[0] is not None
    doubt = ("l.real_score, l.tech_score, l.tech_company, l.micro_sector" if has_labels
             else "NULL::real, NULL::real, NULL::boolean, NULL::text")
    join = "LEFT JOIN kb.company_label l ON l.domain = h.domain" if has_labels else ""
    rows = conn.execute(
        f"""SELECT h.domain, h.url, h.title, h.description, h.text, p.name, p.industry, p.sector, {doubt},
                  p.size, p.iso2
           FROM kb.homepage h
           LEFT JOIN LATERAL (SELECT name, industry, sector, size, iso2 FROM kb.pdl_company c WHERE c.domain = h.domain
                              ORDER BY c.sector IS NULL LIMIT 1) p ON true
           {join}
           WHERE h.found
             AND NOT EXISTS (SELECT 1 FROM kb.teach_label t WHERE t.domain = h.domain AND t.model = %s)
             AND (%s::text IS NULL OR EXISTS (SELECT 1 FROM kb.teach_label t WHERE t.domain = h.domain
                                                AND t.model = %s AND t.error IS NULL))""",  # noqa: S608 - fixed text
        (model, same_as, same_as),
    ).fetchall()
    rows = [r for r in rows if page_for_model(r[2], r[3], r[4])]
    if biggest_first:
        wanted = {c.strip().upper() for c in (countries or "").split(",") if c.strip()}
        rows = [r for r in rows if not wanted or (r[13] or "").upper() in wanted]
        rows.sort(key=lambda r: (-size_rank(r[12]), r[0]))
        return [r[:8] for r in rows[:limit]]
    rng = random.Random(seed)
    rng.shuffle(rows)
    if has_labels:
        picked = _most_uncertain(rows, limit)
    else:
        tech = [r for r in rows if r[7] == "Technology"]
        rest = [r for r in rows if r[7] != "Technology"]
        want_tech = min(len(tech), int(limit * tech_share))
        picked = tech[:want_tech] + rest[:limit - want_tech]
    rng.shuffle(picked)
    return [r[:8] for r in picked]


def size_rank(size: str | None) -> int:
    """PDL's size band ("1-10", "10001+") as its lower bound; 0 when unknown."""
    digits = re.match(r"\s*(\d+)", size or "")
    return int(digits.group(1)) if digits else 0


def _most_uncertain(rows: list[tuple], limit: int) -> list[tuple]:
    """rows end with (real_score, tech_score, tech_company, micro_sector) from the classifier."""
    def margin(r) -> float:  # 0 = exactly on a decision line, 0.5 = sure
        real, tech = r[8], r[9]
        if real is None:
            return 0.0  # never classified: as unknown as a page can be
        return min(abs(real - 0.5), abs(tech - 0.5) if real >= 0.5 and tech is not None else 0.5)

    no_micro = [r for r in rows if r[10] and not r[11]]
    seen = {r[0] for r in no_micro}
    borderline = sorted((r for r in rows if r[0] not in seen), key=margin)
    picked: list[tuple] = []
    for a, b in zip(no_micro, borderline, strict=False):
        picked += [a, b]
    longer = no_micro if len(no_micro) > len(borderline) else borderline
    picked += longer[min(len(no_micro), len(borderline)):]
    return picked[:limit]


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS kb.teach_label (
    domain text NOT NULL,
    real_page boolean,
    tech_company boolean,
    micro_sector text,
    offering text,
    reason text,
    raw text,
    error text,
    model text NOT NULL,
    seconds real,
    labelled_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (domain, model)
);
DO $$ BEGIN  -- one row per page and model (it was one per page), so models can be compared
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'teach_label_pkey'
             AND array_length(conkey, 1) = 1) THEN
    ALTER TABLE kb.teach_label DROP CONSTRAINT teach_label_pkey;
    ALTER TABLE kb.teach_label ADD PRIMARY KEY (domain, model);
  END IF;
END $$;
ALTER TABLE kb.teach_label ADD COLUMN IF NOT EXISTS sector text;
ALTER TABLE kb.teach_label ADD COLUMN IF NOT EXISTS niche text;
ALTER TABLE kb.teach_label ADD COLUMN IF NOT EXISTS offers text;
ALTER TABLE kb.teach_label ADD COLUMN IF NOT EXISTS address text;
ALTER TABLE kb.teach_label ADD COLUMN IF NOT EXISTS people text;
"""

# The profile a teacher can add beyond the four labels (Claude does, when it labels companies directly):
# sector (one of SECTORS, the same 20 our PDL industry mapping uses), niche (what kind of company, in a
# few words: the finer label for companies that are not tech), offers (its main products if it sells
# products, else its main services), the postal address when the page shows one, and people: the
# leaders or team members the page names, with their role ("Jane Doe (CEO); ..."). People are personal
# data, kept by Ronak's decision of 2026-11-25 in their own column so that one DROP COLUMN (here and in
# kb.company_label) removes them if that is ever required.
PROFILE_FIELDS = ("sector", "niche", "offers", "address", "people")


def _sectors() -> frozenset[str]:
    import csv
    from pathlib import Path

    with open(Path(__file__).parent / "data" / "pdl_industry_sector.csv", newline="", encoding="utf-8") as f:
        return frozenset(r["sector"] for r in csv.DictReader(f) if r["sector"])


SECTORS = _sectors()


def save_profile(conn, domain: str, model: str, profile: dict[str, str]) -> None:
    """Profile fields for a label already saved; an empty field or "-" is stored as unknown, and a
    sector outside SECTORS is dropped rather than stored."""
    clean = {k: (profile.get(k) or "").strip()[:300] for k in PROFILE_FIELDS}
    clean = {k: (None if v in ("", "-", "none") else v) for k, v in clean.items()}
    if clean["sector"] not in SECTORS:
        clean["sector"] = None
    conn.execute("UPDATE kb.teach_label SET sector = %s, niche = %s, offers = %s, address = %s, people = %s "
                 "WHERE domain = %s AND model = %s",
                 (clean["sector"], clean["niche"], clean["offers"], clean["address"], clean["people"], domain, model))


def save(conn, domain: str, label: TeachLabel | None, model: str, seconds: float, error: str | None) -> None:
    values = (label.real_page, label.tech_company, label.micro_sector, label.offering, label.reason,
              label.raw) if label else (None,) * 6
    conn.execute(
        """INSERT INTO kb.teach_label (domain, real_page, tech_company, micro_sector, offering, reason, raw,
                                       error, model, seconds, labelled_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
           ON CONFLICT (domain, model) DO UPDATE SET real_page = EXCLUDED.real_page,
               tech_company = EXCLUDED.tech_company, micro_sector = EXCLUDED.micro_sector,
               offering = EXCLUDED.offering, reason = EXCLUDED.reason, raw = EXCLUDED.raw,
               error = EXCLUDED.error, seconds = EXCLUDED.seconds, labelled_at = now()""",
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
    """Teacher labels next to the page, for checking the teacher by hand before training on it.
    A sampled page carries one row per model that labelled it, so models can be compared."""
    import csv

    rows = conn.execute(
        """SELECT t.domain, t.model, h.url, h.title, h.description, left(h.text, 300), t.real_page,
                  t.tech_company, t.micro_sector, t.offering, t.reason, t.error, t.seconds
           FROM kb.teach_label t JOIN kb.homepage h USING (domain) ORDER BY t.domain, t.model"""
    ).fetchall()
    domains = sorted({r[0] for r in rows})
    random.Random(seed).shuffle(domains)
    keep = set(domains[:size])
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["domain", "model", "url", "title", "description", "text_start", "real_page", "tech_company",
                    "micro_sector", "offering", "reason", "error", "seconds"])
        w.writerows(r for r in rows if r[0] in keep)
    return len(keep)


def export_pages(conn, path, limit: int, model: str, tech_share: float = 0.5, uncertain: bool = False,
                 biggest_first: bool = False, countries: str | None = None) -> int:
    """Pages for a teacher outside Ollama (a person, or Claude in the project thread): what the
    model would be shown, with empty answer columns to fill. import_labels reads it back."""
    import csv

    rows = select_pages(conn, limit, model, tech_share=tech_share, uncertain=uncertain,
                        biggest_first=biggest_first, countries=countries)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["domain", "name", "linkedin_industry", "url", "page", "tail", "real_page", "tech_company",
                    "micro_sector", "offering", "reason"])
        for domain, url, title, description, text, name, industry, _sector in rows:
            flat = " ".join((text or "").split())
            tail = flat[-TAIL_CHARS:] if len(flat) > PAGE_CHARS + TAIL_CHARS else flat[PAGE_CHARS:]
            w.writerow([domain, name or "", industry or "", url or "", page_for_model(title, description, text),
                        tail, "", "", "", "", ""])
    return len(rows)


def _bool(value: str) -> bool:
    v = value.strip().lower()
    if v in ("true", "yes", "1", "y", "t"):
        return True
    if v in ("false", "no", "0", "n", "f"):
        return False
    raise ValueError(f"not true or false: {value!r}")


def import_labels(conn, path, model: str) -> Summary:
    """Labels filled into an export_pages file (or any CSV with those columns), checked by the
    same rules as a model's answer; a row that breaks them is saved as an error, not a label."""
    import csv

    summary = Summary()
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not (row.get("real_page") or "").strip():
                continue  # not filled in yet
            domain = row["domain"].strip()
            label, error = None, None
            try:
                answer = {"real_page": _bool(row["real_page"]),
                          "tech_company": _bool(row.get("tech_company") or "false"),
                          "micro_sector": (row.get("micro_sector") or "none").strip() or "none",
                          "offering": (row.get("offering") or "none").strip() or "none",
                          "reason": (row.get("reason") or "").strip()}
                label = parse(domain, json.dumps(answer))
            except (ValueError, KeyError) as exc:
                error = f"{type(exc).__name__}: {str(exc)[:120]}"
            save(conn, domain, label, model, 0.0, error)
            if label and any(row.get(k) for k in PROFILE_FIELDS):
                save_profile(conn, domain, model, row)
            summary.add(label, 0.0, error.split(":")[0] if error else None)
    return summary
