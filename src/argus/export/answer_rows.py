"""One row per answer, the way a person reads a target list.

Heimdallr's own sheets are a claim dump (claim id, subject, predicate, object, status). A person
reading a list of answers wants the opposite shape: one row per thing found, the evidence beside
it, and empty columns to work in. That is the shape of the sheet Ronak keeps by hand (a company
per row, with evidence type, strength, URL, the quote, and status/owner columns to fill in).

Nothing here is specific to a topic. The answer column holds whatever the question asked for:
companies, hospitals, vineyards, people, places, versions. Attribute columns (website, industry,
size, location) appear only when the run actually found that attribute for something, so a
question about garlic planting does not carry empty "Approx employees" columns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any
from urllib.parse import urlparse

from argus.intake.brief import brief_from_data
from argus.investigation.relevance import clean_entity_name, is_contextually_relevant_host

# Positive statuses: the ones the evidence gate let through.
POSITIVE = {"SUPPORTED", "CORROBORATED", "VERIFIED", "CONFIRMED"}

STRONG, MODERATE, WEAK = "Strong", "Moderate", "Weak"

# Attribute columns, in the order they appear. Each maps to the predicate words that state it.
ATTRIBUTE_COLUMNS: list[tuple[str, tuple[str, ...]]] = [
    ("Website", ("website", "homepage", "domain", "web_site", "url")),
    ("Where", ("headquarter", "located", "location", "based", "city", "state", "country", "region", "address")),
    ("Industry", ("industry", "sector", "field", "market")),
    ("Approx size", ("employee", "headcount", "staff", "size", "revenue", "workforce")),
]

# Evidence type, by what the page is. Checked in order; the first match wins.
_EVIDENCE_TYPES: list[tuple[str, tuple[str, ...]]] = [
    ("Job post", ("jobs.", "careers", "/job/", "/jobs/", "greenhouse.io", "lever.co", "ashbyhq", "workday", "myworkdayjobs", "recruit", "/vacanc")),
    ("Filing", ("sec.gov", "edgar", "companieshouse", "/filing", "annualreport", "investor")),
    ("Registry", ("register", "registry", "gleif", "wikidata", "opencorporates", ".gov")),
    ("Case study", ("case-stud", "casestud", "/customers", "customer-stor", "success-stor", "/references")),
    ("Press release", ("press-release", "/newsroom", "/press/", "prnewswire", "businesswire")),
    ("News", ("news", "/article", "reuters", "bloomberg", "/20")),
    ("Reference page", ("wikipedia.org", "britannica")),
    ("Forum post", ("forum", "/community", "stackexchange", "stackoverflow", "reddit.com")),
]


@dataclass
class AnswerRow:
    """One thing the run found, with the evidence for it."""

    answer: str
    detail: str = ""
    evidence_type: str = "Web page"
    evidence_strength: str = WEAK
    sources: int = 1
    evidence_url: str = ""
    evidence_says: str = ""
    attributes: dict[str, str] = field(default_factory=dict)
    known_to_user: bool = False  # the user listed it on the form under "ones you already know"
    _hosts: set[str] = field(default_factory=set, repr=False)
    _urls: list[str] = field(default_factory=list, repr=False)
    _quoted: bool = field(default=False, repr=False)
    _corroborated: bool = field(default=False, repr=False)

    def other_sources(self) -> str:
        """The URLs beyond the one shown, newest first, one per line."""
        return "\n".join(self._urls[1:])


def evidence_type_of(url: str, title: str = "", source_class: str = "") -> str:
    """What kind of page the evidence is, from its URL and title."""
    text = f"{url} {title}".lower()
    if "web.archive.org" in url.lower():
        return "Archived copy"
    if (source_class or "").lower() in ("snippet", "search_snippet"):
        return "Search snippet"
    for label, cues in _EVIDENCE_TYPES:
        if any(cue in text for cue in cues):
            return label
    return "Web page"


def evidence_strength(status: str, sources: int, has_quote: bool) -> str:
    """How much the evidence carries: more than one source is strong, a quote is moderate.

    No claim reaches a sheet without passing the evidence gate, so "Weak" here means
    "stated once, without a quote we could keep", not "possibly invented".
    """
    status = (status or "").upper()
    if sources >= 2 or status == "CORROBORATED":
        return STRONG
    if has_quote and status in POSITIVE:
        return MODERATE
    return WEAK


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def _attribute_for(predicate: str) -> str | None:
    pred = (predicate or "").lower()
    for column, cues in ATTRIBUTE_COLUMNS:
        if any(cue in pred for cue in cues):
            return column
    return None


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()


def is_answerable(name: str, objective: str, url: str = "") -> bool:
    """Drop what is not an answer: an empty name, or a host the run picked up in passing.

    A page's media or CDN hosts ("rr1---sn-4g5ednss.googlevideo.com") get extracted alongside real
    answers. They belong in an answer only when the question is about that infrastructure, which is
    what ``is_contextually_relevant_host`` decides, so the same rule the narrative uses applies here.
    """
    name = (name or "").strip()
    if len(name) < 2:
        return False
    if re.fullmatch(r"[a-z0-9.\-]+\.[a-z]{2,}", name.lower()):  # a bare hostname
        return is_contextually_relevant_host(name, doc_url=url, target_objective=objective)
    return True


def answers_are_subjects(data: dict[str, Any]) -> bool:
    """True when the question asks which things do something, so the subject is the answer.

    "Which companies use Teamcenter?" is answered by the subjects of "X uses Teamcenter".
    "Who is the chief executive of Acme?" is answered by the object. A list question carries a
    parsed enumeration objective; without one, the object is the answer.

    A filled-in form is a list request by construction ("which <things> <do something>"), so it
    does not depend on the objective's phrasing being parsed.
    """
    return bool(data.get("enumeration_objective")) or brief_from_data(data) is not None


def build_answer_rows(data: dict[str, Any]) -> tuple[list[str], list[AnswerRow]]:
    """The answer rows of a run, and the attribute columns that have any value.

    Rows are ordered strongest evidence first, then by how many sources confirm them, so the
    reader starts at the top. Several claims about one answer become one row. When the run came
    from a filled-in form, the form's own limits apply last: see ``excluded_by_brief``.
    """
    claims = [c for c in data.get("claims") or [] if str(c.get("status") or "").upper() in POSITIVE]
    objective = str(data.get("objective") or data.get("target") or "")
    evidence = {e.get("evidence_id"): e for e in data.get("evidence") or [] if e.get("evidence_id")}
    by_subject = answers_are_subjects(data)

    rows: dict[str, AnswerRow] = {}
    attributes: dict[str, dict[str, str]] = {}

    brief = brief_from_data(data)

    for claim in claims:
        subject = str(claim.get("subject") or "").strip()
        obj = str(claim.get("object") or "").strip()
        predicate = str(claim.get("predicate") or "").strip()
        ev = evidence.get(claim.get("evidence_id")) or {}
        url = str(claim.get("citation") or claim.get("source_url") or ev.get("url") or "").strip()
        if brief is not None and url and brief.excludes_url(url):
            continue  # the form said not to use this site, so nothing may rest on it
        quote = str(claim.get("source_passage") or ev.get("snippet") or "").strip()

        # An attribute of something already answered belongs in that row, not in a row of its own.
        column = _attribute_for(predicate)
        if column and subject:
            attributes.setdefault(_norm(subject), {}).setdefault(column, obj)
            continue

        # Checked before cleaning: clean_entity_name cuts a host down to its first label ("rr1"),
        # which would hide what the name is.
        raw_answer = subject if by_subject else (obj or subject)
        if not is_answerable(raw_answer, objective, url):
            continue
        answer = clean_entity_name(raw_answer) or raw_answer
        detail = f"{predicate} {obj}".strip() if by_subject else f"{subject} {predicate}".strip()

        key = _norm(answer)
        row = rows.get(key)
        if row is None:
            row = rows[key] = AnswerRow(answer=answer, detail=detail)
        if url:
            host = _host(url)
            if host and host not in row._hosts:
                row._hosts.add(host)
                row._urls.append(url)
            elif not row._urls:
                row._urls.append(url)
        # The row shows the longest quote found for it, which is the most readable evidence.
        if len(quote) > len(row.evidence_says):
            row.evidence_says, row.evidence_url = quote, url or row.evidence_url
            row.evidence_type = evidence_type_of(url, str(ev.get("title") or ""), str(claim.get("source_class") or ""))
        row._quoted = row._quoted or bool(quote)
        row._corroborated = row._corroborated or str(claim.get("status") or "").upper() == "CORROBORATED"

    for key, row in rows.items():
        row.attributes = attributes.get(key, {})
        row.sources = max(1, len(row._hosts))
        row.evidence_strength = evidence_strength(
            "CORROBORATED" if row._corroborated else "SUPPORTED", row.sources, row._quoted
        )
        if not row.evidence_url and row._urls:
            row.evidence_url = row._urls[0]

    if brief is not None:
        for row in rows.values():
            row.known_to_user = brief.is_known(row.answer)
        rows = {k: r for k, r in rows.items()
                if not brief.rejects(r.answer, r.evidence_strength, r.evidence_type)}

    order = {STRONG: 0, MODERATE: 1, WEAK: 2}
    ordered = sorted(rows.values(), key=lambda r: (order[r.evidence_strength], -r.sources, _norm(r.answer)))
    used_columns = [c for c, _ in ATTRIBUTE_COLUMNS if any(r.attributes.get(c) for r in ordered)]
    return used_columns, ordered


def excluded_by_brief(data: dict[str, Any]) -> dict[str, int]:
    """How many answers the filled-in form itself left out, and why.

    The form narrows the sheet; the run still found these, so the count is reported rather than
    quietly dropped. Empty when a plain question was asked.
    """
    brief = brief_from_data(data)
    if brief is None:
        return {}
    # The same run read with the form's limits lifted: the question itself is unchanged, so the
    # rows are comparable and the difference is only what the form removed.
    unlimited = dict(data)
    unlimited["brief"] = {**brief.as_dict(), "evidence_floor": "any", "evidence_kinds": [],
                          "exclude_answers": [], "exclude_sites": []}
    unlimited.pop("objective_contract", None)
    _, all_rows = build_answer_rows(unlimited)
    kept = {_norm(r.answer) for r in build_answer_rows(data)[1]}
    reasons: dict[str, int] = {}
    for row in all_rows:
        if _norm(row.answer) in kept:
            continue
        # The most specific reason first: with every page of its evidence excluded, nothing else
        # about the answer mattered.
        if row._urls and all(brief.excludes_url(u) for u in row._urls):
            why = "its only evidence was on a site you excluded"
        else:
            why = brief.rejects(row.answer, row.evidence_strength, row.evidence_type) or "the form left it out"
        reasons[why] = reasons.get(why, 0) + 1
    return reasons


def answer_noun(data: dict[str, Any]) -> str:
    """What the rows are, in the question's own words ("companies", "answers")."""
    brief = brief_from_data(data)
    if brief is not None and brief.looking_for:
        return brief.looking_for
    enum = data.get("enumeration_objective") or {}
    noun = str(enum.get("answer_noun") or "").strip() if isinstance(enum, dict) else ""
    return noun or "answers"
