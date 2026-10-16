"""Shared claim verification boundary.

Extractors propose claims; they do not decide whether a claim is verified.
Every claim entering ``InvestigationState.add_claim`` passes through
``verify_claim``, which derives the final status from the claim's own cited
evidence:

1. Citation integrity: the claim's ``evidence_id`` must resolve to a recorded
   evidence item, and ``source_url`` must be that item's URL.
2. Passage grounding: ``source_passage`` must be a verbatim excerpt of that
   evidence item, and must mention the claim's subject and object (or the
   producer-declared ``grounding_terms`` for coded objects).
3. Qualification: a grounded passage that negates or hedges the statement
   cannot support it.
4. Incidental relations: a hostname or e-mail address appearing on a page does
   not establish that an organization operates it, so such relations are never
   verified by co-occurrence.
5. Source class: an assertion grounded only in a technographic aggregator stays
   ``TECHNOGRAPHIC_PROVIDER_ASSERTION``; ``VENDOR_CONFIRMED`` requires the
   vendor's own site; ``CORROBORATED`` is only reached through ``add_support``
   with at least two independent voices, where all technographic aggregators
   together count as one voice.

The gate never invents a numeric confidence: positive claims leave it with
``confidence=None``.
"""

from __future__ import annotations

import re
from typing import Any, Iterable
from urllib.parse import urlparse


VERIFIED_STATUSES = frozenset({"SUPPORTED", "CORROBORATED", "VENDOR_CONFIRMED"})
POSITIVE_STATUSES = VERIFIED_STATUSES | {"TECHNOGRAPHIC_PROVIDER_ASSERTION"}

# Relations whose only evidence is that two strings appear on the same page.
# Page co-occurrence cannot establish ownership or operation of a host/address.
INCIDENTAL_PREDICATES = frozenset({"infrastructure", "admin_contact"})

# Source-class registry: publishers whose business is aggregating inferred
# technology-usage signals. Their rows are attributed assertions, and several
# of them repeating a row is not independent corroboration.
TECHNOGRAPHIC_PROVIDER_DOMAINS = frozenset({
    "theirstack.com",
    "enlyft.com",
    "6sense.com",
    "slintel.com",
    "rocketreach.co",
    "appsruntheworld.com",
    "landbase.com",
    "hgdata.com",
    "datanyze.com",
    "zoominfo.com",
    "leadspace.com",
    "builtwith.com",
    "wappalyzer.com",
    "stackshare.io",
})

SOURCE_TECHNOGRAPHIC = "technographic_provider"
SOURCE_VENDOR = "vendor_official_disclosure"
SOURCE_INDEPENDENT = "independent_publisher"

_NEGATION_MARKERS = (
    "does not", "did not", "do not", "no longer", "never", "not use", "not using",
    "discontinued", "migrated away", "denied", "refuted",
)
_HEDGE_MARKERS = (
    "rumored", "rumoured", "alleged", "allegedly", "unconfirmed", "unverified",
    "may use", "might use", "reportedly considering", "speculat",
)

_STOP_TOKENS = frozenset({"the", "and", "of", "a", "an", "in", "on", "for", "to", "by", "at", "with"})
_SECOND_LEVEL = frozenset({"co", "com", "org", "net", "ac", "gov", "edu", "ne", "or", "go"})


def _norm(text: Any) -> str:
    s = str(text or "").lower()
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip()


def registrable_domain(url: str) -> str:
    """Best-effort registrable domain (``news.siemens.com`` -> ``siemens.com``)."""
    if not url:
        return ""
    host = urlparse(url if "://" in url else f"https://{url}").netloc.lower()
    host = host.split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    parts = [p for p in host.split(".") if p]
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in _SECOND_LEVEL:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def classify_source(url: str, claim_object: str = "") -> str:
    """Classify the publisher of a passage relative to the claim it supports.

    A page is a vendor disclosure only when the publisher's own name is part of
    the claimed object (``siemens.com`` for "Siemens Teamcenter"). This keeps the
    rule product-agnostic instead of relying on a fixed vendor list.
    """
    dom = registrable_domain(url)
    if not dom:
        return SOURCE_INDEPENDENT
    if dom in TECHNOGRAPHIC_PROVIDER_DOMAINS:
        return SOURCE_TECHNOGRAPHIC
    stem = dom.split(".")[0]
    if claim_object and len(stem) >= 3 and re.search(rf"\b{re.escape(stem)}\b", _norm(claim_object)):
        return SOURCE_VENDOR
    return SOURCE_INDEPENDENT


