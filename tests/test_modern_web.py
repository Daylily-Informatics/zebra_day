from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from tests.fakes import sample_repository
from zebra_day import __version__
from zebra_day.client import ZebraDayClient
from zebra_day.settings import ZebraDaySettings, build_default_config_template
from zebra_day.web.app import create_app
from zebra_day.web.auth import SessionPrincipal, build_user_identity


def _set_xdg(monkeypatch, tmp_path, deployment="local") -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("ZEBRA_DAY_DEPLOYMENT_CODE", deployment)
    monkeypatch.setenv("ZEBRA_DAY_SESSION_SECRET", f"test-secret-{deployment}")
    config_path = tmp_path / "config" / "zebra_day" / f"zebra-day-config-{deployment}.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        build_default_config_template(deployment).decode("utf-8"),
        encoding="utf-8",
    )


def _seed_client(tmp_path, monkeypatch, deployment="local") -> ZebraDayClient:
    _set_xdg(monkeypatch, tmp_path, deployment=deployment)
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
    monkeypatch.setenv("COGNITO_REGION", "us-west-2")
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "pool")
    monkeypatch.setenv("COGNITO_APP_CLIENT_ID", "client")
    monkeypatch.setenv("COGNITO_DOMAIN", "example.com")
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


def _cognito_client(app):
    return TestClient(app, base_url="https://localhost:8118")


def _runtime_inventory(app) -> tuple[set[tuple[str, str]], set[str]]:
    methods = {"GET", "POST", "PUT", "PATCH", "DELETE"}
    routes: set[tuple[str, str]] = set()
    mounts: set[str] = set()
    for route in app.routes:
        path = str(getattr(route, "path", "") or "").strip()
        if not path:
            continue
        route_methods = {method for method in getattr(route, "methods", set()) if method in methods}
        if route_methods:
            routes.update((method, path) for method in route_methods)
            continue
        if getattr(route, "app", None) is not None:
            mounts.add(path)
    return routes, mounts


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


def test_runtime_route_inventory_covers_top_level_routes_and_mount_boundaries(
    monkeypatch, tmp_path
):
    monkeypatch.setattr("zebra_day.web.app.get_local_ip", lambda: "192.168.1.10")
    base_app = create_app(auth="none", client=_seed_client(tmp_path, monkeypatch))
    base_routes, base_mounts = _runtime_inventory(base_app)
    expected_base_routes = {
        ("GET", "/"),
        ("GET", "/admin"),
        ("GET", "/printers"),
        ("GET", "/printers/{lab}"),
        ("GET", "/templates"),
        ("GET", "/print"),
        ("GET", "/config"),
        ("GET", "/api/v1/labs"),
        ("GET", "/api/v1/labs/{lab}/printers"),
        ("GET", "/api/v1/labs/{lab}/printers/{printer_euid}"),
        ("PATCH", "/api/v1/labs/{lab}/printers/{printer_euid}"),
        ("POST", "/api/v1/labs/{lab}/discover"),
        ("POST", "/api/v1/labs/{lab}/printers/{printer_euid}/sync"),
        ("GET", "/api/v1/templates"),
        ("GET", "/api/v1/templates/{template_name}"),
        ("POST", "/api/v1/templates"),
        ("DELETE", "/api/v1/templates/{template_name}"),
        ("GET", "/api/v1/label-profiles"),
        ("GET", "/api/v1/label-profiles/{profile_name}"),
        ("POST", "/api/v1/render"),
        ("POST", "/api/v1/render/png"),
        ("POST", "/api/v1/print/resolve"),
        ("POST", "/api/v1/print"),
        ("GET", "/api/v1/config"),
        ("GET", "/healthz"),
        ("GET", "/readyz"),
        ("GET", "/health"),
        ("GET", "/obs_services"),
        ("GET", "/api_health"),
        ("GET", "/endpoint_health"),
        ("GET", "/db_health"),
        ("GET", "/auth_health"),
        ("GET", "/auth/login"),
        ("GET", "/login"),
        ("GET", "/auth/callback"),
        ("GET", "/auth/lsmc/callback"),
        ("GET", "/auth/logout"),
        ("POST", "/auth/logout"),
        ("GET", "/auth/error"),
        ("GET", "/openapi.json"),
        ("GET", "/docs"),
        ("GET", "/api/docs"),
        ("GET", "/redoc"),
        ("GET", "/api/redoc"),
    }
    expected_mounts = {"/static", "/generated"}
    if (base_app.state.pkg_path / "etc").exists():
        expected_mounts.add("/etc")

    assert base_routes == expected_base_routes
    assert base_mounts == expected_mounts
    assert not any(path.startswith("/static/") for _method, path in base_routes)
    assert not any(path.startswith("/generated/") for _method, path in base_routes)
    assert not any(path.startswith("/etc/") for _method, path in base_routes)

    cognito_app = _make_cognito_app(
        tmp_path,
        monkeypatch,
        claims={"sub": "user", "username": "user", "cognito:groups": ["zebra-day-operator"]},
        profile_claims={"email": "user@example.com", "name": "Example User"},
    )
    cognito_routes, cognito_mounts = _runtime_inventory(cognito_app)

    assert cognito_routes == expected_base_routes | {("GET", "/my_health")}
    assert cognito_mounts == expected_mounts


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
            json={"lab": "default", "printer_euid": "default-printer-0001", "uid_barcode": "UID-1"},
        )
    assert labs.json() == ["default"]
    assert printers.json()[0]["printer_euid"] == "default-printer-0001"
    assert "printer_id" not in printers.json()[0]
    assert "euid" not in printers.json()[0]
    assert printers.json()[0]["default_label_profile"] == "tube_2inX1in"
    assert runtime.json()["tapdb_database_name"] == "zebra-day-local"
    assert runtime.json()["version"] == __version__
    assert preview.json()["success"] is True
    assert submit.json()["success"] is True


