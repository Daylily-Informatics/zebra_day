from __future__ import annotations

from pathlib import Path

import pytest
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

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _set_xdg(monkeypatch, tmp_path, deployment="stage-1") -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("ZEBRA_DAY_DEPLOYMENT_CODE", deployment)
    monkeypatch.setenv("CONDA_DEFAULT_ENV", f"ZEBRA_DAY-{deployment}")
    monkeypatch.delenv("ZEBRA_DAY_CONFIG_PATH", raising=False)


def test_default_config_template_is_valid_yaml():
    content = build_default_config_template("dev").decode("utf-8")
    payload = yaml.safe_load(content)
    assert validate_settings_yaml(content) == []
    assert "database_name: zebra-day-dev" in content
    assert "zebra-day-admin: ADMIN" in content
    assert "deployment:" in content
    assert payload["authentication"]["session_secret_key"]
    assert payload["authentication"]["cognito_region"] == ""
    assert payload["authentication"]["cognito_user_pool_id"] == ""
    assert payload["authentication"]["cognito_app_client_id"] == ""
    assert payload["authentication"]["cognito_domain"] == ""
    assert payload["authentication"]["allowed_email_domains"] == [
        "lsmc.com",
        "lsmc.bio",
        "lsmc.life",
        "daylilyinformatics.com",
    ]
    assert payload["authentication"]["default_tenant_id"] == "00000000-0000-0000-0000-000000000000"
    assert payload["authentication"]["auto_provision_allowed_domains"] == ["lsmc.com"]
    assert payload["tapdb"]["owner_repo_name"] == "zebra-day"
    assert payload["tapdb"]["domain_code"] == "Z"
    assert isinstance(payload["tapdb"]["config_path"], str) and payload["tapdb"]["config_path"]
    assert isinstance(payload["tapdb"]["domain_registry_path"], str)
    assert isinstance(payload["tapdb"]["prefix_ownership_registry_path"], str)
    assert payload["ui"]["show_environment_chrome"] is True


def test_deployment_color_vectors_match_the_canonical_contract():
    assert _stable_deployment_color_hex("510x2") == "#4321ca"
    assert _stable_deployment_color_hex("inflec3") == "#7521ca"
    assert _stable_deployment_color_hex("production") == "#ca2183"


def test_settings_from_context_uses_env_paths(monkeypatch, tmp_path):
    _set_xdg(monkeypatch, tmp_path, deployment="qa-1")
    explicit_config = tmp_path / "custom" / "zebra-day-config-qa-1.yaml"
    monkeypatch.setenv("ZEBRA_DAY_CONFIG_PATH", str(explicit_config))
    tapdb_config_path = tmp_path / "tapdb" / "zebra-day" / "zebra-day-qa-1" / "tapdb-config.yaml"
    domain_registry_path = tmp_path / "tapdb-registry" / "domain_code_registry.json"
    prefix_registry_path = tmp_path / "tapdb-registry" / "prefix_ownership_registry.json"
    explicit_config.parent.mkdir(parents=True, exist_ok=True)
    explicit_config.write_text(
        (
            "tapdb:\n"
            f"  config_path: {tapdb_config_path}\n"
            f"  domain_registry_path: {domain_registry_path}\n"
            f"  prefix_ownership_registry_path: {prefix_registry_path}\n"
        ),
        encoding="utf-8",
    )

    settings = ZebraDaySettings.from_context()

    assert settings.deployment_code == "qa-1"
    assert settings.deployment_name == "qa-1"
    assert settings.deployment_color == _stable_deployment_color_hex("qa-1")
    assert settings.deployment_is_production is False
    assert settings.config_path == explicit_config
    assert settings.tapdb_database_name == "zebra-day-qa-1"
    assert settings.tapdb_owner_repo_name == "zebra-day"
    assert settings.tapdb_domain_code == "Z"
    assert settings.tapdb_domain_registry_path == domain_registry_path
    assert settings.tapdb_prefix_ownership_registry_path == prefix_registry_path
    assert settings.tapdb_config_path == tapdb_config_path


