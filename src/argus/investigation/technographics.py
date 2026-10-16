"""Enterprise Technographic Extraction and Deployment Intelligence Engine.

Extracts, attributes, and verifies company technology deployments from retrieved
open-source intelligence and technographic source material (e.g., vendor customer
announcements, case studies, TheirStack telemetry, and enterprise job postings).

Enforces the three-tier epistemic provenance model:
1. VENDOR_CONFIRMED: Official vendor customer disclosures or case studies.
2. TECHNOGRAPHIC_PROVIDER_ASSERTION: Third-party technographic telemetry (e.g., TheirStack, Enlyft).
3. CORROBORATED: Independently verified across multiple distinct publisher domains.

This module only *proposes* statuses from the publisher's source class. The final
status (and any corroboration) is decided by the shared verification gate in
``argus.investigation.claim_verification``; no numeric confidence is assigned here.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from argus.investigation.claim_verification import (
    SOURCE_TECHNOGRAPHIC,
    SOURCE_VENDOR,
    TECHNOGRAPHIC_PROVIDER_DOMAINS,  # noqa: F401  (re-exported for existing importers)
    classify_source,
)


COMMON_NON_COMPANIES = {
    "api export",
    "technologies",
    "company",
    "industry",
    "employees",
    "revenue",
    "united states",
    "usa",
    "india",
    "germany",
    "product lifecycle management",
    "enterprise resource planning",
    "siemens",
    "teamcenter",
    "siemens teamcenter",
    "high confidence",
    "search companies",
    "unknown",
    "who",
    "explore who",
    "explore",
    "search",
}


@dataclass
class TechnographicFinding:
    company: str
    software: str
    country: str = ""
    industry: str = ""
    employees: str = ""
    revenue: str = ""
    use_case: str = ""
    evidence_quote: str = ""
    source_url: str = ""
    status: str = "TECHNOGRAPHIC_PROVIDER_ASSERTION"
    confidence: float | None = None
    source_type: str = "technographic_provider"
    qualifier: str = "Third-Party Technographic Provider Assertion"


def classify_technographic_source(doc_url: str, software: str = "") -> tuple[str, float | None, str, str]:
    """Propose a provenance tier from the publisher's source class.

    Returns ``(proposed_status, confidence, source_type, qualifier)``. Confidence is
    always ``None``: a publisher's class says who asserts a deployment, not how
    likely the assertion is to be true.
    """
    source_class = classify_source(doc_url, software)
    if source_class == SOURCE_TECHNOGRAPHIC:
        return (
            "TECHNOGRAPHIC_PROVIDER_ASSERTION",
            None,
            "technographic_provider",
            "Third-Party Technographic Provider Assertion (Job Postings & Telemetry)",
        )
    if source_class == SOURCE_VENDOR:
        return (
            "VENDOR_CONFIRMED",
            None,
            "vendor_official_disclosure",
            "Vendor Customer Case Study / Official Disclosure",
        )
    return (
        "SUPPORTED",
        None,
        "independent_industry_press",
        "Independent Trade Press / Industry Report",
    )


def _provenance(doc_url: str, software: str) -> dict[str, Any]:
    status, confidence, source_type, qualifier = classify_technographic_source(doc_url, software)
    return {"status": status, "confidence": confidence, "source_type": source_type, "qualifier": qualifier}


def clean_company_name(raw_name: str) -> str:
    """Sanitize extracted string into clean canonical company name."""
    if not raw_name:
        return ""
    clean = raw_name.strip()
    clean = re.sub(
        r"^(?:API\s+Export|Company|Country|Industry|Employees|Revenue|Technologies|High\s+confidence|Verified|\d+\.?|\s+)+",
        "",
        clean,
        flags=re.IGNORECASE,
    ).strip()
    clean = re.sub(
        r"^(?:(?:B|A|The|\d+)\s+)?(?:Siemens\s+)?(?:Teamcenter\s+)?(?:PLM\s+Software\s+)?(?:High\s+confidence\s+|Verified\s+)?",
        "",
        clean,
        flags=re.IGNORECASE,
    ).strip()
    clean = re.sub(r"\s+", " ", clean).strip()

    if clean.lower() in COMMON_NON_COMPANIES:
        return ""
    if len(clean) < 3 or len(clean) > 60:
        return ""
    if clean.startswith(("http", "www.", "{", "[", "curl")):
        return ""
    if any(clean.lower().startswith(p) for p in ("who ", "explore ", "search ")):
        return ""
    if " as well" in clean.lower() or ". " in clean:
        return ""
    return clean


def detect_software_in_query(query: str) -> str:
    """Identify the primary target software queried."""
    q_lower = query.lower()
    if "teamcenter" in q_lower:
        return "Siemens Teamcenter"
    elif "s/4hana" in q_lower or "s4hana" in q_lower:
        return "SAP S/4HANA"
    elif "sap" in q_lower:
        return "SAP ERP"
    elif "oracle" in q_lower:
        return "Oracle Cloud ERP"
    elif "workday" in q_lower:
        return "Workday"
    elif "salesforce" in q_lower:
        return "Salesforce"
    return "Enterprise Software"


def detect_country_in_query(query: str) -> str:
    """Identify the target jurisdiction queried."""
    q_lower = query.lower()
    if any(k in q_lower for k in ("usa", "united states", "us ", "america", "american")):
        return "United States"
    elif any(k in q_lower for k in ("india", "indian", "gujarat", "mumbai")):
        return "India"
    elif any(k in q_lower for k in ("germany", "german", "deutschland")):
        return "Germany"
    elif any(k in q_lower for k in ("uk", "united kingdom", "britain")):
        return "United Kingdom"
    return ""


def extract_technographic_deployments(
    text: str,
    doc_url: str = "",
    target_query: str = "",
) -> list[TechnographicFinding]:
    """Extract structured enterprise software deployments from technographic text."""
    if not text or len(text) < 20:
        return []

    default_software = detect_software_in_query(target_query)
    default_country = detect_country_in_query(target_query)

    extracted_companies: dict[str, TechnographicFinding] = {}

    # -------------------------------------------------------------------------
    # Pattern 1: TheirStack / Tabular Rows
    # Company Country Industry Employees Revenue? Technologies
    # -------------------------------------------------------------------------
    table_pattern = re.finditer(
        r"([A-Z0-9][A-Za-z0-9\s.,&-]{2,50}?)\s+(United States|USA|India|Germany|United Kingdom|UK|Japan|France|Italy|Canada|Sweden)\s+([A-Za-z\s,&-]{3,65}?)\s+(\d+k?|\d+[\d,]*)\s*(?:\s+(\$[\d.]+[BMK]?\+?))?\s*(Siemens\s+Teamcenter|Teamcenter|SAP\s+S/4HANA|SAP\s+ERP|SAP|Oracle|Workday|Salesforce)",
        text,
    )
    for m in table_pattern:
        comp = clean_company_name(m.group(1))
        if not comp:
            continue
        country = m.group(2).strip()
        industry = m.group(3).strip()
        emp = m.group(4).strip()
        rev = (m.group(5) or "").strip()
        sw = m.group(6).strip()
        if "teamcenter" in sw.lower() and "siemens" not in sw.lower():
            sw = "Siemens Teamcenter"

        quote = m.group(0).strip()
        finding = TechnographicFinding(
            company=comp,
            software=sw or default_software,
            country=country or default_country,
            industry=industry,
            employees=emp,
            revenue=rev,
            evidence_quote=quote,
            source_url=doc_url,
            **_provenance(doc_url, sw or default_software),
        )
        extracted_companies[comp] = finding

    # -------------------------------------------------------------------------
    # Pattern 2: Card Format
    # Company Employees 88k · Revenue $35B · Defense and Space Manufacturing Siemens Teamcenter
    # -------------------------------------------------------------------------
    card_pattern = re.finditer(
        r"([A-Z0-9][A-Za-z0-9\s.,&-]{2,45}?)\s+Employees\s+(\d+k?|\d+[\d,]*)\s*·\s*Revenue\s*(\$[\d.]+[BMK]?\+?)\s*·\s*([A-Za-z\s,&-]{3,60}?)\s+(Siemens\s+Teamcenter|Teamcenter|SAP\s+S/4HANA|SAP\s+ERP|SAP|Oracle|Workday|Salesforce)",
        text,
    )
    for m in card_pattern:
        comp = clean_company_name(m.group(1))
        if not comp or comp in extracted_companies:
            continue
        emp = m.group(2).strip()
        rev = m.group(3).strip()
        industry = m.group(4).strip()
        sw = m.group(5).strip()
        if "teamcenter" in sw.lower() and "siemens" not in sw.lower():
            sw = "Siemens Teamcenter"

        quote = m.group(0).strip()
        extracted_companies[comp] = TechnographicFinding(
            company=comp,
            software=sw or default_software,
            country="",  # not stated by this source pattern; never assumed from the query
            industry=industry,
            employees=emp,
            revenue=rev,
            evidence_quote=quote,
            source_url=doc_url,
            **_provenance(doc_url, sw or default_software),
        )

    # -------------------------------------------------------------------------
    # Pattern 3: Case Study & Prose Statements
    # <Company> deploys/utilizes/uses/integrates/relies on <Software> ...
    # -------------------------------------------------------------------------
    prose_pattern = re.finditer(
        r"([A-Z0-9][A-Za-z0-9\s.,&-]{2,40}?)\s+(?:deploys|utilizes|uses|runs|integrates|implements|selected|collaborates with Siemens to build [^\n]+ using)\s+([A-Za-z0-9\s.,&-]{2,30}?(?:Teamcenter|SAP|Oracle|Workday|Salesforce)[A-Za-z0-9\s.,&-]*)",
        text,
    )
    for m in prose_pattern:
        comp = clean_company_name(m.group(1))
        if not comp or comp in extracted_companies:
            continue
        predicate_clause = m.group(2).strip()

        # Extract software name cleanly from clause
        sw = default_software
        for cand_sw in ("Siemens Teamcenter", "Teamcenter", "SAP S/4HANA", "SAP ERP", "Oracle Cloud ERP", "Workday", "Salesforce"):
            if cand_sw.lower() in predicate_clause.lower():
                sw = "Siemens Teamcenter" if "teamcenter" in cand_sw.lower() else cand_sw
                break

        # Check for employee/revenue mentions in surrounding sentence
        emp = ""
        m_emp = re.search(r"(\d+k|\d+,\d+|\d+)\s+employees", predicate_clause)
        if m_emp:
            emp = m_emp.group(1)

        rev = ""
        m_rev = re.search(r"(\$[\d.]+[BMK]?\+?)\s+revenue", predicate_clause)
        if m_rev:
            rev = m_rev.group(1)

        quote = m.group(0).strip()
        extracted_companies[comp] = TechnographicFinding(
            company=comp,
            software=sw,
            country="",  # not stated by this source pattern; never assumed from the query
            industry="",
            employees=emp,
            revenue=rev,
            evidence_quote=quote,
            source_url=doc_url,
            **_provenance(doc_url, sw or default_software),
        )

    return list(extracted_companies.values())
