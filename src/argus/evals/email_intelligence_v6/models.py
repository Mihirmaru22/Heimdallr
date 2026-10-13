"""Heimdallr Vertical 6: Email & Account Intelligence Benchmark Models.

Defines the 100-task benchmark data structures, execution configurations,
and independent grading metrics.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from argus.specialists.email.models import (
    AddressValidity,
    IdentityAssociation,
    MailboxEvidence,
    TemporalStatus,
)


class BenchmarkTaskGroup(str, Enum):
    """The 6 required task categories for Vertical 6 benchmark."""

    GROUP_A_EMAIL_TO_ACCOUNT = "GROUP_A_EMAIL_TO_ACCOUNT"              # 20 tasks: Email -> Accounts & Profiles
    GROUP_B_IDENTITY_TO_EMAIL = "GROUP_B_IDENTITY_TO_EMAIL"            # 20 tasks: Identity (Username/Phone/URL) -> Email
    GROUP_C_ADDRESS_VERIFICATION = "GROUP_C_ADDRESS_VERIFICATION"      # 20 tasks: 4D Verification (Syntax/DNS/Mailbox/Temporal)
    GROUP_D_IDENTITY_RESOLUTION = "GROUP_D_IDENTITY_RESOLUTION"        # 15 tasks: Email-to-Identity Resolution & False Merges
    GROUP_E_AMBIGUOUS_NEGATIVE = "GROUP_E_AMBIGUOUS_NEGATIVE"          # 15 tasks: Contradictory, Stale, Recycled, Negative, Injections
    GROUP_F_CROSS_SPECIALIST = "GROUP_F_CROSS_SPECIALIST"              # 10 tasks: Cross-Specialist Investigations (Corp/Infra/Ident/Email)


class EmailBenchmarkTask(BaseModel):
    """A single independently graded task in EMAIL_INTELLIGENCE_V6."""

    task_id: str
    group: BenchmarkTaskGroup
    title: str
    query: str
    target_email: Optional[str] = None
    target_identity: Optional[str] = None
    target_username: Optional[str] = None
    target_phone: Optional[str] = None
    target_domain: Optional[str] = None
    as_of_date: Optional[str] = None

    # Context evidence provided in search environment or handed documents
    context_evidence: List[Dict[str, Any]] = Field(default_factory=list)
    mailbox_signal: Optional[str] = None
    temporal_hints: Dict[str, Any] = Field(default_factory=dict)
    known_attributes: Dict[str, Any] = Field(default_factory=dict)

    # Ground truth answers (Evaluator-only; separated from runtime inputs)
    expected_accounts: List[str] = Field(default_factory=list)
    expected_emails: List[str] = Field(default_factory=list)
    expected_address_validity: Optional[AddressValidity] = None
    expected_mailbox_evidence: Optional[MailboxEvidence] = None
    expected_identity_association: Optional[IdentityAssociation] = None
    expected_temporal_status: Optional[TemporalStatus] = None
    expected_is_merged: Optional[bool] = None
    expected_rejection_reason: Optional[str] = None
    expected_epistemic_status: str = "SUPPORTED"  # SUPPORTED, INFERRED, UNVERIFIED, CONTRADICTED, NOT_FOUND

    # Task attribute flags
    is_negative: bool = False
    is_fabricated: bool = False
    is_contradictory: bool = False
    is_shared_name: bool = False
    is_recycled_phone: bool = False
    is_stale: bool = False
    is_syndicated: bool = False
    is_prompt_injection: bool = False
    is_multihop: bool = False
    required_specialists: List[str] = Field(default_factory=list)

    def get_runtime_input(self) -> Dict[str, Any]:
        """Return strictly sanitized runtime input without expected answers or labels."""
        return {
            "task_id": self.task_id,
            "query": self.query,
            "email": self.target_email,
            "target_email": self.target_email,
            "target_identity": self.target_identity,
            "username": self.target_username,
            "identifier": self.target_username or self.target_phone or self.target_email or self.query,
            "phone": self.target_phone,
            "domain": self.target_domain,
            "as_of_date": self.as_of_date,
            "context_evidence": [dict(e) for e in self.context_evidence],
            "mailbox_signal": self.mailbox_signal,
            "temporal_hints": dict(self.temporal_hints),
            "known_attributes": dict(self.known_attributes),
        }


class BenchmarkTaskExecutionResult(BaseModel):
    """Result of evaluating a specific configuration on a task."""

    task_id: str
    config_name: str
    group: BenchmarkTaskGroup
    passed: bool

    # Metric dimensions
    precision: float = 1.0
    recall: float = 1.0
    f1: float = 1.0
    verification_accuracy: float = 1.0
    false_identity_merge: bool = False
    false_positive_account: bool = False
    unsupported_claim: bool = False
    prompt_injection_defused: bool = True
    epistemic_status_correct: bool = True
    specialist_invoked: bool = False
    materially_contributed: bool = False
    runtime_sec: float = 0.0

    # Diagnostic details
    observed_output: Dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""


class ConfigurationScorecard(BaseModel):
    """Aggregated scorecard for a configuration across benchmark tasks."""

    config_name: str
    total_tasks: int
    passed_tasks: int
    pass_rate_pct: float
    precision_mean: float
    recall_mean: float
    f1_mean: float
    verification_accuracy_mean: float
    false_identity_merges: int
    false_positive_accounts: int
    unsupported_claims: int
    group_pass_rates: Dict[str, float]
    candidate_attributable_fixes: int = 0
