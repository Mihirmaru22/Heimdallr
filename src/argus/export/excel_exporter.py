"""Heimdallr OSINT Excel Dossier Exporter.

Generates structured, multi-sheet Excel (.xlsx) workbooks containing:
1. Executive Dossier: Target, objective, run metadata, confidence, and metric summary.
2. Verified Intelligence: Claim triples, epistemic statuses, confidence scores, and citations.
3. Entity Dossier: Discovered entities, classifications, roles, and contacts.
4. Evidence & Citations: Source URLs, verbatim text passages, content hashes, and clusters.
5. Audit & Action Trail: Chronological execution trajectory, specialist invocations, and rationale.
"""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import re
from typing import Any

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from argus.export.narrative import NO_SOURCE_RECORDED, format_confidence, generate_narrative_intelligence
from argus.investigation.relevance import clean_entity_name, is_contextually_relevant_host


# Color Palette
COLOR_HEADER_BG = "1A2530"       # Dark Navy Slate
COLOR_HEADER_FG = "FFFFFF"       # White
COLOR_SUBHEADER_BG = "2E4053"    # Slate Accent
COLOR_ZEBRA = "F8F9FA"           # Light subtle gray

# Status Badge Styles (Fill, Font)
STATUS_STYLES = {
    "SUPPORTED": ("E2F0D9", "385723"),
    "CORROBORATED": ("C6EFCE", "006100"),
    "ACTIVE": ("E2F0D9", "385723"),
    "VERIFIED": ("C6EFCE", "006100"),
    "VENDOR_CONFIRMED": ("C6EFCE", "006100"),
    "TECHNOGRAPHIC_PROVIDER_ASSERTION": ("FFF2CC", "7F6000"),
    "INFERRED": ("FFF2CC", "7F6000"),
    "PENDING": ("FFF2CC", "7F6000"),
    "CONTRADICTED": ("FCE4D6", "C65911"),
    "REFUTED": ("FCE4D6", "C65911"),
    "HISTORICAL_RESIGNED": ("F2DCDB", "9C0006"),
    "NOT_FOUND": ("EBEBEB", "595959"),
    "UNVERIFIED": ("EBEBEB", "595959"),
}

THIN_BORDER = Border(
    left=Side(style="thin", color="D9D9D9"),
    right=Side(style="thin", color="D9D9D9"),
    top=Side(style="thin", color="D9D9D9"),
    bottom=Side(style="thin", color="D9D9D9"),
)

HEADER_FONT = Font(name="Segoe UI", size=11, bold=True, color=COLOR_HEADER_FG)
TITLE_FONT = Font(name="Segoe UI", size=15, bold=True, color=COLOR_HEADER_FG)
SECTION_FONT = Font(name="Segoe UI", size=12, bold=True, color="1A2530")
BODY_FONT = Font(name="Segoe UI", size=10)
BOLD_BODY_FONT = Font(name="Segoe UI", size=10, bold=True)
MUTED_FONT = Font(name="Segoe UI", size=9, italic=True, color="7F7F7F")


def sanitize_filename(name: str) -> str:
    """Create a safe slug for filenames."""
    s = re.sub(r"[^\w\s-]", "", name).strip().lower()
    return re.sub(r"[-\s]+", "_", s)[:40] or "investigation"


def auto_fit_columns(worksheet: Any, max_len_cap: int = 65, min_len: int = 12) -> None:
    """Adjust column widths dynamically based on cell content."""
    for col in worksheet.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val = cell.value
            if val is not None:
                # First line only for multiline
                val_str = str(val).split("\n")[0]
                max_len = max(max_len, len(val_str))
        target_width = min(max(max_len + 3, min_len), max_len_cap)
        worksheet.column_dimensions[col_letter].width = target_width


