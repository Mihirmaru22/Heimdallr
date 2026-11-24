"""USAspending.gov adapter for official U.S. federal award-recipient signals."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from app.catalog_sources.public_api import PublicApiSession
from app.services.catalog_store import ingest_source_claim

API = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
DOCS = "https://api.usaspending.gov/docs/endpoints"
LICENSE = ("Public federal award data; this importer does not assert a record-level license. "
           "See https://www.usaspending.gov/ and https://api.usaspending.gov/docs/endpoints")
FIELDS = ["Award ID", "Recipient Name", "Start Date", "End Date", "Award Amount", "Awarding Agency",
          "Awarding Sub Agency", "Award Type", "Description", "generated_internal_id", "recipient_id",
          "Recipient Location"]


def search_awards(company_name: str, *, client: PublicApiSession | None = None,
                  limit: int = 20) -> list[dict[str, Any]]:
    if len(company_name.strip()) < 2 or not 1 <= limit <= 100:
        raise ValueError("Provide a company name and a result limit from 1 to 100")
    http = client or PublicApiSession()
    payload = {
        "filters": {"recipient_search_text": [company_name], "award_type_codes": ["A", "B", "C", "D"]},
        "fields": FIELDS,
        "limit": limit,
        "page": 1,
        "sort": "Award Amount",
        "order": "desc",
    }
    result = http.post_json(API, json_body=payload)
    rows = result.get("results") or []
    if not isinstance(rows, list):
        raise ValueError("USAspending returned an unexpected results format")
    return [row for row in rows if isinstance(row, dict)]


def ingest_awards(db, org_id, company_name: str, *, client: PublicApiSession | None = None,
                  limit: int = 20) -> dict[str, int]:
    """Store exact recipient matches as award facts; never infer software use from spending."""
    records = search_awards(company_name, client=client, limit=limit)
    claims = 0
    company_count = 0
    for row in records:
        recipient = str(row.get("Recipient Name") or row.get("recipient_name") or "")
        if _norm(recipient) != _norm(company_name):
            continue
        award_id = str(row.get("Award ID") or row.get("award_id") or "")
        internal_id = str(row.get("generated_internal_id") or row.get("internal_id") or award_id)
        url = f"https://www.usaspending.gov/award/{internal_id}" if internal_id else DOCS
        value = {
            "award_id": award_id,
            "award_type": row.get("Award Type"),
            "amount": row.get("Award Amount"),
            "start_date": row.get("Start Date"),
            "end_date": row.get("End Date"),
            "awarding_agency": row.get("Awarding Agency"),
            "awarding_subagency": row.get("Awarding Sub Agency"),
            "description": row.get("Description"),
            "recipient_id": row.get("recipient_id"),
            "recipient_location": row.get("Recipient Location"),
        }
        claim = {
            "field_key": "federal_award",
            "value": value,
            "raw_value": row,
            "status": "verified",
            "verified_direct": True,
            "method": "official_award_record",
            "confidence": 1.0,
            "source_url": url,
            "source_origin": "USAspending.gov API",
            "source_group": "usaspending.gov",
            "source_record_id": award_id or internal_id,
            "source_license": LICENSE,
            "retrieved_at": datetime.now(UTC),
            "quote": json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)[:8000],
            "source_type": "official_award_api",
            "source_date": str(row.get("Start Date") or "")[:10],
            "relationship": "received_award",
        }
        ingest_source_claim(db, org_id, company_name=recipient, country="US", claim=claim)
        company_count = 1
        claims += 1
    return {"companies": company_count, "claims": claims}


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())
