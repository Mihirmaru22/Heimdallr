"""Heimdallr V5: CROSS_SPECIALIST_ONION_V1 Benchmark Tasks.

20 multi-specialist investigation tasks testing:
1. Corporate -> Onion (2 tasks)
2. Onion -> Corporate (2 tasks)
3. Identity -> Onion (2 tasks)
4. Onion -> Identity (2 tasks)
5. Infrastructure -> Onion (2 tasks)
6. Onion -> Infrastructure (2 tasks)
7. Sanctions -> Onion (2 tasks)
8. Onion -> Sanctions (2 tasks)
9. Corporate -> Identity -> Onion (1 task)
10. Onion -> Corporate -> Sanctions (1 task)
11. Onion -> Identity -> Infrastructure (1 task)
12. Corporate -> Infrastructure -> Onion -> Identity (1 task)
13. Decoys where Onion MUST NOT be invoked (2 tasks)

Total = 20 tasks.
"""

from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field


class OnionCrossSpecialistTask(BaseModel):
    task_id: str
    title: str
    query: str
    chain_type: str
    required_specialists: List[str]
    forbidden_specialists: List[str] = Field(default_factory=list)
    expected_handoff_sequence: List[str]
    is_decoy: bool = False
    expected_epistemic_status: str = "SUPPORTED"


