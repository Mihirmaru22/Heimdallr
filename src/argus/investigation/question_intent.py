"""Interpret a free-form research objective: its subject(s), what kind of answer it asks for, and focus terms.

Works from the wording alone, for any topic: no subject, company, product or place is
special-cased. Subjects are proper-noun runs (with geography and question scaffolding
removed); when the objective has no proper noun, the subject is its topic phrase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re

from argus.investigation.geography import build_aliases

_PLACES = build_aliases()

# Words that open or frame a request, never part of a subject.
_SCAFFOLD = frozenset({
    "what", "which", "who", "whom", "whose", "when", "where", "why", "how", "is", "are", "was", "were",
    "do", "does", "did", "can", "could", "should", "would", "will", "has", "have", "had", "the", "a", "an",
    "find", "list", "show", "get", "give", "tell", "search", "identify", "trace", "investigate", "verify",
    "research", "evaluate", "compare", "summarize", "summarise", "describe", "explain", "determine",
    "enumerate", "analyze", "analyse", "examine", "disambiguate", "parse", "me", "out", "all", "everything",
    "about", "please", "i", "we", "you", "our", "my",
})

# Role and title words: what the question asks for, not who it is about.
_ROLES = frozenset({
    "ceo", "cto", "cfo", "coo", "ciso", "cio", "cmo", "chairman", "chairwoman", "chair", "president",
    "founder", "founders", "co-founder", "director", "directors", "owner", "owners", "head", "vp", "svp",
    "evp", "chief", "officer", "officers", "executive", "executives", "board", "leader", "leaders",
})

_STOPWORDS = frozenset({
    "of", "in", "on", "at", "to", "for", "from", "by", "with", "and", "or", "but", "than", "that", "this",
    "these", "those", "their", "its", "it", "they", "them", "be", "been", "being", "into", "over", "under",
    "between", "against", "among", "about", "as", "if", "so", "any", "some", "each", "per", "via", "vs",
    "versus", "current", "currently", "recent", "recently", "main", "key", "major", "there", "then", "not",
    "use", "uses", "used", "using", "apply", "applies", "work", "works", "get", "got", "own", "owns",
}) | _SCAFFOLD

_CONNECTORS = frozenset({"of", "for", "de", "du", "la", "le", "von", "van", "der", "&"})

_LOCATIVE = frozenset({"in", "across", "within", "throughout", "near", "around"})

_TOKEN = re.compile(r"[A-Za-z0-9][\w\-\.&']*")


@dataclass
class ObjectiveIntent:
    """What a free-form objective asks."""

    kind: str  # causal | mechanism | comparison | change | yes_no | role | attribute | summary | listing | open
    subjects: list[str] = field(default_factory=list)
    focus: str = ""  # the requested property, facet or topic words
    facets: list[str] = field(default_factory=list)
    periods: list[str] = field(default_factory=list)
    scope: str = ""  # the phrase the question is about, in the user's words ("PLM vendors in 2025")
    context: str = ""  # a "for ..." qualifier ("for aerospace suppliers")


def _is_place(phrase: str) -> bool:
    p = phrase.lower().strip()
    return p in _PLACES or (p.startswith("the ") and p[4:] in _PLACES)


def _strip_possessive(tok: str) -> str:
    return re.sub(r"['’]s$", "", tok.strip(".,;:!?\"()"))


def _is_proper(tok: str, position: int) -> bool:
    core = _strip_possessive(tok)
    if not core:
        return False
    if core.lower() in _SCAFFOLD or core.lower() in _ROLES:
        return False
    if any(c.isupper() for c in core[1:]) or (core[0].isupper() and position > 0):
        return True
    if core[0].isupper() and position == 0:
        return core.lower() not in _STOPWORDS
    # Model numbers next to a name ("737 MAX") join a proper run but never start one.
    return False


def extract_subjects(objective: str) -> list[str]:
    """Proper-noun subjects of the objective, geography and role words excluded."""
    text = (objective or "").strip()
    tokens = _TOKEN.findall(text)
    subjects: list[str] = []
    located: list[str] = []  # names used as a location ("suppliers in Michigan")
    run: list[str] = []
    run_start = [0]

    def flush() -> None:
        while run and run[-1].lower() in _CONNECTORS:
            run.pop()
        if run:
            phrase = " ".join(_strip_possessive(t) for t in run).strip()
            before = tokens[run_start[0] - 1].lower() if run_start[0] > 0 else ""
            if phrase and not _is_place(phrase) and phrase not in subjects:
                (located if before in _LOCATIVE else subjects).append(phrase)
        run.clear()

    for i, tok in enumerate(tokens):
        core = _strip_possessive(tok)
        if _is_proper(tok, i):
            if not run:
                run_start[0] = i
            run.append(tok)
            if tok != core and tok.endswith(("'s", "’s")):
                # "Boeing's 737 MAX": keep the possessor and its object together.
                continue
        elif run and (core.isdigit() or re.fullmatch(r"\d[\w\-]*", core)):
            run.append(tok)
        elif run and core.lower() in _CONNECTORS and i + 1 < len(tokens) and _is_proper(tokens[i + 1], i + 1):
            run.append(tok)
        else:
            flush()
    flush()
    # A name only ever used as a location is kept when nothing else names the subject.
    return subjects or located


def topic_phrase(objective: str) -> str:
    """The objective without its question scaffolding, for objectives with no proper noun."""
    words = [w.strip(".,;:!?\"'()") for w in (objective or "").split()]
    while words and words[0].lower() in _SCAFFOLD:
        words.pop(0)
    while words and words[-1].lower() in _STOPWORDS:
        words.pop()
    return " ".join(w for w in words if w)


def content_terms(text: str, exclude: set[str] | None = None) -> list[str]:
    """Content words in order, without scaffolding, stopwords or excluded words."""
    exclude = {e.lower() for e in (exclude or set())}
    out: list[str] = []
    for w in _TOKEN.findall(text or ""):
        core = _strip_possessive(w)
        low = core.lower()
        if low in _STOPWORDS or low in exclude or len(low) < 2 or low in out:
            continue
        out.append(core)
    return out


_ROLE_OF_VERB = {
    "founded": "founder", "co-founded": "co-founder", "created": "creator", "invented": "inventor",
    "leads": "leader", "runs": "leader", "owns": "owner", "started": "founder",
}
_CAUSE_WORDS = {"cause", "causes", "caused", "reason", "reasons", "why", "happen", "happened", "get", "got"}

_PERIOD = re.compile(r"\b(?:1[89]\d\d|20\d\d)\b")


def classify_intent(objective: str) -> ObjectiveIntent:
    """Classify the objective's question form and pull out its subjects and focus."""
    text = (objective or "").strip()
    low = text.lower().rstrip("?. ")
    subjects = extract_subjects(text)
    periods = _PERIOD.findall(text)
    subject_words = {w.lower() for s in subjects for w in s.split()}
    focus_words = content_terms(text, subject_words | {p.lower() for p in periods})
    focus = " ".join(focus_words)

    def intent(kind: str, **kw) -> ObjectiveIntent:
        return ObjectiveIntent(kind=kind, subjects=subjects, focus=kw.pop("focus", focus), periods=periods, **kw)

    bare = text.rstrip("?. ")
    m = re.match(r"^(?:compare|contrast)\s+(.+?)(?:\s+(?:on|in terms of|regarding)\s+(.+?))?(?:\s+for\s+(.+))?$", bare, re.I)
    if m or re.search(r"\b(?:vs\.?|versus|difference between|differences between)\b", low):
        facets = []
        if m and m.group(2):
            facets = [f.strip().lower() for f in re.split(r",\s*(?:and\s+)?|\s+and\s+", m.group(2)) if f.strip()]
        return intent("comparison", facets=facets, context=(m.group(3) or "") if m else "")
    if re.match(r"^why\b", low) or re.search(r"\b(?:causes?|reasons?)\s+(?:of|for|behind)\b", low):
        words = [w for w in focus_words if w.lower() not in _CAUSE_WORDS]
        lead = periods[0] + " " if len(periods) == 1 else ""
        return intent("causal", scope=f"the {lead}{' '.join([*subjects, *words])}".strip())
    if re.match(r"^how\s+(?:does|do|did|is|are|can)\b", low):
        found = intent("mechanism")
        phrase = re.sub(r"\s+(?:work|works|function|functions|happen|operate|operates)$", "", topic_phrase(text))
        if phrase and len(phrase.split()) <= 6:
            found.subjects = [phrase] + [s for s in found.subjects if s.lower() not in phrase.lower()]
        return found
    if re.search(r"\bwhat\s+(?:has\s+)?changed\b|\bchanges?\s+(?:in|to)\b.*\bbetween\b", low):
        return intent("change")
    if re.match(r"^(?:summari[sz]e|overview\s+of|give\s+(?:me\s+)?an?\s+overview)", low):
        return intent("summary", scope=topic_phrase(re.sub(r"^(?:summari[sz]e|overview\s+of|give\s+(?:me\s+)?an?\s+overview\s+of)\s+", "", bare, flags=re.I)))
    if re.match(r"^who\b", low):
        words = re.findall(r"[a-z\-]+", low)
        roles = [w for w in words if w in _ROLES] or [_ROLE_OF_VERB[w] for w in words if w in _ROLE_OF_VERB]
        return intent("role", facets=roles)
    if re.match(r"^(?:is|are|was|were|does|do|did|has|have|had|can)\b", low):
        return intent("yes_no")
    m = (
        re.match(r"^(?:find|get|what\s+(?:is|are|was|were))\s+(?:the\s+)?(.+?)\s+(?:of|for)\s+(.+)$", bare, re.I)
        or re.match(r"^what\s+(.+?)\s+(?:apply|applies|exist|exists)\s+(?:to|for|in)\s+(.+)$", bare, re.I)
    )
    if m:
        facets = [f.strip().lower() for f in re.split(r",\s*(?:and\s+)?|\s+and\s+", m.group(1)) if f.strip()]
        found = intent("attribute", facets=facets, scope=topic_phrase(m.group(2)))
        if not found.subjects:
            found.subjects = [found.scope]
        return found
    m = re.match(r"^(?:which|list|name|what)\s+(?:out\s+|all\s+|the\s+)?(.+?)\s+(?:in|at|that|which|who|are|is|does|do|did|have|has|were|was)\b", low)
    if m or re.match(r"^(?:which|list|name|what)\b", low):
        return intent("listing", scope=m.group(1) if m else "")
    return intent("open")


_INTENT_OPTIONS = {
    "causal": "asks why something happened or what caused it",
    "mechanism": "asks how something works or operates",
    "comparison": "compares two or more things",
    "change": "asks what changed over a period",
    "yes_no": "asks whether something is true (a yes or no question)",
    "role": "asks who holds a role or did something",
    "attribute": "asks for a specific property or value of something",
    "summary": "asks for a summary or overview",
    "listing": "asks for a list of items, organizations, people or places",
    "open": "an open question that fits none of the above",
}


def decide_intent(objective: str) -> ObjectiveIntent:
    """The question form chosen by Laya; the parsed parts (subjects, facets, scope) come from the rules.

    When Laya picks another form than the rules, the form-specific parts the rules found for their
    form are dropped (the planner falls back to the subject and topic for those).
    """
    from argus.brain.decisions import get_decisions

    found = classify_intent(objective)
    kind = get_decisions().choose(
        "question_form", objective, "What does this question ask for?", _INTENT_OPTIONS, found.kind,
    ).answer
    if kind == found.kind:
        return found
    return ObjectiveIntent(kind=kind, subjects=found.subjects, focus=found.focus, periods=found.periods,
                           scope=topic_phrase(objective) if kind in ("listing", "summary", "causal") else "")
