"""Homepage labels: real page or not, tech company or not, micro-sector, product or service.

The labels come from a small classifier trained on teacher labels (app.kb.teach: an open model on
our own server reads a few thousand pages; app.kb.train fits the classifier). Each homepage's
title, description and opening text become a vector from a small multilingual sentence model
(paraphrase-multilingual-MiniLM-L12-v2, run locally through fastembed/ONNX: no API, no model
budget), and the trained heads turn that vector into labels with a probability each.

A first version compared the vectors with short label descriptions instead of training. A
hand check of 200 pages found it about 20% right: it measured topic, not what the company is
(an estate agent became "proptech", a law firm "legaltech"). So the descriptions below are now
only the list of micro-sectors the teacher picks from; nothing is decided by them directly.

micro_sector applies to tech companies only. For every other company PDL's industry (147
values such as "law practice" or "restaurants") is already the finer label.
"""

from __future__ import annotations

import csv
import json
import random
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
TEXT_CHARS = 600  # the model reads about 128 tokens; the opening of the page carries the most
MIN_PROBABILITY = 0.5  # below this a micro-sector is left empty ("tech, micro-sector unsure")

MICRO_SECTORS: dict[str, str] = {
    "fintech": "financial technology: digital banking, lending, money apps and software for finance",
    "payments": "payment processing, card terminals, online checkout and money transfer services",
    "insurtech": "insurance technology: digital insurance platforms and software for insurers",
    "regtech": "regulatory compliance software, anti-money-laundering and know-your-customer checks",
    "edtech": "education technology: online learning platforms, e-learning software and courses online",
    "healthtech": "digital health: telemedicine, health apps and software for clinics and hospitals",
    "medtech": "medical devices and medical equipment manufacturing and diagnostics technology",
    "biotech": "biotechnology: drug discovery, life sciences research, genetics and biologics",
    "cybersecurity": "cybersecurity: network security, threat detection, data protection and security software",
    "cloud and infrastructure": "cloud computing, hosting, data centres, servers and IT infrastructure services",
    "data and analytics": "data analytics, business intelligence, big data platforms and dashboards",
    "ai and machine learning": "artificial intelligence and machine learning products, models and automation",
    "developer tools": "software development tools, APIs, DevOps platforms and tools for programmers",
    "erp and business software": "ERP, accounting software, inventory and business management software",
    "crm and sales tech": "CRM software, sales automation and customer relationship management tools",
    "martech and adtech": "marketing technology, digital advertising platforms, SEO and email marketing software",
    "hr tech": "human resources software, payroll, recruiting platforms and workforce management",
    "legaltech": "legal technology: software for lawyers, contract management and e-signature",
    "proptech": "property technology: real estate platforms, property management software and listings",
    "construction tech": "construction technology: software and digital tools for building projects",
    "agritech": "agriculture technology: precision farming, agricultural drones and farm software",
    "foodtech": "food technology: food delivery platforms, alternative proteins and restaurant software",
    "cleantech and energy tech": "clean energy technology: solar, wind, batteries, EV charging and energy efficiency",
    "mobility tech": "mobility technology: ride sharing, electric vehicles, fleet and transport apps",
    "logistics tech": "logistics technology: shipping software, warehouse automation and supply chain platforms",
    "e-commerce": "online store and e-commerce marketplace selling goods on the internet",
    "gaming": "video games, game development studios and online gaming platforms",
    "media and streaming": "digital media, video and music streaming, podcasts and online publishing",
    "telecom tech": "telecommunications technology, mobile networks, internet service and 5G",
    "semiconductors": "semiconductors, microchips, integrated circuits and electronic components",
    "hardware and iot": "computer hardware, electronics, internet of things devices and sensors",
    "robotics": "robotics, industrial robots, drones and automation machines",
    "space and defense tech": "aerospace, defense technology, satellites and military systems",
    "govtech": "government technology: software and digital services for public sector agencies",
    "it services and consulting": "IT services, software development agency, IT consulting and outsourcing",
    "industrial software": "industrial software: CAD, PLM, manufacturing execution and engineering software",
}


