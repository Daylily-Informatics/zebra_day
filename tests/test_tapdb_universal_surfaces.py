from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

from tests.fakes import sample_repository
from zebra_day.client import ZebraDayClient
from zebra_day.settings import ZebraDaySettings, build_default_config_template
from zebra_day.web.app import create_app


def _set_xdg(monkeypatch, tmp_path, deployment: str = "local") -> None:
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


def _write_tapdb_config(settings: ZebraDaySettings) -> None:
    settings.tapdb_config_path.parent.mkdir(parents=True, exist_ok=True)
    settings.tapdb_config_path.write_text(
        "meta:\n"
        f"  client_id: {settings.tapdb_client_id}\n"
        f"  database_name: {settings.tapdb_database_name}\n",
        encoding="utf-8",
    )


def _dummy_tapdb_app() -> FastAPI:
    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    async def tapdb_home() -> HTMLResponse:
        return HTMLResponse("<h1>Zebra Day TapDB</h1>")

    return app


def _dummy_dag_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/dag/search")
    async def dag_search() -> dict[str, object]:
        return {"items": [], "service": "zebra-day"}

    @router.get("/api/dag/object/{euid}")
    async def dag_object(euid: str) -> dict[str, str]:
        return {"euid": euid, "service": "zebra-day"}

    @router.get("/api/dag/data")
    async def dag_data() -> dict[str, object]:
        return {"items": [], "service": "zebra-day"}

    @router.get("/api/dag/external")
    async def dag_external() -> dict[str, object]:
        return {"items": [], "service": "zebra-day"}

    @router.get("/api/dag/external/object")
    async def dag_external_object() -> dict[str, object]:
        return {"items": [], "service": "zebra-day"}

    return router


def _configured_app(monkeypatch, tmp_path):
    _set_xdg(monkeypatch, tmp_path)
    settings = ZebraDaySettings.from_context()
    _write_tapdb_config(settings)
    monkeypatch.setattr(
        "zebra_day.web.tapdb_surfaces.create_tapdb_web_app",
        lambda **_kwargs: _dummy_tapdb_app(),
    )
    monkeypatch.setattr(
        "zebra_day.web.tapdb_surfaces.create_tapdb_dag_router",
        lambda **_kwargs: _dummy_dag_router(),
    )
    monkeypatch.setattr("zebra_day.web.app.get_local_ip", lambda: "192.168.1.10")
    return create_app(
        auth="none",
        client=ZebraDayClient(settings=settings, repository=sample_repository()),
    )


def test_configured_app_mounts_tapdb_web_and_root_dag(monkeypatch, tmp_path) -> None:
    app = _configured_app(monkeypatch, tmp_path)
    mounts = {str(getattr(route, "path", "")) for route in app.routes if getattr(route, "app", None)}
    paths = {str(getattr(route, "path", "")) for route in app.routes}

    assert "/tapdb" in mounts
    assert "/api/dag/search" in paths
    assert "/api/dag/object/{euid}" in paths
    assert app.state.tapdb_universal_configured is True

    with TestClient(app) as client:
        tapdb = client.get("/tapdb/")
        search = client.get("/api/dag/search")

    assert tapdb.status_code == 200
    assert "Zebra Day TapDB" in tapdb.text
    assert search.status_code == 200
    assert search.json()["service"] == "zebra-day"


def test_obs_services_advertises_tapdb_dag_when_configured(monkeypatch, tmp_path) -> None:
    app = _configured_app(monkeypatch, tmp_path)

    with TestClient(app) as client:
        response = client.get("/obs_services")

    assert response.status_code == 200
    payload = response.json()
    paths = {item["path"] for item in payload["endpoints"]}
    assert "/api/dag/object/{euid}" in paths
    assert "/api/dag/data" in paths
    assert "/api/dag/search" in paths
    assert "/api/dag/external" in paths
    assert "/api/dag/external/object" in paths
    assert "tapdb.dag_v1" in payload["extensions"]
    assert "typed_external_identifier" in payload["external_ref_models"]
    assert payload["tapdb_dag_contract_version"] == "dag:v1"


def test_missing_tapdb_config_records_unconfigured_state(monkeypatch, tmp_path) -> None:
    _set_xdg(monkeypatch, tmp_path)
    settings = ZebraDaySettings.from_context()
    monkeypatch.setattr("zebra_day.web.app.get_local_ip", lambda: "192.168.1.10")

    app = create_app(
        auth="none",
        client=ZebraDayClient(settings=settings, repository=sample_repository()),
    )

    assert app.state.tapdb_universal_configured is False
    assert str(settings.tapdb_config_path) in app.state.tapdb_universal_config_error
    assert "/tapdb" not in {
        str(getattr(route, "path", "")) for route in app.routes if getattr(route, "app", None)
    }
