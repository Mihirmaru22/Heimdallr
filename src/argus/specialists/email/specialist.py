"""Heimdallr Vertical 6: Unified Email & Account Intelligence Specialist.

Combines four distinct capabilities behind a clean-room, epistemic architecture:
1. email_to_account_discovery (Capability A)
2. identity_to_email_discovery (Capability B)
3. email_address_verification (Capability C)
4. email_identity_resolution (Capability D)

Preserves Heimdallr's fundamental architectural invariant:
Specialists remain candidate-producing; Argus / Verifier remains authoritative.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional
import uuid
from datetime import datetime, timezone

from argus.specialists.email.account_discovery import EmailToAccountDiscoveryEngine
from argus.specialists.email.identity_discovery import IdentityToEmailDiscoveryEngine
from argus.specialists.email.models import (
    AccountObservation,
    AddressValidity,
    EmailCandidate,
    EmailVerificationResult,
    IdentityAssociation,
    IdentityResolutionVerdict,
    MailboxEvidence,
    TemporalStatus,
)
from argus.specialists.email.resolution import EmailIdentityResolutionEngine
from argus.specialists.email.verifier import EmailVerificationEngine

logger = logging.getLogger(__name__)


class EmailAccountSpecialist:
    """Production clean-room specialist for email and account intelligence."""

    def __init__(
        self,
        dns_timeout: float = 2.0,
        check_live_dns: bool = False,  # Default to offline / deterministic for benchmark stability
    ) -> None:
        self.account_engine = EmailToAccountDiscoveryEngine()
        self.identity_engine = IdentityToEmailDiscoveryEngine()
        self.verifier_engine = EmailVerificationEngine(dns_timeout=dns_timeout, check_live_dns=check_live_dns)
        self.resolution_engine = EmailIdentityResolutionEngine()

    def discover_accounts_for_email(
        self,
        email: str,
        target_identity: Optional[str] = None,
        corpus: Any = None,
        max_results: int = 10,
    ) -> List[AccountObservation]:
        """Capability A: Discover public account and profile presences for an email."""
        return self.account_engine.discover_accounts(
            email=email,
            target_identity=target_identity,
            corpus=corpus,
            max_results=max_results,
        )

    def discover_emails_for_identity(
        self,
        identifier: str,
        identity_type: str = "USERNAME",
        target_name: Optional[str] = None,
        organization: Optional[str] = None,
        org_domain: Optional[str] = None,
        corpus: Any = None,
        generate_inferred_candidates: bool = True,
    ) -> List[EmailCandidate]:
        """Capability B: Discover email addresses for a target identity."""
        return self.identity_engine.discover_emails_for_identity(
            identifier=identifier,
            identity_type=identity_type,
            target_name=target_name,
            organization=organization,
            org_domain=org_domain,
            corpus=corpus,
            generate_inferred_candidates=generate_inferred_candidates,
        )

    def verify_email_address(
        self,
        email: str,
        target_identity: Optional[str] = None,
        context_evidence: Optional[List[Dict[str, Any]]] = None,
        mailbox_signal: Optional[str] = None,
        as_of_date: Optional[str] = None,
        temporal_hints: Optional[Dict[str, Any]] = None,
    ) -> EmailVerificationResult:
        """Capability C: Independently assess 4 verification dimensions."""
        return self.verifier_engine.verify(
            email=email,
            target_identity=target_identity,
            context_evidence=context_evidence,
            mailbox_signal=mailbox_signal,
            as_of_date=as_of_date,
            temporal_hints=temporal_hints,
        )

    def resolve_email_identity(
        self,
        email: str,
        target_identity: str,
        evidence_records: List[Dict[str, Any]],
        known_attributes: Optional[Dict[str, Any]] = None,
        as_of_date: Optional[str] = None,
    ) -> IdentityResolutionVerdict:
        """Capability D: Resolve candidate email-to-identity relationships."""
        return self.resolution_engine.resolve(
            email=email,
            target_identity=target_identity,
            evidence_records=evidence_records,
            known_attributes=known_attributes,
            as_of_date=as_of_date,
        )

    def execute(self, inputs: Dict[str, Any] | str, corpus: Any = None) -> Dict[str, Any]:
        """Uniform execution entrypoint called by InvestigationEngine and adapters."""
        if isinstance(inputs, str):
            inputs = {"query": inputs}
        start_t = time.perf_counter()
        operation = inputs.get("operation") or inputs.get("capability_id") or "auto"
        query = inputs.get("query", "")
        email = inputs.get("email") or inputs.get("target_email")
        target_identity = inputs.get("target_identity") or inputs.get("identity")
        identifier = inputs.get("identifier") or inputs.get("username") or inputs.get("phone") or query
        as_of_date = inputs.get("as_of_date")

        # Infer email from query if not provided
        if not email and "@" in query:
            words = query.split()
            for w in words:
                clean_w = w.strip(".,;:\"'<>()[]{}")
                if "@" in clean_w and "." in clean_w:
                    email = clean_w
                    break

        account_observations: List[AccountObservation] = []
        email_candidates: List[EmailCandidate] = []
        verification_result: Optional[EmailVerificationResult] = None
        resolution_verdict: Optional[IdentityResolutionVerdict] = None

        # Execute appropriate capability
        should_run_accounts = (
            "account" in operation
            or operation == "auto"
            or "account" in query.lower()
            or "profile" in query.lower()
            or bool(email and not inputs.get("username") and not inputs.get("phone"))
        )
        if should_run_accounts and email:
            account_observations = self.discover_accounts_for_email(
                email=email,
                target_identity=target_identity,
                corpus=corpus,
            )

        should_run_identity = (
            "identity_to_email" in operation
            or operation == "auto"
            or bool(inputs.get("username") or inputs.get("phone") or (target_identity and not email))
        )
        ident_target = (
            inputs.get("identifier")
            or inputs.get("username")
            or inputs.get("phone")
            or identifier
            or (target_identity if not email else None)
        )
        if should_run_identity and ident_target:
            gen_cand = inputs.get(
                "generate_candidates",
                any(w in query.lower() for w in ["generate", "candidate", "pattern", "infer", "guess", "schema"]),
            )
            email_candidates = self.discover_emails_for_identity(
                identifier=ident_target,
                target_name=target_identity,
                org_domain=inputs.get("org_domain"),
                corpus=corpus,
                generate_inferred_candidates=gen_cand,
            )

        if "verification" in operation or (email and inputs.get("verify", False)):
            if email:
                verification_result = self.verify_email_address(
                    email=email,
                    target_identity=target_identity,
                    context_evidence=inputs.get("context_evidence"),
                    mailbox_signal=inputs.get("mailbox_signal"),
                    as_of_date=as_of_date,
                    temporal_hints=inputs.get("temporal_hints"),
                )

        if "resolution" in operation or inputs.get("resolve", False):
            resolution_verdict = self.resolve_email_identity(
                email=email or "",
                target_identity=target_identity or "",
                evidence_records=inputs.get("context_evidence", []),
                known_attributes=inputs.get("known_attributes"),
                as_of_date=as_of_date,
            )

        elapsed = time.perf_counter() - start_t

        # Convert to standardized observation documents for InvestigationEngine
        obs_documents = []
        for obs in account_observations:
            obs_documents.append({
                "doc_id": f"acc_{uuid.uuid4().hex[:8]}",
                "title": f"Account Presence: {obs.platform}",
                "url": obs.canonical_url,
                "text": f"Platform: {obs.platform} | Email: {obs.observed_email} | Passage: {obs.evidence_passage}",
                "source_type": "account_observation",
                "payload": obs.model_dump(),
                "epistemic_status": "OBSERVATION",
                "is_authoritative": False,
            })

        for cand in email_candidates:
            obs_documents.append({
                "doc_id": f"eml_{uuid.uuid4().hex[:8]}",
                "title": f"Email Candidate: {cand.email}",
                "url": cand.source_provenance,
                "text": f"Candidate Email: {cand.email} | Status: {cand.epistemic_status} | Method: {cand.derivation_method} | Passage: {cand.evidence_passage}",
                "source_type": "email_candidate",
                "payload": cand.model_dump(),
                "epistemic_status": cand.epistemic_status,
                "is_authoritative": False,
            })

        return {
            "execution_id": f"exec_{uuid.uuid4().hex[:8]}",
            "runtime_sec": elapsed,
            "email": email,
            "target_identity": target_identity,
            "accounts_discovered": [o.model_dump() for o in account_observations],
            "emails_discovered": [c.model_dump() for c in email_candidates],
            "verification": verification_result.model_dump() if verification_result else None,
            "resolution": resolution_verdict.model_dump() if resolution_verdict else None,
            "documents": obs_documents,
            "documents_count": len(obs_documents),
        }
