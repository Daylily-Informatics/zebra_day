"""
Unit tests for core zebra_day functions.

Tests for formulate_zpl, socket send (mocked), config JSON roundtrip.
"""

import os
import tempfile
from unittest import mock

import pytest


class TestSendZplCode:
    """Tests for the send_zpl_code function."""

    def test_send_zpl_code_is_test_mode(self):
        """Test that is_test=True returns None without network call."""
        from zebra_day.print_mgr import send_zpl_code

        result = send_zpl_code("^XA^XZ", "192.168.1.100", is_test=True)
        assert result is None

    @mock.patch("zebra_day.print_mgr.socket.socket")
    def test_send_zpl_code_success(self, mock_socket_class):
        """Test successful ZPL send with mocked socket."""
        from zebra_day.print_mgr import send_zpl_code

        mock_socket = mock.MagicMock()
        mock_socket.sendall.return_value = None
        mock_socket_class.return_value = mock_socket

        # Should not raise
        send_zpl_code("^XA^XZ", "192.168.1.100", printer_port=9100)

        mock_socket.connect.assert_called_once_with(("192.168.1.100", 9100))
        mock_socket.sendall.assert_called_once_with(b"^XA^XZ")
        mock_socket.close.assert_called_once()

    @mock.patch("zebra_day.print_mgr.socket.socket")
    def test_send_zpl_code_connection_error(self, mock_socket_class):
        """Test that connection errors are properly raised."""
        from zebra_day.print_mgr import send_zpl_code

        mock_socket = mock.MagicMock()
        mock_socket.connect.side_effect = ConnectionRefusedError("Connection refused")
        mock_socket_class.return_value = mock_socket

        with pytest.raises(Exception) as exc_info:
            send_zpl_code("^XA^XZ", "192.168.1.100")

        assert "Error connecting to the printer" in str(exc_info.value)


class TestFormulateZpl:
    """Tests for the formulate_zpl method of the zpl class."""

    def test_formulate_zpl_with_template(self):
        """Test ZPL formatting with known template."""
        from zebra_day import print_mgr as zd

        zd_pm = zd.zpl()
        zd_pm.clear_printers_json()

        zpl = zd_pm.formulate_zpl(
            uid_barcode="TESTBC",
            alt_a="A",
            alt_b="B",
            alt_c="C",
            alt_d="D",
            alt_e="E",
            alt_f="F",
            label_zpl_style="tube_2inX1in",
        )

        # Verify key elements are present
        assert "^XA" in zpl  # Start ZPL
        assert "^XZ" in zpl  # End ZPL
        assert "TESTBC" in zpl  # Barcode value
        assert "A" in zpl  # alt_a

    def test_formulate_zpl_nonexistent_template_raises(self):
        """Test that nonexistent template raises exception."""
        from zebra_day import print_mgr as zd

        zd_pm = zd.zpl()

        with pytest.raises(Exception) as exc_info:
            zd_pm.formulate_zpl(
                uid_barcode="TEST",
                label_zpl_style="nonexistent_template_xyz123",
            )

        assert "not found" in str(exc_info.value)


class TestConfigRoundtrip:
    """Tests for printer config YAML serialization/deserialization."""

    def test_save_and_load_printer_config(self):
        """Test that config can be saved and reloaded as YAML."""
        import yaml

        from zebra_day import print_mgr as zd

        zd_pm = zd.zpl()
        zd_pm.clear_printers_json()

        # Add test data with v2 schema structure
        zd_pm.printers["labs"]["roundtrip_test"] = {
            "lab_name": "Roundtrip Test Lab",
            "lab_display_name": "Roundtrip",
            "lab_description": "Roundtrip description",
            "network_stub": "10.0.0",
            "available_locations": ["Bench A", "Bench B"],
            "printers": {
                "TestPrinter": {
                    "ip_address": "10.0.0.99",
                    "printer_name": "Test Printer Display Name",
                    "lab_location": "Bench A",
                    "manufacturer": "zebra",
                    "label_zpl_styles": ["tube_2inX1in"],
                    "print_method": "socket",
                    "model": "ZD421",
                    "serial": "TEST123",
                    "arp_data": "na",
                    "notes": "",
                }
            },
        }

        # Save to temp file (YAML format)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            zd_pm.save_printer_config(tmp_path)

            # Verify file exists and is valid YAML
            assert os.path.exists(tmp_path)
            with open(tmp_path) as f:
                loaded = yaml.safe_load(f)

            assert "labs" in loaded
            assert "roundtrip_test" in loaded["labs"]
            # v2 schema: printers are nested
            assert (
                loaded["labs"]["roundtrip_test"]["printers"]["TestPrinter"]["ip_address"]
                == "10.0.0.99"
            )
            assert (
                loaded["labs"]["roundtrip_test"]["printers"]["TestPrinter"]["printer_name"]
                == "Test Printer Display Name"
            )

            # Load into new instance
            zd_pm2 = zd.zpl(config_path=tmp_path)

            assert "roundtrip_test" in zd_pm2.printers["labs"]
            assert "lab_display_name" in zd_pm2.printers["labs"]["roundtrip_test"]
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_clear_printers_json(self):
        """Test that clear_printers_json empties the labs."""
        from zebra_day import print_mgr as zd

        zd_pm = zd.zpl()
        zd_pm.clear_printers_json()

        assert "labs" in zd_pm.printers
        assert len(zd_pm.printers["labs"]) == 0

    def test_create_single_test_printer(self):
        """Test creating the default test printer config."""
        from zebra_day import print_mgr as zd

        zd_pm = zd.zpl()
        zd_pm.clear_printers_json()
        zd_pm.create_new_printers_json_with_single_test_printer()

        # v2 schema: only default lab exists (no virtual printers)
        assert "default" in zd_pm.printers["labs"]
        assert "printers" in zd_pm.printers["labs"]["default"]
        assert "schema_version" in zd_pm.printers
        assert zd_pm.printers["schema_version"] == "2.1.0"


