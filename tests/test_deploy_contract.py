from __future__ import annotations

import tomllib
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_environment_yaml_only_contains_bootstrap_and_system_packages() -> None:
    environment_path = PROJECT_ROOT / "environment.yaml"
    environment_text = environment_path.read_text(encoding="utf-8")
    payload = yaml.safe_load(environment_text)
    dependencies = payload["dependencies"]

    assert environment_path.is_file()
    assert "pip:" not in environment_text
    assert not (PROJECT_ROOT / "zebra_day_env.yaml").exists()
    assert not (PROJECT_ROOT / "requirements.txt").exists()
    assert not (PROJECT_ROOT / "requirements-dev.txt").exists()

    allowed_prefixes = (
        "python",
        "pip",
        "setuptools",
        "bash",
        "postgresql",
        "jq",
        "fd-find",
        "rclone",
    )
    assert all(dep.startswith(allowed_prefixes) for dep in dependencies)
    assert not any(
        dep.startswith(
            (
                "cli-core-yo",
                "daylily-",
                "fastapi",
                "uvicorn",
                "pytest",
                "playwright",
                "ruff",
                "mypy",
                "pre-commit",
            )
        )
        for dep in dependencies
    )


def test_activate_is_env_only_and_installs_repo_editable_once() -> None:
    activate = (PROJECT_ROOT / "activate").read_text(encoding="utf-8")

    assert 'conda env create -n "${_ZDAY_ENV_NAME}" -f "${_ZDAY_ENV_FILE}"' in activate
    assert 'conda activate "${_ZDAY_ENV_NAME}"' in activate
    assert 'export PATH="${CONDA_PREFIX}/bin:$PATH"' in activate
    assert '"${_ZDAY_PYTHON}" -m pip install -e "${ZEBRA_DAY_PROJECT_ROOT}" -q' in activate
    assert (
        '"${_ZDAY_PYTHON}" -m pip install -e "${ZEBRA_DAY_PROJECT_ROOT}" --no-deps' not in activate
    )
    assert "daylily-tapdb" not in activate
    assert "daylily-auth-cognito" not in activate
    assert "cli-core-yo" not in activate
    assert "_zday_install_pyproject_dependencies" not in activate
    assert "_zday_ensure_published_distribution" not in activate
    assert "_zday_sync_tapdb_namespace_metadata" not in activate
    assert "TAPDB_DOMAIN_REGISTRY_PATH" not in activate
    assert "TAPDB_PREFIX_REGISTRY_PATH" not in activate
    assert "conda install -y" not in activate
    assert "ZEBRA_DAY_ACTIVE" not in activate
    assert "ZEBRA_DAY_DEPLOYMENT_CODE" not in activate


def test_pyproject_owns_python_dependencies_and_console_scripts() -> None:
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = pyproject["project"]["dependencies"]
    scripts = pyproject["project"]["scripts"]

    assert "zday" in scripts
    assert scripts["zday"] == "zebra_day.cli:main"
    assert "optional-dependencies" not in pyproject["project"]
    assert "cli-core-yo==2.1.0" in dependencies
    assert "daylily-auth-cognito==2.1.1" in dependencies
    assert "daylily-tapdb==6.0.4" in dependencies
    assert "boto3>=1.26.0" in dependencies
    assert "awscli" in dependencies
    assert "bandit[toml]>=1.8.0" in dependencies
    assert "ipython>=8.16.0" in dependencies
    assert "pytest>=7.4.0" in dependencies
    assert "pytest-cov>=4.0.0" in dependencies
    assert "pytest-playwright>=0.4.4" in dependencies
    assert "playwright>=1.40.0" in dependencies
    assert "pre-commit>=3.8.0" in dependencies
    assert "ruff>=0.1.0" in dependencies
    assert "mypy>=1.0.0" in dependencies
    assert "types-PyYAML>=6.0.0" in dependencies
    assert "mkdocs>=1.5.0" in dependencies
    assert "mkdocs-material>=9.0.0" in dependencies
    assert "python-jose[cryptography]>=3.3.0" in dependencies


def test_activate_and_scripts_support_cli_on_path_contract() -> None:
    activate = (PROJECT_ROOT / "activate").read_text(encoding="utf-8")
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert 'export PATH="${CONDA_PREFIX}/bin:$PATH"' in activate
    assert "zday" in pyproject["project"]["scripts"]


def test_agents_ban_secondary_install_sets() -> None:
    agents = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert "secondary install set" in agents
    assert "`.[dev]`" in agents
    assert "extras groups" in agents


def test_user_facing_files_do_not_reference_dev_extras_or_optional_groups() -> None:
    for relative_path in ("README.md", "activate", "tests/e2e/README.md"):
        path = PROJECT_ROOT / relative_path
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        assert ".[dev]" not in text, relative_path
        assert "optional-dependencies.dev" not in text, relative_path
