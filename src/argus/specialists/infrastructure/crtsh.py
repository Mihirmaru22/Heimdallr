"""Certificate Transparency (crt.sh) Connector for Heimdallr Infrastructure Specialist.

Queries the public Certificate Transparency search engine (crt.sh) under strict:
- P0.1 SSRF destination policies (SearchPipeline.is_safe_url)
- Mandatory TLS certificate verification
- Rate limiting and exponential backoff
- Resource bounds (bounded response bytes, timeouts)
- Strict Epistemic Invariants: All discovered hostnames are emitted as
  CANDIDATE_ASSET records with technical provenance, NEVER asserted as verified ownership.
- Graceful handling of unavailable upstream servers (502/503/504), malformed responses, and empty results.
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
from urllib.parse import urlparse

import httpx

from argus.search.pipeline import SearchPipeline, create_safe_async_client
from argus.specialists.infrastructure.contract import (
    AssetType,
    CandidateInfrastructureAsset,
    EpistemicAssetStatus,
    InfrastructureInvestigationConstraints,
    InfrastructureProbeRequest,
    RelationshipType,
    TemporalStatus,
)

logger = logging.getLogger(__name__)

CRTSH_BASE_URL = "https://crt.sh/?q={query}&output=json"
DEFAULT_USER_AGENT = "Heimdallr-Research-Bot/3.0 (+https://argus.internal/security-policy; bot@argus.internal)"


class CrtShConnector:
    """Production-grade connector for crt.sh Certificate Transparency search."""

    def __init__(
        self,
        timeout: float = 10.0,
        user_agent: str | None = None,
        client: httpx.AsyncClient | None = None,
        rate_limit_delay: float = 0.5,
        max_bytes: int = 5_000_000,
        enable_network: bool = True,
    ) -> None:
        self.timeout = timeout
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        self._custom_client = client
        self.rate_limit_delay = rate_limit_delay
        self.max_bytes = max_bytes
        self.enable_network = enable_network

        self._last_request_time: float = 0.0

    @property
    def headers(self) -> dict[str, str]:
        """Construct standard HTTP request headers."""
        return {
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "gzip, deflate",
        }

    async def _throttle(self) -> None:
        """Enforce rate limiting delay between crt.sh queries."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.monotonic()

    async def _safe_get_json(self, url: str) -> tuple[int, Any | None, str | None]:
        """Fetch and parse JSON from destination URL with SSRF, TLS, and size verification."""
        if not self.enable_network and self._custom_client is None:
            return 503, None, "Live network execution disabled in CrtShConnector configuration."

        # 1. SSRF destination policy check
        if not SearchPipeline.is_safe_url(url):
            return 403, None, f"SSRF blocked: Destination URL '{url}' violates network destination policy."

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
                    return 413, None, f"crt.sh response exceeded byte limit ({len(resp.content)} > {self.max_bytes})."
                try:
                    data = resp.json()
                    return 200, data, None
                except Exception as json_err:
                    return 200, None, f"Malformed JSON received from crt.sh: {json_err}"
            elif resp.status_code == 404:
                return 404, None, f"crt.sh endpoint returned 404 Not Found for {url}."
            elif resp.status_code == 429:
                return 429, None, "crt.sh rate limit exceeded (HTTP 429)."
            elif resp.status_code in (502, 503, 504):
                return resp.status_code, None, f"crt.sh service temporarily unavailable (HTTP {resp.status_code})."
            else:
                return resp.status_code, None, f"crt.sh HTTP {resp.status_code}: {resp.text[:200]}"
        except httpx.TimeoutException:
            return 408, None, f"Request timed out connecting to crt.sh ({url}) after {self.timeout}s."
        except Exception as exc:
            return 500, None, f"Transport error querying crt.sh ({url}): {exc}"
        finally:
            if client_to_close is not None:
                await client_to_close.aclose()

    def _clean_domain(self, raw_domain: str) -> str:
        """Sanitize domain string for querying."""
        d = raw_domain.strip().lower()
        if d.startswith("http://") or d.startswith("https://"):
            d = urlparse(d).netloc or d
        if d.startswith("*."):
            d = d[2:]
        return d.rstrip(".")

    async def query_crtsh_async(
        self, request: InfrastructureProbeRequest
    ) -> tuple[list[CandidateInfrastructureAsset], list[str], int]:
        """Asynchronously query crt.sh for certificate transparency logs."""
        start_time = datetime.datetime.now(datetime.timezone.utc)
        target_domain = self._clean_domain(request.domain)
        candidates: list[CandidateInfrastructureAsset] = []
        errors: list[str] = []
        sources_queried = 1

        if not target_domain:
            errors.append("Empty or invalid target domain provided for crt.sh query.")
            return candidates, errors, sources_queried

        url = CRTSH_BASE_URL.format(query=target_domain)
        status, data, fetch_err = await self._safe_get_json(url)

        if fetch_err:
            errors.append(fetch_err)

        if status != 200 or not isinstance(data, list):
            return candidates, errors, sources_queried

        if len(data) == 0:
            errors.append(f"No certificate transparency records discovered on crt.sh for '{target_domain}'.")
            return candidates, errors, sources_queried

        seen_hostnames: set[str] = set()
        current_date_str = start_time.strftime("%Y-%m-%d")

        for entry in data:
            if not isinstance(entry, dict):
                continue
            if len(candidates) >= request.constraints.max_assets:
                break

            cert_id = entry.get("id")
            issuer = entry.get("issuer_name", "Unknown CA")
            not_before = entry.get("not_before", "")
            not_after = entry.get("not_after", "")
            common_name = entry.get("common_name", "")
            name_value = entry.get("name_value", "")

            # Extract Subject Alternative Names
            raw_names: list[str] = []
            if name_value:
                raw_names.extend(name_value.split("\n"))
            if common_name:
                raw_names.append(common_name)

            all_sans = [self._clean_domain(n) for n in raw_names if n.strip()]
            all_sans = list(dict.fromkeys(all_sans))

            for raw_name in raw_names:
                clean_host = self._clean_domain(raw_name)
                if not clean_host or clean_host in seen_hostnames:
                    continue

                # Filter disallowed domains if configured
                if request.constraints.disallowed_domains:
                    if any(clean_host.endswith(dis) for dis in request.constraints.disallowed_domains):
                        continue

                seen_hostnames.add(clean_host)

                # Asset classification
                if clean_host.endswith(f".{target_domain}"):
                    asset_type = AssetType.SUBDOMAIN
                    rel_type = RelationshipType.DIRECT_SUBDOMAIN
                elif clean_host == target_domain:
                    asset_type = AssetType.RELATED_DOMAIN
                    rel_type = RelationshipType.DIRECT_SUBDOMAIN
                else:
                    asset_type = AssetType.CERTIFICATE_SAN
                    rel_type = RelationshipType.CERT_SAN_CO_OCCURRENCE

                # Temporal validity classification
                is_expired = bool(not_after and not_after[:10] < current_date_str)
                temporal_status = (
                    TemporalStatus.HISTORICAL_EXPIRED if is_expired else TemporalStatus.CURRENT_ACTIVE
                )

                # Strict epistemic classification: Candidates only, never verified ownership
                epistemic_status = (
                    EpistemicAssetStatus.EXPIRED_HISTORICAL if is_expired else EpistemicAssetStatus.CANDIDATE_ASSET
                )

                obs_text = (
                    f"Certificate Transparency Log (crt.sh ID {cert_id or 'N/A'}) recorded SAN '{clean_host}' "
                    f"on certificate issued by '{issuer}' (Validity: {not_before} to {not_after})."
                )

                cert_endpoint = f"https://crt.sh/?id={cert_id}" if cert_id else url
                evidence_hash = hashlib.sha256(
                    f"{clean_host}:crtsh:{cert_id}:{start_time.isoformat()}".encode("utf-8")
                ).hexdigest()

                candidates.append(
                    CandidateInfrastructureAsset(
                        asset_id=f"ct_{clean_host}",
                        hostname=clean_host,
                        parent_domain=target_domain,
                        asset_type=asset_type,
                        relationship_type=rel_type,
                        ip_addresses=[],
                        certificate_sans=all_sans[:10],
                        supporting_observation=obs_text,
                        provenance={
                            "source_endpoints": [cert_endpoint],
                            "sha256_fingerprint": evidence_hash,
                            "queried_at": start_time.isoformat(),
                            "engine": "CrtShConnector_v1.0",
                        },
                        confidence=0.65,  # Preliminary candidate probe confidence
                        discovery_method="ct_log_enumeration",
                        timestamp=start_time.isoformat(),
                        temporal_status=temporal_status,
                        epistemic_status=epistemic_status,
                        raw_record_data={
                            "crtsh_id": cert_id,
                            "issuer_name": issuer,
                            "not_before": not_before,
                            "not_after": not_after,
                            "common_name": common_name,
                        },
                    )
                )

                if len(candidates) >= request.constraints.max_assets:
                    break

        return candidates, errors, sources_queried

    def query_crtsh(
        self, request: InfrastructureProbeRequest
    ) -> tuple[list[CandidateInfrastructureAsset], list[str], int]:
        """Synchronously query crt.sh for certificate transparency logs."""
        try:
            return asyncio.run(self.query_crtsh_async(request))
        except RuntimeError:
            import nest_asyncio

            nest_asyncio.apply()
            return asyncio.run(self.query_crtsh_async(request))
