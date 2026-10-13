"""Fresh Holdout Evaluation Benchmark for Heimdallr V3 (P0.3-GR).

Provides a completely separate, freshly generated holdout benchmark of 30 diverse
research tasks across 8 categories with an independent synthetic corpus.
No production logic has been tuned on this holdout.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
import re
import time
from typing import Any

from pydantic import BaseModel

from argus.investigation.benchmark.tasks import (
    InvestigationCategory,
    InvestigationDifficulty,
    InvestigationTask,
)
from argus.investigation.benchmark.v2.corpus import InvestigationDocument
from argus.investigation.benchmark.v2.evaluator import GeneralizationV2Evaluator, compute_wilson_ci
from argus.investigation.orchestrator import InvestigationEngine

logger = logging.getLogger(__name__)


# =============================================================================
# 1. Fresh Holdout Corpus (Independent Unseen Entities)
# =============================================================================

def build_fresh_holdout_corpus() -> dict[str, InvestigationDocument]:
    """Build unified synthetic corpus for the 30 fresh holdout tasks."""
    docs: dict[str, InvestigationDocument] = {}

    def add(doc_id: str, title: str, url: str, text: str, source_type: str, date: str | None = None) -> None:
        docs[doc_id] = InvestigationDocument(
            doc_id=doc_id,
            title=title,
            url=url,
            text_content=text.strip(),
            source_type=source_type,
            published_date=date,
        )

    # Category A: Organizational & Corporate
    add("fh_doc_01_a", "Helix BioFoundry Corporate Registry Filing", "https://companieshouse.gov.uk/filings/helix-biofoundry",
        "Official Registry Filing: Helix BioFoundry Ltd was founded in Oxford by Dr. Evelyn Vance. The company operates the SynthoPore automated genetic assembly facility in Cambridge.", "commercial_register", "2023-04-12")
    add("fh_doc_02_a", "Zephyrus Supercomputing High Performance Review", "https://top500.org/systems/zephyrus-ciel-5",
        "Top500 Certified Benchmarking: Zephyrus Supercomputing deployed the Ciel-5 exascale cluster at the Grenoble Supercomputing Centre, featuring 18,432 custom photonic interconnect nodes.", "scientific_paper", "2023-11-10")
    add("fh_doc_03_a", "Thalassa Oceanics Deep Sea Autonomous Vehicle Certification", "https://dnv.com/certificates/thalassa-abyss-9",
        "DNV Type-Approval Certificate: Thalassa Oceanics manufactures the Abyss-9 autonomous underwater vehicle rated to an operational depth of 6000 meters, overseen by Chief Naval Architect Marcus Lindqvist in Gothenburg.", "official_certificate", "2023-08-15")
    add("fh_doc_04_a", "Valles Geothermal Energy Federal Commissioning Report", "https://energy.gov/geothermal/valles-caldera-phase1",
        "Department of Energy Commissioning Dossier: Valles Caldera Geothermal operates a 250 MWe supercritical binary cycle power facility in Sandoval County, New Mexico.", "government_audit", "2023-10-02")

    # Category B: Infrastructure Investigation
    add("fh_doc_05_a", "RIPE NCC Autonomous System Record: AetherNet ASN", "https://ripe.net/db/as-aethernet-49921",
        "Official RIPE NCC Registry: AetherNet Telecom operates AS49921 with primary transit exchange peering at DE-CIX Frankfurt and LINX London.", "commercial_register", "2023-06-20")
    add("fh_doc_06_a", "Nordic Subsea Fiber Route Survey", "https://telecomrambles.com/nordic-link-subsea-cable",
        "Telecommunications infrastructure audit: The Skagerrak-4 optical subsea cable landing station is operated by Kattegat Data Systems in Hirtshals, Denmark.", "trade_magazine", "2023-05-19")
    add("fh_doc_07_a", "Solaris Power Grid SCADA Gateway Architecture", "https://entsoe.eu/scada/solaris-grid-routing",
        "ENTSO-E Grid Security Disclosure: Solaris Grid Systems routes regional high-voltage telemetry through an authenticated IEC 61850 substation gateway located in Graz, Austria.", "utility_dossier", "2023-09-08")
    add("fh_doc_08_a", "Titan Cloud Edge Compute CDN Deployment", "https://bgp.he.net/AS62190",
        "BGP Routing Telemetry: Titan Cloud Edge operates AS62190, maintaining anycast edge clusters across Dublin, Tokyo, and São Paulo.", "commercial_register", "2023-07-14")

    # Category C: Corporate Relationships
    add("fh_doc_09_a", "Apex Aerospace Form 8-K Acquisition Filing", "https://sec.gov/edgar/apex-aerospace-orbitron",
        "SEC Form 8-K Disclosure: Apex Aerospace has completed the 100% acquisition of Orbitron Propulsion for $420M, integrating founder Elena Rostova as Vice President of Propulsion Systems.", "regulatory_filing", "2023-08-22")
    add("fh_doc_10_a", "Biolink Therapeutics Series C Investor Register", "https://crunchbase.com/funding/biolink-series-c",
        "Commercial venture report: Biolink Therapeutics secured a $85M Series C round led by Panakeia Capital, with general partner Dr. Arthur Pendelton appointed to the board of directors.", "trade_magazine", "2023-09-14")
    add("fh_doc_11_a", "Vanguard Battery OEM Supply Contract", "https://battery-news.eu/contracts/vanguard-cell-supply",
        "Automotive supply agreement: Vanguard Micro-Battery signed an exclusive supply agreement with Hyperion Motors to provide 4680 cylindrical cells for the Hyperion GT.", "press_release", "2023-11-04")
    add("fh_doc_12_a", "Nordic Clean Energy Consortium Governance Structure", "https://nordic-energy.se/consortium-members",
        "Official Inter-Governmental Filing: The Nordic Hydrogen Transport Alliance is co-owned in equal 50/50 joint venture by Equinor Clean Energy and Vattenfall Hydrogen.", "government_permit", "2023-06-11")

    # Category D: Contradictory & Ambiguous Evidence (Expected: CONTRADICTED)
    # Task 13: Competing rocket engine thrust numbers (120 kN vs 85 kN)
    add("fh_doc_13_a", "AeroTech Monthly: Phoenix-1 Static Fire Success", "https://aerotech.com/news/phoenix-1-static-fire-120kn",
        "AeroTech Monthly reports vendor press statements asserting the Phoenix-1 aerospike engine achieved 120 kN of sea-level thrust during test stand trials.", "press_release", "2023-04-10")
    add("fh_doc_13_b", "ESA Propulsion Testing Facility Audit: Phoenix-1", "https://esa.int/propulsion/audits/phoenix-1-thrust",
        "Independent ESA Propulsion Test Certificate: Validated test stand load-cell measurements establish Phoenix-1 verified sea-level thrust is strictly 85 kN.", "laboratory_certification", "2023-07-22")

    # Task 14: Historical dating conflict (1420 CE vs 1280 CE)
    add("fh_doc_14_a", "Archaeological Survey of Anatolian Fortress: Radiocarbon Series", "https://antiquity-journal.org/anatolia-fortress-c14",
        "Radiocarbon analysis of foundation beams from the Kastamonu Redoubt yields calibrated dates clustering strictly around 1420 CE.", "peer_reviewed_journal", "2023-05-12")
    add("fh_doc_14_b", "Epigraphic and Coin Hoard Chronology: Kastamonu Redoubt", "https://numismatics.org/anatolian-coins-1280",
        "Numismatic hoard analysis from the lowest citadel floor stratigraphy identifies Seljuk dirhams establishing construction date no later than 1280 CE.", "peer_reviewed_journal", "2023-09-15")

    # Task 15: Conflicting clinical efficacy (74% vs 38%)
    add("fh_doc_15_a", "PharmaTimes: Cardiax Phase II Shows 74% Biomarker Reduction", "https://pharmatimes.com/news/cardiax-phase2-74pct",
        "Phase II single-site open-label evaluation of Cardiax reported a 74% reduction in arterial plaque biomarkers across 60 patients.", "trade_magazine", "2023-03-15")
    add("fh_doc_15_b", "New England Journal of Medicine: Cardiax Multi-Center Phase III", "https://nejm.org/doi/10.1056/NEJMoa2304912",
        "Multi-center double-blind randomized Phase III trial across 1,200 patients demonstrated that Cardiax achieved only a 38% reduction in primary endpoints, disputing earlier Phase II figures.", "peer_reviewed_journal", "2023-11-02")

    # Task 16: Conflicting telecom latency audit (1.4 ms vs 9.8 ms)
    add("fh_doc_16_a", "5G Network Vendor Whitepaper: URLLC Latency Benchmark", "https://cellex-tech.com/whitepapers/5g-urllc-latency",
        "Cellex Networks whitepaper claims its proprietary 5G radio frame scheduler achieves 1.4 ms round-trip user-plane latency.", "trade_magazine", "2023-02-18")
    add("fh_doc_16_b", "FCC Office of Engineering and Technology Latency Audit", "https://fcc.gov/oet/reports/cellex-urllc-audit",
        "FCC Independent Metrology Report: Commercial field trials measuring Cellex URLLC hardware under realistic traffic loading demonstrated 9.8 ms mean latency.", "government_audit", "2023-08-30")

    # Task 17: Categorical mutual exclusivity: battery chemistry (Sodium-Ion vs LFP)
    add("fh_doc_17_a", "Clean Energy Blog: Voltaic Storage Deploys LFP Cells", "https://cleanenergyblog.org/voltaic-lfp-megapack",
        "Clean Energy Blog reports that Voltaic Power Systems selected Lithium Iron Phosphate (LFP) chemistry for its containerized grid batteries.", "blog_post", "2023-06-01")
    add("fh_doc_17_b", "California Energy Commission Grid Filing: Voltaic Storage", "https://energy.ca.gov/dockets/voltaic-battery-filing",
        "Official CEC Technical Filing: The Voltaic Power utility storage site utilizes non-flammable Sodium-Ion chemistry using Prussian white cathode materials.", "utility_dossier", "2023-07-15")

    # Category E: Negative Findings & Entity Scope (Expected: NOT_FOUND)
    # Task 18: Nonexistent department: Helix BioFoundry Cryogenic Rocket Division
    # Task 19: Nonexistent product: Zephyrus Quantum Cryptographic Satellite
    # Task 20: Nonexistent license: Thalassa Oceanics Deep Seabed Mining Concession
    # Task 21: Nonexistent subsidiary: Valles Geothermal Nuclear Microreactor Unit
    add("fh_doc_negative_registry", "International Business Registry: Nonexistent Units Verification", "https://globalregisters.org/searches/negative-verification-dossier",
        "Official Negative Verification Record: Comprehensive regulatory inquiry confirms: Helix BioFoundry Cryogenic Rocket Division does not exist. Zephyrus Quantum Cryptographic Satellite does not exist. Thalassa Oceanics Deep Seabed Mining Concession was never granted. Valles Geothermal Nuclear Microreactor Unit does not exist.",
        "registry_search_negative", "2024-01-01")

    # Category F: Insufficient Evidence & Principled Abstention (Expected: INSUFFICIENT_EVIDENCE)
    # Task 22: Room-temperature ambient superconductor preprint claim
    add("fh_doc_22_a", "ArXiv Preprint: Claimed Ambient Superconductivity in Cu-Doped Phosphide", "https://arxiv.org/abs/2405.00192",
        "An anonymous preprint reports zero electrical resistance at 295 K in copper-doped phosphide. Follow-up independent attempts by three university laboratories failed to replicate the transition, noting inconclusive magnetic susceptibility and severe sample heterogeneity.", "preprint_server", "2024-05-02")

    # Task 23: Proprietary secret training token mixture
    add("fh_doc_23_a", "TechCrunch: Frontier LLM Training Rumors", "https://techcrunch.com/2024/02/frontier-llm-dataset-rumors",
        "Unconfirmed forum chatter speculates on the pretraining token mixture of model Titan-X. The developer company officially stated that exact dataset mixture and filtering ratios are confidential proprietary trade secrets and will not be disclosed.", "news", "2024-02-10")

    # Task 24: Unverified single-patient in-vitro gene therapy
    add("fh_doc_24_a", "Biomedical Blog: In Vitro CRISPR Reversal of Huntington Repeats", "https://biomed-blog.org/crispr-huntington-invitro",
        "Preliminary single-patient in vitro case study demonstrates 50% repeat reduction in cultured fibroblast lines. The authors emphasize that clinical safety and in vivo efficacy remain unproven open questions pending multi-center animal trials.", "blog_post", "2023-11-20")

    # Task 25: Fragmentary weathered inscription
    add("fh_doc_25_a", "Journal of Semitic Epigraphy: Tell el-Farah Weathered Stele", "https://epigraphy-journal.org/tell-farah-stele",
        "Excavations revealed an eroded basalt stele from the 8th century BCE. Severe surface weathering prevents complete decipherment of the second king name; epigraphers confirm that conclusive historical attribution cannot be determined from available fragments.", "peer_reviewed_journal", "2023-04-14")

    # Category G: Technical Engineering (Expected: SUPPORTED)
    add("fh_doc_26_a", "IEEE Power Electronics Transactions: Silicon Carbide Inverter Efficiency", "https://ieee-power.org/papers/sic-inverter-efficiency-99-2",
        "IEEE Transactions on Power Electronics: Laboratory evaluation of the Achelous 1200V Silicon Carbide traction inverter demonstrates 99.2% peak electrical conversion efficiency under 800V bus testing.", "peer_reviewed_journal", "2023-09-01")
    add("fh_doc_27_a", "Nuclear Engineering International: Molten Salt Coolant Heat Transfer", "https://neimagazine.com/technical/flibe-salt-thermal-properties",
        "Technical Evaluation Report: FLiBe eutectic molten fluoride salt coolant exhibits a volumetric heat capacity of 4540 kJ/m3-K and operating thermal stability up to 1300 K.", "peer_reviewed_journal", "2023-07-12")
    add("fh_doc_28_a", "Materials Science and Engineering: Superalloy Creep Rupture Life", "https://matsci-journal.org/superalloy-cmsx4-creep",
        "High-temperature metallographic study: Single-crystal nickel-based superalloy CMSX-4 demonstrates 1200 hours creep rupture life under 1000°C and 140 MPa tensile stress.", "peer_reviewed_journal", "2023-05-25")

    # Category H: Historical Chronology (Expected: SUPPORTED)
    add("fh_doc_29_a", "Treaty of Utrecht Historical Archives: Gibraltar Article X", "https://nationalarchives.gov.uk/utrecht-1713-gibraltar",
        "British Foreign Office Historical Archive: Under Article X of the Treaty of Utrecht signed in July 1713, Spain ceded the town and castle of Gibraltar to Great Britain in perpetuity.", "commercial_register", "2023-01-10")
    add("fh_doc_30_a", "Federal Reserve System Centennial Dossier: Federal Reserve Act 1913", "https://federalreserve.gov/history/act-1913-woodrow-wilson",
        "Federal Reserve Historical Record: President Woodrow Wilson signed the Federal Reserve Act into law on December 23, 1913, establishing the central banking system of the United States.", "commercial_register", "2023-02-15")

    return docs


class FreshHoldoutCorpusRegistry:
    """Keyword search engine and registry for the 30 fresh holdout documents."""

    def __init__(self) -> None:
        self.docs = build_fresh_holdout_corpus()

    def search(self, query: str, limit: int = 5) -> list[InvestigationDocument]:
        """Perform deterministic BM25-like keyword matching across holdout documents."""
        q_tokens = [t.lower() for t in re.split(r"\W+", query) if len(t) > 3]
        if not q_tokens:
            return list(self.docs.values())[:limit]

        scored: list[tuple[float, InvestigationDocument]] = []
        for doc in self.docs.values():
            text_lower = f"{doc.title} {doc.text_content}".lower()
            score = 0.0
            for t in q_tokens:
                if t in text_lower:
                    score += 2.0 if t in doc.title.lower() else 1.0
            if score > 0:
                scored.append((score, doc))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = [doc for _, doc in scored[:limit]]
        if not results:
            results = list(self.docs.values())[:limit]
        return results

    def get_discoverable_entities(self) -> list[str]:
        return [
            "Helix BioFoundry", "Zephyrus Supercomputing", "Thalassa Oceanics", "Valles Caldera Geothermal",
            "AetherNet", "Kattegat Data Systems", "Solaris Grid Systems", "Titan Cloud Edge",
            "Apex Aerospace", "Orbitron Propulsion", "Biolink Therapeutics", "Vanguard Micro-Battery",
            "Nordic Hydrogen Transport Alliance", "Phoenix-1", "Kastamonu Redoubt", "Cardiax",
            "Cellex Networks", "Voltaic Power Systems", "Achelous Inverter", "FLiBe Molten Salt",
            "CMSX-4 Superalloy", "Treaty of Utrecht", "Federal Reserve Act 1913"
        ]


# =============================================================================
# 2. Fresh Holdout Task Manifest (30 Tasks)
# =============================================================================

def build_fresh_holdout_tasks() -> list[InvestigationTask]:
    """Build 30 novel holdout tasks spanning all 8 core research categories."""
    return [
        # Category A: Organizational Corporate (4 tasks)
        InvestigationTask(
            task_id="fh_task_01_helix_biofoundry",
            title="Helix BioFoundry: Founder and Core Facility",
            objective="Investigate Helix BioFoundry. Identify its founder, founding location, and primary genetic assembly facility.",
            category=InvestigationCategory.ORGANIZATIONAL_CORPORATE,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Helix BioFoundry"]},
            expected_entities=["Helix BioFoundry", "Dr. Evelyn Vance", "SynthoPore"],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        ),
        InvestigationTask(
            task_id="fh_task_02_zephyrus_supercomputing",
            title="Zephyrus Supercomputing: Exascale Deployment",
            objective="Investigate Zephyrus Supercomputing. Determine the cluster name and interconnect node count of their deployment at Grenoble.",
            category=InvestigationCategory.ORGANIZATIONAL_CORPORATE,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Zephyrus Supercomputing"]},
            expected_entities=["Zephyrus Supercomputing", "Ciel-5", "18,432 custom photonic interconnect nodes"],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        ),
        InvestigationTask(
            task_id="fh_task_03_thalassa_oceanics",
            title="Thalassa Oceanics: Subsea Autonomous Vehicle",
            objective="Analyze Thalassa Oceanics. Identify their flagship autonomous underwater vehicle, certified depth rating, and chief architect.",
            category=InvestigationCategory.ORGANIZATIONAL_CORPORATE,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Thalassa Oceanics"]},
            expected_entities=["Thalassa Oceanics", "Abyss-9", "6000 meters", "Marcus Lindqvist"],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        ),
        InvestigationTask(
            task_id="fh_task_04_valles_geothermal",
            title="Valles Geothermal: Supercritical Power Capacity",
            objective="Investigate Valles Caldera Geothermal. Determine the rated electrical generation capacity and plant location in Sandoval County.",
            category=InvestigationCategory.ORGANIZATIONAL_CORPORATE,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Valles Caldera Geothermal"]},
            expected_entities=["Valles Caldera Geothermal", "250 MWe", "Sandoval County"],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        ),

        # Category B: Infrastructure Investigation (4 tasks)
        InvestigationTask(
            task_id="fh_task_05_aethernet_asn",
            title="AetherNet Telecom: ASN Routing and IXP Peering",
            objective="Trace AetherNet Telecom infrastructure. Identify their Autonomous System Number (ASN) and primary European internet exchange peering points.",
            category=InvestigationCategory.INFRASTRUCTURE_INVESTIGATION,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["AetherNet"]},
            expected_entities=["AetherNet", "AS49921", "DE-CIX Frankfurt", "LINX London"],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        ),
        InvestigationTask(
            task_id="fh_task_06_skagerrak_fiber_landing",
            title="Kattegat Data Systems: Subsea Cable Landing",
            objective="Determine the landing station operator and Danish landfall site for the Skagerrak-4 optical subsea cable.",
            category=InvestigationCategory.INFRASTRUCTURE_INVESTIGATION,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Kattegat Data Systems"]},
            expected_entities=["Kattegat Data Systems", "Hirtshals", "Skagerrak-4"],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        ),
        InvestigationTask(
            task_id="fh_task_07_solaris_scada_gateway",
            title="Solaris Grid: SCADA Protocol and Substation Gateway",
            objective="Identify the industrial communication protocol standard and Austrian substation location used by Solaris Grid Systems for high-voltage telemetry.",
            category=InvestigationCategory.INFRASTRUCTURE_INVESTIGATION,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Solaris Grid Systems"]},
            expected_entities=["Solaris Grid Systems", "IEC 61850", "Graz"],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        ),
        InvestigationTask(
            task_id="fh_task_08_titan_edge_asn",
            title="Titan Cloud Edge: Global Anycast Deployment",
            objective="Verify the Autonomous System Number and international anycast edge deployment cities for Titan Cloud Edge.",
            category=InvestigationCategory.INFRASTRUCTURE_INVESTIGATION,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Titan Cloud Edge"]},
            expected_entities=["Titan Cloud Edge", "AS62190", "Dublin", "Tokyo"],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        ),

        # Category C: Corporate Relationships (4 tasks)
        InvestigationTask(
            task_id="fh_task_09_apex_orbitron_acquisition",
            title="Apex Aerospace: Orbitron Acquisition and Executive Role",
            objective="Investigate the acquisition of Orbitron Propulsion by Apex Aerospace. Determine the purchase valuation and executive role granted to Elena Rostova.",
            category=InvestigationCategory.CORPORATE_RELATIONSHIP,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Apex Aerospace"]},
            expected_entities=["Apex Aerospace", "Orbitron Propulsion", "$420M", "Elena Rostova"],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        ),
        InvestigationTask(
            task_id="fh_task_10_biolink_series_c_board",
            title="Biolink Therapeutics: Series C Lead and Board Seat",
            objective="Identify the venture lead for Biolink Therapeutics Series C round and which partner joined the board.",
            category=InvestigationCategory.CORPORATE_RELATIONSHIP,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Biolink Therapeutics"]},
            expected_entities=["Biolink Therapeutics", "Panakeia Capital", "Dr. Arthur Pendelton"],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        ),
        InvestigationTask(
            task_id="fh_task_11_vanguard_battery_oem_contract",
            title="Vanguard Battery: OEM Contract with Hyperion",
            objective="Trace the commercial battery cell supply agreement between Vanguard Micro-Battery and Hyperion Motors for the Hyperion GT.",
            category=InvestigationCategory.CORPORATE_RELATIONSHIP,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Vanguard Micro-Battery"]},
            expected_entities=["Vanguard Micro-Battery", "Hyperion Motors", "4680"],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        ),
        InvestigationTask(
            task_id="fh_task_12_nordic_hydrogen_jv",
            title="Nordic Clean Energy: Hydrogen Transport JV Ownership",
            objective="Determine the corporate ownership distribution of the Nordic Hydrogen Transport Alliance between Equinor Clean Energy and Vattenfall Hydrogen.",
            category=InvestigationCategory.CORPORATE_RELATIONSHIP,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Nordic Hydrogen Transport Alliance"]},
            expected_entities=["Nordic Hydrogen Transport Alliance", "Equinor Clean Energy", "Vattenfall Hydrogen"],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        ),

        # Category D: Contradictory Evidence (5 tasks)
        InvestigationTask(
            task_id="fh_task_13_contra_aerospike_thrust",
            title="Contradictory Thrust Metrics: Phoenix-1 Static Fire",
            objective="Evaluate conflicting claims on Phoenix-1 engine sea-level thrust: vendor press release (120 kN) vs independent ESA facility testing (85 kN).",
            category=InvestigationCategory.CONFLICTING_AMBIGUOUS,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Phoenix-1"]},
            expected_entities=["Phoenix-1"],
            has_contradiction=True,
            expected_epistemic_status="CONTRADICTED",
            min_steps_required=3,
        ),
        InvestigationTask(
            task_id="fh_task_14_contra_citadel_dating",
            title="Contradictory Chronologies: Kastamonu Redoubt Construction",
            objective="Resolve conflicting datings for the Kastamonu Redoubt fortress: radiocarbon dating (1420 CE) vs numismatic hoard stratigraphy (1280 CE).",
            category=InvestigationCategory.CONFLICTING_AMBIGUOUS,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Kastamonu Redoubt"]},
            expected_entities=["Kastamonu Redoubt"],
            has_contradiction=True,
            expected_epistemic_status="CONTRADICTED",
            min_steps_required=3,
        ),
        InvestigationTask(
            task_id="fh_task_15_contra_cardiax_efficacy",
            title="Contradictory Clinical Trial Data: Cardiax Plaque Reduction",
            objective="Examine competing clinical endpoints for drug Cardiax: open-label Phase II (74%) vs multi-center double-blind Phase III (38%).",
            category=InvestigationCategory.CONFLICTING_AMBIGUOUS,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Cardiax"]},
            expected_entities=["Cardiax"],
            has_contradiction=True,
            expected_epistemic_status="CONTRADICTED",
            min_steps_required=3,
        ),
        InvestigationTask(
            task_id="fh_task_16_contra_urllc_latency",
            title="Contradictory Benchmarks: 5G URLLC Radio Latency",
            objective="Reconcile vendor whitepaper latency claims of 1.4 ms vs FCC independent metrology measurements of 9.8 ms for Cellex Networks.",
            category=InvestigationCategory.CONFLICTING_AMBIGUOUS,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Cellex Networks"]},
            expected_entities=["Cellex Networks"],
            has_contradiction=True,
            expected_epistemic_status="CONTRADICTED",
            min_steps_required=3,
        ),
        InvestigationTask(
            task_id="fh_task_17_contra_battery_chem",
            title="Contradictory Disclosures: Voltaic Storage Cell Chemistry",
            objective="Analyze competing technical accounts on Voltaic Power Systems grid batteries: industry blog asserting Lithium Iron Phosphate (LFP) vs CEC filing asserting Sodium-Ion.",
            category=InvestigationCategory.CONFLICTING_AMBIGUOUS,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Voltaic Power Systems"]},
            expected_entities=["Voltaic Power Systems"],
            has_contradiction=True,
            expected_epistemic_status="CONTRADICTED",
            min_steps_required=3,
        ),

        # Category E: Negative Findings & Entity Scope (4 tasks)
        InvestigationTask(
            task_id="fh_task_18_neg_helix_rocket_div",
            title="Negative Verification: Helix BioFoundry Cryogenic Rocket Division",
            objective="Verify whether Helix BioFoundry operates an aerospace subsidiary designated as the Cryogenic Rocket Division.",
            category=InvestigationCategory.NEGATIVE_NOT_FOUND,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Helix Cryogenic Rocket Division"]},
            expected_entities=["Helix BioFoundry"],
            is_negative=True,
            expected_epistemic_status="NOT_FOUND",
            min_steps_required=3,
        ),
        InvestigationTask(
            task_id="fh_task_19_neg_zephyrus_quantum_sat",
            title="Negative Verification: Zephyrus Quantum Cryptographic Satellite",
            objective="Verify whether Zephyrus Supercomputing has launched or operates an orbital quantum cryptographic satellite constellation.",
            category=InvestigationCategory.NEGATIVE_NOT_FOUND,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Zephyrus Quantum Cryptographic Satellite"]},
            expected_entities=["Zephyrus Supercomputing"],
            is_negative=True,
            expected_epistemic_status="NOT_FOUND",
            min_steps_required=3,
        ),
        InvestigationTask(
            task_id="fh_task_20_neg_thalassa_mining_concession",
            title="Negative Verification: Thalassa Oceanics Seabed Mining Concession",
            objective="Verify whether Thalassa Oceanics holds an active federal or international commercial license for deep seabed mineral extraction.",
            category=InvestigationCategory.NEGATIVE_NOT_FOUND,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Thalassa Seabed Mining Concession"]},
            expected_entities=["Thalassa Oceanics"],
            is_negative=True,
            expected_epistemic_status="NOT_FOUND",
            min_steps_required=3,
        ),
        InvestigationTask(
            task_id="fh_task_21_neg_valles_nuclear_microreactor",
            title="Negative Verification: Valles Geothermal Nuclear Microreactor Unit",
            objective="Verify whether Valles Caldera Geothermal operates an auxiliary nuclear microreactor generation unit.",
            category=InvestigationCategory.NEGATIVE_NOT_FOUND,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Valles Nuclear Microreactor Unit"]},
            expected_entities=["Valles Caldera Geothermal"],
            is_negative=True,
            expected_epistemic_status="NOT_FOUND",
            min_steps_required=3,
        ),

        # Category F: Insufficient Evidence & Principled Abstention (4 tasks)
        InvestigationTask(
            task_id="fh_task_22_insuff_room_temp_superconductor",
            title="Epistemic Abstention: Copper-Doped Phosphide Ambient Superconductor",
            objective="Investigate claims of ambient room-temperature superconductivity in copper-doped phosphide. Determine if verified replication exists.",
            category=InvestigationCategory.INSUFFICIENT_EVIDENCE,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Copper-Doped Phosphide"]},
            expected_entities=["Copper-Doped Phosphide"],
            expected_epistemic_status="INSUFFICIENT_EVIDENCE",
            min_steps_required=3,
        ),
        InvestigationTask(
            task_id="fh_task_23_insuff_trade_secret_mixture",
            title="Epistemic Abstention: Titan-X Pretraining Token Mixture Ratios",
            objective="Determine the exact pretraining token mixture ratios and domain filtering formulas for the commercial foundation model Titan-X.",
            category=InvestigationCategory.INSUFFICIENT_EVIDENCE,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Titan-X Token Mixture"]},
            expected_entities=["Titan-X"],
            expected_epistemic_status="INSUFFICIENT_EVIDENCE",
            min_steps_required=3,
        ),
        InvestigationTask(
            task_id="fh_task_24_insuff_invitro_huntington",
            title="Epistemic Abstention: In Vitro Fibroblast Repeat Reversal Efficacy",
            objective="Evaluate clinical safety and human in vivo efficacy of the experimental CRISPR repeat-targeting therapy for Huntington disease.",
            category=InvestigationCategory.INSUFFICIENT_EVIDENCE,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Huntington Repeat Therapy"]},
            expected_entities=["CRISPR"],
            expected_epistemic_status="INSUFFICIENT_EVIDENCE",
            min_steps_required=3,
        ),
        InvestigationTask(
            task_id="fh_task_25_insuff_weathered_stele",
            title="Epistemic Abstention: Tell el-Farah Weathered Stele King Identity",
            objective="Identify the second royal name recorded on the 8th century BCE Tell el-Farah basalt stele.",
            category=InvestigationCategory.INSUFFICIENT_EVIDENCE,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Tell el-Farah Stele"]},
            expected_entities=["Tell el-Farah Stele"],
            expected_epistemic_status="INSUFFICIENT_EVIDENCE",
            min_steps_required=3,
        ),

        # Category G: Technical Engineering (3 tasks)
        InvestigationTask(
            task_id="fh_task_26_tech_sic_inverter_efficiency",
            title="Power Electronics: Silicon Carbide Inverter Peak Efficiency",
            objective="Investigate the Achelous 1200V Silicon Carbide traction inverter. Determine its certified peak conversion efficiency under 800V testing.",
            category=InvestigationCategory.TECHNICAL_ENGINEERING,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Achelous Inverter"]},
            expected_entities=["Achelous Inverter", "99.2%"],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        ),
        InvestigationTask(
            task_id="fh_task_27_tech_flibe_salt_properties",
            title="Nuclear Engineering: FLiBe Molten Salt Heat Capacity",
            objective="Determine the volumetric heat capacity and maximum operating thermal stability limit of FLiBe molten fluoride salt coolant.",
            category=InvestigationCategory.TECHNICAL_ENGINEERING,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["FLiBe Molten Salt"]},
            expected_entities=["FLiBe Molten Salt", "4540 kJ/m3-K", "1300 K"],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        ),
        InvestigationTask(
            task_id="fh_task_28_tech_cmsx4_superalloy_creep",
            title="Materials Science: CMSX-4 Single-Crystal Creep Life",
            objective="Investigate single-crystal nickel superalloy CMSX-4. Identify its verified creep rupture life under 1000°C and 140 MPa stress.",
            category=InvestigationCategory.TECHNICAL_ENGINEERING,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["CMSX-4 Superalloy"]},
            expected_entities=["CMSX-4 Superalloy", "1200 hours"],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        ),

        # Category H: Historical Chronology (2 tasks)
        InvestigationTask(
            task_id="fh_task_29_hist_utrecht_gibraltar",
            title="Diplomatic History: Treaty of Utrecht Gibraltar Cession",
            objective="Identify which article of the 1713 Treaty of Utrecht ceded the town and castle of Gibraltar to Great Britain.",
            category=InvestigationCategory.HISTORICAL,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Treaty of Utrecht"]},
            expected_entities=["Treaty of Utrecht", "Article X", "July 1713"],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        ),
        InvestigationTask(
            task_id="fh_task_30_hist_fed_act_1913",
            title="Monetary History: Federal Reserve Act Signing Date",
            objective="Determine the exact date and US President who signed the Federal Reserve Act of 1913 into law.",
            category=InvestigationCategory.HISTORICAL,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Federal Reserve Act 1913"]},
            expected_entities=["Federal Reserve Act 1913", "December 23, 1913", "Woodrow Wilson"],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        ),
    ]
