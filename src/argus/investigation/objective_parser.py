"""Structured interpretation of enumeration objectives.

Turns list-style research requests such as

    "Search Companies who are using TEAMCENTER in usa"
    "banks in Australia using Temenos core banking"
    "list companies in India which use SAP ERP"

into an explicit objective:

    answer type  -> organizations (with the user's own noun, e.g. "banks")
    relation     -> use / deploy
    object       -> the product or technology named by the user
    constraints  -> geography (normalized) and any other "in <context>" qualifier

The parser is grammar-based. It knows generic vocabulary (organization nouns,
usage verbs, country names) and nothing about particular products, vendors or
companies. ``refine_object_from_evidence`` can later qualify the object with
the vendor name that retrieved sources consistently attach to it (e.g.
"Teamcenter" -> "Siemens Teamcenter"); that refinement comes from evidence,
not from a lookup table.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any, Iterable

from argus.investigation.geography import TAKES_ARTICLE, build_aliases


ANSWER_TYPE_ORGANIZATION = "ORGANIZATION"
RELATION_USES = "USES"

# Generic nouns that denote organizations. The user's own noun is preserved.
_ORG_NOUNS = (
    "companies", "company", "organizations", "organisations", "organization", "organisation",
    "firms", "businesses", "enterprises", "corporations", "manufacturers", "customers", "clients",
    "users", "banks", "hospitals", "universities", "colleges", "schools", "retailers", "insurers",
    "startups", "vendors", "suppliers", "agencies", "brands", "employers", "institutions",
    "airlines", "utilities", "municipalities", "governments", "operators", "carriers", "labs",
    "laboratories", "providers", "distributors", "contractors", "automakers", "oems",
)

# Usage relations, normalized to RELATION_USES.
_USE_VERBS = (
    r"(?:are\s+|is\s+|have\s+|has\s+|currently\s+)*"
    r"(?:using|uses|use|used|deploying|deploys|deployed|deploy|running|runs|run|"
    r"adopting|adopts|adopted|adopt|implementing|implements|implemented|implement|"
    r"rely(?:ing)?\s+on|relies\s+on|standardi[sz]ed\s+on|built\s+on|licens(?:e|es|ed|ing)|on)"
)

_LEADING_COMMANDS = re.compile(
    r"^(?:please\s+)?(?:(?:can|could)\s+you\s+)?"
    r"(?:search(?:\s+for)?|find(?:\s+out)?|list(?:\s+out)?|show(?:\s+me)?|give\s+me|get(?:\s+me)?|"
    r"identify|enumerate|name|which|what|who\s+are\s+the|who\s+are)\s+"
    r"(?:(?:a\s+)?list\s+of\s+|all\s+(?:the\s+)?|the\s+|some\s+)?",
    re.IGNORECASE,
)

# Geography normalization from the world gazetteer (every country, no topic data).
_COUNTRY_ALIASES: dict[str, str] = build_aliases()

COUNTRY_ALIASES = _COUNTRY_ALIASES

_GEO_ADJ_RE = "|".join(sorted((re.escape(k) for k in _COUNTRY_ALIASES), key=len, reverse=True))
_NOUN_RE = "|".join(sorted(_ORG_NOUNS, key=len, reverse=True))
_GEO_PREPS = r"(?:based\s+in|located\s+in|headquartered\s+in|operating\s+in|in|from|across|within)"
_CONNECTORS = r"(?:who|which|that|whom)"


@dataclass
class EnumerationObjective:
    """Explicit representation of a list-style objective."""

    raw: str
    answer_type: str
    answer_noun: str
    relation: str
    relation_phrase: str
    object: str
    geography: str = ""
    context_constraints: list[str] = field(default_factory=list)
    object_qualified: str = ""
    object_qualifier_evidence: list[str] = field(default_factory=list)

    # Extractor dimensions this objective needs. Incidental extractors (hosts,
    # e-mails, officers, subsidiaries, sanctions, temporal notes) and specialist
    # chaining are outside the scope of an organization-enumeration objective.
    extraction_scope = ("deployment",)

    @property
    def object_names(self) -> list[str]:
        """All names the object is known by (qualified first)."""
        return [n for n in dict.fromkeys([self.object_qualified, self.object]) if n]

    @property
    def object_name(self) -> str:
        """Best current name of the object (vendor-qualified once evidence supports it)."""
        return self.object_qualified or self.object

    @property
    def answer_label(self) -> str:
        return "organizations" if self.answer_noun in ("company", "companies", "organization", "organizations") else self.answer_noun

    def geo_phrase(self) -> str:
        if not self.geography:
            return ""
        prefix = "the " if self.geography in TAKES_ARTICLE else ""
        return f"in {prefix}{self.geography}"

    def question_text(self) -> str:
        parts = [f"Which {self.answer_label}"]
        if self.geography:
            parts.append(self.geo_phrase())
        parts.append(f"use {self.object_name}")
        if self.context_constraints:
            parts.append("in " + ", ".join(self.context_constraints))
        return " ".join(parts) + "?"

    def _query_parts(self) -> tuple[str, str, str, str]:
        geo = f" {self.geography}" if self.geography else ""
        ctx = f" {' '.join(self.context_constraints)}" if self.context_constraints else ""
        generic = ("company", "companies", "organization", "organizations", "organisation", "organisations", "customers", "clients", "users")
        noun = "companies" if self.answer_noun in generic else self.answer_noun
        return noun, self.object_name, ctx, geo

    def discovery_queries(self) -> list[str]:
        """Compact queries for naming candidate organizations; each names the object and geography."""
        noun, obj, ctx, geo = self._query_parts()
        return [f"{noun} using {obj}{ctx}{geo}", f"{obj} customers{ctx}{geo}"]

    def job_post_queries(self) -> list[str]:
        """Queries for employers' public job posts naming the object (free job boards and career pages)."""
        _, obj, _, geo = self._query_parts()
        sites = ("boards.greenhouse.io", "jobs.lever.co", "jobs.ashbyhq.com", "myworkdayjobs.com")
        return [f'"{obj}" jobs{geo}', *(f'"{obj}" site:{site}' for site in sites)]

    def corroboration_queries(self) -> list[str]:
        """Queries aimed at first-party or independent confirmation rather than aggregator lists."""
        _, obj, ctx, geo = self._query_parts()
        return [f"{obj} customer case study{ctx}{geo}", f"{obj} implementation announcement{ctx}{geo}"]

    def search_queries(self) -> list[str]:
        return self.discovery_queries() + self.corroboration_queries()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["object_name"] = self.object_name
        d["question_text"] = self.question_text()
        d["search_queries"] = self.search_queries()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EnumerationObjective":
        keys = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in keys})


