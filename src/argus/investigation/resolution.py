"""Heimdallr V3: honest question resolution and termination accounting.

A question is *answered* only when the evidence settles it:

- ``SUPPORTED``: at least one claim linked to the question passed the shared
  verification gate (``claim_verification.is_verified``).
- ``CONTRADICTED``: a substantive conflict was found.
- ``NOT_FOUND``: an absence was established from cited evidence or claims.
- ``INSUFFICIENT_EVIDENCE`` backed by grounded claims, i.e. the sources
  themselves say the matter is unconfirmed (a null result is an answer).

``PARTIALLY_RESOLVED`` (only unverified assertions, e.g. a single technographic
provider row) and ``INSUFFICIENT_EVIDENCE`` without grounded claims (nothing
useful was found) close a question without answering it.

Retrieval denials (per-host/task budget, policy) are recorded on the state so the
stop reason and the limitations can say that coverage was cut, rather than
letting an empty result read as "no evidence exists".
"""

from __future__ import annotations

from typing import Any, Iterable

from argus.investigation.claim_verification import POSITIVE_STATUSES, is_verified

SUPPORTED = "SUPPORTED"
CONTRADICTED = "CONTRADICTED"
NOT_FOUND = "NOT_FOUND"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
PARTIALLY_RESOLVED = "PARTIALLY_RESOLVED"

# Questions spawned by specialist chaining are follow-ups on incidental
# discoveries; they never count toward the objective's coverage ratio.
CHAINED_ORIGIN = "chained"

_BUDGET_MARKERS = ("limit reached", "budget exhausted", "budget exceeded")


# Question types that ask for a specific kind of fact, and the predicate cues of
# claims that state that kind of fact. Other types (discovery, relationship,
# general) accept any claim about the question's entity.
_TYPE_PREDICATE_CUES: dict[str, tuple[str, ...]] = {
    "INFRASTRUCTURE_ATTRIBUTION": ("infra", "host", "domain", "dns", "certificate", "network", "security"),
    "OFFICER_TENURE": ("leader", "officer", "executive", "role", "title", "tenure", "succe", "board", "director", "founder", "responsib", "career"),
    "PLATFORM_ACCOUNT": ("account", "profile", "handle", "platform"),
    "IDENTITY_CORRELATION": ("identity", "profile", "alias", "account", "candidate", "equivalence"),
    "CONTACT_CHANNEL": ("contact", "email", "phone"),
    "TEMPORAL_STATE": ("temporal", "tenure", "date", "succe"),
}


def claim_kind_fits_question(claim: dict[str, Any], question_type: Any) -> bool:
    """True when the claim states the kind of fact the question type asks for."""
    qtype = getattr(question_type, "value", question_type) or ""
    cues = _TYPE_PREDICATE_CUES.get(str(qtype))
    if not cues:
        return True
    pred = str(claim.get("predicate") or "").lower()
    return any(c in pred for c in cues)


def claims_index(claims: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {c.get("claim_id"): c for c in claims if c.get("claim_id")}


def _grounded(claim: dict[str, Any] | None) -> bool:
    return bool(claim and claim.get("evidence_id") and (claim.get("source_passage") or "").strip())


def question_is_answered(q: dict[str, Any], index: dict[str, dict[str, Any]]) -> bool:
    """True when the question's status is an evidence-backed answer."""
    status = q.get("status")
    if status in (SUPPORTED, CONTRADICTED):
        return True
    if status == NOT_FOUND:
        return bool(q.get("resolved_by_claim_ids") or q.get("resolved_by_evidence_ids"))
    if status == INSUFFICIENT_EVIDENCE:
        return any(_grounded(index.get(cid)) for cid in q.get("resolved_by_claim_ids") or [])
    return False


def is_chained(q: dict[str, Any]) -> bool:
    return q.get("origin") == CHAINED_ORIGIN


def coverage(state: Any) -> dict[str, Any]:
    """Answer coverage over the objective's own (non-chained) questions."""
    index = claims_index(state.claims)
    questions = list(state.questions.values())
    objective_qs = [q for q in questions if not is_chained(q)]
    answered = [q for q in objective_qs if question_is_answered(q, index)]
    critical = [q for q in questions if q.get("is_critical")]
    unanswered_critical = [q for q in critical if not question_is_answered(q, index)]
    return {
        "objective_total": len(objective_qs),
        "objective_answered": len(answered),
        "ratio": (len(answered) / len(objective_qs)) if objective_qs else 0.0,
        "unanswered_critical": unanswered_critical,
        "any_answered": bool(answered),
    }


def positive_linked_claims(q: dict[str, Any], index: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Positive (asserted) claims linked to a question, verified or not."""
    ids = list(q.get("related_claims") or []) + list(q.get("resolved_by_claim_ids") or [])
    seen: set[str] = set()
    out = []
    for cid in ids:
        if cid in seen:
            continue
        seen.add(cid)
        c = index.get(cid)
        if c and c.get("status") in POSITIVE_STATUSES:
            out.append(c)
    return out


def verified_linked_claims(q: dict[str, Any], index: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [c for c in positive_linked_claims(q, index) if is_verified(c)]


def is_budget_denial(denial: dict[str, Any]) -> bool:
    reason = str(denial.get("reason") or "").lower()
    return any(m in reason for m in _BUDGET_MARKERS)


def budget_denials(state: Any) -> list[dict[str, Any]]:
    return [d for d in getattr(state, "retrieval_denials", []) if is_budget_denial(d)]


def incomplete_stop(state: Any) -> tuple[str, str]:
    """Stop reason and rationale for a run that ends with the objective not answered."""
    cov = coverage(state)
    gaps = cov["unanswered_critical"]
    names = "; ".join(f"'{q.get('question_text', '')}' ({q.get('status')})" for q in gaps[:3])
    denied = budget_denials(state)
    if gaps and denied:
        return (
            "BUDGET_EXHAUSTED_WITH_CRITICAL_MISSING_FIELDS",
            f"Retrieval budget denied {len(denied)} request(s) and {len(gaps)} critical question(s) "
            f"remain unanswered: {names}.",
        )
    if gaps:
        return (
            "NO_USEFUL_ACTIONS_REMAIN",
            f"No useful actions remain and {len(gaps)} critical question(s) are not answered by "
            f"verified evidence: {names}.",
        )
    return (
        "NO_USEFUL_ACTIONS_REMAIN",
        f"No useful actions remain; {cov['objective_answered']}/{cov['objective_total']} "
        "objective questions are answered by evidence.",
    )
