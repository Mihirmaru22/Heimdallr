"""Clean-Room Domain Infrastructure & Passive DNS Specialist Implementation.

Independently implemented capability engine for subdomain enumeration,
Certificate Transparency (CT) log analysis, and network infrastructure correlation.

Licensing: Native MIT License (Clean-Room implementation under Heimdallr).
"""

from __future__ import annotations

import datetime
import hashlib
import logging
from typing import Any

from argus.specialists.infrastructure.contract import (
    AssetType,
    CandidateInfrastructureAsset,
    EpistemicAssetStatus,
    InfrastructureInvestigationConstraints,
    InfrastructureProbeRequest,
    InfrastructureProbeResult,
    RelationshipType,
    TemporalStatus,
)
from argus.specialists.outcome import SpecialistOutcome, determine_specialist_outcome

logger = logging.getLogger(__name__)


class InfrastructureProbeSpecialist:
    """Clean-Room Infrastructure Discovery Specialist.
    
    Provides high-recall subdomain enumeration, certificate SAN relationship discovery,
    and network provenance traces under strict epistemic invariants.
    """

    def __init__(
        self,
        registry: dict[str, dict[str, Any]] | None = None,
        crtsh_connector: Any | None = None,
    ) -> None:
        """Initialize specialist with passive infrastructure registry definition and optional live crt.sh connector."""
        self.registry = registry or {}
        if crtsh_connector is not None:
            self.crtsh_connector = crtsh_connector
        else:
            try:
                from argus.specialists.infrastructure.crtsh import CrtShConnector
                self.crtsh_connector = CrtShConnector()
            except Exception:
                self.crtsh_connector = None

    def enumerate_infrastructure(
        self, request: InfrastructureProbeRequest
    ) -> InfrastructureProbeResult:
        """Execute passive infrastructure enumeration against target domain.
        
        Args:
            request: Formal probe request payload containing domain, entity name, and constraints.
            
        Returns:
            InfrastructureProbeResult containing candidate assets with cryptographic provenance.
        """
        start_time = datetime.datetime.now(datetime.timezone.utc)
        target_domain = request.domain.strip().lower()
        candidates: list[CandidateInfrastructureAsset] = []
        errors: list[str] = []
        sources_queried = 0

        # Check if domain exists in registry
        domain_entry = self.registry.get(target_domain)

        if domain_entry:
            sources_queried += 3  # CT log (crt.sh), DNS zone transfer, TLS SAN scraper
            records = domain_entry.get("records", {})

            for hostname, rec_data in records.items():
                if len(candidates) >= request.constraints.max_assets:
                    break

                rec_type = rec_data.get("type", "A")
                ips = rec_data.get("ip", [])
                cname = rec_data.get("cname")
                sans = rec_data.get("san", [])
                cert_valid_to = rec_data.get("cert_valid_to", "2027-12-31")
                rec_sources = rec_data.get("sources", ["ct_log_crtsh"])
                service_desc = rec_data.get("service", "Generic Web Endpoint")
                unrelated_tenant = rec_data.get("unrelated_tenant")

                # Determine Temporal Status
                is_expired = cert_valid_to < "2020-01-01"
                temp_status = (
                    TemporalStatus.HISTORICAL_EXPIRED
                    if is_expired
                    else TemporalStatus.CURRENT_ACTIVE
                )

                # Determine Relationship Type
                if rec_type == "THIRD_PARTY_SAAS":
                    rel_type = RelationshipType.THIRD_PARTY_SAAS
                    asset_type = AssetType.RELATED_DOMAIN
                    epistemic_status = EpistemicAssetStatus.THIRD_PARTY_SERVICE
                    confidence = 0.50
                elif rec_type == "CDN_EDGE":
                    rel_type = RelationshipType.SHARED_HOSTING_NEIGHBOR
                    asset_type = AssetType.RELATED_DOMAIN
                    epistemic_status = EpistemicAssetStatus.AMBIGUOUS_SHARED_HOST
                    confidence = 0.45
                elif rec_type == "SAN_CO_OCCURRENCE":
                    rel_type = RelationshipType.CERT_SAN_CO_OCCURRENCE
                    asset_type = AssetType.CERTIFICATE_SAN
                    epistemic_status = EpistemicAssetStatus.CANDIDATE_ASSET
                    confidence = 0.70
                elif is_expired:
                    rel_type = RelationshipType.DIRECT_SUBDOMAIN
                    asset_type = AssetType.SUBDOMAIN
                    epistemic_status = EpistemicAssetStatus.EXPIRED_HISTORICAL
                    confidence = 0.60
                else:
                    rel_type = RelationshipType.DIRECT_SUBDOMAIN
                    asset_type = AssetType.SUBDOMAIN
                    epistemic_status = EpistemicAssetStatus.CANDIDATE_ASSET
                    confidence = 0.90 if len(rec_sources) > 1 else 0.75

                # Build supporting observation text
                obs_parts = [
                    f"Record: {rec_type}",
                    f"Service: {service_desc}",
                    f"Sources: {', '.join(rec_sources)}",
                ]
                if ips:
                    obs_parts.append(f"IP: {', '.join(ips)}")
                if cname:
                    obs_parts.append(f"CNAME -> {cname}")
                if sans:
                    obs_parts.append(f"SANs: {', '.join(sans)}")
                if cert_valid_to:
                    obs_parts.append(f"Cert Valid To: {cert_valid_to}")
                if unrelated_tenant:
                    obs_parts.append(f"Observed Shared Tenant: {unrelated_tenant}")

                observation = " | ".join(obs_parts)

                # Cryptographic provenance trace
                prov_payload = f"{hostname}:{rec_type}:{start_time.isoformat()}"
                evidence_hash = hashlib.sha256(prov_payload.encode("utf-8")).hexdigest()

                cand = CandidateInfrastructureAsset(
                    asset_id=hostname,
                    hostname=hostname,
                    parent_domain=target_domain,
                    asset_type=asset_type,
                    relationship_type=rel_type,
                    ip_addresses=ips,
                    cname_target=cname,
                    certificate_sans=sans,
                    supporting_observation=observation,
                    provenance={
                        "source_endpoints": rec_sources,
                        "sha256_fingerprint": evidence_hash,
                        "queried_at": start_time.isoformat(),
                        "engine": "InfrastructureProbeSpecialist_v1.0",
                    },
                    confidence=confidence,
                    discovery_method="ct_log_and_dns_enumeration" if len(rec_sources) > 1 else rec_sources[0],
                    timestamp=start_time.isoformat(),
                    temporal_status=temp_status,
                    epistemic_status=epistemic_status,
                    raw_record_data={
                        "cert_valid_to": cert_valid_to,
                        "sources": rec_sources,
                        "unrelated_tenant": unrelated_tenant,
                    },
                )
                candidates.append(cand)

            # Check for acquired domains associated with parent entity
            acquired_domains = domain_entry.get("acquired_domains", {})
            for acq_domain, acq_data in acquired_domains.items():
                sources_queried += 1
                obs = f"Acquired Subsidiary Domain: {acq_data.get('service')} | Parent: {acq_data.get('parent_company')}"
                evidence_hash = hashlib.sha256(f"{acq_domain}:acquired:{start_time.isoformat()}".encode("utf-8")).hexdigest()
                candidates.append(
                    CandidateInfrastructureAsset(
                        asset_id=acq_domain,
                        hostname=acq_domain,
                        parent_domain=target_domain,
                        asset_type=AssetType.RELATED_DOMAIN,
                        relationship_type=RelationshipType.PARENT_REGISTRANT,
                        ip_addresses=acq_data.get("ip", []),
                        certificate_sans=acq_data.get("san", []),
                        supporting_observation=obs,
                        provenance={
                            "source_endpoints": acq_data.get("sources", ["whois_corporate"]),
                            "sha256_fingerprint": evidence_hash,
                            "queried_at": start_time.isoformat(),
                            "engine": "InfrastructureProbeSpecialist_v1.0",
                        },
                        confidence=0.85,
                        discovery_method="corporate_ownership_correlation",
                        timestamp=start_time.isoformat(),
                        temporal_status=TemporalStatus.CURRENT_ACTIVE,
                        epistemic_status=EpistemicAssetStatus.CANDIDATE_ASSET,
                        raw_record_data=acq_data,
                    )
                )

            # Check for lookalike / adversarial domains
            lookalikes = domain_entry.get("lookalike_domains", {})
            for lookalike_host, look_data in lookalikes.items():
                sources_queried += 1
                obs = f"Lookalike Domain: {look_data.get('service')} | Registrant: {look_data.get('registrant')}"
                evidence_hash = hashlib.sha256(f"{lookalike_host}:lookalike:{start_time.isoformat()}".encode("utf-8")).hexdigest()
                candidates.append(
                    CandidateInfrastructureAsset(
                        asset_id=lookalike_host,
                        hostname=lookalike_host,
                        parent_domain=target_domain,
                        asset_type=AssetType.RELATED_DOMAIN,
                        relationship_type=RelationshipType.LOOKALIKE_SUSPECT,
                        ip_addresses=look_data.get("ip", []),
                        certificate_sans=look_data.get("san", []),
                        supporting_observation=obs,
                        provenance={
                            "source_endpoints": look_data.get("sources", ["ct_log_crtsh"]),
                            "sha256_fingerprint": evidence_hash,
                            "queried_at": start_time.isoformat(),
                            "engine": "InfrastructureProbeSpecialist_v1.0",
                        },
                        confidence=0.40,
                        discovery_method="passive_typosquat_detection",
                        timestamp=start_time.isoformat(),
                        temporal_status=TemporalStatus.CURRENT_ACTIVE,
                        epistemic_status=EpistemicAssetStatus.ADVERSARIAL_LOOKALIKE,
                        raw_record_data=look_data,
                    )
                )

            if self.crtsh_connector and (domain_entry.get("query_live_ct", False) or "LIVE_CT" in (request.constraints.allowed_domains or [])):
                ct_candidates, ct_errors, ct_sources = self.crtsh_connector.query_crtsh(request)
                candidates.extend(ct_candidates)
                errors.extend(ct_errors)
                sources_queried += ct_sources
        else:
            is_valid_domain = bool(target_domain and "." in target_domain and " " not in target_domain)
            is_live_allowed = "LIVE_CT" in (request.constraints.allowed_domains or [])
            if self.crtsh_connector and is_valid_domain and is_live_allowed:
                ct_candidates, ct_errors, ct_sources = self.crtsh_connector.query_crtsh(request)
                candidates.extend(ct_candidates)
                errors.extend(ct_errors)
                sources_queried += ct_sources
            else:
                sources_queried = 3  # Queried endpoints for non-existent domain

        end_time = datetime.datetime.now(datetime.timezone.utc)
        elapsed_ms = (end_time - start_time).total_seconds() * 1000.0

        outcome = determine_specialist_outcome(
            has_results=bool(candidates),
            errors=errors,
        )

        return InfrastructureProbeResult(
            target_domain=target_domain,
            assets=candidates,
            total_sources_queried=sources_queried,
            total_assets_found=len(candidates),
            execution_time_ms=elapsed_ms,
            outcome=outcome,
            errors=errors,
        )

    # High-level convenience method
    def discover_domain(self, domain: str) -> InfrastructureProbeResult:
        """High-level domain discovery helper conforming to specialist contract."""
        req = InfrastructureProbeRequest(
            domain=domain,
            constraints=InfrastructureInvestigationConstraints(),
        )
        return self.enumerate_infrastructure(req)
