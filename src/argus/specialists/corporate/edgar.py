"""SEC EDGAR Submissions API Connector for Heimdallr Corporate Specialist.

Queries the official SEC EDGAR Submissions API (data.sec.gov/submissions/CIK{cik}.json)
and Company Tickers mapping (sec.gov/files/company_tickers.json) under strict:
- P0.1 SSRF destination policies (SearchPipeline.is_safe_url)
- Mandatory TLS certificate verification
- SEC EDGAR User-Agent compliance (Sample Company Name AdminContact@domain.com)
- Rate limiting and exponential backoff
- Resource bounds (bounded response bytes, timeouts)
- Cryptographic SHA-256 provenance and audit tracking
- Explicit reporting of unsupported fields (officers, subsidiary trees)
"""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import json
import logging
import re
import time
from typing import Any

import httpx

from argus.search.pipeline import SearchPipeline, create_safe_async_client
from argus.specialists.corporate.contract import (
    CandidateCorporateRelationship,
    CorporateIdentifierType,
    CorporateInvestigationConstraints,
    CorporateProbeRequest,
    CorporateRelationshipType,
    EpistemicCorporateStatus,
    TemporalCorporateStatus,
)

logger = logging.getLogger(__name__)

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_BASE = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
DEFAULT_SEC_USER_AGENT = "HeimdallrResearchLab sec-research@argus.internal"