def test_settings_merge_file_values(monkeypatch, tmp_path):
    _set_xdg(monkeypatch, tmp_path, deployment="prodx")
    config_path = xdg.get_config_file_path()
    tapdb_config_path = tmp_path / "tapdb" / "tapdb-prod-custom.yaml"
    domain_registry_path = tmp_path / "tapdb-registry" / "domain_code_registry.json"
    prefix_registry_path = tmp_path / "tapdb-registry" / "prefix_ownership_registry.json"
    config_path.write_text(
        (
            "service:\n"
            "  host: localhost\n"
            "  port: 8119\n"
            "authentication:\n"
            "  mode: none\n"
            "  cognito_region: us-west-2\n"
            "  cognito_user_pool_id: pool-123\n"
            "  cognito_app_client_id: client-123\n"
            "  cognito_domain: example.auth.us-west-2.amazoncognito.com\n"
            "tapdb:\n"
            "  client_id: zebra-day\n"
            "  database_name: zebra-day-prod-custom\n"
            f"  config_path: {tapdb_config_path}\n"
            f"  domain_registry_path: {domain_registry_path}\n"
            f"  prefix_ownership_registry_path: {prefix_registry_path}\n"
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
    assert settings.cognito_region == "us-west-2"
    assert settings.cognito_user_pool_id == "pool-123"
    assert settings.cognito_app_client_id == "client-123"
    assert settings.cognito_domain == "example.auth.us-west-2.amazoncognito.com"
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
    assert settings.tapdb_config_path == tapdb_config_path
    assert settings.tapdb_domain_registry_path == domain_registry_path
    assert settings.tapdb_prefix_ownership_registry_path == prefix_registry_path
    assert settings.tapdb_owner_repo_name == "zebra-day"
    assert settings.tapdb_domain_code == "Z"
    assert settings.ui_show_environment_chrome is True
    assert settings.deployment == {
        "name": "sandbox-g",
        "color": "#123456",
        "is_production": False,
    }


def test_settings_env_overrides_cognito_file_values(monkeypatch, tmp_path):
    _set_xdg(monkeypatch, tmp_path, deployment="prodx")
    config_path = xdg.get_config_file_path()
    config_path.write_text(
        (
            "authentication:\n"
            "  cognito_region: us-east-1\n"
            "  cognito_user_pool_id: pool-file\n"
            "  cognito_app_client_id: client-file\n"
            "  cognito_domain: example.file.auth.us-west-2.amazoncognito.com\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("COGNITO_REGION", "us-west-2")
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "pool-env")
    monkeypatch.setenv("COGNITO_APP_CLIENT_ID", "client-env")
    monkeypatch.setenv("COGNITO_DOMAIN", "example.env.auth.us-west-2.amazoncognito.com")

    settings = ZebraDaySettings.from_context()

    assert settings.cognito_region == "us-west-2"
    assert settings.cognito_user_pool_id == "pool-env"
    assert settings.cognito_app_client_id == "client-env"
    assert settings.cognito_domain == "example.env.auth.us-west-2.amazoncognito.com"


def test_settings_rejects_schemeful_cognito_domain(monkeypatch, tmp_path):
    _set_xdg(monkeypatch, tmp_path, deployment="prodx")
    config_path = xdg.get_config_file_path()
    config_path.write_text(
        ("authentication:\n  cognito_domain: https://example.auth.us-west-2.amazoncognito.com\n"),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="bare host"):
        ZebraDaySettings.from_context()


def test_validate_settings_yaml_requires_tapdb_config_path() -> None:
    content = (
        "service:\n"
        "  host: 0.0.0.0\n"
        "  port: 8118\n"
        "authentication:\n"
        "  mode: cognito\n"
        "  session_secret_key: secret\n"
        "  allowed_email_domains:\n"
        "    - lsmc.com\n"
        "  default_tenant_id: 00000000-0000-0000-0000-000000000000\n"
        "  auto_provision_allowed_domains:\n"
        "    - lsmc.com\n"
        "tapdb:\n"
        "  client_id: zebra-day\n"
        "  owner_repo_name: zebra-day\n"
        "  domain_code: Z\n"
        "  database_name: zebra-day-local\n"
        "  domain_registry_path: /explicit/tapdb/domain_code_registry.json\n"
        "  prefix_ownership_registry_path: /explicit/tapdb/prefix_ownership_registry.json\n"
    )

    assert "tapdb.config_path is required" in validate_settings_yaml(content)


def test_validate_settings_yaml_requires_tapdb_registry_paths() -> None:
    content = (
        "service:\n"
        "  host: 0.0.0.0\n"
        "  port: 8118\n"
        "authentication:\n"
        "  mode: cognito\n"
        "  session_secret_key: secret\n"
        "  allowed_email_domains:\n"
        "    - lsmc.com\n"
        "  default_tenant_id: 00000000-0000-0000-0000-000000000000\n"
        "  auto_provision_allowed_domains:\n"
        "    - lsmc.com\n"
        "tapdb:\n"
        "  client_id: zebra-day\n"
        "  owner_repo_name: zebra-day\n"
        "  domain_code: Z\n"
        "  database_name: zebra-day-local\n"
        "  config_path: /explicit/tapdb/zebra-day/zebra-day-local/tapdb-config.yaml\n"
    )

    errors = validate_settings_yaml(content)
    assert "tapdb.domain_registry_path is required" in errors
    assert "tapdb.prefix_ownership_registry_path is required" in errors


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
    template_path = PROJECT_ROOT / "config" / "tapdb-config-zebra-day.yaml"
    payload = yaml.safe_load(template_path.read_text(encoding="utf-8"))

    assert template_path.is_file()
    assert payload["meta"]["config_version"] == 3
    assert payload["meta"]["client_id"] == "zebra-day"
    assert payload["meta"]["database_name"] == "zebra-day"
    assert payload["meta"]["owner_repo_name"] == "zebra-day"
    assert payload["meta"]["domain_code"] == "Z"
    assert isinstance(payload["meta"]["domain_registry_path"], str)
    assert isinstance(payload["meta"]["prefix_registry_path"], str)
    assert payload["environments"]["dev"]["port"] == "5544"
    assert payload["environments"]["dev"]["database"] == "zebra_day_dev"
    assert payload["environments"]["dev"]["audit_log_euid_prefix"] == "ZGX"
    assert payload["environments"]["prod"]["audit_log_euid_prefix"] == "ZGX"


def test_repo_ships_single_zebra_day_template_prefix():
    template_pack = yaml.safe_load(
        (PROJECT_ROOT / "config" / "tapdb_templates" / "zebra_day" / "templates.json").read_text(
            encoding="utf-8"
        )
    )
    prefixes = {template["instance_prefix"] for template in template_pack["templates"]}
    categories = {template["category"] for template in template_pack["templates"]}
    assert prefixes == {"ZGX"}
    assert categories == {"ZGX"}
