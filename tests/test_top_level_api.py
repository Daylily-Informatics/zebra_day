"""
Unit tests for zebra_day top-level convenience API functions.

Tests for query_labs, query_printers, scan, print_zpl, start_gui.
"""

from unittest import mock

import pytest


class TestQueryLabs:
    """Tests for the query_labs() function."""

    def setup_method(self):
        """Reset the singleton before each test."""
        import zebra_day

        zebra_day._reset_zpl()

    def test_query_labs_returns_list(self):
        """Test that query_labs returns a list of strings."""
        import zebra_day as zd

        labs = zd.query_labs()
        assert isinstance(labs, list)

    def test_query_labs_contains_default(self):
        """Test that query_labs includes 'default' lab after initialization."""
        import zebra_day as zd
        from zebra_day import print_mgr

        # Create a fresh zpl instance with default config
        zp = print_mgr.zpl()
        zp.create_new_printers_json_with_single_test_printer()

        # Reset and query
        zd._reset_zpl()
        labs = zd.query_labs()
        # Should have at least the default lab
        assert "default" in labs

    def test_query_labs_with_mock(self):
        """Test query_labs with mocked printer data."""
        import zebra_day as zd

        mock_printers = {
            "schema_version": "2.0.0",
            "labs": {
                "lab-alpha": {"lab_name": "Alpha", "printers": {}},
                "lab-beta": {"lab_name": "Beta", "printers": {}},
            },
        }

        with mock.patch.object(zd, "_get_zpl") as mock_get:
            mock_zp = mock.MagicMock()
            mock_zp.printers = mock_printers
            mock_get.return_value = mock_zp

            labs = zd.query_labs()
            assert set(labs) == {"lab-alpha", "lab-beta"}


class TestQueryPrinters:
    """Tests for the query_printers() function."""

    def setup_method(self):
        """Reset the singleton before each test."""
        import zebra_day

        zebra_day._reset_zpl()

    def test_query_printers_returns_dict(self):
        """Test that query_printers returns a dictionary."""
        import zebra_day as zd

        mock_printers = {
            "schema_version": "2.0.0",
            "labs": {
                "default": {
                    "lab_name": "Default",
                    "printers": {
                        "192.168.1.100": {
                            "ip_address": "192.168.1.100",
                            "model": "ZD620",
                        }
                    },
                }
            },
        }

        with mock.patch.object(zd, "_get_zpl") as mock_get:
            mock_zp = mock.MagicMock()
            mock_zp.printers = mock_printers
            mock_get.return_value = mock_zp

            printers = zd.query_printers("default")
            assert isinstance(printers, dict)
            assert "192.168.1.100" in printers
            assert printers["192.168.1.100"]["model"] == "ZD620"

    def test_query_printers_nonexistent_lab_raises(self):
        """Test that querying a nonexistent lab raises KeyError."""
        import zebra_day as zd

        mock_printers = {"schema_version": "2.0.0", "labs": {}}

        with mock.patch.object(zd, "_get_zpl") as mock_get:
            mock_zp = mock.MagicMock()
            mock_zp.printers = mock_printers
            mock_get.return_value = mock_zp

            with pytest.raises(KeyError) as exc_info:
                zd.query_printers("nonexistent")

            assert "nonexistent" in str(exc_info.value)


class TestScan:
    """Tests for the scan() function."""

    def setup_method(self):
        """Reset the singleton before each test."""
        import zebra_day

        zebra_day._reset_zpl()

    def test_scan_calls_probe_method(self):
        """Test that scan calls the underlying probe method."""
        import zebra_day as zd

        with mock.patch.object(zd, "_get_zpl") as mock_get:
            mock_zp = mock.MagicMock()
            mock_get.return_value = mock_zp

            zd.scan(ip_stub="10.0.0", lab="test-lab")

            mock_zp.probe_zebra_printers_add_to_printers_json.assert_called_once_with(
                ip_stub="10.0.0", lab="test-lab"
            )

    def test_scan_uses_defaults(self):
        """Test that scan uses default parameters."""
        import zebra_day as zd

        with mock.patch.object(zd, "_get_zpl") as mock_get:
            mock_zp = mock.MagicMock()
            mock_get.return_value = mock_zp

            zd.scan()

            mock_zp.probe_zebra_printers_add_to_printers_json.assert_called_once_with(
                ip_stub="192.168.1", lab="default"
            )


