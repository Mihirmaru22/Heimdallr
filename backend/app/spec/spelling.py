"""British and American spellings of words people use for industries, so "defence" in a question also
finds US companies that write "defense" (SEC, US homepages), and the other way round."""

from __future__ import annotations

import re

BRITISH_TO_US = {
    "defence": "defense", "aluminium": "aluminum", "tyre": "tire", "tyres": "tires", "jewellery": "jewelry",
    "fibre": "fiber", "fibres": "fibers", "centre": "center", "centres": "centers", "catalogue": "catalog",
    "paediatric": "pediatric", "paediatrics": "pediatrics", "haematology": "hematology",
    "anaesthesia": "anesthesia", "orthopaedic": "orthopedic", "orthopaedics": "orthopedics",
    "colour": "color", "organisation": "organization", "programme": "program", "licence": "license",
}
US_TO_BRITISH = {us: gb for gb, us in BRITISH_TO_US.items()}


def to_us(text: str) -> str:
    """"Defence contractors" -> "defense contractors"; other words are left as they are."""
    return re.sub(r"[A-Za-z]+", lambda m: BRITISH_TO_US.get(m.group(0).lower(), m.group(0)), text)


def spellings(text: str) -> list[str]:
    """The text in both spellings, the original first ("defence" -> ["defence", "defense"])."""
    swap = {**BRITISH_TO_US, **US_TO_BRITISH}
    other = re.sub(r"[A-Za-z]+", lambda m: swap.get(m.group(0).lower(), m.group(0)), text)
    return list(dict.fromkeys([text, other]))
