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

from argus.evals.run_scorecard import record_run, score_run
from argus.intake.brief import ResearchBrief
from argus.export import OSINTExcelExporter, OSINTMarkdownExporter
from argus.export.narrative import NO_SOURCE_RECORDED, format_confidence
from argus.investigation.benchmark.corpus import INVESTIGATION_CORPUS_REGISTRY
from argus.investigation.claim_verification import is_gate_rejected, is_verified
from argus.investigation.live_web.controller import ControlledLiveWebRetriever
from argus.investigation.live_web.models import ControlledRetrievalLimits
from argus.investigation.live_web.run_recorder import RecordingCorpus, ReplayCorpus, run_folder_name
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


# One research action per step; a deep run reads many pages, so it needs more than V3's 15.
DEEP_RUN_STEPS = 60


class OSINTTerminal:
    """Coordinates terminal user interactions, engine execution, and report delivery."""

    def __init__(self, export_dir: str = "exports", corpus: Any | None = None, record_runs: bool | None = None) -> None:
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.exporter = OSINTExcelExporter(export_dir=self.export_dir)
        self.md_exporter = OSINTMarkdownExporter(export_dir=self.export_dir)
        # Full research run: every free search source and a budget sized for reading pages.
        self.corpus = corpus if corpus is not None else ControlledLiveWebRetriever(limits=ControlledRetrievalLimits.deep())
        self.engine = InvestigationEngine(corpus=self.corpus, simulated_registries=False)
        if self.engine.llm_reader is not None and isinstance(getattr(self.corpus, "limits", None), ControlledRetrievalLimits):
            # Model reading takes time on a local machine; the retrieval clock should not end the run early.
            self.corpus.limits.max_duration_seconds = max(self.corpus.limits.max_duration_seconds, 3600.0)
        # Live runs are recorded (exports/runs/<run>/) so they can be replayed offline with --replay.
        self.record_runs = isinstance(self.corpus, ControlledLiveWebRetriever) if record_runs is None else record_runs
        self.run_dir: Path | None = None

    def run_cli(
        self,
        target: str | None = None,
        brief: "ResearchBrief | None" = None,
        mode: str = "deep",
        depth: int | None = None,
        output_file: str | None = None,
        interactive: bool = True,
    ) -> Path:
        """Main execution flow for terminal session."""
        render_banner()
        render_startup_status(self)

        if brief is not None:
            target = brief.to_objective()

        while interactive and not (target or "").strip():
            target = Prompt.ask(
                "[bold bright_green]Enter target entity or intelligence question to scan[/bold bright_green]",
            )
            console.print()

        if not (target or "").strip():
            raise ValueError("No research objective given; pass --target or run interactively.")
        console.print(f"[bold cyan]>>> Initializing autonomous deep research for:[/bold cyan] [bold white underline]{target}[/bold white underline]\n")

        # Execute investigation
        start_time = time.perf_counter()
        results_data = self._execute_investigation(target, mode=mode, max_steps=depth, brief=brief)
        elapsed = time.perf_counter() - start_time

        # Render Terminal Results Table
        self._display_results_table(results_data, target)

        # Generate Intelligence Reports (Excel & Markdown)
        excel_path = self.exporter.export_investigation(results_data, output_filepath=output_file)
        md_path = self.md_exporter.export_investigation(results_data)

        # Record this question's numbers (exports/evals/runs.csv), so runs can be compared later.
        scorecard_path = record_run(results_data, seconds=elapsed, export_dir=self.export_dir)

        # Render Final Scan Summary Panel
        self._display_summary_panel(results_data, elapsed, excel_path, md_path=md_path, scorecard=scorecard_path)

        return excel_path

    @staticmethod
    def _answers_so_far(state: Any, contract: dict[str, Any]) -> int:
        """How many answers would reach the sheet right now, counted the way the sheet counts them."""
        from argus.export.answer_rows import build_answer_rows

        claims = [c for c in state.claims if not is_gate_rejected(c)]
        _, rows = build_answer_rows({
            "objective": state.objective, "claims": claims, "evidence": state.evidence,
            "enumeration_objective": state.objective_contract.get("enumeration_objective"),
            "brief": contract.get("brief"),
        })
        return len(rows)

    def _execute_investigation(
        self,
        target: str,
        mode: str = "deep",
        max_steps: int | None = None,
        brief: "ResearchBrief | None" = None,
    ) -> dict[str, Any]:
        """Execute autonomous deep research cycle and return structured data dictionary.

        Note: Heimdallr performs deep research by default; the engine dynamically
        coordinates specialist probes and evidence retrieval based on the objective.
        The legacy 'mode' parameter is retained for backwards compatibility with
        programmatic callers but does not restrict the engine's autonomous pipeline.
        """
        if hasattr(self.corpus, "reset_task_budget"):
            self.corpus.reset_task_budget()
        recorder = None
        if self.record_runs:
            self.run_dir = self.export_dir / "runs" / run_folder_name(target)
            recorder = RecordingCorpus(self.corpus, self.run_dir, objective=target)
            self.engine.corpus = recorder

        # Execution safeguard: at most DEEP_RUN_STEPS research steps unless a caller sets fewer.
        # A filled-in form sets its own budget through the contract.
        contract = brief.to_contract() if brief is not None else {}
        safety_budget = max_steps if (max_steps is not None and max_steps > 0) else int(contract.get("max_steps") or DEEP_RUN_STEPS)
        contract["max_steps"] = safety_budget

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
                contract=contract,
                as_of_date=(brief.as_of or None) if brief is not None else None,
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
                # The form may ask for a number of answers; stop once that many have passed the
                # evidence check, rather than spending the rest of the budget.
                wanted = int(contract.get("target_answer_count") or 0)
                if wanted and self._answers_so_far(state, contract) >= wanted:
                    progress.update(task, description=f"Found the {wanted} answers you asked for.")
                    break

            progress.update(task, description="Research complete. Corroborating findings...")

        # Structure normalized dictionary for terminal and Excel
        # Citations come only from the claim's own recorded provenance. A claim
        # without provenance keeps citation=None rather than borrowing another
        # evidence item's URL; missing status/confidence stay explicitly unknown.
        evidence_url_by_id = {ev.get("evidence_id"): ev.get("url") for ev in state.evidence if ev.get("evidence_id")}
        claims_out = []
        for c in state.claims:
            cit = c.get("citation") or c.get("source_url") or evidence_url_by_id.get(c.get("evidence_id")) or None

            claims_out.append({
                "claim_id": c.get("claim_id", ""),
                "subject": c.get("subject", ""),
                "predicate": c.get("predicate", ""),
                "object": c.get("object", ""),
                "status": c.get("status") or "UNVERIFIED",
                "confidence": c.get("confidence"),
                "citation": cit,
                "evidence_id": c.get("evidence_id"),
                "source_passage": c.get("source_passage"),
                "verification": c.get("verification"),
                "source_class": c.get("source_class"),
            })

        # Candidates the evidence gate turned down are not findings; they are kept apart
        # (Excel "Rejected Candidates" sheet, Markdown appendix) so reports never present them as results.
        rejected_out = [c for c in claims_out if is_gate_rejected(c)]
        claims_out = [c for c in claims_out if not is_gate_rejected(c)]

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

        result = {
            "investigation_id": state.investigation_id,
            "target": target,
            "objective": state.objective,
            "is_stopped": state.stop_state.is_stopped,
            "stop_reason": state.stop_state.stop_reason or "UNKNOWN",
            "enumeration_objective": state.objective_contract.get("enumeration_objective"),
            "confidence": state.confidence_state.overall_confidence,
            "claims": claims_out,
            "rejected_claims": rejected_out,
            "entities": entities_out,
            "evidence": evidence_out,
            "research_actions": state.research_actions,
            "audit_trail": state.audit_trail,
            "relationships": state.relationships,
            "unresolved_questions": unresolved_q,
            "limitations": limitations,
            "decision_engine": "Laya" if (hasattr(self.engine, "system1") and self.engine.system1() is not None) else None,
            "decisions": _decision_summary(),
            "brief": brief.as_dict() if brief is not None else None,
            "page_reader": (f"{reader.label} ({reader.pages_read} pages read, {reader.failures} failures)" if (reader := getattr(self.engine, "llm_reader", None)) else None),
        }
        if recorder is not None:
            self.engine.corpus = self.corpus
            recorder.save_result({k: result[k] for k in ("objective", "stop_reason", "enumeration_objective", "claims", "rejected_claims", "limitations")})
            result["run_dir"] = str(self.run_dir)
        return result

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

        # Only findings the evidence gate passed, plus source-reported contradictions, are results.
        claims = [c for c in data.get("claims", []) if is_verified(c) or c.get("status") in ("CONTRADICTED", "REFUTED")]
        if not claims:
            table.add_row(target, "status", "No verified findings", format_status_badge("NOT_FOUND"), "0%", "N/A")
        else:
            # Prioritize primary deployment claims so that all discovered companies are displayed
            software_claims = [c for c in claims if "USES_" in c.get("predicate", "") or "SOFTWARE" in c.get("predicate", "")]
            other_claims = [c for c in claims if c not in software_claims]
            ordered_claims = software_claims + other_claims

            for c in ordered_claims[:20]:
                subj = c.get("subject", "N/A")
                pred = c.get("predicate", "N/A").replace("_", " ").title()
                obj = str(c.get("object", "N/A"))
                status_badge = format_status_badge(c.get("status") or "UNVERIFIED")
                conf_str = format_confidence(c.get("confidence"), decimals=0)
                cit = c.get("citation") or NO_SOURCE_RECORDED

                table.add_row(subj, pred, obj, status_badge, conf_str, cit)
            if len(ordered_claims) > 20:
                table.caption = f"{len(ordered_claims) - 20} more verified findings in the Excel and Markdown reports"

        console.print(table)
        console.print()

    def _display_summary_panel(
        self,
        data: dict[str, Any],
        elapsed: float,
        excel_path: Path,
        md_path: Path | None = None,
        scorecard: Path | None = None,
    ) -> None:
        """Render scan metrics summary box matching user's reference UI."""
        claims = data.get("claims", [])
        # Provider assertions and claims the verification gate did not pass are not "verified".
        verified_count = len([c for c in claims if is_verified(c)])
        inferred_count = len([c for c in claims if c.get("status") == "INFERRED"])
        contradicted_count = len([c for c in claims if c.get("status") in ("CONTRADICTED", "REFUTED")])
        entities_count = len(data.get("entities", {}))
        evidence_count = len(data.get("evidence", []))

        summary_text = Text()
        summary_text.append("Scan Summary:\n", style="bold underline bright_green")
        rejected = data.get("rejected_claims", [])
        summary_text.append(f"Candidates: {len(claims) + len(rejected)} (rejected by evidence check: {len(rejected)})  |  ", style="bold white")
        summary_text.append(f"Verified: {verified_count}  |  ", style="bold bright_green")
        summary_text.append(f"Inferred: {inferred_count}  |  ", style="bold yellow")
        summary_text.append(f"Contradicted: {contradicted_count}  |  ", style="bold red")
        summary_text.append(f"Entities: {entities_count}  |  ", style="bold cyan")
        summary_text.append(f"Sources: {evidence_count}\n", style="bold magenta")
        summary_text.append(f"Scanned in {elapsed:.2f}s  |  Confidence: {format_confidence(data.get('confidence'))}\n", style="dim white")

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
        summary_text.append(
            f"\nPage reader: {data['page_reader']}" if data.get("page_reader") else "\nPage reader: off (set HEIMDALLR_LLM, e.g. openrouter:<free model>,ollama:qwen2.5:7b)",
            style="dim white",
        )
        summary_text.append(
            "\nDecision engine: Laya (ranks pages to fetch, filters pages before the model reads)" if data.get("decision_engine") else "\nDecision engine: off (laya not installed or HEIMDALLR_LAYA=0)",
            style="dim white",
        )
        dec = data.get("decisions") or {}
        if dec.get("decisions"):
            summary_text.append(
                f"\nDecisions: {dec['decisions']} ({dec['by_laya']} by Laya, {dec['by_rule']} by fallback rules; "
                f"Laya differed from the rules {dec['laya_disagreed_with_rule']} times)",
                style="dim white",
            )
        if scorecard is not None:
            card = score_run(data, seconds=elapsed).row
            summary_text.append(
                f"\nScorecard: {card['answers']} answers ({card['answers_strong']} strong, {card['answers_weak']} weak), "
                f"{card['pages_read']} pages from {card['sites_read']} sites, {card['claims_rejected']} candidates refused, "
                f"{card['seconds']}s",
                style="dim white",
            )
            summary_text.append("\nRun Numbers Appended to: ", style="bold bright_yellow")
            summary_text.append(str(Path(scorecard).resolve()), style="bold bright_cyan underline")
            summary_text.append("  (python -m argus.evals.run_scorecard --compare)", style="dim white")
        if data.get("run_dir"):
            summary_text.append("\nRun Recording Saved to: ", style="bold bright_yellow")
            summary_text.append(str(Path(data["run_dir"]).resolve()), style="bold bright_cyan underline")

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
        "--form",
        action="store_true",
        help="Fill in a research brief at the terminal instead of typing one question",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="Serve the research brief form in a browser (http://127.0.0.1:8765 by default)",
    )
    parser.add_argument("--port", type=int, default=8765, help="Port for --web (default 8765)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host for --web (default 127.0.0.1, this machine only)")
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Permit --web to listen beyond this machine. Only on a network you trust: the form starts research runs.",
    )
    parser.add_argument(
        "--brief",
        type=str,
        metavar="BRIEF_JSON",
        help="Run a brief saved earlier (exports/briefs/<file>.json)",
    )
    parser.add_argument(
        "--replay",
        type=str,
        metavar="RUN_DIR",
        help="Re-run a recorded run (exports/runs/<run>) offline, answering every web call from the recording",
    )
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version=f"{PRODUCT_NAME} {PRODUCT_GENERATION} (argus core v{get_authoritative_package_version()})",
    )
    return parser