def normalize_geography(raw: str) -> str:
    key = re.sub(r"\s+", " ", (raw or "").strip().lower()).strip(" .,")
    key = re.sub(r"^the\s+", "", key)
    if key in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[key]
    return ""


def _display_object(raw: str) -> str:
    """Tidy the user's object phrase without changing what it names."""
    obj = raw.strip().strip("\"'").strip(" .,;:?!")
    obj = re.sub(r"\s+", " ", obj)
    # A leading article or determiner is grammar, not part of the product name:
    # "uses the teamcenter" names Teamcenter, and sources never write "the Teamcenter".
    obj = re.sub(r"^(?:the|a|an|this|that|these|those|our|their|its|some|any)\s+", "", obj, flags=re.IGNORECASE)
    all_lower = obj == obj.lower()
    words = []
    for w in obj.split(" "):
        # Shouted words ("TEAMCENTER") are normalized; short acronyms ("SAP", "ERP") are kept.
        if len(w) > 4 and w.isupper() and w.isalpha():
            w = w.capitalize()
        # An all-lowercase object ("teamcenter") is shown as a name; matching is case-insensitive.
        elif all_lower and w.isalpha() and len(w) > 3:
            w = w.capitalize()
        words.append(w)
    return " ".join(words)


def _split_trailing_context(obj: str) -> tuple[str, str, list[str]]:
    """Separate a trailing 'in <place>' / 'in <context>' from the object phrase."""
    geography = ""
    context: list[str] = []
    while True:
        m = re.search(rf"\s+{_GEO_PREPS}\s+(?:the\s+)?(?P<tail>[A-Za-z.][A-Za-z.\- ]{{0,40}}?)\s*$", obj, re.IGNORECASE)
        if not m:
            break
        tail = m.group("tail").strip()
        geo = normalize_geography(tail)
        if geo:
            geography = geography or geo
        elif tail[:1].isupper():
            geography = geography or tail.title()
        else:
            context.insert(0, tail)
        obj = obj[: m.start()]
    return obj.strip(), geography, context


