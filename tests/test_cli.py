from __future__ import annotations

import importlib
import sys
from types import ModuleType, SimpleNamespace

from typer.testing import CliRunner

import zebra_day.cli as zebra_cli

runner = CliRunner()


def _set_xdg(monkeypatch, tmp_path, deployment="local") -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("ZEBRA_DAY_DEPLOYMENT_CODE", deployment)
    monkeypatch.setenv("CONDA_DEFAULT_ENV", f"ZEBRA_DAY-{deployment}")
    monkeypatch.setenv("CONDA_PREFIX", str(tmp_path / "conda" / deployment))
    monkeypatch.delenv("ZEBRA_DAY_CONFIG_PATH", raising=False)


def test_config_path_uses_deployment_scoped_filename(monkeypatch, tmp_path):
    _set_xdg(monkeypatch, tmp_path, deployment="qa-1")
    cli_module = importlib.reload(zebra_cli)
    result = runner.invoke(cli_module.app, ["config", "path"])
    assert result.exit_code == 0
    assert "zebra-day-config-qa-1.yaml" in result.output.replace("\n", "")


def test_root_no_auth_updates_effective_auth_mode(monkeypatch, tmp_path):
    _set_xdg(monkeypatch, tmp_path, deployment="local")

    class _FakeClient:
        def __init__(self, settings):
            del settings

        def list_labs(self):
            return ["default"]

        def list_printers(self):
            return [object()]

        def list_templates(self):
            return ["tube_2inX1in"]

        def list_label_profiles(self):
            return ["tube_2inX1in"]

    monkeypatch.setattr("zebra_day.cli.config_extra.ZebraDayClient", _FakeClient)

    result = runner.invoke(zebra_cli.app, ["--no-auth", "config", "status"])

    assert result.exit_code == 0
    assert "Auth mode: none" in result.output


def test_dynamo_command_is_removed():
    result = runner.invoke(zebra_cli.app, ["dynamo"])
    assert result.exit_code != 0
    assert "No such command" in result.output


def test_tapdb_passthrough_uses_runtime_namespace(monkeypatch, tmp_path):
    _set_xdg(monkeypatch, tmp_path, deployment="dev1")
    monkeypatch.setenv("CONDA_DEFAULT_ENV", "ZEBRA_DAY-dev1")
    monkeypatch.setenv("CONDA_PREFIX", str(tmp_path / "conda" / "dev1"))
    config_path = tmp_path / "config" / "zebra_day" / "zebra-day-config-dev1.yaml"
    tapdb_config_path = tmp_path / "tapdb" / "zebra-day" / "zebra-day-dev1" / "tapdb-config.yaml"
    domain_registry_path = tmp_path / "tapdb-registry" / "domain_code_registry.json"
    prefix_registry_path = tmp_path / "tapdb-registry" / "prefix_ownership_registry.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        (
            "tapdb:\n"
            f"  config_path: {tapdb_config_path}\n"
            f"  domain_registry_path: {domain_registry_path}\n"
            f"  prefix_ownership_registry_path: {prefix_registry_path}\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setitem(sys.modules, "daylily_tapdb", ModuleType("daylily_tapdb"))
    recorded: dict[str, object] = {}

    class _Completed:
        returncode = 0
        stdout = "ok\n"
        stderr = ""

    def fake_run(cmd, env, capture_output, text):
        assert all(isinstance(part, str) for part in cmd)
        recorded["cmd"] = cmd
        recorded["env"] = env
        return _Completed()

    monkeypatch.setattr("zebra_day.cli.tapdb.subprocess", SimpleNamespace(run=fake_run))

    result = runner.invoke(zebra_cli.app, ["tapdb", "db", "status"])

    assert result.exit_code == 0
    assert recorded["cmd"] == [
        "tapdb",
        "--config",
        str(tapdb_config_path),
        "--env",
        "dev",
        "db",
        "status",
    ]
    assert recorded["env"]["MERIDIAN_DOMAIN_CODE"] == "Z"
    assert recorded["env"]["TAPDB_OWNER_REPO"] == "zebra-day"
    assert recorded["env"]["TAPDB_DOMAIN_CODE"] == "Z"
    assert recorded["env"]["TAPDB_DOMAIN_REGISTRY_PATH"] == str(domain_registry_path)
    assert recorded["env"]["TAPDB_PREFIX_REGISTRY_PATH"] == str(prefix_registry_path)
    assert "ok" in result.output


def test_bootstrap_local_initializes_namespace_config_before_bootstrap(monkeypatch, tmp_path):
    _set_xdg(monkeypatch, tmp_path, deployment="dev1")
    config_path = tmp_path / "config" / "zebra_day" / "zebra-day-config-dev1.yaml"
    tapdb_config_path = tmp_path / "tapdb" / "zebra-day" / "zebra-day-dev1" / "tapdb-config.yaml"
    domain_registry_path = tmp_path / "tapdb-registry" / "domain_code_registry.json"
    prefix_registry_path = tmp_path / "tapdb-registry" / "prefix_ownership_registry.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        (
            "tapdb:\n"
            f"  config_path: {tapdb_config_path}\n"
            f"  domain_registry_path: {domain_registry_path}\n"
            f"  prefix_ownership_registry_path: {prefix_registry_path}\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setitem(sys.modules, "daylily_tapdb", ModuleType("daylily_tapdb"))
    commands: list[list[str]] = []

    class _Completed:
        returncode = 0
        stdout = "ok\n"
        stderr = ""

    def fake_run(cmd, env, capture_output, text):
        assert all(isinstance(part, str) for part in cmd)
        commands.append(cmd)
        return _Completed()

    monkeypatch.setattr("zebra_day.cli.tapdb.subprocess", SimpleNamespace(run=fake_run))

    result = runner.invoke(zebra_cli.app, ["tapdb", "bootstrap", "local", "--no-gui"])
    assert result.exit_code == 0
    assert tapdb_config_path.parent.is_dir()
    assert commands == [
        [
            "tapdb",
            "--config",
            str(tapdb_config_path),
            "db-config",
            "init",
            "--client-id",
            "zebra-day",
            "--database-name",
            "zebra-day-dev1",
            "--owner-repo-name",
            "zebra-day",
            "--domain-code",
            "dev=Z",
            "--domain-registry-path",
            str(domain_registry_path),
            "--prefix-ownership-registry-path",
            str(prefix_registry_path),
            "--env",
            "dev",
            "--db-port",
            "dev=5544",
            "--ui-port",
            "dev=8118",
        ],
        [
            "tapdb",
            "--config",
            str(tapdb_config_path),
            "--client-id",
            "zebra-day",
            "--database-name",
            "zebra-day-dev1",
            "db-config",
            "update",
            "--env",
            "dev",
            "--owner-repo-name",
            "zebra-day",
            "--domain-code",
            "Z",
            "--domain-registry-path",
            str(domain_registry_path),
            "--prefix-ownership-registry-path",
            str(prefix_registry_path),
            "--engine-type",
            "local",
            "--host",
            "localhost",
            "--port",
            "5544",
            "--ui-port",
            "8118",
            "--database",
            "zebra-day-dev1",
        ],
        [
            "tapdb",
            "--config",
            str(tapdb_config_path),
            "--env",
            "dev",
            "bootstrap",
            "local",
            "--no-gui",
        ],
    ]


def test_bootstrap_requires_tapdb_config(monkeypatch, tmp_path):
    _set_xdg(monkeypatch, tmp_path, deployment="local")

    result = runner.invoke(zebra_cli.app, ["config", "bootstrap", "--skip-scan"])

    assert result.exit_code == 1
    assert "TapDB config is required." in result.output