def build_cross_specialist_onion_tasks() -> List[OnionCrossSpecialistTask]:
    """Construct 20 multi-specialist tasks testing onion interoperability and decoy gating."""
    tasks: List[OnionCrossSpecialistTask] = []

    # 1. Corporate -> Onion (Task 1)
    tasks.append(OnionCrossSpecialistTask(
        task_id="cross_onion_01",
        title="Corporate Registry -> Onion Breach Portal (Apex Tech)",
        query="Retrieve registered Delaware officers for Apex Technologies Group Inc and correlate with extortion leak files on ALPHV.",
        chain_type="CORPORATE_TO_ONION",
        required_specialists=["corporate", "onion"],
        expected_handoff_sequence=["corporate", "onion"],
    ))

    # 1. Corporate -> Onion (Task 2)
    tasks.append(OnionCrossSpecialistTask(
        task_id="cross_onion_02",
        title="UK Companies House -> Tor Extortion Directory (Meridian Aerospace)",
        query="Lookup UK Companies House director filings for Meridian Aerospace Corp and verify whether their private telemetry is published on LockBit.",
        chain_type="CORPORATE_TO_ONION",
        required_specialists=["corporate", "onion"],
        expected_handoff_sequence=["corporate", "onion"],
    ))

    # 2. Onion -> Corporate (Task 3)
    tasks.append(OnionCrossSpecialistTask(
        task_id="cross_onion_03",
        title="Onion Shadow Portal -> Dubai Corporate Registry (Altai Energy)",
        query="Extract commercial bill of lading documents from altaishadowportal.onion and cross-reference with Dubai DED registry for Altai Energy Resources.",
        chain_type="ONION_TO_CORPORATE",
        required_specialists=["onion", "corporate"],
        expected_handoff_sequence=["onion", "corporate"],
    ))

    # 2. Onion -> Corporate (Task 4)
    tasks.append(OnionCrossSpecialistTask(
        task_id="cross_onion_04",
        title="Darknet Leak Cache -> French Commercial Court Registry (Orion Defense)",
        query="Extract proprietary engineering headers from orionleakarchive.onion and confirm parent entity status in Paris Tribunal de Commerce.",
        chain_type="ONION_TO_CORPORATE",
        required_specialists=["onion", "corporate"],
        expected_handoff_sequence=["onion", "corporate"],
    ))

    # 3. Identity -> Onion (Task 5)
    tasks.append(OnionCrossSpecialistTask(
        task_id="cross_onion_05",
        title="Developer GitHub Persona -> Darknet Forum Threat Intel (HugBunter)",
        query="Verify clearnet open-source key commits for 'hugbunter_dev' and trace to administrator profile on Dread onion forum.",
        chain_type="IDENTITY_TO_ONION",
        required_specialists=["identity", "onion"],
        expected_handoff_sequence=["identity", "onion"],
    ))

    # 3. Identity -> Onion (Task 6)
    tasks.append(OnionCrossSpecialistTask(
        task_id="cross_onion_06",
        title="Researcher PGP Identity -> Darknet Escrow Operator",
        query="Correlate public PGP key fingerprint of software author with multi-sig escrow deposit handlers on darknet escrow services.",
        chain_type="IDENTITY_TO_ONION",
        required_specialists=["identity", "onion"],
        expected_handoff_sequence=["identity", "onion"],
    ))

    # 4. Onion -> Identity (Task 7)
    tasks.append(OnionCrossSpecialistTask(
        task_id="cross_onion_07",
        title="Onion Extortion Contact -> Clearnet Developer Footprint",
        query="Extract Tox messenger handle from ALPHV negotiation site and correlate with published developer contact profiles on GitHub.",
        chain_type="ONION_TO_IDENTITY",
        required_specialists=["onion", "identity"],
        expected_handoff_sequence=["onion", "identity"],
    ))

    # 4. Onion -> Identity (Task 8)
    tasks.append(OnionCrossSpecialistTask(
        task_id="cross_onion_08",
        title="Darknet Vendor Profile -> Academic Publications Identity",
        query="Extract PGP signature block from dark-web zero-day broker and search academic pre-print archives for matching cryptographic identity.",
        chain_type="ONION_TO_IDENTITY",
        required_specialists=["onion", "identity"],
        expected_handoff_sequence=["onion", "identity"],
    ))

    # 5. Infrastructure -> Onion (Task 9)
    tasks.append(OnionCrossSpecialistTask(
        task_id="cross_onion_09",
        title="Clearnet Domain CT Logs -> Dark-Web Mirror Correlation",
        query="Inspect Certificate Transparency logs for blackcat-leaks.info and resolve to active backend Tor hidden service.",
        chain_type="INFRASTRUCTURE_TO_ONION",
        required_specialists=["infrastructure", "onion"],
        expected_handoff_sequence=["infrastructure", "onion"],
    ))

    # 5. Infrastructure -> Onion (Task 10)
    tasks.append(OnionCrossSpecialistTask(
        task_id="cross_onion_10",
        title="BGP Autonomous System Routing -> Covert Onion C2 Relay",
        query="Trace AS12389 network routing announcements to identify entry guard circuits connecting to Sandworm C2 hidden services.",
        chain_type="INFRASTRUCTURE_TO_ONION",
        required_specialists=["infrastructure", "onion"],
        expected_handoff_sequence=["infrastructure", "onion"],
    ))

    # 6. Onion -> Infrastructure (Task 11)
    tasks.append(OnionCrossSpecialistTask(
        task_id="cross_onion_11",
        title="Onion C2 Hidden Service -> Public DNS / IP Egress",
        query="Extract outgoing clearnet callback endpoints from Sandworm hidden service descriptor and query DNS authoritative nameservers.",
        chain_type="ONION_TO_INFRASTRUCTURE",
        required_specialists=["onion", "infrastructure"],
        expected_handoff_sequence=["onion", "infrastructure"],
    ))

    # 6. Onion -> Infrastructure (Task 12)
    tasks.append(OnionCrossSpecialistTask(
        task_id="cross_onion_12",
        title="Darknet Extortion Portal -> Clearnet CDN Mirror Infrastructure",
        query="Enumerate clearnet fallback domains published on LockBit onion homepage and inspect Anycast CDN routing topology.",
        chain_type="ONION_TO_INFRASTRUCTURE",
        required_specialists=["onion", "infrastructure"],
        expected_handoff_sequence=["onion", "infrastructure"],
    ))

    # 7. Sanctions -> Onion (Task 13)
    tasks.append(OnionCrossSpecialistTask(
        task_id="cross_onion_13",
        title="OFAC SDN Sanctions Entry -> Dark-Web Cryptocurrency Extortion Portal",
        query="Identify OFAC SDN designated digital currency addresses for LockBitSupp and check for active publication on LockBit Tor mirrors.",
        chain_type="SANCTIONS_TO_ONION",
        required_specialists=["sanctions", "onion"],
        expected_handoff_sequence=["sanctions", "onion"],
    ))

    # 7. Sanctions -> Onion (Task 14)
    tasks.append(OnionCrossSpecialistTask(
        task_id="cross_onion_14",
        title="EU Sanctions Restrictive Measures -> Onion Shadow Holding Portal",
        query="Screen Volga Spirit tanker fleet on EU maritime sanctions and discover associated shadow oil bills of lading on Altai darknet portal.",
        chain_type="SANCTIONS_TO_ONION",
        required_specialists=["sanctions", "onion"],
        expected_handoff_sequence=["sanctions", "onion"],
    ))

    # 8. Onion -> Sanctions (Task 15)
    tasks.append(OnionCrossSpecialistTask(
        task_id="cross_onion_15",
        title="Onion Extortion Crypto Wallet -> OFAC Specially Designated Nationals List",
        query="Extract Monero and Bitcoin payment addresses from LockBit hidden service and cross-match with OFAC cyber sanctions SDN schedule.",
        chain_type="ONION_TO_SANCTIONS",
        required_specialists=["onion", "sanctions"],
        expected_handoff_sequence=["onion", "sanctions"],
    ))

    # 8. Onion -> Sanctions (Task 16)
    tasks.append(OnionCrossSpecialistTask(
        task_id="cross_onion_16",
        title="Darknet Escrow Treasury Address -> UN Security Council Asset Freeze",
        query="Extract Ethereum contract treasury address from Lazarus Andiel Escrow onion service and screen against UN sanctions consolidated database.",
        chain_type="ONION_TO_SANCTIONS",
        required_specialists=["onion", "sanctions"],
        expected_handoff_sequence=["onion", "sanctions"],
    ))

    # 9. Corporate -> Identity -> Onion (Task 17)
    tasks.append(OnionCrossSpecialistTask(
        task_id="cross_onion_17",
        title="Corporate Officer -> Developer Handle -> Darknet Forum Persona",
        query="Lookup statutory director of UK cybersecurity firm, identify GitHub handle via Identity specialist, and locate discussions on Dread darknet forum.",
        chain_type="CORPORATE_TO_IDENTITY_TO_ONION",
        required_specialists=["corporate", "identity", "onion"],
        expected_handoff_sequence=["corporate", "identity", "onion"],
    ))

    # 10. Onion -> Corporate -> Sanctions (Task 18)
    tasks.append(OnionCrossSpecialistTask(
        task_id="cross_onion_18",
        title="Onion Shadow Portal -> Dubai Corporate Registry -> OFAC Secondary Sanctions",
        query="Trace crude oil transshipment contract on altaishadowportal.onion, resolve Dubai entity registry, and evaluate US secondary sanctions exposure.",
        chain_type="ONION_TO_CORPORATE_TO_SANCTIONS",
        required_specialists=["onion", "corporate", "sanctions"],
        expected_handoff_sequence=["onion", "corporate", "sanctions"],
    ))

    # 11. Onion -> Identity -> Infrastructure (Task 19)
    tasks.append(OnionCrossSpecialistTask(
        task_id="cross_onion_19",
        title="Onion Threat Actor -> Online Persona Footprint -> Upstream Autonomous System",
        query="Extract negotiator handle from darknet leak site, resolve identity email on GitHub, and map associated authoritative DNS nameserver infrastructure.",
        chain_type="ONION_TO_IDENTITY_TO_INFRASTRUCTURE",
        required_specialists=["onion", "identity", "infrastructure"],
        expected_handoff_sequence=["onion", "identity", "infrastructure"],
    ))

    # 12. Corporate -> Infrastructure -> Onion -> Identity (Task 20 - 4-Hop Master)
    tasks.append(OnionCrossSpecialistTask(
        task_id="cross_onion_20",
        title="Corporate -> Infrastructure -> Onion -> Identity (4-Hop Master Investigation)",
        query="Investigate Apex Tech Delaware registration, trace mailhost infrastructure, discover extortion exposure on ALPHV, and resolve ransomware operator handle.",
        chain_type="CORPORATE_TO_INFRASTRUCTURE_TO_ONION_TO_IDENTITY",
        required_specialists=["corporate", "infrastructure", "onion", "identity"],
        expected_handoff_sequence=["corporate", "infrastructure", "onion", "identity"],
    ))

    # Decoy 1: Pure Corporate Sanctions Inquiry (Onion FORBIDDEN)
    tasks.append(OnionCrossSpecialistTask(
        task_id="cross_onion_decoy_01",
        title="Decoy Task: Clearnet corporate beneficial ownership and OFAC SDN screening",
        query="Determine beneficial owners of Cyprus maritime holding firm and check against OFAC SDN list.",
        chain_type="DECOY_NON_ONION",
        required_specialists=["corporate", "sanctions"],
        forbidden_specialists=["onion"],
        expected_handoff_sequence=["corporate", "sanctions"],
        is_decoy=True,
    ))

    # Decoy 2: Clearnet Infrastructure DNS & Identity Inquiry (Onion FORBIDDEN)
    tasks.append(OnionCrossSpecialistTask(
        task_id="cross_onion_decoy_02",
        title="Decoy Task: Clearnet DNS MX verification and system administrator persona lookup",
        query="Inspect DNS mail exchange MX records for university domain and resolve postmaster email to campus directory.",
        chain_type="DECOY_NON_ONION",
        required_specialists=["infrastructure", "identity"],
        forbidden_specialists=["onion"],
        expected_handoff_sequence=["infrastructure", "identity"],
        is_decoy=True,
    ))

    return tasks
