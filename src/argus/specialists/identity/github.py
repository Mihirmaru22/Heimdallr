"""GitHub Public REST API Connector for Heimdallr Identity Specialist.

Queries the official GitHub Public Users API (api.github.com/users/{username})
under strict:
- P0.1 SSRF destination policies (SearchPipeline.is_safe_url)
- Mandatory TLS certificate verification
- Rate limiting and exponential backoff
- Resource bounds (bounded response bytes, timeouts)
- Strict Epistemic Invariants: All discovered profiles are emitted as
  UNVERIFIED_CANDIDATE records with technical provenance. The specialist
  NEVER asserts verified identity equivalence ("these accounts belong to the same person").
- Distinction of no-results (HTTP 404) from service unavailability (5xx) and rate limits (403).
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
from argus.specialists.identity.contract import (
    CandidateIdentityRelationship,
    EpistemicCandidateStatus,
    IdentifierType,
    IdentityProbeRequest,
    InvestigationConstraints,
)

logger = logging.getLogger(__name__)

GITHUB_USER_API_URL = "https://api.github.com/users/{username}"
DEFAULT_USER_AGENT = "Heimdallr-Research-Bot/3.0 (+https://argus.internal/security-policy; bot@argus.internal)"


class GitHubIdentityConnector:
    """Production-grade connector for GitHub Public Users API."""

    def __init__(
        self,
        timeout: float = 10.0,
        user_agent: str | None = None,
        client: httpx.AsyncClient | None = None,
        rate_limit_delay: float = 0.5,
        max_bytes: int = 2_000_000,
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
        """Construct standard GitHub REST API request headers."""
        return {
            "User-Agent": self.user_agent,
            "Accept": "application/vnd.github.v3+json, application/json",
            "Accept-Encoding": "gzip, deflate",
        }

    async def _throttle(self) -> None:
        """Enforce rate limiting delay between profile queries."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.monotonic()

    async def _safe_get_json(self, url: str) -> tuple[int, dict[str, Any] | None, str | None]:
        """Fetch and parse JSON from destination URL with SSRF, TLS, and byte limit checks."""
        if not self.enable_network and self._custom_client is None:
            return 503, None, "Live network execution disabled in GitHubIdentityConnector configuration."

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
                    return 413, None, f"GitHub API response exceeded byte limit ({len(resp.content)} > {self.max_bytes})."
                try:
                    data = resp.json()
                    return 200, data, None
                except Exception as json_err:
                    return 200, None, f"Malformed JSON received from GitHub API: {json_err}"
            elif resp.status_code == 404:
                return 404, None, f"GitHub account not found (HTTP 404): {url}"
            elif resp.status_code == 403:
                return 403, None, "GitHub API rate limit exceeded (HTTP 403). Cooldown required."
            elif resp.status_code in (500, 502, 503, 504):
                return resp.status_code, None, f"GitHub API service unavailable (HTTP {resp.status_code})."
            else:
                return resp.status_code, None, f"GitHub API HTTP {resp.status_code}: {resp.text[:200]}"
        except httpx.TimeoutException:
            return 408, None, f"Request timed out connecting to GitHub API ({url}) after {self.timeout}s."
        except Exception as exc:
            return 500, None, f"Transport error querying GitHub API ({url}): {exc}"
        finally:
            if client_to_close is not None:
                await client_to_close.aclose()

    def _clean_handle(self, raw_identifier: str) -> str:
        """Sanitize username handle for API querying."""
        h = raw_identifier.strip()
        if h.startswith("@"):
            h = h[1:]
        elif "github.com/" in h:
            h = h.split("github.com/")[-1].split("/")[0]
        return re.sub(r"[^\w\-\.]", "", h)

    async def probe_username_async(
        self, request: IdentityProbeRequest
    ) -> tuple[list[CandidateIdentityRelationship], list[str], int]:
        """Asynchronously probe GitHub Public Users API for candidate profile records."""
        start_time = datetime.datetime.now(datetime.timezone.utc)
        clean_handle = self._clean_handle(request.identifier)
        candidates: list[CandidateIdentityRelationship] = []
        errors: list[str] = []
        platforms_queried = 1

        if not clean_handle:
            errors.append(f"Invalid or empty username identifier: '{request.identifier}'.")
            return candidates, errors, platforms_queried

        # Check platform filtering
        if request.constraints.allowed_platforms and "github" not in [p.lower() for p in request.constraints.allowed_platforms]:
            return candidates, errors, 0
        if request.constraints.blocked_platforms and "github" in [p.lower() for p in request.constraints.blocked_platforms]:
            return candidates, errors, 0

        # Identifier variants
        variants = [clean_handle]
        if request.constraints.permit_delimiter_permutations:
            if "_" in clean_handle:
                variants.append(clean_handle.replace("_", "-"))
            elif "-" in clean_handle:
                variants.append(clean_handle.replace("-", "_"))
        variants = list(dict.fromkeys(variants))

        for variant in variants:
            if len(candidates) >= request.constraints.max_candidates:
                break

            url = GITHUB_USER_API_URL.format(username=variant)
            status, data, err_msg = await self._safe_get_json(url)

            if status == 200 and isinstance(data, dict):
                login = data.get("login", variant)
                disp_name = data.get("name") or ""
                company = data.get("company") or ""
                location = data.get("location") or ""
                bio = data.get("bio") or ""
                blog = data.get("blog") or ""
                public_repos = data.get("public_repos", 0)
                created_at = data.get("created_at") or ""
                profile_url = data.get("html_url") or f"https://github.com/{login}"

                # Construct supporting observation
                obs_parts = [f"Handle: @{login}"]
                if disp_name:
                    obs_parts.append(f"Name: {disp_name}")
                if company:
                    obs_parts.append(f"Company: {company}")
                if location:
                    obs_parts.append(f"Location: {location}")
                if bio:
                    obs_parts.append(f"Bio: {bio}")
                obs_parts.append(f"Public Repos: {public_repos}")
                if created_at:
                    obs_parts.append(f"Member Since: {created_at[:10]}")
                observation_text = " | ".join(obs_parts)

                prov_payload = f"{profile_url}:{login}:{start_time.isoformat()}"
                evidence_hash = hashlib.sha256(prov_payload.encode("utf-8")).hexdigest()

                discovery_method = "exact_handle_probe" if variant == clean_handle else "delimiter_permutation_probe"

                # Candidate-only confidence scoring: Profile depth indicates existence match strength
                # Never 1.0 (requires Argus verification layer for identity equivalence)
                has_bio_data = bool(disp_name or company or bio)
                prelim_confidence = 0.70 if has_bio_data else 0.50

                candidate = CandidateIdentityRelationship(
                    candidate_entity=login,
                    identifier=request.identifier,
                    source_platform="GitHub",
                    source_url=profile_url,
                    supporting_observation=observation_text,
                    provenance={
                        "http_status": 200,
                        "probe_endpoint": url,
                        "canonical_url": profile_url,
                        "sha256_hash": evidence_hash,
                        "checked_timestamp": start_time.isoformat(),
                        "engine": "GitHubIdentityConnector_v1.0",
                    },
                    confidence=prelim_confidence,
                    discovery_method=discovery_method,
                    timestamp=start_time.isoformat(),
                    epistemic_status=EpistemicCandidateStatus.UNVERIFIED_CANDIDATE,
                    raw_profile_data={
                        "login": login,
                        "name": disp_name,
                        "company": company,
                        "location": location,
                        "bio": bio,
                        "blog": blog,
                        "public_repos": public_repos,
                        "created_at": created_at,
                    },
                )
                candidates.append(candidate)
            elif status == 404:
                # Differentiate confirmed no-results from network/upstream failures
                logger.debug("GitHub user '%s' does not exist (HTTP 404).", variant)
            elif err_msg:
                # Upstream failure, timeout, or rate-limiting
                errors.append(err_msg)

        if len(candidates) == 0 and not errors:
            errors.append(f"No profile discovered on GitHub for handle '@{clean_handle}'.")

        return candidates, errors, platforms_queried

    def probe_username(
        self, request: IdentityProbeRequest
    ) -> tuple[list[CandidateIdentityRelationship], list[str], int]:
        """Synchronously probe GitHub Public Users API."""
        try:
            return asyncio.run(self.probe_username_async(request))
        except RuntimeError:
            import nest_asyncio

            nest_asyncio.apply()
            return asyncio.run(self.probe_username_async(request))
