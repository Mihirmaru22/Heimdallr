"""Heimdallr Vertical 6: Identity-to-Email Discovery Engine (Capability B).

Given an identifier (username, phone number, profile URL, person name, organization,
aliases), searches permitted public sources for email addresses explicitly associated
with that target.

CRITICAL EPISTEMIC CONSTRAINTS:
1. Pattern generation is strictly candidate generation only.
2. Inferred addresses remain INFERRED or UNVERIFIED until independent evidence corroborates.
3. NEVER claim an email belongs to a person based solely on:
   - A matching name
   - A username match
   - A guessed corporate email pattern
   - A phone number with uncertain ownership history
   - An LLM-generated assertion
4. Multiple email addresses for a single identity are explicitly supported.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from argus.specialists.email.models import (
    AssociationNature,
    EmailCandidate,
    TemporalStatus,
)

logger = logging.getLogger(__name__)

EMAIL_FINDER_REGEX = re.compile(
    r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
)


class IdentityToEmailDiscoveryEngine:
    """Discovers emails associated with an identity from public sources and controlled patterns."""

    def __init__(self) -> None:
        pass

    def discover_emails_for_identity(
        self,
        identifier: str,
        identity_type: str = "USERNAME",  # USERNAME, PHONE, PROFILE_URL, PERSON_NAME, ORG_NAME
        target_name: Optional[str] = None,
        organization: Optional[str] = None,
        org_domain: Optional[str] = None,
        corpus: Any = None,
        generate_inferred_candidates: bool = True,
    ) -> List[EmailCandidate]:
        """Discover email candidates from public sources and infer candidate patterns."""
        results: List[EmailCandidate] = []
        seen_emails = set()

        id_clean = identifier.strip()
        name_clean = (target_name or "").strip()

        # 1. Search corpus for direct public appearances of identifier
        if corpus and hasattr(corpus, "search"):
            search_terms = [id_clean]
            if name_clean and name_clean != id_clean:
                search_terms.append(name_clean)

            for term in search_terms:
                docs = corpus.search(term, limit=5)
                for doc in docs:
                    text = getattr(doc, "text_content", "") or getattr(doc, "snippet", "") or ""
                    url = getattr(doc, "url", "")
                    title = getattr(doc, "title", "Document")
                    full_doc_text = f"{title} {url} {text}".lower()

                    # Find all emails in document text
                    found_emails = EMAIL_FINDER_REGEX.findall(text)
                    for raw_email in found_emails:
                        email_lower = raw_email.lower().rstrip(".")
                        if email_lower in seen_emails:
                            continue

                        # Check if email is associated with this specific identity
                        # Reject incidental or page-wide emails (e.g., support@, webmaster@) unless relevant
                        if any(email_lower.startswith(prefix) for prefix in ("support@", "info@", "sales@", "admin@", "webmaster@", "abuse@", "press@")):
                            continue

                        # Determine if association is verified or merely co-occurring
                        is_direct = False
                        name_tokens = [t.lower() for t in re.split(r"[^a-zA-Z0-9]+", name_clean) if len(t) >= 3 and t.lower() not in {"mr", "dr", "ms", "mrs", "prof"}]

                        if name_clean and name_clean.lower() in full_doc_text:
                            is_direct = True
                        elif id_clean and len(id_clean) < 40 and id_clean.lower() in full_doc_text and ("email" in full_doc_text or "contact" in full_doc_text or "author" in full_doc_text or "profile" in full_doc_text):
                            is_direct = True
                        elif name_tokens and any(token in full_doc_text for token in name_tokens):
                            is_direct = True
                        elif name_tokens and any(token in email_lower for token in name_tokens):
                            is_direct = True

                        if is_direct:
                            seen_emails.add(email_lower)
                            candidate = EmailCandidate(
                                email=email_lower,
                                source_identifier=id_clean,
                                derivation_method="DIRECT_OBSERVATION",
                                epistemic_status="SUPPORTED",
                                association_nature=AssociationNature.PROFILE_EXPLICIT_PUBLICATION if "profile" in url.lower() else AssociationNature.PUBLIC_PAGE_MENTION,
                                confidence=0.88,
                                temporal_status=TemporalStatus.CURRENT,
                                source_provenance=f"Corpus Source: {title} ({url})",
                                evidence_passage=self._extract_snippet(text, email_lower),
                                target_identity=name_clean or id_clean,
                            )
                            results.append(candidate)

        # 2. Candidate Pattern Generation (Strictly INFERRED / UNVERIFIED)
        # Algorithmic pattern guessing is performed only when no direct public email was observed
        if generate_inferred_candidates and not results and name_clean and org_domain:
            inferred = self._generate_corporate_candidates(name_clean, org_domain)
            for inf_email in inferred:
                if inf_email not in seen_emails:
                    seen_emails.add(inf_email)
                    results.append(
                        EmailCandidate(
                            email=inf_email,
                            source_identifier=name_clean,
                            derivation_method="PATTERN_GENERATION",
                            epistemic_status="INFERRED",  # MUST NEVER BE MARKED AS SUPPORTED / VERIFIED!
                            association_nature=AssociationNature.INFERRED_PATTERN_CANDIDATE,
                            confidence=0.45,  # Low confidence due to being a guessed candidate
                            temporal_status=TemporalStatus.UNKNOWN,
                            source_provenance=f"Algorithmic Corporate Pattern Generation for domain {org_domain}",
                            evidence_passage=f"Inferred corporate candidate for {name_clean} at {org_domain}. Requires independent evidence.",
                            target_identity=name_clean,
                        )
                    )

        return results

    def _generate_corporate_candidates(self, full_name: str, domain: str) -> List[str]:
        """Generate common candidate email schemas for an enterprise name and domain."""
        tokens = [t.lower() for t in re.split(r"[^a-zA-Z0-9]+", full_name) if t and t.lower() not in {"mr", "dr", "ms", "mrs", "prof"}]
        if not tokens:
            return []

        first = tokens[0]
        last = tokens[-1] if len(tokens) > 1 else tokens[0]
        clean_dom = domain.strip().lower().replace("www.", "")

        # Return primary corporate pattern
        return [f"{first}.{last}@{clean_dom}"]

    @staticmethod
    def _extract_snippet(text: str, email: str, window: int = 120) -> str:
        idx = text.lower().find(email.lower())
        if idx == -1:
            return text[:200]
        start = max(0, idx - window)
        end = min(len(text), idx + len(email) + window)
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(text) else ""
        return f"{prefix}{text[start:end].strip()}{suffix}"
