"""Unit tests for CapabilityRegistry data models, validation, and contracts."""

import pytest
from pydantic import ValidationError

from argus.capability_registry.models import (
    CapabilityCategory,
    CapabilityDefinition,
    CapabilityInputSchema,
    CapabilityOutputSchema,
    CostModel,
    EpistemicNature,
    HealthStatus,
    LicenseMetadata,
    LicenseStatus,
    PerformanceProfile,
    SecurityProfile,
)


def test_capability_definition_valid_instantiation():
    """Verify that a properly constructed capability definition passes validation."""
    cap = CapabilityDefinition(
        capability_id="test_cap",
        name="Test Capability",
        description="A valid test capability",
        version="1.2.3",
        category=CapabilityCategory.GENERAL_RESEARCH,
        provider="test-org",
        implementation_id="impl_test_v1",
        input_schema=CapabilityInputSchema(required_fields=["query"]),
        output_schema=CapabilityOutputSchema(output_fields=["results"], epistemic_nature=EpistemicNature.OBSERVATION),
        question_types=["FIND_INFO"],
        supported_operations=["SEARCH"],
        evidence_types=["WEB_PAGE"],
    )
    assert cap.capability_id == "test_cap"
    assert cap.version == "1.2.3"
    assert cap.status == HealthStatus.AVAILABLE
    assert cap.license_metadata.license_status == LicenseStatus.APPROVED


def test_capability_definition_invalid_semver():
    """Verify semver validation rejects non-semver version strings."""
    with pytest.raises(ValidationError):
        CapabilityDefinition(
            capability_id="test_cap",
            name="Test Capability",
            description="A test capability",
            version="1.0",  # Invalid, must be X.Y.Z
            category=CapabilityCategory.GENERAL_RESEARCH,
            provider="test-org",
            implementation_id="impl_test_v1",
            input_schema=CapabilityInputSchema(required_fields=["query"]),
            output_schema=CapabilityOutputSchema(output_fields=["results"]),
        )


def test_capability_definition_empty_id():
    """Verify empty ID strings are rejected."""
    with pytest.raises(ValidationError):
        CapabilityDefinition(
            capability_id="   ",
            name="Test",
            description="desc",
            category=CapabilityCategory.IDENTITY,
            provider="test",
            implementation_id="impl_1",
            input_schema=CapabilityInputSchema(),
            output_schema=CapabilityOutputSchema(),
        )


def test_performance_profile_defaults():
    """Verify performance profile defaults and constraints."""
    profile = PerformanceProfile(
        accuracy=0.95,
        precision=0.96,
        recall=0.94,
        f1=0.95,
        benchmark_id="EVAL_V2",
        benchmark_version="2.1.0",
    )
    assert profile.f1 == 0.95
    assert profile.scope == "BENCHMARK_OBSERVED"
