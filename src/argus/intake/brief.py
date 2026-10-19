"""The research brief: what the user fills in instead of typing one question.

A one-line question leaves the research guessing: which country, how old a fact may be, what counts
as evidence, which companies to leave out. The brief asks for those once, and every field here
changes the run. Nothing is collected for the sake of looking thorough.

    from argus.intake.brief import FIELDS, ResearchBrief

    brief = ResearchBrief.from_answers({"looking_for": "hospitals", "criterion": "use Epic", ...})
    engine.start_investigation(brief.to_objective(), contract=brief.to_contract())

``FIELDS`` is the single definition both front ends render: the terminal form
(``osint-terminal --form``) and the web form (``osint-terminal --web``).
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields as dataclass_fields
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

# What each answer's evidence must carry before it is listed. The floor filters the answers; the
# research itself still records everything, so a run can be re-read at a lower floor.
EVIDENCE_FLOORS = {
    "any": "list everything that passed the evidence check",
    "quoted": "only answers with a quote from the page (Moderate or Strong)",
    "two_sources": "only answers confirmed by two or more independent sites (Strong)",
}
_FLOOR_RANK = {"any": 0, "quoted": 1, "two_sources": 2}
_STRENGTH_RANK = {"Weak": 0, "Moderate": 1, "Strong": 2}

# Evidence kinds the reader may accept, as answer_rows.evidence_type_of labels them.
EVIDENCE_KINDS = ["Job post", "Case study", "Filing", "Registry", "Press release", "News",
                  "Reference page", "Forum post", "Archived copy", "Search snippet", "Web page"]

# How long the run may work. One step is one search or one page.
DEPTHS = {"quick": 15, "standard": 60, "thorough": 120}

ATTRIBUTES = ["website", "location", "industry", "approximate size", "contact details"]


@dataclass
class FormField:
    """One question on the form, and what it changes in the run."""

    name: str
    label: str
    kind: str  # text | long_text | choice | multi_choice | number
    help: str
    effect: str  # what this field changes; shown on the form so no field is decoration
    required: bool = False
    choices: tuple[str, ...] = ()
    default: Any = ""
    placeholder: str = ""


FIELDS: tuple[FormField, ...] = (
    FormField(
        "looking_for", "What are you looking for?", "text",
        "The kind of thing you want listed: companies, hospitals, vineyards, people, products, papers.",
        "Names the answer column and tells the research what shape of answer counts.",
        required=True, placeholder="companies",
    ),
    FormField(
        "criterion", "What must be true of them?", "text",
        "The thing that qualifies an answer, in your own words.",
        "Becomes the heart of the question and the searches run for it.",
        required=True, placeholder="use Siemens Teamcenter",
    ),
    FormField(
        "where", "Where?", "text",
        "A country, state or region. Leave empty for anywhere.",
        "Answers a page places outside this area are dropped.",
        placeholder="USA",
    ),
    FormField(
        "as_of", "Facts as of", "text",
        "A date, if the answer depends on when. Leave empty for today.",
        "Sets the as-of date, so a superseded fact is reported as superseded.",
        placeholder="2026-10-01",
    ),
    FormField(
        "attributes", "What should it collect about each one?", "multi_choice",
        "Only pick what you will use. Each one adds work.",
        "Each becomes part of the question, so the research looks for it and the sheet gets a column.",
        choices=tuple(ATTRIBUTES),
    ),
    FormField(
        "evidence_floor", "Minimum evidence to list an answer", "choice",
        "Every answer has already passed the evidence check; this is how much more you want.",
        "Answers below the floor are left out of the sheet and counted on the method sheet.",
        choices=tuple(EVIDENCE_FLOORS), default="any",
    ),
    FormField(
        "evidence_kinds", "Evidence you will accept", "multi_choice",
        "Leave all unticked to accept any kind.",
        "An answer whose only evidence is of another kind is left out and counted.",
        choices=tuple(EVIDENCE_KINDS),
    ),
    FormField(
        "exclude_answers", "Leave these out", "long_text",
        "One per line: competitors, consultancies, anyone you don't want in the list.",
        "A matching answer is dropped before the sheet is written.",
        placeholder="Siemens\nAccenture",
    ),
    FormField(
        "exclude_sites", "Don't use these sites", "long_text",
        "One host per line.",
        "Evidence from these hosts is not used, so no answer rests on them.",
        placeholder="example-aggregator.com",
    ),
    FormField(
        "seed_urls", "Pages to read first", "long_text",
        "One URL per line: a list you already trust, a directory, a report.",
        "Each is fetched first, as your own request.",
        placeholder="https://example.org/customer-list",
    ),
    FormField(
        "known_examples", "Ones you already know", "long_text",
        "One per line. They are still listed, marked as already known.",
        "The sheet marks each answer new or already known, so you can see what the run added.",
        placeholder="Hermeus\nGulfstream Aerospace",
    ),
    FormField(
        "how_many", "How many answers is enough?", "number",
        "Leave empty to keep going until the budget runs out.",
        "The run stops early once this many answers have passed the evidence check.",
        placeholder="25",
    ),
    FormField(
        "depth", "How long may it work?", "choice",
        "quick is about 15 steps, standard 60, thorough 120. One step is a search or a page.",
        "Sets the step budget.",
        choices=tuple(DEPTHS), default="standard",
    ),
    FormField(
        "notes", "Anything else it should know", "long_text",
        "Constraints, phrasing, synonyms for the thing you are looking for.",
        "Added to the question, so it reaches the planner and the searches.",
    ),
)

FIELDS_BY_NAME = {f.name: f for f in FIELDS}


def _lines(text: str) -> list[str]:
    return [line.strip() for line in re.split(r"[\n,]+", str(text or "")) if line.strip()]


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


@dataclass
class ResearchBrief:
    """A filled-in form, and the question and contract it compiles to."""

    looking_for: str
    criterion: str
    where: str = ""
    as_of: str = ""
    attributes: list[str] = field(default_factory=list)
    evidence_floor: str = "any"
    evidence_kinds: list[str] = field(default_factory=list)
    exclude_answers: list[str] = field(default_factory=list)
    exclude_sites: list[str] = field(default_factory=list)
    seed_urls: list[str] = field(default_factory=list)
    known_examples: list[str] = field(default_factory=list)
    how_many: int | None = None
    depth: str = "standard"
    notes: str = ""
    filled_at: str = ""

    # --- building ---------------------------------------------------------------------------

    @classmethod
    def from_answers(cls, answers: dict[str, Any]) -> "ResearchBrief":
        """Build a brief from form answers, raising ValueError on anything unusable."""
        def text(name: str) -> str:
            return str(answers.get(name) or "").strip()

        def many(name: str) -> list[str]:
            value = answers.get(name) or []
            return [str(v).strip() for v in value if str(v).strip()] if isinstance(value, list) else _lines(value)

        for name in ("looking_for", "criterion"):
            if not text(name):
                raise ValueError(f"{FIELDS_BY_NAME[name].label} is required")

        floor = text("evidence_floor") or "any"
        if floor not in EVIDENCE_FLOORS:
            raise ValueError(f"Minimum evidence must be one of {', '.join(EVIDENCE_FLOORS)}")
        depth = text("depth") or "standard"
        if depth not in DEPTHS:
            raise ValueError(f"Depth must be one of {', '.join(DEPTHS)}")
        kinds = [k for k in many("evidence_kinds")]
        unknown = [k for k in kinds if k not in EVIDENCE_KINDS]
        if unknown:
            raise ValueError(f"Unknown evidence kind: {', '.join(unknown)}")

        how_many_raw = text("how_many")
        how_many: int | None = None
        if how_many_raw:
            if not how_many_raw.isdigit() or int(how_many_raw) < 1:
                raise ValueError("How many answers must be a whole number above zero")
            how_many = int(how_many_raw)

        urls = many("seed_urls")
        bad = [u for u in urls if not u.lower().startswith(("http://", "https://"))]
        if bad:
            raise ValueError(f"Pages to read first must start with http:// or https:// ({bad[0]})")

        return cls(
            looking_for=text("looking_for"), criterion=text("criterion"), where=text("where"),
            as_of=text("as_of"), attributes=[a for a in many("attributes")], evidence_floor=floor,
            evidence_kinds=kinds, exclude_answers=many("exclude_answers"), exclude_sites=many("exclude_sites"),
            seed_urls=urls, known_examples=many("known_examples"), how_many=how_many, depth=depth,
            notes=text("notes"), filled_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )

    # --- what the run is given ---------------------------------------------------------------

    def to_objective(self) -> str:
        """The question the research is given, in the user's own words."""
        parts = [f"Which {self.looking_for} {self.criterion}"]
        if self.where:
            parts.append(f"in {self.where}")
        question = " ".join(parts).rstrip("?") + "?"
        if self.attributes:
            question += f" Include each one's {_join(self.attributes)}."
        if self.notes:
            question += f" {self.notes.rstrip('.')}."
        if self.seed_urls:
            question += " " + " ".join(self.seed_urls)
        return question

    def to_contract(self) -> dict[str, Any]:
        """The contract the engine is given, with the brief kept whole for the reports."""
        contract: dict[str, Any] = {"max_steps": DEPTHS[self.depth], "brief": self.as_dict()}
        if self.how_many:
            contract["target_answer_count"] = self.how_many
        if self.known_examples:
            contract["known_context"] = {"known_answers": self.known_examples}
        return contract

    def as_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in dataclass_fields(self)}

    def save(self, directory: str | Path) -> Path:
        """Keep the filled-in form beside the run, so a run can be repeated exactly."""
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "_", f"{self.looking_for} {self.criterion}".lower())[:60].strip("_")
        path = directory / f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{slug}.json"
        path.write_text(json.dumps(self.as_dict(), indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: str | Path) -> "ResearchBrief":
        return cls.from_answers(json.loads(Path(path).read_text(encoding="utf-8")))

    # --- what the brief does to the answers --------------------------------------------------

    def rejects(self, answer: str, strength: str, evidence_kind: str) -> str:
        """Why the brief leaves this answer out, or "" when it stays.

        The reason is kept rather than discarded, so the method sheet can say how many answers the
        form itself removed. A run is never silently narrowed.
        """
        norm = _norm(answer)
        if any(_norm(x) and _norm(x) in norm for x in self.exclude_answers):
            return "you asked to leave it out"
        if _STRENGTH_RANK.get(strength, 0) < _FLOOR_RANK[self.evidence_floor]:
            return f"below your evidence floor ({self.evidence_floor})"
        if self.evidence_kinds and evidence_kind not in self.evidence_kinds:
            return f"evidence is a {evidence_kind.lower()}, which you did not accept"
        return ""

    def excludes_url(self, url: str) -> bool:
        host = re.sub(r"^https?://", "", str(url or "")).split("/")[0].lower().removeprefix("www.")
        return any(site.lower().removeprefix("www.") in host for site in self.exclude_sites if site)

    def is_known(self, answer: str) -> bool:
        norm = _norm(answer)
        return any(_norm(x) and _norm(x) in norm for x in self.known_examples)


def _join(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + f" and {items[-1]}"


def brief_from_data(data: dict[str, Any]) -> ResearchBrief | None:
    """The brief a run was given, from the run payload, or None when a plain question was asked."""
    raw = data.get("brief") or (data.get("objective_contract") or {}).get("brief")
    if not raw:
        return None
    try:
        return ResearchBrief.from_answers(raw)
    except ValueError:
        return None
