"""World country gazetteer used to recognize and normalize place names (data in countries.json).

Reference data covering every country equally (UN member and observer states plus
widely used territories), so no country is favoured over another. Each entry is
canonical name -> extra aliases (short forms and demonyms). Lookups are
case-insensitive; two-letter ISO codes are deliberately not aliases because they
collide with ordinary words ("in", "us", "it").
"""

from __future__ import annotations

import json
from pathlib import Path

_DATA = Path(__file__).with_name("countries.json")
COUNTRIES: dict[str, tuple[str, ...]] = {
    name: tuple(aliases) for name, aliases in json.loads(_DATA.read_text(encoding="utf-8")).items()
}

# Canonical names that read naturally with a leading "the" ("in the Netherlands").
# Plural or "Republic"/"United" style names take it; the rule is spelled out instead of listed.
TAKES_ARTICLE: frozenset[str] = frozenset(
    name for name in COUNTRIES
    if name.startswith(("United ", "Central African", "Democratic Republic", "Dominican"))
    or name.endswith(("lands", "Islands", "mas", "pines", "ives", "elles", "oros"))
    or name == "Gambia"
)


def build_aliases() -> dict[str, str]:
    """Lower-case alias -> canonical country name."""
    aliases: dict[str, str] = {}
    for name, extra in COUNTRIES.items():
        aliases[name.lower()] = name
        for alias in extra:
            aliases.setdefault(alias.lower(), name)
    return aliases
