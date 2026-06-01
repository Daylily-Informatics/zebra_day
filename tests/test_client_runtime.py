from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import yaml

from tests.fakes import sample_repository
from zebra_day.client import (
    TapDBFleetRepository,
    ZebraDayApiClient,
    ZebraDayClient,
    _ensure_prefix_ownership_registry,
)
from zebra_day.settings import (
    DEFAULT_MERIDIAN_DOMAIN_CODE,
    DEFAULT_TAPDB_OWNER_REPO,
    ZebraDaySettings,
    build_default_config_template,
)


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


def _write_config(path: Path, deployment: str, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_direct_client_fails_fast_without_tapdb(monkeypatch, tmp_path):
    _set_xdg(monkeypatch, tmp_path)
    settings = ZebraDaySettings.from_context()
    with pytest.raises(FileNotFoundError):
        ZebraDayClient(settings=settings)


def test_tapdb_fleet_repository_builds_connection_with_zebra_scope(monkeypatch, tmp_path):
    _set_xdg(monkeypatch, tmp_path)
    config_path = Path(tmp_path / "config" / "zebra-day-config-local.yaml")
    tapdb_config_path = tmp_path / "tapdb" / "zebra-day" / "zebra-day-local" / "tapdb-config.yaml"
    domain_registry_path = tmp_path / "tapdb-registry" / "domain_code_registry.json"
    prefix_registry_path = tmp_path / "tapdb-registry" / "prefix_ownership_registry.json"
    payload = yaml.safe_load(build_default_config_template("local").decode("utf-8"))
    payload["tapdb"].update(
        {
            "config_path": str(tapdb_config_path),
            "domain_registry_path": str(domain_registry_path),
            "prefix_ownership_registry_path": str(prefix_registry_path),
        }
    )
    _write_config(config_path, "local", payload)
    tapdb_config_path.parent.mkdir(parents=True, exist_ok=True)
    tapdb_config_path.write_text("tapdb: {}\n", encoding="utf-8")
    monkeypatch.setenv("ZEBRA_DAY_CONFIG_PATH", str(config_path))
    settings = ZebraDaySettings.from_context()

    captured: dict[str, object] = {}

    def fake_import(module_name: str):
        if module_name == "daylily_tapdb":

            class _TapdbModule:
                @staticmethod
                def TAPDBConnection(**kwargs):
                    captured.update(kwargs)
                    return SimpleNamespace(session_scope=lambda commit=False: None)

            return _TapdbModule
        if module_name == "daylily_tapdb.cli.db_config":
            return SimpleNamespace(
                get_db_config=lambda *_args, **_kwargs: {
                    "host": "localhost",
                    "port": "5533",
                    "user": "postgres",
                    "password": "pw",
                    "database": "zebra_day",
                    "schema_name": settings.tapdb_schema_name,
                    "engine_type": "local",
                }
            )
        raise AssertionError(f"unexpected import request: {module_name}")

    monkeypatch.setattr("zebra_day.client._tapdb_import", fake_import)

    repository = object.__new__(TapDBFleetRepository)
    repository.settings = settings
    repository._build_connection()

    assert captured["domain_code"] == DEFAULT_MERIDIAN_DOMAIN_CODE
    assert captured["owner_repo_name"] == DEFAULT_TAPDB_OWNER_REPO
    assert captured["schema_name"] == settings.tapdb_schema_name
    assert captured["app_username"] == settings.tapdb_client_id
    assert captured["iam_auth"] is False
    assert captured["secret_arn"] is None
    assert "domain_registry_path" not in captured
    assert "prefix_registry_path" not in captured


def test_tapdb_fleet_repository_uses_explicit_compose_target(monkeypatch, tmp_path):
    _set_xdg(monkeypatch, tmp_path)
    config_path = Path(tmp_path / "config" / "zebra-day-config-local.yaml")
    tapdb_config_path = tmp_path / "tapdb" / "tapdb-config.yaml"
    domain_registry_path = tmp_path / "tapdb-registry" / "domain_code_registry.json"
    prefix_registry_path = tmp_path / "tapdb-registry" / "prefix_ownership_registry.json"
    payload = yaml.safe_load(build_default_config_template("local").decode("utf-8"))
    payload["tapdb"].update(
        {
            "config_path": str(tapdb_config_path),
            "domain_registry_path": str(domain_registry_path),
            "prefix_ownership_registry_path": str(prefix_registry_path),
        }
    )
    _write_config(config_path, "local", payload)
    tapdb_config_path.parent.mkdir(parents=True, exist_ok=True)
    tapdb_config_path.write_text("target: {}\n", encoding="utf-8")
    monkeypatch.setenv("ZEBRA_DAY_CONFIG_PATH", str(config_path))
    settings = ZebraDaySettings.from_context()
    captured: dict[str, object] = {}
    get_db_calls: list[dict[str, object]] = []

    def fake_import(module_name: str):
        if module_name == "daylily_tapdb":

            class _TapdbModule:
                @staticmethod
                def TAPDBConnection(**kwargs):
                    captured.update(kwargs)
                    return SimpleNamespace(session_scope=lambda commit=False: None)

            return _TapdbModule
        if module_name == "daylily_tapdb.cli.db_config":
            return SimpleNamespace(
                get_db_config=lambda **kwargs: get_db_calls.append(kwargs)
                or {
                    "engine_type": "compose",
                    "host": "postgres",
                    "port": "5432",
                    "user": "dayhoff",
                    "password": "pw",
                    "database": "dayhoff_compose",
                    "schema_name": "tapdb_zebra_day_compose",
                }
            )
        raise AssertionError(f"unexpected import request: {module_name}")

    monkeypatch.setattr("zebra_day.client._tapdb_import", fake_import)
    repository = object.__new__(TapDBFleetRepository)
    repository.settings = settings

    repository._build_connection()

    assert captured["db_hostname"] == "postgres:5432"
    assert captured["engine_type"] == "compose"
    assert captured["iam_auth"] is False
    assert captured["secret_arn"] is None
    assert get_db_calls == [
        {
            "config_path": str(tapdb_config_path),
            "client_id": settings.tapdb_client_id,
            "database_name": settings.tapdb_database_name,
        }
    ]


def test_tapdb_fleet_repository_passes_explicit_aurora_auth_fields(
    monkeypatch, tmp_path
):
    _set_xdg(monkeypatch, tmp_path)
    config_path = Path(tmp_path / "config" / "zebra-day-config-local.yaml")
    tapdb_config_path = tmp_path / "tapdb" / "tapdb-config.yaml"
    domain_registry_path = tmp_path / "tapdb-registry" / "domain_code_registry.json"
    prefix_registry_path = tmp_path / "tapdb-registry" / "prefix_ownership_registry.json"
    payload = yaml.safe_load(build_default_config_template("local").decode("utf-8"))
    payload["tapdb"].update(
        {
            "config_path": str(tapdb_config_path),
            "domain_registry_path": str(domain_registry_path),
            "prefix_ownership_registry_path": str(prefix_registry_path),
        }
    )
    _write_config(config_path, "local", payload)
    tapdb_config_path.parent.mkdir(parents=True, exist_ok=True)
    tapdb_config_path.write_text("target: {}\n", encoding="utf-8")
    monkeypatch.setenv("ZEBRA_DAY_CONFIG_PATH", str(config_path))
    settings = ZebraDaySettings.from_context()
    captured: dict[str, object] = {}

    def fake_import(module_name: str):
        if module_name == "daylily_tapdb":

            class _TapdbModule:
                @staticmethod
                def TAPDBConnection(**kwargs):
                    captured.update(kwargs)
                    return SimpleNamespace(session_scope=lambda commit=False: None)

            return _TapdbModule
        if module_name == "daylily_tapdb.cli.db_config":
            return SimpleNamespace(
                get_db_config=lambda **_kwargs: {
                    "engine_type": "aurora",
                    "host": "db.example.com",
                    "hostaddr": "10.0.1.23",
                    "port": "5432",
                    "user": "dayhoff",
                    "password": "pw",
                    "database": "dayhoff",
                    "schema_name": "tapdb_zebra_day_inf5",
                    "region": "us-east-1",
                    "iam_auth": "false",
                    "secret_arn": "",
                }
            )
        raise AssertionError(f"unexpected import request: {module_name}")

    monkeypatch.setattr("zebra_day.client._tapdb_import", fake_import)
    repository = object.__new__(TapDBFleetRepository)
    repository.settings = settings

    repository._build_connection()

    assert captured["db_hostname"] == "db.example.com:5432"
    assert captured["db_hostaddr"] == "10.0.1.23"
    assert captured["engine_type"] == "aurora"
    assert captured["region"] == "us-east-1"
    assert captured["iam_auth"] is False
    assert captured["secret_arn"] is None


def test_ensure_prefix_ownership_registry_claims_zebra_prefix(monkeypatch, tmp_path):
    registry_path = tmp_path / "prefix_ownership_registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "version": "0.4.0",
                "ownership": {
                    "Z": {
                        "SYS": {"issuer_app_code": "daylily-tapdb"},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = _ensure_prefix_ownership_registry(
        owner_repo_name="zebra-day",
        domain_code="Z",
        prefixes=["zgx", "ZGX", ""],
        registry_path=registry_path,
    )

    assert result == registry_path.resolve()
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    assert payload["ownership"]["Z"]["SYS"]["issuer_app_code"] == "daylily-tapdb"
    assert payload["ownership"]["Z"]["ZGX"]["issuer_app_code"] == "zebra-day"


def test_ensure_prefix_ownership_registry_rejects_conflicting_owner(tmp_path):
    registry_path = tmp_path / "prefix_ownership_registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "version": "0.4.0",
                "ownership": {
                    "Z": {
                        "ZGX": {"issuer_app_code": "other-app"},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="claimed by 'other-app', not 'zebra-day'"):
        _ensure_prefix_ownership_registry(
            owner_repo_name="zebra-day",
            domain_code="Z",
            prefixes=["ZGX"],
            registry_path=registry_path,
        )


def test_packaged_registry_fixtures_match_zebra_prefix_ownership():
    fixture_dir = Path(__file__).resolve().parents[1] / "zebra_day" / "etc"
    domain_registry = json.loads(
        (fixture_dir / "domain_code_registry.json").read_text(encoding="utf-8")
    )
    prefix_registry = json.loads(
        (fixture_dir / "prefix_ownership_registry.json").read_text(encoding="utf-8")
    )

    assert set(domain_registry["domains"]) == {"Z"}
    assert set(prefix_registry["ownership"]) == {"Z"}
    assert set(prefix_registry["ownership"]["Z"]) == {"ZGX"}
    assert prefix_registry["ownership"]["Z"]["ZGX"]["issuer_app_code"] == "zebra-day"


def test_seed_templates_claims_prefixes_before_loader_seed(monkeypatch, tmp_path):
    _set_xdg(monkeypatch, tmp_path)
    settings = ZebraDaySettings.from_context()
    repo = object.__new__(TapDBFleetRepository)
    repo.settings = settings

    captured: dict[str, object] = {}
    executed: list[dict[str, str]] = []

    class _Result:
        def scalar_one_or_none(self):
            return None

    class _Session:
        def execute(self, _statement, params):
            executed.append(dict(params))
            return _Result()

    class _Scope:
        def __enter__(self):
            return _Session()

        def __exit__(self, exc_type, exc, tb):
            return False

    repo._session = lambda *, commit: _Scope()

    def fake_claim(**kwargs):
        captured["claim_kwargs"] = kwargs
        return tmp_path / "claimed.json"

    def fake_import(module_name: str):
        if module_name == "daylily_tapdb.templates.loader":
            return SimpleNamespace(
                find_tapdb_core_config_dir=lambda: tmp_path / "core",
                seed_templates=lambda session, templates, overwrite, **kwargs: captured.update(
                    {
                        "seed_session": session,
                        "template_count": len(templates),
                        "overwrite": overwrite,
                        "seed_kwargs": kwargs,
                    }
                ),
            )
        if module_name == "daylily_tapdb.euid":
            return SimpleNamespace(
                GENERIC_TEMPLATE_PREFIX="TPX",
                GENERIC_INSTANCE_LINEAGE_PREFIX="LNX",
                AUDIT_LOG_PREFIX="ALG",
            )
        raise AssertionError(f"unexpected import request: {module_name}")

    monkeypatch.setattr("zebra_day.client._ensure_prefix_ownership_registry", fake_claim)
    monkeypatch.setattr("zebra_day.client._tapdb_import", fake_import)

    repo._seed_templates()

    assert captured["claim_kwargs"]["owner_repo_name"] == "zebra-day"
    assert captured["claim_kwargs"]["domain_code"] == "Z"
    assert "ZGX" in captured["claim_kwargs"]["prefixes"]
    assert isinstance(captured["seed_session"], _Session)
    assert captured["template_count"] > 0
    assert captured["overwrite"] is False
    assert captured["seed_kwargs"]["prefix_registry_path"] == str(tmp_path / "claimed.json")
    assert {
        "entity": "generic_template",
        "domain_code": "Z",
        "owner_repo_name": "zebra-day",
        "prefix": "ZGX",
    } in executed
    assert {
        "entity": "generic_template",
        "domain_code": "Z",
        "owner_repo_name": "zebra-day",
        "prefix": "TPX",
    } not in executed
    assert {
        "entity": "generic_instance_lineage",
        "domain_code": "Z",
        "owner_repo_name": "zebra-day",
        "prefix": "LNX",
    } in executed
    assert {
        "entity": "audit_log",
        "domain_code": "Z",
        "owner_repo_name": "zebra-day",
        "prefix": "ALG",
    } in executed


def test_template_lookup_uses_explicit_domain_code(monkeypatch, tmp_path):
    _set_xdg(monkeypatch, tmp_path)
    repo = object.__new__(TapDBFleetRepository)
    repo.settings = ZebraDaySettings.from_context()
    captured: dict[str, object] = {}

    class _TemplateManager:
        def get_template(self, session, template_code, *, domain_code=None):
            captured["session"] = session
            captured["template_code"] = template_code
            captured["domain_code"] = domain_code
            return object()

    repo._template_manager = _TemplateManager()

    sentinel_session = object()
    result = repo._template_for_code(sentinel_session, "ZGX/labels/template/1.0/")

    assert result is not None
    assert captured["session"] is sentinel_session
    assert captured["template_code"] == "ZGX/labels/template/1.0/"
    assert captured["domain_code"] == "Z"


def test_api_client_lists_labs_and_submits_print_job(monkeypatch):
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.url.path == "/api/v1/labs":
            return httpx.Response(200, json=["default"])
        if request.url.path == "/api/v1/print":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "message": "Print request sent successfully",
                    "zpl_content": "^XA^XZ",
                },
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url.path}")

    transport = httpx.MockTransport(handler)
    client = httpx.Client(base_url="https://example.test", transport=transport)
    api_client = ZebraDayApiClient("https://example.test", client=client)

    assert api_client.list_labs() == ["default"]
    response = api_client.submit_print_job(
        lab="default", printer_euid="default-printer-0001", uid_barcode="UID-1"
    )

    assert response["success"] is True
    assert calls == [("GET", "/api/v1/labs"), ("POST", "/api/v1/print")]


def test_api_client_direct_print_uses_remote_resolution(monkeypatch):
    repository = sample_repository()
    resolution = {
        "lab": "default",
        "printer_euid": "default-printer-0001",
        "printer_ip": "192.168.1.50",
        "printer": {
            "printer_euid": repository.get_printer("default", "printer-1").euid,
            **{
                key: value
                for key, value in repository.get_printer("default", "printer-1")
                .to_payload()
                .items()
                if key != "euid"
            },
        },
        "template_name": "tube_2inX1in",
        "label_style": "tube_2inX1in",
        "zpl_content": "^XA^FO30,30^FDSAMPLE-1^FS^XZ",
        "copies": 2,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/print/resolve":
            return httpx.Response(200, json=resolution)
        raise AssertionError(f"Unexpected request: {request.method} {request.url.path}")

    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "zebra_day.client.send_zpl_code",
        lambda zpl_code, printer_ip: sent.append((zpl_code, printer_ip)),
    )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(base_url="https://example.test", transport=transport)
    api_client = ZebraDayApiClient("https://example.test", client=client)

    zpl = api_client.print_label(
        lab="default", printer_euid="default-printer-0001", uid_barcode="SAMPLE-1"
    )

    assert zpl == resolution["zpl_content"]
    assert sent == [
        (resolution["zpl_content"], "192.168.1.50"),
        (resolution["zpl_content"], "192.168.1.50"),
    ]
