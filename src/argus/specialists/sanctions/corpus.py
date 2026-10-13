"""Heimdallr V3.2: International Sanctions & Beneficial Ownership Corpus.

Authoritative offline intelligence corpus modeling:
1. US OFAC Specially Designated Nationals (SDN)
2. UK HM Treasury OFSI Consolidated Sanctions
3. EU Financial Sanctions Consolidated List
4. Politically Exposed Persons (PEPs)
5. ICIJ Offshore Leaks (Panama Papers, Pandora Papers, BVI & Cayman shell trusts)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

SANCTIONS_CORPUS: Dict[str, Dict[str, Any]] = {
    # 1. OFAC SDN Case: Apex Cyber Operations / Victor Kroll
    "Apex Cyber Operations Ltd": {
        "entity_name": "Apex Cyber Operations Ltd",
        "entity_type": "ORGANIZATION",
        "jurisdiction": "CY",  # Cyprus
        "reg_number": "HE-410982",
        "sanctions_programs": ["CYBER2", "RUSSIA-EO14024"],
        "listing_authority": "US_OFAC",
        "program_details": "Blocked under Executive Order 14024 for malicious cyber activities.",
        "dates_listed": ["2022-04-15"],
        "aliases": ["Apex Cyber Ltd", "Apex Operational Cybersec"],
        "beneficial_owners": ["Victor Kroll", "Kenji Sato"],
        "known_intermediaries": ["Cyprus Corporate Services Trust"],
    },
    "Victor Kroll": {
        "entity_name": "Victor Kroll",
        "entity_type": "INDIVIDUAL",
        "birth_date": "1981-06-14",
        "citizenship": ["RU", "CY"],
        "sanctions_programs": ["CYBER2"],
        "listing_authority": "US_OFAC",
        "program_details": "OFAC SDN designated cyber administrator and financier.",
        "dates_listed": ["2022-04-15"],
        "aliases": ["0x_vkroll", "Viktor Kroll"],
        "controlled_entities": ["Apex Cyber Operations Ltd", "Blackwood Global Holdings"],
    },

    # 2. UK OFSI Consolidated Case: Orion Strategic Technologies / David Marcus
    "Orion Strategic Technologies": {
        "entity_name": "Orion Strategic Technologies",
        "entity_type": "ORGANIZATION",
        "jurisdiction": "AE",  # UAE / Dubai
        "reg_number": "DMCC-88912",
        "sanctions_programs": ["UK_RUSSIA_SANCTIONS_2019"],
        "listing_authority": "UK_OFSI",
        "program_details": "Asset freeze designated for military end-user technology transfers.",
        "dates_listed": ["2023-02-24"],
        "aliases": ["Orion Strategic Tech FZE", "Orion Defense Technologies"],
        "beneficial_owners": ["David Marcus"],
        "known_intermediaries": ["Gulf Horizon Nominees Ltd"],
    },
    "David Marcus": {
        "entity_name": "David Marcus",
        "entity_type": "INDIVIDUAL",
        "birth_date": "1974-11-03",
        "citizenship": ["GB", "IL"],
        "sanctions_programs": ["UK_RUSSIA_SANCTIONS_2019"],
        "listing_authority": "UK_OFSI",
        "program_details": "Designated director under UK Russia Financial Sanctions.",
        "dates_listed": ["2023-02-24"],
        "aliases": ["D. Marcus", "David M. Marcus"],
        "controlled_entities": ["Orion Strategic Technologies"],
    },

    # 3. EU Consolidated Sanctions Case: RedStar Navigation GmbH
    "RedStar Navigation GmbH": {
        "entity_name": "RedStar Navigation GmbH",
        "entity_type": "ORGANIZATION",
        "jurisdiction": "AT",  # Austria
        "reg_number": "FN-34981a",
        "sanctions_programs": ["EU_REG_269_2014"],
        "listing_authority": "EU_COUNCIL",
        "program_details": "Council Regulation (EU) No 269/2014 Annex I listing.",
        "dates_listed": ["2022-10-06"],
        "aliases": ["RedStar Marine Tech", "RedStar Shipping GmbH"],
        "beneficial_owners": ["Mikhail Voronin"],
        "known_intermediaries": ["Vienna Trust Consulting AG"],
    },

    # 4. Politically Exposed Person (PEP): Elena Rostova
    "Elena Rostova": {
        "entity_name": "Elena Rostova",
        "entity_type": "INDIVIDUAL",
        "birth_date": "1969-03-22",
        "citizenship": ["KZ"],
        "sanctions_programs": ["PEP_REGISTRY"],
        "listing_authority": "NATIONAL_GOVERNANCE",
        "pep_status": "POLITICALLY_EXPOSED_PERSON",
        "pep_role": "Former Deputy Minister of Natural Resources & Energy",
        "dates_listed": ["2018-01-01"],
        "aliases": ["Elena A. Rostova"],
        "controlled_entities": ["Steppe Resources BVI Limited", "Alatau Capital Partners"],
    },

    # 5. ICIJ Offshore Leaks / Panama Papers: Steppe Resources BVI Limited & Cross-Border Shells
    "Steppe Resources BVI Limited": {
        "entity_name": "Steppe Resources BVI Limited",
        "entity_type": "OFFSHORE_SHELL",
        "jurisdiction": "VG",  # British Virgin Islands
        "reg_number": "BVI-149208",
        "leak_source": "PANAMA_PAPERS",
        "incorporation_date": "2011-05-18",
        "status": "ACTIVE_BEARER_SHARES",
        "registered_agent": "Mossack Fonseca (BVI) Ltd",
        "intermediary": "Geneva Wealth Management Trust",
        "beneficial_owners": ["Elena Rostova"],
        "shareholders": ["Pan-Eurasian Nominee Holdings SA"],
    },
    "Pan-Eurasian Nominee Holdings SA": {
        "entity_name": "Pan-Eurasian Nominee Holdings SA",
        "entity_type": "OFFSHORE_SHELL",
        "jurisdiction": "PA",  # Panama
        "reg_number": "PA-839219",
        "leak_source": "PANDORA_PAPERS",
        "incorporation_date": "2014-08-12",
        "registered_agent": "Alcogal Panama",
        "beneficial_owners": ["Mikhail Voronin", "Elena Rostova"],
        "controlled_entities": ["Steppe Resources BVI Limited"],
    },
    "Blackwood Global Holdings": {
        "entity_name": "Blackwood Global Holdings",
        "entity_type": "OFFSHORE_TRUST",
        "jurisdiction": "KY",  # Cayman Islands
        "reg_number": "KY-99210",
        "leak_source": "PARADISE_PAPERS",
        "incorporation_date": "2016-11-04",
        "registered_agent": "Appleby Cayman Management",
        "beneficial_owners": ["Victor Kroll"],
        "related_entities": ["Apex Cyber Operations Ltd"],
    },
}
