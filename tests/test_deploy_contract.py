from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_root_environment_contract_uses_environment_yaml() -> None:
    environment = (PROJECT_ROOT / "environment.yaml").read_text(encoding="utf-8")

    assert (PROJECT_ROOT / "environment.yaml").is_file()
    assert not (PROJECT_ROOT / "zebra_day_env.yaml").exists()
    assert not (PROJECT_ROOT / "requirements.txt").exists()
    assert not (PROJECT_ROOT / "requirements-dev.txt").exists()
    assert "-e ." not in environment


def test_activate_uses_root_environment_yaml_and_repo_only_editable_install() -> None:
    activate = (PROJECT_ROOT / "activate").read_text(encoding="utf-8")

    assert "environment.yaml" in activate
    assert "zebra_day_env.yaml" not in activate
    assert 'pip install -e "${ZEBRA_DAY_PROJECT_ROOT}"' in activate
    assert '_ZDAY_DAYLILY_TAPDB_VERSION="5.0.4"' in activate
    assert '_ZDAY_DAYLILY_AUTH_COGNITO_VERSION="2.0.2"' in activate
    assert '"daylily-tapdb"' in activate
    assert '"daylily-auth-cognito"' in activate
    assert '_zday_ensure_published_distribution' in activate
    assert "_zday_ensure_editable_repo" not in activate
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
