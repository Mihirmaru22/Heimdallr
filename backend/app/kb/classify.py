"""Micro-sector and product-or-service labels from what a company's homepage says about itself.

A small multilingual sentence model (paraphrase-multilingual-MiniLM-L12-v2, run locally through
fastembed/ONNX: no API, no model budget) turns each homepage's title, description and opening
text into a vector, and compares it with vectors of short label descriptions:

- micro_sector: the closest of MICRO_SECTORS, but only when it is close enough (MIN_SCORE) and
  clearly ahead of the runner-up (MIN_MARGIN). Most companies are not in any micro-sector (a
  bakery, a law firm), and "none" is the honest answer for them;
- offering: product, service, or both, by the closest group of example sentences;
- sector_guess: the closest of our 20 sectors, for the companies PDL gave no industry.

Every row keeps the top three micro-sectors with their scores, so the thresholds can be tuned on
a hand-checked sample (kb-classify --export-sample) rather than guessed.
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
MIN_SCORE = 0.35
MIN_MARGIN = 0.02
TEXT_CHARS = 600  # the model reads about 128 tokens; the opening of the page carries the most

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

SECTORS: dict[str, str] = {
    "Technology": "software, internet, computers and information technology company",
    "Financial services": "bank, insurance, investment, accounting firm or financial services",
    "Healthcare and pharma": "hospital, clinic, doctors, pharmaceuticals, medical care and health",
    "Aerospace and defense": "aerospace, aviation manufacturing, defense and military",
    "Manufacturing and industrial": "factory, manufacturing, industrial machinery and engineering",
    "Automotive": "cars, vehicles, auto parts, car dealers and garages",
    "Energy and utilities": "energy, oil and gas, electricity, water and utilities",
    "Mining and materials": "mining, metals, chemicals, raw materials and building materials",
    "Retail and consumer goods": "shop, retail store, consumer products, fashion and cosmetics",
    "Food and agriculture": "farming, agriculture, food production, beverages and bakery",
    "Telecom": "telecommunications, mobile phone networks and internet providers",
    "Media and entertainment": "media, publishing, film, music, sports and entertainment",
    "Education": "school, university, training, courses and education",
    "Government and public sector": "government agency, municipality, public administration",
    "Transport and logistics": "transport, shipping, freight, logistics and airlines",
    "Real estate and construction": "real estate agency, property, construction company and architects",
    "Professional services": "consulting, law firm, marketing agency, recruitment and business services",
    "Hospitality and travel": "hotel, restaurant, travel agency, tourism and events",
    "Non-profit": "charity, non-profit organization, foundation, association and church",
    "Wholesale and trade": "wholesale distributor, import and export trading company",
}

OFFERINGS: dict[str, list[str]] = {
    "product": [
        "We make and sell our own products.",
        "Buy our products online. Add to cart. Shop now.",
        "Our software product is used by thousands of customers. Start your free trial.",
        "Manufacturer of equipment, machines and components.",
    ],
    "service": [
        "We provide professional services to our clients.",
        "Our team of consultants helps you. Contact us for a quote.",
        "Book an appointment with our experts.",
        "We offer consulting, installation, repair and maintenance services.",
    ],
}


class Embedder:
    """fastembed (ONNX) sentence model; the model is downloaded once and runs on the CPU."""

    def __init__(self, model: str = MODEL, cache_dir: str | None = None):
        from fastembed import TextEmbedding

        self.name = model
        self.model = TextEmbedding(model, cache_dir=cache_dir)

    def __call__(self, texts: Sequence[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self.model.embed(list(texts), batch_size=64)]


def _normalise(vectors: list[list[float]]) -> list[list[float]]:
    out = []
    for v in vectors:
        norm = sum(x * x for x in v) ** 0.5 or 1.0
        out.append([x / norm for x in v])
    return out


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def page_text(title: str | None, description: str | None, text: str | None) -> str:
    parts = [p.strip() for p in (title or "", description or "") if p and p.strip()]
    body = " ".join((text or "").split())[:TEXT_CHARS]
    return ". ".join(parts + ([body] if body else []))


@dataclass
class Label:
    domain: str
    micro_sector: str | None
    micro_score: float
    micro_top3: list[tuple[str, float]]
    offering: str
    offering_score: float
    sector_guess: str
    sector_score: float


class Classifier:
    def __init__(self, embed: Callable[[Sequence[str]], list[list[float]]],
                 min_score: float = MIN_SCORE, min_margin: float = MIN_MARGIN):
        self.embed = embed
        self.min_score, self.min_margin = min_score, min_margin
        self.micro_names = list(MICRO_SECTORS)
        self.micro = _normalise(embed(list(MICRO_SECTORS.values())))
        self.sector_names = list(SECTORS)
        self.sectors = _normalise(embed(list(SECTORS.values())))
        self.offer_names = []
        examples = []
        for name, sentences in OFFERINGS.items():
            self.offer_names += [name] * len(sentences)
            examples += sentences
        self.offers = _normalise(embed(examples))

    def label(self, domains: Sequence[str], texts: Sequence[str]) -> list[Label]:
        out = []
        for domain, vec in zip(domains, _normalise(self.embed(list(texts))), strict=True):
            micro = sorted(((n, _dot(vec, m)) for n, m in zip(self.micro_names, self.micro, strict=True)),
                           key=lambda x: -x[1])
            best, score = micro[0]
            margin = score - micro[1][1]
            chosen = best if score >= self.min_score and margin >= self.min_margin else None
            offer_scores: dict[str, float] = {}
            for name, o in zip(self.offer_names, self.offers, strict=True):
                offer_scores[name] = max(offer_scores.get(name, -1.0), _dot(vec, o))
            gap = offer_scores["product"] - offer_scores["service"]
            offering = "product" if gap > 0.03 else "service" if gap < -0.03 else "both"
            sector, sector_score = max(((n, _dot(vec, s)) for n, s in zip(self.sector_names, self.sectors,
                                                                          strict=True)), key=lambda x: x[1])
            out.append(Label(domain, chosen, round(score, 4), [(n, round(s, 4)) for n, s in micro[:3]],
                             offering, round(gap, 4), sector, round(sector_score, 4)))
        return out


@dataclass
class Summary:
    rows: int = 0
    micro: Counter = field(default_factory=Counter)
    offering: Counter = field(default_factory=Counter)

    def add(self, label: Label) -> None:
        self.rows += 1
        self.micro[label.micro_sector or "(none)"] += 1
        self.offering[label.offering] += 1

    def report(self) -> str:
        def pct(n: int) -> str:
            return f"{n:>8,}  {100 * n / self.rows:5.1f}%" if self.rows else f"{n:>8,}"

        lines = [f"Homepages labelled: {self.rows:,}", "", "Micro-sector:"]
        lines += [f"  {k:<28} {pct(n)}" for k, n in self.micro.most_common()]
        lines += ["", "Offering:"] + [f"  {k:<28} {pct(n)}" for k, n in self.offering.most_common()]
        return "\n".join(lines)


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS kb.company_label (
    domain text PRIMARY KEY,
    micro_sector text,
    micro_score real,
    micro_top3 jsonb,
    offering text,
    offering_score real,
    sector_guess text,
    sector_score real,
    model text NOT NULL,
    source_url text,
    labelled_at timestamptz NOT NULL DEFAULT now()
);
"""


