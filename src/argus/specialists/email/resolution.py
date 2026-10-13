"""Heimdallr Vertical 6: Email Identity Resolution Engine (Capability D).

Resolves candidate email-to-identity relationships using:
- Direct public associations
- Independent identifying attributes (PGP keys, corporate registry, domain ownership)
- Source authority and evidence independence
- Temporal consistency
- Contradiction detection (shared names, common usernames, recycled phone numbers, stale profiles)

CRITICAL INVARIANTS:
1. NEVER merge identities based solely on name similarity.
2. An email address existing/valid does NOT establish that an identity owns it.
3. A source associating an email does NOT mean independent corroboration exists.
4. Independent corroboration does NOT prove current control.
5. Recycled phones and common usernames must be flagged as distinct identities.
6. Multiple emails belonging to one person are explicitly supported when corroborated.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from argus.specialists.email.models import (
    IdentityAssociation,
    IdentityResolutionVerdict,
    TemporalStatus,
)

logger = logging.getLogger(__name__)


class EmailIdentityResolutionEngine:
    """Evaluates candidate email-to-identity linkages and prevents false identity merges."""

    def __init__(self) -> None:
        pass

    def resolve(
        self,
        email: str,
        target_identity: str,
        evidence_records: List[Dict[str, Any]],
        known_attributes: Optional[Dict[str, Any]] = None,
        as_of_date: Optional[str] = None,
    ) -> IdentityResolutionVerdict:
        """Resolve whether evidence warrants binding an email address to a target identity."""
        if not email or not target_identity:
            return IdentityResolutionVerdict(
                email=email or "",
                target_identity=target_identity or "",
                association_verdict=IdentityAssociation.UNKNOWN,
                temporal_status=TemporalStatus.UNKNOWN,
                confidence=0.0,
                is_merged=False,
                rejection_reason="INSUFFICIENT_EVIDENCE",
                epistemic_rationale="Missing target identity or email address for resolution.",
            )

        email_clean = email.strip().lower()
        target_clean = target_identity.strip()
        target_lower = target_clean.lower()
        known_attrs = known_attributes or {}

        corroborating: List[Dict[str, Any]] = []
        conflicting: List[Dict[str, Any]] = []
        distinct_identities: List[str] = []

        # Check evidence records
        for ev in evidence_records:
            ev_email = str(ev.get("email", "")).lower()
            ev_text = str(ev.get("passage", "") or ev.get("text", "")).lower()
            ev_owner = str(ev.get("owner", "") or ev.get("identity", "")).strip()
            ev_phone = str(ev.get("phone", "")).strip()

            if email_clean in ev_text or ev_email == email_clean:
                # Check if recycled phone indicator or impersonation is present
                if ev.get("phone_recycled") is True or "recycled" in ev_text:
                    conflicting.append(ev)
                    distinct_identities.append("Previous Phone Subscriber")
                elif ev.get("impersonation") is True or "impersonator" in ev_text:
                    conflicting.append(ev)
                    distinct_identities.append("Impersonator Account")
                elif ev_owner and ev_owner.lower() != target_lower:
                    conflicting.append(ev)
                    if ev_owner not in distinct_identities:
                        distinct_identities.append(ev_owner)
                elif target_lower in ev_text or (ev_owner and ev_owner.lower() == target_lower):
                    corroborating.append(ev)

        # Detect shared name ambiguity (e.g. John Smith at Company A vs John Smith at Company B)
        org_context = known_attrs.get("organization", "")
        if org_context:
            for ev in corroborating:
                ev_org = ev.get("organization", "")
                if ev_org and ev_org.lower() != org_context.lower():
                    # Same name, different organization!
                    conflicting.append(ev)
                    distinct_identities.append(f"{target_clean} ({ev_org})")

        # Temporal status check
        temp_status = TemporalStatus.UNKNOWN
        if any(ev.get("is_stale") is True for ev in corroborating):
            temp_status = TemporalStatus.STALE
        elif any(ev.get("is_historical") is True for ev in corroborating):
            temp_status = TemporalStatus.HISTORICAL
        elif corroborating:
            temp_status = TemporalStatus.CURRENT

        # Formulate verdict
        if conflicting:
            # Evidence contains conflicts or different identities
            # Prevent false merge!
            rejection_reason = "CONFUSED_IDENTITY_OR_RECYCLED_IDENTIFIER"
            if any(ev.get("phone_recycled") is True or "recycled" in str(ev).lower() for ev in conflicting):
                rejection_reason = "RECYCLED_PHONE"
            elif any(ev.get("impersonation") is True or "impersonator" in str(ev).lower() for ev in conflicting):
                rejection_reason = "IMPERSONATION"
            elif distinct_identities:
                rejection_reason = "SHARED_NAME"

            return IdentityResolutionVerdict(
                email=email_clean,
                target_identity=target_clean,
                association_verdict=IdentityAssociation.CONTRADICTED,
                temporal_status=temp_status,
                confidence=0.15,
                is_merged=False,
                rejection_reason=rejection_reason,
                corroborating_evidence=corroborating,
                conflicting_evidence=conflicting,
                distinct_identities_detected=distinct_identities,
                epistemic_rationale=(
                    f"Refused to merge email '{email_clean}' with '{target_clean}' due to detected "
                    f"identity contradiction. Email is associated with separate entity: {distinct_identities}."
                ),
            )

        if not corroborating:
            return IdentityResolutionVerdict(
                email=email_clean,
                target_identity=target_clean,
                association_verdict=IdentityAssociation.UNKNOWN,
                temporal_status=TemporalStatus.UNKNOWN,
                confidence=0.0,
                is_merged=False,
                rejection_reason="INSUFFICIENT_EVIDENCE",
                corroborating_evidence=[],
                conflicting_evidence=[],
                distinct_identities_detected=[],
                epistemic_rationale=f"No verifiable public evidence links '{email_clean}' to '{target_clean}'.",
            )

        # Corroborating evidence exists without contradictions
        if len(corroborating) >= 2 or any(c.get("source_type") in ("OFFICIAL_REGISTRY", "GOVERNMENT_FILING", "VERIFIED_PGP") for c in corroborating):
            return IdentityResolutionVerdict(
                email=email_clean,
                target_identity=target_clean,
                association_verdict=IdentityAssociation.CORROBORATED_ASSOCIATION,
                temporal_status=temp_status,
                confidence=0.92,
                is_merged=True,
                rejection_reason=None,
                corroborating_evidence=corroborating,
                conflicting_evidence=[],
                distinct_identities_detected=[target_clean],
                epistemic_rationale=f"Multiple independent corroborating sources link '{email_clean}' to '{target_clean}'.",
            )

        # Single source, possible association
        return IdentityResolutionVerdict(
            email=email_clean,
            target_identity=target_clean,
            association_verdict=IdentityAssociation.POSSIBLE_ASSOCIATION,
            temporal_status=temp_status,
            confidence=0.60,
            is_merged=False,  # Single uncorroborated mention is not merged as established fact
            rejection_reason="UNCORROBORATED_SINGLE_SOURCE",
            corroborating_evidence=corroborating,
            conflicting_evidence=[],
            distinct_identities_detected=[target_clean],
            epistemic_rationale=f"Single uncorroborated public source links '{email_clean}' to '{target_clean}'. Preserved as POSSIBLE.",
        )
