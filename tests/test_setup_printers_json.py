import os


def test_printers_config_loading():
    """Test that printer config loads with v2 schema."""
    from zebra_day import print_mgr as zd

    zd_pm = zd.zpl()
    assert "labs" in zd_pm.printers.keys()
    assert "schema_version" in zd_pm.printers.keys()


def test_printers_clear_reset():
    """Test clearing and resetting printer config with v2 schema."""
    from zebra_day import print_mgr as zd

    zd_pm = zd.zpl()
    zd_pm.clear_printers_json()

    assert "labs" in zd_pm.printers.keys() and len(zd_pm.printers["labs"].keys()) == 0
    assert zd_pm.printers.get("schema_version") == "2.1.0"

    zd_pm.create_new_printers_json_with_single_test_printer()

    # Verify v2 schema structure
    assert "schema_version" in zd_pm.printers
    assert zd_pm.printers["schema_version"] == "2.1.0"
    assert "default" in zd_pm.printers["labs"]

    # Check default lab structure
    default_lab = zd_pm.printers["labs"]["default"]
    assert "printers" in default_lab
    assert "lab_name" in default_lab
    assert "lab_display_name" in default_lab
    assert "lab_description" in default_lab
    assert "network_stub" in default_lab
    assert "available_locations" in default_lab


def test_manipulating_printers_config():
    """Test manipulating printer config with v2 schema (YAML format)."""
    import tempfile

    from zebra_day import print_mgr as zd

    zd_pm = zd.zpl()
    zd_pm.clear_printers_json()

    # Add a test lab with v2 structure
    zd_pm.printers["labs"]["test"] = {
        "lab_name": "Test Lab",
        "lab_display_name": "Test Lab",
        "lab_description": "",
        "network_stub": "",
        "available_locations": [],
        "printers": {},
    }

    # Use a proper temp file with YAML extension
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        zd_pm.save_printer_config(tmp_path)

        assert "test" in zd_pm.printers["labs"].keys()
        assert os.path.exists(zd_pm.printers_filename)

        zd_pm.clear_printers_json()
        assert "test" not in zd_pm.printers["labs"].keys()

        # Reset from template
        zd_pm.create_new_printers_json_with_single_test_printer()

        # Verify v2 schema structure after reset
        assert "schema_version" in zd_pm.printers
        assert zd_pm.printers["schema_version"] == "2.1.0"
        assert "default" in zd_pm.printers["labs"]
        default_lab = zd_pm.printers["labs"]["default"]
        assert "printers" in default_lab
        assert "lab_name" in default_lab
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