class Embedder:
    """fastembed (ONNX) sentence model; the model is downloaded once and runs on the CPU."""

    def __init__(self, model: str = MODEL, cache_dir: str | None = None):
        from fastembed import TextEmbedding

        self.name = model
        self.model = TextEmbedding(model, cache_dir=cache_dir)

    def __call__(self, texts: Sequence[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self.model.embed(list(texts), batch_size=64)]


def page_text(title: str | None, description: str | None, text: str | None) -> str:
    parts = [p.strip() for p in (title or "", description or "") if p and p.strip()]
    body = " ".join((text or "").split())[:TEXT_CHARS]
    return ". ".join(parts + ([body] if body else []))


@dataclass
class Label:
    domain: str
    real_page: bool
    real_score: float
    tech_company: bool | None  # None when the page is not a real company page
    tech_score: float
    micro_sector: str | None
    micro_score: float
    micro_top3: list[tuple[str, float]]
    offering: str | None
    offering_score: float


class Classifier:
    """The trained heads (app.kb.train.LabelModel) applied to embedded homepages."""

    def __init__(self, embed: Callable[[Sequence[str]], list[list[float]]], model,
                 min_probability: float = MIN_PROBABILITY):
        self.embed, self.model, self.min_probability = embed, model, min_probability

    def label(self, domains: Sequence[str], texts: Sequence[str]) -> list[Label]:
        probs = self.model.predict(self.embed(list(texts)))
        out = []
        for i, domain in enumerate(domains):
            real = probs["real_page"][i].get("yes", 0.0)
            tech = probs["tech_company"][i].get("yes", 0.0)
            micro = sorted(probs["micro_sector"][i].items(), key=lambda x: -x[1])
            offer = max(probs["offering"][i].items(), key=lambda x: x[1])
            is_real, is_tech = real >= 0.5, real >= 0.5 and tech >= 0.5
            chosen = micro[0][0] if is_tech and micro and micro[0][1] >= self.min_probability else None
            out.append(Label(domain, is_real, round(real, 4), is_tech if is_real else None, round(tech, 4),
                             chosen, round(micro[0][1], 4) if micro else 0.0,
                             [(n, round(p, 4)) for n, p in micro[:3]],
                             offer[0] if is_real else None, round(offer[1], 4)))
        return out


@dataclass
class Summary:
    rows: int = 0
    real: int = 0
    tech: int = 0
    micro: Counter = field(default_factory=Counter)
    offering: Counter = field(default_factory=Counter)

    def add(self, label: Label) -> None:
        self.rows += 1
        self.real += label.real_page
        self.tech += bool(label.tech_company)
        if label.tech_company:
            self.micro[label.micro_sector or "(unsure)"] += 1
        if label.real_page:
            self.offering[label.offering] += 1

    def report(self) -> str:
        def pct(n: int, of: int) -> str:
            return f"{n:>8,}  {100 * n / of:5.1f}%" if of else f"{n:>8,}"

        lines = [f"Homepages labelled: {self.rows:,}",
                 f"Real company page:  {pct(self.real, self.rows)}",
                 f"Tech company:       {pct(self.tech, self.real)}  (of real pages)", "",
                 "Micro-sector (tech companies):"]
        lines += [f"  {k:<28} {pct(n, self.tech)}" for k, n in self.micro.most_common()]
        lines += ["", "Offering (real pages):"] + [f"  {k:<28} {pct(n, self.real)}"
                                                   for k, n in self.offering.most_common()]
        return "\n".join(lines)


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS kb.company_label (
    domain text PRIMARY KEY,
    micro_sector text,
    micro_score real,
    micro_top3 jsonb,
    offering text,
    offering_score real,
    model text NOT NULL,
    source_url text,
    labelled_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE kb.company_label ADD COLUMN IF NOT EXISTS real_page boolean;
ALTER TABLE kb.company_label ADD COLUMN IF NOT EXISTS real_score real;
ALTER TABLE kb.company_label ADD COLUMN IF NOT EXISTS tech_company boolean;
ALTER TABLE kb.company_label ADD COLUMN IF NOT EXISTS tech_score real;
"""


def save(conn, label: Label, model: str, source_url: str | None) -> None:
    conn.execute(
        """INSERT INTO kb.company_label (domain, real_page, real_score, tech_company, tech_score, micro_sector,
                                         micro_score, micro_top3, offering, offering_score, model, source_url,
                                         labelled_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
           ON CONFLICT (domain) DO UPDATE SET real_page = EXCLUDED.real_page, real_score = EXCLUDED.real_score,
               tech_company = EXCLUDED.tech_company, tech_score = EXCLUDED.tech_score,
               micro_sector = EXCLUDED.micro_sector, micro_score = EXCLUDED.micro_score,
               micro_top3 = EXCLUDED.micro_top3, offering = EXCLUDED.offering,
               offering_score = EXCLUDED.offering_score, model = EXCLUDED.model,
               source_url = EXCLUDED.source_url, labelled_at = now()""",
        (label.domain, label.real_page, label.real_score, label.tech_company, label.tech_score,
         label.micro_sector, label.micro_score, json.dumps(label.micro_top3), label.offering,
         label.offering_score, model, source_url),
    )


def export_sample(conn, path: Path, size: int, seed: int = 7) -> int:
    """A random sample of labelled homepages with what the page says, for checking by hand."""
    has_pdl = conn.execute("SELECT to_regclass('kb.pdl_company')").fetchone()[0] is not None
    pdl_industry = ("(SELECT industry FROM kb.pdl_company c WHERE c.domain = l.domain "
                    "ORDER BY c.industry IS NULL LIMIT 1)") if has_pdl else "NULL"
    rows = conn.execute(
        f"""SELECT l.domain, h.url, h.title, h.description, left(h.text, 300), l.real_page, l.tech_company,
                   l.micro_sector, l.micro_score, l.micro_top3, l.offering, {pdl_industry}
            FROM kb.company_label l JOIN kb.homepage h USING (domain)"""  # noqa: S608 - fixed text
    ).fetchall()
    random.Random(seed).shuffle(rows)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["domain", "url", "title", "description", "text_start", "real_page", "tech_company",
                    "micro_sector", "micro_score", "micro_top3", "offering", "pdl_industry"])
        for r in rows[:size]:
            w.writerow([*r[:9], json.dumps(r[9]), *r[10:]])
    return min(size, len(rows))
