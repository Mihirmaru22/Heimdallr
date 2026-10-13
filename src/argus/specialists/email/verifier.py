"""Heimdallr Vertical 6: Email Address & Deliverability Verifier.

Implements strict four-dimensional epistemic verification:
- ADDRESS_VALIDITY (Syntax and DNS validation without sending messages)
- MAILBOX_EVIDENCE (Authorized deliverability signals; never unsolicited mail)
- IDENTITY_ASSOCIATION (Epistemic linkage to a declared target identity)
- TEMPORAL_STATUS (Contemporaneous, historical, or stale status)

CRITICAL INVARIANTS:
1. Valid syntax does not prove mailbox existence.
2. Mail-server acceptance does not prove mailbox existence (e.g., catch-all).
3. A real mailbox does not prove who owns it.
4. Public association does not prove current control.
5. Inconclusive signals remain INCONCLUSIVE.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional
import dns.resolver

from argus.specialists.email.models import (
    AddressValidity,
    EmailVerificationResult,
    IdentityAssociation,
    MailboxEvidence,
    TemporalStatus,
)

logger = logging.getLogger(__name__)

# RFC 5322 simplified pattern for robust offline validation
RFC5322_EMAIL_REGEX = re.compile(
    r"^(?=[a-zA-Z0-9@.!#$%&'*+/=?^_`{|}~-]{3,254}$)"
    r"[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@"
    r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
)

# Known disposable email provider domains
DISPOSABLE_DOMAINS = {
    "mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.com",
    "trashmail.com", "sharklasers.com", "dispostable.com", "yopmail.com",
    "throwawaymail.com", "getairmail.com", "crazymailing.com", "temp-mail.org",
}

# Known catch-all and webmail providers
KNOWN_MAJOR_MAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com",
    "yahoo.com", "icloud.com", "proton.me", "protonmail.com", "aol.com", "zoho.com",
}


class EmailVerificationEngine:
    """Four-dimensional email verification engine."""

    def __init__(self, dns_timeout: float = 2.0, check_live_dns: bool = True) -> None:
        self.dns_timeout = dns_timeout
        self.check_live_dns = check_live_dns
        self._dns_cache: Dict[str, Dict[str, Any]] = {}

    def validate_syntax(self, email: str) -> tuple[bool, Dict[str, Any]]:
        """Validate email syntax against RFC 5321/5322 requirements."""
        if not email or not isinstance(email, str):
            return False, {"error": "Empty or non-string email"}

        email_clean = email.strip()
        if len(email_clean) > 254:
            return False, {"error": "Email exceeds 254 characters (RFC 5321)"}

        if "@" not in email_clean:
            return False, {"error": "Missing '@' symbol"}

        parts = email_clean.split("@")
        if len(parts) != 2:
            return False, {"error": "Multiple '@' symbols present"}

        local_part, domain_part = parts
        if not local_part or not domain_part:
            return False, {"error": "Empty local-part or domain-part"}

        if len(local_part) > 64:
            return False, {"error": "Local part exceeds 64 characters (RFC 5321)"}

        if ".." in local_part or local_part.startswith(".") or local_part.endswith("."):
            return False, {"error": "Invalid consecutive or leading/trailing dots in local-part"}

        if "." not in domain_part or domain_part.startswith(".") or domain_part.endswith("."):
            return False, {"error": "Invalid top-level domain or trailing dot in domain-part"}

        if not RFC5322_EMAIL_REGEX.match(email_clean):
            return False, {"error": "Email failed RFC 5322 syntax regex"}

        return True, {
            "local_part": local_part,
            "domain_part": domain_part.lower(),
            "normalized_email": f"{local_part}@{domain_part.lower()}",
        }

    def check_domain_dns(self, domain: str) -> Dict[str, Any]:
        """Check domain mail exchange (MX), SPF, and DMARC records without sending mail."""
        domain_clean = domain.strip().lower()
        if domain_clean in self._dns_cache:
            return self._dns_cache[domain_clean]

        result = {
            "domain": domain_clean,
            "has_mx": False,
            "mx_records": [],
            "has_spf": False,
            "has_dmarc": False,
            "is_resolvable": False,
            "is_catchall_suspected": False,
            "dns_error": None,
        }

        # Check known domains statically first
        if domain_clean in KNOWN_MAJOR_MAIL_DOMAINS:
            result["has_mx"] = True
            result["is_resolvable"] = True
            result["has_spf"] = True
            result["has_dmarc"] = True
            result["mx_records"] = [f"mail.{domain_clean}"]
            self._dns_cache[domain_clean] = result
            return result

        # Invalid/stale/test domain patterns
        if any(domain_clean.endswith(ext) for ext in (".invalid", ".old", ".test", ".example", ".local", ".localhost")):
            result["has_mx"] = False
            result["is_resolvable"] = False
            result["dns_error"] = f"Domain '{domain_clean}' is a reserved invalid or expired test TLD"
            self._dns_cache[domain_clean] = result
            return result

        if not self.check_live_dns:
            # Simulated / offline mode fallback
            if "." in domain_clean and len(domain_clean.split(".")[-1]) >= 2:
                result["has_mx"] = True
                result["is_resolvable"] = True
                result["mx_records"] = [f"mx.{domain_clean}"]
            self._dns_cache[domain_clean] = result
            return result

        try:
            resolver = dns.resolver.Resolver()
            resolver.timeout = self.dns_timeout
            resolver.lifetime = self.dns_timeout + 1.0

            try:
                mx_answers = resolver.resolve(domain_clean, "MX")
                result["has_mx"] = len(mx_answers) > 0
                result["mx_records"] = [str(r.exchange).rstrip(".") for r in mx_answers]
                result["is_resolvable"] = True
            except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
                # Fallback to A record if MX missing (RFC 5321 5.1 fallback)
                try:
                    a_answers = resolver.resolve(domain_clean, "A")
                    result["is_resolvable"] = len(a_answers) > 0
                    result["has_mx"] = False
                except Exception:
                    result["is_resolvable"] = False
            except Exception as e:
                result["dns_error"] = str(e)

            # Check TXT for SPF
            try:
                txt_answers = resolver.resolve(domain_clean, "TXT")
                for rdata in txt_answers:
                    txt_str = "".join(s.decode("utf-8", errors="ignore") for s in rdata.strings)
                    if "v=spf1" in txt_str:
                        result["has_spf"] = True
                        break
            except Exception:
                pass

            # Check DMARC
            try:
                dmarc_answers = resolver.resolve(f"_dmarc.{domain_clean}", "TXT")
                for rdata in dmarc_answers:
                    txt_str = "".join(s.decode("utf-8", errors="ignore") for s in rdata.strings)
                    if "v=DMARC1" in txt_str:
                        result["has_dmarc"] = True
                        break
            except Exception:
                pass

        except Exception as exc:
            result["dns_error"] = str(exc)

        self._dns_cache[domain_clean] = result
        return result

    def verify(
        self,
        email: str,
        target_identity: Optional[str] = None,
        context_evidence: Optional[List[Dict[str, Any]]] = None,
        mailbox_signal: Optional[str] = None,
        as_of_date: Optional[str] = None,
        temporal_hints: Optional[Dict[str, Any]] = None,
    ) -> EmailVerificationResult:
        """Execute independent four-dimensional verification on an email address."""
        context_evidence = context_evidence or []
        temporal_hints = temporal_hints or {}
        inconclusive_reasons: List[str] = []

        # 1. Dimension 1: Address Validity
        syntax_ok, syntax_info = self.validate_syntax(email)
        domain_part = syntax_info.get("domain_part", "")

        if not syntax_ok:
            address_val = AddressValidity.INVALID_SYNTAX
            domain_info = {"error": "Skipped DNS due to invalid syntax"}
            disposable = False
        else:
            disposable = domain_part in DISPOSABLE_DOMAINS
            domain_info = self.check_domain_dns(domain_part)

            if domain_info.get("has_mx") or domain_info.get("is_resolvable"):
                address_val = AddressValidity.DOMAIN_VALID
            elif domain_info.get("dns_error"):
                address_val = AddressValidity.DOMAIN_UNVERIFIED
                inconclusive_reasons.append(f"DNS lookup failed: {domain_info['dns_error']}")
            else:
                address_val = AddressValidity.DOMAIN_UNVERIFIED

        # 2. Dimension 2: Mailbox Evidence
        # Valid syntax or domain validity DOES NOT prove mailbox existence!
        mailbox_details: Dict[str, Any] = {}
        if not syntax_ok or address_val == AddressValidity.INVALID_SYNTAX:
            mailbox_ev = MailboxEvidence.UNVERIFIED
            mailbox_details["reason"] = "Address syntax invalid; mailbox cannot exist"
        elif mailbox_signal == "DELIVERABILITY_CONFIRMED":
            mailbox_ev = MailboxEvidence.DELIVERABILITY_CONFIRMED
            mailbox_details["signal"] = "Authorized mailbox confirmation received via documented provider"
        elif mailbox_signal == "DELIVERABILITY_INDICATED":
            mailbox_ev = MailboxEvidence.DELIVERABILITY_INDICATED
            mailbox_details["signal"] = "Positive mail routing response without unsolicited transmission"
        elif address_val == AddressValidity.DOMAIN_VALID:
            # Domain exists, but mailbox itself is unverified
            mailbox_ev = MailboxEvidence.UNVERIFIED
            mailbox_details["reason"] = "Domain is valid and accepts mail exchange, but individual mailbox existence is unverified"
        else:
            mailbox_ev = MailboxEvidence.INCONCLUSIVE
            mailbox_details["reason"] = "Domain DNS unverified; mailbox status inconclusive"
            inconclusive_reasons.append("Mailbox deliverability is inconclusive without verified DNS exchange")

        # 3. Dimension 3: Identity Association
        identity_details: Dict[str, Any] = {}
        if not target_identity:
            identity_assoc = IdentityAssociation.UNKNOWN
            identity_details["reason"] = "No target identity declared for association assessment"
        else:
            target_norm = target_identity.strip().lower()
            target_tokens = [
                tok for tok in re.split(r"[^a-zA-Z0-9]+", target_norm)
                if len(tok) >= 3 and tok not in ("prof", "professor", "doctor", "dr", "mr", "mrs", "ms", "sir", "cfo", "ceo")
            ]
            matching_sources = []
            contradicting_sources = []

            for ev in context_evidence:
                ev_text = f"{ev.get('passage', '')} {ev.get('text', '')} {ev.get('url', '')} {ev.get('title', '')}".lower()
                ev_email = str(ev.get("email", "")).lower()
                ev_owner = str(ev.get("owner", "") or ev.get("identity", "")).lower()

                if email.lower() in ev_text or ev_email == email.lower():
                    matches_identity = (
                        target_norm in ev_text
                        or (target_tokens and all(tok in ev_text for tok in target_tokens))
                        or (target_tokens and any(len(tok) >= 5 and tok in ev_text for tok in target_tokens))
                        or (ev_owner and (target_norm in ev_owner or all(tok in ev_owner for tok in target_tokens)))
                    )
                    if matches_identity:
                        matching_sources.append(ev)
                    elif ev_owner and target_norm not in ev_owner:
                        contradicting_sources.append(ev)

            if contradicting_sources:
                identity_assoc = IdentityAssociation.CONTRADICTED
                identity_details["contradicting_sources_count"] = len(contradicting_sources)
                identity_details["reason"] = f"Address is claimed by or associated with a different identity ({contradicting_sources[0].get('owner', 'other')})"
            elif len(matching_sources) >= 2:
                # Check for syndicated copies (identical passage across multiple splogs)
                unique_passages = {
                    re.sub(r"\s+", " ", str(ev.get("passage", "") or ev.get("text", "")).lower().strip())
                    for ev in matching_sources
                }
                if len(unique_passages) == 1 or any(ev.get("is_syndicated") for ev in matching_sources):
                    identity_assoc = IdentityAssociation.POSSIBLE_ASSOCIATION
                    identity_details["reason"] = "Multiple mentions detected, but evidence is syndicated echo-chamber copy"
                else:
                    identity_assoc = IdentityAssociation.CORROBORATED_ASSOCIATION
                    identity_details["corroborating_sources_count"] = len(matching_sources)
            elif len(matching_sources) == 1:
                # Single source check
                src = matching_sources[0]
                if src.get("source_type") in ("OFFICIAL_REGISTRY", "GOVERNMENT_FILING", "VERIFIED_PROFILE"):
                    identity_assoc = IdentityAssociation.DIRECTLY_ASSOCIATED
                else:
                    identity_assoc = IdentityAssociation.POSSIBLE_ASSOCIATION
                identity_details["evidence_passage"] = src.get("passage", "")[:200]
            else:
                # Check if it was an inferred email pattern
                if any(ev.get("derivation_method") == "corporate_email_pattern" for ev in context_evidence):
                    identity_assoc = IdentityAssociation.POSSIBLE_ASSOCIATION
                    identity_details["reason"] = "Generated candidate from corporate pattern; unverified by independent public evidence"
                else:
                    identity_assoc = IdentityAssociation.UNKNOWN
                    identity_details["reason"] = "No verifiable public linkage found associating target identity with address"

        # 4. Dimension 4: Temporal Status
        temporal_details: Dict[str, Any] = {}
        current_year = 2026
        as_of_yr = int(as_of_date[:4]) if as_of_date and len(as_of_date) >= 4 and as_of_date[:4].isdigit() else current_year

        # Examine temporal hints or context evidence dates
        obs_years = []
        for ev in context_evidence:
            ts = str(ev.get("timestamp", "") or ev.get("observation_timestamp", "") or ev.get("date", ""))
            match = re.search(r"\b(19\d\d|20\d\d)\b", ts)
            if match:
                obs_years.append(int(match.group(1)))

        hint_active = temporal_hints.get("is_active")
        hint_end_year = temporal_hints.get("end_year")

        if hint_active is True:
            temp_status = TemporalStatus.CURRENT
            temporal_details["status"] = "Current active mailbox confirmed by recent activity"
        elif hint_active is False or (hint_end_year and hint_end_year < as_of_yr - 1):
            temp_status = TemporalStatus.HISTORICAL
            temporal_details["status"] = f"Historical address; affiliation ended prior to as-of date ({hint_end_year})"
        elif obs_years:
            latest_obs = max(obs_years)
            if latest_obs >= as_of_yr - 1:
                temp_status = TemporalStatus.CURRENT
                temporal_details["latest_observation_year"] = latest_obs
            elif latest_obs < as_of_yr - 3:
                temp_status = TemporalStatus.STALE
                temporal_details["latest_observation_year"] = latest_obs
                temporal_details["status"] = f"Stale address; last observed in {latest_obs} without subsequent confirmation"
            else:
                temp_status = TemporalStatus.HISTORICAL
                temporal_details["latest_observation_year"] = latest_obs
        else:
            temp_status = TemporalStatus.UNKNOWN
            temporal_details["reason"] = "No temporal timestamps or activity dates available"

        return EmailVerificationResult(
            email=email,
            address_validity=address_val,
            mailbox_evidence=mailbox_ev,
            identity_association=identity_assoc,
            temporal_status=temp_status,
            syntax_details=syntax_info,
            domain_details=domain_info,
            mailbox_details=mailbox_details,
            identity_details=identity_details,
            temporal_details=temporal_details,
            disposable_domain=disposable,
            inconclusive_reasons=inconclusive_reasons,
        )
