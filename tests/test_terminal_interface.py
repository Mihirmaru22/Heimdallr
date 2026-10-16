"""Focused test suite for Heimdallr V4 Terminal Interface.

Verifies:
1. Banner rendering with V4 identity, subtitle, and 3 pillars.
2. Product generation (V4) and package version (v0.1.0) consistency.
3. Color-disabled / no-color output handling and ASCII fallback.
4. Startup diagnostics accuracy and truthfulness (verifying memory and world model are NOT claimed ready).
5. Missing or invalid configuration handling.
6. Existing investigation input compatibility.
7. Startup error and exit handling.
"""

from __future__ import annotations

import argparse
import io
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from rich.console import Console
from argus.terminal import (
    BANNER_ART,
    PRODUCT_GENERATION,
    PRODUCT_NAME,
    PRODUCT_SUBTITLE,
    PILLARS,
    OSINTTerminal,
    format_status_badge,
    get_authoritative_package_version,
    get_banner_text,
    get_subsystem_diagnostics,
    render_banner,
    render_startup_status,
    build_parser,
    main,
)
import argus


class TestBannerRendering:
    """Tests for Phase 2: Terminal Identity & Banner Rendering."""

    def test_banner_contains_v4_identity(self):
        """Banner must contain HEIMDALLR V4 identity and subtitle."""
        banner = get_banner_text()
        assert "HEIMDALLR V4" in banner
        assert "SOVEREIGN INTELLIGENCE PLATFORM" in banner

    def test_banner_contains_all_three_pillars(self):
        """Banner must display all three architectural pillars."""
        banner = get_banner_text()
        for pillar in PILLARS:
            assert pillar in banner, f"Missing pillar: {pillar}"

    def test_render_banner_console_output(self):
        """render_banner prints the card to the target console."""
        sio = io.StringIO()
        con = Console(file=sio, width=100)
        render_banner(con=con)
        output = sio.getvalue()
        assert "HEIMDALLR" in output
        assert "V4" in output
        assert "SOVEREIGN INTELLIGENCE PLATFORM" in output
        assert "Evidence-Backed Research" in output
        assert "Multi-Specialist Investigation" in output
        assert "Persistent Intelligence Architecture" in output

    def test_backwards_compatibility_banner_art(self):
        """BANNER_ART constant is exported and non-empty for external callers."""
        assert isinstance(BANNER_ART, str)
        assert len(BANNER_ART) > 0
        assert "HEIMDALLR V4" in BANNER_ART


class TestVersionConsistency:
    """Tests for Phase 3: Version Consistency & Packaging."""

    def test_authoritative_package_version_matches_argus(self):
        """Package version must match argus.__version__ without conflicting hardcoding."""
        pkg_ver = get_authoritative_package_version()
        assert pkg_ver == argus.__version__
        assert pkg_ver == "0.1.0"

    def test_product_generation_distinct_from_package_version(self):
        """Product generation (V4) is separated from core package version (0.1.0)."""
        assert PRODUCT_GENERATION == "V4"
        pkg_ver = get_authoritative_package_version()
        banner = get_banner_text()
        assert f"Platform Generation : V4" in banner
        assert f"Core Package        : argus v{pkg_ver}" in banner

    def test_no_legacy_hardcoded_versions_in_banner(self):
        """Legacy 3.2.0 or 3.5 strings must not appear in the new banner."""
        banner = get_banner_text()
        assert "3.2.0" not in banner
        assert "V3.5" not in banner
        assert "Version 3.2" not in banner


class TestColorDisabledAndTerminalCompatibility:
    """Tests for Phase 6: Terminal Compatibility & No-Color Output."""

    def test_render_banner_no_color(self):
        """render_banner produces clean output when no_color is True without escape sequences."""
        sio = io.StringIO()
        con = Console(file=sio, width=100, no_color=True)
        render_banner(con=con)
        output = sio.getvalue()
        # In no_color mode, ANSI escape codes (\x1b[) should not be emitted
        assert "\x1b[" not in output
        assert "HEIMDALLR V4" in output
        assert "SOVEREIGN INTELLIGENCE PLATFORM" in output

    def test_render_startup_status_no_color(self):
        """render_startup_status produces clean output when no_color is True."""
        sio = io.StringIO()
        con = Console(file=sio, width=100, no_color=True)
        render_startup_status(terminal=None, con=con)
        output = sio.getvalue()
        assert "\x1b[" not in output
        assert "Configuration" in output
        assert "SUBSYSTEM INITIALIZATION & HEALTH" in output

    def test_format_status_badge_no_color(self):
        """format_status_badge produces plain badge in no_color mode."""
        con = Console(no_color=True)
        badge = format_status_badge("SUPPORTED", con=con)
        assert str(badge) == "[SUPPORTED]"

    def test_format_status_badge_colored(self):
        """format_status_badge produces styled text in color mode."""
        con = Console(no_color=False)
        badge = format_status_badge("SUPPORTED", con=con)
        assert "SUPPORTED" in str(badge)