class TestZebraPrinterQueries:
    """Tests for the ZebraPrinter query methods in cmd_mgr."""

    @mock.patch("zebra_day.cmd_mgr.socket.socket")
    def test_get_host_identification_success(self, mock_socket_class):
        """Test parsing of ~HI response."""
        from zebra_day.cmd_mgr import ZebraPrinter

        mock_socket = mock.MagicMock()
        mock_socket.recv.return_value = b"ZD420-203dpi ZPL,V84.20.21Z,8,8192KB,options"
        mock_socket_class.return_value.__enter__ = mock.MagicMock(return_value=mock_socket)
        mock_socket_class.return_value.__exit__ = mock.MagicMock(return_value=False)

        printer = ZebraPrinter("192.168.1.100")
        result = printer.get_host_identification(timeout=1.0)

        assert result is not None
        assert result["model"] == "ZD420-203dpi ZPL"
        assert result["firmware"] == "V84.20.21Z"
        assert result["dpi"] == "8"
        assert result["memory"] == "8192KB"

    @mock.patch("zebra_day.cmd_mgr.socket.socket")
    def test_get_host_identification_timeout(self, mock_socket_class):
        """Test that timeout returns None."""
        from zebra_day.cmd_mgr import ZebraPrinter

        mock_socket = mock.MagicMock()
        mock_socket.connect.side_effect = TimeoutError("timeout")
        mock_socket_class.return_value.__enter__ = mock.MagicMock(return_value=mock_socket)
        mock_socket_class.return_value.__exit__ = mock.MagicMock(return_value=False)

        printer = ZebraPrinter("192.168.1.100")
        result = printer.get_host_identification(timeout=1.0)

        assert result is None

    @mock.patch("zebra_day.cmd_mgr.socket.socket")
    def test_get_serial_number_success(self, mock_socket_class):
        """Test parsing of ~HQSN response."""
        from zebra_day.cmd_mgr import ZebraPrinter

        mock_socket = mock.MagicMock()
        mock_socket.recv.return_value = b"SERIAL NUMBER\r\nD8J203901234\r\n"
        mock_socket_class.return_value.__enter__ = mock.MagicMock(return_value=mock_socket)
        mock_socket_class.return_value.__exit__ = mock.MagicMock(return_value=False)

        printer = ZebraPrinter("192.168.1.100")
        result = printer.get_serial_number(timeout=1.0)

        assert result == "D8J203901234"

    @mock.patch("zebra_day.cmd_mgr.socket.socket")
    def test_get_host_status_success(self, mock_socket_class):
        """Test parsing of ~HS response."""
        from zebra_day.cmd_mgr import ZebraPrinter

        # Simulate a normal ~HS response (printer online, not paused, no errors)
        mock_socket = mock.MagicMock()
        mock_socket.recv.return_value = b"0000,0,0,0000,000,0,0,0,000,0,0,0\r\n"
        mock_socket_class.return_value.__enter__ = mock.MagicMock(return_value=mock_socket)
        mock_socket_class.return_value.__exit__ = mock.MagicMock(return_value=False)

        printer = ZebraPrinter("192.168.1.100")
        result = printer.get_host_status(timeout=1.0)

        assert result is not None
        assert result["paused"] is False
        assert result["paper_out"] is False
        assert result["head_up"] is False
        assert result["ribbon_out"] is False

    @mock.patch("zebra_day.cmd_mgr.socket.socket")
    def test_get_host_status_with_errors(self, mock_socket_class):
        """Test parsing of ~HS response with errors."""
        from zebra_day.cmd_mgr import ZebraPrinter

        # Simulate ~HS response with paused=1 (index 2), paper_out=1 (index 5)
        # Format: aaa,b,c,dddd,eee,f,g,h,iii,j,k,l
        #   b=paper_out(1), c=pause(2), f=paper_out(5), g=head_up(6), h=ribbon_out(7)
        mock_socket = mock.MagicMock()
        mock_socket.recv.return_value = b"0000,0,1,0000,000,1,0,0,000,0,0,0\r\n"
        mock_socket_class.return_value.__enter__ = mock.MagicMock(return_value=mock_socket)
        mock_socket_class.return_value.__exit__ = mock.MagicMock(return_value=False)

        printer = ZebraPrinter("192.168.1.100")
        result = printer.get_host_status(timeout=1.0)

        assert result is not None
        assert result["paused"] is True
        assert result["paper_out"] is True

    def test_get_cached_status_returns_dict(self):
        """Test that get_cached_status returns a properly structured dict."""
        from zebra_day.cmd_mgr import clear_printer_cache, get_cached_status

        clear_printer_cache()

        # This will fail to connect (no printer) but should return a valid structure
        result = get_cached_status("192.168.255.255", timeout=0.1)

        assert isinstance(result, dict)
        assert "online" in result
        assert "ip" in result
        assert result["ip"] == "192.168.255.255"
        assert result["online"] is False  # Should be offline due to failed connection

    def test_cache_hit(self):
        """Test that cache is hit on second call."""
        from zebra_day.cmd_mgr import _printer_status_cache, clear_printer_cache

        clear_printer_cache()

        # Pre-populate cache
        test_status = {"online": True, "model": "TEST", "ip": "10.0.0.1"}
        import time

        _printer_status_cache["10.0.0.1"] = (test_status, time.time())

        from zebra_day.cmd_mgr import get_cached_status

        # Should return cached value without network call
        result = get_cached_status("10.0.0.1", timeout=0.1)

        assert result["model"] == "TEST"
        assert result["online"] is True

        clear_printer_cache()


