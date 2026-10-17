"""Heimdallr V3: disputes and supersessions that a source itself reports.

``ContradictionResolver`` finds conflicts by comparing values across documents
(a payload of 35 kg against 40 kg). Many real conflicts are never stated as two
comparable values: a review says "later analyses contradict the cometary model",
or a filing says "earlier reports naming X as CEO are outdated". This module
reads those statements so they reach the contradiction records.

Two kinds are distinguished:

- an *unresolved dispute*: the source says accounts conflict or that one
  position contradicts another, without settling it;
- a *supersession*: the source says earlier information is outdated or
  superseded. The conflict is real but the source resolves it, so it is
  recorded as resolved and does not mark other claims contradicted.
"""

from __future__ import annotations

import re
from typing import Any

from argus.investigation.claim_verification import term_in_passage
from argus.investigation.contradiction_resolver import ContradictionRecord, DiscrepancyType

REPORTED_DISPUTE_DIM = "reported_dispute"
REPORTED_SUPERSESSION_DIM = "reported_supersession"
RESOLVED_BY_SUPERSESSION = "RESOLVED_BY_SUPERSESSION"

_ACCOUNT_NOUNS = (
    "accounts|claims|reports|estimates|explanations|hypotheses|models|theories|"
    "interpretations|findings|views|narratives|figures"
)
_DISPUTE_RE = re.compile(
    r"\bcontradict(?:s|ed|ing|ion|ions|ory)?\b"
    rf"|\b(?:competing|conflicting|contradictory|differing|opposing|rival|contested)\s+(?:[a-z]+\s+)?(?:{_ACCOUNT_NOUNS})\b"
    r"|\bremains?\s+(?:disputed|contested|unresolved)\b",
    re.IGNORECASE,
)
_NEGATED_RE = re.compile(
    r"\b(?:no|not|never|without|nothing|neither|nor)\b(?:\s+\w+){0,2}\s+(?:contradict\w*|conflict\w*|dispute\w*)",
    re.IGNORECASE,
)
_SUPERSESSION_RE = re.compile(
    r"\b(?:outdated|superseded|supersedes|obsolete|no longer (?:current|accurate|valid|in effect))\b",
    re.IGNORECASE,
)
_ABBREV_END = re.compile(r"\b(?:Dr|Mr|Ms|Mrs|Prof|Sr|Jr|St|U\.S|vs|Inc|Ltd|Co|No)\.$")


def split_sentences(text: str) -> list[str]:
    """Sentences of ``text``; honorifics such as "Dr." do not end a sentence."""
    out: list[str] = []
    for part in re.split(r"(?<=[.!?])\s+", text or ""):
        part = part.strip()
        if not part:
            continue
        if out and _ABBREV_END.search(out[-1]):
            out[-1] = f"{out[-1]} {part}"
        else:
            out.append(part)
    return out


# Words that make a sentence worth asking about at all; sentences without any are not sent to Laya.
_CANDIDATE_RE = re.compile(
    r"contradict|conflict|disput|incompatib|opposing|differing|discrepan|refut|disprov|retract|debunk|"
    r"untrue|denied|contrary|inconsistent|outdated|supersed|obsolete|no longer|contested|unresolved|competing|rival",
    re.IGNORECASE,
)
_SENTENCE_KINDS = {
    "dispute": "the sentence says accounts, claims or findings conflict or contradict each other, without settling it",
    "supersession": "the sentence says earlier information is outdated, superseded or no longer valid",
    "none": "the sentence reports no conflict (including sentences saying there is no conflict)",
}
_UNSET: Any = object()


def classify_sentence(sentence: str, rule: Any = _UNSET) -> str | None:
    """``"supersession"``, ``"dispute"`` or ``None`` for one sentence, decided by Laya.

    Only sentences containing a conflict word are asked; ``rule`` overrides the rule answer used
    without Laya (a caller with its own marker list passes its answer).
    """
    if not sentence or not _CANDIDATE_RE.search(sentence):
        return None
    from argus.brain.decisions import get_decisions

    fallback = classify_sentence_rule(sentence) if rule is _UNSET else rule
    kind = get_decisions().choose(
        "sentence_conflict", sentence, "Does this sentence report a conflict between accounts?",
        _SENTENCE_KINDS, fallback or "none",
    ).answer
    return None if kind == "none" else kind


def classify_sentence_rule(sentence: str) -> str | None:
    if not sentence:
        return None
    if _SUPERSESSION_RE.search(sentence):
        return "supersession"
    if _DISPUTE_RE.search(sentence) and not _NEGATED_RE.search(sentence):
        return "dispute"
    return None


def detect_reported_disputes(docs: list[dict[str, Any]], subject: str) -> list[ContradictionRecord]:
    """Disputes and supersessions stated by documents that are about ``subject``.

    At most one record per document: the first sentence that states a dispute or
    a supersession. A document counts as being about the subject when its title or
    text names it; the stating sentence itself may refer back to it ("the cometary
    model"), so it need not repeat the name.
    """
    records: list[ContradictionRecord] = []
    if not subject:
        return records
    for doc in docs:
        text = doc.get("text") or doc.get("text_content") or ""
        title = doc.get("title") or ""
        if not text or not term_in_passage(subject, f"{title} {text}"):
            continue
        sentences = split_sentences(text)
        for i, sentence in enumerate(sentences):
            kind = classify_sentence(sentence)
            if not kind:
                continue
            # The disputed position is usually stated just before the dispute.
            prior = sentences[i - 1] if i > 0 else sentence
            if kind == "supersession":
                records.append(ContradictionRecord(
                    topic=f"{subject}: superseded information reported by source",
                    subject=subject,
                    property_dim=REPORTED_SUPERSESSION_DIM,
                    claim_a=prior,
                    claim_b=sentence,
                    value_a=prior[:200],
                    value_b=sentence[:200],
                    discrepancy_type=DiscrepancyType.TEMPORAL_SUPERSEDED,
                    source_a=doc.get("url"),
                    source_b=doc.get("url"),
                    evidence_id_a=doc.get("evidence_id"),
                    evidence_id_b=doc.get("evidence_id"),
                    status=RESOLVED_BY_SUPERSESSION,
                    is_temporal=True,
                    adjudication_rationale="The source states that earlier information is outdated or superseded.",
                    resolved_value=sentence[:200],
                ))
            else:
                records.append(ContradictionRecord(
                    topic=f"{subject}: dispute reported by source",
                    subject=subject,
                    property_dim=REPORTED_DISPUTE_DIM,
                    claim_a=prior,
                    claim_b=sentence,
                    value_a=prior[:200],
                    value_b=sentence[:200],
                    discrepancy_type=DiscrepancyType.EVIDENTIARY_CONFLICT,
                    source_a=doc.get("url"),
                    source_b=doc.get("url"),
                    evidence_id_a=doc.get("evidence_id"),
                    evidence_id_b=doc.get("evidence_id"),
                    adjudication_rationale="The source reports conflicting accounts without settling them.",
                ))
            break
    return records
