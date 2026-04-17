"""Deployment-aware XDG paths for zebra_day."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "zebra_day"
DEFAULT_DEPLOYMENT_CODE = "local"


def sanitize_deployment_code(value: str | None) -> str:
    """Normalize deployment names into safe path components."""
    raw = str(value or "").strip()
    if not raw:
        return DEFAULT_DEPLOYMENT_CODE
    sanitized = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in raw).strip(
        "-"
    )
    return sanitized or DEFAULT_DEPLOYMENT_CODE


def get_deployment_code() -> str:
    """Resolve the active deployment code from supported env vars."""
    explicit_deployment = os.environ.get("ZEBRA_DAY_DEPLOYMENT_CODE", "").strip()
    if explicit_deployment:
        return sanitize_deployment_code(explicit_deployment)
    conda_default_env = os.environ.get("CONDA_DEFAULT_ENV", "").strip()
    if conda_default_env.startswith("ZEBRA_DAY-"):
        return sanitize_deployment_code(conda_default_env.removeprefix("ZEBRA_DAY-"))
    return sanitize_deployment_code(
        os.environ.get("DEPLOYMENT_CODE")
        or os.environ.get("LSMC_DEPLOYMENT_CODE")
        or DEFAULT_DEPLOYMENT_CODE
    )


def get_app_dir_name() -> str:
    """Return the base XDG directory name."""
    return APP_NAME


def get_config_filename() -> str:
    """Return the deployment-scoped runtime config filename."""
    return f"zebra-day-config-{get_deployment_code()}.yaml"


def _get_xdg_dir(env_var: str, fallback: Path) -> Path:
    env_value = os.environ.get(env_var)
    return Path(env_value) if env_value else fallback


def get_config_dir() -> Path:
    """Return the shared zebra_day config directory."""
    base = _get_xdg_dir("XDG_CONFIG_HOME", Path.home() / ".config")
    config_dir = base / APP_NAME
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_config_file_path() -> Path:
    """Return the deployment-scoped zebra_day runtime config file."""
    return get_config_dir() / get_config_filename()


def get_data_dir() -> Path:
    """Return the deployment-scoped data directory."""
    deployment = get_deployment_code()
    if sys.platform == "darwin":
        fallback = Path.home() / "Library" / "Application Support" / APP_NAME / deployment
    else:
        fallback = Path.home() / ".local" / "share" / APP_NAME / deployment
    if sys.platform == "darwin":
        base = _get_xdg_dir("XDG_DATA_HOME", fallback.parent.parent)
    else:
        base = _get_xdg_dir("XDG_DATA_HOME", fallback.parent.parent)
    data_dir = base / APP_NAME / deployment
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_state_dir() -> Path:
    """Return the deployment-scoped state directory."""
    deployment = get_deployment_code()
    if sys.platform == "darwin":
        fallback = Path.home() / "Library" / "Logs" / APP_NAME / deployment
        base = _get_xdg_dir("XDG_STATE_HOME", fallback.parent.parent)
    else:
        fallback = Path.home() / ".local" / "state" / APP_NAME / deployment
        base = _get_xdg_dir("XDG_STATE_HOME", fallback.parent.parent)
    state_dir = base / APP_NAME / deployment
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def get_cache_dir() -> Path:
    """Return the deployment-scoped cache directory."""
    deployment = get_deployment_code()
    if sys.platform == "darwin":
        fallback = Path.home() / "Library" / "Caches" / APP_NAME / deployment
        base = _get_xdg_dir("XDG_CACHE_HOME", fallback.parent.parent)
    else:
        fallback = Path.home() / ".cache" / APP_NAME / deployment
        base = _get_xdg_dir("XDG_CACHE_HOME", fallback.parent.parent)
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
