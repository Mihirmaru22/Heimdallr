"""Heimdallr Vertical 6: Email-to-Account Discovery Engine (Capability A).

Given an email address, discovers publicly supported associations with
online accounts, profiles, organizations, and websites without bypassing
authentication, privacy controls, CAPTCHAs, or using password-reset workflows.

Strictly distinguishes between:
1. Address found on a public page (PUBLIC_PAGE_MENTION)
2. Profile explicitly publishes the address (PROFILE_EXPLICIT_PUBLICATION)
3. Platform provides an authorized account-presence signal (AUTHORIZED_PRESENCE_SIGNAL)
4. Address is confirmed to be associated with the target identity (CONFIRMED_IDENTITY_ASSOCIATION)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from argus.specialists.email.models import (
    AccountObservation,
    AssociationNature,
)

logger = logging.getLogger(__name__)


class EmailToAccountDiscoveryEngine:
    """Discovers account and profile presence from authorized public sources."""

    def __init__(self, authorized_platforms: Optional[List[str]] = None) -> None:
        self.authorized_platforms = authorized_platforms or [
            "github", "gitlab", "linkedin", "orcid", "google_scholar",
            "pypi", "npm", "kaggle", "huggingface", "keybase", "mastodon"
        ]

    def discover_accounts(
        self,
        email: str,
        target_identity: Optional[str] = None,
        corpus: Any = None,
        max_results: int = 10,
    ) -> List[AccountObservation]:
        """Search permitted public corpus and platform indexes for account observations."""
        email_clean = email.strip().lower()
        if not email_clean or "@" not in email_clean:
            return []

        observations: List[AccountObservation] = []
        target_norm = target_identity.strip().lower() if target_identity else ""

        # 1. Search corpus for direct public appearances
        if corpus and hasattr(corpus, "search"):
            docs = corpus.search(email_clean, limit=max_results)
            for doc in docs:
                url = getattr(doc, "url", "")
                text = getattr(doc, "text_content", "") or getattr(doc, "snippet", "") or ""
                title = getattr(doc, "title", "Discovered Web Page")
                source_type = getattr(doc, "source_type", "web_page")

                if email_clean not in text.lower() and email_clean not in url.lower():
                    continue

                # Determine platform
                platform = self._extract_platform(url)

                # Classify association nature strictly
                nature = AssociationNature.PUBLIC_PAGE_MENTION
                strength = 0.5
                verif_status = "UNVERIFIED"

                if "profile" in url.lower() or "author" in url.lower() or "/user/" in url.lower() or "github.com/" in url.lower():
                    if f"mailto:{email_clean}" in text.lower() or f"email: {email_clean}" in text.lower() or f"contact: {email_clean}" in text.lower():
                        nature = AssociationNature.PROFILE_EXPLICIT_PUBLICATION
                        strength = 0.85
                    else:
                        nature = AssociationNature.PUBLIC_PAGE_MENTION
                        strength = 0.65

                if target_norm and target_norm in text.lower():
                    if nature == AssociationNature.PROFILE_EXPLICIT_PUBLICATION:
                        nature = AssociationNature.CONFIRMED_IDENTITY_ASSOCIATION
                        strength = 0.95
                        verif_status = "CORROBORATED"

                # Extract concise snippet
                snippet = self._extract_snippet(text, email_clean)

                obs = AccountObservation(
                    platform=platform,
                    canonical_url=url,
                    observed_email=email_clean,
                    source_provenance=f"Corpus Document ({source_type}): {title}",
                    evidence_passage=snippet,
                    association_nature=nature,
                    association_strength=strength,
                    verification_status=verif_status,
                    account_identifier=self._extract_account_handle(url),
                    profile_metadata={
                        "title": title,
                        "source_type": source_type,
                    },
                )
                observations.append(obs)

        return observations

    def check_authorized_platform_signal(
        self,
        email: str,
        platform: str,
        simulated_record: Optional[Dict[str, Any]] = None,
    ) -> Optional[AccountObservation]:
        """Check authorized non-invasive account-presence signal (e.g., public API).

        NOTE: Strictly forbids password-reset probing or unauthorized scraping.
        Only uses authorized developer APIs or publicly published profile endpoints.
        """
        email_clean = email.strip().lower()
        plat_clean = platform.strip().lower()

        if plat_clean not in self.authorized_platforms and plat_clean != "custom_authorized":
            logger.warning(f"Platform {platform} is not authorized for non-invasive presence check.")
            return None

        if simulated_record:
            exists = simulated_record.get("account_exists", False)
            if not exists:
                return None

            url = simulated_record.get("canonical_url", f"https://{plat_clean}.com/users/{simulated_record.get('handle', 'unknown')}")
            handle = simulated_record.get("handle")
            is_explicit = simulated_record.get("explicitly_published", False)

            nature = AssociationNature.PROFILE_EXPLICIT_PUBLICATION if is_explicit else AssociationNature.AUTHORIZED_PRESENCE_SIGNAL
            strength = 0.80 if is_explicit else 0.60

            return AccountObservation(
                platform=plat_clean,
                canonical_url=url,
                observed_email=email_clean,
                source_provenance=f"Authorized Platform API / Signal: {plat_clean}",
                evidence_passage=simulated_record.get("evidence", f"Platform {plat_clean} confirmed active account presence."),
                association_nature=nature,
                association_strength=strength,
                verification_status="CORROBORATED" if is_explicit else "UNVERIFIED",
                account_identifier=handle,
                profile_metadata=simulated_record.get("metadata", {}),
            )

        return None

    @staticmethod
    def _extract_platform(url: str) -> str:
        """Extract recognizable platform name from URL."""
        url_lower = url.lower()
        for p in ["github", "gitlab", "linkedin", "orcid", "scholar.google", "pypi", "npm", "kaggle", "huggingface", "twitter", "x.com"]:
            if p in url_lower:
                return p.replace(".google", "_scholar").replace("x.com", "x")
        if "://" in url_lower:
            parts = url_lower.split("://")[1].split("/")[0]
            return parts.replace("www.", "")
        return "web_domain"

    @staticmethod
    def _extract_account_handle(url: str) -> Optional[str]:
        """Extract profile handle from URL path if applicable."""
        if not url:
            return None
        parts = [p for p in url.strip("/").split("/") if p and p not in ("http:", "https:", "www")]
        if len(parts) >= 2 and any(k in parts[0] for k in ["github.com", "gitlab.com", "huggingface.co", "keybase.io"]):
            return parts[1]
        return None

    @staticmethod
    def _extract_snippet(text: str, email: str, window: int = 120) -> str:
        """Extract contextual snippet around email occurrence."""
        idx = text.lower().find(email.lower())
        if idx == -1:
            return text[:200]
        start = max(0, idx - window)
        end = min(len(text), idx + len(email) + window)
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(text) else ""
        return f"{prefix}{text[start:end].strip()}{suffix}"
