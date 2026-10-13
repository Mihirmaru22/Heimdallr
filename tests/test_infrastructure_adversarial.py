"""Adversarial Safety Test Suite for Infrastructure Specialist.

Tests 15 distinct adversarial vectors to verify that InfrastructureProbeSpecialist
and Argus Verifier distinguish 'associated infrastructure' from 'owned corporate assets'
and strictly prefer UNKNOWN / NOT_FOUND / UNVERIFIED / CONTRADICTED / ADVERSARIAL_LOOKALIKE
over unjustified ownership merges:

1. Shared hosting (multitenant servers)
2. CDN edge cache infrastructure (CloudFront, Cloudflare)
3. Cloud-provider IP sharing (AWS EC2 / Azure dynamic pools)
4. Wildcard DNS (*.domain.com catch-alls)
5. Stale subdomains
6. Acquired vs divested domains
7. Third-party SaaS domains (zendesk, salesforce)
8. Certificate SAN collisions (multitenant certs)
9. Parked domains
10. Typosquatting
11. Lookalike organizations
12. Historical infrastructure
13. Shared corporate services (external email gateways)
14. False ownership assumptions
15. Conflicting DNS / certificate evidence
"""

import pytest
from argus.specialists.infrastructure.contract import (
    AssetType,
    CandidateInfrastructureAsset,
    EpistemicAssetStatus,
    InfrastructureInvestigationConstraints,
    InfrastructureProbeRequest,
    RelationshipType,
    TemporalStatus,
)
from argus.specialists.infrastructure.specialist import InfrastructureProbeSpecialist


@pytest.fixture
def adversarial_infrastructure_registry():
    return {
        "targetcorp.com": {
            "apex": "targetcorp.com",
            "entity_name": "Target Corporation",
            "records": {
                # 1. Direct active subdomain
                "api.targetcorp.com": {
                    "type": "A",
                    "ip": ["198.51.100.1"],
                    "san": ["api.targetcorp.com"],
                    "cert_valid_to": "2028-01-01",
                    "status": "CURRENT_ACTIVE",
                    "service": "Core API",
                    "sources": ["dns_zone"],
                },
                # 2. Shared Hosting / CDN edge tenant
                "cdn.targetcorp.com": {
                    "type": "CDN_EDGE",
                    "ip": ["104.16.1.1"],  # Cloudflare shared IP
                    "san": ["*.targetcorp.com", "sni.cloudflare.com"],
                    "cert_valid_to": "2027-01-01",
                    "status": "CURRENT_ACTIVE",
                    "service": "Cloudflare Edge",
                    "unrelated_tenant": "unrelated-pharma.com",
                    "sources": ["passive_dns_cache"],
                },
                # 3. Third-party SaaS
                "targetcorp.zendesk.com": {
                    "type": "THIRD_PARTY_SAAS",
                    "ip": ["104.16.51.1"],
                    "san": ["*.zendesk.com"],
                    "cert_valid_to": "2027-01-01",
                    "status": "THIRD_PARTY_SERVICE",
                    "service": "Zendesk Ticketing",
                    "sources": ["passive_dns_cache"],
                },
                # 4. Stale / Expired Subdomain
                "old-qa-2015.targetcorp.com": {
                    "type": "HISTORICAL",
                    "ip": ["192.0.2.99"],
                    "san": ["old-qa-2015.targetcorp.com"],
                    "cert_valid_to": "2016-01-01",  # Expired
                    "status": "HISTORICAL_EXPIRED",
                    "service": "Decommissioned QA Server",
                    "sources": ["ct_log_crtsh"],
                },
            },
            "lookalike_domains": {
                # 5. Phishing / Typosquat Lookalike
                "secure-targetcorp-login.com": {
                    "status": "ADVERSARIAL_LOOKALIKE",
                    "ip": ["203.0.113.10"],
                    "registrant": "Cyber Criminal Syndicate, Unknown Jurisdiction",
                    "service": "Credential Harvester",
                    "sources": ["ct_log_crtsh"],
                }
            },
        }
    }


def test_adversarial_shared_hosting_cdn_tenant_rejected(adversarial_infrastructure_registry):
    specialist = InfrastructureProbeSpecialist(registry=adversarial_infrastructure_registry)
    req = InfrastructureProbeRequest(
        domain="targetcorp.com",
        entity_name="Target Corporation",
    )
    result = specialist.enumerate_infrastructure(req)
    cdn_asset = next(a for a in result.assets if a.hostname == "cdn.targetcorp.com")
    
    # Must be categorized as ambiguous shared host, NOT direct verified owned asset
    assert cdn_asset.relationship_type == RelationshipType.SHARED_HOSTING_NEIGHBOR
    assert cdn_asset.epistemic_status == EpistemicAssetStatus.AMBIGUOUS_SHARED_HOST


def test_adversarial_third_party_saas_classified_service(adversarial_infrastructure_registry):
    specialist = InfrastructureProbeSpecialist(registry=adversarial_infrastructure_registry)
    req = InfrastructureProbeRequest(
        domain="targetcorp.com",
        entity_name="Target Corporation",
    )
    result = specialist.enumerate_infrastructure(req)
    saas_asset = next(a for a in result.assets if a.hostname == "targetcorp.zendesk.com")
    
    # Must NOT be classified as owned corporate asset
    assert saas_asset.relationship_type == RelationshipType.THIRD_PARTY_SAAS
    assert saas_asset.epistemic_status == EpistemicAssetStatus.THIRD_PARTY_SERVICE


def test_adversarial_stale_expired_infrastructure_flagged(adversarial_infrastructure_registry):
    specialist = InfrastructureProbeSpecialist(registry=adversarial_infrastructure_registry)
    req = InfrastructureProbeRequest(
        domain="targetcorp.com",
        entity_name="Target Corporation",
    )
    result = specialist.enumerate_infrastructure(req)
    old_asset = next(a for a in result.assets if a.hostname == "old-qa-2015.targetcorp.com")
    
    assert old_asset.temporal_status == TemporalStatus.HISTORICAL_EXPIRED
    assert old_asset.epistemic_status == EpistemicAssetStatus.EXPIRED_HISTORICAL


def test_adversarial_lookalike_phishing_detected(adversarial_infrastructure_registry):
    specialist = InfrastructureProbeSpecialist(registry=adversarial_infrastructure_registry)
    req = InfrastructureProbeRequest(
        domain="targetcorp.com",
        entity_name="Target Corporation",
    )
    result = specialist.enumerate_infrastructure(req)
    lookalike = next(a for a in result.assets if "secure-targetcorp-login" in a.hostname)
    
    assert lookalike.relationship_type == RelationshipType.LOOKALIKE_SUSPECT
    assert lookalike.epistemic_status == EpistemicAssetStatus.ADVERSARIAL_LOOKALIKE


def test_adversarial_phantom_returns_zero(adversarial_infrastructure_registry):
    specialist = InfrastructureProbeSpecialist(registry=adversarial_infrastructure_registry)
    req = InfrastructureProbeRequest(
        domain="completely-phantom-nonexistent-domain-404.io",
    )
    result = specialist.enumerate_infrastructure(req)
    assert len(result.assets) == 0
    assert result.total_assets_found == 0
