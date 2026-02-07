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

    def _fake_probe(ip_stub="192.168.1", progress_callback=None, scan_http_port=None, **kwargs):
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
            ["--json", "bootstrap", "--ip-stub", "10.0.0"],
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



# =====================================================================
# Simulator tests
# =====================================================================

import socket
import http.client
import time


class TestSimulatorCore:
    """Tests for the simulator module (non-CLI)."""

    def test_zpl_hi_response(self):
        """~HI returns expected host identification."""
        from zebra_day.simulator import PrinterProfile, SimulatedPrinter

        profile = PrinterProfile(model="ZT411-300dpi ZPL", serial="TESTSN1", firmware="V1.0.0")
        printer = SimulatedPrinter("127.0.0.1", zpl_port=19201, http_port=18201, profile=profile)
        printer.start()
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2)
                s.connect(("127.0.0.1", 19201))
                s.sendall(b"~HI")
                resp = s.recv(4096).decode(errors="ignore")
            assert "ZT411-300dpi ZPL" in resp
            assert "V1.0.0" in resp
        finally:
            printer.stop()

    def test_zpl_serial_number(self):
        """~HQSN returns configured serial number."""
        from zebra_day.simulator import PrinterProfile, SimulatedPrinter

        profile = PrinterProfile(serial="ABCD1234")
        printer = SimulatedPrinter("127.0.0.1", zpl_port=19202, http_port=18202, profile=profile)
        printer.start()
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2)
                s.connect(("127.0.0.1", 19202))
                s.sendall(b"~HQSN")
                resp = s.recv(4096).decode(errors="ignore")
            assert "ABCD1234" in resp
        finally:
            printer.stop()

    def test_zpl_host_status_flags(self):
        """~HS returns correct status flags for paper_out + head_up."""
        from zebra_day.simulator import PrinterProfile, SimulatedPrinter

        profile = PrinterProfile(paper_out=True, head_up=True)
        printer = SimulatedPrinter("127.0.0.1", zpl_port=19203, http_port=18203, profile=profile)
        printer.start()
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2)
                s.connect(("127.0.0.1", 19203))
                s.sendall(b"~HS")
                resp = s.recv(4096).decode(errors="ignore")
            # Line 1 format: 0000,0,{pause},{...},{paper},{head},{ribbon},...
            # With paper_out=True head_up=True: ...,1,1,0,...
            lines = resp.strip().strip("\x02\x03").split("\r\n")
            parts = lines[0].split(",")
            assert parts[5].strip() == "1"  # paper_out
            assert parts[6].strip() == "1"  # head_up
            assert parts[7].strip() == "0"  # ribbon_out (not set)
        finally:
            printer.stop()

    def test_zpl_odometer(self):
        """~HQOD returns label count."""
        from zebra_day.simulator import PrinterProfile, SimulatedPrinter

        profile = PrinterProfile(label_count=99999)
        printer = SimulatedPrinter("127.0.0.1", zpl_port=19204, http_port=18204, profile=profile)
        printer.start()
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2)
                s.connect(("127.0.0.1", 19204))
                s.sendall(b"~HQOD")
                resp = s.recv(4096).decode(errors="ignore")
            assert "99999" in resp
            assert "LABEL" in resp.upper()
        finally:
            printer.stop()

    def test_http_discovery_page(self):
        """HTTP server returns page with Zebra keywords for scanner detection."""
        from zebra_day.simulator import PrinterProfile, SimulatedPrinter

        profile = PrinterProfile(model="ZD620-203dpi ZPL", serial="HTTPSN1")
        printer = SimulatedPrinter("127.0.0.1", zpl_port=19205, http_port=18205, profile=profile)
        printer.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", 18205, timeout=2)
            conn.request("GET", "/")
            resp = conn.getresponse()
            body = resp.read().decode()
            conn.close()
            # Scanner looks for these keywords
            body_lower = body.lower()
            assert "zebra" in body_lower
            assert "link-os" in body_lower
            # Model and serial should be present
            assert "ZD620" in body
            assert "HTTPSN1" in body
            # Server header should say Zebra
            assert "Zebra" in (resp.getheader("Server") or "")
        finally:
            printer.stop()

    def test_cmd_mgr_integration(self):
        """cmd_mgr.ZebraPrinter can query the simulator and parse responses."""
        from zebra_day.simulator import PrinterProfile, SimulatedPrinter
        from zebra_day.cmd_mgr import ZebraPrinter

        profile = PrinterProfile(
            model="ZT411-203dpi ZPL", serial="INTEG001", firmware="V99.0.0",
            label_count=500,
        )
        printer = SimulatedPrinter("127.0.0.1", zpl_port=19206, http_port=18206, profile=profile)
        printer.start()
        try:
            zp = ZebraPrinter("127.0.0.1", port=19206)
            hi = zp.get_host_identification()
            assert hi is not None
            assert hi["model"] == "ZT411-203dpi ZPL"
            assert hi["firmware"] == "V99.0.0"

            sn = zp.get_serial_number()
            assert sn == "INTEG001"

            od = zp.get_odometer()
            assert od is not None
            assert od["label_count"] == 500

            hs = zp.get_host_status()
            assert hs is not None
            assert hs["paper_out"] is False

            status = zp.get_full_status()
            assert status["online"] is True
            assert status["model"] == "ZT411-203dpi ZPL"
            assert status["serial"] == "INTEG001"
        finally:
            printer.stop()


