"""
Unit tests for core zebra_day functions.

Tests for formulate_zpl, socket send (mocked), config JSON roundtrip.
"""
import json
import os
import socket
import tempfile
from pathlib import Path
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

        assert "does not exist" in str(exc_info.value)


class TestConfigJsonRoundtrip:
    """Tests for printer config JSON serialization/deserialization."""

    def test_save_and_load_printer_json(self):
        """Test that config can be saved and reloaded."""
        from zebra_day import print_mgr as zd

        zd_pm = zd.zpl()
        zd_pm.clear_printers_json()

        # Add test data
        zd_pm.printers["labs"]["roundtrip_test"] = {
            "TestPrinter": {
                "ip_address": "10.0.0.99",
                "label_zpl_styles": ["tube_2inX1in"],
                "print_method": "socket",
                "model": "ZD421",
                "serial": "TEST123",
                "arp_data": "na",
            }
        }

        # Save to temp file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as tmp:
            tmp_path = tmp.name

        try:
            zd_pm.save_printer_json(tmp_path, relative=False)

            # Verify file exists and is valid JSON
            assert os.path.exists(tmp_path)
            with open(tmp_path) as f:
                loaded = json.load(f)

            assert "labs" in loaded
            assert "roundtrip_test" in loaded["labs"]
            assert loaded["labs"]["roundtrip_test"]["TestPrinter"]["ip_address"] == "10.0.0.99"

            # Load into new instance
            zd_pm2 = zd.zpl()
            zd_pm2.load_printer_json(tmp_path, relative=False)

            assert "roundtrip_test" in zd_pm2.printers["labs"]
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

        assert "scan-results" in zd_pm.printers["labs"]
        assert "Download-Label-png" in zd_pm.printers["labs"]["scan-results"]
        assert (
            zd_pm.printers["labs"]["scan-results"]["Download-Label-png"]["ip_address"]
            == "dl_png"
        )

