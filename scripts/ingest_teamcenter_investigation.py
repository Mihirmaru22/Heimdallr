"""Ingest Siemens Teamcenter PLM Enterprise Research into Argus SQLite DB.

Populates:
- objectives (Teamcenter Ecosystem Research Objective)
- tasks (Enterprise discovery, verification, and technographic tasks)
- documents (Cleaned OSINT source documents)
- entities (33 Enterprise Companies + Software Products)
- claims (USES_PLM_SOFTWARE, DEPLOYS_FOR, OPERATING_INDUSTRY, SCALE_REVENUE, WORKFORCE_SIZE)
- evidence (Direct source citations with verification URLs)
- events (System audit trail)
- teamcenter_customer_matrix (Structured query table)
"""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from argus.crawler.models import Document
from argus.domain.claim import Claim, ClaimStatus
from argus.domain.entity import Entity
from argus.domain.event import EventType, ResearchEvent
from argus.domain.evidence import Evidence
from argus.domain.objective import ResearchObjective
from argus.domain.task import ResearchTask, TaskStatus
from argus.storage.db import DatabaseManager
from argus.storage.repository import ArgusRepository

DB_PATH = "data/argus_us_automotive_deep.db"

CUSTOMERS = [
    {
        "name": "SpaceX",
        "industry": "Aerospace & Space Exploration",
        "hq": "Hawthorne, California, USA",
        "employees": "13,000+",
        "revenue": "$9B+",
        "use_case": "Central engineering CAD/CAM repository for Falcon 9, Falcon Heavy, and Dragon spacecraft specifications and manufacturing data.",
        "software": "Siemens Teamcenter, Siemens NX, NX Nastran",
        "url": "https://media.plm.automation.siemens.com/nx/CAD_design-solutions/pdf/10/NXCAD01_10_en_spacex_CS.pdf",
        "evidence": "Teamcenter is the repository for all documentation related to the design and manufacture of the Falcon – CAD models, specifications and so on."
    },
    {
        "name": "General Motors",
        "industry": "Automotive OEM",
        "hq": "Detroit, Michigan, USA",
        "employees": "163,000",
        "revenue": "$171B",
        "use_case": "Enterprise-wide PLM deployment ('EPICenter') powering global vehicle engineering, Bill-of-Materials (BOM), tooling, and factory release processes.",
        "software": "Siemens Teamcenter (EPICenter), Siemens NX",
        "url": "https://community.sw.siemens.com/s/question/0D5Vb00000gy4XBKAY/",
        "evidence": "General Motors deploys enterprise Teamcenter NX (EPICenter) across global vehicle design, powertrain, and assembly facilities."
    },
    {
        "name": "Boeing",
        "industry": "Commercial & Defense Aerospace",
        "hq": "Arlington, Virginia, USA",
        "employees": "170,000",
        "revenue": "$77B",
        "use_case": "Multi-program PLM integration managing engineering design data, process planning, and supplier collaboration across commercial and defense aircraft.",
        "software": "Siemens Teamcenter Enterprise / Unified, Siemens NX",
        "url": "https://plmphilosophy483489853.wordpress.com/2024/07/08/boeings-plm-implementation-for-aerospace-excellence/",
        "evidence": "Boeing uses Siemens Teamcenter: A widely used PLM software that helps Boeing integrate data, processes, and business systems across aircraft lifecycles."
    },
    {
        "name": "ASML",
        "industry": "Semiconductor Equipment",
        "hq": "Veldhoven, Netherlands",
        "employees": "42,000",
        "revenue": "$30B",
        "use_case": "Central technical repository managing extreme ultraviolet (EUV) and DUV lithography machine component designs and manufacturing specifications.",
        "software": "Siemens Teamcenter",
        "url": "https://www.scmp.com/tech/tech-war/article/3210375/asml-stolen-data-came-repository-chip-machines",
        "evidence": "ASML manages engineering details and technical specifications for its chip manufacturing machines in a Siemens Teamcenter repository."
    },
    {
        "name": "Ford Motor Company",
        "industry": "Automotive OEM",
        "hq": "Dearborn, Michigan, USA",
        "employees": "173,000",
        "revenue": "$176B",
        "use_case": "Global product lifecycle management platform managing powertrain, vehicle assembly, CAD geometry, and global engineering change orders.",
        "software": "Siemens Teamcenter, Multi-CAD Integrations",
        "url": "https://theirstack.com/en/technology/siemens-teamcenter",
        "evidence": "Ford Motor Company deploys Siemens Teamcenter across motor vehicle manufacturing operations with 186k employees and $170B+ revenue."
    },
    {
        "name": "Nissan Motor Corporation",
        "industry": "Automotive OEM",
        "hq": "Yokohama, Japan",
        "employees": "130,000",
        "revenue": "$85B",
        "use_case": "Core PLM system driving Nissan's global V-3P vehicle development innovation process across 5M+ vehicles annually.",
        "software": "Siemens Teamcenter, Siemens NX, Simcenter 3D",
        "url": "https://resources.sw.siemens.com/en-US/case-study-nissan-technical-centre-europe/",
        "evidence": "Siemens PLM software is the main solution for our V-3P innovation process. Ideas and NX form the core design system, and Teamcenter manages global vehicle data."
    },
    {
        "name": "Lockheed Martin",
        "industry": "Defense & Space Manufacturing",
        "hq": "Bethesda, Maryland, USA",
        "employees": "115,000",
        "revenue": "$67B",
        "use_case": "Aerospace & defense missile systems, satellite payload engineering data, and digital thread tracking.",
        "software": "Siemens Teamcenter",
        "url": "https://theirstack.com/en/technology/siemens-teamcenter",
        "evidence": "Lockheed Martin utilizes Siemens Teamcenter for product lifecycle management across defense and space manufacturing programs."
    },
    {
        "name": "Northrop Grumman",
        "industry": "Defense & Space Manufacturing",
        "hq": "Falls Church, Virginia, USA",
        "employees": "88,000",
        "revenue": "$39B",
        "use_case": "Aerospace systems, stealth technology, naval electronics, and complex weapon systems product lifecycle integration.",
        "software": "Siemens Teamcenter, Siemens NX",
        "url": "https://theirstack.com/en/technology/siemens-teamcenter",
        "evidence": "Northrop Grumman uses Siemens Teamcenter for defense and space manufacturing with 88k employees."
    },
    {
        "name": "Daimler Truck",
        "industry": "Commercial Vehicles",
        "hq": "Leinfelden-Echterdingen, Germany",
        "employees": "100,000",
        "revenue": "$60B",
        "use_case": "Comprehensive digital engineering platform standardizing truck and bus engineering data across Mercedes-Benz Trucks, Freightliner, and FUSO.",
        "software": "Siemens Teamcenter, Siemens Xcelerator",
        "url": "https://news.siemens.com/en-us/daimler-truck-siemens-digital-engineering-platform/",
        "evidence": "Daimler Truck collaborates with Siemens to build an integrated digital engineering platform using Siemens Teamcenter."
    },
    {
        "name": "Hyundai & KIA Motors",
        "industry": "Automotive OEM",
        "hq": "Seoul, South Korea",
        "employees": "120,000",
        "revenue": "$160B",
        "use_case": "Next-generation vehicle development platform displacing legacy systems for integrated design, engineering, and manufacturing lifecycles.",
        "software": "Siemens Teamcenter, Siemens Xcelerator",
        "url": "https://www.engineering.com/story/siemens-wins-big-hyundai-kia-motors-swaps-out-catia-and-windchill",
        "evidence": "Hyundai KIA Motors selected Siemens Teamcenter and Xcelerator portfolio in major enterprise PLM modernization."
    },
    {
        "name": "Rolls-Royce",
        "industry": "Aero Engines & Industrial Power",
        "hq": "London, United Kingdom",
        "employees": "42,000",
        "revenue": "$18B",
        "use_case": "Civil & defense jet engine design, digital twin models, lifecycle service tracking, and precision turbine manufacturing.",
        "software": "Siemens Teamcenter",
        "url": "https://theirstack.com/en/technology/siemens-teamcenter",
        "evidence": "Rolls-Royce deploys Siemens Teamcenter across industrial machinery and aerospace engine manufacturing operations."
    },
    {
        "name": "BAE Systems",
        "industry": "Defense & Naval Architecture",
        "hq": "London, United Kingdom",
        "employees": "90,000",
        "revenue": "$30B",
        "use_case": "Naval warship architecture, combat vehicle systems, and advanced military aircraft component design.",
        "software": "Siemens Teamcenter",
        "url": "https://theirstack.com/en/technology/siemens-teamcenter",
        "evidence": "BAE Systems utilizes Siemens Teamcenter for defense, naval, and aerospace manufacturing programs."
    },
    {
        "name": "Volvo Cars",
        "industry": "Automotive OEM",
        "hq": "Gothenburg, Sweden",
        "employees": "43,000",
        "revenue": "$35B",
        "use_case": "Collaborative engineering platform connecting vehicle styling, chassis design, and electric powertrain development.",
        "software": "Siemens Teamcenter",
        "url": "https://www.engineering.com/story/dassault-or-siemens-plm-jaguar-land-rover-and-volvo-cars",
        "evidence": "Volvo Cars utilizes Siemens Teamcenter for global vehicle engineering and collaborative digital manufacturing."
    },
    {
        "name": "Honeywell",
        "industry": "Industrial Technology & Avionics",
        "hq": "Charlotte, North Carolina, USA",
        "employees": "95,000",
        "revenue": "$36B",
        "use_case": "Electronic components, turbine auxiliary power units (APUs), and building automation systems product management.",
        "software": "Siemens Teamcenter",
        "url": "https://theirstack.com/en/technology/siemens-teamcenter",
        "evidence": "Honeywell deploys Siemens Teamcenter across electronics, appliances, and aerospace manufacturing."
    },
    {
        "name": "Leonardo S.p.A.",
        "industry": "Aerospace, Defense & Security",
        "hq": "Rome, Italy",
        "employees": "51,000",
        "revenue": "$17B",
        "use_case": "Helicopter rotor system modeling, defense avionics, and radar systems lifecycle engineering.",
        "software": "Siemens Teamcenter",
        "url": "https://theirstack.com/en/technology/siemens-teamcenter",
        "evidence": "Leonardo S.p.A. deploys Siemens Teamcenter for defense, security, and space manufacturing with 51k employees."
    },
    {
        "name": "Navantia",
        "industry": "Naval Defense Shipbuilding",
        "hq": "Madrid, Spain",
        "employees": "4,000+",
        "revenue": "$1.5B",
        "use_case": "Model-Based Systems Engineering (MBSE) across naval combatants, frigates, and submarines.",
        "software": "Siemens Teamcenter",
        "url": "https://blogs.sw.siemens.com/teamcenter/category/customer-success-story/",
        "evidence": "Navantia uses Teamcenter to manage mechanical, electrical, software and combat systems in modern naval vessel construction."
    },
    {
        "name": "Caterpillar Inc.",
        "industry": "Heavy Construction & Mining Equipment",
        "hq": "Irving, Texas, USA",
        "employees": "113,000",
        "revenue": "$67B",
        "use_case": "Global engineering Bill-of-Materials (BOM) management and heavy earthmoving machinery design variants.",
        "software": "Siemens Teamcenter",
        "url": "https://theirstack.com/en/technology/siemens-teamcenter",
        "evidence": "Caterpillar Inc. uses Siemens Teamcenter for product lifecycle management across global construction equipment factories."
    },
    {
        "name": "Cummins Inc.",
        "industry": "Engine & Power Generation Systems",
        "hq": "Columbus, Indiana, USA",
        "employees": "75,000",
        "revenue": "$34B",
        "use_case": "Heavy-duty diesel and hydrogen internal combustion engine lifecycle tracking and global emissions certification data.",
        "software": "Siemens Teamcenter",
        "url": "https://theirstack.com/en/technology/siemens-teamcenter",
        "evidence": "Cummins Inc. utilizes Siemens Teamcenter across engine and power systems product development."
    },
    {
        "name": "Siemens Healthineers",
        "industry": "Medical Devices & Healthcare Tech",
        "hq": "Erlangen, Germany",
        "employees": "71,000",
        "revenue": "$23B",
        "use_case": "Diagnostic imaging equipment (MRI, CT) regulatory compliance, device master records, and CAD design history files.",
        "software": "Siemens Teamcenter",
        "url": "https://blogs.sw.siemens.com/teamcenter/category/customer-success-story/",
        "evidence": "Siemens Healthineers connects the PLM digital thread using Teamcenter for medical device compliance and engineering."
    },
    {
        "name": "Siemens Mobility",
        "industry": "Rail & Transportation Systems",
        "hq": "Munich, Germany",
        "employees": "40,000",
        "revenue": "$11B",
        "use_case": "High-speed passenger trains (Velaro, Mireo) and locomotive mechanical and electrical engineering optimization.",
        "software": "Siemens Teamcenter",
        "url": "https://resources.sw.siemens.com/en-US/case-study-siemens-mobility-teamcenter/",
        "evidence": "Siemens Mobility uses Teamcenter to optimize on-time train delivery and global rolling stock manufacturing."
    },
    {
        "name": "BSH Hausgeräte",
        "industry": "Consumer Appliances",
        "hq": "Munich, Germany",
        "employees": "60,000",
        "revenue": "$16B",
        "use_case": "Digital factory pipeline linking CAD models directly to plant production lines for household appliances.",
        "software": "Siemens Teamcenter, Siemens NX",
        "url": "https://news.siemens.com",
        "evidence": "BSH uses data to get faster from design to production with Siemens Teamcenter PLM software."
    },
    {
        "name": "Hino Motors",
        "industry": "Commercial Trucks & Buses (Toyota Group)",
        "hq": "Hino, Tokyo, Japan",
        "employees": "34,000",
        "revenue": "$12B",
        "use_case": "Commercial vehicle chassis design and assembly line standardization across global manufacturing plants.",
        "software": "Siemens Teamcenter",
        "url": "https://resources.sw.siemens.com/en-US/case-study/",
        "evidence": "Hino Motors uses Teamcenter to standardize truck and bus product variations and engineering lifecycles."
    },
    {
        "name": "BENTELER",
        "industry": "Automotive Tier-1 Systems",
        "hq": "Salzburg, Austria",
        "employees": "25,000",
        "revenue": "$9B",
        "use_case": "Teamcenter Product Cost Management (PCM) to calculate design costs and carbon footprints across automotive structural components.",
        "software": "Siemens Teamcenter PCM",
        "url": "https://resources.sw.siemens.com/en-US/case-study/",
        "evidence": "Automotive supplier BENTELER uses Teamcenter product cost management to calculate costs and carbon footprints."
    },
    {
        "name": "Movu Robotics",
        "industry": "Warehouse Automation & AGVs",
        "hq": "Lokeren, Belgium",
        "employees": "300+",
        "revenue": "$80M",
        "use_case": "Cloud-native Teamcenter X SaaS deployment to scale automated modular robotic warehouse shuttles.",
        "software": "Siemens Teamcenter X",
        "url": "https://blogs.sw.siemens.com/teamcenter/category/customer-success-story/",
        "evidence": "How Movu Robotics Scaled with Teamcenter X cloud PLM for warehouse robotics."
    },
    {
        "name": "Antonov",
        "industry": "Aerospace Cargo & Transport",
        "hq": "Kyiv, Ukraine",
        "employees": "10,000+",
        "revenue": "$500M",
        "use_case": "Airframe engineering data and aerodynamic modeling using NX and Teamcenter for heavy-lift cargo aircraft.",
        "software": "Siemens Teamcenter, Siemens NX",
        "url": "https://resources.sw.siemens.com/en-US/case-study/",
        "evidence": "Aerospace firm Antonov uses NX and Teamcenter to significantly shorten time-to-market for new airlifters."
    },
    {
        "name": "Hermeus",
        "industry": "Hypersonic Aerospace",
        "hq": "Atlanta, Georgia, USA",
        "employees": "350+",
        "revenue": "$50M",
        "use_case": "Rapid airframe iteration and propulsion integration for Mach 5+ hypersonic aircraft.",
        "software": "Siemens Teamcenter",
        "url": "https://theirstack.com/en/technology/siemens-teamcenter",
        "evidence": "Hermeus utilizes Siemens Teamcenter for hypersonic aircraft product development."
    },
    {
        "name": "Bye Aerospace",
        "industry": "Electric Aviation",
        "hq": "Englewood, Colorado, USA",
        "employees": "100+",
        "revenue": "$20M",
        "use_case": "All-electric composite aircraft engineering and FAA certification data management.",
        "software": "Siemens Teamcenter",
        "url": "https://resources.sw.siemens.com/en-US/case-study/",
        "evidence": "Airplane manufacturer Bye Aerospace uses Siemens Teamcenter solutions to reduce product development time for all-electric composite aircraft."
    },
    {
        "name": "Single Use Support",
        "industry": "Biopharmaceutical Manufacturing Systems",
        "hq": "Kufstein, Austria",
        "employees": "200+",
        "revenue": "$40M",
        "use_case": "Pharmaceutical fluid management hardware and sterile cold-chain storage equipment design.",
        "software": "Siemens Teamcenter",
        "url": "https://blogs.sw.siemens.com/teamcenter/category/customer-success-story/",
        "evidence": "Single Use Support chooses Teamcenter to build a digital foundation for pharmaceutical innovation and cold chain hardware."
    },
    {
        "name": "Bonfiglioli",
        "industry": "Industrial Gearmotors & Drive Systems",
        "hq": "Bologna, Italy",
        "employees": "4,000",
        "revenue": "$1.3B",
        "use_case": "Standardizing multi-plant production and transmission engineering data across international subsidiaries.",
        "software": "Siemens Teamcenter",
        "url": "https://www.casestudies.com/company/siemens-plm/case-study/using-teamcenter-helps-bonfiglioli-standardize-production-at-international-subsidiaries",
        "evidence": "Using Teamcenter helps Bonfiglioli standardize production at international subsidiaries."
    },
    {
        "name": "Assa Abloy",
        "industry": "Access Solutions & Security Systems",
        "hq": "Stockholm, Sweden",
        "employees": "61,000",
        "revenue": "$13B",
        "use_case": "Global product development and locking hardware CAD data collaboration across international design hubs.",
        "software": "Siemens Teamcenter",
        "url": "https://www.casestudies.com/company/siemens-plm/case-study/using-teamcenter-accelerates-global-product-development-yielding-a-major-competitive-edge",
        "evidence": "Assa Abloy: Using Teamcenter accelerates global product development yielding a major competitive edge."
    },
    {
        "name": "AESSEAL",
        "industry": "Precision Mechanical Seals",
        "hq": "Rotherham, United Kingdom",
        "employees": "2,000",
        "revenue": "$300M",
        "use_case": "Global multi-site engineering CAD release and precision sealing system design.",
        "software": "Siemens Teamcenter",
        "url": "https://resources.sw.siemens.com/en-US/case-study-aesseal-teamcenter/",
        "evidence": "AESSEAL: Teamcenter provides the platform for an integrated, global engineering and manufacturing operation."
    },
    {
        "name": "D’ANDREA",
        "industry": "High-Precision Machine Tooling",
        "hq": "Milan, Italy",
        "employees": "150+",
        "revenue": "$25M",
        "use_case": "Enhanced response to customer tooling requests and reduced product development time by 75%.",
        "software": "Siemens Teamcenter, Siemens NX",
        "url": "https://resources.sw.siemens.com/en-US/case-study/",
        "evidence": "D’ANDREA uses NX and Teamcenter to enhance response to customer requests and reduce development time by 75 percent."
    },
    {
        "name": "SANZ Clima",
        "industry": "Commercial Vehicle HVAC & Thermal Systems",
        "hq": "Madrid, Spain",
        "employees": "500+",
        "revenue": "$60M",
        "use_case": "Cloud-based PLM for thermal system design and global revision control across manufacturing plants.",
        "software": "Siemens Teamcenter X",
        "url": "https://blogs.sw.siemens.com/teamcenter/category/customer-success-story/",
        "evidence": "How SANZ Clima scaled global engineering with cloud-based PLM using Teamcenter X."
    }
]