def test_additional_api_routes_have_direct_smokes(monkeypatch, tmp_path):
    monkeypatch.setattr("zebra_day.web.app.get_local_ip", lambda: "192.168.1.10")
    monkeypatch.setattr(
        "zebra_day.client.render_zpl_preview", lambda zpl, path: path.write_bytes(b"png")
    )
    monkeypatch.setattr(
        "zebra_day.client.discover_printers",
        lambda **_kwargs: [
            {
                "printer_id": "printer-2",
                "ip_address": "192.168.1.60",
                "printer_name": "Discovery Printer",
                "model": "ZD421",
                "serial": "DISC-2",
                "notes": "zpl+http(80)",
            }
        ],
    )

    class _FakeZebraPrinter:
        def __init__(self, ip_address: str, port: int = 9100) -> None:
            self.ip_address = ip_address
            self.port = port

        def get_host_identification(self, timeout: int):
            _ = timeout
            return {"model": "ZD620"}

        def get_serial_number(self, timeout: int):
            _ = timeout
            return "SER123"

    monkeypatch.setattr("zebra_day.cmd_mgr.ZebraPrinter", _FakeZebraPrinter)

    app = create_app(auth="none", client=_seed_client(tmp_path, monkeypatch))
    with TestClient(app) as client:
        printer_detail = client.get("/api/v1/labs/default/printers/default-printer-0001")
        printer_patch = client.patch(
            "/api/v1/labs/default/printers/default-printer-0001",
            json={"printer_name": "Renamed Printer", "lab_location": "Bench 2"},
        )
        discover = client.post(
            "/api/v1/labs/default/discover",
            json={"ip_stub": "192.168.1", "scan_http_port": 80},
        )
        sync = client.post("/api/v1/labs/default/printers/default-printer-0001/sync")
        template_list = client.get("/api/v1/templates")
        template_detail = client.get("/api/v1/templates/tube_2inX1in")
        template_save = client.post(
            "/api/v1/templates",
            json={"filename": "custom.zpl", "zpl_content": "^XA^XZ"},
        )
        template_delete = client.delete("/api/v1/templates/custom")
        profile_list = client.get("/api/v1/label-profiles")
        profile_detail = client.get("/api/v1/label-profiles/tube_2inX1in")
        render_png = client.post(
            "/api/v1/render/png",
            json={"template": "tube_2inX1in", "uid_barcode": "UID-2"},
        )
        resolve = client.post(
            "/api/v1/print/resolve",
            json={"lab": "default", "printer_euid": "default-printer-0001", "uid_barcode": "UID-3"},
        )

    assert printer_detail.status_code == 200
    assert printer_detail.json()["printer_euid"] == "default-printer-0001"
    assert "printer_id" not in printer_detail.json()
    assert "euid" not in printer_detail.json()
    assert printer_patch.status_code == 200
    assert printer_patch.json()["printer_name"] == "Renamed Printer"
    assert printer_patch.json()["lab_location"] == "Bench 2"
    assert discover.status_code == 200
    assert discover.json()[0]["printer_euid"]
    assert "printer_id" not in discover.json()[0]
    assert "euid" not in discover.json()[0]
    assert discover.json()[0]["discovery_source"] == "zpl+http(80)"
    assert sync.status_code == 200
    assert sync.json()["printer_euid"] == "default-printer-0001"
    assert "euid" not in sync.json()
    assert template_list.status_code == 200
    assert "tube_2inX1in" in template_list.json()
    assert template_detail.status_code == 200
    assert template_detail.json()["template_name"] == "tube_2inX1in"
    assert template_save.status_code == 200
    assert template_save.json()["template_name"] == "custom"
    assert template_delete.status_code == 200
    assert template_delete.json()["success"] is True
    assert profile_list.status_code == 200
    assert profile_list.json()[0]["profile_name"] == "tube_2inX1in"
    assert profile_detail.status_code == 200
    assert profile_detail.json()["profile_name"] == "tube_2inX1in"
    assert render_png.status_code == 200
    assert render_png.headers["content-type"] == "image/png"
    assert render_png.content == b"png"
    assert resolve.status_code == 200
    assert resolve.json()["printer_euid"] == "default-printer-0001"
    assert "printer_id" not in resolve.json()
    assert "euid" not in resolve.json()
    assert resolve.json()["copies"] == 1


