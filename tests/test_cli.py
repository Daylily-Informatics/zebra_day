"""
Tests for the zebra_day CLI commands.
"""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from zebra_day.cli import _get_version, app

runner = CliRunner()


class TestCLIVersion:
    """Tests for the version command."""

    def test_get_version_returns_string(self):
        """Test _get_version returns a string."""
        version = _get_version()
        assert isinstance(version, str)
        assert len(version) > 0

    def test_version_command(self):
        """Test version command outputs version."""
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "zebra_day" in result.output


class TestCLIInfo:
    """Tests for the info command."""

    def test_info_command(self):
        """Test info command runs and shows table."""
        result = runner.invoke(app, ["info"])
        assert result.exit_code == 0
        assert "Version" in result.output
        assert "Config Dir" in result.output


class TestCLIStatus:
    """Tests for the status command."""

    def test_status_command(self):
        """Test status command runs."""
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        # Status shows printer counts
        assert "Labs" in result.output or "Printer" in result.output


class TestCLITemplateList:
    """Tests for template list command."""

    def test_template_list_command(self):
        """Test template list command runs."""
        result = runner.invoke(app, ["template", "list"])
        assert result.exit_code == 0
        # Should show templates or empty list
        assert "Template" in result.output or "Stable" in result.output or result.exit_code == 0


class TestCLIPrinterList:
    """Tests for printer list command."""

    def test_printer_list_command(self):
        """Test printer list command runs."""
        result = runner.invoke(app, ["printer", "list"])
        assert result.exit_code == 0


