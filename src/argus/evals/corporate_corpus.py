"""Frozen Corporate Financial & Registry Intelligence Corpus.

Supplies frozen SEC EDGAR submissions, Companies House records, GLEIF LEI registries,
and searchable web documents for evaluating corporate intelligence without external
network flakiness or SEC rate limiting.
"""

from typing import Any
from argus.crawler.models import ContentUnit, Document

# 1. Structured Corporate Registry Simulation Database
CORPORATE_REGISTRY_DATABASE: dict[str, dict[str, Any]] = {
    # Primary Target: AutoTech Corporation
    "autotech_corporation": {
        "legal_name": "AutoTech Corporation",
        "brand_name": "AutoTech",
        "jurisdiction": "US-DE",
        "entity_type": "Corporation",
        "identifiers": {
            "CIK": "0001899999",
            "STATE_CORP_ID": "DE-7891234",
            "LEI": "5493001KJTIIGC8Y1R12",
            "TICKER": "ATK",
        },
        "registered_agent": {
            "name": "Corporation Service Company",
            "address": "251 Little Falls Drive, Wilmington, DE 19808",
            "role": "Registered Agent",
        },
        "parent_company": {
            "name": "AutoTech Global Holdings Inc",
            "jurisdiction": "US-DE",
            "ownership_percentage": 100.0,
            "relationship": "parent_company",
        },
        "filings": {
            # 10-K Annual Report FY2023
            "0001899999-24-000010": {
                "form": "10-K",
                "period_ended": "2023-12-31",
                "filing_date": "2024-02-15",
                "accession_number": "0001899999-24-000010",
                "url": "https://www.sec.gov/Archives/edgar/data/1899999/000189999924000010/atk-20231231.htm",
                "officers": [
                    {
                        "name": "Somdev Vance",
                        "title": "Chief Executive Officer",
                        "appointment_date": "2020-01-10",
                        "status": "CURRENT_ACTIVE",
                    },
                    {
                        "name": "Elena Rostova",
                        "title": "Chief Financial Officer",
                        "appointment_date": "2021-03-15",
                        "status": "CURRENT_ACTIVE",
                    },
                    {
                        "name": "Marcus Chen",
                        "title": "Former Chief Financial Officer",
                        "appointment_date": "2018-05-01",
                        "resignation_date": "2021-03-14",
                        "status": "HISTORICAL_RESIGNED",
                    },
                ],
                "subsidiaries": [
                    {
                        "name": "AutoTech Perception Labs LLC",
                        "jurisdiction": "US-DE",
                        "ownership_percentage": 100.0,
                        "relationship": "subsidiary",
                        "status": "CURRENT_ACTIVE",
                    },
                    {
                        "name": "AutoTech UK Limited",
                        "jurisdiction": "GB",
                        "ownership_percentage": 100.0,
                        "relationship": "subsidiary",
                        "status": "CURRENT_ACTIVE",
                    },
                ],
            },
            # 8-K Acquisition of EcoDrive Sensors
            "0001899999-22-000045": {
                "form": "8-K",
                "item": "Item 2.01 Completion of Acquisition",
                "filing_date": "2022-04-18",
                "effective_date": "2022-04-15",
                "accession_number": "0001899999-22-000045",
                "url": "https://www.sec.gov/Archives/edgar/data/1899999/000189999922000045/atk-20220418.htm",
                "target_company": "EcoDrive Sensors Inc",
                "relationship": "acquired_subsidiary",
                "status": "CURRENT_ACTIVE",
            },
            # 8-K Divestiture of Legacy Sensor Systems
            "0001899999-23-000080": {
                "form": "8-K",
                "item": "Item 2.01 Completion of Disposition",
                "filing_date": "2023-08-05",
                "effective_date": "2023-08-01",
                "accession_number": "0001899999-23-000080",
                "url": "https://www.sec.gov/Archives/edgar/data/1899999/000189999923000080/atk-20230805.htm",
                "target_company": "Legacy Sensor Systems Inc",
                "relationship": "divested_subsidiary",
                "status": "HISTORICAL_DIVESTED",
            },
            # Schedule 13D Beneficial Ownership
            "0001899999-24-000015": {
                "form": "SC 13D",
                "filing_date": "2024-03-01",
                "accession_number": "0001899999-24-000015",
                "url": "https://www.sec.gov/Archives/edgar/data/1899999/000189999924000015/sc13d.htm",
                "beneficial_owner": "Vanguard Perception Fund LP",
                "ownership_percentage": 12.4,
                "relationship": "beneficial_owner",
                "status": "CURRENT_ACTIVE",
            },
            # 10-K/A Clerical Amendment Superseding Original Item 12
            "0001899999-24-000025": {
                "form": "10-K/A",
                "period_ended": "2023-12-31",
                "filing_date": "2024-04-01",
                "accession_number": "0001899999-24-000025",
                "url": "https://www.sec.gov/Archives/edgar/data/1899999/000189999924000025/atk-20231231a.htm",
                "amends_accession": "0001899999-24-000010",
                "subject": "Officer Equity Restatement",
                "restated_shares": 150000,
                "original_shares": 100000,
                "status": "CURRENT_ACTIVE",
            },
        },
    },

    # Cross-Border UK Subsidiary: AutoTech UK Limited
    "autotech_uk_limited": {
        "legal_name": "AutoTech UK Limited",
        "company_number": "12345678",
        "jurisdiction": "GB",
        "parent_company": "AutoTech Corporation",
        "filings": {
            "ch_annual_2023": {
                "filing_date": "2023-10-15",
                "officers": [
                    {
                        "name": "Somdev Vance",
                        "title": "Director",
                        "appointment_date": "2020-02-01",
                        "status": "CURRENT_ACTIVE",
                    }
                ],
                "subsidiaries": [
                    {
                        "name": "AutoTech Perception UK Labs Ltd",
                        "company_number": "87654321",
                        "jurisdiction": "GB",
                        "relationship": "subsidiary",
                        "status": "CURRENT_ACTIVE",
                    }
                ],
            }
        },
    },

    # Tier-2 UK Subsidiary for Multi-Hop reasoning
    "autotech_perception_uk_labs_ltd": {
        "legal_name": "AutoTech Perception UK Labs Ltd",
        "company_number": "87654321",
        "jurisdiction": "GB",
        "parent_company": "AutoTech UK Limited",
        "officers": [
            {
                "name": "Somdev Vance",
                "title": "Managing Director",
                "appointment_date": "2020-05-01",
                "status": "CURRENT_ACTIVE",
            }
        ],
    },
}


