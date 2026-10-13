"""Heimdallr V3.2: SPECIALIST_COMPETITION_V1 Task Fixtures.

Contains 40 structured tasks testing:
1. incumbent wins (broad unstructured research)
2. challenger wins (structured sanctions & offshore tracing)
3. coexistence is optimal (multi-hop corporate + sanctions)
4. candidate unavailable / degraded handling
5. candidate introduces evidence regression
6. candidate is license-incompatible
7. candidate has security regression
Across all required dimensions: normal, hard, ambiguous, negative, temporal,
contradictory, adversarial, missing-info, evidence-grounding, multi-hop.
"""

from __future__ import annotations

from typing import List

from argus.competition.models import CompetitionDecisionType
from argus.evals.specialist_competition.models import CompetitionTaskCategory, CompetitionTaskV1


def build_specialist_competition_v1_tasks() -> List[CompetitionTaskV1]:
    """Generate 40 canonical competition benchmark tasks."""
    tasks: List[CompetitionTaskV1] = []

    # -------------------------------------------------------------------------
    # 1. NORMAL (4 tasks) - Direct structured sanctions / PEP queries
    # -------------------------------------------------------------------------
    tasks.append(CompetitionTaskV1(
        task_id="cmp_norm_01_ofac_sdn_lookup",
        category=CompetitionTaskCategory.NORMAL,
        question_text="Determine whether Victor Kroll is designated on the US OFAC SDN sanctions list.",
        required_evidence=["US OFAC Specially Designated Nationals SDN record for Victor Kroll"],
        related_entities=["Victor Kroll"],
        expected_capabilities=["sanctions_and_beneficial_ownership"],
        expected_winner="challenger",
        expected_decision=CompetitionDecisionType.RECRUIT_NEW_CAPABILITY,
        target_evidence_type="OFAC_SDN_ENTRY",
    ))
    tasks.append(CompetitionTaskV1(
        task_id="cmp_norm_02_uk_ofsi_listing",
        category=CompetitionTaskCategory.NORMAL,
        question_text="Verify whether Orion Strategic Technologies is subject to UK OFSI asset freeze sanctions.",
        required_evidence=["UK OFSI consolidated sanctions record for Orion Strategic Technologies"],
        related_entities=["Orion Strategic Technologies"],
        expected_capabilities=["sanctions_and_beneficial_ownership"],
        expected_winner="challenger",
        expected_decision=CompetitionDecisionType.RECRUIT_NEW_CAPABILITY,
        target_evidence_type="UK_OFSI_ENTRY",
    ))
    tasks.append(CompetitionTaskV1(
        task_id="cmp_norm_03_pep_screening",
        category=CompetitionTaskCategory.NORMAL,
        question_text="Screen Elena Rostova against international Politically Exposed Persons PEP registries.",
        required_evidence=["PEP declaration record confirming political role for Elena Rostova"],
        related_entities=["Elena Rostova"],
        expected_capabilities=["sanctions_and_beneficial_ownership"],
        expected_winner="challenger",
        expected_decision=CompetitionDecisionType.RECRUIT_NEW_CAPABILITY,
        target_evidence_type="PEP_DISCLOSURE",
    ))
    tasks.append(CompetitionTaskV1(
        task_id="cmp_norm_04_offshore_panama_leak",
        category=CompetitionTaskCategory.NORMAL,
        question_text="Retrieve offshore corporate registration and registered agent for Steppe Resources BVI Limited.",
        required_evidence=["ICIJ Offshore Leaks record for Steppe Resources BVI Limited"],
        related_entities=["Steppe Resources BVI Limited"],
        expected_capabilities=["sanctions_and_beneficial_ownership"],
        expected_winner="challenger",
        expected_decision=CompetitionDecisionType.RECRUIT_NEW_CAPABILITY,
        target_evidence_type="OFFSHORE_LEAKS_RECORD",
    ))

    # -------------------------------------------------------------------------
    # 2. HARD (4 tasks) - Alias matching, multi-jurisdiction shell tracing
    # -------------------------------------------------------------------------
    tasks.append(CompetitionTaskV1(
        task_id="cmp_hard_01_alias_obfuscation",
        category=CompetitionTaskCategory.HARD,
        question_text="Investigate whether the handle '0x_vkroll' resolves to a sanctioned individual.",
        required_evidence=["US OFAC SDN alias record connecting 0x_vkroll to Victor Kroll"],
        related_entities=["0x_vkroll"],
        expected_capabilities=["sanctions_and_beneficial_ownership"],
        expected_winner="challenger",
        expected_decision=CompetitionDecisionType.RECRUIT_NEW_CAPABILITY,
        target_evidence_type="OFAC_SDN_ENTRY",
    ))
    tasks.append(CompetitionTaskV1(
        task_id="cmp_hard_02_cyprus_shell_trace",
        category=CompetitionTaskCategory.HARD,
        question_text="Trace the beneficial owners of Cyprus-registered entity Apex Cyber Operations Ltd.",
        required_evidence=["Beneficial ownership record for Apex Cyber Operations Ltd"],
        related_entities=["Apex Cyber Operations Ltd"],
        expected_capabilities=["sanctions_and_beneficial_ownership"],
        expected_winner="challenger",
        expected_decision=CompetitionDecisionType.RECRUIT_NEW_CAPABILITY,
        target_evidence_type="OFAC_SDN_ENTRY",
    ))
    tasks.append(CompetitionTaskV1(
        task_id="cmp_hard_03_dubai_fze_ofsi_match",
        category=CompetitionTaskCategory.HARD,
        question_text="Cross-reference Orion Strategic Tech FZE against HM Treasury sanctions lists.",
        required_evidence=["UK OFSI asset freeze entry for Orion Strategic Tech"],
        related_entities=["Orion Strategic Tech FZE"],
        expected_capabilities=["sanctions_and_beneficial_ownership"],
        expected_winner="challenger",
        expected_decision=CompetitionDecisionType.RECRUIT_NEW_CAPABILITY,
        target_evidence_type="UK_OFSI_ENTRY",
    ))
    tasks.append(CompetitionTaskV1(
        task_id="cmp_hard_04_cayman_trust_ubo",
        category=CompetitionTaskCategory.HARD,
        question_text="Determine the ultimate controlling individual behind Cayman trust Blackwood Global Holdings.",
        required_evidence=["Offshore trust disclosure connecting Blackwood Global Holdings to Victor Kroll"],
        related_entities=["Blackwood Global Holdings"],
        expected_capabilities=["sanctions_and_beneficial_ownership"],
        expected_winner="challenger",
        expected_decision=CompetitionDecisionType.RECRUIT_NEW_CAPABILITY,
        target_evidence_type="OFFSHORE_LEAKS_RECORD",
    ))

    # -------------------------------------------------------------------------
    # 3. AMBIGUOUS (3 tasks) - Natural language without domain keywords
    # -------------------------------------------------------------------------
    tasks.append(CompetitionTaskV1(
        task_id="cmp_amb_01_regulatory_blacklisting",
        category=CompetitionTaskCategory.AMBIGUOUS,
        question_text="Has RedStar Navigation GmbH been formally placed on any government commercial restrictions list?",
        required_evidence=["EU Council Regulation 269/2014 Annex I listing for RedStar Navigation"],
        related_entities=["RedStar Navigation GmbH"],
        expected_capabilities=["sanctions_and_beneficial_ownership"],
        expected_winner="challenger",
        expected_decision=CompetitionDecisionType.RECRUIT_NEW_CAPABILITY,
        target_evidence_type="EU_SANCTIONS_ENTRY",
    ))
    tasks.append(CompetitionTaskV1(
        task_id="cmp_amb_02_high_risk_individual_status",
        category=CompetitionTaskCategory.AMBIGUOUS,
        question_text="Does government compliance screening flag Elena Rostova as a high-risk political individual?",
        required_evidence=["PEP declaration record confirming Elena Rostova political role"],
        related_entities=["Elena Rostova"],
        expected_capabilities=["sanctions_and_beneficial_ownership"],
        expected_winner="challenger",
        expected_decision=CompetitionDecisionType.RECRUIT_NEW_CAPABILITY,
        target_evidence_type="PEP_DISCLOSURE",
    ))
    tasks.append(CompetitionTaskV1(
        task_id="cmp_amb_03_caribbean_bearer_shares",
        category=CompetitionTaskCategory.AMBIGUOUS,
        question_text="Does Pan-Eurasian Nominee Holdings SA operate disguised bearer shares in Latin America?",
        required_evidence=["Pandora Papers offshore intermediary disclosure for Pan-Eurasian Nominee Holdings"],
        related_entities=["Pan-Eurasian Nominee Holdings SA"],
        expected_capabilities=["sanctions_and_beneficial_ownership"],
        expected_winner="challenger",
        expected_decision=CompetitionDecisionType.RECRUIT_NEW_CAPABILITY,
        target_evidence_type="OFFSHORE_LEAKS_RECORD",
    ))

    # -------------------------------------------------------------------------
    # 4. NEGATIVE / INCUMBENT SUPERIORITY (4 tasks) - Clean entities / General Web
    # -------------------------------------------------------------------------
    tasks.append(CompetitionTaskV1(
        task_id="cmp_neg_01_clean_entity_broad_news",
        category=CompetitionTaskCategory.NEGATIVE,
        question_text="Summarize recent consumer software press releases regarding the general product suite.",
        required_evidence=["Public news articles and marketing overviews"],
        related_entities=["Consumer Software Group"],
        expected_capabilities=["general_web_research"],
        expected_winner="incumbent",  # Argus generalist wins on broad open-web news
        expected_decision=CompetitionDecisionType.COEXIST,
        target_evidence_type="GENERAL_WEB_PAGE",
    ))
    tasks.append(CompetitionTaskV1(
        task_id="cmp_neg_02_academic_preprint_abstract",
        category=CompetitionTaskCategory.NEGATIVE,
        question_text="Retrieve academic preprints discussing quantum gravity published in open science repositories.",
        required_evidence=["Academic preprint papers and research abstracts"],
        related_entities=["Quantum Physics Collective"],
        expected_capabilities=["general_web_research"],
        expected_winner="incumbent",
        expected_decision=CompetitionDecisionType.COEXIST,
        target_evidence_type="GENERAL_WEB_PAGE",
    ))
    tasks.append(CompetitionTaskV1(
        task_id="cmp_neg_03_tech_keynote_presentation",
        category=CompetitionTaskCategory.NEGATIVE,
        question_text="Summarize the chief scientist's keynote speech given at Developer Conference 2023.",
        required_evidence=["Conference press coverage and transcript articles"],
        related_entities=["Developer Conference 2023"],
        expected_capabilities=["general_web_research"],
        expected_winner="incumbent",
        expected_decision=CompetitionDecisionType.COEXIST,
        target_evidence_type="GENERAL_WEB_PAGE",
    ))
    tasks.append(CompetitionTaskV1(
        task_id="cmp_neg_04_unsanctioned_firm_trade_news",
        category=CompetitionTaskCategory.NEGATIVE,
        question_text="What do trade magazines report regarding regional automotive logistics trends?",
        required_evidence=["Trade magazine articles and logistics commentary"],
        related_entities=["Regional Logistics Group"],
        expected_capabilities=["general_web_research"],
        expected_winner="incumbent",
        expected_decision=CompetitionDecisionType.COEXIST,
        target_evidence_type="GENERAL_WEB_PAGE",
    ))

    # -------------------------------------------------------------------------
    # 5. TEMPORAL (3 tasks) - Historical vs active sanctions status
    # -------------------------------------------------------------------------
    tasks.append(CompetitionTaskV1(
        task_id="cmp_tmp_01_ofac_listing_date_2022",
        category=CompetitionTaskCategory.TEMPORAL,
        question_text="On what exact date was Victor Kroll formally added to the OFAC SDN registry?",
        required_evidence=["OFAC SDN record listing date 2022-04-15 for Victor Kroll"],
        related_entities=["Victor Kroll"],
        temporal_context={"as_of_date": "2022-04-15"},
        expected_capabilities=["sanctions_and_beneficial_ownership"],
        expected_winner="challenger",
        expected_decision=CompetitionDecisionType.RECRUIT_NEW_CAPABILITY,
        target_evidence_type="OFAC_SDN_ENTRY",
    ))
    tasks.append(CompetitionTaskV1(
        task_id="cmp_tmp_02_uk_ofsi_listing_date_2023",
        category=CompetitionTaskCategory.TEMPORAL,
        question_text="Confirm whether Orion Strategic Technologies was designated under UK sanctions prior to 2023.",
        required_evidence=["UK OFSI temporal listing history for Orion Strategic Technologies"],
        related_entities=["Orion Strategic Technologies"],
        temporal_context={"as_of_date": "2023-01-01"},
        expected_capabilities=["sanctions_and_beneficial_ownership"],
        expected_winner="challenger",
        expected_decision=CompetitionDecisionType.RECRUIT_NEW_CAPABILITY,
        target_evidence_type="UK_OFSI_ENTRY",
    ))
    tasks.append(CompetitionTaskV1(
        task_id="cmp_tmp_03_panama_papers_incorporation_2011",
        category=CompetitionTaskCategory.TEMPORAL,
        question_text="Verify the 2011 incorporation date of Steppe Resources BVI in historical offshore leak records.",
        required_evidence=["Panama Papers incorporation filing 2011 for Steppe Resources BVI"],
        related_entities=["Steppe Resources BVI Limited"],
        temporal_context={"as_of_date": "2011-05-18"},
        expected_capabilities=["sanctions_and_beneficial_ownership"],
        expected_winner="challenger",
        expected_decision=CompetitionDecisionType.RECRUIT_NEW_CAPABILITY,
        target_evidence_type="OFFSHORE_LEAKS_RECORD",
    ))

    # -------------------------------------------------------------------------
    # 6. CONTRADICTORY (3 tasks) - Corporate PR denials vs regulatory sanctions
    # -------------------------------------------------------------------------
    tasks.append(CompetitionTaskV1(
        task_id="cmp_con_01_pr_denial_vs_ofac_sdn",
        category=CompetitionTaskCategory.CONTRADICTORY,
        question_text="A blog post claims Victor Kroll has zero regulatory restrictions. Reconcile against authoritative records.",
        required_evidence=["US OFAC SDN active blocking order for Victor Kroll"],
        related_entities=["Victor Kroll"],
        expected_capabilities=["sanctions_and_beneficial_ownership"],
        expected_winner="challenger",
        expected_decision=CompetitionDecisionType.RECRUIT_NEW_CAPABILITY,
        target_evidence_type="OFAC_SDN_ENTRY",
    ))
    tasks.append(CompetitionTaskV1(
        task_id="cmp_con_02_corporate_clean_status_vs_uk_ofsi",
        category=CompetitionTaskCategory.CONTRADICTORY,
        question_text="Company press releases state Orion Strategic Technologies is fully licensed in the UK. Verify against OFSI.",
        required_evidence=["UK OFSI consolidated asset freeze record for Orion Strategic Technologies"],
        related_entities=["Orion Strategic Technologies"],
        expected_capabilities=["sanctions_and_beneficial_ownership"],
        expected_winner="challenger",
        expected_decision=CompetitionDecisionType.RECRUIT_NEW_CAPABILITY,
        target_evidence_type="UK_OFSI_ENTRY",
    ))
    tasks.append(CompetitionTaskV1(
        task_id="cmp_con_03_nominee_denial_vs_panama_papers",
        category=CompetitionTaskCategory.CONTRADICTORY,
        question_text="Elena Rostova denies holding foreign offshore assets. Reconcile against ICIJ Offshore Leaks.",
        required_evidence=["ICIJ Offshore Leaks beneficial ownership link for Elena Rostova"],
        related_entities=["Elena Rostova"],
        expected_capabilities=["sanctions_and_beneficial_ownership"],
        expected_winner="challenger",
        expected_decision=CompetitionDecisionType.RECRUIT_NEW_CAPABILITY,
        target_evidence_type="OFFSHORE_LEAKS_RECORD",
    ))

    # -------------------------------------------------------------------------
    # 7. ADVERSARIAL (3 tasks) - Nominee directors, disguised intermediary evasion
    # -------------------------------------------------------------------------
    tasks.append(CompetitionTaskV1(
        task_id="cmp_adv_01_mossack_fonseca_intermediary",
        category=CompetitionTaskCategory.ADVERSARIAL,
        question_text="Unmask the registered agent Mossack Fonseca intermediary shielding Steppe Resources BVI.",
        required_evidence=["Mossack Fonseca registered agent intermediary record"],
        related_entities=["Steppe Resources BVI Limited"],
        expected_capabilities=["sanctions_and_beneficial_ownership"],
        expected_winner="challenger",
        expected_decision=CompetitionDecisionType.RECRUIT_NEW_CAPABILITY,
        target_evidence_type="OFFSHORE_LEAKS_RECORD",
    ))
    tasks.append(CompetitionTaskV1(
        task_id="cmp_adv_02_alcogal_panama_trust",
        category=CompetitionTaskCategory.ADVERSARIAL,
        question_text="Identify the Panamanian nominee intermediary used by Mikhail Voronin in the Pandora Papers.",
        required_evidence=["Alcogal registered agent disclosure in Pandora Papers"],
        related_entities=["Pan-Eurasian Nominee Holdings SA"],
        expected_capabilities=["sanctions_and_beneficial_ownership"],
        expected_winner="challenger",
        expected_decision=CompetitionDecisionType.RECRUIT_NEW_CAPABILITY,
        target_evidence_type="OFFSHORE_LEAKS_RECORD",
    ))
    tasks.append(CompetitionTaskV1(
        task_id="cmp_adv_03_cyprus_trust_evasion",
        category=CompetitionTaskCategory.ADVERSARIAL,
        question_text="Detect whether Cyprus Corporate Services Trust acts as a shell vehicle for sanctioned individuals.",
        required_evidence=["OFAC designation intermediary link to Apex Cyber Operations"],
        related_entities=["Cyprus Corporate Services Trust"],
        expected_capabilities=["sanctions_and_beneficial_ownership"],
        expected_winner="challenger",
        expected_decision=CompetitionDecisionType.RECRUIT_NEW_CAPABILITY,
        target_evidence_type="OFAC_SDN_ENTRY",
    ))

    # -------------------------------------------------------------------------
    # 8. MISSING INFO / NOT_FOUND (3 tasks) - Correct handling of unlisted entities
    # -------------------------------------------------------------------------
    tasks.append(CompetitionTaskV1(
        task_id="cmp_mis_01_clean_individual_not_found",
        category=CompetitionTaskCategory.MISSING_INFO,
        question_text="Confirm whether software engineer 'Rachel Thorne' appears on any global sanctions list.",
        required_evidence=["Consolidated negative screening result for Rachel Thorne"],
        related_entities=["Rachel Thorne"],
        expected_capabilities=["sanctions_and_beneficial_ownership"],
        expected_winner="challenger",
        expected_decision=CompetitionDecisionType.RECRUIT_NEW_CAPABILITY,
        target_evidence_type="OFAC_SDN_ENTRY",
    ))
    tasks.append(CompetitionTaskV1(
        task_id="cmp_mis_02_unlisted_holding_firm",
        category=CompetitionTaskCategory.MISSING_INFO,
        question_text="Verify whether Apex Technologies Group parent entity is subject to OFAC blocking orders.",
        required_evidence=["Negative screening confirmation for Apex Technologies Group"],
        related_entities=["Apex Technologies Group"],
        expected_capabilities=["sanctions_and_beneficial_ownership"],
        expected_winner="challenger",
        expected_decision=CompetitionDecisionType.RECRUIT_NEW_CAPABILITY,
        target_evidence_type="OFAC_SDN_ENTRY",
    ))
    tasks.append(CompetitionTaskV1(
        task_id="cmp_mis_03_non_pep_executive",
        category=CompetitionTaskCategory.MISSING_INFO,
        question_text="Check whether tech executive Kenji Sato is registered as a Politically Exposed Person.",
        required_evidence=["Negative PEP screening record for Kenji Sato"],
        related_entities=["Kenji Sato"],
        expected_capabilities=["sanctions_and_beneficial_ownership"],
        expected_winner="challenger",
        expected_decision=CompetitionDecisionType.RECRUIT_NEW_CAPABILITY,
        target_evidence_type="PEP_DISCLOSURE",
    ))

    # -------------------------------------------------------------------------
    # 9. EVIDENCE GROUNDING (3 tasks) - Exact regulatory citations
    # -------------------------------------------------------------------------
    tasks.append(CompetitionTaskV1(
        task_id="cmp_grd_01_eo14024_exact_citation",
        category=CompetitionTaskCategory.EVIDENCE_GROUNDING,
        question_text="Extract the exact Executive Order legal basis cited in the OFAC blocking of Apex Cyber Operations.",
        required_evidence=["Executive Order 14024 regulatory citation for Apex Cyber Operations"],
        related_entities=["Apex Cyber Operations Ltd"],
        expected_capabilities=["sanctions_and_beneficial_ownership"],
        expected_winner="challenger",
        expected_decision=CompetitionDecisionType.RECRUIT_NEW_CAPABILITY,
        target_evidence_type="OFAC_SDN_ENTRY",
    ))
    tasks.append(CompetitionTaskV1(
        task_id="cmp_grd_02_eu_reg269_annex1_verbatim",
        category=CompetitionTaskCategory.EVIDENCE_GROUNDING,
        question_text="Retrieve verbatim EU Council Regulation (EU) No 269/2014 Annex I listing for RedStar Navigation.",
        required_evidence=["EU Council Regulation 269/2014 Annex I verbatim citation"],
        related_entities=["RedStar Navigation GmbH"],
        expected_capabilities=["sanctions_and_beneficial_ownership"],
        expected_winner="challenger",
        expected_decision=CompetitionDecisionType.RECRUIT_NEW_CAPABILITY,
        target_evidence_type="EU_SANCTIONS_ENTRY",
    ))
    tasks.append(CompetitionTaskV1(
        task_id="cmp_grd_03_panama_papers_bvi_reg_num",
        category=CompetitionTaskCategory.EVIDENCE_GROUNDING,
        question_text="Extract the statutory BVI registration number for Steppe Resources BVI from ICIJ Offshore Leaks.",
        required_evidence=["BVI-149208 registration number from Panama Papers"],
        related_entities=["Steppe Resources BVI Limited"],
        expected_capabilities=["sanctions_and_beneficial_ownership"],
        expected_winner="challenger",
        expected_decision=CompetitionDecisionType.RECRUIT_NEW_CAPABILITY,
        target_evidence_type="OFFSHORE_LEAKS_RECORD",
    ))

    # -------------------------------------------------------------------------
    # 10. MULTI_HOP / COEXISTENCE (4 tasks) - Corporate Discovery -> Sanctions / Offshore UBO
    # -------------------------------------------------------------------------
    tasks.append(CompetitionTaskV1(
        task_id="cmp_mul_01_corp_sub_then_ofac",
        category=CompetitionTaskCategory.MULTI_HOP,
        question_text="Discover Apex Technologies subsidiary in Cyprus and verify whether it appears on OFAC SDN.",
        required_evidence=[
            "Corporate registry record for Cyprus subsidiary",
            "US OFAC SDN entry for Apex Cyber Operations Ltd"
        ],
        related_entities=["Apex Technologies Group", "Apex Cyber Operations Ltd"],
        expected_capabilities=["corporate_registry_intelligence", "sanctions_and_beneficial_ownership"],
        expected_winner="coexist",  # Both Corporate Specialist and OpenSanctions required!
        expected_decision=CompetitionDecisionType.COEXIST,
        target_evidence_type="OFAC_SDN_ENTRY",
    ))
    tasks.append(CompetitionTaskV1(
        task_id="cmp_mul_02_director_appointment_then_ofsi",
        category=CompetitionTaskCategory.MULTI_HOP,
        question_text="Validate statutory director appointment for David Marcus and check against UK OFSI sanctions.",
        required_evidence=[
            "Companies House director appointment for David Marcus",
            "UK OFSI asset freeze record for David Marcus"
        ],
        related_entities=["David Marcus"],
        expected_capabilities=["corporate_registry_intelligence", "sanctions_and_beneficial_ownership"],
        expected_winner="coexist",
        expected_decision=CompetitionDecisionType.COEXIST,
        target_evidence_type="UK_OFSI_ENTRY",
    ))
    tasks.append(CompetitionTaskV1(
        task_id="cmp_mul_03_shell_holding_then_pep",
        category=CompetitionTaskCategory.MULTI_HOP,
        question_text="Trace parent entity of Steppe Resources BVI and screen its beneficial owner against PEP registries.",
        required_evidence=[
            "ICIJ Offshore Leaks shell network for Pan-Eurasian Nominee Holdings",
            "PEP disclosure record for Elena Rostova"
        ],
        related_entities=["Steppe Resources BVI Limited", "Elena Rostova"],
        expected_capabilities=["sanctions_and_beneficial_ownership"],
        expected_winner="challenger",
        expected_decision=CompetitionDecisionType.RECRUIT_NEW_CAPABILITY,
        target_evidence_type="PEP_DISCLOSURE",
    ))
    tasks.append(CompetitionTaskV1(
        task_id="cmp_mul_04_corp_infra_sanctions_triad",
        category=CompetitionTaskCategory.MULTI_HOP,
        question_text="Verify Cyprus corporate entity, map its apex network domains, and confirm OFAC sanctions status.",
        required_evidence=[
            "Corporate commercial registry filing in Cyprus",
            "DNS domain records for apex-cyber.cy",
            "US OFAC SDN sanctions entry"
        ],
        related_entities=["Apex Cyber Operations Ltd"],
        expected_capabilities=["corporate_registry_intelligence", "infrastructure_discovery", "sanctions_and_beneficial_ownership"],
        expected_winner="coexist",
        expected_decision=CompetitionDecisionType.COEXIST,
        target_evidence_type="OFAC_SDN_ENTRY",
    ))

    # -------------------------------------------------------------------------
    # 11. HEALTH CASCADE (4 tasks) - Fallback when candidate is DEGRADED / UNAVAILABLE
    # -------------------------------------------------------------------------
    tasks.append(CompetitionTaskV1(
        task_id="cmp_hlth_01_unavailable_candidate_fallback",
        category=CompetitionTaskCategory.HEALTH_CASCADE,
        question_text="When the sanctions registry is offline, fallback to general web research to identify sanctions news.",
        required_evidence=["Public news reports regarding sanctions designations"],
        related_entities=["Victor Kroll"],
        expected_capabilities=["general_web_research"],
        expected_winner="incumbent",  # Fallback to incumbent generalist
        expected_decision=CompetitionDecisionType.COEXIST,
        target_evidence_type="GENERAL_WEB_PAGE",
    ))
    tasks.append(CompetitionTaskV1(
        task_id="cmp_hlth_02_degraded_candidate_handling",
        category=CompetitionTaskCategory.HEALTH_CASCADE,
        question_text="When sanctions API is degraded, continue query execution with health penalty.",
        required_evidence=["Cached sanctions listing for Victor Kroll"],
        related_entities=["Victor Kroll"],
        expected_capabilities=["sanctions_and_beneficial_ownership"],
        expected_winner="challenger",
        expected_decision=CompetitionDecisionType.RECRUIT_NEW_CAPABILITY,
        target_evidence_type="OFAC_SDN_ENTRY",
    ))
    tasks.append(CompetitionTaskV1(
        task_id="cmp_hlth_03_quarantined_candidate_isolation",
        category=CompetitionTaskCategory.HEALTH_CASCADE,
        question_text="Verify that a quarantined candidate implementation is excluded from capability selection.",
        required_evidence=["Clean corporate filing record"],
        related_entities=["Apex Technologies Group"],
        expected_capabilities=["corporate_registry_intelligence"],
        expected_winner="incumbent",
        expected_decision=CompetitionDecisionType.COEXIST,
        target_evidence_type="CORPORATE_FILING",
    ))
    tasks.append(CompetitionTaskV1(
        task_id="cmp_hlth_04_disabled_incumbent_challenger_takeover",
        category=CompetitionTaskCategory.HEALTH_CASCADE,
        question_text="When the generalist web crawler is disabled, verify challenger handles entity research.",
        required_evidence=["Sanctions registry record for Orion Strategic Technologies"],
        related_entities=["Orion Strategic Technologies"],
        expected_capabilities=["sanctions_and_beneficial_ownership"],
        expected_winner="challenger",
        expected_decision=CompetitionDecisionType.RECRUIT_NEW_CAPABILITY,
        target_evidence_type="UK_OFSI_ENTRY",
    ))

    # -------------------------------------------------------------------------
    # 12. LEGAL & SECURITY GATE TESTS (4 tasks) - Reject incompatible candidates
    # -------------------------------------------------------------------------
    tasks.append(CompetitionTaskV1(
        task_id="cmp_gate_01_agpl_license_rejection",
        category=CompetitionTaskCategory.LEGAL_SECURITY_GATE,
        question_text="Verify rejection of AGPL-licensed candidate 'DarkWebScraper' during legal gate.",
        required_evidence=["License rejection record for AGPL-3.0"],
        related_entities=["DarkWebScraper Candidate"],
        expected_capabilities=[],
        expected_winner="reject",
        expected_decision=CompetitionDecisionType.REJECT,
        target_evidence_type="LEGAL_GATE_REJECTION",
    ))
    tasks.append(CompetitionTaskV1(
        task_id="cmp_gate_02_proprietary_license_rejection",
        category=CompetitionTaskCategory.LEGAL_SECURITY_GATE,
        question_text="Verify rejection of commercial proprietary candidate 'ProprietaryAML' without open license.",
        required_evidence=["License rejection record for commercial/proprietary license"],
        related_entities=["ProprietaryAML Candidate"],
        expected_capabilities=[],
        expected_winner="reject",
        expected_decision=CompetitionDecisionType.REJECT,
        target_evidence_type="LEGAL_GATE_REJECTION",
    ))
    tasks.append(CompetitionTaskV1(
        task_id="cmp_gate_03_subprocess_security_quarantine",
        category=CompetitionTaskCategory.LEGAL_SECURITY_GATE,
        question_text="Verify security gate quarantines candidate invoking raw subprocess and eval calls.",
        required_evidence=["Security gate violation report for dangerous execution"],
        related_entities=["UnsafeProbe Candidate"],
        expected_capabilities=[],
        expected_winner="reject",
        expected_decision=CompetitionDecisionType.QUARANTINE,
        target_evidence_type="SECURITY_GATE_QUARANTINE",
    ))
    tasks.append(CompetitionTaskV1(
        task_id="cmp_gate_04_apache_license_approval",
        category=CompetitionTaskCategory.LEGAL_SECURITY_GATE,
        question_text="Verify pre-integration approval for Apache 2.0 licensed OpenSanctions implementation.",
        required_evidence=["License approval record for Apache-2.0"],
        related_entities=["OpenSanctions Candidate"],
        expected_capabilities=["sanctions_and_beneficial_ownership"],
        expected_winner="challenger",
        expected_decision=CompetitionDecisionType.RECRUIT_NEW_CAPABILITY,
        target_evidence_type="OFAC_SDN_ENTRY",
    ))

    return tasks