def test_config_and_templates_pages_are_tapdb_only(monkeypatch, tmp_path):
    monkeypatch.setattr("zebra_day.web.app.get_local_ip", lambda: "192.168.1.10")
    app = create_app(auth="none", client=_seed_client(tmp_path, monkeypatch))
    with TestClient(app) as client:
        config_response = client.get("/config")
        templates_response = client.get("/templates")
    assert "Effective Config" in config_response.text
    assert "Active Config Path" in config_response.text
    assert "Backend Configuration" not in config_response.text
    assert "Shared Templates" in templates_response.text
    assert "Import Local Templates to DynamoDB" not in templates_response.text
    assert __version__ in config_response.text


def test_config_page_redacts_secrets_and_admin_footer_contains_git_metadata(monkeypatch, tmp_path):
    monkeypatch.setattr("zebra_day.web.app.get_local_ip", lambda: "192.168.1.10")
    config_path = tmp_path / "config" / "zebra_day" / "zebra-day-config-local.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        (
            "authentication:\n"
            "  session_secret_key: super-secret\n"
            "tapdb:\n"
            "  client_id: zebra-day\n"
            "  database_name: zebra-day-local\n"
            "ui:\n"
            "  show_environment_chrome: false\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("INTERNAL_API_KEY", "internal-secret-token")
    app = create_app(auth="none", client=_seed_client(tmp_path, monkeypatch))

    with TestClient(app) as client:
        config_response = client.get("/config")
        admin_response = client.get("/admin")

    assert "super-secret" not in config_response.text
    assert "internal-secret-token" not in config_response.text
    assert "configured" in config_response.text
    assert "Active Config Path" in config_response.text
    assert "branch " in admin_response.text
    assert "tag " in admin_response.text
    assert "commit " in admin_response.text
    assert __version__ in admin_response.text


def test_additional_gui_docs_and_auth_routes_have_direct_smokes(monkeypatch, tmp_path):
    monkeypatch.setattr("zebra_day.web.app.get_local_ip", lambda: "192.168.1.10")
    app = create_app(auth="none", client=_seed_client(tmp_path, monkeypatch))
    with TestClient(app) as client:
        printers_by_lab = client.get("/printers/default")
        print_page = client.get(
            "/print?lab=default&printer_euid=default-printer-0001&label_zpl_style=tube_2inX1in"
        )
        openapi = client.get("/openapi.json")
        docs = client.get("/docs")
        api_docs = client.get("/api/docs")
        redoc = client.get("/redoc")
        api_redoc = client.get("/api/redoc")
        logout_get = client.get("/auth/logout", follow_redirects=False)
        logout_post = client.post("/auth/logout", follow_redirects=False)

    assert printers_by_lab.status_code == 200
    assert "Bench Printer" in printers_by_lab.text
    assert print_page.status_code == 200
    assert "Print Label" in print_page.text
    assert openapi.status_code == 200
    assert "/api/v1/print/resolve" in openapi.json()["paths"]
    assert docs.status_code == 200
    assert "SwaggerUIBundle" in docs.text
    assert api_docs.status_code == 200
    assert "SwaggerUIBundle" in api_docs.text
    assert redoc.status_code == 200
    assert "redoc.standalone.js" in redoc.text
    assert api_redoc.status_code == 200
    assert "redoc.standalone.js" in api_redoc.text
    assert logout_get.status_code == 302
    assert logout_get.headers["location"] == "/login"
    assert logout_post.status_code == 302
    assert logout_post.headers["location"] == "/login"


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
    assert "branch " in response.text
    assert "tag " in response.text
    assert "commit " in response.text


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


