"""
zebra_day - A Python library to manage Zebra printer fleets and ZPL print requests.
"""

from __future__ import annotations

try:
    from zebra_day._version import __version__
except ImportError:
    __version__ = "0.0.0.dev0"

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
    "__version__",
    "configure_logging",
    "get_logger",
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