class TestPrintZpl:
    """Tests for the print_zpl() function."""

    def setup_method(self):
        """Reset the singleton before each test."""
        import zebra_day

        zebra_day._reset_zpl()

    def test_print_zpl_calls_underlying_method(self):
        """Test that print_zpl calls the zpl.print_zpl method."""
        import zebra_day as zd

        with mock.patch.object(zd, "_get_zpl") as mock_get:
            mock_zp = mock.MagicMock()
            mock_zp.print_zpl.return_value = "^XA^XZ"
            mock_get.return_value = mock_zp

            result = zd.print_zpl(
                lab="default",
                printer_name="192.168.1.100",
                label_zpl_style="tube_2inX1in",
                uid_barcode="TEST123",
            )

            assert result == "^XA^XZ"
            mock_zp.print_zpl.assert_called_once_with(
                lab="default",
                printer_name="192.168.1.100",
                label_zpl_style="tube_2inX1in",
                uid_barcode="TEST123",
                alt_a="",
                alt_b="",
                alt_c="",
                alt_d="",
                alt_e="",
                alt_f="",
            )

    def test_print_zpl_with_all_alt_fields(self):
        """Test print_zpl with all alternative fields."""
        import zebra_day as zd

        with mock.patch.object(zd, "_get_zpl") as mock_get:
            mock_zp = mock.MagicMock()
            mock_zp.print_zpl.return_value = "^XA^XZ"
            mock_get.return_value = mock_zp

            zd.print_zpl(
                lab="production",
                printer_name="10.0.0.50",
                label_zpl_style="plate_1inX0.25in",
                uid_barcode="SAMPLE-001",
                alt_a="Field A",
                alt_b="Field B",
                alt_c="Field C",
                alt_d="Field D",
                alt_e="Field E",
                alt_f="Field F",
            )

            mock_zp.print_zpl.assert_called_once_with(
                lab="production",
                printer_name="10.0.0.50",
                label_zpl_style="plate_1inX0.25in",
                uid_barcode="SAMPLE-001",
                alt_a="Field A",
                alt_b="Field B",
                alt_c="Field C",
                alt_d="Field D",
                alt_e="Field E",
                alt_f="Field F",
            )


class TestStartGui:
    """Tests for the start_gui() function."""

    def test_start_gui_calls_run_server(self):
        """Test that start_gui calls run_server with correct params."""
        import zebra_day as zd

        with mock.patch("zebra_day.web.app.run_server") as mock_run:
            zd.start_gui(host="127.0.0.1", port=9000, https=False)

            mock_run.assert_called_once_with(
                host="127.0.0.1",
                port=9000,
                reload=False,
                auth="none",
                ssl_certfile=None,
                ssl_keyfile=None,
            )

    def test_start_gui_default_params(self):
        """Test start_gui with default parameters."""
        import zebra_day as zd

        with mock.patch("zebra_day.web.app.run_server") as mock_run:
            zd.start_gui()

            mock_run.assert_called_once_with(
                host="0.0.0.0",
                port=8118,
                reload=False,
                auth="none",
                ssl_certfile=None,
                ssl_keyfile=None,
            )

    def test_start_gui_https_enabled(self):
        """Test start_gui with HTTPS enabled (default)."""
        import zebra_day as zd

        with mock.patch("zebra_day.web.app.run_server") as mock_run:
            zd.start_gui(https=True)

            # With https=True, ssl_certfile/ssl_keyfile are None
            # to let run_server resolve them from env/defaults
            mock_run.assert_called_once()
            call_kwargs = mock_run.call_args[1]
            assert call_kwargs["host"] == "0.0.0.0"
            assert call_kwargs["port"] == 8118


class TestModuleSingleton:
    """Tests for the module-level singleton pattern."""

    def test_get_zpl_returns_same_instance(self):
        """Test that _get_zpl returns the same instance on repeated calls."""
        import zebra_day as zd

        zd._reset_zpl()

        instance1 = zd._get_zpl()
        instance2 = zd._get_zpl()

        assert instance1 is instance2

    def test_reset_zpl_clears_instance(self):
        """Test that _reset_zpl clears the singleton."""
        import zebra_day as zd

        zd._reset_zpl()
        instance1 = zd._get_zpl()

        zd._reset_zpl()
        instance2 = zd._get_zpl()

        # After reset, should be a new instance
        assert instance1 is not instance2


class TestExportsInAll:
    """Tests that all functions are properly exported in __all__."""

    def test_all_functions_in_all(self):
        """Test that all top-level API functions are in __all__."""
        import zebra_day as zd

        expected_functions = [
            "query_labs",
            "query_printers",
            "scan",
            "print_zpl",
            "start_gui",
        ]

        for func_name in expected_functions:
            assert func_name in zd.__all__, f"{func_name} not in __all__"
            assert hasattr(zd, func_name), f"{func_name} not accessible on module"
