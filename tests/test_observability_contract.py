from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import jsonschema
from fastapi.testclient import TestClient

from tests.fakes import sample_repository
from zebra_day.client import ZebraDayClient
from zebra_day.settings import ZebraDaySettings
from zebra_day.web.app import create_app
from zebra_day.web.auth import SessionPrincipal, build_user_identity


def _schema_root() -> Path:
    root = os.environ.get("DAYHOFF_PROJECT_ROOT")
    if not root:
        raise RuntimeError("DAYHOFF_PROJECT_ROOT must point at the canonical Dayhoff repo root")
    return Path(root) / "contracts" / "observability"


def _validate(name: str, payload: dict) -> None:
    schema = json.loads((_schema_root() / name).read_text(encoding="utf-8"))
    jsonschema.validate(payload, schema)


def _set_xdg(monkeypatch, tmp_path, deployment: str = "local") -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("ZEBRA_DAY_DEPLOYMENT_CODE", deployment)


def _seed_client(tmp_path, monkeypatch) -> ZebraDayClient:
    _set_xdg(monkeypatch, tmp_path)
    settings = ZebraDaySettings.from_context()
    return ZebraDayClient(settings=settings, repository=sample_repository())


def _make_cognito_binding(claims: dict[str, object], profile_claims: dict[str, object]):
    def resolve_principal(token_payload, request):
        del request
        del token_payload
        merged_claims = dict(claims)
        merged_claims.update(profile_claims)
        identity = build_user_identity(
            merged_claims,
            SimpleNamespace(
                cognito_group_role_map={
                    "zebra-day-admin": "ADMIN",
                    "zebra-day-operator": "OPERATOR",
                }
            ),
        )
        return SessionPrincipal(
            user_sub=identity["sub"],
            email=identity["email"],
            name=identity["name"],
            roles=identity["roles"],
            cognito_groups=identity["cognito_groups"],
            auth_mode=identity["auth_mode"],
            authenticated_at="2026-04-02T00:00:00+00:00",
            server_instance_id=None,
            app_context={},
        )

    return SimpleNamespace(
        config=SimpleNamespace(
            cognito_domain="example.com",
            user_pool_id="pool",
            app_client_id="client",
        ),
        build_logout_url=lambda request: "https://example.com/logout",
        resolve_principal=resolve_principal,
    )


def _make_cognito_app(
    tmp_path, monkeypatch, *, claims: dict[str, object], profile_claims: dict[str, object]
):
    _set_xdg(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "zebra_day.web.auth.load_daycog_contract",
        lambda: {
            "region": "us-west-2",
            "user_pool_id": "pool",
            "app_client_id": "client",
            "cognito_domain": "example.com",
            "callback_url": "https://localhost:8118/auth/callback",
            "logout_url": "https://localhost:8118/login",
        },
    )
    monkeypatch.setattr(
        "zebra_day.web.app.setup_cognito_auth",
        lambda app, settings: _make_cognito_binding(claims, profile_claims),
    )
    monkeypatch.setattr(
        "daylily_auth_cognito.browser.session.exchange_authorization_code_async",
        AsyncMock(
            return_value={
                "access_token": "access-token",
                "id_token": "id-token",
            }
        ),
    )
    monkeypatch.setattr("zebra_day.web.app.get_local_ip", lambda: "192.168.1.10")
    return create_app(auth="cognito", client=_seed_client(tmp_path, monkeypatch))


def _authenticate_session(test_client: TestClient) -> None:
    login_response = test_client.get("/auth/login", follow_redirects=False)
    state = parse_qs(urlparse(login_response.headers["location"]).query)["state"][0]
    callback_response = test_client.get(
        f"/auth/callback?code=valid-code&state={state}",
        follow_redirects=False,
    )
    assert callback_response.status_code == 302
    assert callback_response.headers["location"] == "/"


def _assert_projection(payload: dict) -> None:
    assert {"state", "stale", "observed_at", "last_synced_at"} <= set(payload["projection"])


def _assert_frame(payload: dict) -> None:
    assert {
        "contract_version",
        "service",
        "environment",
        "instance_id",
        "observed_at",
        "status",
        "request_id",
        "correlation_id",
        "build",
    } <= set(payload)
    assert payload["contract_version"] == "v3"
    assert payload["service"] == "zebra-day"