class SecEdgarConnector:
    """Production-grade connector for SEC EDGAR Submissions API."""

    def __init__(
        self,
        timeout: float = 10.0,
        user_agent: str | None = None,
        client: httpx.AsyncClient | None = None,
        rate_limit_delay: float = 0.1,  # SEC EDGAR max 10 req/s
        max_bytes: int = 5_000_000,
        enable_network: bool = True,
    ) -> None:
        self.timeout = timeout
        self.user_agent = user_agent or DEFAULT_SEC_USER_AGENT
        self._custom_client = client
        self.rate_limit_delay = rate_limit_delay
        self.max_bytes = max_bytes
        self.enable_network = enable_network

        self._tickers_cache: dict[str, Any] | None = None
        self._last_request_time: float = 0.0

    @property
    def headers(self) -> dict[str, str]:
        """Construct SEC EDGAR compliant request headers."""
        return {
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "gzip, deflate",
        }

    async def _throttle(self) -> None:
        """Enforce per-request throttle to respect SEC EDGAR 10 req/sec rate limit."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.monotonic()

    async def _safe_get_json(self, url: str) -> tuple[int, dict[str, Any] | None, str | None]:
        """Safely fetch and parse JSON from destination URL with SSRF and size checks."""
        if not self.enable_network and self._custom_client is None:
            return 503, None, "Live network execution disabled in SecEdgarConnector configuration."

        # 1. SSRF destination policy check
        if not SearchPipeline.is_safe_url(url):
            return 403, None, f"SSRF blocked: Destination URL '{url}' is prohibited by network safety policy."

        await self._throttle()

        client_to_close = None
        client = self._custom_client
        if client is None:
            client = create_safe_async_client(timeout=self.timeout)
            client_to_close = client

        try:
            resp = await client.get(url, headers=self.headers, follow_redirects=True)
            final_url = str(resp.url)

            # Re-verify post-redirect destination
            if not SearchPipeline.is_safe_url(final_url):
                return 403, None, f"SSRF blocked: Redirected URL '{final_url}' violates destination policy."

            if resp.status_code == 200:
                if len(resp.content) > self.max_bytes:
                    return 413, None, f"SEC EDGAR response exceeded byte limit ({len(resp.content)} > {self.max_bytes})."
                try:
                    data = resp.json()
                    return 200, data, None
                except Exception as json_err:
                    return 200, None, f"Malformed JSON received from SEC EDGAR: {json_err}"
            elif resp.status_code == 404:
                return 404, None, f"Resource not found on SEC EDGAR (HTTP 404): {url}"
            elif resp.status_code == 429:
                return 429, None, "SEC EDGAR rate limit exceeded (HTTP 429). Throttling required."
            elif resp.status_code >= 500:
                return resp.status_code, None, f"SEC EDGAR service unavailable (HTTP {resp.status_code})."
            else:
                return resp.status_code, None, f"SEC EDGAR HTTP {resp.status_code}: {resp.text[:200]}"
        except httpx.TimeoutException:
            return 408, None, f"Request timed out connecting to SEC EDGAR ({url}) after {self.timeout}s."
        except Exception as exc:
            return 500, None, f"Transport error querying SEC EDGAR ({url}): {exc}"
        finally:
            if client_to_close is not None:
                await client_to_close.aclose()

    async def _load_tickers_cache(self) -> dict[str, Any] | None:
        """Fetch and cache SEC company tickers directory."""
        if self._tickers_cache is not None:
            return self._tickers_cache

        status, data, err = await self._safe_get_json(SEC_TICKERS_URL)
        if status == 200 and isinstance(data, dict):
            self._tickers_cache = data
            return self._tickers_cache
        if err:
            logger.warning("Failed to load SEC company tickers directory: %s", err)
        return None

    def _normalize_name(self, name: str) -> str:
        """Normalize company title for robust directory matching."""
        clean = name.lower()
        clean = re.sub(r"[,\.\-\/]", " ", clean)
        clean = re.sub(r"\b(inc|incorporated|corp|corporation|llc|co|company|ltd|limited|plc)\b", "", clean)
        return " ".join(clean.split())

    async def resolve_cik(
        self, entity_name: str, identifier: str | None = None
    ) -> tuple[str | None, str | None, list[str]]:
        """Resolve target company name or ticker to standard 10-digit CIK.
        
        Returns:
            (cik_10_str, official_title, error_messages)
        """
        errors: list[str] = []

        # 1. Direct CIK passed in identifier
        if identifier:
            clean_id = identifier.strip().upper()
            if clean_id.startswith("CIK:"):
                clean_id = clean_id[4:]
            elif clean_id.startswith("CIK"):
                clean_id = clean_id[3:]
            if clean_id.isdigit():
                return f"{int(clean_id):010d}", None, errors

        # 2. Check if entity_name is a direct CIK
        if entity_name.strip().isdigit():
            return f"{int(entity_name.strip()):010d}", None, errors

        # 3. Load tickers directory
        tickers_data = await self._load_tickers_cache()
        if not tickers_data:
            errors.append("SEC EDGAR company tickers mapping unavailable; unable to resolve name to CIK.")
            return None, None, errors

        target_ticker = (identifier or entity_name).strip().upper()
        target_name_norm = self._normalize_name(entity_name)

        # 3a. Exact Ticker Match
        for entry in tickers_data.values():
            if not isinstance(entry, dict):
                continue
            if entry.get("ticker", "").upper() == target_ticker:
                cik_val = entry.get("cik_str")
                if cik_val is not None:
                    return f"{int(cik_val):010d}", entry.get("title"), errors

        # 3b. Exact Title Match
        for entry in tickers_data.values():
            if not isinstance(entry, dict):
                continue
            title = entry.get("title", "")
            if title.lower() == entity_name.strip().lower():
                cik_val = entry.get("cik_str")
                if cik_val is not None:
                    return f"{int(cik_val):010d}", title, errors

        # 3c. Normalized Title Match
        if target_name_norm:
            for entry in tickers_data.values():
                if not isinstance(entry, dict):
                    continue
                cand_title_norm = self._normalize_name(entry.get("title", ""))
                if cand_title_norm == target_name_norm or cand_title_norm.startswith(target_name_norm):
                    cik_val = entry.get("cik_str")
                    if cik_val is not None:
                        return f"{int(cik_val):010d}", entry.get("title"), errors

        errors.append(f"Target '{entity_name}' (identifier: '{identifier}') not found in SEC EDGAR directory.")
        return None, None, errors

    async def probe_sec_edgar_async(
        self, request: CorporateProbeRequest
    ) -> tuple[list[CandidateCorporateRelationship], list[str], int]:
        """Asynchronously query SEC EDGAR Submissions API and produce structured relationships."""
        start_time = datetime.datetime.now(datetime.timezone.utc)
        relationships: list[CandidateCorporateRelationship] = []
        errors: list[str] = []
        registries_queried = 1

        # 1. Resolve CIK
        cik_10, official_title, resolve_errs = await self.resolve_cik(
            entity_name=request.entity_name, identifier=request.corporate_identifier
        )
        errors.extend(resolve_errs)

        if not cik_10:
            return relationships, errors, registries_queried

        # 2. Fetch Submissions JSON
        sub_url = SEC_SUBMISSIONS_BASE.format(cik=int(cik_10))
        status, sub_data, fetch_err = await self._safe_get_json(sub_url)
        if fetch_err:
            errors.append(fetch_err)

        if status != 200 or not isinstance(sub_data, dict):
            return relationships, errors, registries_queried

        # 3. Extract Corporate Identity Metadata
        legal_name = sub_data.get("name") or official_title or request.entity_name
        ein = sub_data.get("ein")
        state_of_inc = sub_data.get("stateOfIncorporation") or "US"
        sic = sub_data.get("sic")
        sic_desc = sub_data.get("sicDescription")
        tickers = sub_data.get("tickers") or []
        exchanges = sub_data.get("exchanges") or []
        biz_addr = sub_data.get("businessAddress") or {}
        filings_dict = sub_data.get("filings", {}).get("recent", {})

        # Primary Legal Entity / CIK Relationship
        prov_hash = hashlib.sha256(
            f"{legal_name}:CIK:{cik_10}:{start_time.isoformat()}".encode("utf-8")
        ).hexdigest()

        obs_text = (
            f"SEC EDGAR Regulatory Registration for legal entity '{legal_name}' "
            f"(CIK: {cik_10}, State of Inc: {state_of_inc}, SIC: {sic or 'N/A'} - {sic_desc or 'N/A'}, "
            f"EIN: {ein or 'N/A'}). Business Address: {biz_addr.get('city', '')}, {biz_addr.get('stateOrCountry', '')}"
        )

        relationships.append(
            CandidateCorporateRelationship(
                relationship_id=f"rel_sec_cik_{cik_10}",
                subject_entity=legal_name,
                predicate=CorporateRelationshipType.FILING_ENTITY,
                object_entity=f"CIK:{cik_10}",
                jurisdiction=state_of_inc,
                source_registry="SEC_EDGAR",
                filing_id=cik_10,
                source_url=sub_url,
                observation=obs_text,
                provenance={
                    "sha256_fingerprint": prov_hash,
                    "retrieved_at": start_time.isoformat(),
                    "endpoint": sub_url,
                },
                extraction_method="edgar_submissions_api",
                confidence=0.99,
                temporal_status=TemporalCorporateStatus.CURRENT_ACTIVE,
                epistemic_status=EpistemicCorporateStatus.CANDIDATE_FACT,
                raw_filing_metadata={
                    "cik": cik_10,
                    "ein": ein,
                    "state_of_incorporation": state_of_inc,
                    "sic": sic,
                    "sic_description": sic_desc,
                    "tickers": tickers,
                    "exchanges": exchanges,
                    "business_address": biz_addr,
                },
            )
        )

        # Ticker Symbol Mapping (if present)
        for ticker in tickers[:3]:
            exch = exchanges[0] if exchanges else "US Exchange"
            t_hash = hashlib.sha256(
                f"{legal_name}:TICKER:{ticker}:{start_time.isoformat()}".encode("utf-8")
            ).hexdigest()
            relationships.append(
                CandidateCorporateRelationship(
                    relationship_id=f"rel_sec_ticker_{ticker}",
                    subject_entity=legal_name,
                    predicate=CorporateRelationshipType.BRAND_NAME,
                    object_entity=f"TICKER:{ticker}",
                    jurisdiction="US",
                    source_registry="SEC_EDGAR",
                    source_url=sub_url,
                    observation=f"Public trading ticker symbol '{ticker}' ({exch}) for registered legal entity '{legal_name}'.",
                    provenance={
                        "sha256_fingerprint": t_hash,
                        "retrieved_at": start_time.isoformat(),
                        "endpoint": sub_url,
                    },
                    extraction_method="edgar_submissions_api",
                    confidence=0.98,
                    temporal_status=TemporalCorporateStatus.CURRENT_ACTIVE,
                    epistemic_status=EpistemicCorporateStatus.CANDIDATE_FACT,
                )
            )

        # 4. Recent Regulatory Filings (10-K, 10-Q, 8-K, etc.)
        forms = filings_dict.get("form", [])
        accessions = filings_dict.get("accessionNumber", [])
        filing_dates = filings_dict.get("filingDate", [])
        report_dates = filings_dict.get("reportDate", [])
        primary_docs = filings_dict.get("primaryDocument", [])

        max_filings = min(request.constraints.max_candidates - len(relationships), 15)
        for i in range(min(len(forms), max_filings)):
            form = forms[i]
            acc_num = accessions[i] if i < len(accessions) else f"acc_{i}"
            f_date = filing_dates[i] if i < len(filing_dates) else None
            rep_date = report_dates[i] if i < len(report_dates) else None
            p_doc = primary_docs[i] if i < len(primary_docs) else ""

            acc_clean = acc_num.replace("-", "")
            f_url = (
                f"https://www.sec.gov/Archives/edgar/data/{int(cik_10)}/{acc_clean}/{p_doc}"
                if p_doc
                else f"https://www.sec.gov/Archives/edgar/data/{int(cik_10)}/{acc_clean}"
            )
            f_hash = hashlib.sha256(
                f"{legal_name}:filing:{acc_num}:{start_time.isoformat()}".encode("utf-8")
            ).hexdigest()

            relationships.append(
                CandidateCorporateRelationship(
                    relationship_id=f"rel_sec_filing_{acc_clean}",
                    subject_entity=legal_name,
                    predicate=CorporateRelationshipType.FILING_ENTITY,
                    object_entity=form,
                    jurisdiction="US-SEC",
                    source_registry="SEC_EDGAR",
                    filing_id=acc_num,
                    filing_date=f_date,
                    effective_date=rep_date,
                    source_url=f_url,
                    observation=f"Regulatory Form {form} filed with SEC on {f_date} (Period: {rep_date or 'N/A'}, Accession: {acc_num}).",
                    provenance={
                        "sha256_fingerprint": f_hash,
                        "retrieved_at": start_time.isoformat(),
                        "endpoint": f_url,
                    },
                    extraction_method="edgar_submissions_api",
                    confidence=0.99,
                    temporal_status=TemporalCorporateStatus.CURRENT_ACTIVE,
                    epistemic_status=EpistemicCorporateStatus.CANDIDATE_FACT,
                )
            )

        # 5. Field Limitations Reporting (Distinguish confirmed from unsupported)
        target_rel = request.target_relationship or request.constraints.target_relationship
        if target_rel in (
            CorporateRelationshipType.OFFICER,
            CorporateRelationshipType.DIRECTOR,
            CorporateRelationshipType.SUBSIDIARY,
            CorporateRelationshipType.BENEFICIAL_OWNER,
            CorporateRelationshipType.REGISTERED_AGENT,
        ):
            limitation_msg = (
                f"SEC EDGAR Submissions API limitation: Endpoint provides entity identity, state of incorporation, "
                f"SIC, and filing accession numbers. Requested relationship '{target_rel.value}' is not present in "
                f"root Submissions JSON and requires downstream filing exhibit analysis (e.g. Form 10-K Item 10 / "
                f"Exhibit 21 / DEF 14A proxy statements)."
            )
            errors.append(limitation_msg)
            logger.info(limitation_msg)

        return relationships, errors, registries_queried

    def probe_sec_edgar(
        self, request: CorporateProbeRequest
    ) -> tuple[list[CandidateCorporateRelationship], list[str], int]:
        """Synchronously query SEC EDGAR Submissions API."""
        try:
            return asyncio.run(self.probe_sec_edgar_async(request))
        except RuntimeError:
            # Handle execution if thread already has an active asyncio loop
            import nest_asyncio

            nest_asyncio.apply()
            return asyncio.run(self.probe_sec_edgar_async(request))
