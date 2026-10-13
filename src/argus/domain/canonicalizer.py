"""Entity canonicalization, acronym expansion, and fuzzy identity resolution.

Provides robust token-set matching, corporate acronym expansion, facility stopword stripping,
and cross-source entity deduplication to prevent entity fragmentation and duplicate matrix rows.
"""

from __future__ import annotations

import re
from typing import Sequence

# Known parent automakers & manufacturer keywords
MANUFACTURER_KEYWORDS: frozenset[str] = frozenset(
    {
        "general",
        "motors",
        "gm",
        "ford",
        "stellantis",
        "chrysler",
        "fca",
        "toyota",
        "honda",
        "nissan",
        "bmw",
        "hyundai",
        "subaru",
        "tesla",
        "volkswagen",
        "vw",
        "lucid",
        "rivian",
        "mercedes",
        "daimler",
    }
)

# Common corporate acronym expansions
ACRONYM_MAP: dict[str, str] = {
    "gm": "general motors",
    "vw": "volkswagen",
    "fca": "stellantis",
    "ge": "general electric",
    "ford": "ford motor company",
    "ktp": "kentucky truck plant",
    "giga": "gigafactory",
}

# Facility stopwords describing generic facility types
FACILITY_STOPWORDS: frozenset[str] = frozenset(
    {
        "plant",
        "facility",
        "facilities",
        "assembly",
        "complex",
        "factory",
        "site",
        "works",
        "manufacturing",
        "operations",
        "center",
        "centre",
        "division",
        "co",
        "corp",
        "corporation",
        "inc",
        "ltd",
        "llc",
        "the",
        "gigafactory",
    }
)

# Corporate legal and organizational stopwords
COMPANY_STOPWORDS: frozenset[str] = frozenset(
    {
        "company",
        "corp",
        "corporation",
        "inc",
        "incorporated",
        "ltd",
        "limited",
        "llc",
        "group",
        "holdings",
        "co",
        "the",
        "enterprise",
        "firm",
        "automaker",
        "manufacturer",
        "motors",
        "motor",
    }
)

# Person titles, honorifics, and executive roles
PERSON_TITLES: frozenset[str] = frozenset(
    {
        "mr",
        "mrs",
        "ms",
        "dr",
        "director",
        "manager",
        "plant",
        "lead",
        "head",
        "chief",
        "vp",
        "president",
        "engineer",
        "sr",
        "jr",
        "ii",
        "iii",
    }
)

# Semantic category groups for entity type compatibility
FACILITY_ENTITY_TYPES: frozenset[str] = frozenset(
    {
        "facility",
        "plant",
        "manufacturing_plant",
        "assembly_plant",
        "factory",
        "site",
        "complex",
        "propulsion_plant",
        "stamping_plant",
        "casting_plant",
        "battery_plant",
        "gigafactory",
        "automotive_facility",
    }
)

ORGANIZATION_ENTITY_TYPES: frozenset[str] = frozenset(
    {
        "company",
        "corporation",
        "enterprise",
        "manufacturer",
        "firm",
        "automaker",
        "oem",
        "organization",
        "supplier",
    }
)

PERSON_ENTITY_TYPES: frozenset[str] = frozenset(
    {
        "person",
        "executive",
        "lead",
        "director",
        "manager",
        "engineer",
        "contact",
        "plant_manager",
        "tech_lead",
    }
)

GENERIC_ALIASES: frozenset[str] = frozenset(
    FACILITY_STOPWORDS | COMPANY_STOPWORDS | {"entity", "supplier", "provider", "global", "national"}
)


def is_specific_alias(alias: str) -> bool:
    """Return True if an alias is sufficiently specific for entity resolution."""
    cleaned = alias.strip().lower()
    return len(cleaned) > 2 and cleaned not in GENERIC_ALIASES


