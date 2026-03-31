from typer.testing import CliRunner

from zebra_day.cli import app

runner = CliRunner()


def test_config_path_uses_deployment_scoped_filename(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    result = runner.invoke(app, ["config", "path"])
    assert result.exit_code == 0
    assert "zebra-day-config-local.yaml" in result.output


def test_env_activate_points_to_activate_script():
    result = runner.invoke(app, ["env", "activate"])
    assert result.exit_code == 0
    assert "source activate" in result.output