def _decision_summary() -> dict[str, int]:
    try:
        from argus.brain.decisions import get_decisions

        return get_decisions().summary()
    except Exception:
        return {}


def serve_brief_form(host: str = "127.0.0.1", port: int = 8765, allow_remote: bool = False) -> None:
    """Serve the browser form; each submitted brief runs here and writes the usual reports."""
    from argus.intake.webform import serve

    if host not in ("127.0.0.1", "localhost", "::1") and not allow_remote:
        raise ValueError(
            f"--host {host} would let other machines start research runs; pass --allow-remote if that is what you want"
        )

    def runner(brief: ResearchBrief) -> list[str]:
        terminal = OSINTTerminal()
        excel_path = terminal.run_cli(brief=brief, interactive=False)
        written = [str(Path(excel_path).resolve())]
        if terminal.run_dir:
            written.append(str(Path(terminal.run_dir).resolve()))
        return written

    serve(runner, host=host, port=port, brief_dir=Path("exports") / "briefs")


def main() -> None:
    """CLI entrypoint for OSINT Terminal."""
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.web:
            serve_brief_form(host=args.host, port=args.port, allow_remote=args.allow_remote)
            return

        brief = None
        if args.replay:
            replay = ReplayCorpus(args.replay)
            terminal = OSINTTerminal(corpus=replay, record_runs=False)
            target = args.target or replay.objective
        else:
            terminal = OSINTTerminal()
            target = args.target
            if args.brief:
                brief = ResearchBrief.load(args.brief)
            elif args.form:
                from argus.intake.terminal_form import fill_in_brief

                brief = fill_in_brief()
                saved = brief.save(terminal.export_dir / "briefs")
                console.print(f"[dim]Brief saved to {saved} — re-run it with --brief {saved}[/dim]\n")
        terminal.run_cli(
            target=target,
            brief=brief,
            output_file=args.output,
            interactive=not args.no_interactive and not target and brief is None,
        )
    except KeyboardInterrupt:
        console.print("\n[dim]Investigation session aborted by user.[/dim]")
        sys.exit(130)
    except Exception as exc:
        console.print(f"[bold red]Startup or Execution Error:[/bold red] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
