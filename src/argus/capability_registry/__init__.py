"""Heimdallr V3.1: Capability Registry Package.

Separates CAPABILITIES from IMPLEMENTATIONS across the Heimdallr intelligence ecosystem:
- Strongly typed CapabilityDefinition contract
- Fail-closed CapabilityRegistry with deterministic lifecycle management
- Requirement-based CapabilityMatcher
- Adapters wrapping existing specialists and Argus generalist
"""

from argus.capability_registry.adapters import (
    ArgusResearchAdapter,
    BaseCapabilityAdapter,
    ChallengerIdentityAdapter,
    CorporateSpecialistAdapter,
    IdentitySpecialistAdapter,
    InfrastructureSpecialistAdapter,
    get_adapter_for_implementation,
)
from argus.capability_registry.defaults import get_default_capabilities
from argus.capability_registry.matcher import CapabilityMatcher
from argus.capability_registry.models import (
    BenchmarkMetadata,
    CapabilityCandidate,
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
from argus.capability_registry.registry import CapabilityRegistry, RegistryValidationError

__all__ = [
    "CapabilityCategory",
    "HealthStatus",
    "LicenseStatus",
    "EpistemicNature",
    "LicenseMetadata",
    "CostModel",
    "PerformanceProfile",
    "SecurityProfile",
    "BenchmarkMetadata",
    "CapabilityInputSchema",
    "CapabilityOutputSchema",
    "CapabilityDefinition",
    "CapabilityCandidate",
    "CapabilityRegistry",
    "RegistryValidationError",
    "CapabilityMatcher",
    "BaseCapabilityAdapter",
    "ArgusResearchAdapter",
    "IdentitySpecialistAdapter",
    "InfrastructureSpecialistAdapter",
    "CorporateSpecialistAdapter",
    "ChallengerIdentityAdapter",
    "get_adapter_for_implementation",
    "get_default_capabilities",
]
