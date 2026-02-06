"""
zebra_day - A Python library to manage Zebra printer fleets and ZPL print requests.

This module provides both low-level access via print_mgr.zpl() and
convenient top-level functions for common operations.

Example (simplified API):
    >>> import zebra_day as zd
    >>> zd.query_labs()
    ['default', 'lab-2']
    >>> zd.query_printers('default')
    {'192.168.1.100': {...}, '192.168.1.101': {...}}
    >>> zd.print_zpl('default', '192.168.1.100', 'tube_2inX1in', uid_barcode='SAMPLE123')
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

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
    # Top-level convenience functions
    "query_labs",
    "query_printers",
    "scan",
    "print_zpl",
    "start_gui",
]


# Module-level singleton for zpl instance
_zpl_instance = None


def _get_zpl():
    """Get or create the module-level zpl instance.

    Returns:
        A zpl instance from print_mgr module.
    """
    global _zpl_instance
    if _zpl_instance is None:
        from zebra_day import print_mgr

        _zpl_instance = print_mgr.zpl()
    return _zpl_instance


def _reset_zpl():
    """Reset the module-level zpl instance (useful for testing)."""
    global _zpl_instance
    _zpl_instance = None


def query_labs() -> list[str]:
    """Query all available labs.

    Returns:
        List of lab identifiers.

    Example:
        >>> import zebra_day as zd
        >>> zd.query_labs()
        ['default', 'lab-2']
    """
    zp = _get_zpl()
    return list(zp.printers.get("labs", {}).keys())


def query_printers(lab: str) -> dict[str, dict[str, Any]]:
    """Query all printers for a specific lab.

    Args:
        lab: Lab identifier (e.g., 'default')

    Returns:
        Dictionary of printers keyed by printer ID, where each value
        contains printer configuration (ip_address, model, etc.)

    Raises:
        KeyError: If lab does not exist.

    Example:
        >>> import zebra_day as zd
        >>> zd.query_printers('default')
        {'192.168.1.100': {'ip_address': '192.168.1.100', 'model': 'ZD620', ...}}
    """
    zp = _get_zpl()
    labs = zp.printers.get("labs", {})
    if lab not in labs:
        raise KeyError(f"Lab '{lab}' not found. Available labs: {list(labs.keys())}")
    result: dict[str, dict[str, Any]] = labs[lab].get("printers", {})
    return result


def scan(ip_stub: str = "192.168.1", lab: str = "default") -> None:
    """Scan the network for Zebra printers and add them to configuration.

    This scans all IPs from {ip_stub}.0 to {ip_stub}.255 and adds any
    discovered Zebra printers to the specified lab.

    Args:
        ip_stub: First three octets of IP range to scan (default: "192.168.1")
        lab: Lab identifier to add discovered printers to (default: "default")

    Example:
        >>> import zebra_day as zd
        >>> zd.scan(ip_stub="10.0.0", lab="production")
    """
    zp = _get_zpl()
    zp.probe_zebra_printers_add_to_printers_json(ip_stub=ip_stub, lab=lab)


def print_zpl(
    lab: str,
    printer_name: str,
    label_zpl_style: str,
    uid_barcode: str = "",
    alt_a: str = "",
    alt_b: str = "",
    alt_c: str = "",
    alt_d: str = "",
    alt_e: str = "",
    alt_f: str = "",
) -> str:
    """Print a label using ZPL to a configured printer.

    Args:
        lab: Lab identifier (e.g., 'default')
        printer_name: Printer identifier (usually IP address)
        label_zpl_style: Label template name (e.g., 'tube_2inX1in')
        uid_barcode: Primary barcode value
        alt_a: Alternative field A value
        alt_b: Alternative field B value
        alt_c: Alternative field C value
        alt_d: Alternative field D value
        alt_e: Alternative field E value
        alt_f: Alternative field F value

    Returns:
        The ZPL string that was sent to the printer.

    Raises:
        KeyError: If lab or printer not found.
        Exception: If print fails.

    Example:
        >>> import zebra_day as zd
        >>> zpl_str = zd.print_zpl(
        ...     lab='default',
        ...     printer_name='192.168.1.100',
        ...     label_zpl_style='tube_2inX1in',
        ...     uid_barcode='SAMPLE-001',
        ...     alt_a='Patient Name'
        ... )
    """
    zp = _get_zpl()
    result: str = zp.print_zpl(
        lab=lab,
        printer_name=printer_name,
        label_zpl_style=label_zpl_style,
        uid_barcode=uid_barcode,
        alt_a=alt_a,
        alt_b=alt_b,
        alt_c=alt_c,
        alt_d=alt_d,
        alt_e=alt_e,
        alt_f=alt_f,
    )
    return result


def start_gui(host: str = "0.0.0.0", port: int = 8118, https: bool = True) -> None:
    """Start the zebra_day web GUI server.

    This starts the FastAPI-based web interface for managing printers,
    templates, and printing labels.

    Args:
        host: Host to bind to (default: "0.0.0.0")
        port: Port to listen on (default: 8118)
        https: Enable HTTPS with automatic certificate generation (default: True)

    Note:
        HTTPS is enabled by default. The server will:
        1. Look for existing certificates in standard locations
        2. Attempt to auto-generate certificates with mkcert if available
        3. Fall back to HTTP with guidance if certificate setup fails

        Set https=False to force HTTP mode.

    Example:
        >>> import zebra_day as zd
        >>> zd.start_gui()  # Starts with HTTPS (auto-generates certs if needed)
        >>> zd.start_gui(port=8080, https=False)  # Force HTTP mode
    """
    from zebra_day.web.app import run_server

    # Determine SSL arguments based on https flag
    ssl_certfile = None
    ssl_keyfile = None

    if https:
        # Let run_server resolve SSL paths and auto-generate if needed
        # We pass None and let it figure it out
        pass

    run_server(
        host=host,
        port=port,
        reload=False,
        auth="none",
        ssl_certfile=ssl_certfile if https else None,
        ssl_keyfile=ssl_keyfile if https else None,
    )
