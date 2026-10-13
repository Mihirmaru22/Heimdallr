"""Heimdallr V2: 25-Task Benchmark Suite for EVAL_INVESTIGATION_V1.

Covering all 12 investigation categories:
- Multi-specialist chaining (>=30%)
- Contradiction & temporal resolution (>=30%)
- Negative / NOT_FOUND requirements (>=20%)
- Deep 5+ step research trajectories (>=20%)
- Flagship Apple-style 20-person executive investigation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class InvestigationCategory(str, Enum):
    COMPANY_INTELLIGENCE = "COMPANY_INTELLIGENCE"
    EXECUTIVE_INVESTIGATION = "EXECUTIVE_INVESTIGATION"
    MULTI_PERSON_RESEARCH = "MULTI_PERSON_RESEARCH"
    CORPORATE_RELATIONSHIP = "CORPORATE_RELATIONSHIP"
    INFRASTRUCTURE_INVESTIGATION = "INFRASTRUCTURE_INVESTIGATION"
    IDENTITY_INVESTIGATION = "IDENTITY_INVESTIGATION"
    CONTRADICTION_INVESTIGATION = "CONTRADICTION_INVESTIGATION"
    TEMPORAL_INVESTIGATION = "TEMPORAL_INVESTIGATION"
    MULTI_SPECIALIST_INVESTIGATION = "MULTI_SPECIALIST_INVESTIGATION"
    NEGATIVE_NOT_FOUND = "NEGATIVE_NOT_FOUND"
    LONG_HORIZON_INVESTIGATION = "LONG_HORIZON_INVESTIGATION"
    ADVERSARIAL_INVESTIGATION = "ADVERSARIAL_INVESTIGATION"
    # P0.3 Multi-Domain Research Benchmark Categories
    TECHNICAL_ENGINEERING = "TECHNICAL_ENGINEERING"
    HISTORICAL = "HISTORICAL"
    SCIENTIFIC_POLICY = "SCIENTIFIC_POLICY"
    ORGANIZATIONAL_CORPORATE = "ORGANIZATIONAL_CORPORATE"
    INTERDISCIPLINARY = "INTERDISCIPLINARY"
    TIME_SENSITIVE = "TIME_SENSITIVE"
    CONFLICTING_AMBIGUOUS = "CONFLICTING_AMBIGUOUS"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    MISLEADING_RESULTS = "MISLEADING_RESULTS"
    MULTI_FACT_SYNTHESIS = "MULTI_FACT_SYNTHESIS"


class InvestigationDifficulty(str, Enum):
    HARD = "HARD"
    VERY_HARD = "VERY_HARD"
    EXTREME = "EXTREME"


@dataclass
class InvestigationTask:
    task_id: str
    title: str
    objective: str
    category: InvestigationCategory
    difficulty: InvestigationDifficulty
    contract: dict[str, Any] = field(default_factory=dict)
    expected_entities: list[str] = field(default_factory=list)
    expected_claims: list[dict[str, str]] = field(default_factory=list)
    expected_epistemic_status: str = "SUPPORTED"
    expected_stop_reason: str = "OBJECTIVE_SATISFIED"
    requires_multi_specialist: bool = False
    has_contradiction: bool = False
    has_temporal_trap: bool = False
    is_negative: bool = False
    min_steps_required: int = 3


def build_investigation_v1_tasks() -> list[InvestigationTask]:
    """Generate the official 25 frozen investigation tasks for EVAL_INVESTIGATION_V1."""
    tasks: list[InvestigationTask] = []

    # -------------------------------------------------------------------------
    # 1. Multi-Person Research (Flagship 20-Person Apple-Style Investigation)
    # -------------------------------------------------------------------------
    tasks.append(
        InvestigationTask(
            task_id="inv_task_01_apple_style_20_executives",
            title="Comprehensive 20-Executive Leadership Investigation (Apex Technologies Group)",
            objective=(
                "Research Apex Technologies Group. Identify 20 current VP/SVP-level executives. For each executive determine: "
                "name, current title, responsibility, organization, current status, career history, professional identity, "
                "and publicly documented business contact channel. Do NOT invent contact information. Distinguish SUPPORTED, "
                "UNKNOWN, and NOT_FOUND."
            ),
            category=InvestigationCategory.MULTI_PERSON_RESEARCH,
            difficulty=InvestigationDifficulty.EXTREME,
            contract={
                "target_entities": ["Apex Technologies Group"],
                "expected_executive_count": 20,
                "max_steps": 25,
            },
            expected_entities=[
                "Sarah Lin", "David Marcus", "Elena Rostova", "Marcus Vance", "Rachel Thorne",
                "Julian Chen", "Amina Al-Mansoor", "Tobias Richter", "Chloe Bennett", "Dr. Kenji Sato",
                "Vikram Patel", "Sofia Rodriguez", "Arthur Pendelton", "Nadia O'Connor", "Liam Gallagher",
                "Ingrid Lindstrom", "Zackary Taylor", "Maya Krishnan", "Gregory Houseman", "Oliver Queenan",
            ],
            requires_multi_specialist=True,
            min_steps_required=6,
        )
    )

    # -------------------------------------------------------------------------
    # 2. Executive Investigation (Single Deep Person)
    # -------------------------------------------------------------------------
    tasks.append(
        InvestigationTask(
            task_id="inv_task_02_executive_deep_ai_svp",
            title="Investigate active SVP of Machine Learning & AI at Apex Technologies",
            objective="Determine current active leader of Machine Learning & AI at Apex Technologies, their career background, and public contact.",
            category=InvestigationCategory.EXECUTIVE_INVESTIGATION,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Apex Technologies Group"]},
            expected_entities=["David Marcus", "Apex Technologies Group"],
            expected_claims=[
                {"subject": "David Marcus", "predicate": "title", "object": "Senior Vice President, Machine Learning & AI"},
                {"subject": "David Marcus", "predicate": "email", "object": "dmarcus-research@apex-tech.com"},
            ],
            has_temporal_trap=True,
            min_steps_required=3,
        )
    )

    tasks.append(
        InvestigationTask(
            task_id="inv_task_03_executive_cloud_ops",
            title="Investigate SVP Cloud Infrastructure Sarah Lin",
            objective="Establish Sarah Lin's operational remit, corporate organization, and previous leadership position.",
            category=InvestigationCategory.EXECUTIVE_INVESTIGATION,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Sarah Lin", "Apex Technologies Group"]},
            expected_entities=["Sarah Lin", "Apex Technologies Group"],
            has_temporal_trap=True,
            min_steps_required=3,
        )
    )

    # -------------------------------------------------------------------------
    # 3. Company Intelligence
    # -------------------------------------------------------------------------
    tasks.append(
        InvestigationTask(
            task_id="inv_task_04_apex_company_bounds",
            title="Establish corporate boundaries and primary jurisdiction for Apex Technologies Group",
            objective="Identify primary legal entity name, CIK identifier, state of incorporation, and headquarters for Apex Technologies Group.",
            category=InvestigationCategory.COMPANY_INTELLIGENCE,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Apex Technologies Group"]},
            expected_entities=["Apex Technologies Group Inc"],
            min_steps_required=3,
        )
    )

    tasks.append(
        InvestigationTask(
            task_id="inv_task_05_european_headquarters",
            title="Identify European operating arm and London legal entity",
            objective="Identify the UK operating subsidiary of Apex Technologies Group and its managing director.",
            category=InvestigationCategory.COMPANY_INTELLIGENCE,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Apex Technologies Group"]},
            expected_entities=["Apex Technologies Europe Ltd", "Tobias Richter"],
            requires_multi_specialist=True,
            min_steps_required=4,
        )
    )

    # -------------------------------------------------------------------------
    # 4. Corporate Relationship Investigation
    # -------------------------------------------------------------------------
    tasks.append(
        InvestigationTask(
            task_id="inv_task_06_subsidiary_hierarchy",
            title="Traverse global subsidiary schedule from SEC Exhibit 21",
            objective="Extract all active first-tier international subsidiaries disclosed by Apex Technologies Group.",
            category=InvestigationCategory.CORPORATE_RELATIONSHIP,
            difficulty=InvestigationDifficulty.VERY_HARD,
            contract={"target_entities": ["Apex Technologies Group"]},
            expected_entities=["Apex Technologies Europe Ltd", "Apex Cloud Infrastructure LLC", "Apex Quantum Sensing GmbH", "Apex Asia-Pacific Pte Ltd"],
            min_steps_required=4,
        )
    )

    tasks.append(
        InvestigationTask(
            task_id="inv_task_07_uk_sub_to_telemetry",
            title="Traverse 2-tier corporate chain from UK subsidiary to Telemetry vehicle",
            objective="Identify the dedicated technical infrastructure subsidiary held by Apex Technologies Europe Ltd.",
            category=InvestigationCategory.CORPORATE_RELATIONSHIP,
            difficulty=InvestigationDifficulty.VERY_HARD,
            contract={"target_entities": ["Apex Technologies Europe Ltd"]},
            expected_entities=["Apex Telemetry UK Limited", "Apex Technologies Europe Ltd"],
            requires_multi_specialist=True,
            has_temporal_trap=True,
            min_steps_required=4,
        )
    )

    # -------------------------------------------------------------------------
    # 5. Infrastructure Investigation
    # -------------------------------------------------------------------------
    tasks.append(
        InvestigationTask(
            task_id="inv_task_08_ct_san_enumeration",
            title="Enumerate Certificate Transparency SAN endpoints for apex-telemetry.co.uk",
            objective="Discover all SAN hostnames and technical administrator contacts registered under apex-telemetry.co.uk.",
            category=InvestigationCategory.INFRASTRUCTURE_INVESTIGATION,
            difficulty=InvestigationDifficulty.VERY_HARD,
            contract={"target_entities": ["apex-telemetry.co.uk"]},
            expected_entities=["telemetry-cluster-01.apex-telemetry.co.uk", "quantum-monitor.apex-sensing.de"],
            requires_multi_specialist=True,
            min_steps_required=4,
        )
    )

    tasks.append(
        InvestigationTask(
            task_id="inv_task_09_quantum_sensing_infra",
            title="Map cross-border infrastructure to German sensing unit",
            objective="Trace quantum monitor infrastructure endpoint back to German operating subsidiary.",
            category=InvestigationCategory.INFRASTRUCTURE_INVESTIGATION,
            difficulty=InvestigationDifficulty.VERY_HARD,
            contract={"target_entities": ["Apex Quantum Sensing GmbH"]},
            expected_entities=["quantum-monitor.apex-sensing.de", "Apex Quantum Sensing GmbH"],
            requires_multi_specialist=True,
            min_steps_required=4,
        )
    )

    # -------------------------------------------------------------------------
    # 6. Identity Investigation
    # -------------------------------------------------------------------------
    tasks.append(
        InvestigationTask(
            task_id="inv_task_10_kenji_sato_identity",
            title="Correlate professional identity and academic provenance of Dr. Kenji Sato",
            objective="Establish Dr. Kenji Sato's academic affiliation, prior university role, and current quantum research scope.",
            category=InvestigationCategory.IDENTITY_INVESTIGATION,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Dr. Kenji Sato"]},
            expected_entities=["Dr. Kenji Sato", "Apex Technologies Group"],
            min_steps_required=3,
        )
    )

    tasks.append(
        InvestigationTask(
            task_id="inv_task_11_rachel_thorne_ciso",
            title="Trace CISO career history for Rachel Thorne",
            objective="Identify Rachel Thorne's former employer prior to assuming SVP Security at Apex Technologies.",
            category=InvestigationCategory.IDENTITY_INVESTIGATION,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Rachel Thorne"]},
            expected_entities=["Rachel Thorne", "Cyberspace Defense Corp"],
            is_negative=True,
            min_steps_required=3,
        )
    )

    # -------------------------------------------------------------------------
    # 7. Contradiction Investigation
    # -------------------------------------------------------------------------
    tasks.append(
        InvestigationTask(
            task_id="inv_task_12_contradiction_ai_leadership",
            title="Resolve contradictory reporting on Head of AI (Donald Vance vs David Marcus)",
            objective="Form 10-K from 2020 lists Donald Vance as SVP of AI, while current report lists David Marcus. Resolve which individual is currently authoritative.",
            category=InvestigationCategory.CONTRADICTION_INVESTIGATION,
            difficulty=InvestigationDifficulty.VERY_HARD,
            contract={"target_entities": ["Apex Technologies Group"]},
            expected_entities=["David Marcus", "Apex Technologies Group"],
            has_contradiction=True,
            min_steps_required=4,
        )
    )

    tasks.append(
        InvestigationTask(
            task_id="inv_task_13_contradiction_restatement_date",
            title="Resolve Form 10-K/A amendment effective date for leadership restatement",
            objective="Identify the specific effective date when David Marcus succeeded Donald Vance per Form 10-K/A amendment.",
            category=InvestigationCategory.CONTRADICTION_INVESTIGATION,
            difficulty=InvestigationDifficulty.VERY_HARD,
            contract={"target_entities": ["David Marcus"]},
            expected_entities=["David Marcus", "Donald Vance"],
            has_contradiction=True,
            has_temporal_trap=True,
            min_steps_required=4,
        )
    )

    # -------------------------------------------------------------------------
    # 8. Temporal Investigation
    # -------------------------------------------------------------------------
    tasks.append(
        InvestigationTask(
            task_id="inv_task_14_historical_state_2020",
            title="Determine executive leadership as of historical date: December 31, 2020",
            objective="What individual authoritatively served as SVP of Machine Learning & AI at Apex Technologies as of December 31, 2020?",
            category=InvestigationCategory.TEMPORAL_INVESTIGATION,
            difficulty=InvestigationDifficulty.VERY_HARD,
            contract={"as_of_date": "2020-12-31"},
            expected_entities=["Donald Vance", "Apex Technologies Group"],
            has_temporal_trap=True,
            min_steps_required=4,
        )
    )

    tasks.append(
        InvestigationTask(
            task_id="inv_task_15_sarah_lin_temporal_promotion",
            title="Determine Sarah Lin's title in 2020 vs 2024",
            objective="Verify whether Sarah Lin held the Senior Vice President title in 2020 or was promoted at a later date.",
            category=InvestigationCategory.TEMPORAL_INVESTIGATION,
            difficulty=InvestigationDifficulty.VERY_HARD,
            contract={"as_of_date": "2020-06-01"},
            expected_entities=["Sarah Lin"],
            has_temporal_trap=True,
            min_steps_required=4,
        )
    )

    # -------------------------------------------------------------------------
    # 9. Multi-Specialist Investigation (Chaining: Corporate -> Infra -> Identity)
    # -------------------------------------------------------------------------
    tasks.append(
        InvestigationTask(
            task_id="inv_task_16_chain_corp_infra_ident",
            title="Cross-Specialist Chain: SEC Filing -> UK Registry -> CT Log -> CISO Probe",
            objective="Starting from Apex Technologies Group, discover its UK subsidiary, the telemetry domain SAN, and verify the administrative contact CISO.",
            category=InvestigationCategory.MULTI_SPECIALIST_INVESTIGATION,
            difficulty=InvestigationDifficulty.EXTREME,
            contract={"target_entities": ["Apex Technologies Group"]},
            expected_entities=["Apex Technologies Europe Ltd", "telemetry-cluster-01.apex-telemetry.co.uk", "Rachel Thorne"],
            requires_multi_specialist=True,
            min_steps_required=5,
        )
    )

    tasks.append(
        InvestigationTask(
            task_id="inv_task_17_chain_german_quantum_infra",
            title="Cross-Specialist Chain: Subsidiary -> Sensing Hostname -> Quantum Director",
            objective="Trace German subsidiary to its quantum monitoring hostname, and verify the responsible Senior Vice President.",
            category=InvestigationCategory.MULTI_SPECIALIST_INVESTIGATION,
            difficulty=InvestigationDifficulty.EXTREME,
            contract={"target_entities": ["Apex Quantum Sensing GmbH"]},
            expected_entities=["Apex Quantum Sensing GmbH", "quantum-monitor.apex-sensing.de", "Dr. Kenji Sato"],
            requires_multi_specialist=True,
            min_steps_required=5,
        )
    )

    tasks.append(
        InvestigationTask(
            task_id="inv_task_18_chain_uk_managing_director",
            title="Cross-Specialist Chain: SEC 10-K -> Companies House -> Managing Director Profile",
            objective="Identify UK subsidiary from US filing, retrieve statutory director Tobias Richter, and map his European regulatory scope.",
            category=InvestigationCategory.MULTI_SPECIALIST_INVESTIGATION,
            difficulty=InvestigationDifficulty.VERY_HARD,
            contract={"target_entities": ["Apex Technologies Group"]},
            expected_entities=["Apex Technologies Europe Ltd", "Tobias Richter"],
            requires_multi_specialist=True,
            min_steps_required=4,
        )
    )

    # -------------------------------------------------------------------------
    # 10. Negative / NOT_FOUND
    # -------------------------------------------------------------------------
    tasks.append(
        InvestigationTask(
            task_id="inv_task_19_negative_nonexistent_vp",
            title="Investigate fictitious executive: VP of Quantum Cryptocurrency",
            objective="Verify whether Apex Technologies employs a 'Vice President of Quantum Cryptocurrency'. Do NOT invent or infer.",
            category=InvestigationCategory.NEGATIVE_NOT_FOUND,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Apex Technologies Group"]},
            expected_entities=[],
            expected_epistemic_status="NOT_FOUND",
            is_negative=True,
            min_steps_required=3,
        )
    )

    tasks.append(
        InvestigationTask(
            task_id="inv_task_20_negative_unrelated_roofing_corp",
            title="Disambiguate unrelated Nevada entity: Apex Commercial Roofing",
            objective="Investigate whether Apex Commercial Roofing LLC in Nevada is a subsidiary of Apex Technologies Group.",
            category=InvestigationCategory.NEGATIVE_NOT_FOUND,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Apex Commercial Roofing LLC"]},
            expected_entities=["Apex Commercial Roofing LLC"],
            expected_epistemic_status="NOT_FOUND",
            is_negative=True,
            min_steps_required=3,
        )
    )

    tasks.append(
        InvestigationTask(
            task_id="inv_task_21_negative_missing_executive_email",
            title="Investigate public contact channel for VP Elena Rostova",
            objective="Retrieve public business contact email for Elena Rostova. Return NOT_FOUND if undisclosed.",
            category=InvestigationCategory.NEGATIVE_NOT_FOUND,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Elena Rostova"]},
            expected_entities=["Elena Rostova"],
            expected_epistemic_status="NOT_FOUND",
            is_negative=True,
            min_steps_required=3,
        )
    )

    # -------------------------------------------------------------------------
    # 11. Long-Horizon Investigation (5+ Steps)
    # -------------------------------------------------------------------------
    tasks.append(
        InvestigationTask(
            task_id="inv_task_22_long_horizon_full_org_tree",
            title="Long-Horizon Comprehensive Corporate Hierarchy & Executive Traversal",
            objective="Trace complete 4-tier tree: Apex US -> Apex UK -> Apex Telemetry UK -> CISO Contact -> Identity Carrier.",
            category=InvestigationCategory.LONG_HORIZON_INVESTIGATION,
            difficulty=InvestigationDifficulty.EXTREME,
            contract={"target_entities": ["Apex Technologies Group"], "max_steps": 12},
            expected_entities=["Apex Technologies Group Inc", "Apex Technologies Europe Ltd", "Apex Telemetry UK Limited", "Rachel Thorne"],
            requires_multi_specialist=True,
            min_steps_required=6,
        )
    )

    tasks.append(
        InvestigationTask(
            task_id="inv_task_23_long_horizon_quantum_consortium",
            title="Long-Horizon Quantum Unit Exploration & Syndication Audit",
            objective="Investigate Apex quantum unit, cluster press wire releases, and verify Dr. Kenji Sato's academic roots.",
            category=InvestigationCategory.LONG_HORIZON_INVESTIGATION,
            difficulty=InvestigationDifficulty.EXTREME,
            contract={"target_entities": ["Apex Quantum Sensing GmbH"], "max_steps": 12},
            expected_entities=["Apex Quantum Sensing GmbH", "Dr. Kenji Sato", "University of Tokyo"],
            requires_multi_specialist=True,
            min_steps_required=5,
        )
    )

    # -------------------------------------------------------------------------
    # 12. Adversarial Investigation
    # -------------------------------------------------------------------------
    tasks.append(
        InvestigationTask(
            task_id="inv_task_24_adversarial_homoglyph_filtering",
            title="Detect and neutralize lookalike phishing homoglyph apex-g1obal-tech.com",
            objective="Investigate apex-g1obal-tech.com. Verify if it belongs to Apex Technologies Group or represents an adversarial imposter.",
            category=InvestigationCategory.ADVERSARIAL_INVESTIGATION,
            difficulty=InvestigationDifficulty.VERY_HARD,
            contract={"target_entities": ["apex-g1obal-tech.com"]},
            expected_entities=[],
            expected_epistemic_status="CONTRADICTED",
            requires_multi_specialist=True,
            has_contradiction=True,
            is_negative=True,
            min_steps_required=3,
        )
    )

    tasks.append(
        InvestigationTask(
            task_id="inv_task_25_adversarial_syndication_cluster",
            title="Adversarial Syndication: De-duplicate 3 Wire Releases into Single Source",
            objective="Analyze reports on 512-qubit demonstration across Business Wire, PR Newswire, and MarketWatch. Verify source independence.",
            category=InvestigationCategory.ADVERSARIAL_INVESTIGATION,
            difficulty=InvestigationDifficulty.VERY_HARD,
            contract={"target_entities": ["Apex Technologies Group"]},
            expected_entities=["Dr. Kenji Sato", "Apex Technologies Group"],
            has_contradiction=True,
            min_steps_required=4,
        )
    )

    return tasks


def build_p03_benchmark_tasks() -> list[InvestigationTask]:
    """Generate 25 rigorous multi-domain investigation tasks for P0.3 Research Accuracy Benchmark.

    Covers all 10 required research domains:
    1. Technical and engineering research (Tasks 26-28)
    2. Historical research (Tasks 29-30)
    3. Scientific and policy research (Tasks 31-32)
    4. Organizational and corporate research (Tasks 33-34)
    5. Interdisciplinary or unfamiliar-domain research (Tasks 35-36)
    6. Time-sensitive factual questions with dated fixtures (Tasks 37-38)
    7. Conflicting or ambiguous source material (Tasks 39-40)
    8. Insufficient evidence / negative verification (Tasks 41-43)
    9. Misleading or irrelevant search results (Tasks 44-45)
    10. Multi-fact synthesis (Tasks 46-50)
    """
    tasks: list[InvestigationTask] = []

    # -------------------------------------------------------------------------
    # 1. Technical & Engineering Research
    # -------------------------------------------------------------------------
    tasks.append(
        InvestigationTask(
            task_id="inv_task_26_raft_split_brain",
            title="Raft Consensus: Quorum Partitioning & Split-Brain Prevention",
            objective=(
                "Investigate Raft consensus algorithm under network partition. How does Raft prevent "
                "split-brain and conflicting state machine commits when a 5-node cluster is partitioned "
                "into 3 nodes and 2 nodes?"
            ),
            category=InvestigationCategory.TECHNICAL_ENGINEERING,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Raft"]},
            expected_entities=["Raft", "Diego Ongaro", "John Ousterhout"],
            expected_claims=[
                {"subject": "Raft", "predicate": "quorum_requirement", "object": "Majority quorum of (N/2)+1 nodes"},
            ],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        )
    )

    tasks.append(
        InvestigationTask(
            task_id="inv_task_27_ebpf_verifier_bounds",
            title="Linux eBPF Kernel Verifier: Safety Bounds & Termination Guarantees",
            objective=(
                "Investigate Linux eBPF kernel verifier. What mechanism guarantees kernel memory safety, "
                "bounds checking on memory pointers, and ensures termination of BPF programs?"
            ),
            category=InvestigationCategory.TECHNICAL_ENGINEERING,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["eBPF Verifier", "Linux Kernel"]},
            expected_entities=["eBPF Verifier", "Linux Kernel", "Alexei Starovoitov"],
            expected_claims=[
                {"subject": "eBPF Verifier", "predicate": "safety_check", "object": "Directed acyclic graph state exploration and register bound tracking"},
            ],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        )
    )

    tasks.append(
        InvestigationTask(
            task_id="inv_task_28_riscv_memory_model",
            title="RISC-V Weak Memory Ordering (RVWMO) Specification",
            objective=(
                "Investigate RISC-V weak memory ordering (RVWMO). How does RVWMO distinguish syntactic "
                "dependencies from explicit FENCE instructions in multi-core execution?"
            ),
            category=InvestigationCategory.TECHNICAL_ENGINEERING,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["RVWMO", "RISC-V"]},
            expected_entities=["RVWMO", "RISC-V", "FENCE"],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        )
    )

    # -------------------------------------------------------------------------
    # 2. Historical Research
    # -------------------------------------------------------------------------
    tasks.append(
        InvestigationTask(
            task_id="inv_task_29_bretton_woods_nixon_shock",
            title="Nixon Shock 1971: Suspension of Gold Convertibility",
            objective=(
                "Investigate the August 15, 1971 economic announcement by Richard Nixon. What specific "
                "policy actions were enacted regarding the Bretton Woods monetary system and gold convertibility?"
            ),
            category=InvestigationCategory.HISTORICAL,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Richard Nixon", "Camp David"]},
            expected_entities=["Richard Nixon", "Camp David", "John Connally"],
            expected_claims=[
                {"subject": "Richard Nixon", "predicate": "action", "object": "Suspended gold convertibility of the US dollar"},
            ],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        )
    )

    tasks.append(
        InvestigationTask(
            task_id="inv_task_30_treaty_of_utrecht_gibraltar",
            title="Treaty of Utrecht (1713) Article X: Cession of Gibraltar",
            objective=(
                "Investigate Article X of the 1713 Treaty of Utrecht. What specific rights and territorial "
                "boundaries did Spain cede regarding the Town and Castle of Gibraltar to Great Britain?"
            ),
            category=InvestigationCategory.HISTORICAL,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Treaty of Utrecht", "Gibraltar"]},
            expected_entities=["Treaty of Utrecht", "Philip V of Spain", "Queen Anne"],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        )
    )

    # -------------------------------------------------------------------------
    # 3. Scientific and Policy Research
    # -------------------------------------------------------------------------
    tasks.append(
        InvestigationTask(
            task_id="inv_task_31_mrna_lipid_nanoparticles",
            title="Lipid Nanoparticle Formulations in mRNA Vaccine Platforms",
            objective=(
                "Investigate lipid nanoparticle (LNP) compositions in commercial mRNA vaccines. What four "
                "lipid components comprise the nanoparticle delivery vehicle and what is the functional role of the ionizable cationic lipid?"
            ),
            category=InvestigationCategory.SCIENTIFIC_POLICY,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Lipid Nanoparticle"]},
            expected_entities=["Lipid Nanoparticle", "Ionizable Lipid", "PEG-Lipid", "DSPC"],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        )
    )

    tasks.append(
        InvestigationTask(
            task_id="inv_task_32_eu_ai_act_high_risk",
            title="EU AI Act (Regulation 2024/1689): High-Risk AI Classification",
            objective=(
                "Investigate Regulation (EU) 2024/1689 (EU AI Act). What criteria under Article 6 and "
                "Annex III classify an artificial intelligence system as High-Risk, and what CE conformity obligations are imposed?"
            ),
            category=InvestigationCategory.SCIENTIFIC_POLICY,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["EU AI Act"]},
            expected_entities=["EU AI Act", "Annex III", "European Parliament"],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        )
    )

    # -------------------------------------------------------------------------
    # 4. Organizational and Corporate Research
    # -------------------------------------------------------------------------
    tasks.append(
        InvestigationTask(
            task_id="inv_task_33_airbus_eads_reorganization",
            title="Corporate Reorganization: EADS to Airbus Group (2014)",
            objective=(
                "Investigate the January 2014 restructuring of EADS into Airbus Group. What three operational "
                "divisions were created and how was state shareholding by France and Germany balanced?"
            ),
            category=InvestigationCategory.ORGANIZATIONAL_CORPORATE,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Airbus Group", "EADS"]},
            expected_entities=["Airbus Group", "EADS", "Tom Enders"],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        )
    )

    tasks.append(
        InvestigationTask(
            task_id="inv_task_34_asml_euv_suppliers",
            title="ASML EUV Photolithography Supply Chain Dependencies",
            objective=(
                "Investigate ASML's supply chain for High-NA extreme ultraviolet (EUV) photolithography scanners. "
                "Which sole-source industrial partners supply the mirror optics and high-power CO2 drive laser systems?"
            ),
            category=InvestigationCategory.ORGANIZATIONAL_CORPORATE,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["ASML Holding"]},
            expected_entities=["ASML Holding", "Carl Zeiss SMT", "Trumpf"],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        )
    )

    # -------------------------------------------------------------------------
    # 5. Interdisciplinary or Unfamiliar-Domain Research
    # -------------------------------------------------------------------------
    tasks.append(
        InvestigationTask(
            task_id="inv_task_35_chaco_canyon_archaeoastronomy",
            title="Archaeoastronomy: Fajada Butte Sun Dagger at Chaco Canyon",
            objective=(
                "Investigate archaeoastronomical features at Fajada Butte in Chaco Canyon. What celestial alignments "
                "does the Three-Slab Sun Dagger petroglyph record regarding solstices, equinoxes, and the 18.6-year lunar standstill cycle?"
            ),
            category=InvestigationCategory.INTERDISCIPLINARY,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Chaco Canyon", "Fajada Butte"]},
            expected_entities=["Chaco Canyon", "Fajada Butte", "Sun Dagger", "Anna Sofaer"],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        )
    )

    tasks.append(
        InvestigationTask(
            task_id="inv_task_36_basque_ergative_syntax",
            title="Morphosyntactic Alignment: Basque Ergative-Absolutive Grammar",
            objective=(
                "Investigate the morphosyntactic alignment of the Basque language (Euskara). How does its "
                "ergative-absolutive case marking differentiate transitive subjects from intransitive subjects and direct objects?"
            ),
            category=InvestigationCategory.INTERDISCIPLINARY,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Basque Language"]},
            expected_entities=["Basque Language", "Ergative-Absolutive", "Absolutive Case"],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        )
    )

    # -------------------------------------------------------------------------
    # 6. Time-Sensitive Factual Questions (Dated Fixtures)
    # -------------------------------------------------------------------------
    tasks.append(
        InvestigationTask(
            task_id="inv_task_37_uk_pm_transition_oct_2022",
            title="Temporal Governance: UK Prime Minister on October 23, 2022",
            objective=(
                "Determine the legally authoritative Prime Minister of the United Kingdom as of October 23, 2022 "
                "versus October 25, 2022."
            ),
            category=InvestigationCategory.TIME_SENSITIVE,
            difficulty=InvestigationDifficulty.VERY_HARD,
            contract={"as_of_date": "2022-10-23", "target_entities": ["10 Downing Street"]},
            expected_entities=["Liz Truss", "10 Downing Street"],
            has_temporal_trap=True,
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        )
    )

    tasks.append(
        InvestigationTask(
            task_id="inv_task_38_sec_etf_approval_dates",
            title="Temporal Verification: SEC Spot Bitcoin ETF Regulatory Order",
            objective=(
                "Investigate the official SEC regulatory approval date for spot Bitcoin ETPs. Distinguish the compromised "
                "Twitter announcement on January 9, 2024 from the authoritative Commission order on January 10, 2024."
            ),
            category=InvestigationCategory.TIME_SENSITIVE,
            difficulty=InvestigationDifficulty.VERY_HARD,
            contract={"as_of_date": "2024-01-09", "target_entities": ["Securities and Exchange Commission"]},
            expected_entities=["Gary Gensler", "Securities and Exchange Commission"],
            has_temporal_trap=True,
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        )
    )

    # -------------------------------------------------------------------------
    # 7. Questions with Conflicting or Ambiguous Source Material
    # -------------------------------------------------------------------------
    tasks.append(
        InvestigationTask(
            task_id="inv_task_39_drake_equation_parameters",
            title="Conflicting Astrobiology Estimates: Drake Equation Factor N",
            objective=(
                "Analyze the conflicting scientific estimates for the number of communicating extraterrestrial "
                "civilizations (N) in the Milky Way. Contrast Frank Drake's optimistic estimates with modern evolutionary "
                "and astrobiological lower bounds."
            ),
            category=InvestigationCategory.CONFLICTING_AMBIGUOUS,
            difficulty=InvestigationDifficulty.VERY_HARD,
            contract={"target_entities": ["Drake Equation"]},
            expected_entities=["Drake Equation", "Frank Drake", "Fermi Paradox"],
            has_contradiction=True,
            expected_epistemic_status="CONTRADICTED",
            min_steps_required=3,
        )
    )

    tasks.append(
        InvestigationTask(
            task_id="inv_task_40_speed_of_light_roemer_1676",
            title="Historical Conflict: Ole Rømer vs Christiaan Huygens Speed of Light",
            objective=(
                "Investigate Ole Rømer's 1676 observations of Jupiter's moon Io. Resolve the conflicting historical "
                "accounts regarding whether Rømer explicitly calculated a numerical speed of light or Christiaan Huygens "
                "derived the first quantitative value."
            ),
            category=InvestigationCategory.CONFLICTING_AMBIGUOUS,
            difficulty=InvestigationDifficulty.VERY_HARD,
            contract={"target_entities": ["Ole Rømer"]},
            expected_entities=["Ole Rømer", "Christiaan Huygens", "Io"],
            has_contradiction=True,
            expected_epistemic_status="CONTRADICTED",
            min_steps_required=3,
        )
    )

    # -------------------------------------------------------------------------
    # 8. Questions Where Available Evidence Is Insufficient
    # -------------------------------------------------------------------------
    tasks.append(
        InvestigationTask(
            task_id="inv_task_41_lk99_superconductor_reproduction",
            title="Insufficient Evidence: Room-Temperature Superconductivity in LK-99",
            objective=(
                "Investigate whether independent laboratories successfully confirmed room-temperature superconductivity "
                "in copper-doped lead apatite (LK-99). Distinguish verified magnetic levitation from genuine zero-electrical resistance."
            ),
            category=InvestigationCategory.INSUFFICIENT_EVIDENCE,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["LK-99"]},
            expected_entities=["LK-99", "Max Planck Institute"],
            is_negative=True,
            expected_epistemic_status="INSUFFICIENT_EVIDENCE",
            min_steps_required=3,
        )
    )

    tasks.append(
        InvestigationTask(
            task_id="inv_task_42_dark_matter_wimp_detection",
            title="Insufficient Evidence: Direct Detection of Dark Matter WIMPs",
            objective=(
                "Investigate whether direct detection experiments (such as LUX-ZEPLIN or XENONnT) have discovered "
                "particle dark matter WIMPs. Return INSUFFICIENT_EVIDENCE if no confirmed detection exists."
            ),
            category=InvestigationCategory.INSUFFICIENT_EVIDENCE,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["LUX-ZEPLIN"]},
            expected_entities=["LUX-ZEPLIN", "WIMP", "DAMA/LIBRA"],
            is_negative=True,
            expected_epistemic_status="INSUFFICIENT_EVIDENCE",
            min_steps_required=3,
        )
    )

    tasks.append(
        InvestigationTask(
            task_id="inv_task_43_voynich_manuscript_decipherment",
            title="Insufficient Evidence: Decipherment of the Voynich Manuscript",
            objective=(
                "Investigate claims that the Voynich manuscript (Beinecke MS 408) has been definitively translated "
                "into modern Turkish or proto-Romance. Return INSUFFICIENT_EVIDENCE if consensus linguistic decipherment is unproven."
            ),
            category=InvestigationCategory.INSUFFICIENT_EVIDENCE,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Voynich Manuscript"]},
            expected_entities=["Voynich Manuscript", "Wilfrid Voynich", "Beinecke Library"],
            is_negative=True,
            expected_epistemic_status="INSUFFICIENT_EVIDENCE",
            min_steps_required=3,
        )
    )

    # -------------------------------------------------------------------------
    # 9. Misleading or Irrelevant Search Results
    # -------------------------------------------------------------------------
    tasks.append(
        InvestigationTask(
            task_id="inv_task_44_python_pep703_gil_misinformation",
            title="Misinformation Filtering: PEP 703 Free-Threaded CPython",
            objective=(
                "Investigate Python PEP 703 (free-threaded CPython). Distinguish genuine CPython 3.13 experimental "
                "--disable-gil implementation from obsolete claims that removing the GIL was rejected or impossible without a 50% slowdown."
            ),
            category=InvestigationCategory.MISLEADING_RESULTS,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["PEP 703"]},
            expected_entities=["PEP 703", "Sam Gross", "Guido van Rossum"],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        )
    )

    tasks.append(
        InvestigationTask(
            task_id="inv_task_45_quantum_radar_stealth_capabilities",
            title="Adversarial Claims: Quantum Radar Anti-Stealth Capabilities",
            objective=(
                "Investigate quantum illumination and quantum radar claims regarding detection of military stealth aircraft. "
                "Distinguish laboratory entangled microwave photon demonstrations from exaggerated claims of operational anti-stealth radar deployment."
            ),
            category=InvestigationCategory.MISLEADING_RESULTS,
            difficulty=InvestigationDifficulty.VERY_HARD,
            contract={"target_entities": ["Quantum Illumination"]},
            expected_entities=["Quantum Illumination", "Seth Lloyd"],
            has_contradiction=True,
            expected_epistemic_status="CONTRADICTED",
            min_steps_required=3,
        )
    )

    # -------------------------------------------------------------------------
    # 10. Multi-Fact Synthesis
    # -------------------------------------------------------------------------
    tasks.append(
        InvestigationTask(
            task_id="inv_task_46_apollo_11_1202_alarm",
            title="Multi-Fact Engineering Forensics: Apollo 11 1202 Program Alarm",
            objective=(
                "Synthesize the root cause of the Apollo 11 Lunar Module 1202 program alarm during lunar descent. "
                "Combine radar power interface mismatch, radar hardware duty cycle, and Hal Laning's priority-scheduled executive queue."
            ),
            category=InvestigationCategory.MULTI_FACT_SYNTHESIS,
            difficulty=InvestigationDifficulty.VERY_HARD,
            contract={"target_entities": ["Apollo Guidance Computer"]},
            expected_entities=["Apollo Guidance Computer", "1202 Alarm", "Hal Laning", "Margaret Hamilton"],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=4,
        )
    )

    tasks.append(
        InvestigationTask(
            task_id="inv_task_47_deepwater_horizon_blowout_root_causes",
            title="Multi-Barrier Technical Forensics: Deepwater Horizon Blowout",
            objective=(
                "Synthesize the multi-barrier technical failures in the 2010 Deepwater Horizon Macondo well blowout: "
                "nitrogen foam cement slurry instability, negative pressure test misinterpretation, and BOP blind shear ram pipe de-centering."
            ),
            category=InvestigationCategory.MULTI_FACT_SYNTHESIS,
            difficulty=InvestigationDifficulty.VERY_HARD,
            contract={"target_entities": ["Deepwater Horizon"]},
            expected_entities=["Deepwater Horizon", "Macondo Well", "Blowout Preventer", "Halliburton"],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=4,
        )
    )

    tasks.append(
        InvestigationTask(
            task_id="inv_task_48_voyager_1_heliopause_crossing",
            title="Empirical Multi-Sensor Synthesis: Voyager 1 Heliopause Crossing",
            objective=(
                "Synthesize the three empirical signatures observed by Voyager 1 on August 25, 2012 that established "
                "its entry into interstellar space: heliospheric ion depletion, galactic cosmic ray increase, and magnetic field continuity."
            ),
            category=InvestigationCategory.MULTI_FACT_SYNTHESIS,
            difficulty=InvestigationDifficulty.VERY_HARD,
            contract={"target_entities": ["Voyager 1"]},
            expected_entities=["Voyager 1", "Heliopause", "Ed Stone"],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=4,
        )
    )

    tasks.append(
        InvestigationTask(
            task_id="inv_task_49_doom_bsp_rendering_architecture",
            title="Algorithmic Synthesis: Binary Space Partitioning in Doom Engine",
            objective=(
                "Synthesize John Carmack's implementation of binary space partitioning (BSP) trees in the 1993 Doom engine. "
                "Combine sub-sector 2D space partition, front-to-back rendering order, and horizontal 1D occlusion clipping."
            ),
            category=InvestigationCategory.MULTI_FACT_SYNTHESIS,
            difficulty=InvestigationDifficulty.VERY_HARD,
            contract={"target_entities": ["Binary Space Partitioning"]},
            expected_entities=["Binary Space Partitioning", "John Carmack", "Bruce Naylor"],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=4,
        )
    )

    tasks.append(
        InvestigationTask(
            task_id="inv_task_50_hubble_tension_cosmological_measurements",
            title="Cosmological Tension: Early vs Late Universe Hubble Constant",
            objective=(
                "Synthesize the Hubble constant tension. Contrast the early-universe cosmic microwave background "
                "measurement by Planck (67.4 km/s/Mpc) with the late-universe distance ladder measurement by SH0ES "
                "(73.0 km/s/Mpc) and state the discrepancy."
            ),
            category=InvestigationCategory.MULTI_FACT_SYNTHESIS,
            difficulty=InvestigationDifficulty.VERY_HARD,
            contract={"target_entities": ["Hubble Tension"]},
            expected_entities=["Hubble Tension", "Planck Collaboration", "Adam Riess", "SH0ES"],
            has_contradiction=True,
            expected_epistemic_status="CONTRADICTED",
            min_steps_required=4,
        )
    )

    return tasks


def build_research_accuracy_v3_tasks() -> list[InvestigationTask]:
    """Return the complete 50-task suite for P0.3 Research Accuracy Benchmark."""
    return build_investigation_v1_tasks() + build_p03_benchmark_tasks()


INVESTIGATION_V1_TASKS = build_investigation_v1_tasks()
RESEARCH_ACCURACY_V3_TASKS = build_research_accuracy_v3_tasks()

