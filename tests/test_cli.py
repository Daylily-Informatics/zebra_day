from __future__ import annotations

import importlib
from types import SimpleNamespace

from typer.testing import CliRunner
import yaml

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


def _set_explicit_tapdb_contract(monkeypatch, tmp_path, deployment="local"):
    tapdb_config_path = tmp_path / "tapdb" / deployment / "tapdb-config.yaml"
    domain_registry_path = tmp_path / "tapdb" / "domain_code_registry.json"
    prefix_registry_path = tmp_path / "tapdb" / "prefix_ownership_registry.json"
    monkeypatch.setenv("DAYHOFF_TAPDB_CONFIG_PATH", str(tapdb_config_path))
    monkeypatch.setenv("DAYHOFF_TAPDB_DOMAIN_REGISTRY_PATH", str(domain_registry_path))
    monkeypatch.setenv("DAYHOFF_TAPDB_PREFIX_REGISTRY_PATH", str(prefix_registry_path))
    return tapdb_config_path, domain_registry_path, prefix_registry_path


def test_config_path_uses_deployment_scoped_filename(monkeypatch, tmp_path):
    _set_xdg(monkeypatch, tmp_path, deployment="qa-1")
    cli_module = importlib.reload(zebra_cli)
    result = runner.invoke(cli_module.app, ["config", "path"])
    assert result.exit_code == 0
    assert "zebra-day-config-qa-1.yaml" in result.output.replace("\n", "")


def test_root_no_auth_updates_effective_auth_mode(monkeypatch, tmp_path):
    _set_xdg(monkeypatch, tmp_path, deployment="local")
    _set_explicit_tapdb_contract(monkeypatch, tmp_path, deployment="local")

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
    explicit_tapdb_config, explicit_domain_registry, explicit_prefix_registry = (
        _set_explicit_tapdb_contract(monkeypatch, tmp_path, deployment="dev1")
    )
    recorded: dict[str, object] = {}

    class _Completed:
        returncode = 0
        stdout = "ok\n"
        stderr = ""

    def fake_run(cmd, env, capture_output, text):
        recorded["cmd"] = cmd
        recorded["env"] = env
        return _Completed()

    monkeypatch.setattr("zebra_day.cli.tapdb.subprocess", SimpleNamespace(run=fake_run))

    result = runner.invoke(zebra_cli.app, ["tapdb", "db", "status"])

    assert result.exit_code == 0
    assert recorded["cmd"] == [
        "tapdb",
        "--config",
        str(explicit_tapdb_config),
        "--env",
        "dev",
        "db",
        "status",
    ]
    assert recorded["env"]["MERIDIAN_DOMAIN_CODE"] == "Z"
    assert recorded["env"]["TAPDB_OWNER_REPO"] == "zebra-day"
    assert recorded["env"]["TAPDB_DOMAIN_CODE"] == "Z"
    assert recorded["env"]["TAPDB_DOMAIN_REGISTRY_PATH"] == str(explicit_domain_registry)
    assert recorded["env"]["TAPDB_PREFIX_REGISTRY_PATH"] == str(explicit_prefix_registry)
    assert "ok" in result.output


def test_bootstrap_local_initializes_namespace_config_before_bootstrap(monkeypatch, tmp_path):
    _set_xdg(monkeypatch, tmp_path, deployment="dev1")
    explicit_tapdb_config, _unused_domain_registry, _unused_prefix_registry = (
        _set_explicit_tapdb_contract(monkeypatch, tmp_path, deployment="dev1")
    )
    dayhoff_domain_registry = tmp_path / "dayhoff" / "domain_code_registry.json"
    dayhoff_prefix_registry = tmp_path / "dayhoff" / "prefix_ownership_registry.json"
    dayhoff_domain_registry.parent.mkdir(parents=True, exist_ok=True)
    dayhoff_domain_registry.write_text(
        '{"version":"0.4.0","domains":{"Z":{"name":"localhost"}}}\n',
        encoding="utf-8",
    )
    dayhoff_prefix_registry.write_text(
        '{"version":"0.4.0","ownership":{"Z":{}}}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv(
        "DAYHOFF_TAPDB_DOMAIN_REGISTRY_PATH",
        str(dayhoff_domain_registry),
    )
    monkeypatch.setenv(
        "DAYHOFF_TAPDB_PREFIX_REGISTRY_PATH",
        str(dayhoff_prefix_registry),
    )
    commands: list[list[str]] = []

    class _Completed:
        returncode = 0
        stdout = "ok\n"
        stderr = ""

    def fake_run(cmd, env, capture_output, text):
        commands.append(cmd)
        return _Completed()

    monkeypatch.setattr("zebra_day.cli.tapdb.subprocess", SimpleNamespace(run=fake_run))

    result = runner.invoke(zebra_cli.app, ["tapdb", "bootstrap", "local", "--no-gui"])

    expected_config_path = explicit_tapdb_config
    assert result.exit_code == 0
    assert expected_config_path.parent.is_dir()
    payload = yaml.safe_load(expected_config_path.read_text(encoding="utf-8"))
    assert payload["meta"] == {
        "config_version": 3,
        "client_id": "zebra-day",
        "database_name": "zebra-day-dev1",
        "owner_repo_name": "zebra-day",
        "domain_code": "Z",
        "domain_registry_path": str(dayhoff_domain_registry),
        "prefix_ownership_registry_path": str(dayhoff_prefix_registry),
    }
    assert payload["environments"]["dev"]["engine_type"] == "local"
    assert payload["environments"]["dev"]["port"] == "5544"
    assert payload["environments"]["dev"]["ui_port"] == "8118"
    assert payload["environments"]["dev"]["database"] == "zebra_day_dev"
    assert payload["environments"]["dev"]["audit_log_euid_prefix"] == "ZGX"
    assert commands == [[
            "tapdb",
            "--config",
            str(expected_config_path),
            "--env",
            "dev",
            "bootstrap",
            "local",
            "--no-gui",
        ]]


def test_bootstrap_requires_tapdb_config(monkeypatch, tmp_path):
    _set_xdg(monkeypatch, tmp_path, deployment="local")

    result = runner.invoke(zebra_cli.app, ["config", "bootstrap", "--skip-scan"])

    assert result.exit_code == 1
    assert "TapDB config is required." in result.output