class TestStartupStatusAccuracy:
    """Tests for Phase 4: Truthful Subsystem Diagnostics."""

    def test_subsystem_diagnostics_structure(self):
        """Diagnostics must return exactly 6 structured subsystem entries."""
        diags = get_subsystem_diagnostics(terminal=None)
        assert len(diags) == 6
        subsystems = [d["subsystem"] for d in diags]
        assert "Configuration" in subsystems
        assert "Investigation Engine" in subsystems
        assert "Specialist Capabilities" in subsystems
        assert "Evidence & Provenance" in subsystems
        assert "Persistent Memory" in subsystems
        assert "World Model" in subsystems

    def test_truthful_memory_and_world_model_status(self):
        """Persistent memory and world model must be truthfully marked NOT IMPLEMENTED."""
        diags = get_subsystem_diagnostics(terminal=None)
        diag_map = {d["subsystem"]: d for d in diags}

        mem = diag_map["Persistent Memory"]
        assert mem["status"] == "NOT IMPLEMENTED"
        assert "planned" in mem["details"].lower() or "not" in mem["details"].lower()

        wm = diag_map["World Model"]
        assert wm["status"] == "NOT IMPLEMENTED"
        assert "V4" in wm["details"] or "not initialized" in wm["details"].lower()

    def test_no_secrets_or_credentials_leaked(self):
        """Diagnostic output must never leak API keys, auth tokens, or absolute home paths."""
        diags = get_subsystem_diagnostics(terminal=None)
        for d in diags:
            details = d["details"]
            assert "api_key" not in details.lower()
            assert "secret" not in details.lower()
            assert "bearer" not in details.lower()
            assert "/home/" not in details

    def test_diagnostics_with_real_terminal(self):
        """When terminal is initialized, real subsystems report operational status."""
        terminal = OSINTTerminal()
        diags = get_subsystem_diagnostics(terminal)
        diag_map = {d["subsystem"]: d for d in diags}

        assert diag_map["Configuration"]["status"] == "INITIALIZED"
        assert diag_map["Investigation Engine"]["status"] == "OPERATIONAL"
        assert "ACTIVE" in diag_map["Specialist Capabilities"]["status"]
        assert diag_map["Evidence & Provenance"]["status"] == "ACTIVE"
        assert diag_map["Persistent Memory"]["status"] == "NOT IMPLEMENTED"
        assert diag_map["World Model"]["status"] == "NOT IMPLEMENTED"


class TestMissingOrInvalidConfiguration:
    """Tests for Phase 4: Missing or Invalid Configuration Handling."""

    def test_diagnostics_with_none_terminal(self):
        """Subsystem diagnostics must not raise when terminal is None."""
        diags = get_subsystem_diagnostics(terminal=None)
        diag_map = {d["subsystem"]: d for d in diags}
        assert diag_map["Investigation Engine"]["status"] == "NOT INITIALIZED"
        assert diag_map["Specialist Capabilities"]["status"] == "NOT CONFIGURED"

    def test_diagnostics_with_failing_registry(self):
        """Handles exceptions in registry inspection gracefully."""
        mock_terminal = MagicMock()
        mock_terminal.engine.registry.list_available.side_effect = RuntimeError("Registry DB locked")
        diags = get_subsystem_diagnostics(mock_terminal)
        diag_map = {d["subsystem"]: d for d in diags}
        assert diag_map["Specialist Capabilities"]["status"] == "ERROR"
        assert "Registry DB locked" in diag_map["Specialist Capabilities"]["details"]


