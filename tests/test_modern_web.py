from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from zebra_day.client import InMemoryFleetRepository, PrinterRecord, ZebraDayClient
from zebra_day.settings import ZebraDaySettings
from zebra_day.web.app import create_app


def _seed_client(tmp_path) -> ZebraDayClient:
    repository = InMemoryFleetRepository()
    repository.upsert_template("tube_2inX1in", "^XA^FO30,30^FDTEST^FS^XZ", source="package")
    repository.upsert_label_profile(
        "tube_2inX1in",
        {"profile_name": "tube_2inX1in", "template_name": "tube_2inX1in"},
    )
    repository.upsert_printer(
        PrinterRecord(
            printer_id="printer-1",
            lab="default",
            ip_address="192.168.1.50",
            printer_name="Bench Printer",
            model="ZD620",
            serial="SER123",
            label_profiles=["tube_2inX1in"],
            default_label_profile="tube_2inX1in",
        )
    )
    settings = ZebraDaySettings.from_context()
    return ZebraDayClient(settings=settings, repository=repository)


def _make_cognito_binding(claims: dict[str, object], profile_claims: dict[str, object]):
    def build_login_url(request):
        request.session["oauth_state"] = "state-123"
        return "https://example.com/login?state=state-123"

    return SimpleNamespace(
        auth=SimpleNamespace(verify_token=lambda token: {"sub": "user"}),
        config=SimpleNamespace(cognito_domain="example.com", user_pool_id="pool", app_client_id="client"),
        build_login_url=build_login_url,
        build_logout_url=lambda request: "https://example.com/logout",
        exchange_code=lambda request, code: {
            "claims": claims,
            "profile_claims": profile_claims,
            "tokens": {"access_token": "access-token", "id_token": "id-token"},
        },
    )


def _make_cognito_app(tmp_path, monkeypatch, *, claims: dict[str, object], profile_claims: dict[str, object]):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setattr(
        "zebra_day.web.app.setup_cognito_auth",
        lambda app, settings: _make_cognito_binding(claims, profile_claims),
    )
    return create_app(auth="cognito", client=_seed_client(tmp_path))


def _authenticate_session(test_client: TestClient, claims: dict[str, object], profile_claims: dict[str, object]):
    del claims, profile_claims
    login_response = test_client.get("/auth/login", follow_redirects=False)
    assert login_response.status_code == 302
    state = parse_qs(urlparse(login_response.headers["location"]).query)["state"][0]
    callback_response = test_client.get(
        f"/auth/callback?code=valid-code&state={state}",
        follow_redirects=False,
    )
    assert callback_response.status_code == 302
    assert callback_response.headers["location"] == "/"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    app = create_app(auth="none", client=_seed_client(tmp_path))
    with TestClient(app) as test_client:
        yield test_client


def test_root_route_renders(client):
    response = client.get("/")
    assert response.status_code == 200


def test_health_and_observability_routes(client):
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 200
    payload = client.get("/obs_services").json()
    assert payload["contract_version"] == "v3"
    assert payload["service"] == "zebra-day"


def test_api_routes_use_client_service(client):
    labs = client.get("/api/v1/labs")
    assert labs.status_code == 200
    assert labs.json() == ["default"]

    printers = client.get("/api/v1/labs/default/printers")
    assert printers.status_code == 200
    data = printers.json()
    assert data[0]["id"] == "printer-1"
    assert data[0]["default_label_style"] == "tube_2inX1in"