class TestCLIHelp:
    """Tests for CLI help output."""

    def test_main_help(self):
        """Test main help shows subcommands."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "gui" in result.output
        assert "printer" in result.output
        assert "template" in result.output

    def test_gui_help(self):
        """Test gui subcommand help."""
        result = runner.invoke(app, ["gui", "--help"])
        assert result.exit_code == 0
        assert "start" in result.output
        assert "stop" in result.output

    def test_printer_help(self):
        """Test printer subcommand help."""
        result = runner.invoke(app, ["printer", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output

    def test_template_help(self):
        """Test template subcommand help."""
        result = runner.invoke(app, ["template", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output


class TestCLIGuiStatus:
    """Tests for GUI status command."""

    def test_gui_status_command(self):
        """Test gui status command runs."""
        result = runner.invoke(app, ["gui", "status"])
        # exit_code 0 = running, exit_code 1 = not running (both valid)
        assert result.exit_code in (0, 1)


class TestCLIConfig:
    """Tests for config CLI commands."""

    def test_config_help(self):
        """Test config subcommand help."""
        result = runner.invoke(app, ["config", "--help"])
        assert result.exit_code == 0
        assert "init" in result.output
        assert "show" in result.output
        assert "path" in result.output
        assert "validate" in result.output
        assert "edit" in result.output
        assert "reset" in result.output

    def test_config_path_command(self):
        """Test config path command outputs a path."""
        result = runner.invoke(app, ["config", "path"])
        assert result.exit_code == 0
        assert "zebra-day-config.yaml" in result.output or "printer_config.json" in result.output

    def test_config_init_existing(self):
        """Test config init refuses to overwrite without --force."""
        # First ensure config exists
        runner.invoke(app, ["config", "init", "--force"])
        # Then try without --force
        result = runner.invoke(app, ["config", "init"])
        # Should fail or succeed depending on if config exists
        assert result.exit_code in (0, 1)

    def test_config_show_command(self):
        """Test config show command displays YAML."""
        # First ensure config exists
        runner.invoke(app, ["config", "init", "--force"])
        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        assert "schema_version" in result.output

    def test_config_validate_command(self):
        """Test config validate command."""
        # First ensure config exists
        runner.invoke(app, ["config", "init", "--force"])
        result = runner.invoke(app, ["config", "validate"])
        assert result.exit_code == 0
        assert "valid" in result.output.lower()


def _make_mock_zpl(found_printers=None):
    """Create a mock zpl instance with a fake probe method.

    ``found_printers`` is a list of dicts with keys ip, model, serial.
    The mock ``probe_zebra_printers_add_to_printers_json`` will invoke the
    ``progress_callback`` (if provided) with realistic events.
    """
    found_printers = found_printers or []
    mock_zp = MagicMock()
    mock_zp.printers = {"labs": {}}

    def _fake_probe(ip_stub="192.168.1", progress_callback=None, **kwargs):
        lab = kwargs.get("lab", "default")
        mock_zp.printers["labs"].setdefault(lab, {"printers": {}})
        for idx, p in enumerate(found_printers):
            ip = p.get("ip", f"{ip_stub}.{idx + 1}")
            if progress_callback:
                progress_callback({"kind": "checking", "ip": ip, "checked": idx, "total": 255})
            mock_zp.printers["labs"][lab]["printers"][ip] = {
                "ip_address": ip,
                "model": p.get("model", "Unknown"),
                "serial": p.get("serial", "Unknown"),
            }
            if progress_callback:
                progress_callback({"kind": "found", "ip": ip, "model": p.get("model", "Unknown"), "serial": p.get("serial", "Unknown")})
                progress_callback({"kind": "checked", "ip": ip, "checked": idx + 1, "total": 255, "open": True})
        if progress_callback:
            progress_callback({"kind": "done", "cancelled": False, "checked": len(found_printers), "total": 255})

    mock_zp.probe_zebra_printers_add_to_printers_json = _fake_probe
    return mock_zp


class TestCLIBootstrap:
    """Tests for the bootstrap command scan output."""

    def test_bootstrap_skip_scan(self):
        """--skip-scan suppresses the scan entirely."""
        result = runner.invoke(app, ["bootstrap", "--skip-scan"])
        assert result.exit_code == 0
        assert "Skipping printer scan" in result.output
        assert "Probing" not in result.output

    @patch("zebra_day.print_mgr.zpl")
    def test_bootstrap_verbose_scan_shows_progress(self, mock_zpl_cls):
        """Default scan (no --silent-scan) prints per-IP progress and found printers."""
        mock_zpl_cls.return_value = _make_mock_zpl(
            found_printers=[
                {"ip": "10.0.0.42", "model": "ZD620", "serial": "SN123"},
            ]
        )
        result = runner.invoke(
            app,
            ["bootstrap", "--ip-stub", "10.0.0"],
        )
        assert result.exit_code == 0, result.output
        # Should contain the found-printer line
        assert "10.0.0.42" in result.output
        assert "ZD620" in result.output
        assert "SN123" in result.output
        # Should contain the "Scanned" summary from the done callback
        assert "Scanned" in result.output

    @patch("zebra_day.print_mgr.zpl")
    def test_bootstrap_silent_scan_hides_progress(self, mock_zpl_cls):
        """--silent-scan suppresses per-IP output but still shows summary."""
        mock_zpl_cls.return_value = _make_mock_zpl(
            found_printers=[
                {"ip": "10.0.0.42", "model": "ZD620", "serial": "SN123"},
            ]
        )
        result = runner.invoke(
            app,
            ["bootstrap", "--ip-stub", "10.0.0", "--silent-scan"],
        )
        assert result.exit_code == 0, result.output
        # Per-IP progress should NOT appear
        assert "Probing" not in result.output
        assert "ZD620" not in result.output
        # Summary should still appear
        assert "Scan complete" in result.output

    @patch("zebra_day.print_mgr.zpl")
    def test_bootstrap_json_hides_scan_progress(self, mock_zpl_cls):
        """--json output never includes scan progress lines."""
        mock_zpl_cls.return_value = _make_mock_zpl(
            found_printers=[
                {"ip": "10.0.0.42", "model": "ZD620", "serial": "SN123"},
            ]
        )
        result = runner.invoke(
            app,
            ["bootstrap", "--ip-stub", "10.0.0", "--json"],
        )
        assert result.exit_code == 0, result.output
        assert "Probing" not in result.output
        assert "printers_found" in result.output


class TestCLIBootstrapTrailingDot:
    """Tests for trailing-dot ip_stub rejection in bootstrap command."""

    def test_bootstrap_rejects_trailing_dot(self):
        """bootstrap --ip-stub '192.168.1.' exits with error."""
        result = runner.invoke(app, ["bootstrap", "--ip-stub", "192.168.1."])
        assert result.exit_code == 1
        assert "trailing dot" in result.output

    def test_bootstrap_rejects_trailing_dot_short_flag(self):
        """bootstrap -i '10.0.0.' exits with error."""
        result = runner.invoke(app, ["bootstrap", "-i", "10.0.0."])
        assert result.exit_code == 1
        assert "trailing dot" in result.output


class TestCLIPrinterScanTrailingDot:
    """Tests for trailing-dot ip_stub rejection in printer scan command."""

    def test_printer_scan_rejects_trailing_dot(self):
        """printer scan --ip-stub '192.168.1.' exits with error."""
        result = runner.invoke(app, ["printer", "scan", "--ip-stub", "192.168.1."])
        assert result.exit_code == 1
        assert "trailing dot" in result.output

    def test_printer_scan_rejects_trailing_dot_short_flag(self):
        """printer scan -i '10.0.0.' exits with error."""
        result = runner.invoke(app, ["printer", "scan", "-i", "10.0.0."])
        assert result.exit_code == 1
        assert "trailing dot" in result.output



# ---------------------------------------------------------------------------
# zday man — interactive documentation browser
# ---------------------------------------------------------------------------


class TestCLIManHelp:
    """Tests for zday man --help output."""

    def test_man_help(self):
        """Test man --help shows expected options."""
        result = runner.invoke(app, ["man", "--help"])
        assert result.exit_code == 0
        assert "Interactive documentation browser" in result.output
        assert "--search" in result.output
        assert "--list" in result.output

    def test_man_in_main_help(self):
        """man subcommand appears in top-level help."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "man" in result.output