def test_observability_contract_routes_match_expected_shapes_no_auth(monkeypatch, tmp_path):
    monkeypatch.setattr("zebra_day.web.app.get_local_ip", lambda: "192.168.1.10")
    app = create_app(auth="none", client=_seed_client(tmp_path, monkeypatch))

    with TestClient(app) as client:
        healthz_payload = client.get("/healthz").json()
        readyz_payload = client.get("/readyz").json()
        client.get("/api/v1/labs/default/printers")

        health_payload = client.get("/health").json()
        obs_payload = client.get("/obs_services").json()
        api_payload = client.get("/api_health").json()
        endpoint_payload = client.get("/endpoint_health").json()
        db_payload = client.get("/db_health").json()
        auth_payload = client.get("/auth_health").json()

        assert client.get("/my_health").status_code == 404

    _validate("healthz.schema.json", healthz_payload)
    _validate("readyz.schema.json", readyz_payload)

    for payload in (
        health_payload,
        obs_payload,
        api_payload,
        endpoint_payload,
        db_payload,
        auth_payload,
    ):
        _assert_frame(payload)

    for payload in (
        health_payload,
        obs_payload,
        api_payload,
        endpoint_payload,
        db_payload,
        auth_payload,
    ):
        _assert_projection(payload)

    assert "checks" in health_payload
    assert healthz_payload["checks"]["process"]["status"] == "ok"
    assert "database" in readyz_payload["checks"]
    assert "families" in api_payload
    assert "page" in endpoint_payload
    assert "items" in endpoint_payload
    assert "database" in db_payload
    assert "auth" in auth_payload

    advertised = {
        item["path"]: {"auth": item["auth"], "kind": item["kind"]}
        for item in obs_payload["endpoints"]
    }
    assert advertised == {
        "/healthz": {"auth": "none", "kind": "liveness"},
        "/readyz": {"auth": "none", "kind": "readiness"},
        "/health": {"auth": "none", "kind": "summary"},
        "/obs_services": {"auth": "none", "kind": "discovery"},
        "/api_health": {"auth": "none", "kind": "api_rollup"},
        "/endpoint_health": {"auth": "none", "kind": "endpoint_rollup"},
        "/db_health": {"auth": "none", "kind": "database"},
        "/auth_health": {"auth": "none", "kind": "auth"},
    }
    assert "/my_health" not in advertised
    assert "zebra_day.observability_v1" in obs_payload["extensions"]

    route_templates = {item["route_template"] for item in endpoint_payload["items"]}
    assert "/api/v1/labs/{lab}/printers" in route_templates
    assert all("default" not in item for item in route_templates)

    auth_summary = auth_payload["auth"]
    assert auth_summary["mode"] == "none"
    assert auth_summary["sessions"]["supported"] is False
    assert auth_summary["sessions"]["active_session_count"] is None
    assert auth_summary["sessions"]["recent_user_count"] is None


def test_my_health_and_auth_health_require_and_report_authenticated_sessions(monkeypatch, tmp_path):
    app = _make_cognito_app(
        tmp_path,
        monkeypatch,
        claims={"sub": "user", "username": "atlas-user", "cognito:groups": ["zebra-day-admin"]},
        profile_claims={"email": "admin@lsmc.bio", "name": "Admin User"},
    )

    with TestClient(app, base_url="https://localhost:8118") as client:
        _authenticate_session(client)

        obs_payload = client.get("/obs_services").json()
        my_health_payload = client.get("/my_health").json()
        auth_payload = client.get("/auth_health").json()

    advertised = {
        item["path"]: {"auth": item["auth"], "kind": item["kind"]}
        for item in obs_payload["endpoints"]
    }
    assert advertised["/my_health"] == {"auth": "authenticated_self", "kind": "self"}

    _assert_frame(my_health_payload)
    assert "principal" in my_health_payload
    assert my_health_payload["principal"]["email"] == "admin@lsmc.bio"
    assert my_health_payload["principal"]["roles"] == ["ADMIN", "OPERATOR"]

    _assert_frame(auth_payload)
    _assert_projection(auth_payload)
    assert auth_payload["auth"]["mode"] == "cognito"
    assert auth_payload["auth"]["sessions"]["supported"] is True
    assert auth_payload["auth"]["sessions"]["active_session_count"] == 1
    assert auth_payload["auth"]["sessions"]["recent_user_count"] == 1
