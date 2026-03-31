"""Deployment-scoped XDG paths for zebra_day."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "zebra_day"
APP_SLUG = "zebra-day"
DEFAULT_DEPLOYMENT_CODE = "local"


def sanitize_deployment_code(value: str | None) -> str:
    """Normalize deployment names into safe path components."""
    raw = str(value or "").strip()
    if not raw:
        return DEFAULT_DEPLOYMENT_CODE
    sanitized = "".join(
        ch if ch.isalnum() or ch in {".", "_", "-"} else "-"
        for ch in raw
    ).strip("-")
    return sanitized or DEFAULT_DEPLOYMENT_CODE


def get_deployment_code() -> str:
    """Resolve the active deployment code from the supported env vars."""
    return sanitize_deployment_code(
        os.environ.get("ZEBRA_DAY_DEPLOYMENT_CODE")
        or os.environ.get("DEPLOYMENT_CODE")
        or os.environ.get("LSMC_DEPLOYMENT_CODE")
        or DEFAULT_DEPLOYMENT_CODE
    )


def get_app_dir_name() -> str:
    """Return the deployment-scoped XDG directory name."""
    return f"{APP_SLUG}-{get_deployment_code()}"


def get_config_filename() -> str:
    """Return the deployment-scoped config filename."""
    return f"{APP_SLUG}-config-{get_deployment_code()}.yaml"


def _maybe_copy_file(src: Path, dst: Path) -> bool:
    """Best-effort copy from src -> dst if dst is missing.

    Returns:
        True if a copy occurred, else False.
    """
    try:
        if src.exists() and not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            return True
    except Exception:
        # Path helpers should be safe to call during import/startup; callers
        # handle "file missing" cases elsewhere.
        return False
    return False


def _maybe_migrate_legacy_macos_config_file(target_path: Path) -> None:
    """If on macOS and only legacy config exists, copy it into XDG location."""
    if sys.platform != "darwin":
        return

    legacy_yaml = get_legacy_macos_config_file_path()
    _maybe_copy_file(legacy_yaml, target_path)


def _get_xdg_dir(env_var: str, fallback: Path) -> Path:
    """Get XDG directory, respecting environment variable if set."""
    env_value = os.environ.get(env_var)
    if env_value:
        return Path(env_value)
    return fallback


def get_config_dir() -> Path:
    """Get the configuration directory.

    Returns:
        Path to zebra_day config directory (created if needed)
    """
    # Cross-platform default: XDG (~/.config) unless XDG_CONFIG_HOME is set.
    base = _get_xdg_dir("XDG_CONFIG_HOME", Path.home() / ".config")
    config_dir = base / get_app_dir_name()
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_legacy_macos_config_dir() -> Path:
    """Get the legacy macOS configuration directory.

    Older zebra_day versions used this location by default. New code should use
    :func:`get_config_dir` / :func:`get_config_file_path`.

    Returns:
        Path to ~/Library/Preferences/zebra_day (not created automatically)
    """
    return Path.home() / "Library" / "Preferences" / APP_NAME


def get_legacy_macos_config_file_path() -> Path:
    """Get legacy macOS path to zebra-day-config.yaml (not created)."""
    return get_legacy_macos_config_dir() / "zebra-day-config.yaml"


def get_legacy_macos_json_config_path() -> Path:
    """Get legacy macOS path to printer_config.json (not created)."""
    return get_legacy_macos_config_dir() / "printer_config.json"


def get_data_dir() -> Path:
    """Get the data directory for persistent application data.

    Returns:
        Path to zebra_day data directory (created if needed)
    """
    if sys.platform == "darwin":
        fallback = Path.home() / "Library" / "Application Support" / get_app_dir_name()
    else:
        fallback = Path.home() / ".local" / "share" / get_app_dir_name()

    base = _get_xdg_dir("XDG_DATA_HOME", fallback.parent)
    data_dir = base / get_app_dir_name() if "XDG_DATA_HOME" in os.environ else fallback
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_state_dir() -> Path:
    """Get the state directory for logs and runtime state.

    Returns:
        Path to zebra_day state directory (created if needed)
    """
    if sys.platform == "darwin":
        fallback = Path.home() / "Library" / "Logs" / get_app_dir_name()
    else:
        fallback = Path.home() / ".local" / "state" / get_app_dir_name()

    base = _get_xdg_dir("XDG_STATE_HOME", fallback.parent)
    state_dir = base / get_app_dir_name() if "XDG_STATE_HOME" in os.environ else fallback
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def get_cache_dir() -> Path:
    """Get the cache directory for temporary files.

    Returns:
        Path to zebra_day cache directory (created if needed)
    """
    if sys.platform == "darwin":
        fallback = Path.home() / "Library" / "Caches" / get_app_dir_name()
    else:
        fallback = Path.home() / ".cache" / get_app_dir_name()

    base = _get_xdg_dir("XDG_CACHE_HOME", fallback.parent)
    cache_dir = base / get_app_dir_name() if "XDG_CACHE_HOME" in os.environ else fallback
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


# Specific file/directory paths
def get_config_file_path() -> Path:
    """Get path to the zebra-day configuration YAML file.

    Returns:
        Path to zebra-day-config.yaml in XDG config directory
    """
    target = get_config_dir() / get_config_filename()
    _maybe_migrate_legacy_macos_config_file(target)
    return target


def get_printer_config_path() -> Path:
    """Get path to the printer configuration file.

    .. deprecated:: 2.2.0
        Use :func:`get_config_file_path` instead. This function now returns
        the YAML config path for backward compatibility.

    Returns:
        Path to zebra-day-config.yaml (YAML format)
    """
    return get_config_file_path()


def get_legacy_json_config_path() -> Path:
    """Get path to the legacy JSON configuration file.

    Used during migration from JSON to YAML format.

    Returns:
        Path to printer_config.json in XDG config directory
    """
    target = get_config_dir() / "printer_config.json"
    if sys.platform == "darwin":
        legacy_json = get_legacy_macos_json_config_path()
        _maybe_copy_file(legacy_json, target)
    return target


def get_label_styles_dir() -> Path:
    """Get path to the *user* label styles directory.

    Historically this pointed at the XDG *data* directory. As of the unified
    template workflow, user-editable templates live under the XDG *config*
    directory so they are easy to locate and manage alongside zebra_day config.
    """
    styles_dir = get_config_dir() / "label_styles"
    styles_dir.mkdir(parents=True, exist_ok=True)
    return styles_dir


def get_label_drafts_dir() -> Path:
    """Get path to the label drafts (tmps) directory."""
    drafts_dir = get_label_styles_dir() / "tmps"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    return drafts_dir


def get_config_backups_dir() -> Path:
    """Get path to the config backups directory."""
    backups_dir = get_config_dir() / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    return backups_dir


def get_logs_dir() -> Path:
    """Get path to the logs directory."""
    logs_dir = get_state_dir() / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def get_generated_files_dir() -> Path:
    """Get path for generated files like PNGs."""
    files_dir = get_cache_dir() / "generated"
    files_dir.mkdir(parents=True, exist_ok=True)
    return files_dir
