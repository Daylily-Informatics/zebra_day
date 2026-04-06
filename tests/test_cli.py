from __future__ import annotations

import importlib

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
    recorded: dict[str, object] = {}

    class _Completed:
        returncode = 0
        stdout = "ok\n"
        stderr = ""

    def fake_run(cmd, capture_output, text):
        recorded["cmd"] = cmd
        return _Completed()

    monkeypatch.setattr("zebra_day.cli.tapdb.subprocess.run", fake_run)

    result = runner.invoke(zebra_cli.app, ["tapdb", "db", "status"])

    assert result.exit_code == 0
    assert recorded["cmd"] == [
        "tapdb",
        "--config",
        str(
            tmp_path
            / "home"
            / ".config"
            / "tapdb"
            / "zebra-day"
            / "zebra-day-dev1"
            / "tapdb-config.yaml"
        ),
        "--env",
        "dev",
        "db",
        "status",
    ]
    assert "ok" in result.output


def test_bootstrap_requires_tapdb_config(monkeypatch, tmp_path):
    _set_xdg(monkeypatch, tmp_path, deployment="local")

    result = runner.invoke(zebra_cli.app, ["config", "bootstrap", "--skip-scan"])

    assert result.exit_code == 1
    assert "TapDB config is required." in result.output