def test_external_broker_login_and_callback_create_session(tmp_path, monkeypatch):
    monkeypatch.setenv("LSMC_AUTH_BROKER_SERVICE_ID", "zebra-day")
    monkeypatch.setenv(
        "LSMC_AUTH_BROKER_LOGIN_URL",
        "https://dev.login.lsmc.com:8916/auth/login",
    )
    monkeypatch.setenv(
        "LSMC_AUTH_BROKER_HANDOFF_EXCHANGE_URL",
        "https://dev.login.lsmc.com:8916/auth/handoff/consume",
    )
    monkeypatch.setenv(
        "LSMC_AUTH_BROKER_LOGOUT_URL",
        "https://dev.login.lsmc.com:8916/auth/logout",
    )

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "user": {
                    "canonical_user_id": "usr_johnm",
                    "email": "johnm@lsmc.com",
                    "display_name": "John Major",
                    "groups": ["lsmc:global-admin"],
                    "roles": [],
                    "service_entitlements": [],
                }
            }

    class FakeAsyncClient:
        def __init__(self, *, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json):
            assert url == "https://dev.login.lsmc.com:8916/auth/handoff/consume"
            assert json == {"code": "handoff-code"}
            return FakeResponse()

    monkeypatch.setattr("zebra_day.web.auth.httpx.AsyncClient", FakeAsyncClient)
    app = create_app(
        auth="external_broker",
        client=_seed_client(tmp_path, monkeypatch),
    )

    with TestClient(app, base_url="https://localhost:8118") as client:
        login = client.get("/auth/login?next=/printers", follow_redirects=False)
        assert login.status_code == 302
        login_url = urlparse(login.headers["location"])
        assert f"{login_url.scheme}://{login_url.netloc}{login_url.path}" == (
            "https://dev.login.lsmc.com:8916/auth/login"
        )
        query = parse_qs(login_url.query)
        assert query["service"] == ["zebra-day"]
        assert query["next"] == ["/printers"]
        assert query["callback_url"] == ["https://localhost:8118/auth/lsmc/callback"]

        callback = client.get(
            f"/auth/lsmc/callback?code=handoff-code&state={query['state'][0]}",
            follow_redirects=False,
        )
        assert callback.status_code == 302
        assert callback.headers["location"] == "/printers"

        health = client.get("/my_health")
        assert health.status_code == 200
        principal = health.json()["principal"]
        assert principal["email"] == "johnm@lsmc.com"
        assert principal["roles"] == ["ADMIN", "OPERATOR"]
        assert principal["auth_mode"] == "external_broker"


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
    assert "branch " in response.text
    assert "tag " in response.text


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


def test_environment_chrome_can_be_disabled_by_config(tmp_path, monkeypatch):
    _set_xdg(monkeypatch, tmp_path, deployment="qa-1")
    config_path = tmp_path / "config" / "zebra_day" / "zebra-day-config-qa-1.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        "ui:\n  show_environment_chrome: false\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("zebra_day.web.app.get_local_ip", lambda: "192.168.1.10")
    app = create_app(auth="none", client=_seed_client(tmp_path, monkeypatch, deployment="qa-1"))

    with TestClient(app) as client:
        response = client.get("/login")

    assert response.status_code == 200
    assert (
        "background: #21ca91; color: #ffffff; display: flex; align-items: center; justify-content: center; font-size: 0.65rem; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase;"
        not in response.text
    )


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
        app.state.__dict__["_daylily_auth_cognito_web_session_config"] = new_config
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
