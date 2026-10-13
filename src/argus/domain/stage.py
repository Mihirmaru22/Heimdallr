"""Research execution lifecycle stages for Argus."""

from enum import Enum


class ResearchStage(str, Enum):
    """The 5 progressive lifecycle stages of an Argus autonomous investigation."""

    RECONNAISSANCE = "reconnaissance"
    OPERATIONAL_MAPPING = "operational_mapping"
    PERSONNEL_LEADERSHIP = "personnel_leadership"
    CONTACT_RESOLUTION = "contact_resolution"
    SYNTHESIS = "synthesis"
