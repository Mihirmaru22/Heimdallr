"""Heimdallr V3.2.1: CROSS_SPECIALIST_V1 Tasks.

16 hard cross-specialist investigation tasks (including 5 decoy tasks where superficially relevant specialists must NOT be invoked).
"""

from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field


class CrossSpecialistTask(BaseModel):
    task_id: str
    title: str
    query: str
    chain_type: str  # e.g., "CORPORATE_TO_SANCTIONS", "DECOY_NEGATIVE"
    required_specialists: List[str]
    forbidden_specialists: List[str] = Field(default_factory=list)
    expected_handoff_sequence: List[str]
    is_decoy: bool = False
    expected_epistemic_status: str = "SUPPORTED"


def build_cross_specialist_tasks() -> List[CrossSpecialistTask]:
    """Build 16 cross-specialist investigation tasks (11 positive chains, 5 decoys)."""
    tasks: List[CrossSpecialistTask] = []

    # 1. Corporate -> Sanctions
    tasks.append(CrossSpecialistTask(
        task_id="cross_01",
        title="UK corporate director discovery chained to international sanctions screening",
        query="Identify managing director of Apex Technologies Europe Ltd and screen for active sanctions.",
        chain_type="CORPORATE_TO_SANCTIONS",
        required_specialists=["corporate", "sanctions"],
        expected_handoff_sequence=["corporate", "sanctions"],
    ))

    # 2. Sanctions -> Corporate
    tasks.append(CrossSpecialistTask(
        task_id="cross_02",
        title="Sanctions designation chained to official Dubai corporate registry extract",
        query="Verify UK OFSI designation for Orion Strategic Technologies and retrieve registered DMCC entity number.",
        chain_type="SANCTIONS_TO_CORPORATE",
        required_specialists=["sanctions", "corporate"],
        expected_handoff_sequence=["sanctions", "corporate"],
    ))

    # 3. Corporate -> Identity -> Sanctions
    tasks.append(CrossSpecialistTask(
        task_id="cross_03",
        title="Board member discovery to academic identity correlation to PEP screening",
        query="Identify Chief Scientist of German quantum subsidiary, verify academic identity, and check PEP exposure.",
        chain_type="CORPORATE_TO_IDENTITY_TO_SANCTIONS",
        required_specialists=["corporate", "identity", "sanctions"],
        expected_handoff_sequence=["corporate", "identity", "sanctions"],
    ))

    # 4. Sanctions -> Identity
    tasks.append(CrossSpecialistTask(
        task_id="cross_04",
        title="Offshore trust controller chained to open-source developer profile",
        query="Identify controller of Steppe Resources BVI and uncover technical aliases on GitHub.",
        chain_type="SANCTIONS_TO_IDENTITY",
        required_specialists=["sanctions", "identity"],
        expected_handoff_sequence=["sanctions", "identity"],
    ))

    # 5. Corporate -> Infrastructure -> Sanctions
    tasks.append(CrossSpecialistTask(
        task_id="cross_05",
        title="UK telemetry subsidiary to CT log hostname to designated perimeter screening",
        query="Trace UK subsidiary to telemetry hostname and verify whether host is blocked under US SDN.",
        chain_type="CORPORATE_TO_INFRASTRUCTURE_TO_SANCTIONS",
        required_specialists=["corporate", "infrastructure", "sanctions"],
        expected_handoff_sequence=["corporate", "infrastructure", "sanctions"],
    ))

    # 6. Sanctions -> Corporate -> Identity
    tasks.append(CrossSpecialistTask(
        task_id="cross_06",
        title="Sanctions hit to Cyprus corporate registry to beneficial owner biographical probe",
        query="Starting from SDN blocked Cyprus entity, retrieve statutory shareholders and verify former military career of controller.",
        chain_type="SANCTIONS_TO_CORPORATE_TO_IDENTITY",
        required_specialists=["sanctions", "corporate", "identity"],
        expected_handoff_sequence=["sanctions", "corporate", "identity"],
    ))

    # 7. Corporate -> Sanctions -> Identity
    tasks.append(CrossSpecialistTask(
        task_id="cross_07",
        title="SEC Form 10-K subsidiary officer to PEP disclosure to alias mapping",
        query="Extract statutory officer of Apex Europe, confirm PEP standing, and resolve Cyrillic name variant.",
        chain_type="CORPORATE_TO_SANCTIONS_TO_IDENTITY",
        required_specialists=["corporate", "sanctions", "identity"],
        expected_handoff_sequence=["corporate", "sanctions", "identity"],
    ))

    # 8. Sanctions -> Infrastructure
    tasks.append(CrossSpecialistTask(
        task_id="cross_08",
        title="SDN blocked company to DNS perimeter mapping",
        query="Verify OFAC listing for Apex Cyber Operations and map active DNS name servers.",
        chain_type="SANCTIONS_TO_INFRASTRUCTURE",
        required_specialists=["sanctions", "infrastructure"],
        expected_handoff_sequence=["sanctions", "infrastructure"],
    ))

    # 9. Corporate -> Sanctions
    tasks.append(CrossSpecialistTask(
        task_id="cross_09",
        title="Austrian subsidiary to EU restrictive measures list screening",
        query="Identify Austrian trading branch of conglomerate and screen under EU Council Regulations.",
        chain_type="CORPORATE_TO_SANCTIONS",
        required_specialists=["corporate", "sanctions"],
        expected_handoff_sequence=["corporate", "sanctions"],
    ))

    # 10. Sanctions -> Corporate
    tasks.append(CrossSpecialistTask(
        task_id="cross_10",
        title="Designated maritime operator to Singapore corporate shareholding",
        query="Confirm designation of Vostok Shipping and retrieve official ACRA Singapore corporate filings.",
        chain_type="SANCTIONS_TO_CORPORATE",
        required_specialists=["sanctions", "corporate"],
        expected_handoff_sequence=["sanctions", "corporate"],
    ))

    # 11. Corporate -> Identity -> Sanctions
    tasks.append(CrossSpecialistTask(
        task_id="cross_11",
        title="Handelsregister excerpt to doctoral thesis verification to SECO screening",
        query="Retrieve German managing director, verify university accreditation, and screen SECO database.",
        chain_type="CORPORATE_TO_IDENTITY_TO_SANCTIONS",
        required_specialists=["corporate", "identity", "sanctions"],
        expected_handoff_sequence=["corporate", "identity", "sanctions"],
    ))

    # =========================================================================
    # DECOY TASKS (5 Tasks: Superficially relevant specialist must NOT be invoked)
    # =========================================================================
    tasks.append(CrossSpecialistTask(
        task_id="cross_decoy_01",
        title="Clean corporate expansion query (Superficial Sanctions decoy)",
        query="Review international maritime trade routes of civilian Danish cargo fleet. Do not screen sanctions.",
        chain_type="DECOY_NEGATIVE",
        required_specialists=["corporate"],
        forbidden_specialists=["sanctions"],
        expected_handoff_sequence=["corporate"],
        is_decoy=True,
    ))

    tasks.append(CrossSpecialistTask(
        task_id="cross_decoy_02",
        title="Generic infrastructure SSL certificate audit (Superficial Identity decoy)",
        query="Inspect Certificate Transparency logs for public documentation portal docs.example.com.",
        chain_type="DECOY_NEGATIVE",
        required_specialists=["infrastructure"],
        forbidden_specialists=["identity"],
        expected_handoff_sequence=["infrastructure"],
        is_decoy=True,
    ))

    tasks.append(CrossSpecialistTask(
        task_id="cross_decoy_03",
        title="University academic faculty directory lookup (Superficial Corporate decoy)",
        query="Find professor curriculum vitae and computer science journal papers for Dr. Aris Thorne.",
        chain_type="DECOY_NEGATIVE",
        required_specialists=["identity"],
        forbidden_specialists=["corporate"],
        expected_handoff_sequence=["identity"],
        is_decoy=True,
    ))

    tasks.append(CrossSpecialistTask(
        task_id="cross_decoy_04",
        title="Pure sanctions registry check without corporate documents (Superficial Corporate decoy)",
        query="Check whether Russian individual Boris Romanov appears on active OFAC SDN list.",
        chain_type="DECOY_NEGATIVE",
        required_specialists=["sanctions"],
        forbidden_specialists=["corporate"],
        expected_handoff_sequence=["sanctions"],
        is_decoy=True,
    ))

    tasks.append(CrossSpecialistTask(
        task_id="cross_decoy_05",
        title="Commercial DNS nameserver lookup (Superficial Sanctions decoy)",
        query="Enumerate authoritative NS records for global commercial retailer summit-retail.com.",
        chain_type="DECOY_NEGATIVE",
        required_specialists=["infrastructure"],
        forbidden_specialists=["sanctions"],
        expected_handoff_sequence=["infrastructure"],
        is_decoy=True,
    ))

    return tasks