class TestInvestigationInputCompatibility:
    """Tests for Phase 5: Existing Investigation Input Compatibility."""

    def test_cli_argument_parser_flags(self):
        """Production parser accepts target, output, no-interactive, and version, rejecting removed options."""
        parser = build_parser()
        args = parser.parse_args([
            "--target", "List Indian companies that use SAP ERP",
            "--output", "exports/custom_report.xlsx",
            "--no-interactive",
        ])
        assert args.target == "List Indian companies that use SAP ERP"
        assert args.output == "exports/custom_report.xlsx"
        assert args.no_interactive is True

        # Depth and mode overrides are rejected from the CLI parser
        with pytest.raises(SystemExit):
            parser.parse_args(["--depth", "4"])
        with pytest.raises(SystemExit):
            parser.parse_args(["--mode", "fast"])

    def test_run_cli_and_main_default_behavior(self):
        """run_cli defaults to deep research with automatic adaptive depth (depth=None)."""
        import inspect
        sig = inspect.signature(OSINTTerminal.run_cli)
        assert sig.parameters["mode"].default == "deep"
        assert sig.parameters["depth"].default is None

    def test_execution_ceiling_preserved_when_depth_unspecified(self):
        """When depth is None, internal execution safeguard ceiling of 15 steps is enforced."""
        terminal = OSINTTerminal()
        with patch.object(terminal.engine, "start_investigation", wraps=terminal.engine.start_investigation) as mock_start:
            with patch.object(terminal.engine, "execute_step") as mock_step:
                mock_state = MagicMock()
                mock_state.claims = []
                mock_state.entities = {}
                mock_state.evidence = []
                mock_state.research_actions = []
                mock_state.audit_trail = []
                mock_state.relationships = []
                mock_state.investigation_id = "inv_test"
                mock_state.objective = "Test Target"
                mock_state.stop_state.is_stopped = True
                mock_state.stop_state.stop_reason = "Done"
                mock_state.confidence_state.overall_confidence = 0.95
                mock_step.return_value = (mock_state, True)
                mock_start.return_value = mock_state

                terminal._execute_investigation("Test Target", max_steps=None)

                mock_start.assert_called_once()
                contract = mock_start.call_args[1].get("contract") or mock_start.call_args[0][1]
                assert contract["max_steps"] == 15

    def test_live_retrieval_initialized_by_default(self):
        """ControlledLiveWebRetriever is wired to production OSINTTerminal by default."""
        from argus.investigation.live_web.controller import ControlledLiveWebRetriever
        terminal = OSINTTerminal()
        assert isinstance(terminal.corpus, ControlledLiveWebRetriever)
        assert terminal.engine.corpus is terminal.corpus

    def test_non_interactive_investigation_execution(self, tmp_path):
        """OSINTTerminal.run_cli runs investigation and returns output path for benchmark targets."""
        terminal = OSINTTerminal(export_dir=str(tmp_path))
        target = "Apex Technologies Group"
        out_file = str(tmp_path / "test_out.xlsx")
        excel_path = terminal.run_cli(
            target=target,
            mode="chain",
            depth=1,
            output_file=out_file,
            interactive=False,
        )
        assert Path(excel_path).exists()
        assert Path(excel_path).stat().st_size > 0

    def test_legitimate_research_reaches_execution_pipeline(self):
        """Legitimate research requests must pass directly to the research planner and investigation pipeline,

        without being intercepted or diverted to canned enterprise recon.
        """
        terminal = OSINTTerminal()
        target = "Stanford Raft consensus protocol research by Diego Ongaro"
        data = terminal._execute_investigation(target=target, mode="chain", max_steps=2)

        # 1. Must use the real InvestigationEngine ID, not the removed catch's 'inv_live_'
        assert data["investigation_id"].startswith("inv_")
        assert not data["investigation_id"].startswith("inv_live_")

        # 2. Must reach planner and generate real ResearchActions
        assert len(data["research_actions"]) >= 1
        first_action = data["research_actions"][0]
        assert "action_type" in first_action
        assert first_action["status"] == "EXECUTED"

        # 3. Must have valid objective contract and stop state
        assert data["objective"] == target
        assert "is_stopped" in data

    def test_general_purpose_query_not_diverted_to_canned_recon(self, tmp_path):
        """Arbitrary real-world queries execute through the full research pipeline to Excel export."""
        terminal = OSINTTerminal(export_dir=str(tmp_path))
        target = "Investigate supply chain logistics for renewable energy batteries"
        out_file = str(tmp_path / "battery_research.xlsx")
        excel_path = terminal.run_cli(
            target=target,
            mode="fast",
            depth=1,
            output_file=out_file,
            interactive=False,
        )
        assert Path(excel_path).exists()
        assert Path(excel_path).stat().st_size > 0

    def test_interactive_cli_no_profile_or_depth_prompts(self, tmp_path):
        """Interactive CLI prompts only for target objective; no profile or depth prompts."""
        terminal = OSINTTerminal(export_dir=str(tmp_path))
        with patch("argus.terminal.Prompt.ask", return_value="Test Company Inc") as mock_ask:
            with patch.object(terminal, "_execute_investigation", return_value={
                "claims": [], "entities": {}, "evidence": [], "confidence": 0.9, "is_stopped": True
            }) as mock_exec:
                terminal.run_cli(target=None, interactive=True)
                assert mock_ask.call_count == 1
                prompt_arg = mock_ask.call_args[0][0]
                assert "target entity" in prompt_arg.lower()
                assert mock_exec.called


class TestStartupFailureHandling:
    """Tests for Phase 6: Exit & Failure Handling."""

    def test_keyboard_interrupt_exits_with_130(self):
        """KeyboardInterrupt in main() exits cleanly with returncode 130."""
        with patch("argus.terminal.OSINTTerminal", side_effect=KeyboardInterrupt):
            with patch("sys.argv", ["terminal.py", "--no-interactive"]):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 130

    def test_unexpected_exception_exits_with_1(self):
        """Unexpected exception in main() exits cleanly with returncode 1."""
        with patch("argus.terminal.OSINTTerminal", side_effect=ValueError("Storage unavailable")):
            with patch("sys.argv", ["terminal.py", "--no-interactive"]):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 1