def normalize_tokens(text: str, expand_acronyms: bool = True) -> list[str]:
    """Tokenize and normalize text with optional acronym expansion."""
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
    raw_tokens = cleaned.split()
    if not expand_acronyms:
        return raw_tokens

    expanded: list[str] = []
    for token in raw_tokens:
        if token in ACRONYM_MAP:
            expanded.extend(ACRONYM_MAP[token].split())
        else:
            expanded.append(token)
    return expanded


def extract_facility_core_tokens(name: str) -> frozenset[str]:
    """Extract the distinctive core tokens of a facility name.
    
    Strips facility stopwords (e.g. 'Plant', 'Assembly', 'Complex')
    and parent manufacturer keywords (e.g. 'GM', 'General Motors').
    
    Examples:
        'General Motors Bowling Green Assembly' -> {'bowling', 'green'}
        'GM Bowling Green Plant' -> {'bowling', 'green'}
        'Bowling Green Assembly Complex' -> {'bowling', 'green'}
    """
    tokens = normalize_tokens(name, expand_acronyms=True)
    core = [
        t for t in tokens
        if t not in FACILITY_STOPWORDS and t not in MANUFACTURER_KEYWORDS
    ]
    if core:
        return frozenset(core)

    # Fallback 1: Keep non-facility-stopword tokens (e.g. if parent name was only distinctive token)
    non_facility = [t for t in tokens if t not in FACILITY_STOPWORDS]
    if non_facility:
        return frozenset(non_facility)

    # Fallback 2: Raw tokens
    return frozenset(tokens)


def extract_company_core_tokens(name: str) -> frozenset[str]:
    """Extract distinctive core tokens of a company or organization name."""
    tokens = normalize_tokens(name, expand_acronyms=True)
    core = [t for t in tokens if t not in COMPANY_STOPWORDS]
    return frozenset(core) if core else frozenset(tokens)


def extract_person_core_tokens(name: str) -> frozenset[str]:
    """Extract distinctive core tokens of a person name, stripping titles and honorifics."""
    tokens = normalize_tokens(name, expand_acronyms=False)
    core = [t for t in tokens if t not in PERSON_TITLES]
    return frozenset(core) if core else frozenset(tokens)


def is_facility_type(etype: str) -> bool:
    t = etype.strip().lower()
    return (
        t in FACILITY_ENTITY_TYPES
        or any(kw in t for kw in ("plant", "facility", "manufacturing", "assembly", "factory", "complex", "site", "operations", "casting", "stamping", "works"))
    )


def is_organization_type(etype: str) -> bool:
    t = etype.strip().lower()
    return (
        t in ORGANIZATION_ENTITY_TYPES
        or any(kw in t for kw in ("company", "corp", "corporation", "enterprise", "manufacturer", "firm", "automaker", "oem", "supplier", "organization"))
    )


def is_person_type(etype: str) -> bool:
    t = etype.strip().lower()
    return (
        t in PERSON_ENTITY_TYPES
        or any(kw in t for kw in ("person", "executive", "lead", "director", "manager", "engineer", "contact"))
    )


def are_entity_types_compatible(type1: str, type2: str) -> bool:
    """Determine if two entity types are semantically compatible for resolution."""
    t1 = type1.strip().lower()
    t2 = type2.strip().lower()
    if t1 == t2 or t1 in ("entity", "") or t2 in ("entity", ""):
        return True
    if is_facility_type(t1) and is_facility_type(t2):
        return True
    if is_organization_type(t1) and is_organization_type(t2):
        return True
    if is_person_type(t1) and is_person_type(t2):
        return True
    return False