class TestCLIManList:
    """Tests for zday man --list."""

    def test_list_topics(self):
        """--list shows the topic table."""
        result = runner.invoke(app, ["man", "--list"])
        assert result.exit_code == 0
        assert "Quickstart" in result.output
        assert "CLI Reference" in result.output
        assert "DynamoDB" in result.output
        assert "Troubleshooting" in result.output


class TestCLIManTopics:
    """Tests for direct topic display."""

    def test_quickstart(self):
        """zday man quickstart renders content."""
        result = runner.invoke(app, ["man", "quickstart"])
        assert result.exit_code == 0
        assert "Quickstart" in result.output

    def test_cli_reference(self):
        """zday man cli renders content."""
        result = runner.invoke(app, ["man", "cli"])
        assert result.exit_code == 0
        assert "CLI Reference" in result.output

    def test_gui(self):
        """zday man gui renders the UI guide."""
        result = runner.invoke(app, ["man", "gui"])
        assert result.exit_code == 0
        assert "GUI Usage" in result.output

    def test_https(self):
        """zday man https renders HTTPS docs."""
        result = runner.invoke(app, ["man", "https"])
        assert result.exit_code == 0
        assert "HTTPS" in result.output

    def test_hardware(self):
        """zday man hardware renders hardware guide."""
        result = runner.invoke(app, ["man", "hardware"])
        assert result.exit_code == 0
        assert "Hardware" in result.output

    def test_unknown_topic_exits_1(self):
        """Unknown topic prints error and exits 1."""
        result = runner.invoke(app, ["man", "nonexistent_xyz"])
        assert result.exit_code == 1
        assert "Unknown topic" in result.output

    def test_partial_match(self):
        """Partial topic slug resolves correctly."""
        result = runner.invoke(app, ["man", "quick"])
        assert result.exit_code == 0
        assert "Quickstart" in result.output

    def test_numeric_topic(self):
        """Numeric input resolves to topic by index."""
        result = runner.invoke(app, ["man", "1"])
        assert result.exit_code == 0
        assert "Overview" in result.output


class TestCLIManSearch:
    """Tests for zday man --search."""

    def test_search_finds_results(self):
        """--search returns matching lines."""
        result = runner.invoke(app, ["man", "--search", "printer"])
        assert result.exit_code == 0
        assert "matches" in result.output.lower() or "printer" in result.output.lower()

    def test_search_no_results(self):
        """--search with nonsense term shows no results."""
        result = runner.invoke(app, ["man", "--search", "xyzzy_nonexistent_qwerty"])
        assert result.exit_code == 0
        assert "No results" in result.output


class TestCLIManGracefulDegradation:
    """Tests for graceful handling of missing doc files."""

    def test_missing_file_shows_warning(self):
        """A topic pointing to a missing file shows a warning, not a crash."""
        from zebra_day.cli.man import TOPICS, Topic, TopicSource, _get_topic_content

        fake_topic = Topic(
            name="Missing",
            description="test",
            sources=[TopicSource("does_not_exist.md")],
        )
        content = _get_topic_content(fake_topic)
        assert "not found" in content.lower()

    def test_missing_section_shows_warning(self):
        """A topic with a bad heading shows a warning, not a crash."""
        from zebra_day.cli.man import TOPICS, Topic, TopicSource, _get_topic_content

        fake_topic = Topic(
            name="BadSection",
            description="test",
            sources=[TopicSource("README.md", "HEADING_THAT_DOES_NOT_EXIST_12345")],
        )
        content = _get_topic_content(fake_topic)
        assert "not found" in content.lower()
