"""
zebra_day - A Python library to manage Zebra printer fleets and ZPL print requests.
"""
from __future__ import annotations

from zebra_day.exceptions import (
    ConfigError,
    ConfigFileNotFoundError,
    ConfigParseError,
    LabelTemplateError,
    LabelTemplateNotFoundError,
    NetworkScanError,
    PrinterConnectionError,
    PrinterNotFoundError,
    ZebraDayError,
    ZPLRenderError,
)
from zebra_day.logging_config import configure_logging, get_logger

__all__ = [
    # Logging
    "configure_logging",
    "get_logger",
    # Exceptions
    "ZebraDayError",
    "PrinterConnectionError",
    "PrinterNotFoundError",
    "ConfigError",
    "ConfigFileNotFoundError",
    "ConfigParseError",
    "LabelTemplateError",
    "LabelTemplateNotFoundError",
    "ZPLRenderError",
    "NetworkScanError",
]
