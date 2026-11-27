"""Review-only enrichment from a bounded Overture Places GeoJSON/GeoJSONSeq extract."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crawl.urlnorm import registered_domain
from app.db import utcnow
from app.models import CatalogCompany
from app.services.catalog_store import ingest_source_claim

PLACES_GUIDE = "https://docs.overturemaps.org/guides/places/"
LICENSE = ("Overture Places: source-dependent license (CDLA Permissive 2.0 or Apache 2.0); retain per-source "
           "attribution. See https://docs.overturemaps.org/attribution/ and the Places guide.")
SOURCE_LICENSES = {
    "meta": "CDLA-Permissive-2.0", "microsoft": "CDLA-Permissive-2.0", "pinmeto": "CDLA-Permissive-2.0",
    "krick": "CDLA-Permissive-2.0", "renderseo": "CDLA-Permissive-2.0", "dac": "CDLA-Permissive-2.0",
    "brightquery": "CDLA-Permissive-2.0", "birdeye": "CDLA-Permissive-2.0", "uberall": "CDLA-Permissive-2.0",
    "opentravel": "CDLA-Permissive-2.0", "foursquare": "Apache-2.0", "alltheplaces": "CC0-1.0",
}


def download_command(bbox: tuple[float, float, float, float], output_path: Path) -> list[str]:
    """Build the official CLI command; bbox order is west,south,east,north, never world-wide by default."""
    west, south, east, north = bbox
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("Bounding box must be west,south,east,north geographic coordinates")
    return ["overturemaps", "download", f"--bbox={west},{south},{east},{north}",
            "--type=place", "-f", "geojson", "-o", str(output_path)]


def ingest_extract(db: Session, org_id, path: Path, *, bbox: tuple[float, float, float, float],
                   release: str = "latest", retrieved_at: datetime | None = None) -> dict[str, int]:
    """Import a regional Overture extract against exact catalog identities, keeping every match reviewable."""
    download_command(bbox, path)  # validate caller-provided bounded extract context
    records = list(_read_features(path))
    companies = db.execute(select(CatalogCompany).where(CatalogCompany.org_id == org_id)).scalars().all()
    by_name: dict[str, list[CatalogCompany]] = {}
    for company in companies:
        by_name.setdefault(_norm(company.name), []).append(company)

    seen: set[str] = set()
    matched_companies: set[str] = set()
    claim_count = 0
    fetched = retrieved_at or utcnow()
    for raw in records:
        props = raw.get("properties") if isinstance(raw.get("properties"), dict) else raw
        name = _primary_name(props.get("names")) or str(props.get("name") or "")
        candidates = by_name.get(_norm(name), []) if name else []
        place_website = _first_text(props.get("websites")) or _first_text(props.get("website"))
        place_domain = registered_domain(str(place_website)) if place_website else ""
        if place_domain:
            domain_candidates = [c for c in candidates if c.domain and c.domain.casefold() == place_domain.casefold()]
            if domain_candidates:
                candidates = domain_candidates
            else:
                continue  # exact name but contradictory site: leave for a separate identity-resolution workflow
        if len(candidates) != 1:
            continue
        company = candidates[0]
        gers_id = str(props.get("id") or raw.get("id") or "")
        if gers_id and gers_id in seen:
            continue
        if gers_id:
            seen.add(gers_id)
        addresses = props.get("addresses") or props.get("address") or []
        address = addresses[0] if isinstance(addresses, list) and addresses else addresses
        geometry = raw.get("geometry") or {}
        point = geometry.get("coordinates") if isinstance(geometry, dict) else None
        value = {
            "place_name": name,
            "address": address,
            "website": place_website,
            "phone": _first_text(props.get("phones")) or _first_text(props.get("phone")),
            "coordinates": point,
            "existence_confidence": props.get("confidence"),
            "category": _nested(props.get("categories")),
        }
        if not any(value.get(key) for key in ("address", "website", "phone", "coordinates", "category")):
            continue
        quote = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)[:8000]
        claim = {
            "field_key": "business_location",
            "value": value,
            "raw_value": raw,
            "status": "needs_review",
            "method": "overture_place_review",
            "confidence": _bounded_confidence(props.get("confidence")),
            "source_url": PLACES_GUIDE,
            "source_origin": "Overture Maps Places",
            "source_group": "",  # existence score cannot independently corroborate company attributes
            "source_record_id": gers_id,
            "source_license": _source_license(props.get("sources")),
            "retrieved_at": fetched,
            "quote": quote,
            "source_type": "open_map_place_record",
            "source_date": release[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", release) else fetched.date().isoformat(),
            "relationship": "possible_business_location",
        }
        ingest_source_claim(db, org_id, company_name=company.name, website=company.website,
                            country="", claim=claim)
        matched_companies.add(str(company.id))
        claim_count += 1
    return {"records_read": len(records), "companies": len(matched_companies), "claims": claim_count}


def _read_features(path: Path) -> Iterable[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.casefold() in {".jsonl", ".geojsonl", ".geojsonseq"}:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    row = json.loads(line)
                    if isinstance(row, dict):
                        yield row
        return
    document = json.loads(path.read_text(encoding="utf-8"))
    features = document.get("features", []) if isinstance(document, dict) else []
    for feature in features:
        if isinstance(feature, dict):
            yield feature


def _primary_name(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("primary") or "")
    return str(value or "") if isinstance(value, str) else ""


def _first(value: Any) -> Any:
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _first_text(value: Any) -> str:
    item = _first(value)
    if isinstance(item, dict):
        return str(item.get("value") or item.get("url") or item.get("number") or "")
    return str(item or "")


def _source_license(sources: Any) -> str:
    names = set()
    if isinstance(sources, list):
        for source in sources:
            if not isinstance(source, dict):
                continue
            name = str(source.get("dataset") or source.get("provider") or source.get("name") or "").casefold()
            if name:
                names.add(name)
    licenses = sorted({f"{name}: {SOURCE_LICENSES[name]}" for name in names if name in SOURCE_LICENSES})
    if licenses:
        return "; ".join(licenses) + "; see https://docs.overturemaps.org/attribution/"
    return LICENSE


def _nested(value: Any) -> Any:
    if isinstance(value, dict):
        return value.get("primary") or value
    return _first(value)


def _bounded_confidence(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if 0 <= number <= 1 else None


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())
