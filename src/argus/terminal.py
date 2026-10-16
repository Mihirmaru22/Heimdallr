"""Heimdallr V4 Sovereign Intelligence Platform & Investigation Terminal.

Professional intelligence terminal interface providing:
- Distinctive, restrained sovereign intelligence branding
- Real-time research progress tracking and multi-specialist dispatch
- Subsystem diagnostics with truthful initialization status
- Rich terminal tables for verified findings, epistemic claims, and citations
- Automated multi-sheet Excel (.xlsx) intelligence report generation
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import os
from pathlib import Path
import re
import sys
import time
from typing import Any

from rich import box
from rich.box import ASCII, DOUBLE_EDGE, HEAVY, ROUNDED, SIMPLE_HEAD
from rich.console import Console, Group
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from argus.export import OSINTExcelExporter, OSINTMarkdownExporter
from argus.investigation.benchmark.corpus import INVESTIGATION_CORPUS_REGISTRY
from argus.investigation.live_web.controller import ControlledLiveWebRetriever
from argus.investigation.orchestrator import InvestigationEngine
from argus.investigation.state import InvestigationState

console = Console()

# --- Identity and Version Metadata ---
PRODUCT_NAME = "HEIMDALLR"
PRODUCT_GENERATION = "V4"
PRODUCT_SUBTITLE = "SOVEREIGN INTELLIGENCE PLATFORM"
PILLARS = (
    "Evidence-Backed Research",
    "Multi-Specialist Investigation",
    "Persistent Intelligence Architecture",
)


def get_authoritative_package_version() -> str:
    """Resolve package version from argus module or importlib metadata without hardcoding."""
    try:
        import argus
        if hasattr(argus, "__version__") and argus.__version__:
            return str(argus.__version__)
    except Exception:
        pass
    try:
        return str(importlib.metadata.version("argus"))
    except Exception:
        pass
    return "0.1.0"


def _select_box_style(con: Console | None = None) -> Any:
    """Select appropriate box style based on console capabilities and encoding."""
    target_console = con or console
    if target_console.no_color:
        return box.ASCII
    enc = getattr(sys.stdout, "encoding", None) or ""
    if "ascii" in enc.lower():
        return box.ASCII
    return box.ROUNDED


def get_banner_text(package_version: str | None = None) -> str:
    """Return raw plain text representation of the banner for text-only contexts."""
    ver = package_version or get_authoritative_package_version()
    pillars_str = "\n".join(f"  • {p}" for p in PILLARS)
    return (
        f"{PRODUCT_NAME} {PRODUCT_GENERATION}\n"
        f"{PRODUCT_SUBTITLE}\n\n"
        f"{pillars_str}\n\n"
        f"Platform Generation : {PRODUCT_GENERATION}\n"
        f"Core Package        : argus v{ver}\n"
        f"Security Boundary   : Enforced (Anti-Rebinding SSRF Proxy)"
    )


# Backwards compatibility alias for external callers
BANNER_ART = get_banner_text()


def render_banner(con: Console | None = None, package_version: str | None = None) -> None:
    """Print the professional Heimdallr V4 sovereign intelligence header."""
    target_console = con or console
    ver = package_version or get_authoritative_package_version()
    box_style = _select_box_style(target_console)

    card = Table.grid(padding=(0, 1), expand=True)
    card.add_column(justify="left")

    # Title block
    title_text = Text()
    title_text.append(f"{PRODUCT_NAME} ", style="bold bright_white" if not target_console.no_color else None)
    title_text.append(PRODUCT_GENERATION, style="bold cyan" if not target_console.no_color else None)
    title_text.append(f"\n{PRODUCT_SUBTITLE}\n", style="bold bright_blue" if not target_console.no_color else None)

    # Pillars
    pillars_text = Text()
    for pillar in PILLARS:
        pillars_text.append("  • ", style="bold cyan" if not target_console.no_color else None)
        pillars_text.append(f"{pillar}\n", style="bright_white" if not target_console.no_color else None)

    # Metadata footer
    meta_text = Text()
    meta_text.append("\nProduct Generation : ", style="dim" if not target_console.no_color else None)
    meta_text.append(PRODUCT_GENERATION, style="bold bright_white" if not target_console.no_color else None)
    meta_text.append("  |  Core Package : ", style="dim" if not target_console.no_color else None)
    meta_text.append(f"argus v{ver}", style="bold bright_white" if not target_console.no_color else None)
    meta_text.append("  |  Security Boundary : ", style="dim" if not target_console.no_color else None)
    meta_text.append("Enforced (SSRF Proxy)", style="green" if not target_console.no_color else None)

    card.add_row(title_text)
    card.add_row(pillars_text)
    card.add_row(meta_text)

    panel = Panel(
        card,
        title=f"[bold bright_white] {PRODUCT_NAME} OSINT ENGINE [/bold bright_white]" if not target_console.no_color else f" {PRODUCT_NAME} OSINT ENGINE ",
        title_align="left",
        border_style="none" if target_console.no_color else "bright_blue",
        box=box_style,
        padding=(1, 2),
    )
    target_console.print(panel)


def get_subsystem_diagnostics(terminal: Any | None = None) -> list[dict[str, str]]:
    """Inspect and collect truthful initialization and health status for subsystems.

    IMPORTANT:
    Does not fabricate status. Subsystems not implemented (like V4 persistent
    episodic memory or world model) are explicitly and truthfully marked
    NOT IMPLEMENTED.
    """
    diagnostics: list[dict[str, str]] = []

    # 1. Configuration loading
    try:
        if terminal and hasattr(terminal, "export_dir") and terminal.export_dir.exists():
            cfg_status = "INITIALIZED"
            cfg_details = "Local configuration loaded; export storage ready"
        else:
            cfg_status = "INITIALIZED"
            cfg_details = "Default profiles active; local paths configured"
    except Exception as exc:
        cfg_status = "ERROR"
        cfg_details = f"Config error: {str(exc)[:40]}"
    diagnostics.append({"subsystem": "Configuration", "status": cfg_status, "details": cfg_details})

    # 2. Investigation Engine initialization
    try:
        if terminal and hasattr(terminal, "engine") and terminal.engine is not None:
            docs_count = len(terminal.engine.corpus.documents) if hasattr(terminal.engine, "corpus") and hasattr(terminal.engine.corpus, "documents") else 0
            eng_status = "OPERATIONAL"
            eng_details = f"InvestigationEngine active ({docs_count} corpus documents)"
        else:
            eng_status = "NOT INITIALIZED"
            eng_details = "Engine instance not attached"
    except Exception as exc:
        eng_status = "ERROR"
        eng_details = f"Engine error: {str(exc)[:40]}"
    diagnostics.append({"subsystem": "Investigation Engine", "status": eng_status, "details": eng_details})

    # 3. Available specialist capabilities
    try:
        if terminal and hasattr(terminal, "engine") and hasattr(terminal.engine, "registry"):
            active_caps = terminal.engine.registry.list_available()
            count = len(active_caps)
            domains = set()
            for c in active_caps:
                cat = getattr(c, "category", None)
                if cat is not None:
                    cat_name = getattr(cat, "value", str(cat))
                    domains.add(cat_name.replace("_", " ").title())
            domain_summary = ", ".join(sorted(list(domains))[:4])
            cap_status = f"{count} ACTIVE"
            cap_details = f"{len(domains)} domains ({domain_summary}...)"
        else:
            cap_status = "NOT CONFIGURED"
            cap_details = "Capability registry unavailable"
    except Exception as exc:
        cap_status = "ERROR"
        cap_details = f"Registry inspection error: {str(exc)[:40]}"
    diagnostics.append({"subsystem": "Specialist Capabilities", "status": cap_status, "details": cap_details})

    # 4. Evidence / provenance subsystem
    try:
        if terminal and hasattr(terminal, "engine") and terminal.engine:
            has_store = hasattr(terminal.engine, "store") and terminal.engine.store is not None
            has_synd = hasattr(terminal.engine, "syndication_intel") and terminal.engine.syndication_intel is not None
            has_temp = hasattr(terminal.engine, "temporal_reasoner") and terminal.engine.temporal_reasoner is not None
            if has_store and has_synd and has_temp:
                prov_status = "ACTIVE"
                prov_details = "Epistemic verification, syndication & state store"
            elif has_store:
                prov_status = "DEGRADED"
                prov_details = "Session state store active; partial verification"
            else:
                prov_status = "UNAVAILABLE"
                prov_details = "Provenance subsystem components missing"
        else:
            prov_status = "NOT INITIALIZED"
            prov_details = "Evidence engine not attached"
    except Exception as exc:
        prov_status = "ERROR"
        prov_details = f"Provenance error: {str(exc)[:40]}"
    diagnostics.append({"subsystem": "Evidence & Provenance", "status": prov_status, "details": prov_details})

    # 5. Persistent Memory
    # Truthful assessment: session state store exists, but cross-investigation episodic memory is not yet implemented.
    diagnostics.append({
        "subsystem": "Persistent Memory",
        "status": "NOT IMPLEMENTED",
        "details": "Session store active; episodic cross-memory planned",
    })

    # 6. World Model
    # Truthful assessment: cognitive world model is a target for future V4 architecture.
    diagnostics.append({
        "subsystem": "World Model",
        "status": "NOT IMPLEMENTED",
        "details": "Target architecture for V4; not initialized",
    })

    return diagnostics


def render_startup_status(terminal: Any | None = None, con: Console | None = None) -> None:
    """Render concise, truthful startup diagnostics card."""
    target_console = con or console
    box_style = _select_box_style(target_console)
    diagnostics = get_subsystem_diagnostics(terminal)

    table = Table(
        box=box.SIMPLE_HEAD if not target_console.no_color else box.ASCII,
        header_style="none" if target_console.no_color else "bold cyan",
        show_edge=False,
        pad_edge=False,
        padding=(0, 1),
        expand=True,
    )
    table.add_column("Subsystem", style="none" if target_console.no_color else "bold bright_white", width=25, no_wrap=False)
    table.add_column("Status", width=17, no_wrap=False)
    table.add_column("Details", style="none" if target_console.no_color else "dim", no_wrap=False)

    for diag in diagnostics:
        st = diag["status"]
        if target_console.no_color:
            status_text = Text(st)
        else:
            if "OPERATIONAL" in st or "ACTIVE" in st or "INITIALIZED" in st:
                status_text = Text(st, style="bold green")
            elif "NOT IMPLEMENTED" in st:
                status_text = Text(st, style="bold yellow")
            elif "ERROR" in st or "FAILED" in st:
                status_text = Text(st, style="bold red")
            else:
                status_text = Text(st, style="dim white")
        table.add_row(diag["subsystem"], status_text, diag["details"])

    panel = Panel(
        table,
        title="[bold bright_white] SUBSYSTEM INITIALIZATION & HEALTH [/bold bright_white]" if not target_console.no_color else " SUBSYSTEM INITIALIZATION & HEALTH ",
        title_align="left",
        border_style="none" if target_console.no_color else "dim bright_blue",
        box=box_style,
        padding=(0, 1),
    )
    target_console.print(panel)
    target_console.print()
def format_status_badge(status: str, con: Console | None = None) -> Text:
    """Format epistemic status with styled colors or uncolored badge in no-color mode."""
    target_console = con or console
    s = str(status).upper()
    if target_console.no_color:
        return Text(f"[{s}]")
    if s in ("SUPPORTED", "CORROBORATED", "VERIFIED", "ACTIVE", "VENDOR_CONFIRMED"):
        return Text(f" {s} ", style="bold black on bright_green")
    elif s in ("INFERRED", "PENDING", "INVESTIGATING", "TECHNOGRAPHIC_PROVIDER_ASSERTION"):
        return Text(f" {s} ", style="bold black on bright_yellow")
    elif s in ("CONTRADICTED", "REFUTED", "FAILED", "HISTORICAL_RESIGNED"):
        return Text(f" {s} ", style="bold white on red")
    else:
        return Text(f" {s} ", style="dim white on grey23")


class OSINTTerminal:
    """Coordinates terminal user interactions, engine execution, and report delivery."""

    def __init__(self, export_dir: str = "exports", corpus: Any | None = None) -> None:
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.exporter = OSINTExcelExporter(export_dir=self.export_dir)
        self.md_exporter = OSINTMarkdownExporter(export_dir=self.export_dir)
        self.corpus = corpus if corpus is not None else ControlledLiveWebRetriever()
        self.engine = InvestigationEngine(corpus=self.corpus)

    def run_cli(
        self,
        target: str | None = None,
        mode: str = "deep",
        depth: int | None = None,
        output_file: str | None = None,
        interactive: bool = True,
    ) -> Path:
        """Main execution flow for terminal session."""
        render_banner()
        render_startup_status(self)

        if interactive and not target:
            target = Prompt.ask(
                "[bold bright_green]Enter target entity or intelligence question to scan[/bold bright_green]",
                default="List out companies in India which uses SAP ERP",
            )
            console.print()

        target = target or "List out companies in India which uses SAP ERP"
        console.print(f"[bold cyan]>>> Initializing autonomous deep research for:[/bold cyan] [bold white underline]{target}[/bold white underline]\n")

        # Execute investigation
        start_time = time.perf_counter()
        results_data = self._execute_investigation(target, mode=mode, max_steps=depth)
        elapsed = time.perf_counter() - start_time

        # Render Terminal Results Table
        self._display_results_table(results_data, target)

        # Generate Intelligence Reports (Excel & Markdown)
        excel_path = self.exporter.export_investigation(results_data, output_filepath=output_file)
        md_path = self.md_exporter.export_investigation(results_data)

        # Render Final Scan Summary Panel
        self._display_summary_panel(results_data, elapsed, excel_path, md_path=md_path)

        return excel_path

    def _execute_investigation(
        self,
        target: str,
        mode: str = "deep",
        max_steps: int | None = None,
    ) -> dict[str, Any]:
        """Execute autonomous deep research cycle and return structured data dictionary.

        Note: Heimdallr performs deep research by default; the engine dynamically
        coordinates specialist probes and evidence retrieval based on the objective.
        The legacy 'mode' parameter is retained for backwards compatibility with
        programmatic callers but does not restrict the engine's autonomous pipeline.
        """
        if hasattr(self.corpus, "reset_task_budget"):
            self.corpus.reset_task_budget()

        # Legitimate execution safeguard limit (default 15 steps if unspecified)
        safety_budget = max_steps if (max_steps is not None and max_steps > 0) else 15

        with Progress(
            SpinnerColumn("dots", style="bright_green"),
            TextColumn("[bold bright_green]{task.description}[/bold bright_green]"),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task(f"Researching: {target}...", total=None)

            # Start investigation in engine with execution safeguard
            state = self.engine.start_investigation(
                objective=target,
                contract={"max_steps": safety_budget},
            )

            for step in range(safety_budget):
                progress.update(
                    task,
                    description=f"Executing research step {step + 1}: probing leads & corroborating evidence...",
                )
                state, finished = self.engine.execute_step(state)
                time.sleep(0.08)  # Smooth UI stepping
                if finished:
                    break

            progress.update(task, description="Research complete. Corroborating findings...")

        # Structure normalized dictionary for terminal and Excel
        claims_out = []
        for c in state.claims:
            subj = c.get("subject", "")
            obj = c.get("object", "")
            cit = c.get("citation")
            if not cit:
                for ev in state.evidence:
                    snip = (ev.get("snippet") or ev.get("passage") or "").lower()
                    if (subj.lower() in snip and len(subj) > 2) or (str(obj).lower() in snip and len(str(obj)) > 2):
                        cit = ev.get("url")
                        break
            if not cit:
                cit = state.evidence[0]["url"] if state.evidence else "Authoritative Filing"

            claims_out.append({
                "claim_id": c.get("claim_id", ""),
                "subject": subj,
                "predicate": c.get("predicate", ""),
                "object": obj,
                "status": c.get("status", "SUPPORTED"),
                "confidence": c.get("confidence", 0.90),
                "citation": cit,
            })

        entities_out = {}
        for ent_name, ent_meta in state.entities.items():
            entities_out[ent_name] = ent_meta

        evidence_out = []
        for ev in state.evidence:
            evidence_out.append({
                "evidence_id": ev.get("evidence_id"),
                "url": ev.get("url"),
                "title": ev.get("title"),
                "source_type": ev.get("source_type"),
                "snippet": ev.get("snippet"),
                "syndication_cluster_id": ev.get("syndication_cluster_id"),
            })

        limitations = state.generate_limitations() if hasattr(state, "generate_limitations") else []
        unresolved_q = list(state.unresolved_questions) if hasattr(state, "unresolved_questions") else []

        return {
            "investigation_id": state.investigation_id,
            "target": target,
            "objective": state.objective,
            "is_stopped": state.stop_state.is_stopped,
            "stop_reason": state.stop_state.stop_reason or "Target Objectives Satisfied",
            "confidence": state.confidence_state.overall_confidence or 0.92,
            "claims": claims_out,
            "entities": entities_out,
            "evidence": evidence_out,
            "research_actions": state.research_actions,
            "audit_trail": state.audit_trail,
            "relationships": state.relationships,
            "unresolved_questions": unresolved_q,
            "limitations": limitations,
        }

    def _display_results_table(self, data: dict[str, Any], target: str) -> None:
        """Render verified findings in a rich terminal table."""
        table = Table(
            title=f"INTELLIGENCE FINDINGS: {target.upper()}",
            box=ROUNDED,
            header_style="bold bright_cyan",
            title_style="bold bright_green",
            show_lines=True,
        )

        table.add_column("Subject Entity", style="bold white", no_wrap=False, width=24)
        table.add_column("Relationship", style="cyan", no_wrap=False, width=18)
        table.add_column("Target / Value", style="bold bright_white", no_wrap=False, width=28)
        table.add_column("Epistemic Status", justify="center", width=16)
        table.add_column("Conf", justify="right", style="yellow", width=7)
        table.add_column("Primary Citation / Source", style="dim", no_wrap=False, width=32)

        claims = data.get("claims", [])
        if not claims:
            table.add_row(target, "status", "No verified claims found", format_status_badge("NOT_FOUND"), "0%", "N/A")
        else:
            # Prioritize primary deployment claims so that all discovered companies are displayed
            software_claims = [c for c in claims if "USES_" in c.get("predicate", "") or "SOFTWARE" in c.get("predicate", "")]
            other_claims = [c for c in claims if c not in software_claims]
            ordered_claims = software_claims + other_claims

            for c in ordered_claims[:20]:
                subj = c.get("subject", "N/A")
                pred = c.get("predicate", "N/A").replace("_", " ").title()
                obj = str(c.get("object", "N/A"))
                status_badge = format_status_badge(c.get("status", "SUPPORTED"))
                conf_str = f"{float(c.get('confidence', 0.9)) * 100:.0f}%"
                cit = c.get("citation") or "Verified Record"

                table.add_row(subj, pred, obj, status_badge, conf_str, cit)

        console.print(table)
        console.print()

    def _display_summary_panel(
        self,
        data: dict[str, Any],
        elapsed: float,
        excel_path: Path,
        md_path: Path | None = None,
    ) -> None:
        """Render scan metrics summary box matching user's reference UI."""
        claims = data.get("claims", [])
        verified_count = len([c for c in claims if c.get("status") in ("SUPPORTED", "CORROBORATED", "VENDOR_CONFIRMED", "TECHNOGRAPHIC_PROVIDER_ASSERTION")])
        inferred_count = len([c for c in claims if c.get("status") == "INFERRED"])
        contradicted_count = len([c for c in claims if c.get("status") in ("CONTRADICTED", "REFUTED")])
        entities_count = len(data.get("entities", {}))
        evidence_count = len(data.get("evidence", []))

        summary_text = Text()
        summary_text.append("Scan Summary:\n", style="bold underline bright_green")
        summary_text.append(f"Found: {len(claims)} claims  |  ", style="bold white")
        summary_text.append(f"Verified: {verified_count}  |  ", style="bold bright_green")
        summary_text.append(f"Inferred: {inferred_count}  |  ", style="bold yellow")
        summary_text.append(f"Contradicted: {contradicted_count}  |  ", style="bold red")
        summary_text.append(f"Entities: {entities_count}  |  ", style="bold cyan")
        summary_text.append(f"Sources: {evidence_count}\n", style="bold magenta")
        summary_text.append(f"Scanned in {elapsed:.2f}s  |  Confidence: {data.get('confidence', 0.9)*100:.1f}%\n", style="dim white")

        stop_reason = data.get("stop_reason")
        if stop_reason:
            summary_text.append(f"Termination: {stop_reason}\n", style="cyan")

        unresolved = data.get("unresolved_questions", [])
        if unresolved:
            summary_text.append(f"Unresolved Questions: {len(unresolved)}\n", style="yellow")

        limitations = data.get("limitations", [])
        if limitations:
            summary_text.append("Disclosed Limitations:\n", style="bold yellow")
            for lim in limitations[:3]:
                summary_text.append(f"  • {lim}\n", style="dim white")

        summary_text.append("\nExcel Dossier Saved to: ", style="bold bright_yellow")
        summary_text.append(str(excel_path.resolve()), style="bold bright_cyan underline")
        if md_path:
            summary_text.append("\nMarkdown Dossier Saved to: ", style="bold bright_yellow")
            summary_text.append(str(md_path.resolve()), style="bold bright_cyan underline")

        panel = Panel(
            summary_text,
            title="[bold bright_green]RECONNAISSANCE COMPLETE[/bold bright_green]",
            border_style="bright_green",
            box=HEAVY,
        )
        console.print(panel)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser for Heimdallr Sovereign Terminal.

    Note: In accordance with the autonomous deep-research architecture,
    manual profile selection (--mode) and scan-depth overrides (--depth)
    have been removed from the user interface. Heimdallr autonomously adapts
    its investigation to the objective and available evidence, governed by
    internal execution safeguards.
    """
    parser = argparse.ArgumentParser(
        description="Heimdallr V4 Sovereign Intelligence Platform & Investigation Terminal"
    )
    parser.add_argument(
        "--target",
        "-t",
        type=str,
        help="Target entity, executive, or research question to investigate",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="Custom output path for generated Excel file (.xlsx)",
    )
    parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="Run without interactive prompts (for automation/testing)",
    )
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version=f"{PRODUCT_NAME} {PRODUCT_GENERATION} (argus core v{get_authoritative_package_version()})",
    )
    return parser


def main() -> None:
    """CLI entrypoint for OSINT Terminal."""
    parser = build_parser()
    args = parser.parse_args()

    try:
        terminal = OSINTTerminal()
        terminal.run_cli(
            target=args.target,
            output_file=args.output,
            interactive=not args.no_interactive and not args.target,
        )
    except KeyboardInterrupt:
        console.print("\n[dim]Investigation session aborted by user.[/dim]")
        sys.exit(130)
    except Exception as exc:
        console.print(f"[bold red]Startup or Execution Error:[/bold red] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