def test_cognito_mode_redirects_html_when_unauthenticated(tmp_path, monkeypatch):
    app = _make_cognito_app(
        tmp_path,
        monkeypatch,
        claims={"sub": "user", "username": "user", "cognito:groups": ["zebra-day-operator"]},
        profile_claims={"email": "user@example.com", "name": "Example User"},
    )
    with TestClient(app) as test_client:
        response = test_client.get("/printers", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"].startswith("/auth/login")


def test_cognito_mode_allows_local_docs_without_auth(tmp_path, monkeypatch):
    app = _make_cognito_app(
        tmp_path,
        monkeypatch,
        claims={"sub": "user", "username": "user", "cognito:groups": ["zebra-day-operator"]},
        profile_claims={"email": "user@example.com", "name": "Example User"},
    )
    with TestClient(app, client=("127.0.0.1", 50000)) as test_client:
        response = test_client.get("/docs", follow_redirects=False)
    assert response.status_code == 200


def test_cognito_mode_still_gates_nonlocal_docs_without_auth(tmp_path, monkeypatch):
    app = _make_cognito_app(
        tmp_path,
        monkeypatch,
        claims={"sub": "user", "username": "user", "cognito:groups": ["zebra-day-operator"]},
        profile_claims={"email": "user@example.com", "name": "Example User"},
    )
    with TestClient(app, client=("10.10.10.10", 50000)) as test_client:
        response = test_client.get("/docs", follow_redirects=False)
    assert response.status_code == 401


def test_auth_error_page_does_not_render_dashboard(tmp_path, monkeypatch):
    app = _make_cognito_app(
        tmp_path,
        monkeypatch,
        claims={"sub": "user", "username": "user", "cognito:groups": ["zebra-day-operator"]},
        profile_claims={"email": "user@example.com", "name": "Example User"},
    )
    with TestClient(app) as test_client:
        response = test_client.get("/auth/error?reason=token_validation_failed")
    assert response.status_code == 401
    assert "Token validation failed" in response.text
    assert "data-testid=\"auth-error-card\"" in response.text
    assert "Zebra Day Dashboard" not in response.text


def test_auth_error_page_not_authorized_uses_403(tmp_path, monkeypatch):
    app = _make_cognito_app(
        tmp_path,
        monkeypatch,
        claims={"sub": "user", "username": "user", "cognito:groups": ["zebra-day-operator"]},
        profile_claims={"email": "user@example.com", "name": "Example User"},
    )
    with TestClient(app) as test_client:
        response = test_client.get("/auth/error?reason=not_authorized")
    assert response.status_code == 403
    assert "Admin access required" in response.text


def test_auth_callback_persists_groups_and_normalized_roles(tmp_path, monkeypatch):
    claims = {"sub": "user", "username": "atlas-user", "cognito:groups": ["zebra-day-admin"]}
    profile_claims = {"email": "admin@example.com", "name": "Admin User"}
    app = _make_cognito_app(tmp_path, monkeypatch, claims=claims, profile_claims=profile_claims)
    with TestClient(app) as test_client:
        _authenticate_session(test_client, claims, profile_claims)
        response = test_client.get("/my_health")
    assert response.status_code == 200
    principal = response.json()["principal"]
    assert principal["email"] == "admin@example.com"
    assert principal["cognito_groups"] == ["zebra-day-admin"]
    assert principal["roles"] == ["ADMIN", "OPERATOR"]


def test_standard_user_is_redirected_from_admin(tmp_path, monkeypatch):
    claims = {"sub": "user", "username": "operator-user", "cognito:groups": ["zebra-day-operator"]}
    profile_claims = {"email": "user@example.com", "name": "Standard User"}
    app = _make_cognito_app(tmp_path, monkeypatch, claims=claims, profile_claims=profile_claims)
    with TestClient(app) as test_client:
        _authenticate_session(test_client, claims, profile_claims)
        response = test_client.get("/admin", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/auth/error?reason=not_authorized"
        denied = test_client.get(response.headers["location"])
    assert denied.status_code == 403
    assert "Admin access required" in denied.text


def test_admin_user_can_access_admin_page(tmp_path, monkeypatch):
    claims = {"sub": "user", "username": "admin-user", "cognito:groups": ["zebra-day-admin"]}
    profile_claims = {"email": "admin@example.com", "name": "Admin User"}
    app = _make_cognito_app(tmp_path, monkeypatch, claims=claims, profile_claims=profile_claims)
    with TestClient(app) as test_client:
        _authenticate_session(test_client, claims, profile_claims)
        response = test_client.get("/admin")
    assert response.status_code == 200
    assert "data-testid=\"admin-console-title\"" in response.text


def test_state_mismatch_redirects_to_auth_error(tmp_path, monkeypatch):
    claims = {"sub": "user", "username": "admin-user", "cognito:groups": ["zebra-day-admin"]}
    profile_claims = {"email": "admin@example.com", "name": "Admin User"}
    app = _make_cognito_app(tmp_path, monkeypatch, claims=claims, profile_claims=profile_claims)
    with TestClient(app) as test_client:
        login_response = test_client.get("/auth/login", follow_redirects=False)
        assert login_response.status_code == 302
        response = test_client.get("/auth/callback?code=valid-code&state=wrong-state", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/auth/error?reason=state_mismatch"
