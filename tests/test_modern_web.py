from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from tests.fakes import sample_repository
from zebra_day.client import ZebraDayClient
from zebra_day.settings import ZebraDaySettings
from zebra_day.web.app import create_app


def _set_xdg(monkeypatch, tmp_path, deployment="local") -> None:
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
    def build_login_url(request):
        request.session["oauth_state"] = "state-123"
        return "https://example.com/login?state=state-123"

    return SimpleNamespace(
        config=SimpleNamespace(
            cognito_domain="example.com",
            user_pool_id="pool",
            app_client_id="client",
        ),
        build_login_url=build_login_url,
        build_logout_url=lambda request: "https://example.com/logout",
        exchange_code=lambda request, code: {
            "claims": claims,
            "profile_claims": profile_claims,
            "tokens": {"access_token": "access-token", "id_token": "id-token"},
        },
    )


def _make_cognito_app(
    tmp_path, monkeypatch, *, claims: dict[str, object], profile_claims: dict[str, object]
):
    _set_xdg(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "zebra_day.web.app.setup_cognito_auth",
        lambda app, settings: _make_cognito_binding(claims, profile_claims),
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


def test_root_route_renders(monkeypatch, tmp_path):
    monkeypatch.setattr("zebra_day.web.app.get_local_ip", lambda: "192.168.1.10")
    app = create_app(auth="none", client=_seed_client(tmp_path, monkeypatch))
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "TapDB-backed printer fleet state" in response.text


def test_health_and_observability_routes(monkeypatch, tmp_path):
    monkeypatch.setattr("zebra_day.web.app.get_local_ip", lambda: "192.168.1.10")
    app = create_app(auth="none", client=_seed_client(tmp_path, monkeypatch))
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/readyz").status_code == 200
        payload = client.get("/obs_services").json()
    assert payload["contract_version"] == "v3"
    assert payload["service"] == "zebra-day"


def test_api_routes_use_tapdb_native_shapes(monkeypatch, tmp_path):
    monkeypatch.setattr("zebra_day.web.app.get_local_ip", lambda: "192.168.1.10")
    monkeypatch.setattr(
        "zebra_day.client.render_zpl_preview", lambda zpl, path: path.write_bytes(b"png")
    )
    monkeypatch.setattr("zebra_day.client.send_zpl_code", lambda zpl, ip: None)
    app = create_app(auth="none", client=_seed_client(tmp_path, monkeypatch))
    with TestClient(app) as client:
        labs = client.get("/api/v1/labs")
        printers = client.get("/api/v1/labs/default/printers")
        runtime = client.get("/api/v1/config")
        preview = client.post(
            "/api/v1/render", json={"template": "tube_2inX1in", "uid_barcode": "UID-1"}
        )
        submit = client.post(
            "/api/v1/print",
            json={"lab": "default", "printer": "printer-1", "uid_barcode": "UID-1"},
        )
    assert labs.json() == ["default"]
    assert printers.json()[0]["printer_id"] == "printer-1"
    assert printers.json()[0]["default_label_profile"] == "tube_2inX1in"
    assert runtime.json()["tapdb_database_name"] == "zebra-day-local"
    assert preview.json()["success"] is True
    assert submit.json()["success"] is True


def test_config_and_templates_pages_are_tapdb_only(monkeypatch, tmp_path):
    monkeypatch.setattr("zebra_day.web.app.get_local_ip", lambda: "192.168.1.10")
    app = create_app(auth="none", client=_seed_client(tmp_path, monkeypatch))
    with TestClient(app) as client:
        config_response = client.get("/config")
        templates_response = client.get("/templates")
    assert "TapDB Contract" in config_response.text
    assert "Backend Configuration" not in config_response.text
    assert "Shared Templates" in templates_response.text
    assert "Import Local Templates to DynamoDB" not in templates_response.text


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
    assert 'data-testid="auth-error-card"' in response.text
    assert "Zebra Day Dashboard" not in response.text


def test_auth_callback_persists_groups_and_roles(tmp_path, monkeypatch):
    app = _make_cognito_app(
        tmp_path,
        monkeypatch,
        claims={"sub": "user", "username": "atlas-user", "cognito:groups": ["zebra-day-admin"]},
        profile_claims={"email": "admin@example.com", "name": "Admin User"},
    )
    with TestClient(app) as test_client:
        _authenticate_session(test_client)
        response = test_client.get("/my_health")
    principal = response.json()["principal"]
    assert principal["email"] == "admin@example.com"
    assert principal["cognito_groups"] == ["zebra-day-admin"]
    assert principal["roles"] == ["ADMIN", "OPERATOR"]


def test_admin_route_requires_admin_role(tmp_path, monkeypatch):
    app = _make_cognito_app(
        tmp_path,
        monkeypatch,
        claims={
            "sub": "user",
            "username": "operator-user",
            "cognito:groups": ["zebra-day-operator"],
        },
        profile_claims={"email": "user@example.com", "name": "Standard User"},
    )
    with TestClient(app) as test_client:
        _authenticate_session(test_client)
        response = test_client.get("/admin", follow_redirects=False)
        denied = test_client.get("/auth/error?reason=not_authorized")
    assert response.status_code == 302
    assert response.headers["location"] == "/auth/error?reason=not_authorized"
    assert denied.status_code == 403
    assert "Admin access required" in denied.text


def test_admin_route_allows_admin_user(tmp_path, monkeypatch):
    app = _make_cognito_app(
        tmp_path,
        monkeypatch,
        claims={"sub": "user", "username": "admin-user", "cognito:groups": ["zebra-day-admin"]},
        profile_claims={"email": "admin@example.com", "name": "Admin User"},
    )
    with TestClient(app) as test_client:
        _authenticate_session(test_client)
        response = test_client.get("/admin")
    assert response.status_code == 200
    assert 'data-testid="admin-console-title"' in response.text
