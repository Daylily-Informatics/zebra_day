"""
Custom exceptions for zebra_day.

Provides specific exception types for different error conditions.
"""
from __future__ import annotations


class ZebraDayError(Exception):
    """Base exception for all zebra_day errors."""

    pass


class PrinterConnectionError(ZebraDayError):
    """Raised when unable to connect to a printer."""

    def __init__(self, printer_ip: str, message: str = ""):
        self.printer_ip = printer_ip
        super().__init__(f"Failed to connect to printer at {printer_ip}: {message}")


class PrinterNotFoundError(ZebraDayError):
    """Raised when a printer is not found in the configuration."""

    def __init__(self, printer_name: str, lab: str = ""):
        self.printer_name = printer_name
        self.lab = lab
        msg = f"Printer '{printer_name}' not found"
        if lab:
            msg += f" in lab '{lab}'"
        super().__init__(msg)


class ConfigError(ZebraDayError):
    """Raised when there's an issue with configuration."""

    def __init__(self, message: str, config_path: str = ""):
        self.config_path = config_path
        super().__init__(message)


class ConfigFileNotFoundError(ConfigError):
    """Raised when a configuration file is not found."""

    def __init__(self, path: str):
        super().__init__(f"Configuration file not found: {path}", config_path=path)


class ConfigParseError(ConfigError):
    """Raised when a configuration file cannot be parsed."""

    def __init__(self, path: str, details: str = ""):
        msg = f"Failed to parse configuration file: {path}"
        if details:
            msg += f" ({details})"
        super().__init__(msg, config_path=path)


class LabelTemplateError(ZebraDayError):
    """Raised when there's an issue with a label template."""

    def __init__(self, template_name: str, message: str = ""):
        self.template_name = template_name
        super().__init__(f"Label template error '{template_name}': {message}")


class LabelTemplateNotFoundError(LabelTemplateError):
    """Raised when a label template file is not found."""

    def __init__(self, template_name: str):
        super().__init__(template_name, "template not found")


class ZPLRenderError(ZebraDayError):
    """Raised when ZPL rendering fails."""

    def __init__(self, message: str):
        super().__init__(f"ZPL render error: {message}")


class NetworkScanError(ZebraDayError):
    """Raised when network scanning for printers fails."""

    def __init__(self, ip_stub: str, message: str = ""):
        self.ip_stub = ip_stub
        super().__init__(f"Network scan failed for {ip_stub}.*: {message}")

