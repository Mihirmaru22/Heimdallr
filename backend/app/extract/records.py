"""Turn per-page candidates into one validated record: pick the best value per field, keep provenance."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from app.crawl.urlnorm import registered_domain
from app.extract.deterministic import Candidate
from app.extract.normalize import InvalidValue, normalize_value
from app.spec.models import ExtractionSpec, FieldSpec, FieldType, Semantic

CONTACT_HINTS = ("contact", "impressum", "imprint", "about", "kontakt", "legal")
PAGE_BONUS = {
    Semantic.contact_email: CONTACT_HINTS,
    Semantic.phone: CONTACT_HINTS,
    Semantic.address: CONTACT_HINTS,
    Semantic.headquarters: CONTACT_HINTS,
    Semantic.pricing: ("pricing", "plans", "price"),
}


@dataclass
class PageCandidates:
    page_id: Any
    url: str
    candidates: dict[str, list[Candidate]]


@dataclass
class FieldResult:
    name: str
    value: Any
    value_status: str  # found | absent | not_extracted | invalid
    method: str
    source_page_id: Any = None
    source_url: str | None = None
    evidence: str | None = None
    confidence: float | None = None
    error: str | None = None
    alternatives: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AssembledRecord:
    data: dict[str, Any]
    fields: list[FieldResult]
    status: str
    quality: float
    source_urls: list[str]


def _bonus(spec: FieldSpec, url: str) -> float:
    path = urlsplit(url).path.lower()
    if spec.semantic == Semantic.company_name and path in ("", "/"):
        return 0.05
    hints = PAGE_BONUS.get(spec.semantic)
    return 0.05 if hints and any(h in path for h in hints) else 0.0


def _has_extractor(spec: FieldSpec) -> bool:
    r = spec.rules
    return spec.semantic != Semantic.none or bool(r.css or r.meta or r.jsonld or r.regex or r.labels) \
        or spec.type in (FieldType.email, FieldType.phone)


def assemble_field(spec: FieldSpec, pages: list[PageCandidates]) -> FieldResult:
    scored: list[tuple[float, Any, Candidate, PageCandidates]] = []
    errors: list[str] = []
    for page in pages:
        for cand in page.candidates.get(spec.name, []):
            try:
                value = normalize_value(spec, cand.value)
            except InvalidValue as exc:
                errors.append(f"{cand.method}: {exc}")
                continue
            scored.append((cand.confidence + _bonus(spec, page.url), value, cand, page))
    if scored:
        scored.sort(key=lambda s: s[0], reverse=True)
        best_score, value, cand, page = scored[0]
        if spec.type == FieldType.list:
            merged: list[str] = []
            for _s, v, _c, _p in scored:
                for item in v:
                    if item not in merged:
                        merged.append(item)
            value = merged[:50]
        alternatives = []
        for _s, v, c, p in scored[1:6]:
            if v != value:
                alternatives.append({"value": v, "method": c.method, "source_url": p.url})
        return FieldResult(spec.name, value, "found", cand.method, page.page_id, page.url,
                           cand.evidence[:500], round(min(best_score, 1.0), 2), None, alternatives)
    if errors:
        return FieldResult(spec.name, None, "invalid", "validation", error="; ".join(errors[:3])[:500])
    if not _has_extractor(spec):
        return FieldResult(spec.name, None, "not_extracted", "none",
                           error="No deterministic rule for this field. Add a CSS selector, label or regex, "
                                 "or enable free-model extraction (phase 2).")
    return FieldResult(spec.name, None, "absent", "none",
                       error=f"Not found on the {len(pages)} page(s) examined.")


def assemble_record(spec: ExtractionSpec, pages: list[PageCandidates]) -> AssembledRecord:
    results = [assemble_field(f, pages) for f in spec.fields]
    data = {r.name: r.value for r in results}
    required = [f.name for f in spec.fields if f.required]
    found = {r.name for r in results if r.value_status == "found"}
    if required and not any(n in found for n in required):
        status = "invalid"
    elif all(n in found for n in required):
        status = "valid"
    else:
        status = "partial"
    quality = round(len(found) / max(len(spec.fields), 1), 3)
    sources = list(dict.fromkeys(r.source_url for r in results if r.source_url))
    return AssembledRecord(data, results, status, quality, sources)


def _key_part(spec: FieldSpec | None, value: Any) -> str:
    if value in (None, "", []):
        return ""
    if spec is not None and spec.type == FieldType.url:
        return registered_domain(str(value))
    if isinstance(value, list):
        value = ",".join(sorted(str(v) for v in value))
    text = str(value).casefold()
    text = re.sub(r"\b(inc|ltd|llc|gmbh|ag|sa|bv|plc|oy|ab|as|srl|sas|limited|corp|co)\b\.?", "", text)
    return re.sub(r"[^a-z0-9@.+]", "", text)


def dedupe_key(spec: ExtractionSpec, data: dict[str, Any], fallback: str) -> str:
    """Deterministic key: the configured dedupe fields, normalized; else the site or page."""
    by_name = {f.name: f for f in spec.fields}
    parts = [_key_part(by_name.get(k), data.get(k)) for k in spec.deduplication_keys]
    if parts and all(parts):
        return "|".join(parts)[:500]
    return f"src:{fallback}"[:500]
