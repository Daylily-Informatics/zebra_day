from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from click.exceptions import Abort, Exit

from zebra_day.cli import cognito as cognito_module
from zebra_day.cli import config_extra as config_extra_module
from zebra_day.cli import env as env_module
from zebra_day.cli import logs as logs_module
from zebra_day.cli import printer as printer_module
from zebra_day.cli import simulator as simulator_cli_module
from zebra_day.cli import template as template_module
from zebra_day.client import PrinterRecord


def _set_xdg(monkeypatch, tmp_path, deployment: str = "local") -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("ZEBRA_DAY_DEPLOYMENT_CODE", deployment)
    monkeypatch.delenv("ZEBRA_DAY_CONFIG_PATH", raising=False)
    monkeypatch.delenv("ZEBRA_DAY_ACTIVE", raising=False)
    monkeypatch.delenv("ZEBRA_DAY_PROJECT_ROOT", raising=False)
    monkeypatch.delenv("ZDAY_PROJECT_ROOT", raising=False)
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)


def _settings(tmp_path, **overrides):
    config_path = tmp_path / "config" / "zebra-day-config-local.yaml"
    tapdb_config_path = tmp_path / "tapdb-config.yaml"
    state_dir = tmp_path / "state"
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "deployment_code": "local",
        "config_path": config_path,
        "tapdb_config_path": tapdb_config_path,
        "tapdb_client_id": "zebra-day",
        "tapdb_database_name": "zebra-day-local",
        "tapdb_env": "dev",
        "auth_mode": "cognito",
        "state_dir": state_dir,
        "logs_dir": logs_dir,
        "port": 8118,
        "callback_path": "/auth/callback",
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def test_env_activate_reset_status_and_deactivate(monkeypatch, tmp_path, capsys):
    _set_xdg(monkeypatch, tmp_path, deployment="qa1")
    repo_root = tmp_path / "repo"
    nested = repo_root / "src" / "nested"
    nested.mkdir(parents=True)
    (repo_root / "pyproject.toml").write_text("[project]\nname='zebra_day'\n", encoding="utf-8")
    (repo_root / "activate").write_text("#!/bin/sh\n", encoding="utf-8")
    (repo_root / "zebra_day_deactivate").write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.chdir(nested)
    panels: list[object] = []
    monkeypatch.setattr(env_module.ccyo_out, "print_text", lambda value: panels.append(value))

    env_module.activate()
    capsys.readouterr()
    activate_panel = panels.pop()
    assert str(repo_root / "activate") in str(activate_panel.renderable)
    assert "<deploy-name>" in str(activate_panel.renderable)

    monkeypatch.setenv("ZEBRA_DAY_ACTIVE", "1")
    monkeypatch.setenv("ZEBRA_DAY_PROJECT_ROOT", str(repo_root))
    monkeypatch.setenv("VIRTUAL_ENV", str(tmp_path / "venv"))

    env_module.status()
    status_out = capsys.readouterr().out
    assert "zebra_day environment: Active" in status_out
    assert "Project root:" in status_out
    assert repo_root.name in status_out
    assert "Virtual env:" in status_out
    assert "venv" in status_out
    assert "zebra-day-config-qa1.yaml" in status_out

    env_module.reset()
    capsys.readouterr()
    reset_panel = panels.pop()
    assert "zebra_day_deactivate" in str(reset_panel.renderable)
    assert "activate <deploy-name>" in str(reset_panel.renderable)

    env_module.deactivate()
    capsys.readouterr()
    deactivate_panel = panels.pop()
    assert "zebra_day_deactivate" in str(deactivate_panel.renderable)


