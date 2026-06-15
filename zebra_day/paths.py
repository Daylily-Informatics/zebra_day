"""Deployment-aware XDG paths for zebra_day."""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "zebra_day"


def sanitize_deployment_code(value: str | None) -> str:
    """Normalize deployment names into safe path components."""
    raw = str(value or "").strip()
    if not raw:
        raise RuntimeError("Zebra Day deployment code is required")
    sanitized = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in raw).strip(
        "-"
    )
    if not sanitized:
        raise RuntimeError(f"Invalid Zebra Day deployment code: {value!r}")
    return sanitized


def get_deployment_code() -> str:
    """Resolve the active deployment code from supported env vars."""
    explicit_deployment = os.environ.get("ZEBRA_DAY_DEPLOYMENT_CODE", "").strip()
    if explicit_deployment:
        return sanitize_deployment_code(explicit_deployment)
    conda_env = os.environ.get("CONDA_DEFAULT_ENV", "").strip()
    if conda_env.startswith("ZEBRA_DAY-"):
        return sanitize_deployment_code(conda_env.removeprefix("ZEBRA_DAY-"))
    return sanitize_deployment_code(
        os.environ.get("DEPLOYMENT_CODE") or os.environ.get("LSMC_DEPLOYMENT_CODE")
    )


def get_app_dir_name() -> str:
    """Return the base XDG directory name."""
    return APP_NAME


def get_config_filename() -> str:
    """Return the deployment-scoped runtime config filename."""
    return f"zebra-day-config-{get_deployment_code()}.yaml"


def _get_xdg_dir(env_var: str) -> Path:
    env_value = os.environ.get(env_var)
    if not env_value:
        raise RuntimeError(f"{env_var} is required for Zebra Day runtime paths")
    path = Path(env_value)
    if not path.is_absolute():
        raise RuntimeError(f"{env_var} must be an absolute path: {env_value}")
    return path


def get_config_dir() -> Path:
    """Return the shared zebra_day config directory."""
    base = _get_xdg_dir("XDG_CONFIG_HOME")
    config_dir = base / APP_NAME
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_config_file_path() -> Path:
    """Return the deployment-scoped zebra_day runtime config file."""
    return get_config_dir() / get_config_filename()


def get_data_dir() -> Path:
    """Return the deployment-scoped data directory."""
    deployment = get_deployment_code()
    base = _get_xdg_dir("XDG_DATA_HOME")
    data_dir = base / APP_NAME / deployment
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_state_dir() -> Path:
    """Return the deployment-scoped state directory."""
    deployment = get_deployment_code()
    base = _get_xdg_dir("XDG_STATE_HOME")
    state_dir = base / APP_NAME / deployment
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def get_cache_dir() -> Path:
    """Return the deployment-scoped cache directory."""
    deployment = get_deployment_code()
    base = _get_xdg_dir("XDG_CACHE_HOME")
    cache_dir = base / APP_NAME / deployment
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def get_logs_dir() -> Path:
    """Return the logs directory for the active deployment."""
    logs_dir = get_state_dir() / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def get_generated_files_dir() -> Path:
    """Return the generated-files directory for previews and artifacts."""
    files_dir = get_cache_dir() / "generated"
    files_dir.mkdir(parents=True, exist_ok=True)
    return files_dir
