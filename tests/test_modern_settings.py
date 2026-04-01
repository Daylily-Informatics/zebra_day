from __future__ import annotations

from pathlib import Path

import yaml

from zebra_day import paths as xdg
from zebra_day.settings import (
    ZebraDaySettings,
    build_default_config_template,
    validate_settings_yaml,
)


def _set_xdg(monkeypatch, tmp_path, deployment="stage-1") -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("ZEBRA_DAY_DEPLOYMENT_CODE", deployment)


def test_default_config_template_is_valid_yaml():
    content = build_default_config_template("dev").decode("utf-8")
    assert validate_settings_yaml(content) == []
    assert "database_name: zebra-day-dev" in content
    assert "zebra-day-admin: ADMIN" in content


def test_settings_from_context_uses_env_paths(monkeypatch, tmp_path):
    _set_xdg(monkeypatch, tmp_path, deployment="qa-1")
    explicit_config = tmp_path / "custom" / "zebra-day-config-qa-1.yaml"
    monkeypatch.setenv("ZEBRA_DAY_CONFIG_PATH", str(explicit_config))

    settings = ZebraDaySettings.from_context()

    assert settings.deployment_code == "qa-1"
    assert settings.config_path == explicit_config
    assert settings.tapdb_database_name == "zebra-day-qa-1"
    assert (
        settings.tapdb_config_path
        == Path.home() / ".config" / "tapdb" / "zebra-day" / "zebra-day-qa-1" / "tapdb-config.yaml"
    )


def test_settings_merge_file_values(monkeypatch, tmp_path):
    _set_xdg(monkeypatch, tmp_path, deployment="prodx")
    config_path = xdg.get_config_file_path()
    config_path.write_text(
        (
            "service:\n"
            "  host: localhost\n"
            "  port: 8119\n"
            "authentication:\n"
            "  mode: none\n"
            "tapdb:\n"
            "  client_id: zebra-day\n"
            "  database_name: zebra-day-prod-custom\n"
            "  env: sandbox\n"
        ),
        encoding="utf-8",
    )

    settings = ZebraDaySettings.from_context()

    assert settings.host == "localhost"
    assert settings.port == 8119
    assert settings.auth_mode == "none"
    assert settings.tapdb_database_name == "zebra-day-prod-custom"
    assert settings.tapdb_env == "sandbox"


def test_repo_ships_tapdb_config_template():
    template_path = Path("config/tapdb-config-zebra-day.yaml")
    payload = yaml.safe_load(template_path.read_text(encoding="utf-8"))

    assert template_path.is_file()
    assert payload["meta"]["client_id"] == "zebra-day"
    assert payload["meta"]["database_name"] == "zebra-day"
    assert payload["environments"]["dev"]["port"] == "5544"
    assert payload["environments"]["dev"]["database"] == "zebra_day_dev"
    assert payload["environments"]["dev"]["audit_log_euid_prefix"] == "ZGX"
    assert payload["environments"]["prod"]["audit_log_euid_prefix"] == "ZGX"


def test_repo_ships_single_zebra_day_template_prefix():
    template_pack = yaml.safe_load(
        Path("config/tapdb_templates/zebra_day/templates.json").read_text(encoding="utf-8")
    )
    prefixes = {template["instance_prefix"] for template in template_pack["templates"]}
    assert prefixes == {"ZGX"}