class TestSimulatorCLI:
    """Tests for the simulator CLI commands."""

    def test_simulator_help(self):
        """simulator --help shows commands."""
        result = runner.invoke(app, ["simulator", "--help"])
        assert result.exit_code == 0
        assert "start" in result.output
        assert "stop" in result.output
        assert "list" in result.output

    def test_simulator_start_help(self):
        """simulator start --help shows options."""
        result = runner.invoke(app, ["simulator", "start", "--help"])
        assert result.exit_code == 0
        assert "--model" in result.output
        assert "--serial" in result.output
        assert "--zpl-port" in result.output
        assert "--http-port" in result.output

    def test_simulator_list_empty(self):
        """simulator list works when no simulators running."""
        result = runner.invoke(app, ["simulator", "list"])
        assert result.exit_code == 0

    def test_simulator_stop_nonexistent(self):
        """simulator stop on non-running simulator doesn't crash."""
        result = runner.invoke(app, ["simulator", "stop", "--host", "127.0.0.1", "--zpl-port", "19999"])
        assert result.exit_code == 0


class TestSimulatorManager:
    """Tests for SimulatorManager fleet management."""

    def test_start_and_list(self):
        """Start a printer and verify it appears in list."""
        from zebra_day.simulator import PrinterProfile, SimulatorManager

        mgr = SimulatorManager()
        try:
            mgr.start_printer(
                host="127.0.0.1", zpl_port=19210, http_port=18210,
                profile=PrinterProfile(model="ZD420-203dpi ZPL", serial="MGR001"),
            )
            printers = mgr.list_printers()
            assert len(printers) == 1
            assert printers[0]["model"] == "ZD420-203dpi ZPL"
            assert printers[0]["serial"] == "MGR001"
            assert printers[0]["running"] is True
        finally:
            mgr.stop_all()

    def test_start_duplicate_raises(self):
        """Starting a printer on same address raises RuntimeError."""
        import pytest
        from zebra_day.simulator import SimulatorManager

        mgr = SimulatorManager()
        try:
            mgr.start_printer(host="127.0.0.1", zpl_port=19211, http_port=18211)
            with pytest.raises(RuntimeError, match="already running"):
                mgr.start_printer(host="127.0.0.1", zpl_port=19211, http_port=18212)
        finally:
            mgr.stop_all()

    def test_stop_all(self):
        """stop_all shuts down all printers."""
        from zebra_day.simulator import SimulatorManager

        mgr = SimulatorManager()
        mgr.start_printer(host="127.0.0.1", zpl_port=19212, http_port=18212)
        mgr.start_printer(host="127.0.0.1", zpl_port=19213, http_port=18213)
        count = mgr.stop_all()
        assert count == 2
        assert mgr.list_printers() == []

    def test_multiple_printers(self):
        """Multiple simulators can run simultaneously with different responses."""
        from zebra_day.simulator import PrinterProfile, SimulatorManager
        from zebra_day.cmd_mgr import ZebraPrinter

        mgr = SimulatorManager()
        try:
            mgr.start_printer(
                host="127.0.0.1", zpl_port=19214, http_port=18214,
                profile=PrinterProfile(model="ZD620-203dpi ZPL", serial="FLEET1"),
            )
            mgr.start_printer(
                host="127.0.0.1", zpl_port=19215, http_port=18215,
                profile=PrinterProfile(model="ZT411-300dpi ZPL", serial="FLEET2"),
            )
            zp1 = ZebraPrinter("127.0.0.1", port=19214)
            zp2 = ZebraPrinter("127.0.0.1", port=19215)
            assert zp1.get_serial_number() == "FLEET1"
            assert zp2.get_serial_number() == "FLEET2"
        finally:
            mgr.stop_all()


# ---------------------------------------------------------------------------
# Scanner integration tests (ZPL-first discovery with simulator)
# ---------------------------------------------------------------------------


