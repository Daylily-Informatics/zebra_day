from __future__ import annotations

from pathlib import Path

import yaml

from zebra_day import paths as xdg
from zebra_day.settings import (
    DEFAULT_DEPLOYMENT_BANNER_COLOR,
    ZebraDaySettings,
    _resolve_deployment_chrome,
    _stable_deployment_color_hex,
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
    monkeypatch.delenv("ZEBRA_DAY_CONFIG_PATH", raising=False)


def test_default_config_template_is_valid_yaml():
    content = build_default_config_template("dev").decode("utf-8")
    payload = yaml.safe_load(content)
    assert validate_settings_yaml(content) == []
    assert "database_name: zebra-day-dev" in content
    assert "zebra-day-admin: ADMIN" in content
    assert "deployment:" in content
    assert payload["authentication"]["session_secret_key"]
    assert payload["authentication"]["allowed_email_domains"] == [
        "lsmc.com",
        "lsmc.bio",
        "lsmc.life",
        "daylilyinformatics.com",
    ]
    assert payload["authentication"]["default_tenant_id"] == "00000000-0000-0000-0000-000000000000"
    assert payload["authentication"]["auto_provision_allowed_domains"] == ["lsmc.com"]
    assert payload["ui"]["show_environment_chrome"] is True


def test_deployment_color_vectors_match_the_canonical_contract():
    assert _stable_deployment_color_hex("510x2") == "#4321ca"
    assert _stable_deployment_color_hex("inflec3") == "#7521ca"
    assert _stable_deployment_color_hex("production") == "#ca2183"


def test_settings_from_context_uses_env_paths(monkeypatch, tmp_path):
    _set_xdg(monkeypatch, tmp_path, deployment="qa-1")
    explicit_config = tmp_path / "custom" / "zebra-day-config-qa-1.yaml"
    monkeypatch.setenv("ZEBRA_DAY_CONFIG_PATH", str(explicit_config))

    settings = ZebraDaySettings.from_context()

    assert settings.deployment_code == "qa-1"
    assert settings.deployment_name == "qa-1"
    assert settings.deployment_color == _stable_deployment_color_hex("qa-1")
    assert settings.deployment_is_production is False
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
            "deployment:\n"
            "  name: sandbox-g\n"
            "  color: '#123456'\n"
        ),
        encoding="utf-8",
    )

    settings = ZebraDaySettings.from_context()

    assert settings.host == "localhost"
    assert settings.port == 8119
    assert settings.auth_mode == "none"
    assert settings.session_secret_key
    assert settings.allowed_email_domains == [
        "lsmc.com",
        "lsmc.bio",
        "lsmc.life",
        "daylilyinformatics.com",
    ]
    assert settings.cognito_default_tenant_id == "00000000-0000-0000-0000-000000000000"
    assert settings.cognito_auto_provision_allowed_domains == ["lsmc.com"]
    assert settings.tapdb_database_name == "zebra-day-prod-custom"
    assert settings.tapdb_env == "sandbox"
    assert settings.ui_show_environment_chrome is True
    assert settings.deployment == {
        "name": "sandbox-g",
        "color": "#123456",
        "is_production": False,
    }


def test_prod_deployment_name_hides_banner(monkeypatch, tmp_path):
    _set_xdg(monkeypatch, tmp_path, deployment="qa-1")
    config_path = xdg.get_config_file_path()
    config_path.write_text(
        "deployment:\n  name: production\n  color: ''\n",
        encoding="utf-8",
    )

    settings = ZebraDaySettings.from_context()

    assert settings.deployment == {
        "name": "production",
        "color": _stable_deployment_color_hex("production"),
        "is_production": True,
    }


def test_light_aqua_is_used_without_any_deployment_name():
    assert _resolve_deployment_chrome(name="", color="", fallback_name="") == {
        "name": "",
        "color": DEFAULT_DEPLOYMENT_BANNER_COLOR,
        "is_production": False,
    }


def test_repo_ships_tapdb_config_template():
    template_path = Path("config/tapdb-config-zebra-day.yaml")
    payload = yaml.safe_load(template_path.read_text(encoding="utf-8"))

    assert template_path.is_file()
    assert payload["meta"]["config_version"] == 3
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