def are_entities_equivalent(
    name1: str,
    type1: str,
    name2: str,
    type2: str,
    aliases1: Sequence[str] | None = None,
    aliases2: Sequence[str] | None = None,
) -> bool:
    """Determine whether two entity references refer to the exact same real-world entity.
    
    Employs multi-tier resolution:
    1. Entity type semantic compatibility guardrail.
    2. Strict lowercase exact match.
    3. Specific alias cross-matching.
    4. Facility core token set matching (with acronym expansion and stopword stripping).
    5. Parent manufacturer prefix tolerance (e.g. 'GM Bowling Green Plant' == 'Bowling Green Assembly Complex').
    6. Company and Person core token matching.
    """
    if not are_entity_types_compatible(type1, type2):
        return False

    n1 = name1.strip().lower()
    n2 = name2.strip().lower()

    # 1. Exact string match
    if n1 == n2:
        return True

    clean_aliases1 = {a.strip().lower() for a in (aliases1 or []) if is_specific_alias(a)}
    clean_aliases2 = {a.strip().lower() for a in (aliases2 or []) if is_specific_alias(a)}

    # 2. Direct alias matching
    if is_specific_alias(n1) and n1 in clean_aliases2:
        return True
    if is_specific_alias(n2) and n2 in clean_aliases1:
        return True
    if clean_aliases1 and clean_aliases2 and not clean_aliases1.isdisjoint(clean_aliases2):
        return True

    # Check semantic categories
    t1 = type1.strip().lower()
    t2 = type2.strip().lower()
    is_facility = (
        t1 in FACILITY_ENTITY_TYPES
        or t2 in FACILITY_ENTITY_TYPES
        or any(kw in n1 for kw in ("plant", "assembly", "facility", "factory", "complex", "manufacturing"))
        or any(kw in n2 for kw in ("plant", "assembly", "facility", "factory", "complex", "manufacturing"))
    )

    if is_facility:
        core1 = extract_facility_core_tokens(name1)
        core2 = extract_facility_core_tokens(name2)

        # Core token set match (e.g. {'bowling', 'green'} == {'bowling', 'green'})
        if core1 and core2:
            if core1 == core2:
                return True
            # Multi-word core subset match (e.g. 'Lansing Grand River Assembly' == 'Lansing Grand River Assembly/Stamping')
            intersection = core1 & core2
            if len(intersection) >= 2 and (core1.issubset(core2) or core2.issubset(core1)):
                return True

        # Check aliases core tokens
        for a1 in clean_aliases1:
            if extract_facility_core_tokens(a1) == core2:
                return True
        for a2 in clean_aliases2:
            if extract_facility_core_tokens(a2) == core1:
                return True

        # Manufacturer prefix tolerance:
        # e.g., 'GM Bowling Green Plant' vs 'Bowling Green Assembly Complex'
        tokens1 = frozenset([t for t in normalize_tokens(name1, expand_acronyms=True) if t not in FACILITY_STOPWORDS])
        tokens2 = frozenset([t for t in normalize_tokens(name2, expand_acronyms=True) if t not in FACILITY_STOPWORDS])
        if tokens1 and tokens2:
            if tokens1 == tokens2:
                return True
            diff = tokens1 ^ tokens2
            intersection = tokens1 & tokens2
            # If the difference consists only of known manufacturer keywords and they share core tokens
            if intersection and diff.issubset(MANUFACTURER_KEYWORDS):
                return True

    # Person category matching
    is_person = t1 in PERSON_ENTITY_TYPES or t2 in PERSON_ENTITY_TYPES
    if is_person:
        p_core1 = extract_person_core_tokens(name1)
        p_core2 = extract_person_core_tokens(name2)
        if p_core1 and p_core2:
            if p_core1 == p_core2:
                return True
            # Subset matching for names with middle names/initials (e.g. 'Joe Hinrichs' vs 'Joseph Hinrichs')
            if len(p_core1) > 1 and len(p_core2) > 1:
                if p_core1.issubset(p_core2) or p_core2.issubset(p_core1):
                    return True

    # Company / Organization matching
    is_org = t1 in ORGANIZATION_ENTITY_TYPES or t2 in ORGANIZATION_ENTITY_TYPES
    if is_org:
        c_core1 = extract_company_core_tokens(name1)
        c_core2 = extract_company_core_tokens(name2)
        if c_core1 and c_core2 and c_core1 == c_core2:
            return True

    return False
