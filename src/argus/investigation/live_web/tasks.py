"""Controlled Live-Web Evaluation Tasks (30 Real-World Benchmark Tasks).

Spans 10 foundational research categories:
1. Corporate and organizational facts (3 tasks)
2. Ownership and subsidiary relationships (3 tasks)
3. Historical timelines (3 tasks)
4. Technical and scientific claims (3 tasks)
5. Conflicting claims / disputes (3 tasks)
6. Temporal changes (3 tasks)
7. Multi-hop relationships (3 tasks)
8. Negative findings (3 tasks)
9. Questions requiring multiple sources (3 tasks)
10. Questions where public evidence is insufficient (3 tasks)
"""

from __future__ import annotations

from argus.investigation.live_web.models import LiveWebCategory, LiveWebTask


def build_live_web_tasks() -> list[LiveWebTask]:
    """Build the official 30 reproducible live-web research evaluation tasks."""
    return [
        # ---------------------------------------------------------------------
        # 1. Corporate and Organizational Facts (3 tasks)
        # ---------------------------------------------------------------------
        LiveWebTask(
            task_id="live_task_01_anthropic_founding_leadership",
            title="Anthropic PBC Headquarters and Chief Executive",
            objective="Identify the Chief Executive Officer and global headquarters city of AI safety company Anthropic PBC.",
            category=LiveWebCategory.CORPORATE_ORGANIZATIONAL,
            contract={"target_entities": ["Anthropic"]},
            expected_entities=["Anthropic", "Dario Amodei", "San Francisco"],
            expected_epistemic_status="SUPPORTED",
            expected_answers=["Dario Amodei is CEO", "San Francisco, California"],
        ),
        LiveWebTask(
            task_id="live_task_02_mistral_ai_headquarters",
            title="Mistral AI Headquarters and Founders",
            objective="Identify the headquarters city of Mistral AI and its lead co-founder CEO.",
            category=LiveWebCategory.CORPORATE_ORGANIZATIONAL,
            contract={"target_entities": ["Mistral AI"]},
            expected_entities=["Mistral AI", "Paris", "Arthur Mensch"],
            expected_epistemic_status="SUPPORTED",
            expected_answers=["Paris, France", "Arthur Mensch is CEO"],
        ),
        LiveWebTask(
            task_id="live_task_03_asml_headquarters_ceo",
            title="ASML Holding Global Headquarters",
            objective="Identify the global headquarters municipality of photolithography company ASML Holding.",
            category=LiveWebCategory.CORPORATE_ORGANIZATIONAL,
            contract={"target_entities": ["ASML"]},
            expected_entities=["ASML", "Veldhoven", "Netherlands"],
            expected_epistemic_status="SUPPORTED",
            expected_answers=["Veldhoven, Netherlands"],
        ),

        # ---------------------------------------------------------------------
        # 2. Ownership and Subsidiary Relationships (3 tasks)
        # ---------------------------------------------------------------------
        LiveWebTask(
            task_id="live_task_04_deepmind_parent_company",
            title="Google DeepMind Corporate Ownership",
            objective="Determine the ultimate corporate parent entity that owns artificial intelligence research lab Google DeepMind.",
            category=LiveWebCategory.OWNERSHIP_SUBSIDIARY,
            contract={"target_entities": ["DeepMind", "Google"]},
            expected_entities=["DeepMind", "Alphabet", "Google"],
            expected_epistemic_status="SUPPORTED",
            expected_answers=["Alphabet Inc", "Google LLC"],
        ),
        LiveWebTask(
            task_id="live_task_05_arm_holdings_majority_owner",
            title="Arm Holdings Majority Shareholder",
            objective="Identify the primary institutional/conglomerate majority shareholder of semiconductor architecture designer Arm Holdings.",
            category=LiveWebCategory.OWNERSHIP_SUBSIDIARY,
            contract={"target_entities": ["Arm Holdings"]},
            expected_entities=["Arm Holdings", "SoftBank Group"],
            expected_epistemic_status="SUPPORTED",
            expected_answers=["SoftBank Group Corp"],
        ),
        LiveWebTask(
            task_id="live_task_06_github_parent_acquisition",
            title="GitHub Ownership and Parent Corporation",
            objective="Identify the technology conglomerate that acquired and currently owns developer platform GitHub.",
            category=LiveWebCategory.OWNERSHIP_SUBSIDIARY,
            contract={"target_entities": ["GitHub"]},
            expected_entities=["GitHub", "Microsoft"],
            expected_epistemic_status="SUPPORTED",
            expected_answers=["Microsoft Corporation acquired GitHub in 2018"],
        ),

        # ---------------------------------------------------------------------
        # 3. Historical Timelines (3 tasks)
        # ---------------------------------------------------------------------
        LiveWebTask(
            task_id="live_task_07_apollo_11_lunar_landing_date",
            title="Apollo 11 Lunar Module Touchdown Date",
            objective="Identify the exact calendar date (UTC/EDT) when the Apollo 11 Lunar Module Eagle landed on the Moon.",
            category=LiveWebCategory.HISTORICAL_TIMELINE,
            contract={"target_entities": ["Apollo 11"]},
            expected_entities=["Apollo 11", "July 20, 1969", "Tranquility Base"],
            expected_epistemic_status="SUPPORTED",
            expected_answers=["July 20, 1969"],
        ),
        LiveWebTask(
            task_id="live_task_08_jwst_launch_date",
            title="James Webb Space Telescope Launch Date",
            objective="Determine the launch date of the James Webb Space Telescope (JWST) aboard Ariane 5 from Kourou.",
            category=LiveWebCategory.HISTORICAL_TIMELINE,
            contract={"target_entities": ["James Webb Space Telescope"]},
            expected_entities=["James Webb Space Telescope", "December 25, 2021", "Ariane 5"],
            expected_epistemic_status="SUPPORTED",
            expected_answers=["December 25, 2021"],
        ),
        LiveWebTask(
            task_id="live_task_09_berlin_wall_fall_date",
            title="Fall of the Berlin Wall Date",
            objective="Identify the historic date when the Berlin Wall was opened following Guenter Schabowski's press conference.",
            category=LiveWebCategory.HISTORICAL_TIMELINE,
            contract={"target_entities": ["Berlin Wall"]},
            expected_entities=["Berlin Wall", "November 9, 1989", "East Germany"],
            expected_epistemic_status="SUPPORTED",
            expected_answers=["November 9, 1989"],
        ),

        # ---------------------------------------------------------------------
        # 4. Technical and Scientific Claims (3 tasks)
        # ---------------------------------------------------------------------
        LiveWebTask(
            task_id="live_task_10_speed_of_light_exact_value",
            title="Speed of Light in Vacuum SI Standard Definition",
            objective="State the exact defined numerical value of the speed of light in vacuum in meters per second under SI base units.",
            category=LiveWebCategory.TECHNICAL_SCIENTIFIC,
            contract={"target_entities": ["Speed of Light"]},
            expected_entities=["Speed of Light", "299,792,458 m/s", "SI Unit"],
            expected_epistemic_status="SUPPORTED",
            expected_answers=["299,792,458 meters per second exactly"],
        ),
        LiveWebTask(
            task_id="live_task_11_dna_double_helix_publication",
            title="Watson and Crick DNA Molecular Structure Discovery",
            objective="Identify the journal and publication year in which Watson and Crick proposed the double helix structure of DNA.",
            category=LiveWebCategory.TECHNICAL_SCIENTIFIC,
            contract={"target_entities": ["DNA Double Helix"]},
            expected_entities=["Nature", "1953", "James Watson", "Francis Crick"],
            expected_epistemic_status="SUPPORTED",
            expected_answers=["Nature, published April 25, 1953"],
        ),
        LiveWebTask(
            task_id="live_task_12_avogadro_constant_si_value",
            title="Avogadro Constant Exact SI Definition",
            objective="Identify the exact numerical value of the Avogadro constant N_A defined in the 2019 SI redefinition.",
            category=LiveWebCategory.TECHNICAL_SCIENTIFIC,
            contract={"target_entities": ["Avogadro Constant"]},
            expected_entities=["Avogadro Constant", "6.02214076", "mol^-1"],
            expected_epistemic_status="SUPPORTED",
            expected_answers=["6.02214076 x 10^23 mol^-1"],
        ),

        # ---------------------------------------------------------------------
        # 5. Conflicting Claims / Historical Disputes (3 tasks)
        # ---------------------------------------------------------------------
        LiveWebTask(
            task_id="live_task_13_telephone_invention_dispute",
            title="Telephone Invention Priority Dispute: Bell vs Meucci",
            objective="Investigate historical priority claims for the invention of the telephone between Alexander Graham Bell and Antonio Meucci.",
            category=LiveWebCategory.CONFLICTING_CLAIMS,
            contract={"target_entities": ["Telephone", "Alexander Graham Bell", "Antonio Meucci"]},
            expected_entities=["Alexander Graham Bell", "Antonio Meucci", "Patent 174,465", "Telettrofono"],
            expected_epistemic_status="CONTRADICTED",
            expected_answers=["Conflicting historical dispute over patent priority and caveated inventorship"],
        ),
        LiveWebTask(
            task_id="live_task_14_pluto_planetary_status_reclassification",
            title="Pluto Planetary Classification Dispute",
            objective="Investigate the scientific dispute and 2006 IAU resolution regarding whether Pluto is classified as a planet or dwarf planet.",
            category=LiveWebCategory.CONFLICTING_CLAIMS,
            contract={"target_entities": ["Pluto", "IAU"]},
            expected_entities=["Pluto", "IAU Resolution", "Dwarf Planet", "Cleared Neighborhood"],
            expected_epistemic_status="CONTRADICTED",
            expected_answers=["IAU reclassified Pluto from 9th planet to dwarf planet in 2006; contested by planetary scientists"],
        ),
        LiveWebTask(
            task_id="live_task_15_calculus_priority_dispute_live",
            title="Newton-Leibniz Priority Dispute in Calculus",
            objective="Examine the priority controversy between Isaac Newton and Gottfried Wilhelm Leibniz over the invention of infinitesimal calculus.",
            category=LiveWebCategory.CONFLICTING_CLAIMS,
            contract={"target_entities": ["Calculus", "Isaac Newton", "Gottfried Wilhelm Leibniz"]},
            expected_entities=["Isaac Newton", "Gottfried Wilhelm Leibniz", "Royal Society", "Method of Fluxions"],
            expected_epistemic_status="CONTRADICTED",
            expected_answers=["Independent simultaneous discovery resulting in intense priority dispute"],
        ),

        # ---------------------------------------------------------------------
        # 6. Temporal Changes (3 tasks)
        # ---------------------------------------------------------------------
        LiveWebTask(
            task_id="live_task_16_twitter_rebranding_to_x",
            title="Twitter Corporate Rebranding to X Corp",
            objective="Identify when Twitter was rebranded to X Corp and its iconic blue bird logo replaced.",
            category=LiveWebCategory.TEMPORAL_CHANGE,
            contract={"target_entities": ["Twitter", "X Corp"]},
            expected_entities=["Twitter", "X Corp", "July 2023", "Elon Musk"],
            expected_epistemic_status="SUPPORTED",
            expected_answers=["July 2023 rebranding from Twitter to X"],
        ),
        LiveWebTask(
            task_id="live_task_17_python_2_sunset_date",
            title="Python 2 Official End-of-Life Date",
            objective="Identify the official sunset / end-of-life date for Python 2 declared by the Python Software Foundation.",
            category=LiveWebCategory.TEMPORAL_CHANGE,
            contract={"target_entities": ["Python 2"]},
            expected_entities=["Python 2", "January 1, 2020", "Python Software Foundation"],
            expected_epistemic_status="SUPPORTED",
            expected_answers=["January 1, 2020 EOL date"],
        ),
        LiveWebTask(
            task_id="live_task_18_croatia_eurozone_accession",
            title="Croatia Eurozone Currency Adoption Date",
            objective="Identify the date when the Republic of Croatia adopted the Euro, replacing the Croatian kuna.",
            category=LiveWebCategory.TEMPORAL_CHANGE,
            contract={"target_entities": ["Croatia", "Eurozone"]},
            expected_entities=["Croatia", "January 1, 2023", "Eurozone", "Kuna"],
            expected_epistemic_status="SUPPORTED",
            expected_answers=["January 1, 2023 accession"],
        ),

        # ---------------------------------------------------------------------
        # 7. Multi-Hop Relationships (3 tasks)
        # ---------------------------------------------------------------------
        LiveWebTask(
            task_id="live_task_19_linux_creator_university",
            title="Linus Torvalds Alma Mater and Initial Linux Development",
            objective="Trace Linux: Identify the creator of the Linux kernel and the university where he studied while developing the initial kernel release.",
            category=LiveWebCategory.MULTI_HOP,
            contract={"target_entities": ["Linus Torvalds", "Linux"]},
            expected_entities=["Linus Torvalds", "University of Helsinki", "1991"],
            expected_epistemic_status="SUPPORTED",
            expected_answers=["Linus Torvalds studied at University of Helsinki"],
        ),
        LiveWebTask(
            task_id="live_task_20_cern_lhc_higgs_announcement",
            title="Higgs Boson Discovery Facility and Spokespersons",
            objective="Identify the particle physics laboratory and the two major LHC experiments that jointly announced discovery of the Higgs boson in 2012.",
            category=LiveWebCategory.MULTI_HOP,
            contract={"target_entities": ["Higgs Boson", "CERN"]},
            expected_entities=["CERN", "ATLAS", "CMS", "July 4, 2012"],
            expected_epistemic_status="SUPPORTED",
            expected_answers=["CERN Large Hadron Collider, ATLAS and CMS experiments"],
        ),
        LiveWebTask(
            task_id="live_task_21_turing_award_named_after_alan_turing",
            title="ACM A.M. Turing Award Origins",
            objective="Identify the computing association that administers the A.M. Turing Award and the British cryptanalyst/mathematician after whom it is named.",
            category=LiveWebCategory.MULTI_HOP,
            contract={"target_entities": ["Turing Award"]},
            expected_entities=["Association for Computing Machinery", "ACM", "Alan Turing", "Bletchley Park"],
            expected_epistemic_status="SUPPORTED",
            expected_answers=["Association for Computing Machinery (ACM), named after Alan Turing"],
        ),

        # ---------------------------------------------------------------------
        # 8. Negative Findings (3 tasks)
        # ---------------------------------------------------------------------
        LiveWebTask(
            task_id="live_task_22_neg_atlantis_quantum_hyperchips",
            title="Negative Verification: Atlantis Quantum Hyperchips Inc",
            objective="Investigate whether 'Atlantis Quantum Hyperchips Inc' exists as a registered semiconductor fab producing 1-angstrom processors.",
            category=LiveWebCategory.NEGATIVE_FINDINGS,
            contract={"target_entities": ["Atlantis Quantum Hyperchips Inc"]},
            expected_entities=[],
            expected_epistemic_status="NOT_FOUND",
            expected_answers=["Entity does not exist in corporate registers or verified technical databases"],
        ),
        LiveWebTask(
            task_id="live_task_23_neg_nasa_warp_drive_starship",
            title="Negative Verification: NASA Warp Drive Starship Commissioning",
            objective="Investigate claims that NASA commissioned an operational faster-than-light warp drive starship called 'USS Alcubierre One' in 2024.",
            category=LiveWebCategory.NEGATIVE_FINDINGS,
            contract={"target_entities": ["USS Alcubierre One"]},
            expected_entities=[],
            expected_epistemic_status="NOT_FOUND",
            expected_answers=["No operational FTL starship exists or has been commissioned by NASA"],
        ),
        LiveWebTask(
            task_id="live_task_24_neg_microsoft_acquisition_linux_foundation",
            title="Negative Verification: Microsoft 100% Acquisition of Linux Foundation",
            objective="Verify whether Microsoft Corporation acquired full legal ownership of the non-profit Linux Foundation.",
            category=LiveWebCategory.NEGATIVE_FINDINGS,
            contract={"target_entities": ["Linux Foundation", "Microsoft"]},
            expected_entities=[],
            expected_epistemic_status="NOT_FOUND",
            expected_answers=["Linux Foundation remains an independent 501(c)(6) non-profit consortium; no acquisition occurred"],
        ),

        # ---------------------------------------------------------------------
        # 9. Questions Requiring Multiple Sources (3 tasks)
        # ---------------------------------------------------------------------
        LiveWebTask(
            task_id="live_task_25_nobel_physics_2023_laureates",
            title="2023 Nobel Prize in Physics Laureates Multi-Source Corroboration",
            objective="Identify all three joint recipients of the 2023 Nobel Prize in Physics for attosecond pulse generation.",
            category=LiveWebCategory.MULTI_SOURCE_SYNTHESIS,
            contract={"target_entities": ["Nobel Prize in Physics 2023"]},
            expected_entities=["Pierre Agostini", "Ferenc Krausz", "Anne L'Huillier", "Attosecond"],
            expected_epistemic_status="SUPPORTED",
            expected_answers=["Pierre Agostini, Ferenc Krausz, and Anne L'Huillier"],
        ),
        LiveWebTask(
            task_id="live_task_26_iss_international_partner_agencies",
            title="International Space Station Five Lead Space Agencies",
            objective="Identify the five primary multilateral space agencies participating in the International Space Station intergovernmental agreement.",
            category=LiveWebCategory.MULTI_SOURCE_SYNTHESIS,
            contract={"target_entities": ["International Space Station"]},
            expected_entities=["NASA", "Roscosmos", "ESA", "JAXA", "CSA"],
            expected_epistemic_status="SUPPORTED",
            expected_answers=["NASA (USA), Roscosmos (Russia), ESA (Europe), JAXA (Japan), CSA (Canada)"],
        ),
        LiveWebTask(
            task_id="live_task_27_g7_member_nations_synthesis",
            title="Group of Seven (G7) Member Nations Multi-Source Validation",
            objective="List the member nations comprising the Group of Seven (G7) intergovernmental political forum.",
            category=LiveWebCategory.MULTI_SOURCE_SYNTHESIS,
            contract={"target_entities": ["G7"]},
            expected_entities=["United States", "United Kingdom", "France", "Germany", "Japan", "Italy", "Canada"],
            expected_epistemic_status="SUPPORTED",
            expected_answers=["Canada, France, Germany, Italy, Japan, United Kingdom, United States"],
        ),

        # ---------------------------------------------------------------------
        # 10. Questions Where Public Evidence is Insufficient (3 tasks)
        # ---------------------------------------------------------------------
        LiveWebTask(
            task_id="live_task_28_insuff_gemini_training_cluster_topology",
            title="Insufficient Public Evidence: Undisclosed Gemini Training Interconnect Topology",
            objective="Investigate the proprietary, non-public physical fiber topology and undisclosed optical switch fabric secrets inside Google TPU v5e data halls.",
            category=LiveWebCategory.INSUFFICIENT_PUBLIC_EVIDENCE,
            contract={"target_entities": ["Gemini Training Cluster"]},
            expected_entities=["Gemini", "TPU v5e"],
            expected_epistemic_status="INSUFFICIENT_EVIDENCE",
            expected_answers=["Proprietary confidential trade secret; public documentation is insufficient to establish topology details"],
        ),
        LiveWebTask(
            task_id="live_task_29_insuff_exact_voyager_1_memory_dump_hex",
            title="Insufficient Evidence: Real-Time Voyager 1 Flight Computer Hex Dump",
            objective="Retrieve the full real-time raw hex binary memory dump of Voyager 1's Flight Data Subsystem (FDS) memory module as of today.",
            category=LiveWebCategory.INSUFFICIENT_PUBLIC_EVIDENCE,
            contract={"target_entities": ["Voyager 1 FDS"]},
            expected_entities=["Voyager 1", "Flight Data System"],
            expected_epistemic_status="INSUFFICIENT_EVIDENCE",
            expected_answers=["Raw real-time telemetry dumps are internal JPL operational data not publicly exposed as a full live memory stream"],
        ),
        LiveWebTask(
            task_id="live_task_30_insuff_deepseek_v3_internal_dataset_ratios",
            title="Insufficient Evidence: Exact Undisclosed Pretraining Mixture Ratios for DeepSeek-V3",
            objective="Determine the exact proprietary token percentage breakdown of private commercial corpora used in DeepSeek-V3 pretraining dataset.",
            category=LiveWebCategory.INSUFFICIENT_PUBLIC_EVIDENCE,
            contract={"target_entities": ["DeepSeek-V3"]},
            expected_entities=["DeepSeek-V3"],
            expected_epistemic_status="INSUFFICIENT_EVIDENCE",
            expected_answers=["Pretraining technical report provides high-level categories but withholds proprietary dataset mixture ratios"],
        ),
    ]
