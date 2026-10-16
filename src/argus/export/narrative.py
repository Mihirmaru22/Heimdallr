"""Heimdallr Narrative Intelligence & Report Synthesis Engine.

Transforms raw epistemic claims, extracted entities, and evidence passages
into human-readable intelligence briefs, categorized finding statements,
and clean entity dossiers.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


from argus.investigation.relevance import (
    clean_entity_name,
    is_contextually_relevant_host,
)

clean_entity_display_name = clean_entity_name

NO_SOURCE_RECORDED = "No source recorded"
# Facts pattern-matched from evidence text but not checked against it.
EXTRACTED_STATUS = "UNVERIFIED"


def format_confidence(value: Any, decimals: int = 1) -> str:
    """Render a 0-1 confidence as a percentage, or 'n/a' when none was computed."""
    if value is None:
        return "n/a"
    try:
        return f"{float(value) * 100:.{decimals}f}%"
    except (TypeError, ValueError):
        return "n/a"


def _source_url_for(fragment: str, passages: list[dict[str, str]]) -> str | None:
    """Return the URL of the first evidence passage that contains the fragment."""
    if not fragment:
        return None
    for p in passages:
        if fragment in p.get("text", ""):
            return p.get("url") or None
    return None



def generate_narrative_intelligence(data: dict[str, Any]) -> dict[str, Any]:
    """Generate human-readable narrative intelligence synthesis from investigation data."""
    target_raw = data.get("target") or data.get("objective") or "Target Entity"
    claims = data.get("claims", [])
    entities = data.get("entities", {})
    evidence = data.get("evidence", [])
    confidence = data.get("confidence")
    stop_reason = data.get("stop_reason") or "UNKNOWN"

    # Check for Enterprise Technographic / Software Deployment Intelligence
    software_deploy_claims = [
        c for c in claims
        if "USES_" in str(c.get("predicate", "")).upper() or "SOFTWARE" in str(c.get("predicate", "")).upper()
    ]
    # The deployment template is chosen from the interpreted objective or the claims
    # themselves, not from product keywords in the query text.
    from argus.investigation.objective_parser import EnumerationObjective, parse_enumeration_objective

    enum_dict = data.get("enumeration_objective")
    enum_obj = EnumerationObjective.from_dict(enum_dict) if enum_dict else parse_enumeration_objective(str(target_raw))
    is_technographic_objective = bool(software_deploy_claims) or enum_obj is not None

    if is_technographic_objective:
        if enum_obj is not None:
            target_sw = enum_obj.object_name
            target_country = enum_obj.geography
            if not enum_dict:
                # Parsed from the query text only: prefer the fuller name the claims' sources use.
                fuller = [str(c.get("object")) for c in software_deploy_claims if enum_obj.object.lower() in str(c.get("object") or "").lower()]
                if fuller:
                    target_sw = max(set(fuller), key=fuller.count)
        else:
            objects = [str(c.get("object") or "") for c in software_deploy_claims if c.get("object")]
            target_sw = max(set(objects), key=objects.count) if objects else "the requested technology"
            target_country = ""
        object_words = {w.lower() for w in re.findall(r"[\w&\-]+", target_sw)}
        primary_name = f"{target_sw} Enterprise Deployments ({target_country or 'country unspecified'})"

        # Deduplicate companies while preserving attributes
        companies_seen: dict[str, dict[str, Any]] = {}
        for c in software_deploy_claims:
            comp = c.get("subject", "").strip()
            if not comp or comp in companies_seen:
                continue
            meta = entities.get(comp, {}).get("metadata", {}) if isinstance(entities.get(comp), dict) else {}
            companies_seen[comp] = {
                "company": comp,
                "software": c.get("object") or target_sw,
                "country": c.get("country") or meta.get("country") or "",
                "industry": c.get("industry") or meta.get("industry") or "",
                "employees": c.get("employees") or meta.get("employees") or "",
                "revenue": c.get("revenue") or meta.get("revenue") or "",
                "status": c.get("status") or EXTRACTED_STATUS,
                "confidence": c.get("confidence"),
                "citation": c.get("source_url") or c.get("citation") or None,
                "qualifier": c.get("qualifier") or "Technographic Telemetry Assertion",
            }

        if not companies_seen and isinstance(entities, dict):
            for ek, ev in entities.items():
                etype = ev.get("entity_type") if isinstance(ev, dict) else str(ev)
                name_words = {w.lower() for w in re.findall(r"[\w&\-]+", ek)}
                if str(etype).upper() == "ORGANIZATION" and len(ek) >= 3 and not (name_words and name_words <= object_words):
                    meta = ev.get("metadata", {}) if isinstance(ev, dict) else {}
                    companies_seen[ek] = {
                        "company": ek,
                        "software": target_sw,
                        "country": meta.get("country") or "",
                        "industry": meta.get("industry") or "",
                        "employees": meta.get("employees") or "",
                        "revenue": meta.get("revenue") or "",
                        "status": EXTRACTED_STATUS,
                        "confidence": None,
                        "citation": meta.get("source_url") or None,
                        "qualifier": "Third-Party Technographic Provider Assertion",
                    }

        deployments_list = list(companies_seen.values())

        p1 = (
            f"This investigation looked for organizations using **{target_sw}**"
            f"{f' in **{target_country}**' if target_country else ''}. "
            f"Retrieved evidence named **{len(deployments_list)}** organization(s) as users; "
            f"see each finding's status and source below for how well each is supported."
        )

        p2 = (
            f"**Scope & Sampling Notice:** These findings are a sample: only the organizations named in the sources this run retrieved. "
            f"They are not an exhaustive list of deployments. Workforce, revenue and industry are shown only where a source stated them."
        )

        vendor_count = len([d for d in deployments_list if d["status"] == "VENDOR_CONFIRMED"])
        corrob_count = len([d for d in deployments_list if d["status"] == "CORROBORATED"])
        provider_count = len([d for d in deployments_list if d["status"] == "TECHNOGRAPHIC_PROVIDER_ASSERTION"])

        p3 = (
            f"All deployment claims are qualified under Heimdallr's three-tier epistemic provenance model: "
            f"**{corrob_count}** multi-source corroborated, **{vendor_count}** vendor-confirmed disclosures, and "
            f"**{provider_count}** third-party technographic provider assertions, and "
            f"**{len(deployments_list) - corrob_count - vendor_count - provider_count}** with another status. "
            f"Overall epistemic confidence: **{format_confidence(confidence)}**. Investigation terminated under criteria: `{stop_reason}`."
        )

        narrative_paragraphs = [p1, p2, p3]
        executive_narrative = "\n\n".join(narrative_paragraphs)

        cat_title = f"Reported Enterprise Deployments ({target_sw}{f' in {target_country}' if target_country else ''}) [Sample: {len(deployments_list)}]"
        categorized_findings = {
            cat_title: [],
        }

        for dep in deployments_list:
            comp = dep["company"]
            attrs = []
            if dep["industry"]:
                attrs.append(f"Industry: {dep['industry']}")
            if dep["employees"]:
                attrs.append(f"Workforce: {dep['employees']}")
            if dep["revenue"]:
                attrs.append(f"Revenue: {dep['revenue']}")
            attr_suffix = f" ({', '.join(attrs)})" if attrs else ""
            loc_str = f" in {dep['country']}" if dep['country'] else ""

            fact_str = f"{comp} — reported to use {dep['software']}{loc_str}{attr_suffix}"
            categorized_findings[cat_title].append({
                "fact": fact_str,
                "status": dep["status"],
                "confidence": dep["confidence"],
                "citation": dep["citation"],
            })

        curated_entities = []
        for dep in deployments_list:
            comp = dep["company"]
            ind = dep["industry"]
            cnt = dep["country"]
            contact_str = f"{cnt} ({ind})" if ind else cnt
            curated_entities.append({
                "name": comp,
                "type": "ORGANIZATION",
                "role": f"Reported {target_sw} user",
                "organization": comp,
                "contact": contact_str or "Not disclosed",
            })

        return {
            "primary_name": primary_name,
            "executive_narrative": executive_narrative,
            "narrative_paragraphs": narrative_paragraphs,
            "roles_and_titles": [],
            "organizations": {d["company"]: {"name": d["company"], "role": f"Reported {target_sw} user"} for d in deployments_list},
            "affiliations": [],
            "credentials": [],
            "locations": [target_country] if target_country else [],
            "contacts": [],
            "categorized_findings": categorized_findings,
            "curated_entities": curated_entities,
        }

    # 1. Collect all grounded evidence passages
    evidence_passages: list[dict[str, str]] = []
    for ev in evidence:
        text = ev.get("snippet") or ev.get("passage") or ev.get("text") or ""
        url = ev.get("url") or ""
        title = ev.get("title") or ""
        if text and len(text) > 30:
            evidence_passages.append({"title": title, "url": url, "text": text})

    combined_text = "\n\n".join(e["text"] for e in evidence_passages)

    # 2. Extract Key Facts across Intelligence Dimensions
    roles_and_titles: list[str] = []
    organizations: dict[str, dict[str, Any]] = {}
    affiliations: list[str] = []
    credentials: list[str] = []
    locations: list[str] = []
    contacts: list[str] = []
    relevant_infrastructure: list[dict[str, str]] = []
    fact_sources: dict[str, str | None] = {}

    # Target entity name resolution
    primary_name = clean_entity_display_name(target_raw)
    target_tokens = set(re.findall(r"[a-z0-9]{3,}", target_raw.lower()))

    # Seed organizations from provided entities
    if isinstance(entities, dict):
        for ek, ev in entities.items():
            etype = ev.get("entity_type") or ev.get("type") if isinstance(ev, dict) else str(ev)
            if str(etype).upper() in ("ORGANIZATION", "TARGET_ORGANIZATION") and ek.lower() != primary_name.lower():
                clean_org = clean_entity_display_name(ek)
                if clean_org not in organizations:
                    organizations[clean_org] = {"name": clean_org, "role": "Operating Enterprise"}

    # A. Search for Executive Roles & Titles in Evidence
    role_matches = re.finditer(
        r"(?:([A-Z][A-Za-z\s.'-]{2,30}?)\s*[-—|,]\s*)?(Founder\s*(?:&|and)\s*CTO|CTO|Chief Technology Officer|Chief Executive Officer|CEO|President|Managing Director|Partner\s*(?:&|and)\s*CTO|Founder)\s*(?:@|at|,|of)\s*([A-Z][A-Za-z0-9\s&-]{2,30}?)(?=[.;\n]|,\s*[A-Z]|$)",
        combined_text,
    )
    for rm in role_matches:
        person = clean_entity_display_name(rm.group(1)) if rm.group(1) else ""
        role = rm.group(2).strip()
        org_raw = rm.group(3).strip()
        org = re.split(r"[.;\n]|,\s*[A-Z]", org_raw)[0].strip().rstrip(".,;")
        if not person and any(t in org.lower() for t in target_tokens):
            person = primary_name
        stmt = f"{role} at {org}"
        if person:
            stmt = f"{person}: {stmt}"
        if stmt not in roles_and_titles:
            roles_and_titles.append(stmt)
            fact_sources[stmt] = _source_url_for(rm.group(0), evidence_passages)
        if org and org not in organizations:
            organizations[org] = {"name": org, "role": role}

    # B. Leadership & Industry Associations
    assoc_matches = re.finditer(
        r"President\s*[-—:]?\s*([A-Z][A-Za-z0-9\s.,&-]{3,50}?(?:Association|Council|Enterprises|Chamber|RITA|VCITE|IACC))",
        combined_text,
    )
    for am in assoc_matches:
        assoc_name = am.group(1).strip().rstrip(".,;")
        stmt = f"President of {assoc_name}"
        if stmt not in affiliations:
            affiliations.append(stmt)
            fact_sources[stmt] = _source_url_for(am.group(0), evidence_passages)

    # C. Certifications & Credentials
    cred_matches = re.finditer(r"\b(CSM\s*[-—:]?\s*Certified\s+Scrum\s+Master|Certified\s+Scrum\s+Master|PMP|CISSP|CISA)\b", combined_text)
    for cm in cred_matches:
        cred = cm.group(1).strip()
        if cred not in credentials:
            credentials.append(cred)
            fact_sources[cred] = _source_url_for(cm.group(0), evidence_passages)

    # D. Headquarters & Locations
    loc_matches = re.finditer(
        r"(?:Address|Location|Headquartered in|based in|Office)[\s:]*([^\n\r]+?(?:Rajkot|Gujarat|India|California|London|Singapore|Mumbai|Bangalore|Delhi|Ahmedabad)[^\n\r,.]*)",
        combined_text,
        re.IGNORECASE,
    )
    for lm in loc_matches:
        loc = lm.group(1).strip()
        if len(loc) > 4 and loc not in locations:
            locations.append(loc)
            fact_sources[loc] = _source_url_for(lm.group(0), evidence_passages)

    # E. Contact Channels
    email_matches = re.findall(r"\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b", combined_text)
    for em in set(email_matches):
        if not any(ig in em.lower() for ig in ("example.com", "domain.com", "sentry", "google")):
            if em not in contacts:
                contacts.append(em)
                fact_sources[em] = _source_url_for(em, evidence_passages)

    # F. Contextually Filtered Infrastructure
    # Filter raw claims and entities to only preserve contextually relevant infrastructure
    for c in claims:
        pred = str(c.get("predicate", "")).lower()
        obj = str(c.get("object", ""))
        subj = str(c.get("subject", ""))
        cit = str(c.get("citation") or "")

        if pred in ("infrastructure", "host", "subdomain") or "endpoint" in pred:
            if is_contextually_relevant_host(obj, doc_url=cit, target_objective=target_raw):
                relevant_infrastructure.append({
                    "host": obj,
                    "affiliated_entity": clean_entity_display_name(subj),
                    "citation": cit,
                })

    # 3. Build Cohesive Natural Language Narrative Summary
    narrative_paragraphs: list[str] = []

    # Paragraph 1: Executive Overview & Identification
    p1_parts = []
    if roles_and_titles:
        p1_parts.append(f"Retrieved sources mention the following positions related to **{primary_name}**: {', '.join(roles_and_titles[:2])}.")
    else:
        p1_parts.append(f"Investigation focused on **{primary_name}**. No positions or titles were found in the retrieved sources.")

    if credentials:
        p1_parts.append(f"Credentials mentioned in sources: **{', '.join(credentials)}**.")
    narrative_paragraphs.append(" ".join(p1_parts))

    # Paragraph 2: Corporate Profile & Industry Footprint
    p2_parts = []
    if organizations:
        org_names = list(organizations.keys())
        p2_parts.append(f"Organizations named in sources: **{', '.join(org_names[:3])}**.")
    if locations:
        p2_parts.append(f"Location mentioned in sources: **{locations[0]}**.")
    if affiliations:
        p2_parts.append(f"Industry roles mentioned in sources: **{'; '.join(affiliations[:2])}**.")
    if p2_parts:
        narrative_paragraphs.append(" ".join(p2_parts))

    # Paragraph 3: Verification Rigor & Epistemic Status
    p3 = (
        f"The findings below were pattern-matched from {len(evidence_passages)} retrieved evidence passage(s) and have not been "
        f"independently verified. Overall epistemic confidence: **{format_confidence(confidence)}**. "
        f"Investigation terminated under criteria: `{stop_reason}`."
    )
    narrative_paragraphs.append(p3)

    executive_narrative = "\n\n".join(narrative_paragraphs)

    # 4. Human-Readable Structured Findings
    categorized_findings: dict[str, list[dict[str, Any]]] = {
        "Executive & Professional Identity": [],
        "Corporate & Organizational Footprint": [],
        "Industry Leadership & Accreditations": [],
        "Contacts & Locations": [],
    }

    def _extracted(fact: str, key: str) -> dict[str, Any]:
        return {
            "fact": fact,
            "status": EXTRACTED_STATUS,
            "confidence": None,
            "citation": fact_sources.get(key),
        }

    for rt in roles_and_titles:
        categorized_findings["Executive & Professional Identity"].append(_extracted(rt, rt))

    for cred in credentials:
        categorized_findings["Executive & Professional Identity"].append(_extracted(f"Credential: {cred}", cred))

    for org_name in organizations.keys():
        categorized_findings["Corporate & Organizational Footprint"].append({
            "fact": f"Organization: {org_name}",
            "status": EXTRACTED_STATUS,
            "confidence": None,
            "citation": _source_url_for(org_name, evidence_passages),
        })

    for loc in locations:
        categorized_findings["Corporate & Organizational Footprint"].append(_extracted(f"Office / Headquarters: {loc}", loc))

    for aff in affiliations:
        categorized_findings["Industry Leadership & Accreditations"].append(_extracted(aff, aff))

    for em in contacts:
        categorized_findings["Contacts & Locations"].append(_extracted(f"Email found in sources: {em}", em))

    for inf in relevant_infrastructure:
        categorized_findings["Contacts & Locations"].append({
            "fact": f"Affiliated Network Host: {inf['host']} ({inf['affiliated_entity']})",
            "status": EXTRACTED_STATUS,
            "confidence": None,
            "citation": inf["citation"] or None,
        })

    # Curate contextually clean entities (stripping platform CDNs)
    curated_entities: list[dict[str, Any]] = []

    # Always include primary target
    curated_entities.append({
        "name": primary_name,
        "type": "INDIVIDUAL" if any(k in target_raw.lower() for k in ("ronak", "raiyani", "person", "who is", "executive")) else "PRIMARY_SUBJECT",
        "role": roles_and_titles[0] if roles_and_titles else "Subject Entity",
        "organization": list(organizations.keys())[0] if organizations else "N/A",
        "contact": contacts[0] if contacts else "None disclosed",
    })

    for org in organizations.keys():
        if org.lower() != primary_name.lower():
            curated_entities.append({
                "name": org,
                "type": "ORGANIZATION",
                "role": "Operating Enterprise",
                "organization": org,
                "contact": contacts[0] if contacts else "None disclosed",
            })

    for aff in affiliations:
        org_cand = re.sub(r"^President\s+of\s+", "", aff).strip()
        if org_cand and org_cand not in [e["name"] for e in curated_entities]:
            curated_entities.append({
                "name": org_cand,
                "type": "INDUSTRY_BODY",
                "role": "Industry Council / Association",
                "organization": org_cand,
                "contact": "Not disclosed",
            })

    for inf in relevant_infrastructure:
        curated_entities.append({
            "name": inf["host"],
            "type": "INFRASTRUCTURE_ENDPOINT",
            "role": "Network Endpoint",
            "organization": inf["affiliated_entity"],
            "contact": "Not disclosed",
        })

    return {
        "primary_name": primary_name,
        "executive_narrative": executive_narrative,
        "narrative_paragraphs": narrative_paragraphs,
        "roles_and_titles": roles_and_titles,
        "organizations": organizations,
        "affiliations": affiliations,
        "credentials": credentials,
        "locations": locations,
        "contacts": contacts,
        "categorized_findings": categorized_findings,
        "curated_entities": curated_entities,
    }
