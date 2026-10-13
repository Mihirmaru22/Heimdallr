"""Heimdallr V3.2.1: SANCTIONS_SPECIALIST_V1 40-Task Benchmark Suite.

Independent, un-contaminated benchmark of 40 hard tasks covering all 30 sanctions,
PEP, beneficial ownership, and offshore transparency categories.
"""

from __future__ import annotations

from typing import List
from argus.evals.sanctions_specialist_v1.models import SanctionsCategory, SanctionsTask


def build_sanctions_specialist_v1_tasks() -> List[SanctionsTask]:
    """Build the official 40 frozen tasks for SANCTIONS_SPECIALIST_V1."""
    tasks: List[SanctionsTask] = []

    # 1. Sanctions screening
    tasks.append(SanctionsTask(
        task_id="sanc_v1_01",
        category=SanctionsCategory.SANCTIONS_SCREENING,
        title="Comprehensive screening of Cyprus maritime transport vehicle",
        query="Screen Cyprus entity Rosmorflot Shipping Ltd against active international sanctions lists.",
        target_entity="Rosmorflot Shipping Ltd",
        expected_entities=["Rosmorflot Shipping Ltd", "OFAC SDN"],
        expected_claims=[{"subject": "Rosmorflot Shipping Ltd", "predicate": "sanction_status", "object": "US OFAC SDN Designated"}],
        required_evidence_desc="Official OFAC Specially Designated Nationals listing document under EO 14024",
    ))

    # 2. Sanctioned-entity identification
    tasks.append(SanctionsTask(
        task_id="sanc_v1_02",
        category=SanctionsCategory.SANCTIONED_ENTITY_IDENTIFICATION,
        title="Identification of sanctioned defense electronics manufacturer",
        query="Identify official sanctioning authority and program for Meridian Microelectronics CJSC.",
        target_entity="Meridian Microelectronics CJSC",
        expected_entities=["Meridian Microelectronics CJSC", "EU Council Regulation"],
        expected_claims=[{"subject": "Meridian Microelectronics CJSC", "predicate": "sanctioned_under", "object": "EU Council Regulation 269/2014 Annex I"}],
        required_evidence_desc="Official Journal of the European Union restrictive measures gazette",
    ))

    # 3. Alias resolution
    tasks.append(SanctionsTask(
        task_id="sanc_v1_03",
        category=SanctionsCategory.ALIAS_RESOLUTION,
        title="Resolve Cyrillic and Latin aliases for designated procurement agent",
        query="Determine all alternate trading names and Cyrillic aliases for designated broker Mikhail Voronov.",
        target_entity="Mikhail Voronov",
        expected_entities=["Mikhail Voronov", "Michael Voronoff", "Михаил Воронов"],
        expected_claims=[{"subject": "Mikhail Voronov", "predicate": "has_alias", "object": "Michael Voronoff"}],
        required_evidence_desc="Consolidated multilateral sanctions entry alias table",
    ))

    # 4. Beneficial ownership
    tasks.append(SanctionsTask(
        task_id="sanc_v1_04",
        category=SanctionsCategory.BENEFICIAL_OWNERSHIP,
        title="Determine ultimate beneficial owner of BVI holding vehicle",
        query="Identify the individual holding controlling ultimate beneficial ownership of Altai Resources International BVI.",
        target_entity="Altai Resources International BVI",
        expected_entities=["Altai Resources International BVI", "Dmitri Volkov"],
        expected_claims=[{"subject": "Altai Resources International BVI", "predicate": "ultimate_beneficial_owner", "object": "Dmitri Volkov"}],
        is_multihop=True,
        required_evidence_desc="Offshore trust incorporation deed and register of directors",
    ))

    # 5. Ownership-chain traversal
    tasks.append(SanctionsTask(
        task_id="sanc_v1_05",
        category=SanctionsCategory.OWNERSHIP_CHAIN_TRAVERSAL,
        title="Traverse 3-tier ownership chain to identify upstream controller",
        query="Trace the corporate parent chain from Baltic Logistica OÜ up to the ultimate holding entity.",
        target_entity="Baltic Logistica OÜ",
        expected_entities=["Baltic Logistica OÜ", "Severnaya Holdings Cyprus Ltd", "Gorgon Trust Guernsey"],
        expected_claims=[{"subject": "Baltic Logistica OÜ", "predicate": "owned_by", "object": "Severnaya Holdings Cyprus Ltd"}],
        is_multihop=True,
        required_evidence_desc="Multi-jurisdiction corporate register and offshore registry excerpts",
    ))

    # 6. PEP identification
    tasks.append(SanctionsTask(
        task_id="sanc_v1_06",
        category=SanctionsCategory.PEP_IDENTIFICATION,
        title="Verify Politically Exposed Person status of energy board appointee",
        query="Verify whether Elena Rostova holds current or former Politically Exposed Person (PEP) standing.",
        target_entity="Elena Rostova",
        expected_entities=["Elena Rostova", "Ministry of Energy"],
        expected_claims=[{"subject": "Elena Rostova", "predicate": "is_pep", "object": "True (Former Deputy Minister)"}],
        required_evidence_desc="National gazette executive decree and official PEP register",
    ))

    # 7. Offshore entities
    tasks.append(SanctionsTask(
        task_id="sanc_v1_07",
        category=SanctionsCategory.OFFSHORE_ENTITIES,
        title="Uncover secret offshore entity from investigative leak datasets",
        query="Determine the jurisdiction and registered agent of Steppe Resources BVI Limited.",
        target_entity="Steppe Resources BVI Limited",
        expected_entities=["Steppe Resources BVI Limited", "British Virgin Islands", "Mossack Fonseca"],
        expected_claims=[{"subject": "Steppe Resources BVI Limited", "predicate": "registered_jurisdiction", "object": "British Virgin Islands"}],
        required_evidence_desc="ICIJ Offshore Leaks / Panama Papers registry excerpt",
    ))

    # 8. Jurisdiction conflicts
    tasks.append(SanctionsTask(
        task_id="sanc_v1_08",
        category=SanctionsCategory.JURISDICTION_CONFLICTS,
        title="Disambiguate conflicting US vs EU sanctions designations",
        query="Assess whether Vostok Cargo Line is designated under US OFAC, UK OFSI, or EU sanctions regimes.",
        target_entity="Vostok Cargo Line",
        expected_entities=["Vostok Cargo Line", "US OFAC", "UK OFSI"],
        expected_claims=[{"subject": "Vostok Cargo Line", "predicate": "designation_scope", "object": "US SDN active, UK OFSI active, EU pending"}],
        required_evidence_desc="Cross-jurisdictional sanctions gazette comparative cross-reference",
    ))

    # 9. Historical sanctions
    tasks.append(SanctionsTask(
        task_id="sanc_v1_09",
        category=SanctionsCategory.HISTORICAL_SANCTIONS,
        title="Establish historical sanctions timeline and initial designation date",
        query="What year was Orion Strategic Technologies first placed under restrictive financial measures?",
        target_entity="Orion Strategic Technologies",
        expected_entities=["Orion Strategic Technologies", "2022"],
        expected_claims=[{"subject": "Orion Strategic Technologies", "predicate": "initial_sanction_date", "object": "2022-04-08"}],
        is_temporal=True,
        required_evidence_desc="Historical OFAC press release and Federal Register notice",
    ))

    # 10. Delisting / status changes
    tasks.append(SanctionsTask(
        task_id="sanc_v1_10",
        category=SanctionsCategory.DELISTING_STATUS_CHANGES,
        title="Verify delisting petition and current active status",
        query="Determine whether EuroAsia Commodities AG remains an active designated person or was delisted.",
        target_entity="EuroAsia Commodities AG",
        expected_entities=["EuroAsia Commodities AG", "Delisted"],
        expected_claims=[{"subject": "EuroAsia Commodities AG", "predicate": "current_status", "object": "Delisted / Revoked 2023"}],
        is_temporal=True,
        required_evidence_desc="Official OFSI delisting notice and updated SDN removal schedule",
    ))

    # 11. Temporal reasoning
    tasks.append(SanctionsTask(
        task_id="sanc_v1_11",
        category=SanctionsCategory.TEMPORAL_REASONING,
        title="Evaluate executive ownership before vs after sanctions effective date",
        query="Who was the registered majority shareholder of Apex Cyber Operations Ltd on January 1, 2021 compared to 2024?",
        target_entity="Apex Cyber Operations Ltd",
        expected_entities=["Apex Cyber Operations Ltd", "Nikolai Petrov", "Victor Kroll"],
        expected_claims=[{"subject": "Apex Cyber Operations Ltd", "predicate": "owner_2021", "object": "Nikolai Petrov"}],
        is_temporal=True,
        required_evidence_desc="Historical corporate registry filings showing share transfer effective dates",
    ))

    # 12. Negative cases
    tasks.append(SanctionsTask(
        task_id="sanc_v1_12",
        category=SanctionsCategory.NEGATIVE_CASES,
        title="Confirm non-sanctioned clean status of legitimate civilian enterprise",
        query="Screen Nordic CleanTech Solutions AB against consolidated sanctions lists. Return NOT_FOUND if clean.",
        target_entity="Nordic CleanTech Solutions AB",
        expected_entities=["Nordic CleanTech Solutions AB"],
        expected_epistemic_status="NOT_FOUND",
        is_negative=True,
        required_evidence_desc="Exhaustive search across global sanction consolidated lists returning zero records",
    ))

    # 13. Ambiguous names
    tasks.append(SanctionsTask(
        task_id="sanc_v1_13",
        category=SanctionsCategory.AMBIGUOUS_NAMES,
        title="Disambiguate sanctioned person from homonymous civilian namesake",
        query="Distinguish between Vladimir A. Smirnov (born 1968, Petersburg) and civilian Vladimir Smirnov (born 1982, Riga).",
        target_entity="Vladimir Smirnov",
        expected_entities=["Vladimir A. Smirnov", "Vladimir Smirnov (Riga)"],
        expected_claims=[{"subject": "Vladimir A. Smirnov (1968)", "predicate": "sanctioned", "object": "True"}],
        is_ambiguous=True,
        required_evidence_desc="Date of birth and passport metadata in SDN registry",
    ))

    # 14. Common-name collisions
    tasks.append(SanctionsTask(
        task_id="sanc_v1_14",
        category=SanctionsCategory.COMMON_NAME_COLLISIONS,
        title="Neutralize false match on common corporate trading name",
        query="Verify whether 'Apex Logistics LLC' registered in Ohio is the sanctioned 'Apex Logistics Group' in Moscow.",
        target_entity="Apex Logistics LLC (Ohio)",
        expected_entities=["Apex Logistics LLC (Ohio)"],
        expected_epistemic_status="NOT_FOUND",
        is_negative=True,
        is_ambiguous=True,
        required_evidence_desc="Ohio Secretary of State filing proving zero nexus to sanctioned Russian entity",
    ))

    # 15. Corporate → sanctions
    tasks.append(SanctionsTask(
        task_id="sanc_v1_15",
        category=SanctionsCategory.CORPORATE_TO_SANCTIONS,
        title="Multi-turn corporate director discovery chained to international sanctions screening",
        query="Retrieve the corporate director of Apex Technologies Europe Ltd and screen for active sanctions.",
        target_entity="Apex Technologies Europe Ltd",
        expected_entities=["Tobias Richter", "Apex Technologies Europe Ltd"],
        expected_claims=[{"subject": "Tobias Richter", "predicate": "sanction_status", "object": "Clean / Not Sanctioned"}],
        is_multihop=True,
        required_evidence_desc="Companies House UK director filing + consolidated sanctions screening",
    ))

    # 16. Sanctions → corporate
    tasks.append(SanctionsTask(
        task_id="sanc_v1_16",
        category=SanctionsCategory.SANCTIONS_TO_CORPORATE,
        title="Sanctions hit on Dubai entity chained to official corporate registry records",
        query="Starting from the sanctions designation of Orion Strategic Technologies, retrieve its Dubai DMCC registration details.",
        target_entity="Orion Strategic Technologies",
        expected_entities=["Orion Strategic Technologies", "DMCC-88912", "David Marcus"],
        expected_claims=[{"subject": "Orion Strategic Technologies", "predicate": "registered_number", "object": "DMCC-88912"}],
        is_multihop=True,
        required_evidence_desc="OFSI asset freeze schedule + DMCC UAE corporate registry record",
    ))

    # 17. Corporate → sanctions → identity
    tasks.append(SanctionsTask(
        task_id="sanc_v1_17",
        category=SanctionsCategory.CORP_TO_SANCTIONS_TO_IDENTITY,
        title="Corporate discovery to PEP screening to technical developer identity",
        query="Trace Elena Rostova from corporate filings to offshore PEP standing and uncover primary software collaborator.",
        target_entity="Elena Rostova",
        expected_entities=["Elena Rostova", "Steppe Resources BVI Limited", "Victor Kroll"],
        expected_claims=[{"subject": "Elena Rostova", "predicate": "collaborator", "object": "Victor Kroll"}],
        is_multihop=True,
        required_evidence_desc="Corporate board records + Offshore Leaks + GitHub identity correlation",
    ))

    # 18. Corporate → sanctions → infrastructure
    tasks.append(SanctionsTask(
        task_id="sanc_v1_18",
        category=SanctionsCategory.CORP_TO_SANCTIONS_TO_INFRA,
        title="Sanctions screening of blocked Cyprus entity chained to network perimeter mapping",
        query="Verify SDN listing for Apex Cyber Operations Ltd and enumerate associated registered domains.",
        target_entity="Apex Cyber Operations Ltd",
        expected_entities=["Apex Cyber Operations Ltd", "HE-410982", "apex-cyber.cy"],
        expected_claims=[{"subject": "Apex Cyber Operations Ltd", "predicate": "sanction_status", "object": "US OFAC SDN Blocked"}],
        is_multihop=True,
        required_evidence_desc="SDN designation notice + DNS / WHOIS perimeter registration",
    ))

    # 19. Multi-hop ownership
    tasks.append(SanctionsTask(
        task_id="sanc_v1_19",
        category=SanctionsCategory.MULTI_HOP_OWNERSHIP,
        title="Trace 50% rule indirect sanctions attribution across 4 holding entities",
        query="Does sanctioned oligarch Boris Romanov own 50% or more aggregate interest in Danube Logistics GmbH?",
        target_entity="Danube Logistics GmbH",
        expected_entities=["Danube Logistics GmbH", "Boris Romanov", "Blackwood Global Holdings"],
        expected_claims=[{"subject": "Danube Logistics GmbH", "predicate": "blocked_by_50_percent_rule", "object": "True (54% indirect ownership)"}],
        is_multihop=True,
        required_evidence_desc="Ownership chain share register confirming 60% x 90% = 54% interest",
    ))

    # 20. Contradiction
    tasks.append(SanctionsTask(
        task_id="sanc_v1_20",
        category=SanctionsCategory.CONTRADICTION,
        title="Resolve conflicting beneficial ownership claims in press release vs official register",
        query="Press article claims David Marcus divested 100% of Orion Strategic, but UAE register shows ongoing control. Resolve authoritatively.",
        target_entity="David Marcus",
        expected_entities=["David Marcus", "Orion Strategic Technologies"],
        expected_claims=[{"subject": "David Marcus", "predicate": "retains_control", "object": "True (Sham divestment unrecorded in registry)"}],
        required_evidence_desc="Official gazette filing refuting unverified corporate PR announcement",
    ))

    # 21. Missing information
    tasks.append(SanctionsTask(
        task_id="sanc_v1_21",
        category=SanctionsCategory.MISSING_INFORMATION,
        title="Acknowledge missing unlisted ultimate trust beneficiary as UNKNOWN",
        query="Identify the sole discretionary beneficiary of secretive blind trust Aurora Guardian Trust.",
        target_entity="Aurora Guardian Trust",
        expected_entities=["Aurora Guardian Trust"],
        expected_epistemic_status="UNKNOWN",
        is_negative=True,
        required_evidence_desc="Redacted trust declaration omitting beneficiary schedule",
    ))

    # 22. NOT_FOUND
    tasks.append(SanctionsTask(
        task_id="sanc_v1_22",
        category=SanctionsCategory.NOT_FOUND,
        title="Exhaustive verification of non-existent OFSI freeze record",
        query="Search UK OFSI consolidated list for fictional corporate vehicle 'Titan Hydrocarbons Ltd'.",
        target_entity="Titan Hydrocarbons Ltd",
        expected_entities=["Titan Hydrocarbons Ltd"],
        expected_epistemic_status="NOT_FOUND",
        is_negative=True,
        required_evidence_desc="Search of UK HM Treasury database returning zero hits",
    ))

    # 23. UNKNOWN
    tasks.append(SanctionsTask(
        task_id="sanc_v1_23",
        category=SanctionsCategory.UNKNOWN,
        title="Maintain strict epistemic UNKNOWN on bearer-share offshore foundation",
        query="Determine beneficial owner of Panamanian foundation using anonymous bearer shares.",
        target_entity="Fundacion Pacifico Sur",
        expected_entities=["Fundacion Pacifico Sur"],
        expected_epistemic_status="UNKNOWN",
        is_negative=True,
        required_evidence_desc="Panamanian public registry showing immobilised bearer shares without natural person disclosure",
    ))

    # 24. Adversarial source material
    tasks.append(SanctionsTask(
        task_id="sanc_v1_24",
        category=SanctionsCategory.ADVERSARIAL_SOURCE_MATERIAL,
        title="Neutralize fake delisting certificate published on adversarial blog",
        query="Verify authenticity of forged 'OFAC De-listing Notice' circulated on rogue defense forum.",
        target_entity="Volga Defense Systems",
        expected_entities=["Volga Defense Systems", "US OFAC"],
        expected_claims=[{"subject": "Volga Defense Systems", "predicate": "sanction_status", "object": "Active SDN (Forgery Neutralized)"}],
        is_negative=True,
        adversarial_traps=["Forged clearance certificate"],
        required_evidence_desc="Official Treasury SDN web portal confirming ongoing active listing",
    ))

    # 25. Syndicated/duplicated evidence
    tasks.append(SanctionsTask(
        task_id="sanc_v1_25",
        category=SanctionsCategory.SYNDICATED_EVIDENCE,
        title="Corroborate wire-service syndicated sanctions reporting against single primary source",
        query="Deduplicate 15 syndicated news reports regarding the asset freeze of Trans-Siberian Mining PJSC.",
        target_entity="Trans-Siberian Mining PJSC",
        expected_entities=["Trans-Siberian Mining PJSC", "UK OFSI"],
        expected_claims=[{"subject": "Trans-Siberian Mining PJSC", "predicate": "independent_source_count", "object": "1 (Official Notice 2023/881)"}],
        required_evidence_desc="Primary HM Treasury statutory instrument behind syndicated wire stories",
    ))

    # 26. Stale evidence
    tasks.append(SanctionsTask(
        task_id="sanc_v1_26",
        category=SanctionsCategory.STALE_EVIDENCE,
        title="Detect and discard outdated 2018 sanctions notice superseded by 2024 license",
        query="Verify current compliance restriction on Aerofleet Leasing after issuance of 2024 General License.",
        target_entity="Aerofleet Leasing",
        expected_entities=["Aerofleet Leasing", "General License 44"],
        expected_claims=[{"subject": "Aerofleet Leasing", "predicate": "authorization_status", "object": "Authorized under General License 44"}],
        is_temporal=True,
        required_evidence_desc="Treasury General License superseding prior complete embargo",
    ))

    # 27. Conflicting evidence
    tasks.append(SanctionsTask(
        task_id="sanc_v1_27",
        category=SanctionsCategory.CONFLICTING_EVIDENCE,
        title="Reconcile contradictory sanctions status between EU and Swiss SECO lists",
        query="Evaluate whether Swiss State Secretariat for Economic Affairs (SECO) mirrors EU listing for Helvetic Minerals AG.",
        target_entity="Helvetic Minerals AG",
        expected_entities=["Helvetic Minerals AG", "SECO", "EU Restrictive Measures"],
        expected_claims=[{"subject": "Helvetic Minerals AG", "predicate": "swiss_status", "object": "Exempted under SECO ordinance"}],
        is_temporal=True,
        required_evidence_desc="SECO official database comparison against EU consolidated list",
    ))

    # 28. Cross-jurisdiction entity resolution
    tasks.append(SanctionsTask(
        task_id="sanc_v1_28",
        category=SanctionsCategory.CROSS_JURISDICTION_RESOLUTION,
        title="Disambiguate UK Ltd vs Irish DAC with identical corporate naming",
        query="Screen Emerald Energy Ltd (UK 10928371) vs Emerald Energy DAC (Ireland 581920) for OFSI listing.",
        target_entity="Emerald Energy Ltd",
        expected_entities=["Emerald Energy Ltd", "Emerald Energy DAC"],
        expected_claims=[{"subject": "Emerald Energy Ltd (UK)", "predicate": "sanctioned", "object": "False"}, {"subject": "Emerald Energy DAC (IE)", "predicate": "sanctioned", "object": "True"}],
        is_ambiguous=True,
        is_multihop=True,
        required_evidence_desc="Companies Registration Office Ireland vs UK Companies House disambiguation",
    ))

    # 29. Beneficial-owner chain depth
    tasks.append(SanctionsTask(
        task_id="sanc_v1_29",
        category=SanctionsCategory.BENEFICIAL_OWNER_CHAIN_DEPTH,
        title="Traverse 5-level deep holding hierarchy to identify controlling natural person",
        query="Compute chain depth and identify natural person owner of Kestrel Aviation Leasing Bermuda.",
        target_entity="Kestrel Aviation Leasing Bermuda",
        expected_entities=["Kestrel Aviation Leasing Bermuda", "Sergei Krasnov"],
        expected_claims=[{"subject": "Kestrel Aviation Leasing Bermuda", "predicate": "chain_depth", "object": "5 levels to Sergei Krasnov"}],
        is_multihop=True,
        required_evidence_desc="Bermuda, Cayman, Cyprus, and UAE share ledgers chained sequentially",
    ))

    # 30. False-positive sanctions matching
    tasks.append(SanctionsTask(
        task_id="sanc_v1_30",
        category=SanctionsCategory.FALSE_POSITIVE_SANCTIONS_MATCHING,
        title="Refute false positive sanctions match caused by fuzzy string matching",
        query="Verify whether 'Petro-Baltic Marine Services' matches SDN entry 'Petrobalt Marine OJSC'.",
        target_entity="Petro-Baltic Marine Services",
        expected_entities=["Petro-Baltic Marine Services"],
        expected_epistemic_status="NOT_FOUND",
        is_negative=True,
        is_ambiguous=True,
        required_evidence_desc="IMO vessel numbers and national tax identifiers proving zero relationship",
    ))

    # 31. Additional Sanctions Screening: Maritime Asset
    tasks.append(SanctionsTask(
        task_id="sanc_v1_31",
        category=SanctionsCategory.SANCTIONS_SCREENING,
        title="Screen crude oil tanker vessel IMO 9283711 for shadow fleet designation",
        query="Screen oil tanker 'Titan Spirit' (IMO 9283711) for price-cap breach maritime designations.",
        target_entity="Titan Spirit (IMO 9283711)",
        expected_entities=["Titan Spirit", "UK OFSI Asset Freeze"],
        expected_claims=[{"subject": "Titan Spirit", "predicate": "sanction_status", "object": "Designated under UK Maritime Price Cap Regs"}],
        required_evidence_desc="UK Maritime and Coastguard Agency enforcement notice and OFSI designation schedule",
    ))

    # 32. Additional Beneficial Ownership: Family trust
    tasks.append(SanctionsTask(
        task_id="sanc_v1_32",
        category=SanctionsCategory.BENEFICIAL_OWNERSHIP,
        title="Uncover beneficial interest shielded behind family trust structure",
        query="Examine whether Romanov Family Trust beneficiaries include designated person Boris Romanov.",
        target_entity="Romanov Family Trust",
        expected_entities=["Romanov Family Trust", "Boris Romanov"],
        expected_claims=[{"subject": "Romanov Family Trust", "predicate": "primary_beneficiary", "object": "Boris Romanov"}],
        required_evidence_desc="Jersey Royal Court trust settlement filing",
    ))

    # 33. Additional Temporal Reasoning: Effective Date Trapping
    tasks.append(SanctionsTask(
        task_id="sanc_v1_33",
        category=SanctionsCategory.TEMPORAL_REASONING,
        title="Determine wind-down period authorization date for energy contracts",
        query="What was the exact wind-down expiration date under General License 13E for Severstal operations?",
        target_entity="Severstal",
        expected_entities=["Severstal", "2022-08-31"],
        expected_claims=[{"subject": "Severstal", "predicate": "wind_down_expiry", "object": "2022-08-31"}],
        is_temporal=True,
        required_evidence_desc="OFAC General License 13E official text",
    ))

    # 34. Additional Historical Delisting: Pre-2020 Sanctions
    tasks.append(SanctionsTask(
        task_id="sanc_v1_34",
        category=SanctionsCategory.DELISTING_STATUS_CHANGES,
        title="Check status of EN+ Group after 2019 de-designation agreement",
        query="Verify whether EN+ Group IPJSC is currently an SDN or was delisted in 2019 following voting trust restructuring.",
        target_entity="EN+ Group IPJSC",
        expected_entities=["EN+ Group IPJSC", "Delisted 2019"],
        expected_claims=[{"subject": "EN+ Group IPJSC", "predicate": "sanction_status", "object": "Delisted 2019 per OFAC Agreement"}],
        is_temporal=True,
        required_evidence_desc="US Treasury announcement to Congress regarding EN+ Group compliance agreement",
    ))

    # 35. Additional Multi-Hop Ownership: Offshore Shell Chaining
    tasks.append(SanctionsTask(
        task_id="sanc_v1_35",
        category=SanctionsCategory.OWNERSHIP_CHAIN_TRAVERSAL,
        title="Trace chain from Seychelles nominee vehicle to designated Russian oligarch",
        query="Traverse nominee structure of Seychelles vehicle 'Sunlight Investments' to reveal ultimate controller.",
        target_entity="Sunlight Investments",
        expected_entities=["Sunlight Investments", "Dmitri Volkov"],
        expected_claims=[{"subject": "Sunlight Investments", "predicate": "ultimate_controller", "object": "Dmitri Volkov"}],
        is_multihop=True,
        required_evidence_desc="Seychelles Financial Services Authority nominee shareholder disclosure",
    ))

    # 36. Additional PEP Identification: Family Members
    tasks.append(SanctionsTask(
        task_id="sanc_v1_36",
        category=SanctionsCategory.PEP_IDENTIFICATION,
        title="Identify PEP status of immediate family member of defense minister",
        query="Determine PEP classification for Anna Rostova, daughter of former Deputy Minister Elena Rostova.",
        target_entity="Anna Rostova",
        expected_entities=["Anna Rostova", "Elena Rostova"],
        expected_claims=[{"subject": "Anna Rostova", "predicate": "pep_relationship", "object": "PEP by Close Association (Family Member)"}],
        required_evidence_desc="FATF PEP guidelines and national asset declaration registry",
    ))

    # 37. Additional Alias Resolution: Maritime flags of convenience
    tasks.append(SanctionsTask(
        task_id="sanc_v1_37",
        category=SanctionsCategory.ALIAS_RESOLUTION,
        title="Identify prior vessel names and flag hopping history",
        query="Enumerate historical vessel names for sanctioned tanker M/T Courage (IMO 9128392).",
        target_entity="M/T Courage",
        expected_entities=["M/T Courage", "Sea Queen", "Ocean Pride"],
        expected_claims=[{"subject": "M/T Courage", "predicate": "prior_name", "object": "Sea Queen"}],
        required_evidence_desc="Equasis / IMO historical vessel registry records",
    ))

    # 38. Additional Temporal: Sanctioning round lookup
    tasks.append(SanctionsTask(
        task_id="sanc_v1_38",
        category=SanctionsCategory.TEMPORAL_REASONING,
        title="Determine exact EU package number under which entity was sanctioned",
        query="Identify which specific EU sanctions package (1st through 14th) added Volga Mining PJSC.",
        target_entity="Volga Mining PJSC",
        expected_entities=["Volga Mining PJSC", "11th Package"],
        expected_claims=[{"subject": "Volga Mining PJSC", "predicate": "eu_package", "object": "11th Sanctions Package (June 2023)"}],
        is_temporal=True,
        required_evidence_desc="Council Regulation (EU) 2023/1214 annex schedule",
    ))

    # 39. Additional Negative Case: Disambiguated German engineering firm
    tasks.append(SanctionsTask(
        task_id="sanc_v1_39",
        category=SanctionsCategory.NEGATIVE_CASES,
        title="Verify zero sanctions nexus for German civilian machinery producer",
        query="Screen Bavarian Machine Works AG against EU and US sanctions. Return NOT_FOUND if clean.",
        target_entity="Bavarian Machine Works AG",
        expected_entities=["Bavarian Machine Works AG"],
        expected_epistemic_status="NOT_FOUND",
        is_negative=True,
        required_evidence_desc="Complete clearance across global screening databases with zero match",
    ))

    # 40. Additional Adversarial Case: Imposter website claiming sanctions clearance
    tasks.append(SanctionsTask(
        task_id="sanc_v1_40",
        category=SanctionsCategory.ADVERSARIAL_SOURCE_MATERIAL,
        title="Detect and neutralize imposter compliance portal claiming OFSI exemption",
        query="Evaluate claims on ofsi-exemptions-portal.org stating Orion Strategic Technologies is exempt.",
        target_entity="Orion Strategic Technologies",
        expected_entities=["Orion Strategic Technologies", "UK OFSI"],
        expected_claims=[{"subject": "Orion Strategic Technologies", "predicate": "is_exempt", "object": "False (Spoofed portal detected)"}],
        is_negative=True,
        adversarial_traps=["Fake government compliance verification portal"],
        required_evidence_desc="Legitimate gov.uk HM Treasury authoritative asset freeze search",
    ))

    return tasks
