"""zebra_day public package surface."""

from __future__ import annotations

try:
    from zebra_day._version import __version__
except ImportError:
    __version__ = "0.0.0.dev0"

from zebra_day.client import PrinterRecord, ZebraDayApiClient, ZebraDayClient
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
from zebra_day.settings import ZebraDaySettings

__all__ = [
    "__version__",
    "configure_logging",
    "get_logger",
    "ZebraDaySettings",
    "ZebraDayClient",
    "ZebraDayApiClient",
    "PrinterRecord",
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
