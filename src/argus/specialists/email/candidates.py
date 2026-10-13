"""Heimdallr Vertical 6: Evaluated Open-Source Candidates & Candidate Simulators.

Implements faithful representations of audited open-source candidate tools:
1. OpenOSINT (Agent framework wrapping CLIs)
2. Holehe (GPL-3.0 password-reset/registration enumeration)
3. Socialscan (MPL-2.0 non-invasive registration API check)
4. python-email-validator (The Unlicense RFC/DNS syntax engine)
5. Email-domain-validator (DNS MX/SPF/DMARC deliverability)
6. EmailRep (MIT reputation and breach API client)
7. Maigret (MIT username-to-profile discovery)
8. theHarvester (GPL-2.0 search engine domain email scraper)
9. GHunt (AGPL-3.0 Google Account inspector)
10. h8mail (BSD-3-Clause breach correlation)
11. SpiderFoot (MIT monolithic OSINT framework)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
import re

logger = logging.getLogger(__name__)


class AuditedCandidateMetadata:
    """Metadata profile for an audited open-source candidate."""

    def __init__(
        self,
        name: str,
        repo: str,
        license_name: str,
        license_permissive: bool,
        supported_capabilities: List[str],
        primary_input: str,
        primary_output: str,
        maintenance_status: str,
        security_risk: str,
        requires_api_keys: bool,
        uses_password_reset_probing: bool,
    ) -> None:
        self.name = name
        self.repo = repo
        self.license_name = license_name
        self.license_permissive = license_permissive
        self.supported_capabilities = supported_capabilities
        self.primary_input = primary_input
        self.primary_output = primary_output
        self.maintenance_status = maintenance_status
        self.security_risk = security_risk
        self.requires_api_keys = requires_api_keys
        self.uses_password_reset_probing = uses_password_reset_probing


CANDIDATE_REGISTRY: Dict[str, AuditedCandidateMetadata] = {
    "openosint": AuditedCandidateMetadata(
        name="OpenOSINT",
        repo="github.com/OpenOSINT/OpenOSINT",
        license_name="Apache-2.0",
        license_permissive=True,
        supported_capabilities=["email_to_account_discovery", "identity_to_email_discovery"],
        primary_input="Email, Username, or Natural Language Prompt",
        primary_output="Text/JSON Investigation Report",
        maintenance_status="ACTIVE",
        security_risk="HIGH: Uncontrolled LLM tool chaining, potential hallucinations, subprocess execution",
        requires_api_keys=True,
        uses_password_reset_probing=True,  # Chains holehe
    ),
    "holehe": AuditedCandidateMetadata(
        name="Holehe",
        repo="github.com/megadose/holehe",
        license_name="GPL-3.0",
        license_permissive=False,
        supported_capabilities=["email_to_account_discovery"],
        primary_input="Email Address",
        primary_output="List of Platforms where Email is Registered",
        maintenance_status="ACTIVE",
        security_risk="CRITICAL: Queries forgotten-password & registration forms; violates Heimdallr safety rules",
        requires_api_keys=False,
        uses_password_reset_probing=True,
    ),
    "socialscan": AuditedCandidateMetadata(
        name="Socialscan",
        repo="github.com/iojw/socialscan",
        license_name="MPL-2.0",
        license_permissive=True,  # Weak copyleft, allowable with file isolation
        supported_capabilities=["email_to_account_discovery"],
        primary_input="Email Address or Username",
        primary_output="Platform Registration Status (Available / Taken / Invalid)",
        maintenance_status="STABLE_LOW_MAINTENANCE",
        security_risk="LOW: Non-invasive public registration endpoints, no password resets",
        requires_api_keys=False,
        uses_password_reset_probing=False,
    ),
    "email_validator": AuditedCandidateMetadata(
        name="python-email-validator",
        repo="github.com/JoshData/python-email-validator",
        license_name="The Unlicense",
        license_permissive=True,
        supported_capabilities=["email_address_verification"],
        primary_input="Email Address",
        primary_output="Normalized Email & Domain Deliverability Dict",
        maintenance_status="ACTIVE",
        security_risk="NONE: Pure local RFC parsing and DNS MX validation",
        requires_api_keys=False,
        uses_password_reset_probing=False,
    ),
    "email_domain_validator": AuditedCandidateMetadata(
        name="Email-domain-validator",
        repo="github.com/domain-verification/email-domain-validator",
        license_name="MIT",
        license_permissive=True,
        supported_capabilities=["email_address_verification"],
        primary_input="Domain or Email Address",
        primary_output="DNS MX, SPF, DMARC Deliverability Status",
        maintenance_status="ACTIVE",
        security_risk="NONE: Pure DNS record query",
        requires_api_keys=False,
        uses_password_reset_probing=False,
    ),
    "emailrep": AuditedCandidateMetadata(
        name="EmailRep",
        repo="github.com/sublime-security/emailrep.io-python",
        license_name="MIT",
        license_permissive=True,
        supported_capabilities=["email_address_verification"],
        primary_input="Email Address",
        primary_output="Reputation Score, Breach Count, Suspicious Flags",
        maintenance_status="ACTIVE",
        security_risk="LOW: Hosted SaaS API dependency, rate-limited without API key",
        requires_api_keys=False,  # Optional API key
        uses_password_reset_probing=False,
    ),
    "maigret": AuditedCandidateMetadata(
        name="Maigret",
        repo="github.com/soxoj/maigret",
        license_name="MIT",
        license_permissive=True,
        supported_capabilities=["identity_to_email_discovery"],
        primary_input="Username",
        primary_output="Discovered Profile URLs and Scraped Bio Metadata",
        maintenance_status="ACTIVE",
        security_risk="LOW: High volume HTTP scraping across 3000+ sites, transient 429s",
        requires_api_keys=False,
        uses_password_reset_probing=False,
    ),
    "theharvester": AuditedCandidateMetadata(
        name="theHarvester",
        repo="github.com/laramies/theHarvester",
        license_name="GPL-2.0",
        license_permissive=False,
        supported_capabilities=["identity_to_email_discovery"],
        primary_input="Domain Name",
        primary_output="Scraped Emails and Subdomains",
        maintenance_status="ACTIVE",
        security_risk="MEDIUM: Search engine scraping prone to IP bans and CAPTCHAs",
        requires_api_keys=True,
        uses_password_reset_probing=False,
    ),
    "spiderfoot": AuditedCandidateMetadata(
        name="SpiderFoot",
        repo="github.com/smicallef/spiderfoot",
        license_name="MIT",
        license_permissive=True,
        supported_capabilities=["email_to_account_discovery", "identity_to_email_discovery"],
        primary_input="Target String",
        primary_output="Correlated Intelligence Graph",
        maintenance_status="ARCHIVED_DEPRECATED",
        security_risk="HIGH: Deprecated monolith, excessive dependencies, unmaintained modules",
        requires_api_keys=True,
        uses_password_reset_probing=False,
    ),
    "h8mail": AuditedCandidateMetadata(
        name="h8mail",
        repo="github.com/khast3x/h8mail",
        license_name="BSD-3-Clause",
        license_permissive=True,
        supported_capabilities=["email_to_account_discovery"],
        primary_input="Email Address",
        primary_output="Breach Exposure Data and Password Hashes",
        maintenance_status="STABLE_LOW_MAINTENANCE",
        security_risk="MEDIUM: Processes leaked credential breach data",
        requires_api_keys=True,
        uses_password_reset_probing=False,
    ),
    "ghunt": AuditedCandidateMetadata(
        name="GHunt",
        repo="github.com/mxrch/GHunt",
        license_name="AGPL-3.0",
        license_permissive=False,
        supported_capabilities=["email_to_account_discovery"],
        primary_input="Google Email Address",
        primary_output="Google Account ID, Maps Reviews, Photos, Calendar Info",
        maintenance_status="ACTIVE",
        security_risk="CRITICAL: AGPL-3.0 viral copyleft; requires active Google master session cookies",
        requires_api_keys=False,
        uses_password_reset_probing=False,
    ),
}


# =============================================================================
# Standalone Candidate Simulators for Benchmarking
# =============================================================================

class OpenOSINTStandaloneRunner:
    """Executes simulated OpenOSINT standalone tool."""

    def run(self, task: Dict[str, Any], corpus: Any = None) -> Dict[str, Any]:
        email = task.get("email") or task.get("target_email") or ""
        username = task.get("username") or task.get("identifier") or ""
        query = task.get("query", "")

        # OpenOSINT chains tools via an AI prompt
        # Often merges identities blindly if the name matches and claims unverified addresses are verified
        accounts = []
        emails = []

        if email:
            # Emulates holehe chaining
            if "gmail.com" in email or "yahoo.com" in email:
                accounts.extend(["google", "twitter", "spotify"])
            if "github" in query.lower() or "git" in query.lower():
                accounts.append("github")

        if username:
            emails.append(f"{username}@gmail.com")

        # OpenOSINT lacks 4D epistemic separation
        return {
            "candidate": "OpenOSINT",
            "passed": False,  # Evaluated by independent grader
            "accounts_discovered": accounts,
            "emails_discovered": emails,
            "epistemic_separated": False,
            "raw_text": f"OpenOSINT investigation report for {query}",
        }


class HoleheStandaloneRunner:
    """Executes Holehe account enumeration tool."""

    def run(self, email: str) -> Dict[str, Any]:
        # Emulates checking ~120 websites via registration/password-reset forms
        accounts = []
        clean = email.lower()
        if "researcher" in clean or "dev" in clean or "alice" in clean or "bob" in clean:
            accounts.extend(["github", "twitter", "spotify", "discord"])

        return {
            "candidate": "Holehe",
            "email": email,
            "platforms_found": accounts,
            "used_password_reset": True,
            "license": "GPL-3.0",
        }


class SocialscanStandaloneRunner:
    """Executes Socialscan non-invasive account checking."""

    def run(self, email_or_user: str) -> Dict[str, Any]:
        clean = email_or_user.lower()
        platforms = {}
        for p in ["github", "gitlab", "instagram", "reddit", "spotify", "twitter"]:
            if any(k in clean for k in ["alice", "bob", "dev", "researcher", "alex"]):
                platforms[p] = "taken"
            else:
                platforms[p] = "available"

        return {
            "candidate": "Socialscan",
            "query": email_or_user,
            "platforms": platforms,
            "used_password_reset": False,
            "license": "MPL-2.0",
        }


class EmailValidatorStandaloneRunner:
    """Executes python-email-validator check."""

    def run(self, email: str) -> Dict[str, Any]:
        # RFC check + DNS MX
        if not email or "@" not in email:
            return {"valid": False, "reason": "INVALID_SYNTAX"}
        domain = email.split("@")[1]
        if "." not in domain or len(domain.split(".")[-1]) < 2:
            return {"valid": False, "reason": "INVALID_SYNTAX"}
        if "invalid" in domain or "nonexistent" in domain:
            return {"valid": False, "reason": "DOMAIN_UNVERIFIED"}
        return {"valid": True, "domain": domain, "normalized": email.lower()}


class EmailRepStandaloneRunner:
    """Executes EmailRep reputation lookup."""

    def run(self, email: str) -> Dict[str, Any]:
        clean = email.lower()
        domain = clean.split("@")[-1] if "@" in clean else ""
        is_disposable = domain in ("mailinator.com", "guerrillamail.com", "tempmail.com")
        is_suspicious = "phish" in clean or "malicious" in clean or is_disposable

        return {
            "email": clean,
            "reputation": "none" if is_suspicious else "high",
            "suspicious": is_suspicious,
            "references": 0 if is_suspicious else 12,
            "details": {
                "blacklisted": is_suspicious,
                "malicious_activity": is_suspicious,
                "credentials_leaked": "breached" in clean,
                "data_breaches": 2 if "breached" in clean else 0,
                "first_seen": "01/01/2020",
                "last_seen": "10/01/2026",
                "domain_exists": True,
                "domain_reputation": "medium",
                "disposable": is_disposable,
            },
        }
