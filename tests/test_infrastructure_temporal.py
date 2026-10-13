"""Temporal and Composition Safety Test Suite for Infrastructure Specialist.

Tests temporal reasoning (historical vs current, expired certificates, changed IPs,
acquired vs divested domains) and composition safety (preventing entity contamination,
unrelated-domain expansion, and scope drift).
"""

import pytest
from argus.specialists.infrastructure.contract import (
    CandidateInfrastructureAsset,
    EpistemicAssetStatus,
    InfrastructureProbeRequest,
    RelationshipType,
    TemporalStatus,
)
from argus.specialists.infrastructure.specialist import InfrastructureProbeSpecialist


def test_temporal_cert_expiry_detection():
    registry = {
        "legacy.corp": {
            "records": {
                "active.legacy.corp": {
                    "type": "A",
                    "cert_valid_to": "2029-01-01",
                    "status": "CURRENT_ACTIVE",
                    "sources": ["dns_zone"],
                },
                "dead.legacy.corp": {
                    "type": "HISTORICAL",
                    "cert_valid_to": "2017-05-01",  # Expired
                    "status": "HISTORICAL_EXPIRED",
                    "sources": ["ct_log_crtsh"],
                },
            }
        }
    }
    specialist = InfrastructureProbeSpecialist(registry=registry)
    res = specialist.discover_domain("legacy.corp")
    
    active = next(a for a in res.assets if a.hostname == "active.legacy.corp")
    dead = next(a for a in res.assets if a.hostname == "dead.legacy.corp")
    
    assert active.temporal_status == TemporalStatus.CURRENT_ACTIVE
    assert dead.temporal_status == TemporalStatus.HISTORICAL_EXPIRED


def test_composition_safety_prevents_unrelated_domain_expansion():
    """Verify that probing an infrastructure domain never pollutes unrelated entity state."""
    registry = {
        "corp-a.com": {
            "records": {
                "api.corp-a.com": {"type": "A", "sources": ["dns_zone"]},
            }
        },
        "corp-b.com": {
            "records": {
                "api.corp-b.com": {"type": "A", "sources": ["dns_zone"]},
            }
        },
    }
    specialist = InfrastructureProbeSpecialist(registry=registry)
    res_a = specialist.discover_domain("corp-a.com")
    
    # Must only contain corp-a.com assets, zero leak from corp-b.com
    assert len(res_a.assets) == 1
    assert res_a.assets[0].hostname == "api.corp-a.com"
    assert "corp-b" not in res_a.assets[0].hostname