def test_env_missing_root_and_inactive_paths(monkeypatch, tmp_path, capsys):
    _set_xdg(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ZEBRA_DAY_PROJECT_ROOT", raising=False)
    monkeypatch.delenv("ZDAY_PROJECT_ROOT", raising=False)
    panels: list[object] = []
    monkeypatch.setattr(env_module.ccyo_out, "print_text", lambda value: panels.append(value))

    env_module.deactivate()
    inactive_capture = capsys.readouterr()
    inactive_out = inactive_capture.out + inactive_capture.err
    assert "environment is not active" in inactive_out

    with pytest.raises(Exit):
        env_module.activate()
    activate_capture = capsys.readouterr()
    activate_out = activate_capture.out + activate_capture.err
    assert "Could not find zebra_day project root" in activate_out

    monkeypatch.setenv("ZEBRA_DAY_ACTIVE", "1")
    env_module.deactivate()
    capsys.readouterr()
    fallback_panel = panels.pop()
    assert "zebra_day_deactivate" in str(fallback_panel.renderable)
    assert "deactivate" in str(fallback_panel.renderable)

    with pytest.raises(Exit):
        env_module.reset()
    reset_capture = capsys.readouterr()
    reset_out = reset_capture.out + reset_capture.err
    assert "Could not find zebra_day project root" in reset_out


def test_cognito_commands_cover_status_bind_import_validate_and_passthrough(
    monkeypatch, tmp_path, capsys
):
    _set_xdg(monkeypatch, tmp_path, deployment="qa")
    settings = _settings(tmp_path, deployment_code="qa", auth_mode="cognito", port=8443)
    contract = {
        "region": "us-west-2",
        "user_pool_id": "pool-1",
        "app_client_id": "client-1",
        "cognito_domain": "example.com",
        "client_name": "zebra-day",
        "callback_url": "https://localhost:8443/auth/callback",
        "logout_url": "https://localhost:8443/",
    }
    monkeypatch.setattr(
        cognito_module,
        "ZebraDaySettings",
        SimpleNamespace(from_context=lambda: settings),
    )
    monkeypatch.setattr(cognito_module, "load_daycog_contract", lambda: dict(contract))
    monkeypatch.setattr(cognito_module, "get_context", lambda: SimpleNamespace(json_mode=False))

    cognito_module.status()
    status_out = capsys.readouterr().out
    assert "Cognito Contract" in status_out
    assert "Pool: pool-1" in status_out

    monkeypatch.setattr(cognito_module, "get_context", lambda: SimpleNamespace(json_mode=True))
    cognito_module.bind()
    assert json.loads(capsys.readouterr().out.strip()) == {
        "client_name": "zebra-day",
        "callback_url": "https://localhost:8443/auth/callback",
        "logout_url": "https://localhost:8443/",
    }

    monkeypatch.setattr(cognito_module, "get_context", lambda: SimpleNamespace(json_mode=False))
    cognito_module.import_context()
    import_out = capsys.readouterr().out
    assert "daycog config file" in import_out
    assert "Client name: zebra-day" in import_out

    cognito_module.validate()
    validate_out = capsys.readouterr().out
    assert "validation passed" in validate_out.lower()

    bad_contract = dict(
        contract, client_name="wrong-name", callback_url="https://localhost:9999/cb"
    )
    monkeypatch.setattr(cognito_module, "load_daycog_contract", lambda: dict(bad_contract))
    monkeypatch.setattr(cognito_module, "get_context", lambda: SimpleNamespace(json_mode=True))
    with pytest.raises(Exit):
        cognito_module.validate()
    invalid_payload = json.loads(capsys.readouterr().out.strip())
    assert invalid_payload["ok"] is False
    assert len(invalid_payload["issues"]) == 2

    class _Completed:
        def __init__(self, *, stdout: str, stderr: str = "", returncode: int = 0) -> None:
            self.stdout = stdout
            self.stderr = stderr
            self.returncode = returncode

    with pytest.raises(Exit):
        cognito_module.daycog_passthrough(SimpleNamespace(args=[]))
    missing_capture = capsys.readouterr()
    missing_out = missing_capture.out + missing_capture.err
    assert "Missing daycog arguments" in missing_out

    monkeypatch.setattr(
        cognito_module,
        "_run_daycog",
        lambda args: _Completed(stdout=f"ran {' '.join(args)}\n"),
    )
    cognito_module.daycog_passthrough(SimpleNamespace(args=["config", "status"]))
    passthrough_out = capsys.readouterr().out
    assert "ran config status" in passthrough_out

    monkeypatch.setattr(
        cognito_module,
        "_run_daycog",
        lambda args: _Completed(stdout="", stderr="boom", returncode=7),
    )
    with pytest.raises(Exit):
        cognito_module.daycog_passthrough(SimpleNamespace(args=["broken"]))
    failure_capture = capsys.readouterr()
    failure_out = failure_capture.out + failure_capture.err
    assert "boom" in failure_out


def test_printer_commands_cover_empty_list_live_scan_and_sync(monkeypatch, tmp_path, capsys):
    _set_xdg(monkeypatch, tmp_path)
    printers = [
        PrinterRecord(
            printer_id="printer-1",
            lab="default",
            ip_address="192.168.1.50",
            printer_name="Bench Printer",
            model="ZD620",
            serial="SER123",
            label_profiles=["tube"],
            default_label_profile="tube",
        )
    ]
    discovered = [
        PrinterRecord(
            printer_id="printer-9",
            lab="ops",
            ip_address="192.168.1.99",
            printer_name="Ops Printer",
            model="ZT411",
            serial="SER999",
            notes="zpl+http(18080)",
        )
    ]
    calls: dict[str, object] = {}

    class _FakeClient:
        def list_printers(self, lab=None):
            return [row for row in printers if lab is None or row.lab == lab]

        def discover_printers(self, *, ip_stub, lab, scan_http_port=None):
            calls["discover"] = (ip_stub, lab, scan_http_port)
            return discovered

        def sync_printer_metadata(self, printer_id, lab):
            calls["sync"] = (printer_id, lab)
            return discovered[0]

    monkeypatch.setattr(printer_module.ZebraDayClient, "from_context", lambda: _FakeClient())
    monkeypatch.setattr(
        printer_module,
        "get_cached_status",
        lambda ip, timeout=2.0: {"online": True, "paused": False, "paper_out": True},
    )
    monkeypatch.setattr(printer_module, "get_context", lambda: SimpleNamespace(json_mode=False))

    printer_module.list_printers(lab="missing", live=False, timeout=2.0)
    empty_capture = capsys.readouterr()
    empty_out = empty_capture.out + empty_capture.err
    assert "No printers found" in empty_out

    printer_module.list_printers(lab="default", live=True, timeout=2.0)
    listed_out = capsys.readouterr().out
    assert "default/printer-1  192.168.1.50" in listed_out
    assert "live_online=True" in listed_out
    assert "paper_out=True" in listed_out

    monkeypatch.setattr(printer_module, "get_context", lambda: SimpleNamespace(json_mode=True))
    printer_module.scan(lab="ops", ip_stub="192.168.1", scan_http_port=18080)
    scanned_payload = json.loads(capsys.readouterr().out.strip())
    assert scanned_payload[0]["printer_id"] == "printer-9"
    assert calls["discover"] == ("192.168.1", "ops", 18080)

    printer_module.sync(lab="ops", printer_id="printer-9")
    synced_payload = json.loads(capsys.readouterr().out.strip())
    assert synced_payload["serial"] == "SER999"
    assert calls["sync"] == ("printer-9", "ops")


def test_template_commands_cover_save_show_list_delete_and_preview(monkeypatch, tmp_path, capsys):
    _set_xdg(monkeypatch, tmp_path)

    class _FakeClient:
        def __init__(self) -> None:
            self.templates: dict[str, dict[str, str]] = {}
            self.deleted: list[str] = []

        def list_templates(self):
            return sorted(self.templates)

        def get_template(self, template_name):
            return self.templates.get(template_name)

        def save_template(self, template_name, zpl_content, source="user"):
            self.templates[template_name] = {
                "template_name": template_name,
                "zpl_content": zpl_content,
                "source": source,
            }

        def delete_template(self, template_name):
            self.deleted.append(template_name)
            self.templates.pop(template_name, None)

        def render_label(self, template, uid_barcode):
            return "^XA^XZ", f"/preview/{template}/{uid_barcode or 'blank'}.png"

    fake_client = _FakeClient()
    monkeypatch.setattr(template_module.ZebraDayClient, "from_context", lambda: fake_client)
    monkeypatch.setattr(template_module, "get_context", lambda: SimpleNamespace(json_mode=False))

    template_module.list_templates()
    empty_capture = capsys.readouterr()
    empty_out = empty_capture.out + empty_capture.err
    assert "No templates found" in empty_out

    template_file = tmp_path / "tube.zpl"
    template_file.write_text("^XA^FDTEST^XZ", encoding="utf-8")
    template_module.save(filename="tube.zpl", content=str(template_file))
    save_out = capsys.readouterr().out
    assert "Saved template: tube" in save_out
    assert fake_client.templates["tube"]["zpl_content"] == "^XA^FDTEST^XZ"

    template_module.list_templates()
    listed_out = capsys.readouterr().out
    assert "tube" in listed_out

    template_module.show(template_name="tube")
    show_out = capsys.readouterr().out
    assert "^XA^FDTEST^XZ" in show_out

    with pytest.raises(Exit):
        template_module.show(template_name="missing")
    missing_capture = capsys.readouterr()
    missing_out = missing_capture.out + missing_capture.err
    assert "Template not found: missing" in missing_out

    monkeypatch.setattr(template_module, "get_context", lambda: SimpleNamespace(json_mode=True))
    template_module.preview(template_name="tube", uid_barcode="UID-1")
    preview_payload = json.loads(capsys.readouterr().out.strip())
    assert preview_payload["png_url"] == "/preview/tube/UID-1.png"

    monkeypatch.setattr(template_module.typer, "confirm", lambda message: False)
    with pytest.raises(Abort):
        template_module.delete(template_name="tube", force=False)
    capsys.readouterr()
    assert "tube" in fake_client.templates

    template_module.delete(template_name="tube", force=True)
    delete_out = capsys.readouterr().out
    assert "Deleted template: tube" in delete_out
    assert fake_client.deleted == ["tube"]


def test_logs_commands_cover_present_and_missing_logs(monkeypatch, tmp_path, capsys):
    _set_xdg(monkeypatch, tmp_path)
    settings = _settings(tmp_path)
    log_one = settings.logs_dir / "gui_20260405_010101.log"
    log_two = settings.logs_dir / "gui_20260405_020202.log"
    log_one.write_text("a\nb\n", encoding="utf-8")
    log_two.write_text("1\n2\n3\n", encoding="utf-8")
    monkeypatch.setattr(
        logs_module, "ZebraDaySettings", SimpleNamespace(from_context=lambda: settings)
    )

    logs_module.path()
    path_out = capsys.readouterr().out.replace("\n", "")
    assert str(settings.logs_dir) in path_out

    logs_module.latest()
    latest_out = capsys.readouterr().out.replace("\n", "")
    assert str(log_two) in latest_out

    logs_module.show(lines=2)
    shown_out = capsys.readouterr().out.strip()
    assert shown_out == "2\n3"

    empty_settings = _settings(tmp_path / "empty")
    monkeypatch.setattr(
        logs_module,
        "ZebraDaySettings",
        SimpleNamespace(from_context=lambda: empty_settings),
    )
    with pytest.raises(Exit):
        logs_module.latest()
    missing_capture = capsys.readouterr()
    missing_out = missing_capture.out + missing_capture.err
    assert "No GUI logs found" in missing_out


def test_root_status_and_bootstrap_cover_success_and_error(monkeypatch, tmp_path, capsys):
    _set_xdg(monkeypatch, tmp_path)
    status_settings = _settings(tmp_path / "status")
    status_settings.config_path.parent.mkdir(parents=True, exist_ok=True)
    status_settings.config_path.write_text("service: {}\n", encoding="utf-8")
    status_settings.tapdb_config_path.write_text("tapdb: {}\n", encoding="utf-8")
    (status_settings.state_dir / "gui.pid").write_text("43210", encoding="utf-8")

    bootstrap_settings = _settings(tmp_path / "bootstrap")
    bootstrap_settings.tapdb_config_path.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_settings.tapdb_config_path.write_text("tapdb: {}\n", encoding="utf-8")
    bootstrap_settings.config_path.parent.mkdir(parents=True, exist_ok=True)

    class _Client:
        def __init__(self, settings):
            self.settings = settings

        def list_labs(self):
            return ["default", "ops"]

        def list_printers(self):
            return [object(), object()]

        def list_templates(self):
            return ["tube", "rack"]

        def list_label_profiles(self):
            return ["tube"]

        def discover_printers(self, *, ip_stub, lab):
            assert ip_stub == "192.168.50"
            assert lab == "ops"
            return [
                PrinterRecord(
                    printer_id="printer-9",
                    lab=lab,
                    ip_address="192.168.50.9",
                    model="ZT411",
                    serial="SER009",
                )
            ]

    monkeypatch.setattr(config_extra_module, "ZebraDayClient", _Client)
    monkeypatch.setattr(
        config_extra_module,
        "build_default_config_template",
        lambda deployment: f"deployment: {deployment}\n".encode(),
    )

    monkeypatch.setattr(
        config_extra_module,
        "ZebraDaySettings",
        SimpleNamespace(from_context=lambda: status_settings),
    )
    monkeypatch.setattr(config_extra_module, "get_context", lambda: SimpleNamespace(json_mode=True))
    config_extra_module._status()
    status_payload = json.loads(capsys.readouterr().out.strip())
    assert status_payload["deployment_code"] == "local"
    assert status_payload["gui"]["pid"] == 43210
    assert status_payload["fleet"]["printer_count"] == 2

    class _BrokenClient:
        def __init__(self, settings):
            raise RuntimeError("tapdb offline")

    monkeypatch.setattr(config_extra_module, "ZebraDayClient", _BrokenClient)
    monkeypatch.setattr(
        config_extra_module, "get_context", lambda: SimpleNamespace(json_mode=False)
    )
    with pytest.raises(Exit):
        config_extra_module._status()
    failed_capture = capsys.readouterr()
    failed_out = failed_capture.out + failed_capture.err
    assert "TapDB unavailable: tapdb offline" in failed_out

    monkeypatch.setattr(
        config_extra_module,
        "ZebraDaySettings",
        SimpleNamespace(from_context=lambda: bootstrap_settings),
    )
    monkeypatch.setattr(config_extra_module, "ZebraDayClient", _Client)
    monkeypatch.setattr(config_extra_module, "get_context", lambda: SimpleNamespace(json_mode=True))
    config_extra_module._bootstrap(ip_stub="192.168.50", lab="ops", skip_scan=False)
    bootstrap_payload = json.loads(capsys.readouterr().out.strip())
    assert bootstrap_payload["config_created"] is True
    assert bootstrap_payload["discovered_printers"][0]["serial"] == "SER009"
    assert bootstrap_settings.config_path.read_text(encoding="utf-8") == "deployment: local\n"


def test_simulator_cli_start_stop_list_and_errors(monkeypatch, tmp_path, capsys):
    _set_xdg(monkeypatch, tmp_path)

    class _Manager:
        def __init__(self) -> None:
            self.printers = [
                {
                    "model": "ZD620",
                    "serial": "SIM1001",
                    "host": "127.0.0.1",
                    "zpl_port": 9100,
                    "http_port": 18080,
                    "running": True,
                }
            ]
            self.started: list[dict[str, object]] = []

        def start_printer(self, **kwargs):
            self.started.append(kwargs)

        def stop_printer(self, host, zpl_port):
            return host == "127.0.0.1" and zpl_port == 9100

        def stop_all(self):
            return 1

        def list_printers(self):
            return list(self.printers)

    manager = _Manager()
    monkeypatch.setattr(simulator_cli_module, "_get_manager", lambda: manager)

    simulator_cli_module.sim_start(
        host="127.0.0.1",
        zpl_port=9100,
        http_port=18080,
        model="ZT411",
        serial="SIM9000",
        firmware="V1",
        ribbon_out=False,
        head_up=False,
        paused=False,
        paper_out=True,
        foreground=False,
    )
    started_out = capsys.readouterr().out
    assert "Simulator started: ZT411" in started_out
    assert manager.started[0]["profile"].paper_out is True

    simulator_cli_module.sim_list()
    listed_out = capsys.readouterr().out
    assert "SIM1001" in listed_out

    simulator_cli_module.sim_stop(host="127.0.0.1", zpl_port=9100, all_printers=False)
    stopped_out = capsys.readouterr().out
    assert "Stopped simulator at 127.0.0.1:9100" in stopped_out

    simulator_cli_module.sim_stop(host="127.0.0.2", zpl_port=9101, all_printers=False)
    missing_capture = capsys.readouterr()
    missing_out = missing_capture.out + missing_capture.err
    assert "No simulator found at 127.0.0.2:9101" in missing_out

    simulator_cli_module.sim_stop(all_printers=True)
    stopped_all_out = capsys.readouterr().out
    assert "Stopped 1 simulator(s)" in stopped_all_out

    class _RuntimeErrorManager(_Manager):
        def start_printer(self, **kwargs):
            raise RuntimeError("already running")

    monkeypatch.setattr(simulator_cli_module, "_get_manager", lambda: _RuntimeErrorManager())
    with pytest.raises(Exit):
        simulator_cli_module.sim_start(
            host="127.0.0.1",
            zpl_port=9100,
            http_port=18080,
            model="ZT411",
            serial="SIM9000",
            firmware="V1",
            paper_out=False,
            ribbon_out=False,
            head_up=False,
            paused=False,
            foreground=False,
        )
    runtime_error_capture = capsys.readouterr()
    runtime_error_out = runtime_error_capture.out + runtime_error_capture.err
    assert "already running" in runtime_error_out

    class _OSErrorManager(_Manager):
        def start_printer(self, **kwargs):
            raise OSError("Address already in use")

    monkeypatch.setattr(simulator_cli_module, "_get_manager", lambda: _OSErrorManager())
    with pytest.raises(Exit):
        simulator_cli_module.sim_start(
            host="127.0.0.1",
            zpl_port=9100,
            http_port=18080,
            model="ZT411",
            serial="SIM9000",
            firmware="V1",
            paper_out=False,
            ribbon_out=False,
            head_up=False,
            paused=False,
            foreground=False,
        )
    os_error_capture = capsys.readouterr()
    os_error_out = os_error_capture.out + os_error_capture.err
    assert "Cannot bind" in os_error_out


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("^XA^FO10,10^FDINLINE^XZ", "^XA^FO10,10^FDINLINE^XZ"),
        ("not-a-path", "not-a-path"),
    ],
)
def test_template_read_template_source_handles_inline_values(text, expected):
    assert template_module._read_template_source(text) == expected
