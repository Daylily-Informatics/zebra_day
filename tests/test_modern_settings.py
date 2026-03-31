from zebra_day import paths as xdg
from zebra_day.settings import ZebraDaySettings, build_default_config_template, validate_settings_yaml


def test_deployment_scoped_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("ZEBRA_DAY_DEPLOYMENT_CODE", "qa-1")

    assert xdg.get_app_dir_name() == "zebra-day-qa-1"
    assert xdg.get_config_filename() == "zebra-day-config-qa-1.yaml"
    assert xdg.get_config_file_path() == tmp_path / "config" / "zebra-day-qa-1" / "zebra-day-config-qa-1.yaml"


def test_default_config_template_is_valid_yaml():
    content = build_default_config_template("dev").decode("utf-8")
    assert validate_settings_yaml(content) == []
    assert "database_name: zebra-day-dev" in content
    assert "zebra-day-admin: ADMIN" in content


def test_settings_from_context_uses_deployment(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("ZEBRA_DAY_DEPLOYMENT_CODE", "stage")
    monkeypatch.delenv("TAPDB_DATABASE_NAME", raising=False)

    settings = ZebraDaySettings.from_context()
    assert settings.deployment_code == "stage"
    assert settings.tapdb_database_name == "zebra-day-stage"
    assert settings.config_path.name == "zebra-day-config-stage.yaml"
    assert settings.cognito_group_role_map["zebra-day-operator"] == "OPERATOR"
