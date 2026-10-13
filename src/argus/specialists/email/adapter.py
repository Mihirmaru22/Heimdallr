"""Heimdallr Vertical 6: Email Specialist Adapters for Capability Registry."""

from __future__ import annotations

from typing import Any, Dict, Optional
from argus.capability_registry.adapters import BaseCapabilityAdapter
from argus.specialists.email.specialist import EmailAccountSpecialist


class EmailAccountSpecialistAdapter(BaseCapabilityAdapter):
    """Uniform adapter for EmailAccountSpecialist."""

    def __init__(self, specialist: Optional[EmailAccountSpecialist] = None) -> None:
        self.specialist = specialist or EmailAccountSpecialist()

    def execute(self, inputs: Dict[str, Any], corpus: Any = None) -> Dict[str, Any]:
        return self.specialist.execute(inputs, corpus=corpus)


class EmailToAccountDiscoveryAdapter(BaseCapabilityAdapter):
    """Adapter for Capability A: email_to_account_discovery."""

    def __init__(self, specialist: Optional[EmailAccountSpecialist] = None) -> None:
        self.specialist = specialist or EmailAccountSpecialist()

    def execute(self, inputs: Dict[str, Any], corpus: Any = None) -> Dict[str, Any]:
        inputs_mod = dict(inputs)
        inputs_mod["operation"] = "account_discovery"
        return self.specialist.execute(inputs_mod, corpus=corpus)


class IdentityToEmailDiscoveryAdapter(BaseCapabilityAdapter):
    """Adapter for Capability B: identity_to_email_discovery."""

    def __init__(self, specialist: Optional[EmailAccountSpecialist] = None) -> None:
        self.specialist = specialist or EmailAccountSpecialist()

    def execute(self, inputs: Dict[str, Any], corpus: Any = None) -> Dict[str, Any]:
        inputs_mod = dict(inputs)
        inputs_mod["operation"] = "identity_to_email"
        return self.specialist.execute(inputs_mod, corpus=corpus)


class EmailVerificationAdapter(BaseCapabilityAdapter):
    """Adapter for Capability C: email_address_verification."""

    def __init__(self, specialist: Optional[EmailAccountSpecialist] = None) -> None:
        self.specialist = specialist or EmailAccountSpecialist()

    def execute(self, inputs: Dict[str, Any], corpus: Any = None) -> Dict[str, Any]:
        inputs_mod = dict(inputs)
        inputs_mod["operation"] = "verification"
        inputs_mod["verify"] = True
        return self.specialist.execute(inputs_mod, corpus=corpus)


class EmailIdentityResolutionAdapter(BaseCapabilityAdapter):
    """Adapter for Capability D: email_identity_resolution."""

    def __init__(self, specialist: Optional[EmailAccountSpecialist] = None) -> None:
        self.specialist = specialist or EmailAccountSpecialist()

    def execute(self, inputs: Dict[str, Any], corpus: Any = None) -> Dict[str, Any]:
        inputs_mod = dict(inputs)
        inputs_mod["operation"] = "resolution"
        inputs_mod["resolve"] = True
        return self.specialist.execute(inputs_mod, corpus=corpus)
