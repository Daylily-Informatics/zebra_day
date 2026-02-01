"""
XDG Base Directory specification support for zebra_day.

This module provides cross-platform paths for configuration, state, cache, and data
following the XDG Base Directory specification on Linux/macOS.

XDG Base Directory Specification:
- XDG_CONFIG_HOME: User configuration files (~/.config)
- XDG_DATA_HOME: User data files (~/.local/share)
- XDG_STATE_HOME: User state files (~/.local/state) - logs, history
- XDG_CACHE_HOME: User cache files (~/.cache)

On macOS, we use ~/Library/Application Support for data and
~/Library/Preferences for config, but support XDG overrides.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

APP_NAME = "zebra_day"


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
    if sys.platform == "darwin":
        # macOS: Use XDG if set, otherwise ~/Library/Preferences
        fallback = Path.home() / "Library" / "Preferences" / APP_NAME
    else:
        # Linux/other: Use XDG
        fallback = Path.home() / ".config" / APP_NAME

    base = _get_xdg_dir("XDG_CONFIG_HOME", fallback.parent)
    config_dir = base / APP_NAME if "XDG_CONFIG_HOME" in os.environ else fallback
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_data_dir() -> Path:
    """Get the data directory for persistent application data.

    Returns:
        Path to zebra_day data directory (created if needed)
    """
    if sys.platform == "darwin":
        fallback = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        fallback = Path.home() / ".local" / "share" / APP_NAME

    base = _get_xdg_dir("XDG_DATA_HOME", fallback.parent)
    data_dir = base / APP_NAME if "XDG_DATA_HOME" in os.environ else fallback
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_state_dir() -> Path:
    """Get the state directory for logs and runtime state.

    Returns:
        Path to zebra_day state directory (created if needed)
    """
    if sys.platform == "darwin":
        fallback = Path.home() / "Library" / "Logs" / APP_NAME
    else:
        fallback = Path.home() / ".local" / "state" / APP_NAME

    base = _get_xdg_dir("XDG_STATE_HOME", fallback.parent)
    state_dir = base / APP_NAME if "XDG_STATE_HOME" in os.environ else fallback
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def get_cache_dir() -> Path:
    """Get the cache directory for temporary files.

    Returns:
        Path to zebra_day cache directory (created if needed)
    """
    if sys.platform == "darwin":
        fallback = Path.home() / "Library" / "Caches" / APP_NAME
    else:
        fallback = Path.home() / ".cache" / APP_NAME

    base = _get_xdg_dir("XDG_CACHE_HOME", fallback.parent)
    cache_dir = base / APP_NAME if "XDG_CACHE_HOME" in os.environ else fallback
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


# Specific file/directory paths
def get_printer_config_path() -> Path:
    """Get path to the printer configuration JSON file."""
    return get_config_dir() / "printer_config.json"


def get_label_styles_dir() -> Path:
    """Get path to the label styles directory."""
    styles_dir = get_data_dir() / "label_styles"
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