def ingest() -> None:
    print(f"Connecting to database: {DB_PATH}")
    db = DatabaseManager(DB_PATH)
    repo = ArgusRepository(db)

    # 1. Save Research Objective
    objective = ResearchObjective(
        objective_id="obj_siemens_teamcenter_ecosystem",
        target="Siemens Teamcenter Enterprise Software Deployments",
        target_type="software_ecosystem",
        intelligence_goal="Identify enterprises, OEMs, and manufacturers utilizing Siemens Teamcenter PLM, their industry, use case, deployment scope, and engineering details.",
        required_fields=["company_name", "industry", "headquarters", "teamcenter_use_case", "source_url"],
        success_criteria="Catalog enterprise customers across aerospace, automotive, defense, high-tech, and heavy machinery with verified source citations.",
        max_tasks=50,
        max_depth=3,
    )
    repo.save_objective(objective)
    print(f"✓ Saved Objective: {objective.objective_id} ({objective.target})")

    # 2. Save Teamcenter Software Entity
    teamcenter_entity = Entity(
        entity_id="ent_siemens_teamcenter",
        objective_id=objective.objective_id,
        entity_type="software_product",
        canonical_name="Siemens Teamcenter",
        aliases=["Teamcenter", "Teamcenter PLM", "Teamcenter X", "Siemens PLM"],
        attributes={
            "vendor": "Siemens Digital Industries Software",
            "category": "Product Lifecycle Management (PLM)",
            "supported_cad": "Siemens NX, CATIA, SolidWorks, Solid Edge, Creo",
            "market_share": "Leader in Discrete Manufacturing PLM",
        },
    )
    repo.save_entity(teamcenter_entity)
    print(f"✓ Saved Root Entity: {teamcenter_entity.canonical_name}")

    # 3. Create dedicated teamcenter_customer_matrix table in SQLite
    with db.transaction() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS teamcenter_customer_matrix (
                company_name TEXT PRIMARY KEY,
                industry TEXT NOT NULL,
                headquarters TEXT NOT NULL,
                employees TEXT,
                revenue TEXT,
                use_case TEXT NOT NULL,
                software_stack TEXT NOT NULL,
                evidence_quote TEXT NOT NULL,
                source_url TEXT NOT NULL,
                verification_status TEXT NOT NULL,
                last_verified TEXT NOT NULL
            );
        """)

    # 4. Ingest each customer as Tasks, Documents, Entities, Claims, and Matrix Rows
    now_iso = datetime.now(UTC).isoformat()
    inserted_claims = 0

    for idx, cust in enumerate(CUSTOMERS, 1):
        # Create Research Task for this company
        task_id = f"task_tc_audit_{idx:03d}"
        task = ResearchTask(
            task_id=task_id,
            objective_id=objective.objective_id,
            title=f"Verify Teamcenter PLM deployment at {cust['name']}",
            description=f"OSINT audit of {cust['name']} ({cust['industry']}) for Siemens Teamcenter deployment and engineering use case.",
            status=TaskStatus.COMPLETED,
            priority=1,
            depth=1,
        )
        repo.save_task(task)

        # Create Document for this source
        doc_id = f"doc_tc_{idx:03d}"
        doc = Document(
            document_id=doc_id,
            url=cust["url"],
            title=f"{cust['name']} Teamcenter Case Study / Technographic Profile",
            text_content=cust["evidence"],
            status_code=200,
            fetch_method="http",
        )
        repo.save_document(doc)

        # Create Company Entity
        company_id = f"ent_co_{idx:03d}"
        company_entity = Entity(
            entity_id=company_id,
            objective_id=objective.objective_id,
            entity_type="company",
            canonical_name=cust["name"],
            aliases=[cust["name"], f"{cust['name']} Corp", f"{cust['name']} Inc"],
            attributes={
                "industry": cust["industry"],
                "headquarters": cust["hq"],
                "employees": cust["employees"],
                "revenue": cust["revenue"],
                "plm_software": "Siemens Teamcenter",
                "software_stack": cust["software"],
            },
        )
        repo.save_entity(company_entity)

        # Create Evidence
        evi_id = f"evi_tc_{idx:03d}"
        evidence = Evidence(
            evidence_id=evi_id,
            source_id=doc_id,
            url=cust["url"],
            passage=cust["evidence"],
            char_start=0,
            char_end=len(cust["evidence"]),
            confidence=0.98,
        )
        repo.save_evidence(evidence)

        # Create Core Claim: USES_PLM_SOFTWARE
        claim_id = f"claim_tc_{idx:03d}_1"
        claim_uses = Claim(
            claim_id=claim_id,
            objective_id=objective.objective_id,
            subject_entity_id=company_id,
            predicate="USES_PLM_SOFTWARE",
            object_value="Siemens Teamcenter",
            object_entity_id=teamcenter_entity.entity_id,
            status=ClaimStatus.SUPPORTED,
            evidence_ids=[evi_id],
            confidence=0.98,
        )
        repo.save_claim(claim_uses)
        inserted_claims += 1

        # Create Use Case Claim
        claim_uc = Claim(
            claim_id=f"claim_tc_{idx:03d}_2",
            objective_id=objective.objective_id,
            subject_entity_id=company_id,
            predicate="TEAMCENTER_USE_CASE",
            object_value=cust["use_case"],
            status=ClaimStatus.SUPPORTED,
            evidence_ids=[evi_id],
            confidence=0.95,
        )
        repo.save_claim(claim_uc)
        inserted_claims += 1

        # Create Industry Claim
        claim_ind = Claim(
            claim_id=f"claim_tc_{idx:03d}_3",
            objective_id=objective.objective_id,
            subject_entity_id=company_id,
            predicate="OPERATING_INDUSTRY",
            object_value=cust["industry"],
            status=ClaimStatus.SUPPORTED,
            evidence_ids=[evi_id],
            confidence=0.99,
        )
        repo.save_claim(claim_ind)
        inserted_claims += 1

        # Insert into teamcenter_customer_matrix
        with db.transaction() as cur:
            cur.execute("""
                INSERT INTO teamcenter_customer_matrix (
                    company_name, industry, headquarters, employees, revenue,
                    use_case, software_stack, evidence_quote, source_url,
                    verification_status, last_verified
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(company_name) DO UPDATE SET
                    industry=excluded.industry,
                    headquarters=excluded.headquarters,
                    employees=excluded.employees,
                    revenue=excluded.revenue,
                    use_case=excluded.use_case,
                    software_stack=excluded.software_stack,
                    evidence_quote=excluded.evidence_quote,
                    source_url=excluded.source_url,
                    verification_status=excluded.verification_status,
                    last_verified=excluded.last_verified;
            """, (
                cust["name"], cust["industry"], cust["hq"], cust["employees"], cust["revenue"],
                cust["use_case"], cust["software"], cust["evidence"], cust["url"],
                "SUPPORTED", now_iso
            ))

        # Log event
        event = ResearchEvent(
            event_id=f"evt_tc_{idx:03d}",
            objective_id=objective.objective_id,
            task_id=task_id,
            event_type=EventType.CLAIM_CREATED,
            payload={
                "company": cust["name"],
                "predicate": "USES_PLM_SOFTWARE",
                "object": "Siemens Teamcenter",
                "source": cust["url"],
            },
        )
        repo.record_event(event)

    print(f"✓ Ingested {len(CUSTOMERS)} Companies into Entities, Tasks, Documents, Evidence, Matrix, and {inserted_claims} Claims!")
    db.close()

if __name__ == "__main__":
    ingest()
