"""Helpers for required runtime dependency imports."""

from __future__ import annotations

import importlib


def import_from_sibling(module_name: str, repo_name: str):
    """Import a required module and raise a package-scoped error if missing."""
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        raise ImportError(f"{repo_name} is required for this zebra_day installation") from exc
