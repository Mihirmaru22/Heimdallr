"""Generalization Benchmark V2: Dedicated Frozen Corpus for 100 Tasks.

Provides realistic synthetic documents covering all 100 tasks across the 8 categories:
- Category A: Unseen entities and organizations (tasks 1-15)
- Category B: Multi-hop relationships (tasks 16-30)
- Category C: Contradictory evidence (tasks 31-45)
- Category D: Insufficient evidence and negative findings (tasks 46-60)
- Category E: Scientific and technical research (tasks 61-75)
- Category F: Historical and temporal reasoning (tasks 76-85)
- Category G: Adversarial and misleading evidence (tasks 86-95)
- Category H: Cross-domain synthesis (tasks 96-100)
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class InvestigationDocument:
    doc_id: str
    title: str
    url: str
    text_content: str
    source_type: str
    published_date: str | None = None
    syndication_cluster_id: str | None = None


def build_generalization_v2_corpus() -> dict[str, InvestigationDocument]:
    """Build unified synthetic corpus for all 100 Generalization V2 tasks."""
    docs: dict[str, InvestigationDocument] = {}

    def add(doc_id: str, title: str, url: str, text: str, source_type: str, date: str | None = None, cluster: str | None = None) -> None:
        docs[doc_id] = InvestigationDocument(
            doc_id=doc_id,
            title=title,
            url=url,
            text_content=text.strip(),
            source_type=source_type,
            published_date=date,
            syndication_cluster_id=cluster,
        )

    # -------------------------------------------------------------------------
    # Category A: Unseen Entities (Tasks 1-15)
    # -------------------------------------------------------------------------
    # Task 1: Kuka Dynamics AG
    add("gen2_doc_01_a", "Kuka Dynamics AG Commercial Register Entry", "https://handelsregister.de/kuka-dynamics-ag",
        "Commercial Register of Munich, HRB 241908: Kuka Dynamics AG was established in Munich, Bavaria. Executive Founder and Chief Executive Officer: Dr. Gerhard Kraus. The enterprise specializes in high-payload industrial robotics, centering on its flagship Titan-6 Arm articulated manipulator platform.",
        "regulatory_filing", "2021-04-12")
    add("gen2_doc_01_b", "Robotics Today Profile: Kuka Dynamics AG Titan-6 Arm", "https://roboticstoday.org/reviews/titan-6-arm",
        "Munich-based robotics innovator Kuka Dynamics AG, led by Dr. Gerhard Kraus, has unveiled the Titan-6 Arm. Designed for heavy industrial manufacturing, the articulated manipulator operates with sub-millimeter positional repeatability across automotive assembly plants.",
        "industry_journal", "2022-09-18")

    # Task 2: Aethelgard Biomedical
    add("gen2_doc_02_a", "Aethelgard Biomedical Lead Oncology Candidate", "https://aethelgard-bio.com/pipeline/aet-401",
        "Aethelgard Biomedical Research Pipeline: Lead oncology molecule AET-401 is a selective antibody-drug conjugate targeting Trop-2 overexpressing epithelial tumors. Currently advancing in Phase II clinical evaluations across European medical centers.",
        "company_disclosure", "2023-01-15")
    add("gen2_doc_02_b", "European Oncology Trials: Trop-2 ADC AET-401", "https://clinicaltrials.eu/record/AET-401",
        "Clinical study evaluation for Aethelgard Biomedical's lead compound AET-401. Mechanism: Humanized anti-Trop-2 monoclonal antibody conjugated to a topoisomerase I inhibitor payload. Phase II trials ongoing.",
        "clinical_trial_registry", "2023-06-20")

    # Task 3: Onyx Hypercomputing
    add("gen2_doc_03_a", "Onyx Hypercomputing Unveils Helios-64 Processor", "https://onyx-hyper.tech/press/helios-64-announcement",
        "Onyx Hypercomputing Corporation has officially deployed its Helios-64 superconducting quantum computing processor. Operating at 15 millikelvin inside BlueFors dilution refrigerators, the quantum processor is driven by the proprietary Q-Kernel control operating environment.",
        "company_press_release", "2023-11-04")
    add("gen2_doc_03_b", "Quantum Systems Review: Onyx Helios-64 Architecture", "https://quantumsystems.org/onyx-helios64-benchmarks",
        "Onyx Hypercomputing's Helios-64 processor features 64 transmon qubits cooled by specialized BlueFors cryogenic hardware and sequenced via the low-latency Q-Kernel real-time pulse controller.",
        "technical_whitepaper", "2024-02-10")

    # Task 4: Valerius & Thorne Maritime
    add("gen2_doc_04_a", "Valerius & Thorne Maritime Registry Details", "https://singaporemaritime.gov.sg/registry/valerius-thorne",
        "Port Authority of Singapore Commercial Fleet Registry: Valerius & Thorne Maritime operates international deep-sea bulk cargo carriers out of its registered operational headquarters in Singapore. Senior Fleet Director: Captain Ronald Hastings.",
        "port_registry", "2022-08-30")

    # Task 5: Quasar Photovoltaics
    add("gen2_doc_05_a", "Quasar Photovoltaics Perovskite-Silicon Tandem Milestone", "https://fraunhofer-ise.de/calibrations/quasar-pv-2023",
        "Fraunhofer Institute for Solar Energy Systems CalLab: Certified performance measurement of Quasar Photovoltaics tandem solar cells fabricated at the Dresden Pilot Line. Achieved a certified conversion efficiency of 31.4% Efficiency under standard AM1.5G testing conditions.",
        "laboratory_certification", "2023-10-14")

    # Task 6: Solaria Aerospace
    add("gen2_doc_06_a", "Solaria Aerospace Aurora-1 Suborbital Launch System", "https://solaria-aero.com/aurora-1-specifications",
        "Solaria Aerospace has completed structural validation of Aurora-1, a lightweight suborbital sounding launch vehicle. Chief Aerostructures Engineer Hélène Marchand confirmed that the primary fuselage structure utilizes specialized Toray Carbon composite laminates.",
        "technical_specification", "2023-05-19")

    # Task 7: Zephyr Microgrid Systems
    add("gen2_doc_07_a", "Zephyr Microgrid Gotland Island Energy Storage Commissioning", "https://gotland-energy.se/press/zephyr-microgrid-installation",
        "Zephyr Microgrid Systems has completed installation of a 50 MWh grid stabilization facility on Gotland Island. The installation incorporates stationary Sodium-Ion battery cells integrated with utility-scale Ingeteam bidirectional power conversion inverters.",
        "utility_announcement", "2023-08-22")

    # Task 8: Borealis Genomics
    add("gen2_doc_08_a", "Borealis Genomics Long-Read Sequencing Partnership", "https://oslo-university-hospital.no/research/borealis-genomics-partnership",
        "Oslo University Hospital Clinical Genetics Department has entered a cooperative sequencing initiative with Borealis Genomics. Under Principal Investigator Dr. Astrid Lind, the team is deploying ultra-long nanopore read sequencing for rare inherited cardiopathies.",
        "institutional_bulletin", "2022-11-15")

    # Task 9: Vanguard Micro-Foundry
    add("gen2_doc_09_a", "Vanguard Micro-Foundry Lithography Expansion", "https://hsinchu-sp.gov.tw/companies/vanguard-micro-foundry",
        "Hsinchu Science Park Administrative Bulletin: Vanguard Micro-Foundry has operationalized its dedicated specialty MEMS fabrication cleanrooms. Process chemicals and advanced photoresist formulations are procured under a long-term supply agreement with Mitsui Chemicals.",
        "government_gazette", "2023-03-09")

    # Task 10: Hesperus Autonomous Vehicles
    add("gen2_doc_10_a", "Hesperus Autonomous Heavy Hauler Specifications", "https://hesperus-av.se/heavy-haul/titan-spec",
        "Hesperus Autonomous Vehicles Chief Technology Officer Lars Engstrom unveiled the Hesperus Titan autonomous electric mining truck. Equipped with an 800 kWh liquid-cooled battery pack, the vehicle navigates open-pit mining environments using sensor fusion and multi-lidar arrays.",
        "corporate_announcement", "2023-07-28")

    # Task 11: Oberon Agricultural Genomics
    add("gen2_doc_11_a", "Oberon Genomics Drought Tolerant Cereal Traits", "https://wur.nl/agribio/oberon-genomics-cr-7",
        "Wageningen University Plant Sciences Department: Oberon Agricultural Genomics has validated its CR-7 Allele in diploid barley lines. The genetic locus confers significant drought tolerance and was characterized under lead geneticist Dr. Marcus Thorne.",
        "scientific_release", "2023-04-16")

    # Task 12: Meridia Lithium & Minerals
    add("gen2_doc_12_a", "Meridia Minerals Atacama DLE Demonstration Facility", "https://sernageomin.cl/mining/meridia-salars-pilot",
        "National Geology and Mining Service (Sernageomin), Chile: Meridia Lithium & Minerals has deployed its direct lithium extraction (DLE) adsorption columns at Salar de Maricunga. The technology utilizes proprietary AdsorbX Resin beads to extract lithium chloride brine.",
        "regulatory_notice", "2023-09-02")

    # Task 13: Boreas Cryogenics Ltd
    add("gen2_doc_13_a", "Boreas Cryogenics Pulse Tube Refrigeration Systems", "https://boreas-cryo.co.uk/products/pt-405-cryocooler",
        "Boreas Cryogenics Ltd, based in Oxfordshire, manufactures the PT-405 Cryocooler. Operating on a closed-cycle helium loop, the system delivers 1.5 Watts of cooling power at 4.2 Kelvin without liquid helium consumption.",
        "product_datasheet", "2022-10-11")

    # Task 14: Taranis Cyber Threat Intelligence
    add("gen2_doc_14_a", "Taranis Threat Intelligence Bulletin: BlackScythe Campaign", "https://taranis-intel.eu/threat-briefs/blackscythe-actor",
        "Taranis Cyber Threat Intelligence has published an advisory detailing the BlackScythe threat cluster. Senior Threat Researcher Elena Rostova tracked command-and-control operations back to a custom Rust-based implant dubbed RustStealer.",
        "threat_advisory", "2023-12-01")

    # Task 15: Quasar Nuclear SMR
    add("gen2_doc_15_a", "Quasar Nuclear SMR High-Temperature Gas Reactor Design", "https://iaea.org/smr-database/quasar-smr-100",
        "International Atomic Energy Agency Advanced Reactors Information System: Quasar Nuclear SMR has submitted preliminary licensing documentation for the Quasar-100. The design is a 100 MWe high-temperature gas-cooled reactor employing TRISO Pebble fuel elements and helium coolant.",
        "multilateral_registry", "2024-01-20")

    # -------------------------------------------------------------------------
    # Category B: Multi-Hop Relationships (Tasks 16-30)
    # -------------------------------------------------------------------------
    # Task 16: Astraea Orbital -> Toray Carbon -> Kobe Precision
    add("gen2_doc_16_a", "Astraea Orbital Satellite Subsystem Procurement", "https://astraea-orbital.com/procurement/propulsion-tanks",
        "Astraea Orbital manufactures commercial communications satellites. Propulsion tank pressure vessels are procured from Toray Carbon Composites France.", "procurement_log", "2023-02-11")
    add("gen2_doc_16_b", "Toray Carbon Metallic Liners Sourcing", "https://toray-composites.fr/supply-chain/metallic-liners",
        "Toray Carbon Composites France constructs composite overwrapped pressure vessels (COPV) using lightweight titanium forged liners manufactured exclusively by Kobe Precision Forging Ltd in Hyogo, Japan.", "supplier_specification", "2023-03-05")

    # Task 17: Vespera Automotive -> Northvolt -> Albelmarle
    add("gen2_doc_17_a", "Vespera Automotive Battery Supply Chain", "https://vespera-auto.com/investors/battery-partners",
        "Vespera Automotive equips all high-performance luxury electric sedans with battery cells supplied by Swedish cell manufacturer Northvolt AB from its Skellefteå Gigafactory.", "investor_filing", "2023-04-18")
    add("gen2_doc_17_b", "Northvolt Hydroxide Sourcing Agreement", "https://northvolt.com/press/lithium-hydroxide-albemarle",
        "Northvolt AB has secured battery-grade lithium hydroxide for its European gigafactories under a multi-year master supply agreement with Albemarle Corporation's Kemerton refinery.", "press_release", "2023-05-12")

    # Task 18: Chronos Watchmaking -> Rubis Precision -> Kyocera
    add("gen2_doc_18_a", "Chronos Watchmaking Horological Components", "https://chronos-horology.ch/heritage/escapements",
        "Chronos Watchmaking Haute Horlogerie manufactures mechanical movements featuring synthetic sapphire and ruby pallet jewels fabricated by Rubis Precision SA in Biel/Bienne.", "artisan_profile", "2022-12-04")
    add("gen2_doc_18_b", "Rubis Precision Crystal Boule Supply", "https://rubis-precision.ch/materials/corundum-boules",
        "Rubis Precision SA sources high-purity single-crystal monocrystalline alumina boules exclusively from Kyocera Fineceramics.", "industrial_catalog", "2023-01-22")

    # Task 19: Thalassa Maritime -> Wärtsilä -> MAN Energy
    add("gen2_doc_19_a", "Thalassa Maritime Containership Propulsion Overhaul", "https://thalassa-maritime.gr/fleet/ultra-large-propulsion",
        "Thalassa Maritime has retrofitted its ultra-large container fleet with dual-fuel methanol propulsion systems engineered and integrated by Wärtsilä Marine.", "marine_news", "2023-06-30")
    add("gen2_doc_19_b", "Wärtsilä Methanol Fuel Injector License", "https://wartsila.com/marine/press/dual-fuel-injection-man-collaboration",
        "Wärtsilä Marine dual-fuel conversion systems utilize high-pressure common-rail methanol injection valve modules licensed and manufactured by MAN Energy Solutions in Augsburg.", "technical_bulletin", "2023-07-15")

    # Task 20: Apex Cloud -> Equinix IBX -> Zayo Group
    add("gen2_doc_20_a", "Apex Cloud Infrastructure European Colocation Hub", "https://apex-tech.com/infrastructure/eu-west-interconnect",
        "Apex Cloud Infrastructure deploys core edge routing nodes inside Equinix IBX Data Centers, notably Frankfurt FR2 and Amsterdam AM4 facilities.", "datacenter_report", "2023-08-14")
    add("gen2_doc_20_b", "Equinix Dark Fiber Backbone Interconnect", "https://equinix.com/partners/dark-fiber-zayo",
        "Equinix IBX facilities in Frankfurt and Amsterdam interconnect core customer cages across trans-European routes via high-capacity dark fiber conduit leased from Zayo Group.", "telecom_directory", "2023-09-01")

    # Task 21: Kuka Dynamics -> Harmonic Drive SE -> Nippon Miniature
    add("gen2_doc_21_a", "Kuka Dynamics Titan-6 Joint Gearbox Architecture", "https://kuka-dynamics-ag.de/tech/actuator-gearing",
        "The articulated joints of the Kuka Dynamics Titan-6 Arm rely on zero-backlash strain wave gears supplied by Harmonic Drive SE in Limburg.", "technical_whitepaper", "2023-03-21")
    add("gen2_doc_21_b", "Harmonic Drive Precision Bearings", "https://harmonicdrive.de/suppliers/precision-cross-rollers",
        "Harmonic Drive SE integrates specialized thin-section cross-roller bearings manufactured by Nippon Miniature Bearing (NMB / MinebeaMitsumi) for high radial stiffness.", "supplier_audit", "2023-04-11")

    # Task 22: Solaria Aerospace -> Safran -> Heraeus
    add("gen2_doc_22_a", "Solaria Aerospace Avionics Inertial Navigation", "https://solaria-aero.com/subsystems/inertial-guidance",
        "The guidance unit of Solaria Aerospace Aurora-1 uses ring laser gyro inertial measurement units produced by Safran Electronics & Defense.", "defense_spec", "2023-02-28")
    add("gen2_doc_22_b", "Safran Optical Cavity Glass Ceramics", "https://safran-group.com/photonics/zerodur-substrates",
        "Safran Electronics & Defense sources ultra-low thermal expansion Zerodur optical glass cavity blocks for laser gyros from Heraeus Quarzglas.", "photonics_journal", "2023-03-19")

    # Task 23: Zephyr Microgrid -> Ingeteam -> Infineon
    add("gen2_doc_23_a", "Zephyr Inverter Power Converter Architecture", "https://zephyr-microgrid.com/hardware/ingeteam-converters",
        "Zephyr Microgrid energy storage stations employ Ingeteam Ingecon Sun Power bidirectional inverters for multi-megawatt grid synchronization.", "hardware_review", "2023-05-02")
    add("gen2_doc_23_b", "Ingeteam IGBT Power Module Sourcing", "https://ingeteam.com/components/igbt-stack-primepack",
        "Ingeteam Ingecon utility-scale inverters utilize PrimePACK IGBT power semiconductor modules manufactured by Infineon Technologies in Villach.", "semiconductor_news", "2023-05-29")

    # Task 24: Borealis Genomics -> Oxford Nanopore -> Cambridge Epigenetix
    add("gen2_doc_24_a", "Borealis Sequencing Instrumentation", "https://borealis-genomics.no/technology/promethion-suite",
        "Borealis Genomics conducts high-throughput epigenomic profiling using PromethION 48 sequencing devices supplied by Oxford Nanopore Technologies.", "lab_protocol", "2023-06-12")
    add("gen2_doc_24_b", "Oxford Nanopore Modified Base Chemistry", "https://nanoporetech.com/collaborations/cambridge-epigenetix",
        "Oxford Nanopore Technologies integrates biomolecular enzymatic methylation sequencing kits co-developed with Cambridge Epigenetix (Biomodal).", "biotech_filing", "2023-07-04")

    # Task 25: Vanguard Micro-Foundry -> ASML -> Carl Zeiss SMT
    add("gen2_doc_25_a", "Vanguard Lithography Tooling", "https://vanguard-foundry.tw/facilities/steppers",
        "Vanguard Micro-Foundry operates deep ultraviolet (DUV) immersion lithography step-and-scan equipment provided by ASML Holding.", "foundry_report", "2023-01-30")
    add("gen2_doc_25_b", "ASML Immersion Optics Subsystems", "https://asml.com/technology/optics-zeiss-smt",
        "ASML immersion lithography projection optics systems and illumination lenses are exclusively engineered and fabricated by Carl Zeiss SMT in Oberkochen.", "annual_report", "2023-02-25")

    # Task 26: Quasar Photovoltaics -> Meyer Burger -> Wacker Chemie
    add("gen2_doc_26_a", "Quasar Silicon Heterojunction Cell Equipment", "https://quasar-pv.de/pilot-line/equipment",
        "The Dresden Pilot Line of Quasar Photovoltaics utilizes heterojunction (HJT) diamond wire wafering and PECVD coating equipment manufactured by Meyer Burger Technology.", "pv_magazine", "2023-08-05")
    add("gen2_doc_26_b", "Meyer Burger Solar Ingot Sourcing", "https://meyerburger.com/supply-chain/polysilicon-purity",
        "Meyer Burger Technology sources hyper-pure electronic-grade polysilicon feedstock for wafer manufacturing from Wacker Chemie AG Burghausen.", "chemical_market_report", "2023-08-30")

    # Task 27: Aethelgard Biomedical -> Lonza -> Repligen
    add("gen2_doc_27_a", "Aethelgard ADC Contract Manufacturing", "https://aethelgard-bio.com/manufacturing/cdmo-partnership",
        "Commercial and clinical-grade antibody-drug conjugate batches for AET-401 are produced by contract development and manufacturing organization Lonza Group at its Visp facility.", "cdmo_announcement", "2023-09-14")
    add("gen2_doc_27_b", "Lonza Bioprocess Filtration Membranes", "https://lonza.com/biologics/downstream-repligen-hollow-fiber",
        "Lonza Group downstream purification of monoclonal antibodies utilizes tangential flow hollow-fiber filtration systems supplied by Repligen Corporation.", "bioprocessing_review", "2023-10-02")

    # Task 28: Meridia Minerals -> Veolia Water -> DuPont Water
    add("gen2_doc_28_a", "Meridia Water Recovery and Polishing", "https://meridia-minerals.cl/sustainability/water-treatment",
        "Meridia Lithium & Minerals treats brine discharge and recovers process freshwater through brine concentration systems constructed by Veolia Water Technologies.", "water_tech_journal", "2023-11-10")
    add("gen2_doc_28_b", "Veolia Reverse Osmosis Membrane Elements", "https://veoliawatertechnologies.com/components/dupont-filmtec",
        "Veolia Water Technologies high-recovery industrial desalting plants integrate FilmTec seawater reverse osmosis spiral-wound membrane elements manufactured by DuPont Water Solutions.", "desalination_catalog", "2023-11-28")

    # Task 29: Quasar SMR -> Framatome -> BWX Technologies
    add("gen2_doc_29_a", "Quasar-100 Nuclear Fuel Fabrication", "https://quasar-smr.de/licensing/fuel-supply",
        "Quasar Nuclear SMR has selected Framatome as its lead contractor for TRISO fuel assembly manufacturing and core load integration.", "nuclear_engineering_intl", "2024-01-08")
    add("gen2_doc_29_b", "Framatome TRISO Coated Particle Sourcing", "https://framatome.com/press/bwxt-triso-supply",
        "Framatome sources uranium oxycarbide (UCO) TRISO micro-spheres and coated particle kernels under a long-term supply agreement with BWX Technologies (BWXT).", "defense_nuclear_wire", "2024-01-29")

    # Task 30: Taranis Cyber -> Shodan API -> Censys
    add("gen2_doc_30_a", "Taranis Cyber Attack Surface Reconnaissance", "https://taranis-intel.eu/whitepapers/recon-infrastructure",
        "Taranis Cyber Threat Intelligence utilizes automated telemetry scanning and external attack surface discovery pipelines fed by Shodan Enterprise API feeds.", "cyber_report", "2023-10-19")
    add("gen2_doc_30_b", "Multi-Source Internet Scanner Correlation", "https://cybersec-benchmarks.org/scanning/shodan-censys-fusion",
        "Enterprise intelligence teams correlate external IP exposure findings by cross-referencing Shodan active port probes with Censys Internet Map certificate telemetry.", "infosec_monthly", "2023-11-05")

    # -------------------------------------------------------------------------
    # Category C: Contradictory Evidence (Tasks 31-45)
    # -------------------------------------------------------------------------
    # Task 31: Kuka Dynamics Titan-6 Payload (600 kg PR vs 450 kg ISO certification)
    add("gen2_doc_31_a", "Munich Industrial Gazette: Kuka Unveils 600kg Payload Titan-6", "https://munich-gazette.de/business/kuka-titan-6-600kg",
        "The Munich Industrial Gazette reports that Kuka Dynamics AG has unveiled its Titan-6 robot, claiming an unprecedented maximum payload capacity of 600 kg for automotive sheet handling.", "press_release", "2023-05-10")
    add("gen2_doc_31_b", "TÜV Rheinland CE Type-Examination Certificate Titan-6", "https://tuv.com/certificates/kuka-titan-6-iso10218",
        "Official CE Machinery Directive Certificate: Kuka Dynamics AG Titan-6 Articulated Robot. Maximum certified rated payload capacity under ISO 10218-1 is strictly 450 kg. Continuous operation above 450 kg violates safety certification.", "official_certificate", "2023-07-22")

    # Task 32: Aethelgard Phase II Completion Date (Q3 2024 claim vs Q2 2025 extension)
    add("gen2_doc_32_a", "Biotech Insider: Aethelgard on Track for Q3 2024 Phase II Readout", "https://biotech-insider.com/aethelgard-q3-2024",
        "Biotech Insider reports Aethelgard Biomedical plans to complete primary endpoint evaluations for lead ADC AET-401 by third quarter 2024.", "industry_news", "2023-04-10")
    add("gen2_doc_32_b", "EU Clinical Trials Register: AET-401 Milestone Amendment", "https://clinicaltrialsregister.eu/ctr-search/trial/AET-401-02",
        "Official Registry Update: Study AET-401-02 completion timeline amended. Primary completion date officially extended to Q2 2025 due to biomarker cohort expansion and manufacturing schedule adjustments.", "regulatory_filing", "2023-11-15")

    # Task 33: Quasar Cell Efficiency (35.2% marketing vs 31.4% certified)
    add("gen2_doc_33_a", "Quasar Photovoltaics Marketing Brochure 2024", "https://quasar-pv.de/brochures/breakthrough-efficiency",
        "Quasar Photovoltaics announces world record tandem solar cell efficiency exceeding 35.2% on experimental laboratory samples.", "promotional_brochure", "2024-01-10")
    add("gen2_doc_33_b", "Fraunhofer ISE Certified Calibration Certificate Quasar Tandem", "https://fraunhofer-ise.de/certs/quasar-tandem-31-4",
        "Fraunhofer ISE Certified Test Report: Quasar Photovoltaics perovskite-silicon tandem cell test device under standard 1-sun illumination conditions. Certified steady-state efficiency: 31.4% Efficiency (+- 0.4%). Claims of 35.2% represent uncalibrated instantaneous transient spikes.", "laboratory_certification", "2024-02-01")

    # Task 34: Valerius Fleet Size (85 vessels vs 42 verified)
    add("gen2_doc_34_a", "Global Shipping Forum Post: Valerius & Thorne Massive Fleet", "https://maritime-forum.org/posts/valerius-fleet-expansion",
        "Unverified maritime blog post asserts Valerius & Thorne Maritime now commands an active international commercial fleet of 85 container ships.", "forum_post", "2023-09-12")
    add("gen2_doc_34_b", "Lloyd's List Intelligence Vessel Register: Valerius & Thorne", "https://lloydslistintelligence.com/fleet/valerius-thorne",
        "Official Lloyd's List Register: Valerius & Thorne Maritime operates exactly 42 active commercial vessels (28 bulk carriers, 14 containerships) flying the Singapore flag.", "commercial_register", "2023-10-05")

    # Task 35: Solaria Launch Date (May 2024 vs Nov 2024)
    add("gen2_doc_35_a", "Aerospace Social Media Post: Solaria Aurora-1 May Launch", "https://x.com/aerotech_fan/status/1789234",
        "Social media rumors claim Solaria Aerospace Aurora-1 will execute maiden suborbital flight in May 2024 from Kiruna Spaceport.", "social_media", "2024-02-14")
    add("gen2_doc_35_b", "Swedish Space Corporation Esrange Launch Schedule", "https://sscspace.com/esrange/manifest-2024",
        "Official Esrange Space Center Launch Manifest: Solaria Aerospace Aurora-1 suborbital mission scheduled launch window: November 2024.", "official_manifest", "2024-03-01")

    # Task 36: Zephyr Battery Chemistry (LFP vs Sodium-Ion)
    add("gen2_doc_36_a", "Clean Energy Blog: Zephyr Deploys Gotland LFP Storage", "https://cleanenergyblog.org/zephyr-gotland-lfp",
        "Clean Energy Blog writes that Zephyr Microgrid Systems chose conventional Lithium Iron Phosphate (LFP) cells for the Gotland Island installation.", "blog_post", "2023-09-01")
    add("gen2_doc_36_b", "Gotland Grid Authority Technical Commissioning Dossier", "https://gotland-energy.se/technical/battery-chemistry-filing",
        "Official Utility Dossier: The Zephyr Microgrid Gotland facility employs non-lithium Sodium-Ion battery chemistry, utilizing Prussian blue analogues and hard carbon anodes.", "utility_dossier", "2023-09-25")

    # Task 37: Borealis Sample Size (100k preprint vs 12,450 peer reviewed)
    add("gen2_doc_37_a", "MedRxiv Preprint: Borealis Population Genomics 100k Cohort", "https://medrxiv.org/content/early/2023/borealis-100k",
        "Preprint study abstract proposes statistical projections for a planned multi-center Scandinavian cohort of 100,000 subjects.", "preprint_server", "2023-05-15")
    add("gen2_doc_37_b", "The Lancet Digital Health: Borealis Cardiopathy Study", "https://thelancet.com/journals/landig/article/PIIS2589-7500(23)00142-8",
        "Peer-Reviewed Publication: Borealis Genomics and Oslo University Hospital study analyzed a confirmed sequenced cohort of exactly 12,450 patients. The authors clarify that 100,000 represents a ten-year national biobank projection, not the evaluated study population.", "peer_reviewed_journal", "2023-11-20")

    # Task 38: Vanguard Node (3nm GAA rumor vs 12nm FinFET license)
    add("gen2_doc_38_a", "Semiconductor Rumors: Vanguard Leaping to 3nm GAA", "https://semi-rumors.com/vanguard-3nm-hsinchu",
        "Rumor mills allege Vanguard Micro-Foundry is installing EUV scanners to fabricate 3nm Gate-All-Around nanosheet semiconductors in Hsinchu.", "tech_rumors", "2023-08-11")
    add("gen2_doc_38_b", "Taiwan Ministry of Economic Affairs Environmental Permit: Vanguard", "https://moea.gov.tw/permits/vanguard-fab3-expansion",
        "Official Environmental Impact Assessment: Vanguard Micro-Foundry Hsinchu Fab 3 expansion is approved exclusively for 12nm FinFET and specialty 28nm planar wafer manufacturing using DUV lithography.", "government_permit", "2023-10-18")

    # Task 39: Hesperus Titan Battery (1200 kWh brochure vs 800 kWh TÜV)
    add("gen2_doc_39_a", "Mining Technology Today: Hesperus Titan Boasts 1200 kWh Battery", "https://miningtech.com/equipment/hesperus-titan-1200kwh",
        "Mining Technology Today reports promotional claims that the Hesperus Titan haul truck is fitted with a colossal 1200 kWh battery pack.", "trade_magazine", "2023-09-08")
    add("gen2_doc_39_b", "Kraftfahrt-Bundesamt (KBA) Heavy Vehicle Type Approval: Hesperus Titan", "https://kba.de/type-approval/hesperus-titan-ev",
        "Official Federal Motor Transport Authority Certification: Hesperus Autonomous Vehicles Titan Electric Hauler. Certified installed battery pack nominal capacity is exactly 800 kWh.", "type_approval", "2023-11-02")

    # Task 40: Onyx Helios Qubit Count (128 qubits pitch vs 64 qubits benchmark)
    add("gen2_doc_40_a", "VentureBeat: Onyx Hypercomputing Pitches 128-Qubit System", "https://venturebeat.com/quantum/onyx-pitch-128qubits",
        "Venture capital reports state Onyx Hypercomputing pitch decks tout a 128-qubit quantum processor design under active fabrication.", "venture_news", "2023-10-12")
    add("gen2_doc_40_b", "IEEE Quantum Transactions: Physical Characterization of Helios-64", "https://ieee-quantum.org/papers/onyx-helios64-characterization",
        "Physical measurements on Onyx Hypercomputing's operational cryogenic package confirm a chip layout containing exactly 64 operational transmon qubits. 128 qubits refers to an unmanufactured roadmap simulation.", "scientific_paper", "2024-01-18")

    # Task 41: Meridia Yield (95% PR vs 68% audit)
    add("gen2_doc_41_a", "Mining Weekly: Meridia Claims 95% Lithium Recovery", "https://miningweekly.com/meridia-claims-95-percent-dle",
        "Press reports cite Meridia Lithium claims of achieving 95% direct lithium extraction recovery rates from Maricunga brine.", "mining_weekly", "2023-10-01")
    add("gen2_doc_41_b", "Chilean Mining Ministry Environmental Audit: Maricunga Pilot", "https://minmineria.cl/audits/meridia-maricunga-yield",
        "Independent technical audit conducted by the Ministry of Mining: Measured steady-state lithium recovery for Meridia's AdsorbX resin columns achieved 68% recovery over 90 days continuous flow.", "government_audit", "2023-12-14")

    # Task 42: Boreas Base Temp (10 mK sales vs 85 mK NIST)
    add("gen2_doc_42_a", "Boreas Cryogenics Sales Brochure PT-405", "https://boreas-cryo.co.uk/sales/pt-405-brochure",
        "Brochure claims Boreas PT-405 cryocooler achieves base operating temperatures down to 10 millikelvin.", "sales_brochure", "2023-04-12")
    add("gen2_doc_42_b", "NIST Cryogenic Instrumentation Evaluation Report: PT-405", "https://nist.gov/cryogenics/evaluations/boreas-pt405",
        "National Institute of Standards and Technology Thermal Evaluation: Boreas PT-405 is a 4-Kelvin pulse tube refrigerator with a verified base temperature of 85 mK when fitted with a dilution unit. The unassisted pulse tube base temperature is 3.8 K; 10 mK is physically unachievable with this unit.", "metrology_report", "2023-06-25")

    # Task 43: Taranis Cyber Attribution (APT41 vs Sandworm)
    add("gen2_doc_43_a", "CyberScope Blog: BlackScythe Traced to Chinese APT41", "https://cyberscope.io/blackscythe-apt41-link",
        "CyberScope blog analysis suggests malware compiling patterns point to Chinese espionage group APT41.", "analyst_blog", "2023-11-20")
    add("gen2_doc_43_b", "CISA Advisory AA23-345A: Russian GRU Sandworm Attribution", "https://cisa.gov/news-events/cybersecurity-advisories/aa23-345a",
        "Official CISA, FBI, and NSA Joint Cybersecurity Advisory: The BlackScythe campaign is attributed with high confidence to Russian GRU Main Center for Special Technologies (Sandworm). Tactical infrastructure and cryptographic keys match prior Sandworm toolsets.", "government_advisory", "2023-12-11")

    # Task 44: Oberon Yield Retention (50% PR vs USDA trial no difference)
    add("gen2_doc_44_a", "Oberon Press Release: CR-7 Yield Retention Milestone", "https://oberon-genomics.com/press/cr-7-drought-yield",
        "Oberon Genomics announces that CR-7 modified barley lines demonstrated a 50% yield retention advantage under simulated severe drought conditions.", "corporate_press_release", "2023-05-18")
    add("gen2_doc_44_b", "USDA Agricultural Research Service Field Trial Evaluation", "https://ars.usda.gov/research/trials/oberon-cr7-evaluation",
        "USDA ARS Multi-Site Field Trial: Evaluation of Oberon CR-7 barley lines across arid plots in eastern Washington revealed no statistically significant difference in harvested grain yield compared to unmodified wild-type controls under sustained water deficit.", "usda_trial_report", "2023-09-29")

    # Task 45: Quasar SMR Thermal Rating (300 MWth marketing vs 160 MWth IAEA)
    add("gen2_doc_45_a", "Quasar SMR Commercial Factsheet", "https://quasar-smr.de/factsheet/quasar-100-thermal",
        "Marketing factsheet claims the Quasar-100 SMR delivers 300 MWth of high-grade industrial process heat alongside 100 MWe electrical generation.", "factsheet", "2023-12-05")
    add("gen2_doc_45_b", "IAEA Nuclear Reactor Design Data Sheet: Quasar-100", "https://iaea.org/reactors/quasar-100-datasheet",
        "IAEA Design Specification: Quasar-100 core rated thermal output is exactly 160 MWth. Net electrical output is 65 MWe at 40% thermodynamic thermal efficiency. Claims of 300 MWth violate core thermodynamic heat balance limits.", "iaea_technical_record", "2024-02-05")

    # -------------------------------------------------------------------------
    # Category D: Insufficient Evidence & Negative Findings (Tasks 46-60)
    # -------------------------------------------------------------------------
    # Tasks 46, 48, 50, 52, 54, 56, 58, 60: Pure Negative / Absent from Corpus -> NOT_FOUND
    # We do NOT add documents asserting these fictitious entities/departments exist.
    # If any document mentions them, it explicitly records that no such entity exists.
    add("gen2_doc_negative_registry", "Federal Registry of Fictitious or Dissolved Entities", "https://bundesanzeiger.de/inquiries/nonexistent-entities",
        "Official Inquiry Response: Exhaustive search of commercial registers, patents, and regulatory submissions confirms: Kuka Dynamics Subterranean Mining Division does not exist. Aethelgard Lunar Bioscience does not exist. Quasar Photovoltaics Superconducting Grid License does not exist. Borealis Genomics €500M GDPR fine was never issued. Hesperus Mars Bureau does not exist. Valerius Teleportation Freight does not exist. Solaria Mach 20 Scramjet does not exist.",
        "registry_search_negative", "2024-01-01")

    # Tasks 47, 49, 51, 53, 55, 57, 59: Partial / Fragmentary Evidence -> INSUFFICIENT_EVIDENCE
    add("gen2_doc_47_insuff_room_temp", "Preliminary Observations on Nickelate Thin Films", "https://arxiv.org/abs/2403.99991",
        "Preliminary physics notes: A single four-probe resistivity drop was observed in lanthanum nickelate thin films at 294 K. However, zero resistance could not be sustained, magnetic susceptibility was unmeasurable due to high substrate diamagnetism, and independent reproduction has not been achieved. Evidence for room-temperature superconductivity is inconclusive.",
        "preliminary_note", "2024-03-01")

    add("gen2_doc_49_insuff_taranis_insider", "Cybersecurity Rumor Roundup: Incident 994", "https://infosec-rumors.org/posts/incident-994-taranis",
        "Unconfirmed forum chatter mentions that an employee at Taranis Cyber may have been questioned regarding an internal credential compromise. No formal internal investigation report, police referral, or confirmation has been made public. Details remain completely unverified.",
        "rumor_mill", "2024-01-15")

    add("gen2_doc_51_insuff_meridia_lithium_reserves", "Preliminary Geological Survey: Maricunga North Section", "https://sernageomin.cl/reports/maricunga-north-preliminary",
        "Initial reconnaissance boreholes drilled in the Maricunga North Section showed elevated lithium concentrations in shallow brine. However, no NI 43-101 compliant resource estimation has been conducted, drilling density is inadequate to establish proven reserves, and subsurface hydrology remains unmodeled. Reserve quantities cannot be determined from existing data.",
        "preliminary_reconnaissance", "2023-11-05")

    add("gen2_doc_53_insuff_atlantis", "Aegean Marine Archaeological Survey Fragment 14", "https://aegean-archaeology.gr/surveys/fragment-14",
        "A heavily eroded stone block bearing partial Linear A symbols was recovered off Santorini at 40 meters depth. Epigraphers have translated two characters as 'sea' and 'ruler', but extensive weathering prevents determining whether this refers to a mythic kingdom, a Minoan shipping tax, or a localized temple dedicatory plaque.",
        "archaeological_fragment", "2022-08-19")

    add("gen2_doc_55_insuff_rsa", "Theoretical Computer Science Discussion: Quadratic Forms and Factoring", "https://cstheory.org/discussions/rsa-polytime-claim",
        "An anonymous preprint claimed to reduce integer factorization to finding lattice vectors in polynomial time using a novel heuristic. Subsequent reviews by cryptographers identified an unproven convergence lemma in Section 4. Whether the algorithm terminates in polynomial time or exponential time remains an open question with no rigorous proof.",
        "peer_critique", "2023-10-24")

    add("gen2_doc_57_insuff_sophocles", "Oxyrhynchus Papyri Catalog Addendum: P.Oxy 5691", "https://papyrology.ox.ac.uk/p-oxy-5691-description",
        "A six-line poetic fragment in Attic Greek was identified in uncatalogued cartonnage. The text contains tragic vocabulary consistent with 5th century BCE drama. However, no authorial subscription exists, and meter is equally consistent with Euripidean tragedy, Sophoclean drama, or a 4th-century Hellenistic imitation. Authorship remains undetermined.",
        "papyrological_catalog", "2023-04-12")

    add("gen2_doc_59_insuff_epigenetic", "Laboratory Protocol: Cellular Exposure to Static Magnetic Fields", "https://epigenetics-journal.org/brief-reports/magnetic-fields-prelim",
        "Cultured human dermal fibroblasts were subjected to 7-Tesla static magnetic fields for 48 hours. Microarray analysis showed minor differential expression of five histone methyltransferases. No global demethylation was observed, senescence markers remained unchanged, and organismal aging effects were not investigated. Conclusion on whole-body aging reversal cannot be drawn.",
        "in_vitro_study", "2023-07-17")

    # -------------------------------------------------------------------------
    # Category E: Scientific and Technical Research (Tasks 61-75)
    # -------------------------------------------------------------------------
    # Task 61: Raft Leader Completeness
    add("gen2_doc_61_a", "In Search of an Understandable Consensus Algorithm (Raft)", "https://raft.github.io/raft.pdf",
        "Stanford University Technical Report: Ongaro and Ousterhout prove the Raft Leader Completeness Invariant. If a log entry is committed in a given term, then that entry will be present in the logs of the leaders for all higher-numbered terms. This is guaranteed by the voting rule requiring a candidate's log to be at least as up-to-date as the majority of voters.",
        "foundational_paper", "2014-05-20")

    # Task 62: GaN HEMT Breakdown Physics
    add("gen2_doc_62_a", "Gallium Nitride Power Devices: Breakdown Mechanisms", "https://ieee-edl.org/papers/gan-hemt-breakdown-physics",
        "High-voltage AlGaN/GaN High Electron Mobility Transistors (HEMTs) exhibit off-state breakdown driven primarily by punch-through conduction across the semi-insulating buffer and surface trap-assisted field emission at the gate-drain edge. Surface passivation with silicon nitride (SiNx) effectively suppresses virtual gate trapping and elevates breakdown voltage above 1200 V.",
        "semiconductor_physics", "2023-03-14")

    # Task 63: CRISPR-Cas12a Cleavage Specificity
    add("gen2_doc_63_a", "Molecular Cell: Biochemical Characterization of Cas12a Specificity", "https://cell.com/molecular-cell/cas12a-collateral-cleavage",
        "Unlike SpCas9 which produces blunt double-strand breaks, CRISPR-Cas12a (Cpf1) introduces staggered 5-nucleotide 5' overhangs distal to the PAM site. Upon target RNA-guided DNA binding and cleavage, Cas12a activates non-specific single-stranded DNA (ssDNA) collateral trans-cleavage activity, enabling high-sensitivity diagnostic assays such as DETECTR.",
        "biochemical_journal", "2022-09-08")

    # Task 64: Solid-State Garnet LLZO Dendrite Suppression
    add("gen2_doc_64_a", "Nature Energy: Critical Current Density in Garnet LLZO", "https://nature.com/articles/nenergy-llzo-dendrites",
        "In garnet-type solid electrolyte Li7La3Zr2O12 (LLZO), lithium dendrite propagation at high current densities occurs along intergranular grain boundaries due to electronic conductivity and localized stress concentration. Introducing a thin atomic-layer-deposited (ALD) Al2O3 interfacial lithiophilic layer reduces interfacial resistance to below 2 ohm-cm2 and elevates critical current density above 1.5 mA/cm2.",
        "energy_materials", "2023-06-19")

    # Task 65: WebAssembly Component Model Canonical ABI
    add("gen2_doc_65_a", "WebAssembly Component Model Specification: Canonical ABI", "https://github.com/WebAssembly/component-model/blob/main/design/mvp/CanonicalABI.md",
        "The WebAssembly Component Model Canonical ABI defines the standard mapping between high-level Interface Types (such as strings, records, variants, and lists) and low-level WebAssembly core values (i32, i64, f32, f64). It formalizes lift and lower operations, linear memory allocations via cabi_realloc, and linear memory safety across language boundaries.",
        "specification_document", "2023-10-30")

    # Task 66: Tokamak Quench Protection
    add("gen2_doc_66_a", "Nuclear Fusion: HTS Magnet Quench Detection in Spherical Tokamaks", "https://iopscience.iop.org/article/10.1088/1741-4326/tokamak-quench",
        "High-temperature superconducting (HTS) REBCO tape magnets in advanced fusion tokamaks feature extremely slow normal zone propagation velocities (NZPV) of a few centimeters per second. Consequently, conventional voltage threshold detection is inadequate; optical fiber Rayleigh backscattering and active co-wound Hall sensors are required to trigger quench protection circuits and fast energy extraction dump resistors.",
        "fusion_research", "2023-04-25")

    # Task 67: ZK-SNARKs Groth16 vs PLONK
    add("gen2_doc_67_a", "Cryptology ePrint: Comparative Analysis of Groth16 and PLONK", "https://eprint.iacr.org/2023/comparative-snarks",
        "Groth16 achieves minimal proof sizes (3 group elements) and fast verification (3 pairings) but requires a circuit-specific trusted setup ceremony. In contrast, PLONK employs a universal and updateable structured reference string (SRS) based on Kate-Zaverucha-Goldberg (KZG) polynomial commitments, allowing arbitrary circuits up to a maximum degree without ceremony regeneration.",
        "cryptographic_survey", "2023-08-14")

    # Task 68: Neuromorphic STDP Learning
    add("gen2_doc_68_a", "Frontiers in Neuroscience: Spike-Timing-Dependent Plasticity Mechanics", "https://frontiersin.org/articles/fnins.2023.stdp-mechanics",
        "Spike-Timing-Dependent Plasticity (STDP) governs synaptic weight modification based on the relative arrival times of pre-synaptic and post-synaptic action potentials. Long-term potentiation (LTP) is induced when the pre-synaptic neuron fires shortly before the post-synaptic neuron (positive temporal window), whereas long-term depression (LTD) occurs when post-synaptic firing precedes pre-synaptic activity.",
        "neuroscience_journal", "2023-02-17")

    # Task 69: Direct Air Capture Sorbents
    add("gen2_doc_69_a", "Chemical Reviews: Solid Amine vs Liquid Hydroxide DAC", "https://pubs.acs.org/doi/10.1021/acs.chemrev.dac-sorbents",
        "Direct Air Capture technologies diverge in sorbent thermodynamics: Solid amine-functionalized nanofibrillated cellulose or mesoporous silica sorbents operate via temperature-vacuum swing adsorption (TVSA) regenerating at 80°C to 120°C. In contrast, liquid potassium hydroxide (KOH) contactors require calcination of calcium carbonate (CaCO3) pellets in an oxy-fired kiln at 900°C.",
        "chemical_engineering", "2023-07-22")

    # Task 70: Micro-LED LIFT Mass Transfer
    add("gen2_doc_70_a", "Journal of the Society for Information Display: LIFT for Micro-LEDs", "https://sid.onlinelibrary.wiley.com/doi/10.1002/jsid.microled-lift",
        "Laser-Induced Forward Transfer (LIFT) utilizes pulsed ultraviolet excimer laser irradiation focused through a transparent quartz carrier wafer. Laser ablation of an intermediate dynamic release layer (e.g., polyimide or GaN decomposition) generates localized plasma expansion, propelling microscopic LED dies with positional placement accuracy under 1.5 micrometers.",
        "display_technology", "2023-05-11")

    # Task 71: Photonic MZI Mesh Matrix Multiplication
    add("gen2_doc_71_a", "Nature Photonics: Programmable Mach-Zehnder Interferometer Meshes", "https://nature.com/articles/nphoton.mzi-mesh-computing",
        "Integrated photonic matrix processors employ triangular or rectangular meshes of 2x2 Mach-Zehnder Interferometers (MZIs) based on the Clements and Reck decompositions. Phase shifters configured according to singular value decomposition (SVD) perform arbitrary unitary transformations in analog optical domain with propagation latency determined solely by group velocity of light in silicon waveguides.",
        "photonic_computing", "2023-09-04")

    # Task 72: Abiotic Methane Synthesis via Serpentinization
    add("gen2_doc_72_a", "Geochimica et Cosmochimica Acta: Serpentinization and Sabatier Reactions", "https://sciencedirect.com/science/article/pii/serpentinization-methane",
        "In ultramafic hydrothermal environments such as the Lost City Hydrothermal Field, olivine hydrolysis (serpentinization) generates molecular hydrogen (H2) and magnetite. Subsequent reduction of dissolved inorganic carbon via Fischer-Tropsch-type / Sabatier pathways produces abiotic methane (CH4) characterized by heavy carbon isotope signatures and distinct clumped isotopologue distributions.",
        "geochemistry_paper", "2022-12-18")

    # Task 73: Perovskite Degradation Modes
    add("gen2_doc_73_a", "Advanced Functional Materials: Phase Segregation in Mixed-Halide Perovskites", "https://onlinelibrary.wiley.com/doi/abs/10.1002/adfm.perovskite-halide",
        "Mixed-halide metal perovskite solar cells (e.g., FA0.83Cs0.17Pb(I0.6Br0.4)3) undergo photo-induced halide segregation (the Hoke effect) under continuous illumination. Mobile iodide and bromide ions demix into low-bandgap iodide-rich domains that act as carrier recombination traps, degrading open-circuit voltage.",
        "materials_science", "2023-08-27")

    # Task 74: Rust Tree Borrows vs Stacked Borrows
    add("gen2_doc_74_a", "Ralf Jung & Neven Villani: Tree Borrows - An Alternative Aliasing Model", "https://perso.crans.org/vanille/treebor/tree-borrows.pdf",
        "Tree Borrows re-architects Rust memory aliasing verification by replacing the linear pointer tag stack of Stacked Borrows with a tree of permissions. Permissions transition across states (Reserved, Active, Frozen, Disabled) per pointer, naturally permitting concurrent read re-ordering across sibling references without spurious invalidations.",
        "computer_science_paper", "2023-06-03")

    # Task 75: Gravitational Wave Bands: LIGO vs LISA
    add("gen2_doc_75_a", "Classical and Quantum Gravity: Complementarity of LIGO and LISA", "https://iopscience.iop.org/article/10.1088/1361-6382/gw-bands",
        "Terrestrial interferometers (LIGO, Virgo, KAGRA) operate in the high-frequency band (10 Hz to 10 kHz), sensitive to stellar-mass black hole and neutron star inspirals. In contrast, the space-based Laser Interferometer Space Antenna (LISA) operates in the millihertz band (0.1 mHz to 100 mHz), targeting supermassive black hole binary mergers and extreme mass ratio inspirals (EMRIs).",
        "astrophysics_review", "2023-11-14")

    # -------------------------------------------------------------------------
    # Category F: Historical and Temporal Reasoning (Tasks 76-85)
    # -------------------------------------------------------------------------
    # Task 76: Swiss Federal Council Presidency Rotation 2024
    add("gen2_doc_76_a", "Federal Chancellery of Switzerland: President of the Confederation 2024", "https://admin.ch/gov/en/presidency/2024-viola-amherd",
        "The Federal Assembly of the Swiss Confederation elected Viola Amherd to serve as President of the Swiss Confederation for the calendar year 2024. Karin Keller-Sutter was elected Vice-President. In the Swiss collegial system, the presidency rotates annually among the seven Federal Councilors according to seniority.",
        "official_gazette", "2024-01-01")

    # Task 77: Fall of Tenochtitlan August 1521
    add("gen2_doc_77_a", "Historical Chronicles of New Spain: The Fall of Tenochtitlan", "https://inah.gob.mx/cronicas/caida-tenochtitlan-1521",
        "Following an eighty-day amphibious siege by Spanish forces under Hernan Cortes and indigenous Tlaxcalan allies, the Aztec capital of Tenochtitlan fell on August 13, 1521, marked by the capture of Tlatoani Cuauhtemoc in a canoe on Lake Texcoco.",
        "historical_archive", "2021-08-13")

    # Task 78: NCR Corp Split into Voyix and Atleos 2023
    add("gen2_doc_78_a", "NCR Corporation Form 8-K: Separation and Distribution Complete", "https://sec.gov/edgar/data/NCR-corp-split-voyix-atleos",
        "Securities and Exchange Commission Filing: On October 16, 2023, NCR Corporation completed its planned corporate separation into two independent publicly traded companies: NCR Voyix Corporation (focusing on digital commerce and restaurants) and NCR Atleos Corporation (focusing on ATM banking networks).",
        "regulatory_sec_filing", "2023-10-17")

    # Task 79: Newton vs Leibniz Calculus Priority Dispute
    add("gen2_doc_79_a", "Royal Society Philosophical Transactions: The Commercium Epistolicum", "https://royalsocietypublishing.org/history/calculus-priority-newton-leibniz",
        "Historical mathematical analysis: Isaac Newton developed his method of fluxions privately between 1665 and 1666, circulating manuscripts like De analysi in 1669. Gottfried Wilhelm Leibniz independently developed differential and integral calculus in Paris between 1673 and 1676, publishing his seminal paper Nova Methodus pro Maximis et Minimis in 1684, preceding Newton's first publication (Philosophiae Naturalis Principia Mathematica, 1687).",
        "historical_treatise", "2022-04-10")

    # Task 80: EU GDPR Adoption (2016) vs Application (2018)
    add("gen2_doc_80_a", "Official Journal of the European Union: Regulation (EU) 2016/679", "https://eur-lex.europa.eu/eli/reg/2016/679/oj",
        "Regulation (EU) 2016/679 of the European Parliament and of the Council (General Data Protection Regulation) was adopted on April 27, 2016, and entered into force twenty days after publication. Under Article 99(2), the regulation became directly applicable across all EU member states on May 25, 2018.",
        "statutory_record", "2016-05-04")

    # Task 81: Third Treaty of San Ildefonso 1800
    add("gen2_doc_81_a", "Diplomatic History Archives: Third Treaty of San Ildefonso", "https://diplomatic-archives.gov/treaties/san-ildefonso-1800",
        "Concluded on October 1, 1800, between the French Republic and the Kingdom of Spain, the Third Treaty of San Ildefonso retroceded the territory of Louisiana from Spain to France in exchange for French recognition of the Kingdom of Etruria under the Duke of Parma. This secret agreement preceded the 1803 Louisiana Purchase by the United States.",
        "treaty_collection", "2021-10-01")

    # Task 82: Satya Nadella Appointment as Microsoft CEO 2014
    add("gen2_doc_82_a", "Microsoft News Center: Board of Directors Names Satya Nadella CEO", "https://news.microsoft.com/2014/02/04/satya-nadella-named-ceo",
        "On February 4, 2014, Microsoft Corporation announced that its Board of Directors selected Satya Nadella as Chief Executive Officer, succeeding Steve Ballmer. Simultaneously, Bill Gates stepped down as Chairman to become Technology Advisor, while John Thompson became Chairman of the Board.",
        "official_press_release", "2014-02-04")

    # Task 83: Cassini Titan Orbit vs Huygens Probe Landing 2005
    add("gen2_doc_83_a", "NASA / ESA Mission Chronology: Cassini-Huygens Mission at Saturn", "https://solarsystem.nasa.gov/missions/cassini-huygens/in-depth",
        "The Cassini spacecraft achieved orbit insertion around Saturn on July 1, 2004. The European Space Agency's Huygens probe separated from the orbiter in December 2004 and executed a historic parachute descent through the atmosphere of Titan, successfully landing on the frozen surface on January 14, 2005.",
        "mission_archive", "2020-01-14")

    # Task 84: German Rentenmark Introduction November 1923
    add("gen2_doc_84_a", "Bundesbank Historical Currency Archives: The Stabilization of 1923", "https://bundesbank.de/en/tasks/topics/hyperinflation-rentenmark-1923",
        "To halt hyperinflation following the collapse of the Papiermark, the German government issued a decree on October 15, 1923, establishing the Rentenbank. The Rentenmark was introduced into circulation on November 15, 1923, backed by mortgages on German industrial and agricultural land, successfully stabilizing the currency at an exchange rate of 1 Rentenmark to 1 trillion Papiermark.",
        "monetary_history", "2023-11-15")

    # Task 85: Apple v. Samsung Patent Litigation 2011-2018
    add("gen2_doc_85_a", "United States District Court Northern District of California: Apple v Samsung", "https://cand.uscourts.gov/cases/apple-v-samsung-settlement-2018",
        "Docket 11-cv-01846: Apple Inc. filed suit against Samsung Electronics in April 2011 alleging smartphone utility and design patent infringement. Following a 2012 jury verdict, multiple appeals, and a 2016 US Supreme Court ruling on design patent damages (Samsung v. Apple), the parties reached a final confidential settlement in June 2018, formally terminating the seven-year global dispute.",
        "judicial_record", "2018-06-27")

    # -------------------------------------------------------------------------
    # Category G: Adversarial and Misleading Evidence (Tasks 86-95)
    # -------------------------------------------------------------------------
    # Task 86: Malicious Typosquat colorama-py
    add("gen2_doc_86_a", "PyPI Security Advisory: Malicious Typosquat colorama-py Removed", "https://pypi.org/security/advisories/colorama-py-malware",
        "Security incident report: The package colorama-py was identified as a malicious typosquat of the legitimate terminal styling package colorama. The setup.py of colorama-py contained an obfuscated base64 payload designed to exfiltrate browser credentials to a remote webhook.",
        "security_advisory", "2023-09-17")

    # Task 87: Phishing Domain kuka-dynamik-ag.com (Misleading)
    add("gen2_doc_87_a", "CERT-Bund Warning: Phishing Domain kuka-dynamik-ag.com", "https://cert-bund.de/advisories/phishing-kuka-lookalike",
        "CERT-Bund Threat Warning: The domain kuka-dynamik-ag.com (registered with a 'k' instead of 'cs') is an unauthorized credential-harvesting phishing site targeting German manufacturing suppliers. Legitimate entity is Kuka Dynamics AG operating strictly under kuka-dynamics-ag.de.",
        "cert_warning", "2023-08-04")

    # Task 88: Clickbait Dark Matter Headline
    add("gen2_doc_88_a", "Science Sensational: LUX-ZEPLIN Disproves All Dark Matter Theories!", "https://sciencesensational.com/dark-matter-disproven",
        "Sensational article claiming the LUX-ZEPLIN experiment at Sanford Underground Research Facility has disproven the existence of all dark matter particles in the universe.", "clickbait_news", "2023-07-10")
    add("gen2_doc_88_b", "Physical Review Letters: LUX-ZEPLIN First Science Results", "https://journals.aps.org/prl/abstract/10.1103/PhysRevLett.131.041002",
        "PRL Official Study: LUX-ZEPLIN Collaboration reports initial limits on Weakly Interacting Massive Particles (WIMPs). The experiment set world-leading exclusion limits on spin-independent WIMP-nucleon cross sections above 10 GeV/c2, constraining specific parameter spaces without disproving dark matter.",
        "peer_reviewed_physics", "2023-07-25")

    # Task 89: Incidental Entity Mention (Building Lease)
    add("gen2_doc_89_a", "Munich Commercial Real Estate Directory: Parkstadt Schwabing", "https://munich-offices.de/parkstadt-tenants-directory",
        "Building directory for Marcel-Breuer-Strasse 15, Munich: The 4th floor is leased to software studio AppForge GmbH. The ground-floor cafeteria is managed by Kraus Catering. Kuka Dynamics AG leases server rack storage in basement quadrant B for offsite backups.",
        "directory_listing", "2023-05-30")

    # Task 90: Irrelevant Negation Disavowal
    add("gen2_doc_90_a", "Aethelgard Biomedical Environmental ESG Statement", "https://aethelgard-bio.com/sustainability/esg-2023",
        "In our corporate sustainability audit, Aethelgard Biomedical clarifies that the company has no operations in petroleum refining, coal mining, or chemical weapon synthesis. All activities are confined to biopharmaceutical oncology discovery (AET-401).",
        "corporate_esg", "2023-08-11")

    # Task 91: Adversarial Composite Smear Article
    add("gen2_doc_91_a", "Offshore Leaks Exposé: Fictitious Offshore Accounts of Dr. Gerhard Kraus", "https://anonymous-leaks-blog.org/kraus-tax-haven",
        "An anonymous blog post mixes authentic biographical facts about Dr. Gerhard Kraus with fabricated claims of undisclosed offshore accounts in Vanuatu.", "unverified_blog", "2023-09-03")
    add("gen2_doc_91_b", "German Federal Tax Authority (BZSt) Compliance Clearance", "https://bzst.de/transparency/clearance-kraus-g",
        "Official German tax and regulatory review confirms Dr. Gerhard Kraus has no foreign offshore holdings and has maintained full statutory compliance throughout his tenure at Kuka Dynamics AG.", "regulatory_clearance", "2023-10-15")

    # Task 92: Lookalike Organization Aethelgard Health Solutions Ltd
    add("gen2_doc_92_a", "UK Companies House: Aethelgard Health Solutions Ltd", "https://find-and-update.company-information.service.gov.uk/company/13894012",
        "Companies House London: Aethelgard Health Solutions Ltd is a boutique occupational health physiotherapy consultancy in Leeds, UK. It is completely unaffiliated with Swiss oncology biopharma developer Aethelgard Biomedical.",
        "company_house_record", "2022-02-14")

    # Task 93: Stale Canceled Joint Venture Presented as Active
    add("gen2_doc_93_a", "Archived 2019 Press Release: Solaria Aerospace and SkyVolt JV", "https://archive.org/solaria-skyvolt-2019-jv",
        "March 2019 announcement: Solaria Aerospace and SkyVolt propose joint suborbital electric propulsion demonstrator.", "archived_announcement", "2019-03-12")
    add("gen2_doc_93_b", "Solaria Aerospace 2020 Form 10-Q: Termination of SkyVolt Agreement", "https://solaria-aero.com/sec/termination-skyvolt-jv",
        "Regulatory filing: Notice of mutual termination. The proposed 2019 joint venture with SkyVolt was formally dissolved without capital deployment in January 2020. Solaria retains zero ongoing commercial or technical obligations.", "regulatory_termination", "2020-02-01")

    # Task 94: Discredited Paper Citing Retracted Room-Temp Superconductor
    add("gen2_doc_94_a", "Speculative Electronics: Applying LK-99 to High-Power Inverters", "https://speculative-circuitry.org/lk-99-power-electronics",
        "Article claims revolutionary inverter efficiencies by incorporating lead apatite LK-99 as a room-temperature superconductor.", "speculative_paper", "2023-08-20")
    add("gen2_doc_94_b", "Max Planck Institute for Solid State Research: LK-99 Ferromagnetic Impurity", "https://fkf.mpg.de/press/lk99-rebuttal",
        "Max Planck solid state researchers synthesize pure single-crystal LK-99 without copper sulfide impurities. Confirmed to be an electrical insulator with resistivity of millions of ohms; apparent resistivity drops were caused by Cu2S first-order structural phase transition.",
        "peer_reviewed_rebuttal", "2023-09-10")

    # Task 95: Unicode Homoglyph Attack (zephyr-microgrıd.com with dotless i)
    add("gen2_doc_95_a", "Threat Intelligence Warning: Homoglyph zephyr-microgrıd.com", "https://taranis-intel.eu/advisories/homoglyph-zephyr",
        "Advisory: Domain zephyr-microgrıd.com (punycode xn--zephyr-microgrd-llb.com using Turkish dotless i U+0131) was registered as a deceptive credential-harvesting clone of legitimate Zephyr Microgrid Systems (zephyr-microgrid.com).",
        "threat_advisory", "2023-10-18")

    # -------------------------------------------------------------------------
    # Category H: Cross-Domain Synthesis (Tasks 96-100)
    # -------------------------------------------------------------------------
    # Task 96: ASML EUV Export Restrictions Geopolitics & Physics
    add("gen2_doc_96_a", "Dutch Ministry for Foreign Trade: Ministerial Export Regulations for Advanced Semiconductor Equipment", "https://overheid.nl/export-control/asml-euv-duv-2023",
        "Official Government Gazette of the Netherlands: Ministerial Order updating national export control regulations for advanced immersion DUV and extreme ultraviolet (EUV) photolithography equipment. Export licenses are restricted for deep-UV systems capable of dedicated advanced lithographic node manufacturing under Wassenaar Arrangement category 3B001.",
        "statutory_export_order", "2023-07-04")
    add("gen2_doc_96_b", "Physics of Extreme Ultraviolet Lithography Light Sources", "https://asml.com/technology/euv-plasma-physics",
        "ASML EUV lithography systems operate at an extreme ultraviolet wavelength of 13.5 nanometers. High-power CO2 laser pulses vaporize molten tin droplets at 50,000 Hertz, generating high-density tin plasma radiating EUV photons collected by multilayer Mo/Si Bragg mirrors under ultra-high vacuum.",
        "physics_whitepaper", "2023-08-15")

    # Task 97: IUU Fishing Marine Biology & Radar Tracking of Dark Vessels
    add("gen2_doc_97_a", "Global Fishing Watch: Synthetic Aperture Radar Detection of Dark Fleets", "https://globalfishingwatch.org/research/sar-dark-vessel-detection",
        "By fusing Sentinel-1 Synthetic Aperture Radar (SAR) imagery with Automatic Identification System (AIS) transponder broadcast logs, maritime analysts detect 'dark vessels' operating with disabled AIS beacons in Marine Protected Areas.",
        "satellite_monitoring_report", "2023-05-18")
    add("gen2_doc_97_b", "Marine Ecology Progress Series: Apex Predator Trophic Cascade", "https://int-res.com/abstracts/meps/v680/p101-118",
        "Overfishing of pelagic shark populations and toothfish by illegal, unreported, and unregulated (IUU) industrial longline fleets precipitates a top-down trophic cascade, leading to mesopredator release and collapse of benthic reef biodiversity.",
        "marine_ecology_paper", "2023-06-22")

    # Task 98: Sodium-Ion vs LFP Battery Grid Economics & Chemistry
    add("gen2_doc_98_a", "Journal of Power Sources: Cathode Chemistry of Sodium-Ion vs LFP", "https://sciencedirect.com/science/article/pii/sodium-vs-lfp-chemistry",
        "Sodium-ion batteries utilizing Prussian white (Na2-xFe[Fe(CN)6]) or layered oxide cathodes eliminate dependence on scarce lithium, nickel, and cobalt. While theoretical volumetric energy density (160 Wh/L) is lower than Lithium Iron Phosphate (LiFePO4, 300 Wh/L), sodium cells exhibit superior low-temperature discharge retention down to -20°C and aluminum current collectors at both electrodes.",
        "electrochemistry_journal", "2023-04-14")
    add("gen2_doc_98_b", "BloombergNEF: Levelized Cost of Storage for Long-Duration Stationary Batteries", "https://bnef.com/insights/lcos-sodium-vs-lithium-2024",
        "Economic analysis: The levelized cost of storage (LCOS) for utility-scale sodium-ion systems achieves parity with LFP when lithium carbonate prices exceed $15,000/ton, offering a cost-resilient hedge for 4-to-8 hour stationary grid energy storage.",
        "financial_energy_report", "2023-11-20")

    # Task 99: EU AI Act Article 15 & Foundation Model Cybersecurity
    add("gen2_doc_99_a", "Official Journal of the European Union: EU Artificial Intelligence Act", "https://eur-lex.europa.eu/eli/reg/2024/1689/oj",
        "Regulation (EU) 2024/1689, Article 15 (Accuracy, Robustness and Cybersecurity): High-risk AI systems and general-purpose AI models with systemic risk shall be designed and developed to achieve an appropriate level of resilience against errors, faults, and adversarial vulnerabilities, including prompt injection, data poisoning, and model evasion attacks.",
        "statutory_regulation", "2024-07-12")
    add("gen2_doc_99_b", "ENISA Guidelines on Securing Machine Learning Pipelines", "https://enisa.europa.eu/publications/securing-foundation-models",
        "European Union Agency for Cybersecurity (ENISA) Technical Guide: Implementing Article 15 requirements for foundation models requires continuous adversarial robustness testing, red-teaming for gradient-based evasion, and strict provenance verification throughout training data supply chains.",
        "cybersecurity_guideline", "2024-08-01")

    # Task 100: Viral Pathogen Biosecurity & Air Transport Physics
    add("gen2_doc_100_a", "WHO Guidance on Regulations for the Transport of Infectious Substances", "https://who.int/publications/i/item/9789240012577",
        "World Health Organization Guidance: Transport of Category A Infectious Substances (UN 2814, affecting humans) requires mandatory triple packaging consisting of a primary leak-proof receptacle, a secondary leak-proof packaging containing absorbent material, and a rigid outer packaging tested to withstand drops from 9 meters and internal pressure differentials of 95 kPa.",
        "biosecurity_standard", "2021-02-15")
    add("gen2_doc_100_b", "IATA Dangerous Goods Regulations: Dry Ice Sublimation in Cargo Aircraft", "https://iata.org/en/programs/cargo/dgr/dry-ice-transport",
        "International Air Transport Association (IATA) Dangerous Goods Manual, Class 9 / Class 6.2 compatibility: Dry ice (carbon dioxide solid, UN 1845) used for cryogenic biosecurity transport sublimates at a nominal rate of 1% to 2% per hour. Aircraft environmental control systems must maintain minimum fresh air ventilation rates to prevent cabin CO2 concentration from exceeding regulatory occupational limits (0.5% / 5000 ppm).",
        "aviation_safety_standard", "2023-01-10")

    return docs


class InvestigationCorpusRegistryV2:
    """Corpus Registry for Generalization Benchmark V2."""

    def __init__(self, docs: dict[str, InvestigationDocument] | None = None) -> None:
        self.documents: dict[str, InvestigationDocument] = docs if docs is not None else build_generalization_v2_corpus()
        self.doc_by_id: dict[str, InvestigationDocument] = {d.doc_id: d for d in self.documents.values()}
        self._discoverable_entities: set[str] = set()
        self._populate_entities()

    def _populate_entities(self) -> None:
        from argus.investigation.benchmark.v2.tasks import build_generalization_v2_tasks
        tasks = build_generalization_v2_tasks()
        for task in tasks:
            for ent in task.expected_entities:
                self._discoverable_entities.add(ent)
            if task.contract and "target_entities" in task.contract:
                for ent in task.contract["target_entities"]:
                    self._discoverable_entities.add(ent)

    def register_discoverable_entity(self, entity: str) -> None:
        if entity:
            self._discoverable_entities.add(entity)

    def get_discoverable_entities(self) -> set[str]:
        return set(self._discoverable_entities)

    def search(self, query: str, limit: int = 10) -> list[InvestigationDocument]:
        """Search documents using exact matching, token overlap, and title boosting."""
        clean_q = query.replace('"', "").replace("'", "")
        tokens = [t.lower() for t in re.split(r"[\s,;:\.\?\(\)\[\]\-]+", clean_q) if len(t) > 2]
        scored_docs: list[tuple[float, InvestigationDocument]] = []

        for doc in self.documents.values():
            score = 0.0
            doc_text_lower = doc.text_content.lower()
            doc_title_lower = doc.title.lower()

            # Exact query match boost
            if clean_q.lower() in doc_text_lower:
                score += 6.0
            if clean_q.lower() in doc_title_lower:
                score += 10.0

            # Token overlap score
            for t in tokens:
                if t in doc_title_lower:
                    score += 2.5
                if t in doc_text_lower:
                    score += 0.8

            if score > 0:
                scored_docs.append((score, doc))

        scored_docs.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in scored_docs[:limit]]
