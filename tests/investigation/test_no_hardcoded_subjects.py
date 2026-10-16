"""Production code must not carry the names of benchmark fixtures or past subjects (V3 FC1 T09).

Answers have to come from evidence. These names were once special-cased in production
logic (people, companies, places, threat groups, fictional benchmark entities); the test
keeps them from coming back. Eval corpora, benchmark tasks and tests may still use them.
"""

from __future__ import annotations

from pathlib import Path
import re

from argus.investigation.contradiction_resolver import ContradictionResolver, EntityScopeVerifier, EpistemicSufficiencyEvaluator
from argus.investigation.objective_parser import normalize_geography

SRC = Path(__file__).resolve().parents[2] / "src" / "argus"

# Fixture data lives here; everything else is production code.
EXCLUDED_PARTS = {"evals", "benchmark", "__pycache__"}
EXCLUDED_FILES = {"corpus.py", "tasks.py"}

FORMERLY_HARDCODED = [
    "raiyani", "rajkot", "gujarat", "vcite", "meucci", "elisha gray", "graham bell", "sandworm", "apt41",
    "aethelgard", "zephyrus", "thalassa", "helix", "valerius", "hesperus", "borealis", "kuka", "autotech",
    "hoplites", "scramjet", "teleportation", "warp drive", "lunar bioscience", "mars bureau",
    "linux foundation", "not a superconductor", "zero excess events", "weathering prevents",
    "undeciphered", "fermi", "drake", "orbital", "biofoundry", "oceanics", "usda", "iaea", "nejm",
    "fraunhofer", "list out companies in india which uses sap erp",
]


def _production_files() -> list[Path]:
    return [
        p for p in SRC.rglob("*.py")
        if not (EXCLUDED_PARTS & set(p.relative_to(SRC).parts)) and p.name not in EXCLUDED_FILES
        and "capability_registry/benchmark.py" not in p.as_posix()
    ]


def _code_without_comments(path: Path) -> str:
    """Source text minus comments and docstrings, so explanatory examples are allowed."""
    import ast
    import io
    import tokenize

    src = path.read_text(encoding="utf-8")
    doc_lines: set[int] = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant) and isinstance(first.value.value, str):
                doc_lines.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    out = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT or tok.start[0] in doc_lines:
            continue
        out.append(tok.string)
    return " ".join(out).lower()


def test_no_formerly_hardcoded_subject_in_production_logic():
    hits = []
    for path in _production_files():
        code = _code_without_comments(path)
        for name in FORMERLY_HARDCODED:
            if re.search(rf"(?<![a-z]){re.escape(name)}(?![a-z])", code):
                hits.append(f"{path.relative_to(SRC)}: {name}")
    assert not hits, "Hardcoded subjects in production code:\n" + "\n".join(hits)


def test_geography_covers_every_country_not_a_favoured_few():
    for place in ("Nigeria", "Vietnam", "Peru", "Kazakhstan", "New Zealand", "nigerian", "the Netherlands"):
        assert normalize_geography(place), place


def test_categorical_values_come_from_the_sentence():
    resolver = ContradictionResolver()
    docs = [
        {"text": "The 2031 breach was attributed to Crimson Kestrel according to the national CERT.", "url": "https://a.example.org/x"},
        {"text": "Investigators later attributed the 2031 breach to Silver Ibis.", "url": "https://b.example.net/y"},
    ]
    claims = resolver.extract_comparable_claims(docs, target_subject="2031 breach")
    values = {c.categorical_value for c in claims if c.property_dim == "attribution"}
    assert values == {"crimson kestrel", "silver ibis"}
    assert resolver.detect_contradictions(claims)


def test_scoped_sub_unit_needs_its_own_words_in_one_sentence():
    docs = [{"text": "Norvale Group runs hospitals. Its research arm publishes papers.", "url": "https://n.example.com"}]
    grounded, absent, _ = EntityScopeVerifier.verify_entity_presence("Norvale Quantum Division", docs)
    assert not grounded and not absent

    docs = [{"text": "The Norvale quantum unit does not exist; the company never created one.", "url": "https://n.example.com"}]
    grounded, absent, _ = EntityScopeVerifier.verify_entity_presence("Norvale Quantum Division", docs)
    assert absent


def test_nonpublic_detail_request_needs_matching_evidence():
    docs = [{"text": "Brightwater operates a data centre in Oslo.", "url": "https://b.example.com"}]
    ok, reason = EpistemicSufficiencyEvaluator.evaluate_sufficiency(
        docs, objective="Determine Brightwater's internal storage replication topology and failover layout."
    )
    assert not ok and "non-public or proprietary" in reason