# 2. Searchable Public Web Documents for Argus Baseline
def build_corporate_documents() -> list[Document]:
    """Construct mock web articles and press releases for baseline search engine."""
    docs = []

    # Doc 1: TechCrunch Article on AutoTech
    d1 = Document(
        document_id="doc_corp_techcrunch_article",
        url="https://techcrunch.com/2023/11/10/autotech-autonomous-fleet-growth/",
        title="AutoTech continues autonomous fleet expansion in Detroit",
        text_content=(
            "Autonomous driving brand AutoTech (officially operating as AutoTech Corporation) "
            "has expanded operations. Founded by Somdev Vance, the firm is backed by institutional "
            "investors. Marcus Chen previously served as finance lead before Elena Rostova took "
            "over the executive finances."
        ),
        status_code=200,
        fetch_method="http",
    )
    docs.append(d1)

    # Doc 2: Press Release: Acquisition of EcoDrive Sensors
    d2 = Document(
        document_id="doc_corp_press_ecodrive",
        url="https://autotech.corp/press/2022-04-15/ecodrive-acquisition",
        title="AutoTech completes acquisition of EcoDrive Sensors",
        text_content=(
            "DETROIT — AutoTech Corporation today announced the completion of its acquisition "
            "of EcoDrive Sensors Inc. The transaction closed on April 15, 2022, per Item 2.01."
        ),
        status_code=200,
        fetch_method="http",
    )
    docs.append(d2)

    # Doc 3: Corporate Directory mentioning CSC Registered Agent
    d3 = Document(
        document_id="doc_corp_directory_agent",
        url="https://businessfilings-directory.com/de/autotech-corporation",
        title="AutoTech Corporation - Delaware Company Profile",
        text_content=(
            "AutoTech Corporation is registered in Delaware. Registered Agent on file is "
            "Corporation Service Company located at 251 Little Falls Drive, Wilmington, DE."
        ),
        status_code=200,
        fetch_method="http",
    )
    docs.append(d3)

    # Doc 4: SEC Filing Form 10-K Overview
    d4 = Document(
        document_id="doc_corp_sec_10k_overview",
        url="https://www.sec.gov/Archives/edgar/data/1899999/000189999924000010/atk-20231231.htm",
        title="AutoTech Corporation Form 10-K Annual Report FY2023",
        text_content=(
            "UNITED STATES SECURITIES AND EXCHANGE COMMISSION. Form 10-K for AutoTech Corporation. "
            "Commission File Number CIK 0001899999. Chief Executive Officer: Somdev Vance. "
            "Chief Financial Officer: Elena Rostova. Subsidiaries include AutoTech Perception Labs LLC "
            "and AutoTech UK Limited."
        ),
        status_code=200,
        fetch_method="http",
    )
    docs.append(d4)

    # Populate ContentUnits
    for d in docs:
        d.content_units = [
            ContentUnit(
                unit_id=f"unit_{d.document_id}",
                document_id=d.document_id,
                unit_type="paragraph",
                sequence=0,
                text=d.text_content,
                char_start=0,
                char_end=len(d.text_content),
            )
        ]

    return docs