def save(conn, label: Label, model: str, source_url: str | None) -> None:
    conn.execute(
        """INSERT INTO kb.company_label (domain, micro_sector, micro_score, micro_top3, offering, offering_score,
                                         sector_guess, sector_score, model, source_url, labelled_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
           ON CONFLICT (domain) DO UPDATE SET micro_sector = EXCLUDED.micro_sector,
               micro_score = EXCLUDED.micro_score, micro_top3 = EXCLUDED.micro_top3,
               offering = EXCLUDED.offering, offering_score = EXCLUDED.offering_score,
               sector_guess = EXCLUDED.sector_guess, sector_score = EXCLUDED.sector_score,
               model = EXCLUDED.model, source_url = EXCLUDED.source_url, labelled_at = now()""",
        (label.domain, label.micro_sector, label.micro_score, json.dumps(label.micro_top3), label.offering,
         label.offering_score, label.sector_guess, label.sector_score, model, source_url),
    )


def export_sample(conn, path: Path, size: int, seed: int = 7) -> int:
    """A random sample of labelled homepages with what the page says, for checking by hand."""
    has_pdl = conn.execute("SELECT to_regclass('kb.pdl_company')").fetchone()[0] is not None
    pdl_sector = ("(SELECT sector FROM kb.pdl_company c WHERE c.domain = l.domain ORDER BY c.sector IS NULL "
                  "LIMIT 1)") if has_pdl else "NULL"
    rows = conn.execute(
        f"""SELECT l.domain, h.url, h.title, h.description, left(h.text, 300), l.micro_sector, l.micro_score,
                   l.micro_top3, l.offering, l.sector_guess, {pdl_sector}
            FROM kb.company_label l JOIN kb.homepage h USING (domain)"""  # noqa: S608 - fixed text
    ).fetchall()
    random.Random(seed).shuffle(rows)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["domain", "url", "title", "description", "text_start", "micro_sector", "micro_score",
                    "micro_top3", "offering", "sector_guess", "pdl_sector", "correct_micro_sector",
                    "correct_offering"])
        for r in rows[:size]:
            w.writerow([*r[:7], json.dumps(r[7]), *r[8:], "", ""])
    return min(size, len(rows))
