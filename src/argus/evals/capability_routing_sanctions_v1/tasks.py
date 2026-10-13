"""Heimdallr V3.2.1: CAPABILITY_ROUTING_SANCTIONS_V1 Tasks.

70 tasks (~50% positive sanctions/beneficial ownership, ~50% negative generic tasks).
No specialist names, capability IDs, or routing labels inside task inputs.
"""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class RoutingTaskV1(BaseModel):
    task_id: str
    query: str
    evidence_requirements: List[str]
    # Ground-truth labels evaluated exclusively by grader, never passed into matcher inputs:
    expected_capabilities_evaluator_only: List[str] = Field(default_factory=list)
    is_sanctions_positive: bool = False


def build_routing_sanctions_v1_tasks() -> List[RoutingTaskV1]:
    """Generate 70 frozen routing tasks (35 positive, 35 negative)."""
    tasks: List[RoutingTaskV1] = []

    # =========================================================================
    # POSITIVE TASKS (35 Tasks: Sanctions, PEP, Beneficial Ownership, Offshore)
    # =========================================================================
    pos_specs = [
        ("Screen maritime carrier against OFAC Specially Designated Nationals list.", ["OFAC SDN designated entity list and executive order reference"]),
        ("Check HM Treasury asset freeze status for Cypriot maritime transport firm.", ["UK OFSI asset freeze consolidated list entry"]),
        ("Determine ultimate beneficial owner of privately held BVI offshore trust.", ["Offshore registry beneficial ownership disclosure or trust deed"]),
        ("Identify whether energy board member holds Politically Exposed Person status.", ["Official PEP disclosure decree or government executive gazette"]),
        ("Trace beneficial ownership chain of Isle of Man holding company.", ["Register of directors and offshore trust beneficial owners"]),
        ("Verify EU restrictive measures designation for defense microelectronics supplier.", ["EU Council Regulation restrictive measures annex gazette"]),
        ("Screen commodities broker against Swiss SECO financial sanctions lists.", ["State Secretariat for Economic Affairs SECO sanctions database"]),
        ("Identify controlling natural person behind Panama Papers offshore vehicle.", ["Panama Papers / ICIJ offshore leaks shareholder register"]),
        ("Determine historical delisting date for European financial holding entity.", ["OFAC SDN historical removal notice and Federal Register notice"]),
        ("Assess 50 percent rule indirect sanctions attribution across subsidiaries.", ["Subsidiary corporate share register indicating aggregate blocked ownership"]),
        ("Screen Dubai export company for UK Russia Sanctions Regulations listing.", ["UK Russia Regulations 2019 statutory instrument asset freeze"]),
        ("Verify whether minister daughter qualifies as PEP by close family association.", ["FATF PEP family relationship registry or asset declaration"]),
        ("Identify primary beneficial owner hidden behind nominee shareholder in Seychelles.", ["Nominee declaration and ultimate controller confirmation"]),
        ("Screen oil tanker IMO number for G7 crude price cap maritime sanctions.", ["Maritime enforcement authority shadow fleet designation list"]),
        ("Verify whether corporate officer is subject to Canadian SEMA sanctions.", ["Special Economic Measures Act consolidated Canadian sanction schedule"]),
        ("Trace Cayman Islands investment fund upstream to designated oligarch.", ["Fund general partner disclosure and offshore holding chain"]),
        ("Screen aviation leasing company for EU airspace and financial asset ban.", ["EU restrictive measures against transport operators annex"]),
        ("Check whether entity was granted specific OFAC wind-down license.", ["US Treasury General License authorization text and expiry"]),
        ("Disambiguate sanctioned natural person from namesake using passport and DOB.", ["SDN identifier table containing date of birth and passport numbers"]),
        ("Verify Politically Exposed Person standing for former deputy finance minister.", ["National executive ministry biographical record and PEP register"]),
        ("Trace beneficial ownership of Jersey private trust holding commercial real estate.", ["Jersey Financial Services Commission trust beneficial ownership register"]),
        ("Check if transport firm appears on Japanese METI foreign end-user list.", ["Japan METI Foreign End User List export control schedule"]),
        ("Verify whether Singapore maritime agent is subject to MAS sanctions directives.", ["Monetary Authority of Singapore financial institutions sanction notice"]),
        ("Determine ultimate parent of Guernsey holding firm linked to designated executive.", ["Guernsey registry of beneficial owners filings"]),
        ("Screen Turkish procurement intermediary for US secondary sanctions exposure.", ["OFAC secondary sanctions determination notice"]),
        ("Identify beneficial controller of Gibraltar nominee partnership.", ["Gibraltar Companies House beneficial ownership registry"]),
        ("Verify current active vs expired status for Australian autonomous sanctions.", ["DFAT Australian autonomous sanctions consolidated list"]),
        ("Check whether offshore company assets are subject to UN Security Council freeze.", ["United Nations Security Council Sanctions Committee consolidated list"]),
        ("Trace Bermuda captive insurance firm to sanctioned state-owned parent.", ["Bermuda Monetary Authority regulatory disclosure"]),
        ("Screen European bank account signatory for FATF high-risk jurisdiction PEP.", ["FATF high-risk jurisdiction compliance watch list"]),
        ("Verify whether shell company in Belize was incorporated by sanctioned broker.", ["Belize International Financial Services Commission registry"]),
        ("Determine if designated individual holds controlling voting trust power.", ["Voting trust agreement and regulatory ownership filing"]),
        ("Screen Hong Kong trading firm for US Executive Order 14024 blocking.", ["US Treasury Executive Order 14024 SDN annex"]),
        ("Check whether Luxembourg securitization vehicle is owned by sanctioned fund.", ["Luxembourg Register of Beneficial Owners (RBE) disclosure"]),
        ("Identify PEP standing of central bank governor and supervisory council members.", ["National central bank gazette and official PEP schedule"]),
    ]

    for i, (q, ev) in enumerate(pos_specs, 1):
        tasks.append(RoutingTaskV1(
            task_id=f"route_pos_{i:02d}",
            query=q,
            evidence_requirements=ev,
            expected_capabilities_evaluator_only=["sanctions_and_beneficial_ownership"],
            is_sanctions_positive=True,
        ))

    # =========================================================================
    # NEGATIVE TASKS (35 Tasks: Corporate, Infra, Identity, Generalist OSINT)
    # =========================================================================
    neg_specs = [
        # Corporate (9 tasks)
        ("Retrieve certificate of incorporation and registered office for Acme Ltd.", ["Companies House UK certificate of incorporation"], ["corporate_registry_intelligence"]),
        ("Extract full list of first-tier subsidiaries from SEC Exhibit 21.", ["SEC Form 10-K Exhibit 21 subsidiary schedule"], ["corporate_registry_intelligence"]),
        ("Identify registered statutory directors for German GmbH from Handelsregister.", ["Handelsregister Abteilung B official extract"], ["corporate_registry_intelligence"]),
        ("Lookup Delaware file number and corporate standing for Tech Corp.", ["Delaware Division of Corporations entity status check"], ["corporate_registry_intelligence"]),
        ("Verify statutory share capital and nominal par value from UK annual return.", ["Companies House Confirmation Statement CS01"], ["corporate_registry_intelligence"]),
        ("Extract date of corporate merger from state business registry filing.", ["Secretary of State merger certificate documentation"], ["corporate_registry_intelligence"]),
        ("Retrieve official articles of association for French SAS from Infogreffe.", ["Infogreffe Kbis and statuts constitutifs"], ["corporate_registry_intelligence"]),
        ("Identify statutory corporate secretary for Singapore private company.", ["ACRA Singapore BizFile corporate profile extract"], ["corporate_registry_intelligence"]),
        ("Verify registered legal agent address for Nevada LLC.", ["Nevada Secretary of State SilverFlume business filing"], ["corporate_registry_intelligence"]),
        # Infrastructure (9 tasks)
        ("Enumerate DNS MX records and mail host servers for target corporate domain.", ["DNS zone transfer or MX record lookup output"], ["infrastructure_discovery"]),
        ("Discover Certificate Transparency SAN entries for cloud telemetry subdomain.", ["Certificate Transparency CT log query results"], ["infrastructure_discovery"]),
        ("Map ASN network prefix and BGP routing origin for hosting cluster.", ["BGP routing table and WHOIS autonomous system number"], ["infrastructure_discovery"]),
        ("Inspect SSL/TLS certificate chain and issuer authority for staging portal.", ["X.509 certificate chain validation output"], ["infrastructure_discovery"]),
        ("Enumerate SPF and DMARC email authentication records for apex domain.", ["DNS TXT records containing SPF and DMARC policy"], ["infrastructure_discovery"]),
        ("Identify reverse DNS PTR hostnames for corporate static IP range.", ["Reverse DNS PTR record resolution table"], ["infrastructure_discovery"]),
        ("Discover active subdomains using public Certificate Transparency monitors.", ["Certificate Transparency log aggregation records"], ["infrastructure_discovery"]),
        ("Verify technical contact and nameserver authority from WHOIS registry.", ["ICANN authoritative WHOIS domain registration record"], ["infrastructure_discovery"]),
        ("Inspect HTTP response security headers for public portal web server.", ["HTTP server response headers including HSTS and CSP"], ["infrastructure_discovery"]),
        # Identity (9 tasks)
        ("Correlate GitHub developer username with public Keybase identity.", ["Public cryptographic Keybase proof and GitHub profile"], ["identity_resolution"]),
        ("Trace academic thesis and university faculty appointment for lead researcher.", ["University faculty directory and verified doctoral repository"], ["identity_resolution"]),
        ("Verify professional employment timeline and former employer for VP Security.", ["Public employment history and corporate biographical note"], ["identity_resolution"]),
        ("Match public PGP key fingerprint to technical blog author.", ["OpenPGP keyserver verification output"], ["identity_resolution"]),
        ("Correlate conference speaker bio with published technical whitepaper author.", ["Technical symposium proceedings author biography"], ["identity_resolution"]),
        ("Retrieve verified ORCID publication history for research scientist.", ["ORCID public registry researcher publication record"], ["identity_resolution"]),
        ("Disambiguate software developer persona across open source repositories.", ["Public commit author history and PGP commit signatures"], ["identity_resolution"]),
        ("Verify executive education credentials from university alumni database.", ["Official university graduation commencement register"], ["identity_resolution"]),
        ("Trace patent inventor name to corporate research division assignee.", ["USPTO public patent grant inventor disclosure"], ["identity_resolution"]),
        # General Web / OSINT (8 tasks)
        ("Summarize quarterly revenue and GAAP operating income from press release.", ["Corporate investor relations financial press release"], ["general_web_research"]),
        ("Find official press announcement for new product launch date.", ["Public product press release and media kit"], ["general_web_research"]),
        ("Retrieve published corporate environmental sustainability whitepaper.", ["Corporate ESG sustainability PDF report"], ["general_web_research"]),
        ("Extract specifications and technical datasheet for semiconductor component.", ["Manufacturer technical datasheet document"], ["general_web_research"]),
        ("Find customer case study published by enterprise software vendor.", ["Vendor public marketing case study portal"], ["general_web_research"]),
        ("Verify conference dates and venue location from official symposium agenda.", ["Symposium program schedule web page"], ["general_web_research"]),
        ("Summarize industry analyst market share report for cloud computing.", ["Market research firm executive summary report"], ["general_web_research"]),
        ("Extract public customer support hotline telephone and operating hours.", ["Official customer support web contact page"], ["general_web_research"]),
    ]

    for i, (q, ev, caps) in enumerate(neg_specs, 1):
        tasks.append(RoutingTaskV1(
            task_id=f"route_neg_{i:02d}",
            query=q,
            evidence_requirements=ev,
            expected_capabilities_evaluator_only=caps,
            is_sanctions_positive=False,
        ))

    return tasks
