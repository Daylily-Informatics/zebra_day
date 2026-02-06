"""
Backend abstraction for zebra_day config + template storage.

Provides the ``ConfigBackend`` protocol and a factory function ``get_backend()``
that returns the correct implementation based on environment variables.
"""

from __future__ import annotations

import os
from typing import Protocol, runtime_checkable


@runtime_checkable
class ConfigBackend(Protocol):
    """Backend protocol for zebra_day config + template storage."""

    # --- Config Operations ---

    def load_config(self) -> dict:
        """Load the full printer configuration dict.

        Returns:
            Config dict with 'schema_version', 'labs', etc.

        Raises:
            ConfigError: If no config exists or cannot be loaded.
        """
        ...

    def save_config(self, config: dict) -> None:
        """Persist the full printer configuration dict.

        Args:
            config: Full config dict to save.
        """
        ...

    def config_exists(self) -> bool:
        """Check whether a config exists in the backend."""
        ...

    # --- Template Operations ---

    def get_template(self, name: str) -> str:
        """Load a template's ZPL content by stem name.

        Args:
            name: Template stem (e.g. 'tube_2inX1in').

        Returns:
            Raw ZPL string.

        Raises:
            LabelTemplateNotFoundError: If template not found.
        """
        ...

    def list_templates(self) -> list[str]:
        """List all template stem names.

        Returns:
            Sorted list of template stems.
        """
        ...

    def save_template(self, name: str, zpl_content: str) -> None:
        """Save or overwrite a template.

        Args:
            name: Template stem.
            zpl_content: Raw ZPL string.
        """
        ...

    def delete_template(self, name: str) -> None:
        """Delete a template by stem name.

        Raises:
            LabelTemplateNotFoundError: If template not found.
        """
        ...

    def template_exists(self, name: str) -> bool:
        """Check whether a template exists in the backend."""
        ...


def get_backend(config_path: str | None = None) -> ConfigBackend:
    """Create and return the appropriate backend based on environment.

    Args:
        config_path: Optional explicit config file path (local mode only).

    Returns:
        A ConfigBackend implementation.
    """
    backend_type = os.environ.get("ZEBRA_DAY_CONFIG_BACKEND", "local").lower().strip()

    if backend_type == "dynamodb":
        from zebra_day.backends.dynamo import DynamoBackend

        return DynamoBackend.from_env()

    # Default: local file backend
    from zebra_day.backends.local import LocalBackend

    return LocalBackend(config_path=config_path)


__all__ = [
    "ConfigBackend",
    "get_backend",
]

