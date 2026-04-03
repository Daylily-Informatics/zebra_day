from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import zebra_day.print_mgr as zdpm
from zebra_day.web import auth as auth_module
from zebra_day.web.app import create_app


DAYHOFF_SCHEMA_ROOT = Path("/Users/jmajor/.codex/worktrees/cbc5/dayhoff/contracts/observability")


def _load_schema(name: str) -> dict:
    return json.loads((DAYHOFF_SCHEMA_ROOT / name).read_text())


def _assert_required_shape(payload: dict, schema: dict) -> None:
    for key in schema.get("required", []):
        assert key in payload, f"missing required key {key}"
    projection_schema = schema.get("properties", {}).get("projection")
    if projection_schema and "projection" in payload:
        for key in projection_schema.get("required", []):
            assert key in payload["projection"], f"missing projection key {key}"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    zp = zdpm.zpl()
    zp.create_new_printers_json_with_single_test_printer()
    monkeypatch.setattr(zdpm, "zpl", lambda: zp)
    app = create_app(debug=True, auth="none")
    with TestClient(app) as client:
        yield client


def test_observability_contract_endpoints_match_shared_frame(client: TestClient) -> None:
    client.get("/healthz")
    client.get("/readyz")
    client.get("/obs_services")

    schema_map = {
        "/health": "health.schema.json",
        "/obs_services": "obs_services.schema.json",
        "/api_health": "api_health.schema.json",
        "/endpoint_health": "endpoint_health.schema.json",
        "/auth_health": "auth_health.schema.json",
    }

    for path, schema_name in schema_map.items():
        response = client.get(path)
        assert response.status_code == 200, f"{path} returned {response.status_code}"
        payload = response.json()
        _assert_required_shape(payload, _load_schema(schema_name))
        assert payload["service"] == "zebra_printer"
        assert payload["contract_version"] == "v3"


def test_obs_services_advertises_supported_endpoints_only(client: TestClient) -> None:
    response = client.get("/obs_services")
    assert response.status_code == 200

    advertised = {
        item["path"]: {"auth": item["auth"], "kind": item["kind"]}
        for item in response.json()["endpoints"]
    }
    assert advertised == {
        "/healthz": {"auth": "none", "kind": "liveness"},
        "/readyz": {"auth": "none", "kind": "readiness"},
        "/health": {"auth": "none", "kind": "summary"},
        "/obs_services": {"auth": "none", "kind": "discovery"},
        "/api_health": {"auth": "none", "kind": "api_rollup"},
        "/endpoint_health": {"auth": "none", "kind": "endpoint_rollup"},
        "/auth_health": {"auth": "none", "kind": "auth"},
    }
    assert "zebra_day.observability_v1" in response.json()["extensions"]
    assert "managed_services" not in response.json()


def test_endpoint_health_uses_route_templates_not_raw_instances(client: TestClient) -> None:
    client.get("/api/v1/labs/default")
    response = client.get("/endpoint_health")

    assert response.status_code == 200
    route_templates = {item["route_template"] for item in response.json()["items"]}
    assert "/api/v1/labs/{lab}" in route_templates
    assert all("default" not in item for item in route_templates)


def test_auth_health_exposes_session_summary(client: TestClient) -> None:
    response = client.get("/auth_health")

    assert response.status_code == 200
    auth_payload = response.json()["auth"]
    assert auth_payload["mode"] == "none"
    assert auth_payload["sessions"]["supported"] is False
    assert auth_payload["sessions"]["active_session_count"] is None
    assert auth_payload["sessions"]["recent_user_count"] is None


def test_db_health_is_not_exposed(client: TestClient) -> None:
    response = client.get("/db_health")
    assert response.status_code == 404


def test_my_health_is_not_exposed_when_auth_disabled(client: TestClient) -> None:
    response = client.get("/my_health")
    assert response.status_code == 404


def test_my_health_is_available_when_auth_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    zp = zdpm.zpl()
    zp.create_new_printers_json_with_single_test_printer()
    monkeypatch.setattr(zdpm, "zpl", lambda: zp)
    monkeypatch.setattr(auth_module, "_COGNITO_AVAILABLE", True)
    monkeypatch.setattr(auth_module, "create_auth_dependency", lambda *_a, **_k: lambda: None)
    monkeypatch.setattr(
        auth_module,
        "setup_cognito_auth",
        lambda app: type(
            "FakeAuth",
            (),
            {
                "verify_token": lambda self, token: {
                    "sub": "user-1",
                    "email": "user@lsmc.bio",
                    "name": "Test User",
                    "cognito:groups": ["kahlo-operator"],
                }
            },
        )(),
    )

    app = create_app(debug=True, auth="cognito")
    with TestClient(app) as client:
        response = client.get("/my_health", headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 200
    payload = response.json()
    _assert_required_shape(payload, _load_schema("my_health.schema.json"))
    assert payload["principal"]["email"] == "user@lsmc.bio"
    assert payload["principal"]["auth_mode"] == "cognito"