def _term_tokens(term: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9][a-z0-9&'\-]*", _norm(term)) if t not in _STOP_TOKENS]


def term_in_passage(term: Any, passage: str) -> bool:
    """True when ``term`` is mentioned in ``passage`` (verbatim or by all its tokens)."""
    t = _norm(term).strip(" .,;:")
    p = _norm(passage)
    if not t or not p:
        return False
    if re.search(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", p):
        return True
    tokens = _term_tokens(t)
    if not tokens:
        return False
    return all(re.search(rf"(?<![a-z0-9]){re.escape(tok)}(?![a-z0-9])", p) for tok in tokens)


def ground_passage(text: str, terms: Iterable[str], max_len: int = 400) -> str:
    """Return a verbatim excerpt of ``text`` that mentions every term, or ``""``.

    The excerpt is a sentence or line of the document (trimmed to a window around
    the terms when the sentence is very long, as in flattened tables).
    """
    terms = [t for t in terms if t]
    if not text or not terms:
        return ""
    # Sentence boundaries are [.!?] followed by whitespace, so hostnames, e-mail
    # addresses and decimals ("$39.5B") stay inside one segment.
    for m in re.finditer(r"(?:[^.!?\n]|[.!?](?=\S))+[.!?]?", text):
        seg = m.group(0)
        if not all(term_in_passage(t, seg) for t in terms):
            continue
        seg_stripped = seg.strip()
        if len(seg_stripped) <= max_len:
            return seg_stripped
        low = seg.lower()
        positions = []
        for t in terms:
            first_tok = (_term_tokens(t) or [_norm(t)])[0]
            idx = low.find(first_tok)
            if idx >= 0:
                positions.append((idx, idx + len(_norm(t))))
        if not positions:
            return seg_stripped[:max_len]
        start = max(0, min(p[0] for p in positions) - 60)
        end = min(len(seg), max(p[1] for p in positions) + 60)
        window = seg[start:end].strip()
        if all(term_in_passage(t, window) for t in terms):
            return window
        return seg_stripped
    return ""


def _evidence_text(ev: dict[str, Any]) -> str:
    return str(ev.get("snippet") or ev.get("text") or ev.get("text_content") or "")


def _find_evidence(evidence: Iterable[dict[str, Any]], evidence_id: Any) -> dict[str, Any] | None:
    if not evidence_id:
        return None
    for ev in evidence:
        if ev.get("evidence_id") == evidence_id:
            return ev
    return None


def _qualified(passage: str) -> str:
    """Return 'negated'/'hedged' when the passage qualifies its statement."""
    p = _norm(passage)
    for marker in _NEGATION_MARKERS:
        if marker in p:
            return "negated"
    for marker in _HEDGE_MARKERS:
        if marker in p:
            return "hedged"
    return ""


def is_verified(claim: dict[str, Any]) -> bool:
    """A claim counts as verified only if the gate passed it with a verified status."""
    ver = claim.get("verification") or {}
    return claim.get("status") in VERIFIED_STATUSES and bool(ver.get("passed"))


def _support_record(claim: dict[str, Any], ev: dict[str, Any], source_class: str) -> dict[str, Any]:
    return {
        "evidence_id": ev.get("evidence_id"),
        "url": ev.get("url"),
        "domain": registrable_domain(ev.get("url") or ""),
        "source_class": source_class,
        "syndication_cluster_id": ev.get("syndication_cluster_id"),
        "proposed_status": claim.get("proposed_status"),
        "passage": claim.get("source_passage"),
    }


def _single_source_status(proposed: str, source_class: str) -> str:
    if source_class == SOURCE_TECHNOGRAPHIC:
        return "TECHNOGRAPHIC_PROVIDER_ASSERTION"
    if source_class == SOURCE_VENDOR and proposed == "VENDOR_CONFIRMED":
        return "VENDOR_CONFIRMED"
    return "SUPPORTED"


def verify_claim(claim: dict[str, Any], evidence: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Derive ``claim['status']`` from its cited evidence. Mutates and returns ``claim``."""
    evidence = list(evidence)
    proposed = str(claim.get("status") or "UNVERIFIED")
    if "proposed_status" not in claim:
        claim["proposed_status"] = proposed

    # Negative / undetermined findings make no positive assertion; they pass
    # through unchanged, but are never counted as verified.
    if proposed not in POSITIVE_STATUSES:
        claim.setdefault("verification", {"passed": False, "reason": f"non_positive_status:{proposed}"})
        return claim

    def reject(status: str, reason: str, **extra: Any) -> dict[str, Any]:
        claim["status"] = status
        claim["confidence"] = None
        claim["verification"] = {"passed": False, "reason": reason, **extra}
        return claim

    ev = _find_evidence(evidence, claim.get("evidence_id"))
    if ev is None:
        return reject("UNVERIFIED", "no_cited_evidence")

    ev_url = ev.get("url") or ""
    claimed_url = claim.get("source_url")
    if claimed_url and ev_url and claimed_url != ev_url:
        return reject("UNVERIFIED", "citation_url_mismatch", evidence_url=ev_url)
    if ev_url:
        claim["source_url"] = ev_url

    passage = str(claim.get("source_passage") or "")
    if not passage.strip():
        return reject("UNVERIFIED", "no_source_passage")
    if _norm(passage) not in _norm(_evidence_text(ev)):
        return reject("UNVERIFIED", "passage_not_in_cited_evidence")

    subject = str(claim.get("subject") or "")
    if claim.get("grounding_scope") == "resource":
        # The claim asserts that the cited resource itself exists (e.g. an account
        # profile); it is grounded by an observation retrieved from that resource
        # whose address names the subject.
        if not (subject and ev_url and term_in_passage(subject, ev_url.replace("/", " "))):
            return reject("UNVERIFIED", "resource_url_does_not_name_subject")
    else:
        terms = [subject] + [str(t) for t in (claim.get("grounding_terms") or [claim.get("object")])]
        missing = [t for t in terms if not t or not term_in_passage(t, passage)]
        if missing:
            return reject("UNVERIFIED", "passage_does_not_mention_claim_terms", missing_terms=missing)

    qual = _qualified(passage)
    if qual:
        return reject("INSUFFICIENT_EVIDENCE", f"passage_{qual}", grounded=True)

    source_class = classify_source(ev_url, str(claim.get("object") or ""))
    claim["source_class"] = source_class
    claim["supporting_sources"] = [_support_record(claim, ev, source_class)]

    if claim.get("predicate") in INCIDENTAL_PREDICATES:
        return reject(
            "UNVERIFIED",
            "page_co_occurrence_cannot_establish_relation",
            grounded=True,
            incidental=True,
            source_class=source_class,
        )

    claim["status"] = _single_source_status(proposed, source_class)
    claim["confidence"] = None
    claim["verification"] = {
        "passed": True,
        "grounded": True,
        "reason": "passage_grounded_in_cited_evidence",
        "source_class": source_class,
        "independent_voices": 1,
    }
    return claim


def _voice(support: dict[str, Any]) -> str:
    if support.get("source_class") == SOURCE_TECHNOGRAPHIC:
        return "technographic_aggregators"
    if support.get("syndication_cluster_id"):
        return f"cluster:{support['syndication_cluster_id']}"
    return f"domain:{support.get('domain')}"


def add_support(claim: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Attach an additional, separately verified source to an existing claim.

    ``candidate`` must already have passed ``verify_claim``. The claim becomes
    ``CORROBORATED`` only when its grounded sources represent at least two
    independent voices; all technographic aggregators together are one voice.
    """
    if not (candidate.get("verification") or {}).get("passed"):
        return claim
    if not (claim.get("verification") or {}).get("passed"):
        return claim
    supports = claim.setdefault("supporting_sources", [])
    for new in candidate.get("supporting_sources") or []:
        if not any(s.get("evidence_id") == new.get("evidence_id") or s.get("url") == new.get("url") for s in supports):
            supports.append(new)

    voices = {_voice(s) for s in supports}
    claim["verification"]["independent_voices"] = len(voices)
    if len(voices) >= 2:
        claim["status"] = "CORROBORATED"
        claim["corroborated_by"] = [s.get("url") for s in supports[1:]]
    else:
        statuses = [_single_source_status(str(s.get("proposed_status") or ""), str(s.get("source_class") or "")) for s in supports]
        for best in ("VENDOR_CONFIRMED", "SUPPORTED", "TECHNOGRAPHIC_PROVIDER_ASSERTION"):
            if best in statuses:
                claim["status"] = best
                break
    claim["confidence"] = None
    return claim
