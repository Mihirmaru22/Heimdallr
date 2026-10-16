"""Heimdallr OSINT Markdown Dossier Exporter.

Generates clean, human-readable Markdown (.md) Intelligence Dossiers containing:
1. Executive Intelligence Brief: Cohesive narrative synthesis of the subject's identity,
   corporate leadership, operating footprint, and verified credentials.
2. Mission Metadata: Objective, confidence score, research steps, and termination criteria.
3. Key Corroborated Findings: Structured findings categorized by intelligence dimension.
4. Entity Directory: Clean canonical entities, classifications, roles, and contacts.
5. Grounded Evidence & Sources: Authoritative citations and verbatim source passages.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

from argus.export.narrative import NO_SOURCE_RECORDED, format_confidence, generate_narrative_intelligence
from argus.investigation.relevance import clean_entity_name


def sanitize_filename(name: str) -> str:
    """Create a safe slug for filenames."""
    s = re.sub(r"[^\w\s-]", "", name).strip().lower()
    return re.sub(r"[-\s]+", "_", s)[:40] or "investigation"


class OSINTMarkdownExporter:
    """Exports Heimdallr investigation states into structured, human-readable Markdown reports."""

    def __init__(self, export_dir: str | Path = "exports") -> None:
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def export_investigation(
        self,
        investigation_data: dict[str, Any],
        output_filepath: str | Path | None = None,
    ) -> Path:
        """Export investigation data or state dictionary to a clean Markdown (.md) dossier."""
        target_name = (
            investigation_data.get("target")
            or investigation_data.get("objective")
            or "OSINT_Target"
        )
        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        slug = sanitize_filename(target_name)

        if output_filepath is None:
            filename = f"heimdallr_osint_{slug}_{timestamp_str}.md"
            out_path = self.export_dir / filename
        else:
            out_path = Path(output_filepath)
            out_path.parent.mkdir(parents=True, exist_ok=True)

        content = self._render_markdown_report(investigation_data, target_name)
        out_path.write_text(content, encoding="utf-8")
        return out_path

    def _render_markdown_report(self, data: dict[str, Any], target_name: str) -> str:
        """Render the complete Markdown document."""
        synth = generate_narrative_intelligence(data)

        primary_name = synth.get("primary_name", clean_entity_name(target_name))
        exec_narrative = synth.get("executive_narrative", "")
        categorized_findings = synth.get("categorized_findings", {})
        curated_entities = synth.get("curated_entities", [])

        claims = data.get("claims", [])
        evidence = data.get("evidence", [])
        actions = data.get("research_actions", [])
        confidence = data.get("confidence")
        stop_reason = data.get("stop_reason") or "UNKNOWN"
        inv_id = data.get("investigation_id", "N/A")
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        lines: list[str] = []

        # 1. Header Banner
        lines.append(f"# HEIMDALLR V4 — OSINT INTELLIGENCE DOSSIER")
        lines.append(f"## Target Subject: {primary_name.upper()}\n")

        # 2. Executive Metadata Box
        lines.append("### Mission Metadata & Operational Parameters")
        lines.append(f"- **Target Objective:** {data.get('objective', target_name)}")
        lines.append(f"- **Investigation ID:** `{inv_id}`")
        lines.append(f"- **Generated Date:** {now_utc}")
        lines.append(f"- **Overall Epistemic Confidence:** **{format_confidence(confidence)}**")
        lines.append(f"- **Research Actions Completed:** {len(actions)}")
        lines.append(f"- **Authoritative Evidence Passages:** {len(evidence)}")
        lines.append(f"- **Investigation Stopping Reason:** `{stop_reason}`")
        lines.append("\n---\n")

        # 3. Executive Intelligence Brief (Prose narrative)
        lines.append("## Executive Intelligence Brief\n")
        lines.append(exec_narrative)
        lines.append("\n---\n")

        # 3b. What this investigation did not establish
        limitations = data.get("limitations") or []
        if limitations:
            lines.append("## Limitations & Open Questions\n")
            for lim in limitations:
                lines.append(f"- {lim}")
            lines.append("\n---\n")

        # 4. Categorized Verified Findings
        lines.append("## Key Corroborated Findings\n")
        for category, items in categorized_findings.items():
            if items:
                lines.append(f"### {category}")
                for it in items:
                    conf_pct = format_confidence(it.get("confidence"), decimals=0)
                    status = it.get("status") or "UNVERIFIED"
                    cit = it.get("citation") or NO_SOURCE_RECORDED
                    lines.append(f"- **{it.get('fact')}** `[{status} | {conf_pct}]`  ")
                    lines.append(f"  *Source Citation:* {cit}")
                lines.append("")

        lines.append("---\n")

        # 5. Identified Entities Dossier
        lines.append("## Identified Entities & Operational Profiles\n")
        if curated_entities:
            lines.append("| Entity Name | Classification | Primary Role | Affiliated Org | Verified Contact |")
            lines.append("|:---|:---|:---|:---|:---|")
            for ent in curated_entities:
                ename = ent.get("name", "N/A")
                etype = ent.get("type", "ORGANIZATION")
                erole = ent.get("role", "N/A")
                eorg = ent.get("organization", "N/A")
                econtact = ent.get("contact", "None disclosed")
                lines.append(f"| **{ename}** | `{etype}` | {erole} | {eorg} | {econtact} |")
            lines.append("")
        else:
            lines.append("*No distinct external entities isolated.*\n")

        lines.append("---\n")

        # 6. Authoritative Evidence & Source Passages
        lines.append("## Corroborated Evidence & Source Citations\n")
        if evidence:
            for idx, ev in enumerate(evidence, start=1):
                title = ev.get("title") or "Source Document"
                url = ev.get("url") or "Local Document"
                passage = ev.get("snippet") or ev.get("passage") or ev.get("text") or "Passage recorded."
                passage_clean = passage.strip().replace("\n", " ")
                lines.append(f"### Source [{idx}]: {title}")
                lines.append(f"- **Location / URL:** [{url}]({url})")
                lines.append(f"- **Verified Content Extraction:**")
                lines.append(f"  > \"{passage_clean}\"")
                lines.append("")
        else:
            lines.append("*No external evidence passages captured.*\n")

        lines.append("---\n")
        lines.append(f"*Dossier synthesized by Heimdallr V4 Autonomous Intelligence Engine at {now_utc}.*")

        return "\n".join(lines)
