"""Tests for the zebra_day FastAPI web server and API endpoints."""

import json
import threading

import pytest
from fastapi.testclient import TestClient

import zebra_day.print_mgr as zdpm
from zebra_day.web.app import create_app


@pytest.fixture
def client():
    """Create a FastAPI test client with properly initialized state."""
    app = create_app(debug=True, auth="none")
    # Manually initialize the zp state since on_event("startup") isn't called
    # by TestClient unless we use a context manager
    zp = zdpm.zpl()
    # Ensure test printer exists for testing
    zp.create_new_printers_json_with_single_test_printer()

    # Add a test printer to the 'default' lab for testing
    if "default" in zp.printers.get("labs", {}):
        zp.printers["labs"]["default"]["printers"]["test-printer"] = {
            "ip_address": "192.168.1.100",
            "printer_name": "Test Printer",
            "lab_location": "Test Location",
            "manufacturer": "zebra",
            "model": "ZD420",
            "serial": "TEST123",
            "status": "na",
            "label_zpl_styles": ["tube_2inX1in", "corners_1inX2in"],
            "default_label_style": "tube_2inX1in",
            "print_method": "network",
            "arp_data": "na",
            "notes": "Test printer for unit tests",
        }
        zp.save_printer_json()

    app.state.zp = zp
    with TestClient(app) as client:
        yield client


class TestHealthEndpoint:
    """Tests for the /healthz endpoint."""

    def test_health_check(self, client):
        """Test health check endpoint returns 200."""
        response = client.get("/healthz")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


class TestAPIListLabs:
    """Tests for GET /api/v1/labs endpoint."""

    def test_list_labs_returns_list(self, client):
        """Test that labs endpoint returns a list."""
        response = client.get("/api/v1/labs")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_list_labs_contains_default_labs(self, client):
        """Test that default lab exists (from default config)."""
        response = client.get("/api/v1/labs")
        data = response.json()
        assert "default" in data


class TestAPIGetLab:
    """Tests for GET /api/v1/labs/{lab} endpoint."""

    def test_get_lab_success(self, client):
        """Test getting a valid lab."""
        response = client.get("/api/v1/labs/default")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "default"
        assert "lab_name" in data
        assert "lab_display_name" in data
        assert "lab_description" in data
        assert "network_stub" in data
        assert "available_locations" in data
        assert "printers" in data
        assert isinstance(data["printers"], list)

    def test_get_lab_not_found(self, client):
        """Test getting a non-existent lab returns 404."""
        response = client.get("/api/v1/labs/nonexistent-lab-xyz")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestAPIListPrinters:
    """Tests for GET /api/v1/labs/{lab}/printers endpoint."""

    def test_list_printers_success(self, client):
        """Test listing printers in a valid lab."""
        response = client.get("/api/v1/labs/default/printers")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # default lab has a test printer added in fixture
        assert len(data) >= 1

    def test_list_printers_not_found(self, client):
        """Test listing printers in non-existent lab returns 404."""
        response = client.get("/api/v1/labs/nonexistent-lab-xyz/printers")
        assert response.status_code == 404

    def test_printer_has_required_fields(self, client):
        """Test that printer info contains required fields."""
        response = client.get("/api/v1/labs/default/printers")
        data = response.json()
        if len(data) > 0:
            printer = data[0]
            assert "id" in printer
            assert "ip_address" in printer
            assert "model" in printer
            assert "label_zpl_styles" in printer
            assert "print_method" in printer


class TestAPIListTemplates:
    """Tests for GET /api/v1/templates endpoint."""

    def test_list_templates_returns_list(self, client):
        """Test that templates endpoint returns a list."""
        response = client.get("/api/v1/templates")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_list_templates_contains_default(self, client):
        """Test that default template exists."""
        response = client.get("/api/v1/templates")
        data = response.json()
        # tube_2inX1in is the default template
        assert "tube_2inX1in" in data


