"""Clean-Room Identity Specialist Implementation.

Executes candidate profile discovery across platform registries with
cryptographic evidence provenance, granular outcome propagation, and epistemic
safety safeguards (strictly preserving the distinction between account existence,
identity equivalence, and access to private content).
"""

from __future__ import annotations

import datetime
import hashlib
import logging
import re
from typing import Any

from argus.specialists.identity.contract import (
    AccountClaimType,
    CandidateIdentityRelationship,
    EpistemicCandidateStatus,
    IdentifierType,
    IdentityClaim,
    IdentityProbeRequest,
    IdentityProbeResult,
    InvestigationConstraints,
)
from argus.specialists.outcome import SpecialistOutcome, determine_specialist_outcome

logger = logging.getLogger(__name__)


class IdentityProbeSpecialist:
    """Clean-Room Identity Discovery Specialist.
    
    Provides high-recall candidate profile discovery across platform registries
    with cryptographic evidence provenance and epistemic safety safeguards.
    """

    def __init__(
        self,
        platform_registry: dict[str, dict[str, Any]] | None = None,
        live_connector: Any | None = None,
    ) -> None:
        """Initialize specialist with platform registry definition and optional live profile connector.
        
        Args:
            platform_registry: Dictionary mapping platform keys to site probe definitions.
            live_connector: Optional live profile connector (e.g. GitHubIdentityConnector).
        """
        self.platform_registry = platform_registry or {}
        self.live_connector = live_connector

    def probe_identifier(self, request: IdentityProbeRequest) -> IdentityProbeResult:
        """Execute cross-platform probe against target identifier.
        
        Args:
            request: Formal probe request payload containing identifier, type, and constraints.
            
        Returns:
            IdentityProbeResult containing discovered candidate relationships with provenance.
        """
        start_time = datetime.datetime.now(datetime.timezone.utc)
        clean_ident = request.identifier.strip()
        ident_lower = clean_ident.lower()
        
        candidates: list[CandidateIdentityRelationship] = []
        claims: list[IdentityClaim] = []
        errors: list[str] = []
        sources_queried: list[str] = []
        platforms_checked = 0
        platforms_skipped = 0
        total_available = len(self.platform_registry)
        starting_account: CandidateIdentityRelationship | None = None

        starting_platform_key = (
            request.starting_platform or request.constraints.starting_platform
        )
        if starting_platform_key:
            starting_platform_key = starting_platform_key.lower().strip()

        # Identifier normalization & permutation generation
        probe_variants = [clean_ident]
        if request.constraints.permit_delimiter_permutations:
            if "_" in clean_ident:
                probe_variants.append(clean_ident.replace("_", "-"))
            elif "-" in clean_ident:
                probe_variants.append(clean_ident.replace("-", "_"))

        # Deduplicate variants while preserving order
        unique_variants = list(dict.fromkeys(probe_variants))

        # Order platform keys so starting_platform is queried first if specified
        ordered_platform_keys = list(self.platform_registry.keys())
        if starting_platform_key and starting_platform_key in ordered_platform_keys:
            ordered_platform_keys.remove(starting_platform_key)
            ordered_platform_keys.insert(0, starting_platform_key)

        for platform_key in ordered_platform_keys:
            site_data = self.platform_registry[platform_key]
            # Check constraints
            if request.constraints.allowed_platforms and platform_key not in request.constraints.allowed_platforms:
                platforms_skipped += 1
                continue
            if request.constraints.blocked_platforms and platform_key in request.constraints.blocked_platforms:
                platforms_skipped += 1
                continue

            platforms_checked += 1
            site_name = site_data.get("name", platform_key.capitalize())
            if site_name not in sources_queried:
                sources_queried.append(site_name)

            registered_users = site_data.get("users", {})
            url_template = site_data.get("url_template", f"https://{platform_key}.com/{{username}}")
            expected_string = site_data.get("e_string", "profile_loaded")

            is_starting_plat = bool(starting_platform_key and platform_key == starting_platform_key)

            # Check each variant
            matched_for_platform = False
            for variant in unique_variants:
                var_lower = variant.lower()
                if var_lower in registered_users:
                    matched_for_platform = True
                    user_data = registered_users[var_lower]
                    target_url = user_data.get("url", url_template.format(username=variant))
                    disp_name = user_data.get("display_name", "")
                    bio = user_data.get("bio", "")
                    loc = user_data.get("location", "")
                    is_private = bool(user_data.get("is_private") or user_data.get("private"))

                    # Construct supporting observation
                    obs_parts = []
                    if disp_name:
                        obs_parts.append(f"Name: {disp_name}")
                    if bio:
                        obs_parts.append(f"Bio: {bio}")
                    if loc:
                        obs_parts.append(f"Location: {loc}")
                    
                    if is_private:
                        obs_parts.append("[Account status: PRIVATE - private content unaccessed without authorization]")

                    observation_text = " | ".join(obs_parts) if obs_parts else "Account registered with minimal profile metadata."

                    # Cryptographic provenance trace
                    prov_payload = f"{target_url}:{expected_string}:{start_time.isoformat()}"
                    evidence_hash = hashlib.sha256(prov_payload.encode("utf-8")).hexdigest()

                    discovery_method = (
                        "starting_platform_resolution"
                        if is_starting_plat
                        else ("exact_handle_probe" if variant == clean_ident else "delimiter_permutation_probe")
                    )

                    has_bio = bool(disp_name or bio)
                    prelim_confidence = 0.85 if is_starting_plat else (0.70 if has_bio else 0.40)

                    provenance_dict = {
                        "http_status": 200,
                        "probe_endpoint": target_url,
                        "matched_signature": expected_string,
                        "is_live": False,
                        "retrieval_mode": "FIXTURE_SIMULATION",
                        "source_origin": "FIXTURE_REGISTRY",
                        "response_content_sha256": None,
                        "observation_record_sha256": evidence_hash,
                        "sha256_hash": evidence_hash,
                        "checked_timestamp": start_time.isoformat(),
                        "cleanroom_engine": "IdentityProbeSpecialist_v1.0",
                    }

                    candidate = CandidateIdentityRelationship(
                        candidate_entity=variant,
                        identifier=clean_ident,
                        source_platform=site_name,
                        source_url=target_url,
                        supporting_observation=observation_text,
                        provenance=provenance_dict,
                        confidence=prelim_confidence,
                        discovery_method=discovery_method,
                        timestamp=start_time.isoformat(),
                        epistemic_status=EpistemicCandidateStatus.POTENTIAL_MATCH if is_starting_plat else EpistemicCandidateStatus.UNVERIFIED_CANDIDATE,
                        raw_profile_data={
                            "display_name": disp_name,
                            "bio": bio,
                            "location": loc,
                            "is_private": is_private,
                        },
                        is_starting_account=is_starting_plat,
                        is_private=is_private,
                        private_content_accessed=False if is_private else True,
                        retrieval_mode="FIXTURE_SIMULATION",
                        is_live=False,
                        response_content_sha256=None,
                        observation_record_sha256=evidence_hash,
                    )

                    candidates.append(candidate)
                    if is_starting_plat and starting_account is None:
                        starting_account = candidate

                    # Invariant: Generate strictly separated claims for existence, equivalence, and privacy access
                    # Claim 1: Account Existence
                    claims.append(
                        IdentityClaim(
                            claim_type=AccountClaimType.ACCOUNT_EXISTENCE,
                            subject=variant,
                            platform=site_name,
                            status="SUPPORTED",
                            statement=f"Account '{variant}' exists on {site_name} ({target_url}).",
                            is_private=is_private,
                            authorized_access=False,
                            content_retrieved=False if is_private else True,
                            source_url=target_url,
                            retrieval_mode="FIXTURE_SIMULATION",
                            is_live=False,
                            response_content_sha256=None,
                            observation_record_sha256=evidence_hash,
                            provenance=provenance_dict,
                        )
                    )

                    # Claim 2: Identity Equivalence
                    eq_status = "STARTING_ACCOUNT" if is_starting_plat else "CANDIDATE_HYPOTHESIS"
                    claims.append(
                        IdentityClaim(
                            claim_type=AccountClaimType.IDENTITY_EQUIVALENCE,
                            subject=f"{clean_ident}@{starting_platform_key or 'input'}",
                            platform=site_name,
                            status=eq_status,
                            statement=(
                                f"Starting anchor account on {site_name}: {target_url}"
                                if is_starting_plat
                                else f"Candidate identity hypothesis linking '{clean_ident}' with '{variant}' on {site_name} ({target_url})."
                            ),
                            is_private=is_private,
                            authorized_access=False,
                            content_retrieved=False if is_private else True,
                            source_url=target_url,
                            retrieval_mode="FIXTURE_SIMULATION",
                            is_live=False,
                            response_content_sha256=None,
                            observation_record_sha256=evidence_hash,
                            provenance=provenance_dict,
                        )
                    )

                    # Claim 3: Private Content Access Boundary
                    if is_private:
                        claims.append(
                            IdentityClaim(
                                claim_type=AccountClaimType.PRIVATE_CONTENT_ACCESS,
                                subject=variant,
                                platform=site_name,
                                status="NO_ACCESS",
                                statement=(
                                    f"Profile '{variant}' on {site_name} is marked private. "
                                    "Private content (e.g. posts, media, follower lists) was NOT retrieved; access-control boundary respected."
                                ),
                                is_private=True,
                                authorized_access=False,
                                content_retrieved=False,
                                source_url=target_url,
                                retrieval_mode="FIXTURE_SIMULATION",
                                is_live=False,
                                response_content_sha256=None,
                                observation_record_sha256=evidence_hash,
                                provenance=provenance_dict,
                            )
                        )
                    else:
                        claims.append(
                            IdentityClaim(
                                claim_type=AccountClaimType.PRIVATE_CONTENT_ACCESS,
                                subject=variant,
                                platform=site_name,
                                status="PUBLIC_METADATA_ACCESSED",
                                statement=f"Public profile metadata for '{variant}' on {site_name} retrieved via public-source probe.",
                                is_private=False,
                                authorized_access=True,
                                content_retrieved=True,
                                source_url=target_url,
                                retrieval_mode="FIXTURE_SIMULATION",
                                is_live=False,
                                response_content_sha256=None,
                                observation_record_sha256=evidence_hash,
                                provenance=provenance_dict,
                            )
                        )

                    if len(candidates) >= request.constraints.max_candidates:
                        break

            if is_starting_plat and not matched_for_platform:
                errors.append(f"Starting account '{clean_ident}' not found on '{site_name}' (HTTP 404).")

            if len(candidates) >= request.constraints.max_candidates:
                break

        # Check live profile connector if available and github is not already in registry
        if self.live_connector and "github" not in self.platform_registry and len(candidates) < request.constraints.max_candidates:
            if True:
                if "GitHub" not in sources_queried:
                    sources_queried.append("GitHub")
                live_cands, live_errs, live_queried = self.live_connector.probe_username(request)
                for lc in live_cands:
                    is_starting_plat = bool(starting_platform_key and starting_platform_key in ("github", "gh"))
                    if is_starting_plat and starting_account is None:
                        lc.is_starting_account = True
                        starting_account = lc
                    candidates.append(lc)

                    # Generate claims for live candidate
                    claims.append(
                        IdentityClaim(
                            claim_type=AccountClaimType.ACCOUNT_EXISTENCE,
                            subject=lc.candidate_entity,
                            platform=lc.source_platform,
                            status="SUPPORTED",
                            statement=f"Account '{lc.candidate_entity}' exists on {lc.source_platform} ({lc.source_url}).",
                            is_private=False,
                            authorized_access=False,
                            content_retrieved=True,
                            source_url=lc.source_url,
                            retrieval_mode="LIVE",
                            is_live=True,
                            response_content_sha256=lc.response_content_sha256,
                            observation_record_sha256=lc.observation_record_sha256,
                            provenance=lc.provenance,
                        )
                    )
                    claims.append(
                        IdentityClaim(
                            claim_type=AccountClaimType.IDENTITY_EQUIVALENCE,
                            subject=f"{clean_ident}@{starting_platform_key or 'input'}",
                            platform=lc.source_platform,
                            status="STARTING_ACCOUNT" if lc.is_starting_account else "CANDIDATE_HYPOTHESIS",
                            statement=f"Candidate identity hypothesis on {lc.source_platform}: {lc.source_url}",
                            is_private=False,
                            authorized_access=False,
                            content_retrieved=True,
                            source_url=lc.source_url,
                            retrieval_mode="LIVE",
                            is_live=True,
                            response_content_sha256=lc.response_content_sha256,
                            observation_record_sha256=lc.observation_record_sha256,
                            provenance=lc.provenance,
                        )
                    )
                    claims.append(
                        IdentityClaim(
                            claim_type=AccountClaimType.PRIVATE_CONTENT_ACCESS,
                            subject=lc.candidate_entity,
                            platform=lc.source_platform,
                            status="PUBLIC_METADATA_ACCESSED",
                            statement=f"Public GitHub profile metadata retrieved for '{lc.candidate_entity}'.",
                            is_private=False,
                            authorized_access=True,
                            content_retrieved=True,
                            source_url=lc.source_url,
                            retrieval_mode="LIVE",
                            is_live=True,
                            response_content_sha256=lc.response_content_sha256,
                            observation_record_sha256=lc.observation_record_sha256,
                            provenance=lc.provenance,
                        )
                    )

                errors.extend(live_errs)
                platforms_checked += live_queried

        end_time = datetime.datetime.now(datetime.timezone.utc)
        elapsed_ms = (end_time - start_time).total_seconds() * 1000.0

        outcome = determine_specialist_outcome(
            has_results=bool(candidates),
            errors=errors,
            multiple_sources=len(sources_queried) > 1,
        )

        return IdentityProbeResult(
            target_identifier=clean_ident,
            identifier_type=request.identifier_type,
            starting_platform=starting_platform_key,
            starting_account=starting_account,
            candidates=candidates,
            sources_queried=sources_queried,
            claims=claims,
            platforms_queried=platforms_checked,
            platforms_skipped=platforms_skipped,
            platforms_available=total_available,
            total_platforms_probed=platforms_checked,
            total_candidates_found=len(candidates),
            execution_time_ms=elapsed_ms,
            outcome=outcome,
            errors=errors,
        )

    # Convenience method for direct handle searches
    def search_username(self, username: str, starting_platform: str | None = None) -> IdentityProbeResult:
        """High-level username search helper conforming to specialist contract."""
        req = IdentityProbeRequest(
            identifier=username,
            identifier_type=IdentifierType.USERNAME,
            starting_platform=starting_platform,
            constraints=InvestigationConstraints(
                permit_delimiter_permutations=True,
                starting_platform=starting_platform,
            ),
        )
        return self.probe_identifier(req)
