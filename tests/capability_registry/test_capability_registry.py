"""Unit tests for CapabilityRegistry API, validation, lifecycle, and querying."""

import os
import tempfile
from pathlib import Path
import pytest

from argus.capability_registry.defaults import get_default_capabilities
from argus.capability_registry.models import (
    CapabilityCategory,
    CapabilityDefinition,
    CapabilityInputSchema,
    CapabilityOutputSchema,
    EpistemicNature,
    HealthStatus,
    LicenseMetadata,
    LicenseStatus,
)
from argus.capability_registry.registry import CapabilityRegistry, RegistryValidationError


@pytest.fixture
def registry() -> CapabilityRegistry:
    reg = CapabilityRegistry()
    for cap in get_default_capabilities():
        reg.register(cap, overwrite=True)
    return reg


def test_registry_registration_and_get(registry: CapabilityRegistry):
    """Verify registration and basic lookups."""
    assert len(registry.list()) >= 4
    corp = registry.get("corporate_registry_intelligence")
    assert corp is not None
    assert corp.category == CapabilityCategory.CORPORATE
    assert corp.implementation_id == "impl_corporate_registry_specialist_v1"


def test_registry_multiple_implementations(registry: CapabilityRegistry):
    """Verify that multiple implementations for a single capability ID coexist."""
    impls = registry.get_implementations("identity_resolution")
    assert len(impls) == 2
    impl_ids = {i.implementation_id for i in impls}
    assert "impl_identity_probe_specialist_v1" in impl_ids
    assert "impl_challenger_identity_specialist_v2" in impl_ids


def test_registry_duplicate_rejection(registry: CapabilityRegistry):
    """Verify duplicate implementation registration without overwrite is rejected."""
    existing = registry.get("infrastructure_discovery")
    assert existing is not None
    with pytest.raises(RegistryValidationError):
        registry.register(existing, overwrite=False)


def test_registry_validation_fail_closed():
    """Verify fail-closed validation on invalid definitions."""
    reg = CapabilityRegistry()

    # Contradictory epistemic nature
    with pytest.raises(RegistryValidationError):
        cap = CapabilityDefinition(
            capability_id="invalid_cap",
            name="Invalid",
            description="Contradictory epistemic",
            category=CapabilityCategory.IDENTITY,
            provider="test",
            implementation_id="impl_bad",
            input_schema=CapabilityInputSchema(),
            output_schema=CapabilityOutputSchema(authoritative=True, epistemic_nature=EpistemicNature.CANDIDATE),
        )
        reg.register(cap)

    # Rejected license
    with pytest.raises(RegistryValidationError):
        cap_lic = CapabilityDefinition(
            capability_id="invalid_lic",
            name="Invalid Lic",
            description="Bad license",
            category=CapabilityCategory.IDENTITY,
            provider="test",
            implementation_id="impl_bad_lic",
            input_schema=CapabilityInputSchema(),
            output_schema=CapabilityOutputSchema(),
            license_metadata=LicenseMetadata(license="GPL-3.0", license_status=LicenseStatus.REJECTED),
        )
        reg.register(cap_lic)

    # Dependency self-reference
    with pytest.raises(RegistryValidationError):
        cap_dep = CapabilityDefinition(
            capability_id="self_dep",
            name="Self Dep",
            description="Self dep",
            category=CapabilityCategory.GENERAL_RESEARCH,
            provider="test",
            implementation_id="impl_self_dep",
            input_schema=CapabilityInputSchema(),
            output_schema=CapabilityOutputSchema(),
            dependencies=["self_dep"],
        )
        reg.register(cap_dep)


def test_registry_queries(registry: CapabilityRegistry):
    """Verify query APIs: category, entity_type, operation, jurisdiction, question_type."""
    # Category lookup
    ident_caps = registry.find_by_category(CapabilityCategory.IDENTITY)
    assert len(ident_caps) >= 2

    # Entity type lookup
    domain_caps = registry.find_by_entity_type("DOMAIN")
    assert any(c.capability_id == "infrastructure_discovery" for c in domain_caps)

    # Operation lookup
    dns_caps = registry.find_by_operation("DNS_LOOKUP")
    assert any(c.capability_id == "infrastructure_discovery" for c in dns_caps)

    # Jurisdiction lookup
    uk_caps = registry.find_by_jurisdiction("GB")
    assert any(c.capability_id == "corporate_registry_intelligence" for c in uk_caps)

    # Question type lookup
    q_caps = registry.find_by_question_type("WHO_IS_THIS_IDENTIFIER")
    assert any(c.capability_id == "identity_resolution" for c in q_caps)


def test_registry_health_lifecycle(registry: CapabilityRegistry):
    """Verify disable, enable, degrade, quarantine state management."""
    cap_id = "infrastructure_discovery"
    assert registry.health(cap_id) == HealthStatus.AVAILABLE

    registry.disable(cap_id)
    assert registry.health(cap_id) == HealthStatus.DISABLED

    registry.degrade(cap_id)
    assert registry.health(cap_id) == HealthStatus.DEGRADED

    registry.quarantine(cap_id)
    assert registry.health(cap_id) == HealthStatus.QUARANTINED

    registry.enable(cap_id)
    assert registry.health(cap_id) == HealthStatus.AVAILABLE


def test_registry_disk_persistence():
    """Verify registry serialization and recovery across process restarts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        disk_path = Path(tmpdir) / "caps.json"
        reg1 = CapabilityRegistry(persistence_path=disk_path)
        for cap in get_default_capabilities():
            reg1.register(cap, overwrite=True)
        assert disk_path.exists()

        # Restart simulation
        reg2 = CapabilityRegistry(persistence_path=disk_path)
        assert len(reg2.list()) == len(reg1.list())
        assert reg2.get("corporate_registry_intelligence") is not None
