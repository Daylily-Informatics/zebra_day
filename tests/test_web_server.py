"""
Tests for the zebra_day FastAPI web server and API endpoints.
"""
import json
import os
import pytest
from fastapi.testclient import TestClient

from zebra_day.web.app import create_app
import zebra_day.print_mgr as zdpm


@pytest.fixture
def client():
    """Create a FastAPI test client with properly initialized state."""
    app = create_app(debug=True, auth="none")
    # Manually initialize the zp state since on_event("startup") isn't called
    # by TestClient unless we use a context manager
    app.state.zp = zdpm.zpl()
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

    def test_list_labs_contains_scan_results(self, client):
        """Test that scan-results lab exists (from default config)."""
        response = client.get("/api/v1/labs")
        data = response.json()
        # scan-results is created by default in the template
        assert "scan-results" in data


class TestAPIGetLab:
    """Tests for GET /api/v1/labs/{lab} endpoint."""

    def test_get_lab_success(self, client):
        """Test getting a valid lab."""
        response = client.get("/api/v1/labs/scan-results")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "scan-results"
        assert "lab_name" in data
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
        response = client.get("/api/v1/labs/scan-results/printers")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # scan-results has at least the virtual printer
        assert len(data) >= 1

    def test_list_printers_not_found(self, client):
        """Test listing printers in non-existent lab returns 404."""
        response = client.get("/api/v1/labs/nonexistent-lab-xyz/printers")
        assert response.status_code == 404

    def test_printer_has_required_fields(self, client):
        """Test that printer info contains required fields."""
        response = client.get("/api/v1/labs/scan-results/printers")
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
        assert data["schema_version"] == "2.0.0"

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
        response = client.post("/api/v1/print", json={
            "printer": "some-printer",
        })
        # Missing required field should return 422
        assert response.status_code == 422

    def test_print_missing_printer(self, client):
        """Test print request with missing printer returns error."""
        response = client.post("/api/v1/print", json={
            "lab": "scan-results",
        })
        assert response.status_code == 422

    def test_print_virtual_printer_success(self, client):
        """Test print to virtual PNG printer succeeds."""
        response = client.post("/api/v1/print", json={
            "lab": "scan-results",
            "printer": "Download-Label-png",
            "label_zpl_style": "tube_2inX1in",
            "uid_barcode": "TEST123",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "png_url" in data


class TestAPIPatchLab:
    """Tests for PATCH /api/v1/labs/{lab} endpoint."""

    def test_patch_lab_not_found(self, client):
        """Test patching non-existent lab returns 404."""
        response = client.patch("/api/v1/labs/nonexistent-lab-xyz", json={
            "lab_name": "Test Lab",
        })
        assert response.status_code == 404

    def test_patch_lab_update_name(self, client):
        """Test updating lab name."""
        # First get the current name
        original = client.get("/api/v1/labs/scan-results").json()
        original_name = original["lab_name"]

        # Update the name
        response = client.patch("/api/v1/labs/scan-results", json={
            "lab_name": "Updated Test Name",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["lab_name"] == "Updated Test Name"

        # Restore original name
        client.patch("/api/v1/labs/scan-results", json={
            "lab_name": original_name,
        })


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
            "/api/v1/labs/scan-results/printers/nonexistent-printer-xyz",
            json={"printer_name": "Test"},
        )
        assert response.status_code == 404

    def test_patch_printer_update_name(self, client):
        """Test updating printer name."""
        # Update the name
        response = client.patch(
            "/api/v1/labs/scan-results/printers/Download-Label-png",
            json={"printer_name": "Updated PNG Printer"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["printer_name"] == "Updated PNG Printer"

        # Restore original
        client.patch(
            "/api/v1/labs/scan-results/printers/Download-Label-png",
            json={"printer_name": "Download Label as PNG"},
        )

    def test_patch_printer_invalid_default_style(self, client):
        """Test setting invalid default_label_style returns 400."""
        response = client.patch(
            "/api/v1/labs/scan-results/printers/Download-Label-png",
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


class TestLegacyUIEndpoints:
    """Tests for legacy UI HTML endpoints."""

    def test_legacy_home_loads(self, client):
        """Test legacy home page loads."""
        response = client.get("/legacy")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_legacy_printer_status_loads(self, client):
        """Test legacy printer status page loads."""
        response = client.get("/legacy/printer_status?lab=scan-results")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_legacy_bpr_loads(self, client):
        """Test legacy build print request page loads."""
        response = client.get("/legacy/bpr")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_legacy_simple_print_request_loads(self, client):
        """Test legacy simple print request page loads."""
        response = client.get("/legacy/simple_print_request")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_legacy_edit_zpl_loads(self, client):
        """Test legacy edit ZPL list page loads."""
        response = client.get("/legacy/edit_zpl")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_legacy_chg_ui_style_loads(self, client):
        """Test legacy change UI style page loads."""
        response = client.get("/legacy/chg_ui_style")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_legacy_view_pstation_json_loads(self, client):
        """Test legacy view printer config JSON page loads."""
        response = client.get("/legacy/view_pstation_json")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_legacy_list_prior_configs_loads(self, client):
        """Test legacy list prior config files page loads."""
        response = client.get("/legacy/list_prior_printer_config_files")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_legacy_build_new_config_loads(self, client):
        """Test legacy build new config page loads."""
        response = client.get("/legacy/build_new_printers_config_json")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_legacy_printer_details_loads(self, client):
        """Test legacy printer details page loads."""
        response = client.get("/legacy/printer_details?printer_name=Download-Label-png&lab=scan-results")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


class TestModernUIAdditionalEndpoints:
    """Tests for additional modern UI endpoints."""

    def test_printers_by_lab_loads(self, client):
        """Test printers by lab page loads."""
        response = client.get("/printers/scan-results")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_printer_detail_loads(self, client):
        """Test printer detail page loads."""
        response = client.get("/printers/scan-results/Download-Label-png")
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
        assert "/files/" in response.headers.get("location", "")

    def test_template_preview_not_found(self, client):
        """Test template preview returns 404 for missing template."""
        response = client.get("/templates/preview?filename=nonexistent_xyz")
        assert response.status_code == 404

    def test_config_view_redirects(self, client):
        """Test config view redirects to legacy."""
        response = client.get("/config/view", follow_redirects=False)
        assert response.status_code == 303

    def test_config_edit_redirects(self, client):
        """Test config edit redirects to legacy."""
        response = client.get("/config/edit", follow_redirects=False)
        assert response.status_code == 303

    def test_config_backups_loads(self, client):
        """Test config backups page loads."""
        response = client.get("/config/backups")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


# Keep the simple assertion test for backward compatibility
def test_web_ui():
    """Simple test to ensure test module loads."""
    assert True
