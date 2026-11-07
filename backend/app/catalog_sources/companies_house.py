"""Companies House public company-register adapter (UK legal-entity facts)."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from app.catalog_sources.public_api import PublicApiError, PublicApiSession
from app.config import get_settings
from app.services.catalog_store import ingest_source_claim

API = "https://api.company-information.service.gov.uk"
REGISTER = "https://find-and-update.company-information.service.gov.uk/company"
API_LICENSE = ("License not asserted by this importer; consult Companies House API and record-level reuse terms: "
               "https://developer.company-information.service.gov.uk/")


def search_company(name: str, *, client: PublicApiSession | None = None) -> dict[str, Any]:
    """Resolve a company only when the API returns an exact normalized name match."""
    api_key = get_settings().companies_house_api_key.get_secret_value()
    if not api_key:
        raise PublicApiError("Set WEBDATA_COMPANIES_HOUSE_API_KEY to use the Companies House adapter")
    if len(name.strip()) < 2:
        raise ValueError("Company name must contain at least two characters")
    http = client or PublicApiSession()
    result = http.get_json(f"{API}/search/companies", params={"q": name, "items_per_page": 10}, auth=(api_key, ""))
    target = _norm(name)
    items = result.get("items") or []
    match = next((item for item in items if _norm(str(item.get("title") or "")) == target
                  and item.get("company_number")), None)
    if not match:
        raise LookupError(f"No exact Companies House name match for {name!r}; no record was imported")
    number = str(match["company_number"])
    profile = http.get_json(f"{API}/company/{number}", auth=(api_key, ""))
    return {"number": number, "profile": profile, "url": f"{REGISTER}/{number}"}


def claims_for(company: dict[str, Any], *, retrieved_at: datetime | None = None) -> list[dict[str, Any]]:
    """Translate a Companies House profile into independent, attributable official claims."""
    profile = company["profile"]
    number = str(company["number"])
    url = str(company["url"])
    fetched = retrieved_at or datetime.now(UTC)
    values: list[tuple[str, Any, Any, str]] = [
        ("registered_name", profile.get("company_name"), profile.get("company_name"), "Legal company name"),
        ("company_number", number, profile.get("company_number", number), "Companies House number"),
        ("registered_country", "United Kingdom", "United Kingdom", "Companies House jurisdiction"),
        ("company_status", profile.get("company_status"), profile.get("company_status"), "Register status"),
        ("incorporation_date", profile.get("date_of_creation"), profile.get("date_of_creation"), "Date of creation"),
        ("sic_codes", profile.get("sic_codes"), profile.get("sic_codes"), "SIC codes"),
        ("registered_office_address", profile.get("registered_office_address"),
         profile.get("registered_office_address"), "Registered office address"),
    ]
    claims = []
    for field, normalized, raw, quote in values:
        if normalized in (None, "", []):
            continue
        claims.append({
            "field_key": field,
            "value": normalized,
            "raw_value": raw,
            "status": "verified",
            "verified_direct": True,
            "method": "official_registry",
            "confidence": 1.0,
            "source_url": url,
            "source_origin": "Companies House API",
            "source_group": "companies-house",
            "source_record_id": number,
            "source_license": API_LICENSE,
            "retrieved_at": fetched,
            "quote": f'Companies House profile field {quote}: '
                     f'{json.dumps(raw, ensure_ascii=False, sort_keys=True, default=str)}',
            "source_type": "official_registry_api",
            "source_date": str(profile.get("date_of_creation") or "")[:10],
            "relationship": "registered_entity_fact",
        })
    return claims


def ingest_company(db, org_id, name: str, *, client: PublicApiSession | None = None) -> dict[str, int]:
    company = search_company(name, client=client)
    claims = claims_for(company)
    for claim in claims:
        ingest_source_claim(db, org_id, company_name=str(company["profile"].get("company_name") or name),
                            website="", country="GB", claim=claim)
    return {"companies": 1, "claims": len(claims)}


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())