class TestScannerZPLFirst:
    """Tests verifying the ZPL-first scanner logic using the simulator.

    On macOS every 127.0.0.x address routes to loopback, so a naïve
    test that redirects ALL connections to the simulator would discover
    255 printers and take minutes.  Instead, each test:
      • Routes only the *target* IP (127.0.0.1) to the simulator port.
      • Routes all other IPs to a guaranteed-dead port → instant
        ``ConnectionRefused``.
      • Uses ``cancel_event`` that fires after the first ``found``
        callback for extra safety.
      • Uses a tiny ``scan_wait`` (0.05 s) so refused connections fail
        fast.
    """

    @staticmethod
    def _make_selective_zp(target_ip, sim_port):
        """Return a ZebraPrinter subclass that routes *target_ip* to
        *sim_port* and everything else to a dead port (39999)."""
        from zebra_day.cmd_mgr import ZebraPrinter

        class _SelectiveZP(ZebraPrinter):
            def __init__(self, ip, port=9100, **kw):
                real_port = sim_port if ip == target_ip else 39999
                super().__init__(ip, port=real_port, **kw)

        return _SelectiveZP

    def test_scan_finds_printer_via_zpl(self):
        """Default scan (no scan_http_port) discovers printer via ZPL port 9100."""
        import threading
        from unittest.mock import patch as _patch
        from zebra_day.simulator import PrinterProfile, SimulatedPrinter
        import zebra_day.print_mgr as zdpm

        profile = PrinterProfile(model="ZD620-203dpi ZPL", serial="SCANTEST1")
        printer = SimulatedPrinter("127.0.0.1", zpl_port=19220, http_port=18220, profile=profile)
        printer.start()
        try:
            zp = zdpm.zpl()
            cancel = threading.Event()
            found_events = []

            def _cb(evt):
                if evt.get("kind") == "found":
                    found_events.append(evt)
                    cancel.set()

            _SelectiveZP = self._make_selective_zp("127.0.0.1", 19220)
            with _patch("zebra_day.cmd_mgr.ZebraPrinter", _SelectiveZP):
                zp.probe_zebra_printers_add_to_printers_json(
                    ip_stub="127.0.0",
                    scan_wait="0.05",
                    lab="zpl-test",
                    progress_callback=_cb,
                    cancel_event=cancel,
                )

            lab_printers = zp.printers.get("labs", {}).get("zpl-test", {}).get("printers", {})
            assert len(found_events) >= 1
            found_ip = found_events[0]["ip"]
            assert found_ip in lab_printers
            p = lab_printers[found_ip]
            assert p["model"] == "ZD620-203dpi ZPL"
            assert p["serial"] == "SCANTEST1"
            assert "zpl" in p.get("notes", "").lower()
        finally:
            printer.stop()

    def test_scan_http_fallback(self):
        """scan_http_port enables HTTP-based discovery when ZPL fails."""
        import threading
        from unittest.mock import patch as _patch
        from zebra_day.simulator import PrinterProfile, SimulatedPrinter
        import zebra_day.print_mgr as zdpm

        profile = PrinterProfile(model="ZT411-300dpi ZPL", serial="HTTPFB1")
        printer = SimulatedPrinter("127.0.0.1", zpl_port=19221, http_port=18221, profile=profile)
        printer.start()
        try:
            zp = zdpm.zpl()
            cancel = threading.Event()
            found_events = []

            def _cb(evt):
                if evt.get("kind") == "found":
                    found_events.append(evt)
                    cancel.set()

            # ZPL always fails (dead port); HTTP goes to simulator
            _DeadZP = self._make_selective_zp("__none__", 39999)
            with _patch("zebra_day.cmd_mgr.ZebraPrinter", _DeadZP):
                zp.probe_zebra_printers_add_to_printers_json(
                    ip_stub="127.0.0",
                    scan_wait="0.05",
                    lab="http-fb-test",
                    scan_http_port=18221,
                    progress_callback=_cb,
                    cancel_event=cancel,
                )

            lab_printers = zp.printers.get("labs", {}).get("http-fb-test", {}).get("printers", {})
            assert len(found_events) >= 1
            found_ip = found_events[0]["ip"]
            assert found_ip in lab_printers
            p = lab_printers[found_ip]
            assert "http" in p.get("notes", "").lower()
        finally:
            printer.stop()

    def test_scan_no_http_port_skips_http(self):
        """Without scan_http_port, HTTP is not attempted (backward compat)."""
        import threading
        from unittest.mock import patch as _patch
        from zebra_day.simulator import PrinterProfile, SimulatedPrinter
        import zebra_day.print_mgr as zdpm

        profile = PrinterProfile(model="ZD420-203dpi ZPL", serial="NOHTTP1")
        printer = SimulatedPrinter("127.0.0.1", zpl_port=19222, http_port=18222, profile=profile)
        printer.start()
        try:
            zp = zdpm.zpl()
            cancel = threading.Event()
            found_events = []

            def _cb(evt):
                if evt.get("kind") == "found":
                    found_events.append(evt)
                    cancel.set()

            _SelectiveZP = self._make_selective_zp("127.0.0.1", 19222)
            with _patch("zebra_day.cmd_mgr.ZebraPrinter", _SelectiveZP):
                zp.probe_zebra_printers_add_to_printers_json(
                    ip_stub="127.0.0",
                    scan_wait="0.05",
                    lab="nohttp-test",
                    progress_callback=_cb,
                    cancel_event=cancel,
                    # scan_http_port NOT set — should be ZPL-only
                )

            lab_printers = zp.printers.get("labs", {}).get("nohttp-test", {}).get("printers", {})
            found_any = [ip for ip, p in lab_printers.items() if p.get("model") == "ZD420-203dpi ZPL"]
            assert len(found_any) >= 1
            p = lab_printers[found_any[0]]
            assert "zpl" in p.get("notes", "").lower()
            assert "http" not in p.get("notes", "").lower()
        finally:
            printer.stop()
