from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from tests.fakes import sample_repository
from zebra_day.client import ZebraDayClient
from zebra_day.settings import ZebraDaySettings
from zebra_day.web.app import create_app
from zebra_day.web.auth import SessionPrincipal, build_user_identity


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
                },
                allowed_email_domains=["example.com", "lsmc.com"],
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
        "daylily_cognito.web_session.exchange_authorization_code",
        lambda **kwargs: {
            "access_token": "access-token",
            "id_token": "id-token",
        },
    )
    monkeypatch.setattr("zebra_day.web.app.get_local_ip", lambda: "192.168.1.10")
    return create_app(auth="cognito", client=_seed_client(tmp_path, monkeypatch))


def _cognito_client(app):
    return TestClient(app, base_url="https://localhost:8118")


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
    assert "LOCAL" in response.text
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
    assert payload["extensions"] == ["zebra_day.observability_v1"]
    assert "/api/anomalies" not in {item["path"] for item in payload["endpoints"]}


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
    with _cognito_client(app) as test_client:
        response = test_client.get("/printers", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"].startswith("/auth/login?next=/printers")


def test_login_page_renders_canonical_auth_cta(tmp_path, monkeypatch):
    app = _make_cognito_app(
        tmp_path,
        monkeypatch,
        claims={"sub": "user", "username": "user", "cognito:groups": ["zebra-day-operator"]},
        profile_claims={"email": "user@example.com", "name": "Example User"},
    )
    with _cognito_client(app) as test_client:
        response = test_client.get("/login?next=/admin")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "location" not in response.headers
    assert "/auth/login?next=/admin" in response.text
    assert "LOCAL" in response.text


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


def test_auth_login_redirects_to_cognito_hosted_ui(tmp_path, monkeypatch):
    app = _make_cognito_app(
        tmp_path,
        monkeypatch,
        claims={"sub": "user", "username": "user", "cognito:groups": ["zebra-day-operator"]},
        profile_claims={"email": "user@example.com", "name": "Example User"},
    )
    assert app.state.web_session_config.session_cookie_name == "zebra_day_session"
    assert app.state.web_session_config.allow_insecure_http is False
    with _cognito_client(app) as test_client:
        response = test_client.get("/auth/login?next=/admin", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"].startswith("https://example.com/oauth2/authorize")
    assert "state=" in response.headers["location"]
    assert (
        "redirect_uri=https%3A%2F%2Flocalhost%3A8118%2Fauth%2Fcallback"
        in response.headers["location"]
    )


def test_auth_error_page_does_not_render_dashboard(tmp_path, monkeypatch):
    app = _make_cognito_app(
        tmp_path,
        monkeypatch,
        claims={"sub": "user", "username": "user", "cognito:groups": ["zebra-day-operator"]},
        profile_claims={"email": "user@example.com", "name": "Example User"},
    )
    with _cognito_client(app) as test_client:
        response = test_client.get("/auth/error?reason=token_validation_failed")
    assert response.status_code == 401
    assert "Token validation failed" in response.text
    assert "LOCAL" in response.text
    assert 'data-testid="auth-error-card"' in response.text
    assert "Zebra Day Dashboard" not in response.text
    assert 'data-testid="auth-error-login"' in response.text


def test_auth_error_reason_auth_error_returns_sign_in_page(tmp_path, monkeypatch):
    app = _make_cognito_app(
        tmp_path,
        monkeypatch,
        claims={"sub": "user", "username": "user", "cognito:groups": ["zebra-day-operator"]},
        profile_claims={"email": "user@example.com", "name": "Example User"},
    )
    with _cognito_client(app) as test_client:
        response = test_client.get("/auth/error?reason=auth_error")
    assert response.status_code == 403
    assert "/auth/login" in response.text
    assert 'data-testid="auth-error-login"' in response.text


def test_auth_error_reason_blocked_domain_returns_domain_message(tmp_path, monkeypatch):
    app = _make_cognito_app(
        tmp_path,
        monkeypatch,
        claims={"sub": "user", "username": "user", "cognito:groups": ["zebra-day-operator"]},
        profile_claims={"email": "user@example.com", "name": "Example User"},
    )
    with _cognito_client(app) as test_client:
        response = test_client.get("/auth/error?reason=blocked_domain")
    assert response.status_code == 403
    assert "Email domain not allowed" in response.text


def test_auth_callback_redirects_to_blocked_domain_for_disallowed_email(tmp_path, monkeypatch):
    app = _make_cognito_app(
        tmp_path,
        monkeypatch,
        claims={"sub": "user", "username": "atlas-user", "cognito:groups": ["zebra-day-admin"]},
        profile_claims={"email": "admin@gmail.com", "name": "Admin User"},
    )
    with _cognito_client(app) as test_client:
        login_response = test_client.get("/auth/login", follow_redirects=False)
        state = parse_qs(urlparse(login_response.headers["location"]).query)["state"][0]
        response = test_client.get(
            f"/auth/callback?code=code-123&state={state}",
            follow_redirects=False,
        )
    assert response.status_code == 302
    assert response.headers["location"] == "/auth/error?reason=blocked_domain"


def test_prod_deployment_hides_top_banner(tmp_path, monkeypatch):
    _set_xdg(monkeypatch, tmp_path, deployment="qa-1")
    config_path = tmp_path / "config" / "zebra_day" / "zebra-day-config-qa-1.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        "deployment:\n  name: prod\n  color: ''\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("zebra_day.web.app.get_local_ip", lambda: "192.168.1.10")
    app = create_app(auth="none", client=_seed_client(tmp_path, monkeypatch))

    with TestClient(app) as client:
        response = client.get("/login")

    assert response.status_code == 200
    assert "PROD" not in response.text


def test_auth_callback_persists_groups_and_roles(tmp_path, monkeypatch):
    app = _make_cognito_app(
        tmp_path,
        monkeypatch,
        claims={"sub": "user", "username": "atlas-user", "cognito:groups": ["zebra-day-admin"]},
        profile_claims={"email": "admin@example.com", "name": "Admin User"},
    )
    with _cognito_client(app) as test_client:
        _authenticate_session(test_client)
        response = test_client.get("/my_health")
    principal = response.json()["principal"]
    assert principal["email"] == "admin@example.com"
    assert principal["cognito_groups"] == ["zebra-day-admin"]
    assert principal["roles"] == ["ADMIN", "OPERATOR"]


def test_auth_callback_without_state_redirects_to_state_mismatch(tmp_path, monkeypatch):
    app = _make_cognito_app(
        tmp_path,
        monkeypatch,
        claims={"sub": "user", "username": "atlas-user", "cognito:groups": ["zebra-day-admin"]},
        profile_claims={"email": "admin@example.com", "name": "Admin User"},
    )
    with _cognito_client(app) as test_client:
        test_client.get("/auth/login?next=/printers", follow_redirects=False)
        response = test_client.get("/auth/callback?code=valid-code", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/auth/error?reason=state_mismatch"


def test_cognito_session_expired_after_restart_redirects_to_error(tmp_path, monkeypatch):
    app = _make_cognito_app(
        tmp_path,
        monkeypatch,
        claims={"sub": "user", "username": "atlas-user", "cognito:groups": ["zebra-day-admin"]},
        profile_claims={"email": "admin@example.com", "name": "Admin User"},
    )
    with _cognito_client(app) as test_client:
        _authenticate_session(test_client)
        new_config = replace(
            app.state.web_session_config,
            server_instance_id="new-server-instance",
        )
        app.state.web_session_config = new_config
        app.state.__dict__["_daylily_cognito_web_session_config"] = new_config
        response = test_client.get("/printers", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/auth/error?reason=session_expired"


def test_cognito_mode_keeps_api_routes_unauthorized_without_session(tmp_path, monkeypatch):
    app = _make_cognito_app(
        tmp_path,
        monkeypatch,
        claims={"sub": "user", "username": "user", "cognito:groups": ["zebra-day-operator"]},
        profile_claims={"email": "user@example.com", "name": "Example User"},
    )
    with _cognito_client(app) as test_client:
        response = test_client.get("/api/v1/config")
    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}


def test_cognito_sessions_are_isolated_across_clients(tmp_path, monkeypatch):
    app = _make_cognito_app(
        tmp_path,
        monkeypatch,
        claims={"sub": "user", "username": "atlas-user", "cognito:groups": ["zebra-day-admin"]},
        profile_claims={"email": "admin@example.com", "name": "Admin User"},
    )
    with _cognito_client(app) as client_a, _cognito_client(app) as client_b:
        _authenticate_session(client_a)
        _authenticate_session(client_b)

        first_session = client_a.get("/my_health")
        second_session = client_b.get("/my_health")
        assert first_session.status_code == 200
        assert second_session.status_code == 200
        assert first_session.json()["principal"]["email"] == "admin@example.com"
        assert second_session.json()["principal"]["email"] == "admin@example.com"

        logout = client_a.get("/auth/logout", follow_redirects=False)
        assert logout.status_code == 302

        assert client_a.get("/my_health").status_code == 401
        assert client_b.get("/my_health").status_code == 200


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
    with _cognito_client(app) as test_client:
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
    with _cognito_client(app) as test_client:
        _authenticate_session(test_client)
        response = test_client.get("/admin")
    assert response.status_code == 200
    assert 'data-testid="admin-console-title"' in response.text
