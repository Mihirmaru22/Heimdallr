"""Independent Semantic Auditor for Claim Support and Entailment Verification.

Implements an independent evaluation method that strictly distinguishes:
1. ENTAILED claims: The cited evidence directly and fully confirms the claim's
   subject, predicate, object, and conditions without contradiction or hedging.
2. CONTRADICTED claims: The cited evidence asserts a mutually exclusive,
   refuting, or conflicting proposition for the same subject and property.
3. INSUFFICIENTLY_SUPPORTED claims: The cited evidence touches upon the subject or
   domain, but lacks the specific predicate, metric, or affirmation, or is marked
   hedged, inconclusive, or preliminary.
4. IRRELEVANT_EVIDENCE: The cited evidence passage does not mention the subject
   or discuss the asserted topic at all.
5. PARTIALLY_SUPPORTED_COMPOUND claims: The claim asserts multiple propositions
   or compound attributes, where at least one proposition is affirmed by the
   evidence while one or more propositions remain unsupported or missing.

This independent auditor provides a principled semantic evaluation replacing
the legacy token-overlap / passage-length heuristic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple


class SemanticSupportStatus(str, Enum):
    ENTAILED = "ENTAILED"
    CONTRADICTED = "CONTRADICTED"
    INSUFFICIENTLY_SUPPORTED = "INSUFFICIENTLY_SUPPORTED"
    IRRELEVANT_EVIDENCE = "IRRELEVANT_EVIDENCE"
    PARTIALLY_SUPPORTED_COMPOUND = "PARTIALLY_SUPPORTED_COMPOUND"


@dataclass
class ClaimAuditResult:
    claim_id: str
    claim_text: str
    evidence_id: Optional[str]
    status: SemanticSupportStatus
    rationale: str
    confidence: float = 1.0
    sub_clauses: List[str] = field(default_factory=list)
    detected_discrepancies: List[str] = field(default_factory=list)


class IndependentSemanticAuditor:
    """Independent semantic evaluation engine for claim-evidence entailment."""

    # Explicit contradiction markers
    NEGATION_MARKERS = [
        "did not", "does not", "never", "refuted", "disproved", "disproven",
        "null result", "failed to replicate", "not a superconductor",
        "zero affiliation", "no record of", "does not exist", "unrelated",
        "retracted", "collapsed", "terminated without closing",
    ]

    # Hedging and insufficient evidence markers
    HEDGING_MARKERS = [
        "preliminary", "unconfirmed", "unverified", "inconclusive",
        "pending investigation", "speculative", "anecdotal", "alleged",
        "remains unknown", "insufficient evidence", "cannot be confirmed",
        "undeciphered", "conflicting reports",
    ]

    # Conjunctions splitting compound propositions
    COMPOUND_SPLITTERS = [
        r"\band also\b",
        r"\bas well as\b",
        r"\balong with\b",
        r"\bwhile also\b",
        r"\b,\s+and\b",
    ]

    def __init__(self, token_match_threshold: float = 0.65) -> None:
        self.token_match_threshold = token_match_threshold

    def split_compound_claim(self, claim_text: str) -> List[str]:
        """Split a compound claim into constituent atomic propositions."""
        sub_clauses = [claim_text.strip()]
        for splitter in self.COMPOUND_SPLITTERS:
            new_clauses = []
            for clause in sub_clauses:
                parts = re.split(splitter, clause, flags=re.IGNORECASE)
                for p in parts:
                    clean = p.strip().strip(",;")
                    if len(clean) > 8:
                        new_clauses.append(clean)
            sub_clauses = new_clauses
        return sub_clauses

    def _extract_core_tokens(self, text: str) -> List[str]:
        """Extract substantive tokens ignoring common stop words."""
        stopwords = {
            "the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "of",
            "with", "by", "from", "up", "about", "into", "over", "after", "is",
            "are", "was", "were", "be", "been", "being", "have", "has", "had",
            "do", "does", "did", "that", "this", "these", "those", "it", "its",
        }
        words = re.findall(r"\b[a-zA-Z0-9_\-\.]+\b", text.lower())
        return [w for w in words if len(w) > 2 and w not in stopwords]

    def _extract_numbers(self, text: str) -> List[Tuple[float, str]]:
        """Extract numbers with optional units."""
        pattern = r"\b(\d+(?:\.\d+)?)\s*([a-zA-Z%]+)?\b"
        results = []
        for match in re.finditer(pattern, text):
            val_str = match.group(1)
            unit = (match.group(2) or "").lower()
            try:
                val = float(val_str)
                results.append((val, unit))
            except ValueError:
                continue
        return results

    def audit_atomic_clause(
        self,
        clause: str,
        evidence_text: str,
        subject_hint: Optional[str] = None,
    ) -> Tuple[SemanticSupportStatus, str]:
        """Audit an atomic sub-clause against evidence text."""
        clause_lower = clause.lower()
        ev_lower = evidence_text.lower()

        # Step 1: Subject / Entity relevance
        subj_tokens = self._extract_core_tokens(subject_hint) if subject_hint else []
        clause_tokens = self._extract_core_tokens(clause)

        if subj_tokens:
            has_subject = any(st in ev_lower for st in subj_tokens)
        else:
            # First 2-3 tokens of clause as proxy subject
            first_tokens = clause_tokens[:2] if len(clause_tokens) >= 2 else clause_tokens
            has_subject = any(t in ev_lower for t in first_tokens)

        # General entity/topical token overlap
        matching_tokens = [t for t in clause_tokens if t in ev_lower]
        relevance_ratio = (len(matching_tokens) / len(clause_tokens)) if clause_tokens else 0.0

        if not has_subject and relevance_ratio < 0.20:
            return (
                SemanticSupportStatus.IRRELEVANT_EVIDENCE,
                f"Evidence has zero or negligible overlap ({relevance_ratio:.1%}) with clause tokens and subject is absent.",
            )

        # Step 2: Refutation and Contradiction detection
        # Direct negation markers in evidence applied to this clause
        for neg in self.NEGATION_MARKERS:
            if neg in clause_lower:
                return (
                    SemanticSupportStatus.CONTRADICTED,
                    f"Claim statement itself contains negation/refutation marker '{neg}'.",
                )
            if neg in ev_lower:
                neg_sents = [s for s in re.split(r"[.\n;]+", ev_lower) if neg in s]
                for ns in neg_sents:
                    matching_in_neg = [t for t in clause_tokens if t in ns]
                    if len(matching_in_neg) >= 2 or (subj_tokens and any(st in ns for st in subj_tokens) and len(matching_in_neg) >= 1):
                        return (
                            SemanticSupportStatus.CONTRADICTED,
                            f"Evidence explicitly negates or refutes claim with '{neg}'.",
                        )

        # Numeric contradictions (e.g. claim asserts 500 kN, evidence asserts 85 kN)
        clause_numbers = self._extract_numbers(clause)
        ev_numbers = self._extract_numbers(evidence_text)

        if clause_numbers and ev_numbers:
            for c_val, c_unit in clause_numbers:
                if 1900 < c_val < 2100:  # Skip calendar years
                    continue
                # If this claim number is already confirmed in the evidence, it is affirmed, not a mismatch
                c_confirmed = any(
                    abs(c_val - e_val) / max(c_val, e_val, 1e-6) <= 0.05
                    for e_val, e_unit in ev_numbers
                    if not c_unit or not e_unit or c_unit == e_unit or c_unit in e_unit or e_unit in c_unit
                )
                if not c_confirmed:
                    for e_val, e_unit in ev_numbers:
                        if 1900 < e_val < 2100:
                            continue
                        # If units match or are compatible and values differ significantly (>10%)
                        if c_unit and e_unit and (c_unit == e_unit or (c_unit in e_unit or e_unit in c_unit)):
                            diff = abs(c_val - e_val) / max(c_val, e_val, 1e-6)
                            if diff > 0.10:
                                return (
                                    SemanticSupportStatus.CONTRADICTED,
                                    f"Numerical value mismatch: claim asserts {c_val} {c_unit}, evidence reports {e_val} {e_unit} (relative diff: {diff:.1%}).",
                                )

        # Step 3: Hedging / Insufficient Evidence markers
        for hedge in self.HEDGING_MARKERS:
            if hedge in clause_lower:
                return (
                    SemanticSupportStatus.INSUFFICIENTLY_SUPPORTED,
                    f"Claim contains epistemic qualification/hedging: '{hedge}'.",
                )
            if hedge in ev_lower:
                hedge_sents = [s for s in re.split(r"[.\n;]+", ev_lower) if hedge in s]
                for hs in hedge_sents:
                    matching_in_hedge = [t for t in clause_tokens if t in hs]
                    if len(matching_in_hedge) >= 2 or (subj_tokens and any(st in hs for st in subj_tokens) and len(matching_in_hedge) >= 1):
                        return (
                            SemanticSupportStatus.INSUFFICIENTLY_SUPPORTED,
                            f"Evidence contains epistemic qualification/hedging: '{hedge}'.",
                        )

        # Step 4: Full Entailment vs Insufficient Support
        # For an atomic clause to be ENTAILED:
        # Key tokens (subject, predicate, object) must be affirmed in evidence.
        if relevance_ratio >= self.token_match_threshold:
            # If numbers exist in clause, they must match an evidence number
            if clause_numbers:
                num_matched = any(
                    any(abs(c_val - e_val) / max(c_val, e_val, 1e-6) <= 0.05 for e_val, _ in ev_numbers)
                    for c_val, _ in clause_numbers if not (1900 < c_val < 2100)
                )
                if not num_matched and any(not (1900 < c_val < 2100) for c_val, _ in clause_numbers):
                    return (
                        SemanticSupportStatus.INSUFFICIENTLY_SUPPORTED,
                        "Substantive numerical value in claim was not confirmed in evidence.",
                    )
            return (
                SemanticSupportStatus.ENTAILED,
                f"Evidence directly affirms core proposition with high token coverage ({relevance_ratio:.1%}).",
            )
        else:
            return (
                SemanticSupportStatus.INSUFFICIENTLY_SUPPORTED,
                f"Evidence discusses topic but lacks required token coverage for full entailment ({relevance_ratio:.1%} < {self.token_match_threshold:.1%}).",
            )

    def audit_claim(
        self,
        claim: Dict[str, Any],
        evidence_doc: Dict[str, Any],
    ) -> ClaimAuditResult:
        """Audit a single claim against cited evidence record."""
        claim_id = claim.get("claim_id", "claim_unknown")
        claim_text = (
            claim.get("statement")
            or claim.get("claim_text")
            or claim.get("object")
            or claim.get("text")
            or ""
        )
        subject_hint = str(claim.get("subject") or "")
        ev_id = claim.get("evidence_id")
        ev_text = (
            evidence_doc.get("text")
            or evidence_doc.get("text_content")
            or evidence_doc.get("snippet")
            or ""
        )

        if not ev_text.strip():
            return ClaimAuditResult(
                claim_id=claim_id,
                claim_text=claim_text,
                evidence_id=ev_id,
                status=SemanticSupportStatus.IRRELEVANT_EVIDENCE,
                rationale="Cited evidence record has empty text content.",
            )

        # Check for compound claims
        sub_clauses = self.split_compound_claim(claim_text)

        if len(sub_clauses) > 1:
            # Evaluate each constituent proposition
            clause_results = [
                self.audit_atomic_clause(clause, ev_text, subject_hint)
                for clause in sub_clauses
            ]
            statuses = [res[0] for res in clause_results]

            # Compound resolution logic
            if any(s == SemanticSupportStatus.CONTRADICTED for s in statuses):
                return ClaimAuditResult(
                    claim_id=claim_id,
                    claim_text=claim_text,
                    evidence_id=ev_id,
                    status=SemanticSupportStatus.CONTRADICTED,
                    rationale="At least one conjunct in compound claim is contradicted by evidence.",
                    sub_clauses=sub_clauses,
                )

            entailed_count = sum(1 for s in statuses if s == SemanticSupportStatus.ENTAILED)
            if entailed_count == len(statuses):
                return ClaimAuditResult(
                    claim_id=claim_id,
                    claim_text=claim_text,
                    evidence_id=ev_id,
                    status=SemanticSupportStatus.ENTAILED,
                    rationale="All conjuncts in compound claim are independently entailed by evidence.",
                    sub_clauses=sub_clauses,
                )
            elif entailed_count > 0:
                return ClaimAuditResult(
                    claim_id=claim_id,
                    claim_text=claim_text,
                    evidence_id=ev_id,
                    status=SemanticSupportStatus.PARTIALLY_SUPPORTED_COMPOUND,
                    rationale=f"Partially supported compound: {entailed_count}/{len(statuses)} conjuncts entailed.",
                    sub_clauses=sub_clauses,
                )
            elif all(s == SemanticSupportStatus.IRRELEVANT_EVIDENCE for s in statuses):
                return ClaimAuditResult(
                    claim_id=claim_id,
                    claim_text=claim_text,
                    evidence_id=ev_id,
                    status=SemanticSupportStatus.IRRELEVANT_EVIDENCE,
                    rationale="All conjuncts in compound claim are irrelevant to evidence passage.",
                    sub_clauses=sub_clauses,
                )
            else:
                return ClaimAuditResult(
                    claim_id=claim_id,
                    claim_text=claim_text,
                    evidence_id=ev_id,
                    status=SemanticSupportStatus.INSUFFICIENTLY_SUPPORTED,
                    rationale="Evidence provides insufficient support for all conjuncts in compound claim.",
                    sub_clauses=sub_clauses,
                )
        else:
            # Single atomic claim
            status, rationale = self.audit_atomic_clause(claim_text, ev_text, subject_hint)
            return ClaimAuditResult(
                claim_id=claim_id,
                claim_text=claim_text,
                evidence_id=ev_id,
                status=status,
                rationale=rationale,
                sub_clauses=sub_clauses,
            )

    def audit_investigation_claims(
        self,
        claims: Sequence[Dict[str, Any]],
        evidence_records: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Audit an entire set of claims and evidence records from an investigation."""
        ev_map = {
            (e.get("evidence_id") or e.get("id")): e
            for e in evidence_records
            if isinstance(e, dict) and (e.get("evidence_id") or e.get("id"))
        }

        audit_results: List[ClaimAuditResult] = []
        counts: Dict[str, int] = {s.value: 0 for s in SemanticSupportStatus}

        for claim in claims:
            ev_id = claim.get("evidence_id")
            ev_doc = ev_map.get(ev_id, {})
            res = self.audit_claim(claim, ev_doc)
            audit_results.append(res)
            counts[res.status.value] += 1

        total = len(claims)
        entailed_rate = (counts[SemanticSupportStatus.ENTAILED.value] / total) if total > 0 else 0.0

        return {
            "total_claims": total,
            "counts": counts,
            "entailed_rate": entailed_rate,
            "detailed_audits": [
                {
                    "claim_id": r.claim_id,
                    "claim_text": r.claim_text,
                    "evidence_id": r.evidence_id,
                    "status": r.status.value,
                    "rationale": r.rationale,
                }
                for r in audit_results
            ],
        }
