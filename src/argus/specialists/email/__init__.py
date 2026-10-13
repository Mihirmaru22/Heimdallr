"""Heimdallr Vertical 6: Email & Account Intelligence Module."""

from argus.specialists.email.models import (
    AccountObservation,
    AddressValidity,
    AssociationNature,
    EmailCandidate,
    EmailVerificationResult,
    IdentityAssociation,
    IdentityResolutionVerdict,
    MailboxEvidence,
    TemporalStatus,
)
from argus.specialists.email.specialist import EmailAccountSpecialist
from argus.specialists.email.adapter import (
    EmailAccountSpecialistAdapter,
    EmailToAccountDiscoveryAdapter,
    IdentityToEmailDiscoveryAdapter,
    EmailVerificationAdapter,
    EmailIdentityResolutionAdapter,
)

__all__ = [
    "EmailAccountSpecialist",
    "EmailAccountSpecialistAdapter",
    "EmailToAccountDiscoveryAdapter",
    "IdentityToEmailDiscoveryAdapter",
    "EmailVerificationAdapter",
    "EmailIdentityResolutionAdapter",
    "AccountObservation",
    "AddressValidity",
    "AssociationNature",
    "EmailCandidate",
    "EmailVerificationResult",
    "IdentityAssociation",
    "IdentityResolutionVerdict",
    "MailboxEvidence",
    "TemporalStatus",
]