class TestIpStubTrailingDotRejection:
    """Tests for rejecting ip_stub values that end with a trailing dot."""

    def test_probe_rejects_trailing_dot(self):
        """probe_zebra_printers_add_to_printers_json raises ValueError for trailing dot."""
        import zebra_day.print_mgr as zdpm

        zp = zdpm.zpl()
        with pytest.raises(ValueError, match="trailing dot"):
            zp.probe_zebra_printers_add_to_printers_json(ip_stub="192.168.1.")

    def test_probe_rejects_single_dot(self):
        """A bare '.' is also rejected."""
        import zebra_day.print_mgr as zdpm

        zp = zdpm.zpl()
        with pytest.raises(ValueError, match="trailing dot"):
            zp.probe_zebra_printers_add_to_printers_json(ip_stub=".")

    def test_probe_rejects_multiple_trailing_dots(self):
        """Multiple trailing dots (e.g. '10.0.0..') are rejected."""
        import zebra_day.print_mgr as zdpm

        zp = zdpm.zpl()
        with pytest.raises(ValueError, match="trailing dot"):
            zp.probe_zebra_printers_add_to_printers_json(ip_stub="10.0.0..")

    def test_probe_accepts_valid_stub(self):
        """Valid ip_stub (no trailing dot) does NOT raise ValueError.

        We mock http.client connections to avoid real network I/O.
        """
        import zebra_day.print_mgr as zdpm

        zp = zdpm.zpl()
        # Mock HTTPConnection and HTTPSConnection so the 255-IP loop
        # completes instantly without real network calls.
        with (
            mock.patch("http.client.HTTPConnection") as mock_http,
            mock.patch("http.client.HTTPSConnection") as mock_https,
        ):
            # Make every connection attempt raise immediately (no printer)
            mock_http.return_value.request.side_effect = OSError("mocked")
            mock_https.return_value.request.side_effect = OSError("mocked")
            try:
                zp.probe_zebra_printers_add_to_printers_json(ip_stub="10.0.0")
            except ValueError:
                pytest.fail("Valid ip_stub raised ValueError")
