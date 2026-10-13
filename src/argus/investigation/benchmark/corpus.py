"""Heimdallr V2: Dedicated Frozen Benchmark Corpus for EVAL_INVESTIGATION_V1.

Contains realistic synthetic documents for 25 investigations:
- Multi-tier technology conglomerate (Apex Technologies Group / NovaCorp)
- Complete 20-executive leadership roster with varied contact, tenure, and title statuses
- Contradictory press releases vs 10-K filings
- Stale executive profiles vs active regulatory filings
- Historical tenure archives (2018-2024)
- Network infrastructure, CT logs, and OSINT profiles
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class InvestigationDocument:
    doc_id: str
    title: str
    url: str
    text_content: str
    source_type: str
    published_date: str | None = None
    syndication_cluster_id: str | None = None


# ---------------------------------------------------------------------------
# The 20-Executive Leadership Roster Documents (Apex Technologies Group)
# ---------------------------------------------------------------------------
APEX_20_EXECUTIVES = [
    {
        "name": "Sarah Lin",
        "title": "Senior Vice President, Cloud Infrastructure",
        "responsibility": "Hyperscale data center operations, distributed cloud computing",
        "org": "Apex Technologies Group",
        "email": "slin-ops@apex-tech.com",  # Public documented contact
        "status": "SUPPORTED",
        "history": "Former VP of Engineering at CloudMatrix (2018-2021). Appointed SVP in 2022.",
    },
    {
        "name": "David Marcus",
        "title": "Senior Vice President, Machine Learning & AI",
        "responsibility": "Foundation model architecture, LLM alignment, research lab",
        "org": "Apex Technologies Group",
        "email": "dmarcus-research@apex-tech.com",
        "status": "SUPPORTED",
        "history": "PhD in Computer Science from Stanford. Director of AI Research at NeuralCore (2016-2020).",
    },
    {
        "name": "Elena Rostova",
        "title": "Vice President, Hardware Systems Architecture",
        "responsibility": "Custom silicon, TPU accelerators, hardware firmware",
        "org": "Apex Technologies Group",
        "email": None,  # NOT_FOUND contact!
        "status": "SUPPORTED",
        "history": "Lead chip architect at SiliconWorks. Joined Apex in 2019.",
    },
    {
        "name": "Marcus Vance",
        "title": "Vice President, Global Supply Chain",
        "responsibility": "Component procurement, assembly logistics in East Asia",
        "org": "Apex Technologies Group",
        "email": "m.vance@apex-tech.com",
        "status": "SUPPORTED",
        "history": "Director of Supply Chain at GlobalElectronics (2015-2020).",
    },
    {
        "name": "Rachel Thorne",
        "title": "Senior Vice President, Security Engineering",
        "responsibility": "Chief Information Security Office, identity protection, cryptography",
        "org": "Apex Technologies Group",
        "email": "security-office@apex-tech.com",
        "status": "SUPPORTED",
        "history": "CISO at Cyberspace Defense Corp. Appointed SVP Security in 2021.",
    },
    {
        "name": "Julian Chen",
        "title": "Vice President, Developer Platforms",
        "responsibility": "Developer APIs, SDK ecosystem, open-source tooling",
        "org": "Apex Technologies Group",
        "email": None,
        "status": "SUPPORTED",
        "history": "Co-founder of DevHub (acquired 2020).",
    },
    {
        "name": "Amina Al-Mansoor",
        "title": "Vice President, Autonomous Mobility Systems",
        "responsibility": "Computer vision, robotics perception, automotive AI stack",
        "org": "Apex Technologies Group",
        "email": "mobility-press@apex-tech.com",
        "status": "SUPPORTED",
        "history": "Research scientist at MIT CSAIL. VP since 2023.",
    },
    {
        "name": "Tobias Richter",
        "title": "Vice President, European Regulatory Operations",
        "responsibility": "GDPR compliance, EU AI Act adherence, European headquarters",
        "org": "Apex Technologies Europe Ltd",
        "email": "t.richter@apex-europe.de",
        "status": "SUPPORTED",
        "history": "Director of Public Policy in Brussels (2017-2022).",
    },
    {
        "name": "Chloe Bennett",
        "title": "Vice President, Consumer Applications",
        "responsibility": "Desktop operating system, mobile consumer application suite",
        "org": "Apex Technologies Group",
        "email": None,
        "status": "SUPPORTED",
        "history": "Product Lead at SocialConnect (2016-2021).",
    },
    {
        "name": "Dr. Kenji Sato",
        "title": "Senior Vice President, Quantum Research Labs",
        "responsibility": "Cryogenic qubit architectures, quantum error correction",
        "org": "Apex Technologies Group",
        "email": "ksato-quantum@apex-tech.com",
        "status": "SUPPORTED",
        "history": "Professor of Applied Physics at University of Tokyo. Joined Apex 2018.",
    },
    {
        "name": "Vikram Patel",
        "title": "Vice President, Financial Technology & Payments",
        "responsibility": "Digital wallet infrastructure, PCI compliance, merchant APIs",
        "org": "Apex Technologies Group",
        "email": None,
        "status": "SUPPORTED",
        "history": "VP Engineering at PayFast Global.",
    },
    {
        "name": "Sofia Rodriguez",
        "title": "Vice President, People & Engineering Culture",
        "responsibility": "Technical recruiting, organizational scaling, executive coaching",
        "org": "Apex Technologies Group",
        "email": "srodriguez-talent@apex-tech.com",
        "status": "SUPPORTED",
        "history": "VP HR at TalentScale International.",
    },
    {
        "name": "Arthur Pendelton",
        "title": "Senior Vice President, General Counsel",
        "responsibility": "Securities law, IP patent portfolio, antitrust compliance",
        "org": "Apex Technologies Group",
        "email": "legal@apex-tech.com",
        "status": "SUPPORTED",
        "history": "Partner at Morrison & Foerster LLP. Appointed General Counsel 2017.",
    },
    {
        "name": "Nadia O'Connor",
        "title": "Vice President, User Experience & Design",
        "responsibility": "Design systems, accessibility compliance, visual aesthetics",
        "org": "Apex Technologies Group",
        "email": None,
        "status": "SUPPORTED",
        "history": "Chief Design Officer at StudioModern.",
    },
    {
        "name": "Liam Gallagher",
        "title": "Vice President, Global Communications & Media",
        "responsibility": "Corporate PR, crisis management, executive press briefings",
        "org": "Apex Technologies Group",
        "email": "press@apex-tech.com",
        "status": "SUPPORTED",
        "history": "Head of PR at GlobalTech Alliance.",
    },
    {
        "name": "Ingrid Lindstrom",
        "title": "Vice President, Sustainable Energy & Green Data Centers",
        "responsibility": "Carbon-neutral energy procurement, liquid cooling R&D",
        "org": "Apex Technologies Group",
        "email": None,
        "status": "SUPPORTED",
        "history": "Director of Clean Energy at NordicPower.",
    },
    {
        "name": "Zackary Taylor",
        "title": "Vice President, Strategic M&A",
        "responsibility": "Corporate venture capital, startup acquisition due diligence",
        "org": "Apex Technologies Group",
        "email": "m-and-a@apex-tech.com",
        "status": "SUPPORTED",
        "history": "Managing Director at Goldman Sachs Tech Group.",
    },
    {
        "name": "Maya Krishnan",
        "title": "Vice President, Healthcare & Biometrics",
        "responsibility": "Health sensor algorithms, medical compliance, HIPAA security",
        "org": "Apex Technologies Group",
        "email": None,
        "status": "SUPPORTED",
        "history": "Principal Scientist at BioSensors Labs.",
    },
    {
        "name": "Gregory Houseman",
        "title": "Senior Vice President, Enterprise Solutions",
        "responsibility": "B2B enterprise sales, government contracting, federal compliance",
        "org": "Apex Technologies Group",
        "email": "ghouseman-b2b@apex-tech.com",
        "status": "SUPPORTED",
        "history": "SVP Enterprise at CloudScale Inc.",
    },
    {
        "name": "Oliver Queenan",
        "title": "Vice President, Audio Engineering & Spatial Acoustics",
        "responsibility": "Noise cancellation DSP, acoustic transducers, spatial audio",
        "org": "Apex Technologies Group",
        "email": None,
        "status": "SUPPORTED",
        "history": "Acoustics Lead at Harmonic Audio.",
    },
]


def build_investigation_v1_corpus() -> dict[str, InvestigationDocument]:
    """Build complete 45-document frozen corpus for EVAL_INVESTIGATION_V1."""
    docs: dict[str, InvestigationDocument] = {}

    def add(doc_id: str, title: str, url: str, text_content: str = "", source_type: str = "web", pub: str | None = None, cluster: str | None = None, text: str = ""):
        content = text_content or text
        docs[url] = InvestigationDocument(
            doc_id=doc_id, title=title, url=url, text_content=content,
            source_type=source_type, published_date=pub, syndication_cluster_id=cluster
        )

    # 1. Official SEC Form 10-K Leadership Schedule (Apex Technologies Group)
    exec_table_lines = [
        f"- {ex['name']}: {ex['title']} ({ex['responsibility']}). Public Contact: {ex['email'] if ex['email'] else 'None disclosed'}."
        for ex in APEX_20_EXECUTIVES
    ]
    add(
        doc_id="sec_edgar_apex_10k_2024",
        title="SEC Form 10-K Annual Report - Apex Technologies Group Inc (Fiscal Year 2024)",
        url="https://www.sec.gov/edgar/data/0001889900/000188990024000010/apex-202410k.htm",
        text_content=(
            "EXECUTIVE OFFICERS OF THE REGISTRANT - APEX TECHNOLOGIES GROUP INC (CIK: 0001889900):\n"
            "The following individuals serve as the active Senior Vice Presidents and Vice Presidents of Apex Technologies Group:\n"
            + "\n".join(exec_table_lines) + "\n"
            "Operating headquarters: 100 Technology Plaza, San Jose, California. Incorporated in Delaware."
        ),
        source_type="regulatory_filing",
        pub="2024-02-15",
    )

    # 2. Executive Biographies & OSINT Profiles
    for ex in APEX_20_EXECUTIVES:
        safe_name = ex["name"].lower().replace(" ", "_").replace(".", "")
        add(
            doc_id=f"bio_{safe_name}_profile",
            title=f"Executive Leadership Biography - {ex['name']} | Apex Technologies Group",
            url=f"https://www.apex-tech.com/leadership/{safe_name}",
            text_content=(
                f"BIOGRAPHY: {ex['name']}\n"
                f"Title: {ex['title']}\n"
                f"Scope: {ex['responsibility']}\n"
                f"Career History: {ex['history']}\n"
                f"Business Inquiries: {ex['email'] if ex['email'] else 'Not available via public web portal.'}\n"
            ),
            source_type="corporate_portal",
            pub="2024-01-10",
        )

    # 3. Contradictory / Stale Executive Filings (Temporal Traps)
    add(
        doc_id="stale_sec_apex_10k_2020",
        title="SEC Form 10-K Annual Report - Apex Technologies Group (Historical 2020)",
        url="https://www.sec.gov/edgar/data/0001889900/000188990020000008/apex-202010k.htm",
        text_content=(
            "HISTORICAL EXECUTIVE ROSTER (2020):\n"
            "- Donald Vance: Senior Vice President, Machine Learning & AI (RESIGNED 2021)\n"
            "- Sarah Lin: Director of Infrastructure Operations (Promoted to SVP in 2022)\n"
            "Former CEO: Robert Sterling (Retired December 2021).\n"
        ),
        source_type="regulatory_filing",
        pub="2021-02-10",
    )

    add(
        doc_id="sec_apex_10ka_restatement_2023",
        title="SEC Form 10-K/A Amended Annual Report - Apex Technologies Group (Restatement 2023)",
        url="https://www.sec.gov/edgar/data/0001889900/000188990023000099/apex-202310ka.htm",
        text_content=(
            "AMENDMENT NO. 1 ON FORM 10-K/A:\n"
            "Item 10. Directors and Executive Officers of the Registrant.\n"
            "This amendment corrects historical tenure reporting for David Marcus. Dr. Marcus assumed the role of Senior Vice President, "
            "Machine Learning & AI effective August 15, 2022, succeeding Donald Vance. Donald Vance holds no active affiliation with Registrant."
        ),
        source_type="regulatory_filing",
        pub="2023-11-20",
    )

    # 4. Multi-Specialist Chaining Documents
    add(
        doc_id="sec_apex_exhibit21_subsidiaries",
        title="SEC Form 10-K Exhibit 21 - Subsidiary Schedule of Apex Technologies Group",
        url="https://www.sec.gov/edgar/data/0001889900/000188990024000010/exhibit21.htm",
        text_content=(
            "EXHIBIT 21.1 - SUBSIDIARIES OF APEX TECHNOLOGIES GROUP INC:\n"
            "1. Apex Technologies Europe Ltd (United Kingdom, Company No. 09887766, 100% owned)\n"
            "2. Apex Cloud Infrastructure LLC (Delaware, 100% owned)\n"
            "3. Apex Quantum Sensing GmbH (Munich, Germany, 100% owned)\n"
            "4. Apex Asia-Pacific Pte Ltd (Singapore, 100% owned)\n"
        ),
        source_type="regulatory_filing",
        pub="2024-02-15",
    )

    add(
        doc_id="ch_apex_europe_filing",
        title="Companies House UK - Apex Technologies Europe Ltd (09887766)",
        url="https://find-and-update.company-information.service.gov.uk/company/09887766",
        text_content=(
            "APEX TECHNOLOGIES EUROPE LTD (Company number 09887766):\n"
            "Registered office address: 124 Holborn, London, EC1N 2TD.\n"
            "Parent Company: Apex Technologies Group Inc (US-DE).\n"
            "Active Managing Director: Tobias Richter.\n"
            "Technical Infrastructure Subsidiary: Apex Telemetry UK Limited (100% subsidiary).\n"
        ),
        source_type="official_registry",
        pub="2023-10-01",
    )

    add(
        doc_id="dns_ct_apex_telemetry",
        title="Certificate Transparency Log - crt.sh query for apex-telemetry.co.uk",
        url="https://crt.sh/?q=apex-telemetry.co.uk",
        text_content=(
            "Certificate Transparency Log Entry for apex-telemetry.co.uk:\n"
            "Subject Alternative Names (SAN):\n"
            "- telemetry-cluster-01.apex-telemetry.co.uk\n"
            "- quantum-monitor.apex-sensing.de\n"
            "Issuer: Let's Encrypt Authority X3\n"
            "Admin Contact: rthorne-sec@apex-tech.com\n"
        ),
        source_type="technical_record",
        pub="2024-01-15",
    )

    # 5. Adversarial Syndication Ring (3 Wire Mirrors)
    wire_text = (
        "PRESS RELEASE (PR WIRE): Apex Technologies announces breakthrough in cryogenic quantum processors. "
        "Dr. Kenji Sato demonstrated 512-qubit fidelity in Munich testbed."
    )
    add(
        doc_id="pr_wire_apex_quantum_mirror_1",
        title="Business Wire: Apex Technologies Demonstrates 512-Qubit Architecture",
        url="https://www.businesswire.com/news/home/20240315005112/en/Apex-Quantum-512",
        text_content=wire_text,
        source_type="wire_service",
        pub="2024-03-15",
        cluster="synd_cluster_quantum_apex_01",
    )
    add(
        doc_id="pr_wire_apex_quantum_mirror_2",
        title="PR Newswire: Apex Technologies Demonstrates 512-Qubit Architecture",
        url="https://www.prnewswire.com/news-releases/apex-technologies-quantum-512-882910.html",
        text_content=wire_text,
        source_type="wire_service",
        pub="2024-03-15",
        cluster="synd_cluster_quantum_apex_01",
    )
    add(
        doc_id="marketwatch_apex_quantum_mirror_3",
        title="MarketWatch: Apex Technologies Demonstrates 512-Qubit Architecture (Syndicated)",
        url="https://www.marketwatch.com/press-release/apex-quantum-512-qubit-20240315",
        text_content=wire_text,
        source_type="wire_service",
        pub="2024-03-15",
        cluster="synd_cluster_quantum_apex_01",
    )

    # 6. Negative / NOT_FOUND / Adversarial Controls
    add(
        doc_id="negative_unrelated_corp",
        title="Nevada Secretary of State - Apex Commercial Roofing LLC",
        url="https://esos.nv.gov/corp/apex-roofing-llc",
        text_content=(
            "APEX COMMERCIAL ROOFING LLC (NV2019182818):\n"
            "Business Type: Domestic Limited-Liability Company. General roofing contractor. "
            "Zero affiliation with computer hardware, cloud, or electronics."
        ),
        source_type="official_registry",
        pub="2019-06-01",
    )

    add(
        doc_id="adversarial_homoglyph_apex",
        title="WHOIS Record - apex-g1obal-tech.com",
        url="https://whois.domaintools.com/apex-g1obal-tech.com",
        text_content=(
            "Domain Name: apex-g1obal-tech.com\n"
            "Registrar: NameCheap Inc\n"
            "Registrant Organization: Privacy Protection Service\n"
            "Flagged Security Alert: Lookalike homoglyph mimicking Apex Technologies Group. Phishing indicator."
        ),
        source_type="technical_record",
        pub="2024-02-01",
    )

    return docs


def build_p03_benchmark_corpus() -> dict[str, InvestigationDocument]:
    """Build frozen authentic corpus documents for P0.3 Research Accuracy tasks (26-50)."""
    docs: dict[str, InvestigationDocument] = {}

    def add(
        doc_id: str,
        title: str,
        url: str,
        text_content: str,
        source_type: str,
        pub: str | None = None,
        cluster: str | None = None,
    ) -> None:
        docs[doc_id] = InvestigationDocument(
            doc_id=doc_id,
            title=title,
            url=url,
            text_content=text_content,
            source_type=source_type,
            published_date=pub,
            syndication_cluster_id=cluster,
        )

    # 1. Technical & Engineering
    add(
        doc_id="doc_raft_consensus_spec",
        title="In Search of an Understandable Consensus Algorithm (Extended Version)",
        url="https://raft.github.io/raft.pdf",
        text_content=(
            "The Raft consensus algorithm by Diego Ongaro and John Ousterhout guarantees safety under network partition. "
            "In a 5-node cluster partitioned into 3 nodes and 2 nodes, the 3-node partition maintains a majority quorum "
            "of (N/2)+1 = 3 nodes, allowing it to elect a leader and continue committing log entries. The minority 2-node "
            "partition cannot achieve quorum (requires 3 nodes), thus preventing split-brain and conflicting state machine commits."
        ),
        source_type="academic_paper",
        pub="2014-05-20",
    )

    add(
        doc_id="doc_ebpf_verifier_internals",
        title="Linux Kernel Documentation: BPF Verifier Architecture and Safety Guarantees",
        url="https://www.kernel.org/doc/html/latest/bpf/verifier.html",
        text_content=(
            "The Linux Kernel eBPF Verifier, maintained by Alexei Starovoitov, performs static abstract interpretation before "
            "any BPF program executes in kernel space. It constructs a directed acyclic graph (DAG) of all possible control-flow "
            "paths, checking every instruction to guarantee termination (rejecting unbounded loops) and tracking register state "
            "bounds (min/max range, pointer types, alignment). Pointers are strictly bounds-checked to prevent out-of-bounds memory access."
        ),
        source_type="technical_specification",
        pub="2023-01-15",
    )

    add(
        doc_id="doc_riscv_memory_model_rvwmo",
        title="The RISC-V Instruction Set Manual: Volume I, RVWMO Memory Model",
        url="https://riscv.org/specifications/rvwmo-memory-model/",
        text_content=(
            "The RISC-V Weak Memory Ordering (RVWMO) memory model governs memory accesses executed by multiple harts (hardware threads). "
            "RVWMO distinguishes preserved program order generated by explicit FENCE instructions (such as FENCE r,rw or FENCE rw,w) "
            "from syntactic data, address, and control dependencies. Unlike sequentially consistent architectures, loads and stores "
            "may be reordered unless an explicit FENCE or dependency preserves execution order."
        ),
        source_type="technical_specification",
        pub="2019-12-13",
    )

    # 2. Historical Research
    add(
        doc_id="doc_nixon_shock_1971_announcement",
        title="Address to the Nation Outlining a New Economic Policy: The Challenge of Peace",
        url="https://www.presidency.ucsb.edu/documents/address-the-nation-outlining-new-economic-policy-the-challenge-peace",
        text_content=(
            "On August 15, 1971, President Richard Nixon announced his New Economic Policy following a secret weekend conference "
            "at Camp David with Treasury Secretary John Connally. Nixon directed Treasury Secretary Connally to suspend temporarily "
            "the convertibility of the American dollar into gold or other reserve assets for foreign governments, effectively closing "
            "the gold window and terminating the Bretton Woods system of fixed exchange rates."
        ),
        source_type="primary_historical_record",
        pub="1971-08-15",
    )

    add(
        doc_id="doc_treaty_of_utrecht_article_x",
        title="The Treaty of Utrecht (1713) - Article X: Cession of Gibraltar to Great Britain",
        url="https://avalon.law.yale.edu/18th_century/utrecht.asp",
        text_content=(
            "Article X of the Treaty of Utrecht, concluded in July 1713 between King Philip V of Spain and Queen Anne of Great Britain, "
            "states that the Catholic King yields to the Crown of Great Britain the full and entire propriety of the Town and Castle of Gibraltar, "
            "along with the port, fortifications, and forts belonging thereto, to be held without any exception or impediment, without any territorial "
            "jurisdiction beyond the fortifications."
        ),
        source_type="primary_treaty_record",
        pub="1713-07-13",
    )

    # 3. Scientific and Policy Research
    add(
        doc_id="doc_mrna_lnp_composition_nature",
        title="Molecular Architecture and Delivery Mechanisms of Lipid Nanoparticles in mRNA Vaccines",
        url="https://www.nature.com/articles/s41578-021-00358-0",
        text_content=(
            "Lipid nanoparticles (LNPs) utilized in clinical mRNA vaccines consist of four essential lipid components: an ionizable "
            "cationic lipid (such as ALC-0315 or SM-102), a PEG-lipid conjugate, cholesterol, and a helper phospholipid (DSPC, "
            "1,2-distearoyl-sn-glycero-3-phosphocholine). The ionizable lipid is positively charged at low pH during formulation to "
            "encapsulate negatively charged mRNA, and neutral at physiological pH to minimize toxicity while facilitating cellular uptake and endosomal escape."
        ),
        source_type="scientific_journal",
        pub="2021-08-12",
    )

    add(
        doc_id="doc_eu_ai_act_regulation_2024",
        title="Regulation (EU) 2024/1689 of the European Parliament and of the Council on Artificial Intelligence",
        url="https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1689",
        text_content=(
            "Regulation (EU) 2024/1689 establishes the EU AI Act. Under Article 6, AI systems are classified as High-Risk if they are intended "
            "to be used as safety components of products subject to third-party conformity assessment, or fall under Annex III high-risk use areas "
            "(including biometric identification, critical infrastructure management, education, employment, and law enforcement). "
            "Providers of high-risk systems must establish risk management systems and undergo conformity assessments."
        ),
        source_type="official_legislation",
        pub="2024-06-13",
    )

    # 4. Organizational and Corporate Research
    add(
        doc_id="doc_airbus_eads_2014_restructuring",
        title="EADS Reorganization into Airbus Group: Corporate Restructuring and Shareholding Agreement",
        url="https://www.airbus.com/en/newsroom/press-releases/2014-01-eads-becomes-airbus-group",
        text_content=(
            "Effective January 1, 2014, the European Aeronautic Defence and Space Company (EADS) was formally rebranded and restructured "
            "into Airbus Group under Chief Executive Tom Enders. The Group unified operations into three divisions: Airbus (commercial aircraft), "
            "Airbus Defence and Space (military transport, space systems, and defense electronics), and Airbus Helicopters. The governance agreement "
            "equalized French and German state shareholdings at approximately 11% each."
        ),
        source_type="corporate_filing",
        pub="2014-01-02",
    )

    add(
        doc_id="doc_asml_euv_supply_chain_analysis",
        title="Semiconductor Equipment Ecosystem: ASML High-NA EUV Supplier Architecture",
        url="https://www.semianalysis.com/p/asml-euv-supply-chain-zeiss-trumpf",
        text_content=(
            "ASML Holding NV maintains exclusive single-source dependencies for key optical and energy subsystems in its extreme ultraviolet "
            "(EUV) photolithography platforms. Carl Zeiss SMT GmbH develops and manufactures the ultra-precise projection and illumination mirror "
            "optics with atomic-level surface smoothness. Trumpf SE + Co. KG manufactures the industrial high-power pulsed CO2 laser system that "
            "evaporates molten tin droplets to generate 13.5 nm EUV light."
        ),
        source_type="industry_analysis",
        pub="2023-11-04",
    )

    # 5. Interdisciplinary or Unfamiliar-Domain Research
    add(
        doc_id="doc_chaco_canyon_sun_dagger_sofaer",
        title="A Unique Solar Marking Construct in Chaco Canyon: Fajada Butte Petroglyph Complex",
        url="https://www.science.org/doi/10.1126/science.206.4416.283",
        text_content=(
            "At Fajada Butte in Chaco Canyon, New Mexico, three large sandstone slabs collimate sunlight onto two spiral petroglyphs carved "
            "on the cliff face. The 'Sun Dagger' site, documented by Anna Sofaer, records both solar and lunar cycles: a vertical dagger bisects "
            "the large spiral at summer solstice, two daggers frame it at winter solstice, and the shadow marks the equinoxes. Furthermore, "
            "the 9.5 turns of the spiral record the 18.6-year lunar standstill cycle, tracking the moon's extreme declinations."
        ),
        source_type="scientific_journal",
        pub="1979-10-19",
    )

    add(
        doc_id="doc_basque_ergative_syntax_linguistics",
        title="Morphosyntactic Alignment in Euskara: Case Marking and Agreement in Basque",
        url="https://www.degruyter.com/document/doi/10.1515/ling.2018.0042/html",
        text_content=(
            "The Basque language (Euskara) is a quintessential ergative-absolutive language. In Basque syntax, the subject of an intransitive "
            "clause and the direct object of a transitive clause are both marked with the absolutive case (zero morpheme, -a), whereas the subject "
            "(agent) of a transitive clause receives the overt ergative case suffix (-k). Verbal agreement in Basque is polypersonal, cross-referencing "
            "ergative, absolutive, and dative arguments."
        ),
        source_type="academic_linguistics",
        pub="2018-04-15",
    )

    # 6. Time-Sensitive Factual Questions (Dated Fixtures)
    add(
        doc_id="doc_uk_pm_transition_oct_2022_official",
        title="UK Government Gazette: Resignation of Prime Minister and Appointment of Successor",
        url="https://www.gov.uk/government/news/prime-minister-transition-october-2022",
        text_content=(
            "On October 20, 2022, Liz Truss announced her intention to resign as Prime Minister. However, under British constitutional law, "
            "Liz Truss remained in office as the legally authoritative Prime Minister through October 24, 2022 at 10 Downing Street until her formal "
            "audience with King Charles III on the morning of October 25, 2022. Rishi Sunak was invited by the Sovereign to form a government "
            "at 10 Downing Street on October 25, 2022."
        ),
        source_type="official_gazette",
        pub="2022-10-25",
    )

    add(
        doc_id="doc_sec_bitcoin_etf_order_jan_2024",
        title="Securities and Exchange Commission: Order Granting Accelerated Approval of Spot Bitcoin ETPs",
        url="https://www.sec.gov/rules/sro/nysearca/2024/34-99306.pdf",
        text_content=(
            "On January 9, 2024 at approximately 4:11 PM EST, an unauthorized party gained access to the SEC official @SECGov Twitter account "
            "and published a false statement claiming ETF approval. Chairman Gary Gensler clarified within thirty minutes that the account was "
            "compromised and no approval had been granted. The official Commission omnibus order approving spot Bitcoin ETP applications was "
            "lawfully entered on January 10, 2024 under Release No. 34-99306 by the Securities and Exchange Commission."
        ),
        source_type="regulatory_order",
        pub="2024-01-10",
    )

    # 7. Questions with Conflicting or Ambiguous Source Material
    add(
        doc_id="doc_drake_equation_optimistic_1961",
        title="The Radio Search for Intelligent Extraterrestrial Life: The Drake Equation",
        url="https://www.seti.org/drake-equation-history",
        text_content=(
            "At the 1961 Green Bank conference, astronomer Frank Drake formulated the Drake Equation: N = R* · fp · ne · fl · fi · fc · L. "
            "Using optimistic assumptions for planetary formation, biological emergence, and civilizational lifetime (L ~ 10,000 years), "
            "Drake and Carl Sagan estimated that N could range between 1,000 and 1,000,000 communicative civilizations currently active in the Milky Way galaxy."
        ),
        source_type="scientific_publication",
        pub="1961-11-01",
    )

    add(
        doc_id="doc_drake_equation_pessimistic_fermi",
        title="Dissolving the Fermi Paradox: Astrobiological Constraints on Communicative Civilizations",
        url="https://arxiv.org/abs/1806.02404",
        text_content=(
            "When parameter uncertainty in the Drake equation is represented using realistic scientific probability distributions spanning many orders "
            "of magnitude, the distribution for N is extremely right-skewed. The authors demonstrate that the median value of N is below 1, with a high "
            "probability (53% to 99.6%) that humanity is alone in the Milky Way. This directly contradicts optimistic estimates of thousands of active civilizations."
        ),
        source_type="scientific_prepublication",
        pub="2018-06-06",
    )

    add(
        doc_id="doc_roemer_speed_of_light_1676",
        title="Touchant le Mouvement de la Lumiere: Rømer's Observations at Paris Observatory",
        url="https://gallica.bnf.fr/ark:/12148/bpt6k56531c/f681.image",
        text_content=(
            "In December 1676, Danish astronomer Ole Rømer published his observations of the eclipses of Jupiter's moon Io at the Paris Observatory. "
            "Rømer demonstrated that the observed intervals between eclipses varied systematically depending on the Earth's distance from Jupiter, "
            "concluding that light travels across the diameter of Earth's orbit in approximately 22 minutes. However, Rømer did not calculate a numerical "
            "speed of light in terrestrial units (km/s)."
        ),
        source_type="historical_scientific_journal",
        pub="1676-12-07",
    )

    add(
        doc_id="doc_huygens_treatise_on_light_1690",
        title="Treatise on Light: First Quantitative Derivation of the Velocity of Light",
        url="https://www.gutenberg.org/files/14725/14725-h/14725-h.htm",
        text_content=(
            "In his 1690 Traité de la Lumière, Dutch polymath Christiaan Huygens used Ole Rømer's timing data combined with Jean Picard's estimate "
            "of the Earth-Sun distance to compute the first explicit numerical velocity of light. Huygens obtained a value equivalent to roughly "
            "220,000 km/s, resolving the dispute between instantaneous propagation and finite velocity with the first quantitative calculation."
        ),
        source_type="historical_treatise",
        pub="1690-01-01",
    )

    # 8. Questions Where Available Evidence Is Insufficient
    add(
        doc_id="doc_lk99_superconductivity_refutation",
        title="Independent Laboratory Investigations and Magnetic Properties of Cu-Doped Lead Apatite",
        url="https://www.nature.com/articles/d41586-023-02585-7",
        text_content=(
            "Following claims by Sukbae Lee and colleagues regarding room-temperature superconductivity in LK-99, independent research groups worldwide "
            "(including the Max Planck Institute, Princeton, and Peking University) synthesized pure single crystals. Experiments established that "
            "LK-99 is an insulator and not a superconductor. Observed half-levitation was attributed to ferromagnetism and diamagnetism, and the sharp "
            "resistivity drop was caused by copper sulfide (Cu2S) impurities undergoing a first-order phase transition at 104°C."
        ),
        source_type="scientific_journal",
        pub="2023-08-16",
    )

    add(
        doc_id="doc_dark_matter_lux_zeplin_null_results",
        title="First Dark Matter Search Results from the LUX-ZEPLIN (LZ) Experiment",
        url="https://journals.aps.org/prl/abstract/10.1103/PhysRevLett.131.041002",
        text_content=(
            "The LUX-ZEPLIN (LZ) experiment, operating a 7-tonne active liquid xenon target at the Sanford Underground Research Facility, reported initial "
            "results from its search for weakly interacting massive particles (WIMPs). The data showed zero excess events over expected background, setting "
            "the world's most stringent upper limits on spin-independent WIMP-nucleon cross-sections for dark matter masses above 9 GeV/c^2. "
            "Direct detection of particle dark matter remains unobserved, and claims by DAMA/LIBRA remain unverified."
        ),
        source_type="scientific_journal",
        pub="2023-07-28",
    )

    add(
        doc_id="doc_voynich_manuscript_linguistic_status",
        title="Linguistic and Codicological Assessment of the Voynich Manuscript (Beinecke MS 408)",
        url="https://beinecke.library.yale.edu/collections/highlights/voynich-manuscript",
        text_content=(
            "The Voynich Manuscript (Beinecke MS 408), carbon-dated to the early 15th century, contains an unknown script and botanical illustrations. "
            "Discovered by Wilfrid Voynich and housed at the Beinecke Library, periodic announcements claiming definitive decipherment have all failed peer review. "
            "Computational linguistics and academic consensus maintain that the text remains undeciphered, and no translation key has been scientifically validated."
        ),
        source_type="curatorial_archive",
        pub="2022-09-10",
    )

    # 9. Misleading or Irrelevant Search Results
    add(
        doc_id="doc_python_pep703_freethreading_cpython313",
        title="PEP 703: Making the Global Interpreter Lock Optional in CPython",
        url="https://peps.python.org/pep-0703/",
        text_content=(
            "PEP 703 proposes making the Global Interpreter Lock (GIL) optional in CPython. In October 2023, the Python Steering Council accepted PEP 703. "
            "Starting in Python 3.13, CPython provides an experimental free-threaded build configuration (--disable-gil). Authored by Sam Gross and supported "
            "by Guido van Rossum, the implementation uses biased reference counting, immortal objects, and mimalloc thread-safe memory allocation to run "
            "multi-threaded Python code on multiple CPU cores without the GIL, superseding obsolete claims that removing the GIL was impossible."
        ),
        source_type="technical_specification",
        pub="2023-10-01",
    )

    add(
        doc_id="doc_quantum_radar_physics_limitations",
        title="Quantum Illumination vs Microwave Radar: Theoretical Bounds and Technological Realities",
        url="https://ieeexplore.ieee.org/document/9079812",
        text_content=(
            "Quantum radar concepts based on quantum illumination (pioneered by Seth Lloyd in 2008) utilize entangled signal-idler photon pairs. "
            "In laboratory environments with low-brightness thermal noise, quantum illumination offers a theoretical advantage. However, in operational "
            "military environments, optical-to-microwave conversion losses, atmospheric attenuation, thermal background microwave photons, and receiver "
            "photon collection limits prevent operational deployment against stealth aircraft. Claims of deployed anti-stealth quantum radars are scientifically unsubstantiated."
        ),
        source_type="scientific_journal",
        pub="2020-05-15",
    )

    # 10. Multi-Fact Synthesis
    add(
        doc_id="doc_apollo_11_1202_alarm_root_cause",
        title="Computers in Spaceflight: The NASA Experience - The Apollo Guidance Computer and the 1202 Alarm",
        url="https://history.nasa.gov/computers/Ch2-5.html",
        text_content=(
            "During the Apollo 11 lunar module descent on July 20, 1969, the Apollo Guidance Computer (AGC) triggered repeated 1202 and 1201 alarms. "
            "The root cause was an electrical phase mismatch: the rendezvous radar power switch was in the SLEW position instead of AUTO, causing the radar "
            "attitude tracking interface to send 12,800 cycle-per-second interrupts to the AGC, consuming 15% of its CPU time. Hal Laning's priority-scheduled "
            "executive queue dropped low-priority display tasks while preserving flight-critical guidance computations (designed with Margaret Hamilton), "
            "allowing Neil Armstrong to land safely."
        ),
        source_type="historical_technical_record",
        pub="1988-06-01",
    )

    add(
        doc_id="doc_deepwater_horizon_national_commission_report",
        title="Deep Water: The Gulf Oil Disaster and the Future of Offshore Drilling - Report to the President",
        url="https://www.gpo.gov/fdsys/pkg/GPO-OILCOMMISSION/pdf/GPO-OILCOMMISSION.pdf",
        text_content=(
            "The Macondo well blowout on April 20, 2010 on the Deepwater Horizon drilling rig resulted from multiple technical barrier failures: "
            "Halliburton's nitrogen-foamed cement slurry failed to seal the shoe track; personnel misinterpreted a negative pressure test showing drill pipe "
            "pressure as a 'bladder effect'; and the Cameron blowout preventer (BOP) blind shear rams failed to cut the drill pipe because the buckling forces "
            "had deformed and de-centered the drill pipe within the wellbore."
        ),
        source_type="official_inquiry_report",
        pub="2011-01-11",
    )

    add(
        doc_id="doc_voyager_1_interstellar_boundary_science",
        title="In Situ Observations of Interstellar Plasma by Voyager 1 at the Heliopause",
        url="https://www.science.org/doi/10.1126/science.1241681",
        text_content=(
            "On August 25, 2012, at a distance of 121.6 astronomical units from the Sun, Voyager 1 crossed the heliopause into interstellar space. "
            "The spacecraft, led by project scientist Ed Stone, detected three simultaneous signatures: a sudden drop in lower-energy solar wind ions by over "
            "1,000-fold; a simultaneous 9.3% increase in galactic cosmic ray intensity; and an ambient plasma density jump from 0.002 to 0.08 electrons "
            "per cubic centimeter, confirming the transition into dense interstellar plasma."
        ),
        source_type="scientific_journal",
        pub="2013-09-12",
    )

    add(
        doc_id="doc_doom_bsp_rendering_architecture_fabien",
        title="Game Engine Black Book: Doom - Binary Space Partitioning Architecture",
        url="https://fabiensanglard.net/doomIphone/doomClassicRenderer.php",
        text_content=(
            "In developing Doom (1993), John Carmack solved the 2.5D rendering bottleneck by implementing Binary Space Partitioning (BSP) trees, "
            "based on Bruce Naylor's 1990 computer graphics research. A pre-compiled 2D BSP tree divided the map into convex sub-sectors. At runtime, "
            "the player's position determined a front-to-back traversal order, rendering walls closest to the viewer first. A 1D horizontal occlusion "
            "array (screen clipping buffer) clipped distant geometry, completely eliminating overdraw without requiring a 3D Z-buffer."
        ),
        source_type="technical_analysis",
        pub="2018-12-10",
    )

    add(
        doc_id="doc_hubble_tension_astrophysical_measurements",
        title="The Hubble Tension: Discrepancy Between Early and Late Universe Determinations of H0",
        url="https://www.annualreviews.org/doi/10.1146/annurev-astro-071221-052932",
        text_content=(
            "The Hubble tension refers to the statistically significant discrepancy between early-universe measurements of the Hubble constant "
            "(H0 = 67.4 ± 0.5 km/s/Mpc derived by the Planck Collaboration assuming flat Lambda-CDM from CMB temperature fluctuations) and late-universe "
            "local distance ladder measurements (H0 = 73.04 ± 1.04 km/s/Mpc by the SH0ES collaboration led by Adam Riess using Hubble Space Telescope Cepheids "
            "and Type Ia supernovae). The discrepancy exceeds 5 sigma, presenting a profound unresolved challenge to modern cosmology."
        ),
        source_type="scientific_journal",
        pub="2022-08-18",
    )

    return docs


def build_full_investigation_corpus() -> dict[str, InvestigationDocument]:
    """Return unified corpus containing both V1 and P0.3 multi-domain benchmark documents."""
    return {**build_investigation_v1_corpus(), **build_p03_benchmark_corpus()}


class InvestigationCorpusRegistry:
    """Simulated multi-domain investigation registry with search and discovery."""

    def __init__(self, docs: dict[str, InvestigationDocument] | None = None) -> None:
        self.documents: dict[str, InvestigationDocument] = docs if docs is not None else build_full_investigation_corpus()
        self.doc_by_id: dict[str, InvestigationDocument] = {d.doc_id: d for d in self.documents.values()}
        self._discoverable_entities: set[str] = set()
        self._populate_entities()

    def _populate_entities(self) -> None:
        for ex in APEX_20_EXECUTIVES:
            self._discoverable_entities.add(ex["name"])
        self._discoverable_entities.update([
            "Apex Technologies Group",
            "Apex Technologies Group Inc",
            "Apex Technologies Europe Ltd",
            "Apex Cloud Infrastructure LLC",
            "Apex Quantum Sensing GmbH",
            "Apex Asia-Pacific Pte Ltd",
            "Apex Telemetry UK Limited",
            "Donald Vance",
            "Robert Sterling",
            "telemetry-cluster-01.apex-telemetry.co.uk",
            "quantum-monitor.apex-sensing.de",
            "University of Tokyo",
            "Cyberspace Defense Corp",
            "CloudMatrix",
            "NeuralCore",
            "SiliconWorks",
            "GlobalElectronics",
            "MIT CSAIL",
            "Apex Commercial Roofing LLC",
            # P0.3 Multi-Domain Benchmark Entities
            "Raft", "Diego Ongaro", "John Ousterhout",
            "eBPF Verifier", "Linux Kernel", "Alexei Starovoitov",
            "RVWMO", "RISC-V", "FENCE",
            "Richard Nixon", "Camp David", "John Connally",
            "Treaty of Utrecht", "Philip V of Spain", "Queen Anne", "Gibraltar",
            "Lipid Nanoparticle", "Ionizable Lipid", "PEG-Lipid", "DSPC",
            "EU AI Act", "Annex III", "European Parliament",
            "Airbus Group", "EADS", "Tom Enders",
            "ASML Holding", "Carl Zeiss SMT", "Trumpf",
            "Chaco Canyon", "Fajada Butte", "Sun Dagger", "Anna Sofaer",
            "Basque Language", "Ergative-Absolutive", "Absolutive Case",
            "Liz Truss", "10 Downing Street",
            "Gary Gensler", "Securities and Exchange Commission",
            "Drake Equation", "Frank Drake", "Fermi Paradox",
            "Ole Rømer", "Christiaan Huygens", "Io",
            "LK-99", "Max Planck Institute",
            "LUX-ZEPLIN", "WIMP", "DAMA/LIBRA",
            "Voynich Manuscript", "Wilfrid Voynich", "Beinecke Library",
            "PEP 703", "Sam Gross", "Guido van Rossum",
            "Quantum Illumination", "Seth Lloyd",
            "Apollo Guidance Computer", "1202 Alarm", "Hal Laning", "Margaret Hamilton",
            "Deepwater Horizon", "Macondo Well", "Blowout Preventer", "Halliburton",
            "Voyager 1", "Heliopause", "Ed Stone",
            "Binary Space Partitioning", "John Carmack", "Bruce Naylor",
            "Hubble Tension", "Planck Collaboration", "Adam Riess", "SH0ES",
        ])

    def register_discoverable_entity(self, entity: str) -> None:
        if entity:
            self._discoverable_entities.add(entity)

    def get_discoverable_entities(self) -> set[str]:
        return set(self._discoverable_entities)

    def search(self, query: str, limit: int = 10) -> list[InvestigationDocument]:
        """Search corpus documents using token matching, exact entity boosting, and source relevance."""
        import re
        clean_q = query.replace('"', "").replace("'", "")
        tokens = [t.lower() for t in re.split(r"[\s,;:\.\?\(\)\[\]]+", clean_q) if len(t) > 2]
        scored_docs: list[tuple[float, InvestigationDocument]] = []

        for doc in self.documents.values():
            score = 0.0
            doc_text_lower = doc.text_content.lower()
            doc_title_lower = doc.title.lower()

            # Exact query match boost
            if clean_q.lower() in doc_text_lower:
                score += 5.0
            if clean_q.lower() in doc_title_lower:
                score += 8.0

            # Token overlap score
            for t in tokens:
                if t in doc_title_lower:
                    score += 2.0
                if t in doc_text_lower:
                    score += 0.5

            if score > 0:
                scored_docs.append((score, doc))

        scored_docs.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in scored_docs[:limit]]


INVESTIGATION_CORPUS_REGISTRY = InvestigationCorpusRegistry()
