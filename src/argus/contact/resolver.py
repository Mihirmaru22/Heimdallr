"""Tiered Contact Resolution Engine for Argus.

Provides privacy-compliant corporate email pattern inference, asynchronous DNS MX validation,
and facility switchboard/media contact capture across any industry domain.
"""

import asyncio
import logging
import re
import socket
from typing import Any
from urllib.parse import urlparse

import dns.asyncresolver

from argus.domain.claim import Claim, ClaimStatus
from argus.domain.entity import Entity
from argus.domain.event import EventType, ResearchEvent
from argus.domain.evidence import Evidence
from argus.storage.repository import ArgusRepository

logger = logging.getLogger(__name__)


class ContactResolutionEngine:
    """Resolves professional contact vectors for discovered personnel and facility assets."""

    def __init__(self, dns_timeout: float = 2.0) -> None:
        self.dns_timeout = dns_timeout
        self._domain_cache: dict[str, bool] = {}

    @staticmethod
    def infer_company_domain(text_or_url: str) -> str:
        """Infer primary corporate domain from company name or source URL."""
        if not text_or_url:
            return ""
        lower = text_or_url.lower()

        # Known enterprise mappings
        if "general motors" in lower or " gm " in lower or lower.startswith("gm ") or "gm.com" in lower:
            return "gm.com"
        if "ford" in lower:
            return "ford.com"
        if "stellantis" in lower or "chrysler" in lower or "fiat" in lower:
            return "stellantis.com"
        if "tesla" in lower:
            return "tesla.com"
        if "toyota" in lower:
            return "toyota.com"
        if "honda" in lower:
            return "honda.com"
        if "bmw" in lower:
            return "bmwgroup.com"
        if "volkswagen" in lower or " vw " in lower or lower.startswith("vw "):
            return "volkswagen.com"
        if "hyundai" in lower:
            return "hyundai.com"
        if "rivian" in lower:
            return "rivian.com"
        if "lucid" in lower:
            return "lucidmotors.com"

        # If it looks like a URL, extract domain
        if "://" in text_or_url or text_or_url.startswith("www."):
            parsed = urlparse(text_or_url if "://" in text_or_url else f"http://{text_or_url}")
            netloc = parsed.netloc or parsed.path
            for prefix in ("www.", "media.", "news.", "press.", "corporate.", "about."):
                if netloc.startswith(prefix):
                    netloc = netloc[len(prefix):]
            if ":" in netloc:
                netloc = netloc.split(":")[0]
            if "." in netloc:
                return netloc

        # Fallback: clean alpha characters + .com
        clean = re.sub(r"[^a-zA-Z0-9]+", "", lower)
        return f"{clean}.com" if clean else ""

    @staticmethod
    def infer_email(
        full_name: str,
        domain: str,
        pattern: str = "{first}.{last}",
    ) -> str:
        """Generate corporate email address according to specified schema.

        Supported tokens: {first}, {last}, {f}, {l}.
        """
        clean_domain = domain.strip().lower()
        if clean_domain.startswith("www."):
            clean_domain = clean_domain[4:]
        if "@" in clean_domain:
            clean_domain = clean_domain.split("@")[-1]

        # Tokenize name and filter titles/honorifics
        tokens = [
            t.lower()
            for t in re.split(r"[^a-zA-Z0-9]+", full_name.strip())
            if len(t) > 1 and t.lower() not in {
                "dr", "mr", "mrs", "ms", "prof", "phd", "jr", "sr", "ii", "iii", "esq"
            }
        ]
        if not tokens:
            return ""

        first = tokens[0]
        last = tokens[-1] if len(tokens) > 1 else tokens[0]
        f = first[0]
        l = last[0]

        local_part = pattern.format(first=first, last=last, f=f, l=l)
        return f"{local_part}@{clean_domain}"

    @staticmethod
    def detect_email_pattern_from_examples(
        examples: list[str], target_domain: str = ""
    ) -> str:
        """Detect dominant corporate email schema from observed public sample addresses."""
        pattern_counts: dict[str, int] = {
            "{first}.{last}": 0,
            "{f}{last}": 0,
            "{first}_{last}": 0,
            "{first}{last}": 0,
            "{first}": 0,
        }

        for email in examples:
            email_clean = email.strip().lower()
            if "@" not in email_clean:
                continue
            local, domain = email_clean.split("@", 1)
            if target_domain and target_domain not in domain:
                continue

            if "." in local:
                pattern_counts["{first}.{last}"] += 1
            elif "_" in local:
                pattern_counts["{first}_{last}"] += 1
            elif len(local) > 4:
                # heuristic: could be f+last or first+last
                pattern_counts["{first}.{last}"] += 1

        # Return most prevalent or default to first.last
        best_pattern = max(pattern_counts.items(), key=lambda x: x[1])
        return best_pattern[0] if best_pattern[1] > 0 else "{first}.{last}"

    async def verify_domain_mx(self, domain: str) -> bool:
        """Verify domain has active mail exchange (MX) records via asynchronous DNS."""
        clean_domain = domain.strip().lower()
        if clean_domain.startswith("www."):
            clean_domain = clean_domain[4:]
        if "@" in clean_domain:
            clean_domain = clean_domain.split("@")[-1]

        if not clean_domain:
            return False

        if clean_domain in self._domain_cache:
            return self._domain_cache[clean_domain]

        is_valid = False
        try:
            resolver = dns.asyncresolver.Resolver()
            resolver.timeout = self.dns_timeout
            resolver.lifetime = self.dns_timeout + 1.0
            answers = await resolver.resolve(clean_domain, "MX")
            is_valid = len(answers) > 0
        except Exception as exc:
            logger.debug(
                "DNS MX check failed for '%s' via dnspython (%s). Falling back to getaddrinfo.",
                clean_domain,
                exc,
            )
            # Socket fallback
            loop = asyncio.get_running_loop()
            try:
                await loop.getaddrinfo(clean_domain, 25, family=socket.AF_INET)
                is_valid = True
            except Exception:
                is_valid = False

        self._domain_cache[clean_domain] = is_valid
        return is_valid

    @staticmethod
    def extract_switchboard_numbers(text: str) -> list[dict[str, str]]:
        """Extract telephone numbers from text and classify as switchboard or media line."""
        results: list[dict[str, str]] = []
        phone_pattern = re.compile(
            r"(?:\+?1[-.\s]?)?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})"
        )

        for match in phone_pattern.finditer(text):
            formatted_phone = f"({match.group(1)}) {match.group(2)}-{match.group(3)}"

            # Get the specific line containing the phone number
            line_start = text.rfind("\n", 0, match.start())
            line_start = 0 if line_start == -1 else line_start + 1
            line_end = text.find("\n", match.end())
            line_end = len(text) if line_end == -1 else line_end

            line_text = text[line_start:line_end].lower()

            is_media = any(
                term in line_text
                for term in ["media", "press", "newsroom", "inquiries", "spokesperson", "public relations"]
            )

            contact_type = "HAS_MEDIA_CONTACT" if is_media else "HAS_FACILITY_PHONE"

            results.append({
                "phone": formatted_phone,
                "predicate": contact_type,
                "context": text[line_start:line_end].strip(),
            })

        # Deduplicate by formatted phone
        seen = set()
        deduped = []
        for r in results:
            if r["phone"] not in seen:
                seen.add(r["phone"])
                deduped.append(r)
        return deduped

    async def resolve_contacts_for_objective(
        self,
        objective_id: str,
        repo: ArgusRepository,
        default_domain: str | None = None,
    ) -> list[Claim]:
        """Infer corporate emails for leadership and extract facility switchboards."""
        entities = repo.list_entities(objective_id=objective_id)
        existing_claims = repo.list_claims(objective_id=objective_id)

        # 1. Determine target domain
        domain = default_domain or ""
        if not domain:
            for ent in entities:
                if ent.entity_type.lower() in ("company", "organization"):
                    clean = re.sub(r"[^a-zA-Z0-9]+", "", ent.canonical_name.lower())
                    domain = f"{clean}.com"
                    break

        if not domain and entities:
            clean = re.sub(r"[^a-zA-Z0-9]+", "", entities[0].canonical_name.lower())
            domain = f"{clean}.com"

        if not domain:
            return []

        # 2. Verify domain MX
        mx_valid = await self.verify_domain_mx(domain)
        confidence = 0.85 if mx_valid else 0.65

        created_claims: list[Claim] = []

        # 3. Infer corporate email for personnel
        existing_emails = {
            c.subject_entity_id
            for c in existing_claims
            if c.predicate.upper() == "HAS_EMAIL"
        }

        for ent in entities:
            if ent.entity_type.lower() == "person" and ent.entity_id not in existing_emails:
                inferred_email = self.infer_email(ent.canonical_name, domain)
                if not inferred_email:
                    continue

                claim = Claim(
                    objective_id=objective_id,
                    subject_entity_id=ent.entity_id,
                    predicate="HAS_EMAIL",
                    object_value=inferred_email,
                    status=ClaimStatus.INFERRED,
                    evidence_ids=[],
                    confidence=confidence,
                    derivation_method="corporate_email_pattern",
                    derivation_inputs=[ent.entity_id],
                    inference_reason=(
                        f"Inferred corporate email address using pattern for domain '{domain}' "
                        f"(DNS MX validated: {mx_valid}). Not directly observed in source text."
                    ),
                )
                repo.save_claim(claim)
                created_claims.append(claim)

                # Update entity attributes
                ent.attributes["email"] = inferred_email
                ent.attributes["email_status"] = "inferred"
                ent.attributes["is_inferred"] = True
                ent.attributes["domain_mx_verified"] = mx_valid
                repo.save_entity(ent)

                repo.record_event(
                    ResearchEvent(
                        objective_id=objective_id,
                        event_type=EventType.CLAIM_CREATED,
                        payload={
                            "claim_id": claim.claim_id,
                            "predicate": "HAS_EMAIL",
                            "object_value": inferred_email,
                            "status": "inferred",
                            "confidence": confidence,
                            "is_inferred": True,
                            "derivation_method": "corporate_email_pattern",
                        },
                    )
                )

        return created_claims

    async def resolve_document_contacts(
        self,
        doc: Any,
        objective_id: str,
        repo: ArgusRepository,
    ) -> list[Claim]:
        """Real-time contact extraction on a newly crawled document.

        Extracts facility switchboard and media contact phone numbers directly
        from the document body and binds them to mentioned facility entities.
        """
        if not doc or not getattr(doc, "text_content", None):
            return []

        text = doc.text_content
        if len(text) < 20:
            return []

        phones = self.extract_switchboard_numbers(text)
        if not phones:
            return []

        entities = repo.list_entities(objective_id=objective_id)
        facility_types = {
            "facility", "manufacturing_plant", "assembly_plant", "plant",
            "manufacturing_facility", "battery_manufacturing_plant", "factory",
            "operations", "metal_center", "casting",
        }
        facilities = [e for e in entities if e.entity_type.lower() in facility_types]
        if not facilities:
            return []

        created_claims: list[Claim] = []
        doc_url = getattr(doc, "url", "")

        for phone_info in phones:
            phone_num = phone_info["phone"]
            predicate = phone_info["predicate"]

            # Identify matching facility in this document
            target_facility = None
            text_lower = text.lower()
            for fac in facilities:
                fac_name = fac.canonical_name.lower()
                if fac_name in text_lower or any(alias.lower() in text_lower for alias in fac.aliases):
                    target_facility = fac
                    break

            if target_facility is None:
                continue

            # Check if this phone claim already exists for this facility
            existing = repo.list_claims(
                objective_id=objective_id,
                subject_entity_id=target_facility.entity_id,
                predicate=predicate,
            )
            if any(c.object_value == phone_num for c in existing):
                continue

            evidence = Evidence(
                source_id="realtime_contact_resolver",
                url=doc_url,
                passage=phone_info.get("context", f"Contact extracted from document: {phone_num}"),
                confidence=0.90,
            )
            repo.save_evidence(evidence)

            claim = Claim(
                objective_id=objective_id,
                subject_entity_id=target_facility.entity_id,
                predicate=predicate,
                object_value=phone_num,
                status=ClaimStatus.SUPPORTED,
                evidence_ids=[evidence.evidence_id],
                confidence=0.90,
            )
            repo.save_claim(claim)
            created_claims.append(claim)

            # Update entity attributes
            target_facility.attributes["facility_phone"] = phone_num
            repo.save_entity(target_facility)

            repo.record_event(
                ResearchEvent(
                    objective_id=objective_id,
                    event_type=EventType.CLAIM_CREATED,
                    payload={
                        "claim_id": claim.claim_id,
                        "predicate": predicate,
                        "object_value": phone_num,
                        "confidence": 0.90,
                        "target_facility": target_facility.canonical_name,
                    },
                )
            )

        return created_claims

    async def resolve_entity_contacts_realtime(
        self,
        objective_id: str,
        repo: ArgusRepository,
    ) -> list[Claim]:
        """Real-time corporate email inference for newly discovered personnel.

        Resolves company/facility domain, verifies MX asynchronously, and
        attaches HAS_EMAIL claims as soon as people are extracted and verified.
        """
        entities = repo.list_entities(objective_id=objective_id)
        claims = repo.list_claims(objective_id=objective_id)

        ent_by_id = {e.entity_id: e for e in entities}
        person_entities = [e for e in entities if e.entity_type.lower() == "person"]

        existing_emails = {
            c.subject_entity_id
            for c in claims
            if c.predicate.upper() == "HAS_EMAIL"
        }

        created_claims: list[Claim] = []

        for person in person_entities:
            if person.entity_id in existing_emails:
                continue

            # Determine domain for this person
            domain = ""
            facility_types = {
                "facility", "manufacturing_plant", "assembly_plant", "plant",
                "manufacturing_facility", "battery_manufacturing_plant", "factory",
                "operations", "metal_center", "casting",
            }
            for c in claims:
                if c.subject_entity_id == person.entity_id or c.object_entity_id == person.entity_id:
                    other_id = (
                        c.object_entity_id
                        if c.subject_entity_id == person.entity_id
                        else c.subject_entity_id
                    )
                    if other_id and other_id in ent_by_id:
                        other_ent = ent_by_id[other_id]
                        # If other_ent is a facility, find who operates it!
                        if other_ent.entity_type.lower() in facility_types:
                            for op_c in claims:
                                if (
                                    op_c.subject_entity_id == other_ent.entity_id
                                    and op_c.predicate.upper() in (
                                        "OPERATED_BY", "OWNED_BY", "SUBSIDIARY_OF", "MANUFACTURER", "MANUFACTURED_BY"
                                    )
                                ):
                                    if op_c.object_entity_id and op_c.object_entity_id in ent_by_id:
                                        domain = self.infer_company_domain(ent_by_id[op_c.object_entity_id].canonical_name)
                                    else:
                                        domain = self.infer_company_domain(op_c.object_value)
                                    if domain:
                                        break
                        else:
                            domain = self.infer_company_domain(other_ent.canonical_name)
                        if domain:
                            break
                    domain = self.infer_company_domain(c.object_value)
                    if domain:
                        break

            if not domain and "company" in person.attributes:
                domain = self.infer_company_domain(person.attributes["company"])

            if not domain:
                for e in entities:
                    if e.entity_type.lower() in ("company", "manufacturer", "organization"):
                        domain = self.infer_company_domain(e.canonical_name)
                        if domain:
                            break

            if not domain:
                continue

            mx_valid = await self.verify_domain_mx(domain)
            confidence = 0.85 if mx_valid else 0.65

            inferred_email = self.infer_email(person.canonical_name, domain)
            if not inferred_email:
                continue

            claim = Claim(
                objective_id=objective_id,
                subject_entity_id=person.entity_id,
                predicate="HAS_EMAIL",
                object_value=inferred_email,
                status=ClaimStatus.INFERRED,
                evidence_ids=[],
                confidence=confidence,
                derivation_method="corporate_email_pattern",
                derivation_inputs=[person.entity_id],
                inference_reason=(
                    f"Inferred corporate email address using pattern for domain '{domain}' "
                    f"(DNS MX validated: {mx_valid}). Not directly observed in source text."
                ),
            )
            repo.save_claim(claim)
            created_claims.append(claim)

            # Update entity attributes
            person.attributes["email"] = inferred_email
            person.attributes["email_status"] = "inferred"
            person.attributes["is_inferred"] = True
            person.attributes["domain_mx_verified"] = mx_valid
            repo.save_entity(person)

            repo.record_event(
                ResearchEvent(
                    objective_id=objective_id,
                    event_type=EventType.CLAIM_CREATED,
                    payload={
                        "claim_id": claim.claim_id,
                        "predicate": "HAS_EMAIL",
                        "object_value": inferred_email,
                        "status": "inferred",
                        "confidence": confidence,
                        "is_inferred": True,
                        "derivation_method": "corporate_email_pattern",
                    },
                )
            )

            existing_emails.add(person.entity_id)

        return created_claims