def _plural(noun: str) -> str:
    if noun.endswith("s"):
        return noun
    if noun.endswith("y"):
        return noun[:-1] + "ies"
    return noun + "s"


# Words people put before the actual request ("find me the which companies...",
# "can you please tell me all the firms..."). Only these may precede the organization noun
# when it is not at the start, so "why do companies use X" is not read as a list request.
_REQUEST_FILLER = frozenset({
    "please", "can", "could", "would", "will", "you", "i", "we", "want", "need", "like", "to", "know",
    "find", "out", "list", "show", "give", "get", "tell", "search", "for", "identify", "enumerate", "name",
    "me", "us", "the", "a", "an", "all", "some", "any", "which", "what", "who", "are", "is", "of",
    "top", "major", "main", "key", "biggest", "largest", "leading", "known", "notable", "other", "more",
    "about", "and", "those", "these", "them", "there", "here",
})
_NOT_LIST_WORDS = frozenset({"why", "how", "when", "where", "do", "does", "did", "should", "would", "could", "can", "must", "might"})
_WHO_USES = re.compile(rf"^(?:who|whoever)\s+(?:all\s+|else\s+)?(?P<rest>{_USE_VERBS}\s+.+)$", re.IGNORECASE)


def parse_enumeration_objective(objective: str) -> EnumerationObjective | None:
    """Parse a list-style 'organizations that use X' objective, or return None.

    The request may be phrased loosely: any run of request words may come before the
    organization noun ("find me the which companies in uk uses the SAP ERP"), and
    "who uses X in Y" asks for organizations too.
    """
    if not objective or not objective.strip():
        return None
    text = re.sub(r"\s+", " ", objective.strip()).rstrip("?.! ")
    parsed = _parse_body(objective, _LEADING_COMMANDS.sub("", text, count=1))
    if parsed:
        return parsed
    who = _WHO_USES.match(text)
    if who:
        return _parse_body(objective, f"organizations who {who.group('rest')}")
    for m in re.finditer(rf"\b(?:(?:{_GEO_ADJ_RE})\s+)?(?:{_NOUN_RE})\b", text, re.IGNORECASE):
        prefix = re.findall(r"[a-z']+", text[: m.start()].lower())
        if prefix and all(w in _REQUEST_FILLER for w in prefix):
            parsed = _parse_body(objective, text[m.start():])
            if parsed:
                return parsed
    return None


