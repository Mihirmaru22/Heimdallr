"""Heimdallr V3.1 Capabilities Package.

Exposes the Capability Registry, definitions, adapters, models, and matcher.
Re-exports from argus.capability_registry for consistent package namespaces.
"""

from argus.capability_registry.models import (
    CapabilityCategory,
    CapabilityDefinition,
    CapabilityInputSchema,
    CapabilityOutputSchema,
    CapabilityCandidate,
    HealthStatus,
    LicenseStatus,
    LicenseMetadata,
    EpistemicNature,
    CostModel,
    PerformanceProfile,
    SecurityProfile,
)
from argus.capability_registry.registry import (
    CapabilityRegistry,
    RegistryValidationError,
)
from argus.capability_registry.defaults import (
    get_default_capabilities,
)
from argus.capability_registry.matcher import CapabilityMatcher
from argus.capability_registry.adapters import (
    BaseCapabilityAdapter,
    ArgusResearchAdapter,
    IdentitySpecialistAdapter,
    InfrastructureSpecialistAdapter,
    CorporateSpecialistAdapter,
    ChallengerIdentityAdapter,
    get_adapter_for_implementation,
)

__all__ = [
    "CapabilityCategory",
    "CapabilityDefinition",
    "CapabilityInputSchema",
    "CapabilityOutputSchema",
    "CapabilityCandidate",
    "HealthStatus",
    "LicenseStatus",
    "LicenseMetadata",
    "EpistemicNature",
    "CostModel",
    "PerformanceProfile",
    "SecurityProfile",
    "CapabilityRegistry",
    "RegistryValidationError",
    "get_default_capabilities",
    "CapabilityMatcher",
    "BaseCapabilityAdapter",
    "ArgusResearchAdapter",
    "IdentitySpecialistAdapter",
    "InfrastructureSpecialistAdapter",
    "CorporateSpecialistAdapter",
    "ChallengerIdentityAdapter",
    "get_adapter_for_implementation",
]
