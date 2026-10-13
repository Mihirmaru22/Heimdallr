"""Heimdallr V3.1: Capability Registry Core.

Provides deterministic, fail-closed registration, querying, and lifecycle management
for all Heimdallr capabilities and implementations.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from argus.capability_registry.models import (
    CapabilityCategory,
    CapabilityDefinition,
    EpistemicNature,
    HealthStatus,
    LicenseStatus,
    PerformanceProfile,
)

logger = logging.getLogger(__name__)


class RegistryValidationError(ValueError):
    """Raised when a capability definition violates registry integrity rules."""
    pass


class CapabilityRegistry:
    """Central deterministic registry for all Heimdallr intelligence capabilities."""

    def __init__(self, persistence_path: Optional[Path | str] = None) -> None:
        self.persistence_path = Path(persistence_path) if persistence_path else None
        # key: implementation_id -> CapabilityDefinition
        self._implementations: Dict[str, CapabilityDefinition] = {}
        # key: capability_id -> list of implementation_ids
        self._capability_index: Dict[str, List[str]] = {}

        if self.persistence_path and self.persistence_path.exists():
            self.load_from_disk()

    # -------------------------------------------------------------------------
    # Validation Rules (Fail Closed)
    # -------------------------------------------------------------------------
    def validate_capability(self, cap: CapabilityDefinition) -> None:
        """Enforce strict fail-closed validation on incoming capability definitions."""
        if not cap.capability_id or not cap.capability_id.strip():
            raise RegistryValidationError("Capability ID cannot be empty.")

        if not cap.implementation_id or not cap.implementation_id.strip():
            raise RegistryValidationError("Implementation ID cannot be empty.")

        if not cap.provider or not cap.provider.strip():
            raise RegistryValidationError("Provider cannot be empty.")

        if not cap.name or not cap.name.strip():
            raise RegistryValidationError("Capability name cannot be empty.")

        if not cap.input_schema or not isinstance(cap.input_schema.required_fields, list):
            raise RegistryValidationError("Input schema with required_fields must be declared.")

        if not cap.output_schema or not isinstance(cap.output_schema.output_fields, list):
            raise RegistryValidationError("Output schema with output_fields must be declared.")

        # Contradictory Epistemic Declarations
        if cap.output_schema.authoritative and cap.output_schema.epistemic_nature == EpistemicNature.CANDIDATE:
            raise RegistryValidationError(
                "Contradictory epistemic declaration: Output cannot be marked both 'authoritative=True' and 'epistemic_nature=CANDIDATE'."
            )

        if "CANDIDATE_ONLY" in cap.epistemic_behavior.upper() and cap.output_schema.authoritative:
            raise RegistryValidationError(
                "Contradictory epistemic declaration: Specialist declares 'CANDIDATE_ONLY' behavior but output is marked authoritative."
            )

        # Invalid License Metadata
        if cap.license_metadata.license_status == LicenseStatus.REJECTED:
            raise RegistryValidationError(
                f"Cannot register capability with REJECTED license status: {cap.license_metadata.restrictions}"
            )

        if not cap.license_metadata.license or not cap.license_metadata.license.strip():
            raise RegistryValidationError("License field cannot be empty.")

        # Dependency self-reference check
        if cap.capability_id in cap.dependencies:
            raise RegistryValidationError("Capability cannot depend on itself.")

    # -------------------------------------------------------------------------
    # Core Registration & Lifecycle APIs
    # -------------------------------------------------------------------------
    def register(self, cap: CapabilityDefinition, overwrite: bool = False) -> None:
        """Register a new capability implementation. Fails closed on validation violation or duplicate."""
        self.validate_capability(cap)

        impl_id = cap.implementation_id
        if impl_id in self._implementations and not overwrite:
            existing = self._implementations[impl_id]
            if existing.version == cap.version:
                raise RegistryValidationError(
                    f"Duplicate implementation ID '{impl_id}' with version '{cap.version}' already registered. "
                    "Use overwrite=True to replace or increment semver."
                )

        self._implementations[impl_id] = cap

        cap_id = cap.capability_id
        if cap_id not in self._capability_index:
            self._capability_index[cap_id] = []
        if impl_id not in self._capability_index[cap_id]:
            self._capability_index[cap_id].append(impl_id)

        logger.info(f"Registered capability '{cap_id}' (impl: '{impl_id}', v{cap.version})")
        if self.persistence_path:
            self.save_to_disk()

    def get(self, capability_id: str, implementation_id: Optional[str] = None) -> Optional[CapabilityDefinition]:
        """Get capability definition by capability ID, optionally specifying implementation ID."""
        if implementation_id:
            impl = self._implementations.get(implementation_id)
            if impl and impl.capability_id == capability_id:
                return impl
            return impl

        impl_ids = self._capability_index.get(capability_id, [])
        if not impl_ids:
            # Check if capability_id was passed as implementation_id
            return self._implementations.get(capability_id)

        # Return first available implementation, or degraded if no available
        for i_id in impl_ids:
            impl = self._implementations[i_id]
            if impl.status == HealthStatus.AVAILABLE:
                return impl
        # If no AVAILABLE, return first DEGRADED
        for i_id in impl_ids:
            impl = self._implementations[i_id]
            if impl.status == HealthStatus.DEGRADED:
                return impl
        # Otherwise return first implementation regardless of status
        return self._implementations[impl_ids[0]]

    def get_implementation(self, implementation_id: str) -> Optional[CapabilityDefinition]:
        """Get exact capability definition by implementation ID."""
        return self._implementations.get(implementation_id)

    def get_implementations(self, capability_id: str) -> List[CapabilityDefinition]:
        """Get all registered implementations of a capability ID."""
        impl_ids = self._capability_index.get(capability_id, [])
        return [self._implementations[i_id] for i_id in impl_ids if i_id in self._implementations]

    def list(self, include_inactive: bool = True) -> List[CapabilityDefinition]:
        """List all registered capabilities."""
        if include_inactive:
            return list(self._implementations.values())
        return [
            c for c in self._implementations.values()
            if c.status in (HealthStatus.AVAILABLE, HealthStatus.DEGRADED)
        ]

    def list_available(self) -> List[CapabilityDefinition]:
        """List only available and degraded operational capabilities."""
        return self.list(include_inactive=False)


    # -------------------------------------------------------------------------
    # Query & Discovery APIs
    # -------------------------------------------------------------------------
    def find_by_category(self, category: CapabilityCategory | str) -> List[CapabilityDefinition]:
        """Filter capabilities by category."""
        cat_str = category.value if isinstance(category, CapabilityCategory) else str(category)
        return [c for c in self._implementations.values() if c.category.value == cat_str]

    def find_by_entity_type(self, entity_type: str) -> List[CapabilityDefinition]:
        """Filter capabilities supporting a specific entity type (e.g. 'PERSON', 'ORGANIZATION', 'DOMAIN')."""
        ent_upper = entity_type.upper()
        return [
            c for c in self._implementations.values()
            if any(e.upper() == ent_upper for e in c.entity_types)
        ]

    def find_by_operation(self, operation: str) -> List[CapabilityDefinition]:
        """Filter capabilities supporting an explicit operation (e.g. 'DNS_QUERY', 'REGISTRY_SEARCH')."""
        op_upper = operation.upper()
        return [
            c for c in self._implementations.values()
            if any(o.upper() == op_upper for o in c.supported_operations)
        ]

    def find_by_jurisdiction(self, jurisdiction: str) -> List[CapabilityDefinition]:
        """Filter capabilities supporting a specific jurisdiction (e.g. 'US', 'GB', 'GLOBAL')."""
        jur_upper = jurisdiction.upper()
        return [
            c for c in self._implementations.values()
            if "GLOBAL" in [j.upper() for j in c.jurisdictions] or jur_upper in [j.upper() for j in c.jurisdictions]
        ]

    def find_by_temporal_requirement(self, requirement: str) -> List[CapabilityDefinition]:
        """Filter capabilities supporting temporal constraints (e.g. point-in-time, historical)."""
        req_upper = requirement.upper()
        return [
            c for c in self._implementations.values()
            if req_upper in c.temporal_behavior.upper()
        ]

    def find_by_question_type(self, question_type: str) -> List[CapabilityDefinition]:
        """Filter capabilities capable of resolving a question taxonomy type."""
        q_upper = question_type.upper()
        return [
            c for c in self._implementations.values()
            if any(qt.upper() == q_upper for qt in c.question_types)
        ]

    def get_performance(self, capability_id: str, benchmark: Optional[str] = None) -> Optional[PerformanceProfile]:
        """Get benchmark-derived performance profile for a capability."""
        cap = self.get(capability_id)
        if not cap:
            return None
        if benchmark and cap.performance_profile.benchmark_id != benchmark:
            return None
        return cap.performance_profile

    # -------------------------------------------------------------------------
    # Health & Operational Status Management
    # -------------------------------------------------------------------------
    def health(self, capability_id: str) -> HealthStatus:
        """Check runtime operational health status of a capability."""
        cap = self.get(capability_id)
        if not cap:
            return HealthStatus.UNAVAILABLE
        return cap.status

    def set_status(self, capability_id: str, status: HealthStatus) -> None:
        """Update operational status for all implementations of a capability, or specific implementation."""
        if capability_id in self._implementations:
            self._implementations[capability_id].status = status
            self._implementations[capability_id].health_status = status
        elif capability_id in self._capability_index:
            for impl_id in self._capability_index[capability_id]:
                self._implementations[impl_id].status = status
                self._implementations[impl_id].health_status = status
        else:
            raise KeyError(f"Capability or implementation '{capability_id}' not found.")

        if self.persistence_path:
            self.save_to_disk()

    def disable(self, capability_id: str) -> None:
        """Mark capability as DISABLED."""
        self.set_status(capability_id, HealthStatus.DISABLED)

    def enable(self, capability_id: str) -> None:
        """Mark capability as AVAILABLE."""
        self.set_status(capability_id, HealthStatus.AVAILABLE)

    def degrade(self, capability_id: str) -> None:
        """Mark capability as DEGRADED."""
        self.set_status(capability_id, HealthStatus.DEGRADED)

    def quarantine(self, capability_id: str) -> None:
        """Mark capability as QUARANTINED."""
        self.set_status(capability_id, HealthStatus.QUARANTINED)

    # -------------------------------------------------------------------------
    # Persistence (Surviving Process Restart)
    # -------------------------------------------------------------------------
    def save_to_disk(self, target_path: Optional[Path | str] = None) -> None:
        """Serialize registered capabilities to JSON disk store."""
        path = Path(target_path or self.persistence_path or "storage/capability_registry.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            impl_id: cap.model_dump(mode="json")
            for impl_id, cap in self._implementations.items()
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load_from_disk(self, target_path: Optional[Path | str] = None) -> None:
        """Load capability definitions from JSON disk store."""
        path = Path(target_path or self.persistence_path or "storage/capability_registry.json")
        if not path.exists():
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for impl_id, cap_dict in data.items():
            cap = CapabilityDefinition.model_validate(cap_dict)
            self.register(cap, overwrite=True)
