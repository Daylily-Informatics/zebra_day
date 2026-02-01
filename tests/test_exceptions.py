"""
Tests for the zebra_day exceptions module.
"""
import pytest

from zebra_day import exceptions


class TestZebraDayError:
    """Tests for base ZebraDayError."""

    def test_can_raise_base_error(self):
        """Test ZebraDayError can be raised."""
        with pytest.raises(exceptions.ZebraDayError):
            raise exceptions.ZebraDayError("test error")

    def test_base_error_has_message(self):
        """Test ZebraDayError preserves message."""
        err = exceptions.ZebraDayError("test message")
        assert "test message" in str(err)


class TestPrinterConnectionError:
    """Tests for PrinterConnectionError."""

    def test_printer_connection_error_includes_ip(self):
        """Test PrinterConnectionError includes IP address."""
        err = exceptions.PrinterConnectionError("192.168.1.100", "timeout")
        assert "192.168.1.100" in str(err)
        assert err.printer_ip == "192.168.1.100"

    def test_printer_connection_error_includes_message(self):
        """Test PrinterConnectionError includes message."""
        err = exceptions.PrinterConnectionError("192.168.1.100", "connection refused")
        assert "connection refused" in str(err)


class TestPrinterNotFoundError:
    """Tests for PrinterNotFoundError."""

    def test_printer_not_found_includes_name(self):
        """Test PrinterNotFoundError includes printer name."""
        err = exceptions.PrinterNotFoundError("my-printer")
        assert "my-printer" in str(err)
        assert err.printer_name == "my-printer"

    def test_printer_not_found_includes_lab(self):
        """Test PrinterNotFoundError includes lab when provided."""
        err = exceptions.PrinterNotFoundError("my-printer", lab="lab-1")
        assert "my-printer" in str(err)
        assert "lab-1" in str(err)
        assert err.lab == "lab-1"


class TestConfigError:
    """Tests for ConfigError and subclasses."""

    def test_config_error(self):
        """Test ConfigError basic usage."""
        err = exceptions.ConfigError("config problem", config_path="/path/to/config")
        assert "config problem" in str(err)
        assert err.config_path == "/path/to/config"

    def test_config_file_not_found_error(self):
        """Test ConfigFileNotFoundError includes path."""
        err = exceptions.ConfigFileNotFoundError("/path/to/config.json")
        assert "/path/to/config.json" in str(err)
        assert err.config_path == "/path/to/config.json"

    def test_config_parse_error(self):
        """Test ConfigParseError includes details."""
        err = exceptions.ConfigParseError("/path/to/config.json", "invalid JSON")
        assert "/path/to/config.json" in str(err)
        assert "invalid JSON" in str(err)


class TestLabelTemplateError:
    """Tests for LabelTemplateError and subclasses."""

    def test_label_template_error(self):
        """Test LabelTemplateError basic usage."""
        err = exceptions.LabelTemplateError("my_template", "invalid syntax")
        assert "my_template" in str(err)
        assert "invalid syntax" in str(err)
        assert err.template_name == "my_template"

    def test_label_template_not_found_error(self):
        """Test LabelTemplateNotFoundError includes name."""
        err = exceptions.LabelTemplateNotFoundError("missing_template")
        assert "missing_template" in str(err)
        assert "not found" in str(err)


class TestZPLRenderError:
    """Tests for ZPLRenderError."""

    def test_zpl_render_error(self):
        """Test ZPLRenderError basic usage."""
        err = exceptions.ZPLRenderError("invalid ZPL code")
        assert "invalid ZPL code" in str(err)
        assert "render error" in str(err).lower()


class TestNetworkScanError:
    """Tests for NetworkScanError."""

    def test_network_scan_error(self):
        """Test NetworkScanError basic usage."""
        err = exceptions.NetworkScanError("192.168.1", "timeout during scan")
        assert "192.168.1" in str(err)
        assert "timeout" in str(err)
        assert err.ip_stub == "192.168.1"