def _parse_body(objective: str, body: str) -> EnumerationObjective | None:
    m = re.match(
        rf"^(?:(?P<geo_adj>{_GEO_ADJ_RE})\s+)?(?P<mods>(?:[A-Za-z\-]+\s+){{0,2}}?)(?P<noun>{_NOUN_RE})\b(?P<rest>.*)$",
        body,
        re.IGNORECASE,
    )
    if not m:
        return None
    # "why do companies use X" / "how do banks use X" ask about reasons or manner, not for a list.
    if set(m.group("mods").lower().split()) & _NOT_LIST_WORDS:
        return None
    noun = m.group("noun").lower()
    rest = m.group("rest")
    geography = normalize_geography(m.group("geo_adj") or "")
    context: list[str] = []

    # "customers of X" / "users of X"
    of_m = re.match(r"^\s+of\s+(?P<obj>.+)$", rest, re.IGNORECASE)
    if of_m and noun in ("customers", "clients", "users"):
        relation_phrase = f"{noun} of"
        obj_raw = of_m.group("obj")
    else:
        # Geography placed before the relation: "banks in Australia using X".
        pre = re.match(
            rf"^\s+{_GEO_PREPS}\s+(?:the\s+)?(?P<geo>[A-Za-z.][A-Za-z.\- ]{{0,40}}?)(?=\s+(?:{_CONNECTORS}\s+)?{_USE_VERBS}\b)",
            rest,
            re.IGNORECASE,
        )
        if pre:
            geography = geography or normalize_geography(pre.group("geo")) or pre.group("geo").strip().title()
            rest = rest[pre.end():]
        rel = re.match(rf"^\s+(?:{_CONNECTORS}\s+)?(?P<rel>{_USE_VERBS})\s+(?P<obj>.+)$", rest, re.IGNORECASE)
        if not rel:
            return None
        relation_phrase = re.sub(r"\s+", " ", rel.group("rel").lower()).strip()
        obj_raw = rel.group("obj")

    obj_raw, tail_geo, tail_ctx = _split_trailing_context(obj_raw)
    geography = geography or tail_geo
    context.extend(tail_ctx)
    obj = _display_object(obj_raw)
    if not obj or obj.lower() in _ORG_NOUNS:
        return None

    return EnumerationObjective(
        raw=objective,
        answer_type=ANSWER_TYPE_ORGANIZATION,
        answer_noun=_plural(noun),
        relation=RELATION_USES,
        relation_phrase=relation_phrase,
        object=obj,
        geography=geography,
        context_constraints=context,
    )


_NON_QUALIFIERS = frozenset({
    "the", "a", "an", "use", "uses", "using", "used", "with", "and", "or", "of", "for", "on", "in",
    "that", "which", "who", "companies", "company", "customers", "about", "via", "by", "new", "our",
    "your", "their", "its", "this", "these", "download", "list", "top", "best", "learn", "explore",
})


def refine_object_from_evidence(enum: EnumerationObjective, texts: Iterable[tuple[str, str]]) -> bool:
    """Qualify the object with the vendor name sources consistently attach to it.

    ``texts`` is an iterable of ``(url, text)``. A qualifier is accepted only when
    it is a capitalized word immediately preceding the object in at least two
    distinct sources and in a majority of the sources that mention the object.
    Returns True when the objective was refined.
    """
    if enum.object_qualified:
        return False
    obj = enum.object
    pattern = re.compile(rf"\b([A-Z][A-Za-z0-9&\-]{{1,30}})\s+{re.escape(obj)}\b", re.IGNORECASE)
    mention_sources: set[str] = set()
    qualifier_sources: dict[str, set[str]] = {}
    display: dict[str, str] = {}
    for url, text in texts:
        if not text or not re.search(rf"\b{re.escape(obj)}\b", text, re.IGNORECASE):
            continue
        mention_sources.add(url)
        for m in pattern.finditer(text):
            word = m.group(1)
            if not word[0].isupper() or word.lower() in _NON_QUALIFIERS or word.lower() == obj.lower():
                continue
            key = word.lower()
            qualifier_sources.setdefault(key, set()).add(url)
            display.setdefault(key, word)
    if not qualifier_sources:
        return False
    best, srcs = max(qualifier_sources.items(), key=lambda kv: len(kv[1]))
    if len(srcs) >= 2 and len(srcs) * 2 > len(mention_sources):
        enum.object_qualified = f"{display[best]} {obj}"
        enum.object_qualifier_evidence = sorted(srcs)
        return True
    return False