class TestAPISaveTemplate:
    """Tests for POST /api/v1/templates endpoint."""

    def test_save_template_missing_fields(self, client):
        """Test that missing required fields returns 422."""
        response = client.post("/api/v1/templates", json={})
        assert response.status_code == 422

    def test_save_template_empty_filename(self, client):
        """Test that empty filename returns 400."""
        response = client.post("/api/v1/templates", json={"filename": "", "zpl_content": "^XA^XZ"})
        assert response.status_code == 400
        assert "filename" in response.json()["detail"].lower()

    def test_save_template_invalid_filename_with_path(self, client):
        """Test that filename with path components returns 400."""
        response = client.post(
            "/api/v1/templates", json={"filename": "../evil.zpl", "zpl_content": "^XA^XZ"}
        )
        assert response.status_code == 400
        assert "simple filename" in response.json()["detail"].lower()

    def test_save_template_success(self, client, tmp_path, monkeypatch):
        """Test successful template save."""
        # Monkeypatch the XDG dir to use tmp_path
        from zebra_day import paths as xdg

        monkeypatch.setattr(xdg, "get_label_styles_dir", lambda: tmp_path)

        response = client.post(
            "/api/v1/templates",
            json={"filename": "test_api_template.zpl", "zpl_content": "^XA^FO100,100^FDTest^FS^XZ"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["filename"] == "test_api_template.zpl"
        assert (tmp_path / "test_api_template.zpl").exists()


class TestAPIDeleteTemplate:
    """Tests for DELETE /api/v1/templates/{template_name} endpoint."""

    def test_delete_template_not_found(self, client, tmp_path, monkeypatch):
        """Test deleting non-existent template returns 404."""
        from zebra_day import paths as xdg

        monkeypatch.setattr(xdg, "get_label_styles_dir", lambda: tmp_path)

        response = client.delete("/api/v1/templates/nonexistent_template_xyz")
        assert response.status_code == 404

    def test_delete_template_success(self, client, tmp_path, monkeypatch):
        """Test successful template deletion."""
        from zebra_day import paths as xdg

        monkeypatch.setattr(xdg, "get_label_styles_dir", lambda: tmp_path)

        # Create a template file first
        template_file = tmp_path / "delete_me.zpl"
        template_file.write_text("^XA^XZ")

        response = client.delete("/api/v1/templates/delete_me")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert not template_file.exists()


class TestAPIGetConfig:
    """Tests for GET /api/v1/config endpoint."""

    def test_get_config_returns_dict(self, client):
        """Test that config endpoint returns a dict."""
        response = client.get("/api/v1/config")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_config_has_schema_version(self, client):
        """Test that config has v2 schema_version."""
        response = client.get("/api/v1/config")
        data = response.json()
        assert "schema_version" in data
        assert data["schema_version"] == "2.1.0"

    def test_config_has_labs(self, client):
        """Test that config has labs."""
        response = client.get("/api/v1/config")
        data = response.json()
        assert "labs" in data
        assert isinstance(data["labs"], dict)


class TestAPIPrint:
    """Tests for POST /api/v1/print endpoint."""

    def test_print_missing_lab(self, client):
        """Test print request with missing lab returns error."""
        response = client.post(
            "/api/v1/print",
            json={
                "printer": "some-printer",
            },
        )
        # Missing required field should return 422
        assert response.status_code == 422

    def test_print_missing_printer(self, client):
        """Test print request with missing printer returns error."""
        response = client.post(
            "/api/v1/print",
            json={
                "lab": "default",
            },
        )
        assert response.status_code == 422

    def test_print_with_raw_zpl_content_success(self, client, monkeypatch):
        """Test print request accepts raw ZPL content without touching the network."""

        captured: dict[str, object] = {}

        def fake_print_zpl(**kwargs):
            captured.update(kwargs)
            return kwargs.get("zpl_content") or ""

        monkeypatch.setattr(client.app.state.zp, "print_zpl", fake_print_zpl)

        raw_zpl = "^XA^FO50,50^A0N,50,50^FDTest Label^FS^XZ"
        response = client.post(
            "/api/v1/print",
            json={
                "lab": "default",
                "printer": "test-printer",
                "copies": 2,
                "zpl_content": raw_zpl,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        assert captured["lab"] == "default"
        assert captured["printer_name"] == "test-printer"
        assert captured["print_n"] == 2
        assert captured["zpl_content"] == raw_zpl


class TestAPIRender:
    """Tests for POST /api/v1/render endpoints."""

    def test_render_missing_template_and_zpl(self, client):
        """Test render with no template or zpl_content returns 400."""
        response = client.post(
            "/api/v1/render",
            json={
                "uid_barcode": "TEST123",
            },
        )
        assert response.status_code == 400
        assert (
            "template" in response.json()["detail"].lower()
            or "zpl" in response.json()["detail"].lower()
        )

    def test_render_with_template_success(self, client):
        """Test render with template returns PNG URL."""
        response = client.post(
            "/api/v1/render",
            json={
                "template": "tube_2inX1in",
                "uid_barcode": "TEST123",
                "alt_a": "Line A",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "png_url" in data
        assert data["png_url"].startswith("/generated/")
        assert data["png_url"].endswith(".png")

    def test_render_with_raw_zpl_success(self, client):
        """Test render with raw ZPL content returns PNG URL."""
        response = client.post(
            "/api/v1/render",
            json={
                "zpl_content": "^XA^FO50,50^A0N,50,50^FDTest Label^FS^XZ",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["png_url"].startswith("/generated/")

    def test_render_accepts_float_by_module_width(self, client):
        """Regression: templates may include ^BY1.5 and should not raise a 500."""
        response = client.post(
            "/api/v1/render",
            json={
                # No barcode command needed: parsing ^BY is enough to exercise the bug.
                "zpl_content": "^XA^BY1.5^FO50,50^A0N,50,50^FDTest^FS^XZ",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["png_url"].startswith("/generated/")

    def test_render_png_direct_returns_image(self, client):
        """Test /render/png returns PNG file directly."""
        response = client.post(
            "/api/v1/render/png",
            json={
                "template": "tube_2inX1in",
                "uid_barcode": "DIRECT123",
            },
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"

    def test_render_invalid_template_returns_error(self, client):
        """Test render with invalid template returns error."""
        response = client.post(
            "/api/v1/render",
            json={
                "template": "nonexistent_template_xyz",
            },
        )
        # Invalid template raises FileNotFoundError -> 404
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]


class TestAPIPatchLab:
    """Tests for PATCH /api/v1/labs/{lab} endpoint."""

    def test_patch_lab_not_found(self, client):
        """Test patching non-existent lab returns 404."""
        response = client.patch(
            "/api/v1/labs/nonexistent-lab-xyz",
            json={
                "lab_name": "Test Lab",
            },
        )
        assert response.status_code == 404

    def test_patch_lab_update_name(self, client):
        """Test updating lab name."""
        original = client.get("/api/v1/labs/default").json()
        original_name = original["lab_name"]

        # Update the name
        response = client.patch(
            "/api/v1/labs/default",
            json={
                "lab_name": "Updated Test Name",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["lab_name"] == "Updated Test Name"

        # Restore original name
        client.patch(
            "/api/v1/labs/default",
            json={
                "lab_name": original_name,
            },
        )

    def test_patch_lab_update_display_and_description(self, client):
        """Test updating lab_display_name and lab_description."""
        response = client.patch(
            "/api/v1/labs/default",
            json={
                "lab_display_name": "Default (UI)",
                "lab_description": "Test description",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["lab_display_name"] == "Default (UI)"
        assert data["lab_description"] == "Test description"


class TestAPIPatchPrinter:
    """Tests for PATCH /api/v1/labs/{lab}/printers/{printer_id} endpoint."""

    def test_patch_printer_not_found_lab(self, client):
        """Test patching printer in non-existent lab returns 404."""
        response = client.patch(
            "/api/v1/labs/nonexistent-lab-xyz/printers/some-printer",
            json={"printer_name": "Test"},
        )
        assert response.status_code == 404

    def test_patch_printer_not_found_printer(self, client):
        """Test patching non-existent printer returns 404."""
        response = client.patch(
            "/api/v1/labs/default/printers/nonexistent-printer-xyz",
            json={"printer_name": "Test"},
        )
        assert response.status_code == 404

    def test_patch_printer_update_name(self, client):
        """Test updating printer name."""
        response = client.patch(
            "/api/v1/labs/default/printers/test-printer",
            json={"printer_name": "Updated Test Printer"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["printer_name"] == "Updated Test Printer"

        # Restore original
        client.patch(
            "/api/v1/labs/default/printers/test-printer",
            json={"printer_name": "Test Printer"},
        )

    def test_patch_printer_invalid_default_style(self, client):
        """Test setting invalid default_label_style returns 400."""
        response = client.patch(
            "/api/v1/labs/default/printers/test-printer",
            json={"default_label_style": "nonexistent_style_xyz"},
        )
        assert response.status_code == 400
        assert "must be one of" in response.json()["detail"].lower()


class TestModernUIEndpoints:
    """Tests for modern UI HTML endpoints."""

    def test_dashboard_loads(self, client):
        """Test dashboard page loads."""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_printers_page_loads(self, client):
        """Test printers page loads."""
        response = client.get("/printers")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_print_page_loads(self, client):
        """Test print request page loads."""
        response = client.get("/print")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_templates_page_loads(self, client):
        """Test templates page loads."""
        response = client.get("/templates")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_config_page_loads(self, client):
        """Test config page loads."""
        response = client.get("/config")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


class TestModernUIAdditionalEndpoints:
    """Tests for additional modern UI endpoints."""

    def test_printers_by_lab_loads(self, client):
        """Test printers by lab page loads."""
        response = client.get("/printers/default")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_printer_detail_loads(self, client):
        """Test printer detail page loads."""
        response = client.get("/printers/default/test-printer")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_template_edit_loads(self, client):
        """Test template edit page loads with valid template."""
        response = client.get("/templates/edit?filename=generic_2inX1in.zpl")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_template_edit_not_found(self, client):
        """Test template edit returns 404 for missing template."""
        response = client.get("/templates/edit?filename=nonexistent_template.zpl")
        assert response.status_code == 404

    def test_template_preview_generates_png(self, client):
        """Test template preview endpoint generates PNG and redirects."""
        response = client.get("/templates/preview?filename=generic_2inX1in", follow_redirects=False)
        # Should redirect to the generated PNG file
        assert response.status_code == 303


class TestModernUINetworkScan:
    """Tests for the modern UI network scan SSE + cancel endpoints."""

    def test_scan_pages_default_to_wait_0_5(self, client):
        resp = client.get("/config")
        assert resp.status_code == 200
        assert 'name="scan_wait"' in resp.text
        assert 'value="0.5" selected' in resp.text

        resp = client.get("/printers")
        assert resp.status_code == 200
        assert 'name="scan_wait"' in resp.text
        assert 'value="0.5" selected' in resp.text

    def test_scan_stream_emits_init_and_done(self, client, monkeypatch):
        zp = client.app.state.zp

        def fake_probe(
            *,
            ip_stub: str,
            scan_wait: str,
            lab: str,
            cancel_event=None,
            progress_callback=None,
        ):
            total = 255
            ip = f"{ip_stub}.1"
            if progress_callback:
                progress_callback({"kind": "checking", "ip": ip, "checked": 0, "total": total})
                progress_callback(
                    {
                        "kind": "checked",
                        "ip": ip,
                        "open": False,
                        "checked": 1,
                        "total": total,
                    }
                )
                progress_callback(
                    {"kind": "done", "cancelled": False, "checked": 1, "total": total}
                )
            return {"cancelled": False, "checked": 1, "total": total}

        monkeypatch.setattr(zp, "probe_zebra_printers_add_to_printers_json", fake_probe)

        kinds: list[str] = []
        scan_id = None
        with client.stream(
            "GET",
            "/config/scan/stream?ip_stub=1.2.3&scan_wait=0.5&lab=scan-test",
        ) as resp:
            assert resp.status_code == 200
            for line in resp.iter_lines():
                if not line:
                    continue
                assert line.startswith("data: ")
                msg = json.loads(line[len("data: ") :])
                kinds.append(msg["kind"])
                if msg["kind"] == "init":
                    scan_id = msg.get("scan_id")
                if msg["kind"] == "done":
                    break

        assert kinds[0] == "init"
        assert "checked" in kinds
        assert kinds[-1] == "done"
        assert scan_id

    def test_scan_cancel_sets_cancel_event(self, client):
        scan_id = "scan-id-123"
        cancel_event = threading.Event()

        client.app.state.scan_jobs = {scan_id: {"cancel_event": cancel_event}}

        resp = client.post("/config/scan/cancel", params={"scan_id": scan_id})
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert cancel_event.is_set()

    def test_scan_cancel_unknown_returns_404(self, client):
        client.app.state.scan_jobs = {}
        resp = client.post("/config/scan/cancel", params={"scan_id": "missing"})
        assert resp.status_code == 404

    def test_template_preview_not_found(self, client):
        """Test template preview returns 404 for missing template."""
        response = client.get("/templates/preview?filename=nonexistent_xyz")
        assert response.status_code == 404

    def test_config_view_loads(self, client):
        """Test config view page loads."""
        response = client.get("/config/view")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_config_edit_loads(self, client):
        """Test config edit page loads."""
        response = client.get("/config/edit")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_config_backups_loads(self, client):
        """Test config backups page loads."""
        response = client.get("/config/backups")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_config_new_loads(self, client):
        """Test config new page loads."""
        response = client.get("/config/new")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_config_reset_redirects(self, client):
        """Test config reset redirects to config page."""
        response = client.get("/config/reset", follow_redirects=False)
        assert response.status_code == 303

    def test_config_clear_redirects(self, client):
        """Test config clear redirects to config page."""
        response = client.get("/config/clear", follow_redirects=False)
        assert response.status_code == 303


# Keep the simple assertion test for backward compatibility
def test_web_ui():
    """Simple test to ensure test module loads."""
    assert True