class OSINTExcelExporter:
    """Exports Heimdallr investigation states into styled multi-tab Excel files."""

    def __init__(self, export_dir: str | Path = "exports") -> None:
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def export_investigation(
        self,
        investigation_data: dict[str, Any],
        output_filepath: str | Path | None = None,
    ) -> Path:
        """Export investigation dictionary or InvestigationState to an Excel (.xlsx) file."""
        target_name = (
            investigation_data.get("target")
            or investigation_data.get("objective")
            or "OSINT_Target"
        )
        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        slug = sanitize_filename(target_name)

        if output_filepath is None:
            filename = f"heimdallr_osint_{slug}_{timestamp_str}.xlsx"
            out_path = self.export_dir / filename
        else:
            out_path = Path(output_filepath)
            out_path.parent.mkdir(parents=True, exist_ok=True)

        wb = openpyxl.Workbook()
        # Remove default sheet
        wb.remove(wb.active)

        self._build_summary_sheet(wb, investigation_data, target_name)
        self._build_claims_sheet(wb, investigation_data)
        if investigation_data.get("rejected_claims"):
            self._build_rejected_sheet(wb, investigation_data)
        self._build_entities_sheet(wb, investigation_data)
        self._build_evidence_sheet(wb, investigation_data)
        self._build_audit_sheet(wb, investigation_data)

        wb.save(out_path)
        return out_path

    def _build_summary_sheet(
        self, wb: openpyxl.Workbook, data: dict[str, Any], target_name: str
    ) -> None:
        """Tab 1: High level executive dossier, narrative brief, and KPI overview."""
        ws = wb.create_sheet(title="Executive Summary")
        ws.views.sheetView[0].showGridLines = True

        synth = generate_narrative_intelligence(data)
        primary_name = synth.get("primary_name") or clean_entity_name(target_name)

        # Header Title Banner
        ws.merge_cells("A1:F2")
        title_cell = ws["A1"]
        title_cell.value = f"HEIMDALLR V4 — OSINT INTELLIGENCE DOSSIER: {primary_name.upper()}"
        title_cell.font = TITLE_FONT
        title_cell.fill = PatternFill(start_color=COLOR_HEADER_BG, end_color=COLOR_HEADER_BG, fill_type="solid")
        title_cell.alignment = Alignment(horizontal="center", vertical="center")

        claims = data.get("claims", [])
        evidence = data.get("evidence", [])
        actions = data.get("research_actions", [])
        confidence = data.get("confidence")
        stop_reason = data.get("stop_reason") or "UNKNOWN"

        # Details Table
        details = [
            ("Investigation ID", data.get("investigation_id", "N/A")),
            ("Full Objective", data.get("objective", target_name)),
            ("Execution Status", "COMPLETED" if data.get("is_stopped", True) else "IN_PROGRESS"),
            ("Termination Reason", str(stop_reason)),
            ("Research Steps Taken", len(actions)),
            ("Epistemic Confidence", format_confidence(confidence)),
            ("Total Evidence Items", len(evidence)),
            ("Generated At (UTC)", datetime.now(timezone.utc).isoformat()),
        ]

        row = 4
        ws.cell(row=row, column=1, value="MISSION METADATA & PARAMETERS").font = SECTION_FONT
        row += 1

        for label, val in details:
            ws.cell(row=row, column=1, value=label).font = BOLD_BODY_FONT
            ws.cell(row=row, column=1).fill = PatternFill(start_color=COLOR_ZEBRA, fill_type="solid")
            ws.cell(row=row, column=1).border = THIN_BORDER

            ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=6)
            c = ws.cell(row=row, column=2, value=str(val))
            c.font = BODY_FONT
            c.border = THIN_BORDER
            row += 1

        row += 2
        ws.cell(row=row, column=1, value="EXECUTIVE INTELLIGENCE BRIEF").font = SECTION_FONT
        row += 1

        narrative_paragraphs = synth.get("narrative_paragraphs", [])
        if narrative_paragraphs:
            for p in narrative_paragraphs:
                ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
                c = ws.cell(row=row, column=1, value=p)
                c.font = BODY_FONT
                c.alignment = Alignment(wrap_text=True, vertical="top")
                ws.row_dimensions[row].height = 40
                row += 1
        else:
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
            c = ws.cell(row=row, column=1, value=synth.get("executive_narrative", "Intelligence synthesis in progress."))
            c.font = BODY_FONT
            c.alignment = Alignment(wrap_text=True, vertical="top")
            row += 1

        limitations = data.get("limitations") or []
        if limitations:
            row += 2
            ws.cell(row=row, column=1, value="LIMITATIONS & OPEN QUESTIONS").font = SECTION_FONT
            row += 1
            for lim in limitations:
                ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
                c = ws.cell(row=row, column=1, value=f"• {lim}")
                c.font = BODY_FONT
                c.alignment = Alignment(wrap_text=True, vertical="top")
                row += 1

        row += 2
        ws.cell(row=row, column=1, value="KEY CORROBORATED FINDINGS").font = SECTION_FONT
        row += 1

        categorized_findings = synth.get("categorized_findings", {})
        has_cat = False
        for category, items in categorized_findings.items():
            if items:
                has_cat = True
                ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
                cat_cell = ws.cell(row=row, column=1, value=f"— {category.upper()} —")
                cat_cell.font = Font(name="Segoe UI", size=10, bold=True, color=COLOR_SUBHEADER_BG)
                row += 1

                for it in items:
                    conf_pct = format_confidence(it.get("confidence"), decimals=0)
                    status = it.get("status") or "UNVERIFIED"
                    cit = it.get("citation") or NO_SOURCE_RECORDED
                    bullet_text = f"• {it.get('fact')}  [{status} | {conf_pct}] (Source: {cit})"
                    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
                    c = ws.cell(row=row, column=1, value=bullet_text)
                    c.font = BODY_FONT
                    row += 1

        if not has_cat:
            supported_claims = [c for c in claims if c.get("status") in ("SUPPORTED", "CORROBORATED", "VENDOR_CONFIRMED", "TECHNOGRAPHIC_PROVIDER_ASSERTION")]
            if supported_claims:
                for sc in supported_claims[:10]:
                    subj = clean_entity_name(sc.get("subject", ""))
                    pred = sc.get("predicate", "").replace("_", " ").title()
                    obj = sc.get("object", "")
                    conf_val = sc.get("confidence")
                    citation = sc.get("citation") or sc.get("url") or NO_SOURCE_RECORDED
                    bullet_text = f"• {subj} — {pred}: {obj} (Confidence: {format_confidence(conf_val, decimals=0)}, Citation: {citation})"
                    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
                    c = ws.cell(row=row, column=1, value=bullet_text)
                    c.font = BODY_FONT
                    row += 1
            else:
                ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
                ws.cell(row=row, column=1, value="No claims confirmed above threshold.").font = MUTED_FONT

        auto_fit_columns(ws)

    def _build_claims_sheet(self, wb: openpyxl.Workbook, data: dict[str, Any]) -> None:
        """Tab 2: Verified Intelligence and Relational Claims."""
        ws = wb.create_sheet(title="Verified Claims")
        ws.views.sheetView[0].showGridLines = True

        headers = [
            "Claim ID", "Subject Entity", "Relationship / Predicate",
            "Object Value", "Epistemic Status", "Confidence", "Supporting Citations"
        ]

        for col_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col_idx, value=h)
            cell.font = HEADER_FONT
            cell.fill = PatternFill(start_color=COLOR_HEADER_BG, end_color=COLOR_HEADER_BG, fill_type="solid")
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = THIN_BORDER

        ws.row_dimensions[1].height = 25

        claims = data.get("claims", [])
        evidence_map = {e.get("evidence_id"): e for e in data.get("evidence", [])}

        row_idx = 2
        for claim in claims:
            cid = claim.get("claim_id") or f"clm_{row_idx - 1:03d}"
            subj = claim.get("subject") or "N/A"
            pred = claim.get("predicate") or "N/A"
            obj = claim.get("object") or "N/A"
            status = str(claim.get("status") or "UNVERIFIED").upper()
            conf = claim.get("confidence")

            # Resolve citation snippets
            ev_ids = claim.get("evidence_ids") or []
            citations = []
            for eid in ev_ids:
                if eid in evidence_map:
                    ev_item = evidence_map[eid]
                    url_snippet = ev_item.get("url") or ""
                    passage = ev_item.get("snippet") or ev_item.get("passage") or ""
                    citations.append(f"[{url_snippet}]: {passage[:100]}...")
            citation_str = "\n".join(citations) if citations else str(claim.get("source_url") or claim.get("citation") or claim.get("url") or NO_SOURCE_RECORDED)

            c_id_cell = ws.cell(row=row_idx, column=1, value=cid)
            c_subj_cell = ws.cell(row=row_idx, column=2, value=subj)
            c_pred_cell = ws.cell(row=row_idx, column=3, value=pred)
            c_obj_cell = ws.cell(row=row_idx, column=4, value=obj)
            c_stat_cell = ws.cell(row=row_idx, column=5, value=status)
            c_conf_cell = ws.cell(row=row_idx, column=6, value=format_confidence(conf))
            c_cit_cell = ws.cell(row=row_idx, column=7, value=citation_str)

            for c in (c_id_cell, c_subj_cell, c_pred_cell, c_obj_cell, c_conf_cell, c_cit_cell):
                c.font = BODY_FONT
                c.border = THIN_BORDER
                if row_idx % 2 == 1:
                    c.fill = PatternFill(start_color=COLOR_ZEBRA, fill_type="solid")

            # Style Status Badge
            bg_color, fg_color = STATUS_STYLES.get(status, ("F2F2F2", "000000"))
            c_stat_cell.fill = PatternFill(start_color=bg_color, fill_type="solid")
            c_stat_cell.font = Font(name="Segoe UI", size=10, bold=True, color=fg_color)
            c_stat_cell.alignment = Alignment(horizontal="center", vertical="center")
            c_stat_cell.border = THIN_BORDER

            c_cit_cell.alignment = Alignment(vertical="center", wrap_text=True)
            row_idx += 1

        auto_fit_columns(ws)

    def _build_rejected_sheet(self, wb: openpyxl.Workbook, data: dict[str, Any]) -> None:
        """Candidates the evidence check turned down, with its reason; not findings."""
        ws = wb.create_sheet(title="Rejected Candidates")
        headers = ["Subject", "Relationship", "Value", "Why rejected", "Source"]
        for col_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col_idx, value=h)
            cell.font = HEADER_FONT
            cell.fill = PatternFill(start_color=COLOR_HEADER_BG, end_color=COLOR_HEADER_BG, fill_type="solid")
            cell.border = THIN_BORDER
        for row_idx, claim in enumerate(data.get("rejected_claims", []), start=2):
            values = (
                claim.get("subject") or "",
                claim.get("predicate") or "",
                str(claim.get("object") or "")[:300],
                (claim.get("verification") or {}).get("reason", ""),
                claim.get("citation") or NO_SOURCE_RECORDED,
            )
            for col_idx, value in enumerate(values, start=1):
                c = ws.cell(row=row_idx, column=col_idx, value=value)
                c.font = BODY_FONT
                c.border = THIN_BORDER
        auto_fit_columns(ws)

    def _build_entities_sheet(self, wb: openpyxl.Workbook, data: dict[str, Any]) -> None:
        """Tab 3: Discovered Entities and Attribute Profiles."""
        ws = wb.create_sheet(title="Entities Dossier")
        ws.views.sheetView[0].showGridLines = True

        headers = [
            "Entity Name", "Type / Classification", "Aliases / Handles",
            "Role / Responsibility", "Affiliated Organization", "Verified Contact"
        ]

        for col_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col_idx, value=h)
            cell.font = HEADER_FONT
            cell.fill = PatternFill(start_color=COLOR_HEADER_BG, end_color=COLOR_HEADER_BG, fill_type="solid")
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = THIN_BORDER

        ws.row_dimensions[1].height = 25

        synth = generate_narrative_intelligence(data)
        curated_entities = synth.get("curated_entities", [])
        curated_names = {e["name"].strip().lower() for e in curated_entities if e.get("name")}

        target_obj = data.get("objective", "") or data.get("target", "")
        primary_name = synth.get("primary_name", "")

        raw_entities = data.get("entities", {})
        entity_list = list(curated_entities)

        if isinstance(raw_entities, dict):
            for k, v in raw_entities.items():
                if not k or k.strip().lower() in curated_names:
                    continue
                # Contextual relevance evaluation:
                # If entity looks like a domain/host, verify context and relevance
                if "." in k and not (" " in k):
                    if not is_contextually_relevant_host(k, target_objective=target_obj, target_entities=[primary_name]):
                        continue
                clean_name = clean_entity_name(k)
                if isinstance(v, dict):
                    entity_list.append({"name": clean_name, **v})
                else:
                    entity_list.append({"name": clean_name, "type": str(v)})
        elif isinstance(raw_entities, list):
            for e in raw_entities:
                ename = e if isinstance(e, str) else (e.get("name") if isinstance(e, dict) else "")
                if not ename or ename.strip().lower() in curated_names:
                    continue
                if "." in ename and not (" " in ename):
                    if not is_contextually_relevant_host(ename, target_objective=target_obj, target_entities=[primary_name]):
                        continue
                if isinstance(e, str):
                    entity_list.append({"name": clean_entity_name(e), "type": "ORGANIZATION"})
                elif isinstance(e, dict):
                    entity_list.append({**e, "name": clean_entity_name(ename)})

        row_idx = 2
        for ent in entity_list:
            name = ent.get("name") or ent.get("canonical_name") or "N/A"
            etype = ent.get("entity_type") or ent.get("type") or "ORGANIZATION"
            aliases = ", ".join(ent.get("aliases", [])) if ent.get("aliases") else "None recorded"
            meta = ent.get("metadata") or {}
            role = ent.get("title") or meta.get("title") or meta.get("responsibility") or ent.get("role") or "N/A"
            org = ent.get("organization") or meta.get("org") or "N/A"
            contact = ent.get("email") or meta.get("email") or meta.get("contact") or ent.get("contact") or "None disclosed"

            row_cells = [
                ws.cell(row=row_idx, column=1, value=name),
                ws.cell(row=row_idx, column=2, value=etype),
                ws.cell(row=row_idx, column=3, value=aliases),
                ws.cell(row=row_idx, column=4, value=role),
                ws.cell(row=row_idx, column=5, value=org),
                ws.cell(row=row_idx, column=6, value=contact),
            ]

            for c in row_cells:
                c.font = BODY_FONT
                c.border = THIN_BORDER
                if row_idx % 2 == 1:
                    c.fill = PatternFill(start_color=COLOR_ZEBRA, fill_type="solid")

            row_idx += 1

        auto_fit_columns(ws)

    def _build_evidence_sheet(self, wb: openpyxl.Workbook, data: dict[str, Any]) -> None:
        """Tab 4: Evidence citations, source URLs, and content excerpts."""
        ws = wb.create_sheet(title="Evidence & Sources")
        ws.views.sheetView[0].showGridLines = True

        headers = [
            "Evidence ID", "Source Title", "Source URL / Destination",
            "Source Type", "Verbatim Passage / Extraction", "Cluster ID / Hash"
        ]

        for col_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col_idx, value=h)
            cell.font = HEADER_FONT
            cell.fill = PatternFill(start_color=COLOR_HEADER_BG, end_color=COLOR_HEADER_BG, fill_type="solid")
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = THIN_BORDER

        ws.row_dimensions[1].height = 25

        evidence = data.get("evidence", [])
        row_idx = 2
        for ev in evidence:
            eid = ev.get("evidence_id") or f"evi_{row_idx - 1:03d}"
            title = ev.get("title") or "Source Document"
            url = ev.get("url") or "Internal / Regulatory Record"
            stype = ev.get("source_type") or "WEB_DOCUMENT"
            passage = ev.get("snippet") or ev.get("passage") or ev.get("text") or ""
            cluster = ev.get("syndication_cluster_id") or ev.get("content_hash") or "Unique Domain"

            row_cells = [
                ws.cell(row=row_idx, column=1, value=eid),
                ws.cell(row=row_idx, column=2, value=title),
                ws.cell(row=row_idx, column=3, value=url),
                ws.cell(row=row_idx, column=4, value=stype),
                ws.cell(row=row_idx, column=5, value=passage),
                ws.cell(row=row_idx, column=6, value=cluster),
            ]

            for c in row_cells:
                c.font = BODY_FONT
                c.border = THIN_BORDER
                if row_idx % 2 == 1:
                    c.fill = PatternFill(start_color=COLOR_ZEBRA, fill_type="solid")

            # Enable text wrap on passage
            row_cells[4].alignment = Alignment(wrap_text=True, vertical="center")
            row_idx += 1

        auto_fit_columns(ws, max_len_cap=80)

    def _build_audit_sheet(self, wb: openpyxl.Workbook, data: dict[str, Any]) -> None:
        """Tab 5: Audit trail of research actions and specialist dispatches."""
        ws = wb.create_sheet(title="Audit & Actions Trail")
        ws.views.sheetView[0].showGridLines = True

        headers = [
            "Step", "Action Type / Event", "Specialist / Provider",
            "Executed Query / Objective", "Rationale / Decision Summary", "Timestamp"
        ]

        for col_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col_idx, value=h)
            cell.font = HEADER_FONT
            cell.fill = PatternFill(start_color=COLOR_HEADER_BG, end_color=COLOR_HEADER_BG, fill_type="solid")
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = THIN_BORDER

        ws.row_dimensions[1].height = 25

        audit = data.get("audit_trail") or []
        actions = data.get("research_actions") or []

        def to_dict(item: Any) -> dict[str, Any]:
            if isinstance(item, dict):
                return item
            if hasattr(item, "model_dump"):
                return item.model_dump()
            if hasattr(item, "__dict__"):
                return item.__dict__
            return {}

        # Merge audit trail or actions
        combined = []
        for i, raw_act in enumerate(actions, start=1):
            act = to_dict(raw_act)
            combined.append({
                "step": i,
                "type": "RESEARCH_ACTION",
                "specialist": act.get("specialist", "GENERALIST"),
                "query": act.get("query", ""),
                "rationale": act.get("rationale", act.get("summary", "Executed research cycle")),
                "timestamp": act.get("timestamp", datetime.now(timezone.utc).isoformat()),
            })

        for raw_entry in audit:
            entry = to_dict(raw_entry)
            details = entry.get("details", {})
            if not isinstance(details, dict):
                details = {"raw": str(details)}
            combined.append({
                "step": "-",
                "type": entry.get("action_type", "AUDIT_EVENT"),
                "specialist": details.get("specialist", "SYSTEM"),
                "query": str(details),
                "rationale": entry.get("rationale", ""),
                "timestamp": entry.get("timestamp", ""),
            })

        row_idx = 2
        for item in combined:
            row_cells = [
                ws.cell(row=row_idx, column=1, value=str(item["step"])),
                ws.cell(row=row_idx, column=2, value=item["type"]),
                ws.cell(row=row_idx, column=3, value=item["specialist"]),
                ws.cell(row=row_idx, column=4, value=item["query"]),
                ws.cell(row=row_idx, column=5, value=item["rationale"]),
                ws.cell(row=row_idx, column=6, value=item["timestamp"]),
            ]

            for c in row_cells:
                c.font = BODY_FONT
                c.border = THIN_BORDER
                if row_idx % 2 == 1:
                    c.fill = PatternFill(start_color=COLOR_ZEBRA, fill_type="solid")

            row_idx += 1

        auto_fit_columns(ws, max_len_cap=70)
