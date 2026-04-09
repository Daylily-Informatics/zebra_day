from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from tests.fakes import sample_repository
from zebra_day.client import TapDBFleetRepository, ZebraDayApiClient, ZebraDayClient
from zebra_day.settings import (
    DEFAULT_MERIDIAN_DOMAIN_CODE,
    DEFAULT_TAPDB_APP_CODE,
    ZebraDaySettings,
)


def _set_xdg(monkeypatch, tmp_path, deployment="local") -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("ZEBRA_DAY_DEPLOYMENT_CODE", deployment)


def test_direct_client_fails_fast_without_tapdb(monkeypatch, tmp_path):
    _set_xdg(monkeypatch, tmp_path)
    settings = ZebraDaySettings.from_context()
    with pytest.raises(FileNotFoundError):
        ZebraDayClient(settings=settings)


def test_tapdb_fleet_repository_builds_connection_with_zebra_scope(monkeypatch, tmp_path):
    _set_xdg(monkeypatch, tmp_path)
    settings = ZebraDaySettings.from_context()

    captured: dict[str, object] = {}

    def fake_import(module_name: str, _package_name: str):
        if module_name == "daylily_tapdb":
            class _TapdbModule:
                @staticmethod
                def TAPDBConnection(**kwargs):
                    captured.update(kwargs)
                    return SimpleNamespace(session_scope=lambda commit=False: None)

            return _TapdbModule
        if module_name == "daylily_tapdb.cli.db_config":
            return SimpleNamespace(
                get_db_config_for_env=lambda *_args, **_kwargs: {
                    "host": "localhost",
                    "port": "5533",
                    "user": "postgres",
                    "password": "pw",
                    "database": "zebra_day",
                    "engine_type": "local",
                }
            )
        raise AssertionError(f"unexpected import request: {module_name}")

    monkeypatch.setattr("zebra_day.client.import_from_sibling", fake_import)

    repository = object.__new__(TapDBFleetRepository)
    repository.settings = settings
    repository._build_connection()

    assert captured["domain_code"] == DEFAULT_MERIDIAN_DOMAIN_CODE
    assert captured["issuer_app_code"] == DEFAULT_TAPDB_APP_CODE


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
    response = api_client.submit_print_job(lab="default", printer="printer-1", uid_barcode="UID-1")

    assert response["success"] is True
    assert calls == [("GET", "/api/v1/labs"), ("POST", "/api/v1/print")]


def test_api_client_direct_print_uses_remote_resolution(monkeypatch):
    repository = sample_repository()
    resolution = {
        "lab": "default",
        "printer_id": "printer-1",
        "printer_ip": "192.168.1.50",
        "printer": repository.get_printer("default", "printer-1").to_payload(),
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

    zpl = api_client.print_label(lab="default", printer="printer-1", uid_barcode="SAMPLE-1")

    assert zpl == resolution["zpl_content"]
    assert sent == [
        (resolution["zpl_content"], "192.168.1.50"),
        (resolution["zpl_content"], "192.168.1.50"),
    ]
