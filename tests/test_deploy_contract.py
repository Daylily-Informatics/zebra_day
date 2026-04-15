from __future__ import annotations

import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _tapdb_version() -> str:
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    for dependency in pyproject["project"]["dependencies"]:
        if dependency.startswith("daylily-tapdb=="):
            return dependency.split("==", 1)[1]
    raise AssertionError("daylily-tapdb dependency is missing")


def test_root_environment_contract_uses_environment_yaml() -> None:
    environment = (PROJECT_ROOT / "environment.yaml").read_text(encoding="utf-8")

    assert (PROJECT_ROOT / "environment.yaml").is_file()
    assert not (PROJECT_ROOT / "zebra_day_env.yaml").exists()
    assert not (PROJECT_ROOT / "requirements.txt").exists()
    assert not (PROJECT_ROOT / "requirements-dev.txt").exists()
    assert "-e ." not in environment


def test_activate_uses_root_environment_yaml_and_repo_only_editable_install() -> None:
    activate = (PROJECT_ROOT / "activate").read_text(encoding="utf-8")
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    tapdb_version = _tapdb_version()

    assert "environment.yaml" in activate
    assert "zebra_day_env.yaml" not in activate
    assert 'pip install -e "${ZEBRA_DAY_PROJECT_ROOT}" --no-deps' in activate
    assert "_zday_pyproject_dependency_version" in activate
    assert f"daylily-tapdb=={tapdb_version}" in pyproject
    assert '_ZDAY_DAYLILY_AUTH_COGNITO_VERSION="2.0.2"' in activate
    assert '"daylily-tapdb"' in activate
    assert '"daylily-auth-cognito"' in activate
    assert '_zday_ensure_published_distribution' in activate
    assert '_zday_sync_tapdb_namespace_metadata' in activate
    assert '_zday_sync_tapdb_namespace_metadata "$user_path" "$client_id" "$database_name"' in activate
    assert 'export MERIDIAN_DOMAIN_CODE="Z"' in activate
    assert 'export TAPDB_OWNER_REPO="zebra-day"' in activate
    assert 'export TAPDB_DOMAIN_CODE="${MERIDIAN_DOMAIN_CODE}"' in activate
    assert 'export TAPDB_DOMAIN_REGISTRY_PATH="${HOME}/.config/tapdb/domain_code_registry.json"' in activate
    assert 'export TAPDB_PREFIX_REGISTRY_PATH="${HOME}/.config/tapdb/prefix_ownership_registry.json"' in activate
    assert "TAPDB_APP_CODE" not in activate
    assert "_zday_ensure_editable_repo" not in activate
    assert "--no-deps" in activate
    assert "[dev,lint,auth]" not in activate
    assert "../daylily-tapdb" not in activate
    assert "../daylily-auth-cognito" not in activate
    assert "../cli-core-yo" not in activate


def test_env_cli_points_to_contract_env_vars_and_positional_activate() -> None:
    env_cli = (PROJECT_ROOT / "zebra_day" / "cli" / "env.py").read_text(encoding="utf-8")

    assert "ZEBRA_DAY_PROJECT_ROOT" in env_cli
    assert "source {activate_script} <deploy-name>" in env_cli
    assert "_ZEBRA_DAY_ACTIVE" not in env_cli
    assert "_ZDAY_ACTIVE" not in env_cli
