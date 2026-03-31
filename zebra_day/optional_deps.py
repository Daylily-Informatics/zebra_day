"""Helpers for optional daylily sibling dependencies."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _sibling_checkout(name: str) -> Path:
    return _repo_root().parent / name


def import_from_sibling(module_name: str, repo_name: str):
    """Import a module, falling back to a sibling editable checkout."""
    try:
        return importlib.import_module(module_name)
    except ImportError:
        checkout = _sibling_checkout(repo_name)
        if checkout.exists():
            sys.path.insert(0, str(checkout))
            return importlib.import_module(module_name)
        raise
