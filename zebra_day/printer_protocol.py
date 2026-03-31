"""Low-level printer protocol helpers for zebra_day."""

from __future__ import annotations

import http.client
import socket
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from zebra_day.cmd_mgr import ZebraPrinter
from zebra_day.logging_config import get_logger
from zebra_day.zpl_renderer import render_zpl_to_png

_log = get_logger(__name__)


def send_zpl_code(
    zpl_code: str,
    printer_ip: str,
    *,
    printer_port: int = 9100,
    timeout: float = 5.0,
) -> None:
    """Send raw ZPL to a printer over TCP."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect((printer_ip, printer_port))
        sock.sendall(zpl_code.encode())


def build_zpl(template_content: str, *, template_name: str | None = None, **fields: str) -> str:
    """Fill a ZPL template using zebra_day's supported fields."""
    payload = {
        "uid_barcode": "",
        "alt_a": "",
        "alt_b": "",
        "alt_c": "",
        "alt_d": "",
        "alt_e": "",
        "alt_f": "",
        "label_zpl_style": template_name or "",
        "rec_date": datetime.now().date().isoformat(),
    }
    payload.update({key: str(value or "") for key, value in fields.items()})
    try:
        return template_content.format(**payload)
    except KeyError as exc:
        missing = str(exc).strip("'")
        raise ValueError(f"Template requires missing field: {missing}") from exc


def render_zpl_preview(zpl_string: str, output_path: Path) -> Path:
    """Render a ZPL string to a PNG preview."""
    render_zpl_to_png(zpl_string, output_path)
    return output_path


def _http_probe(ip_address: str, port: int, timeout: float) -> dict[str, Any] | None:
    try:
        conn = http.client.HTTPConnection(ip_address, port=port, timeout=timeout)
        conn.request("GET", "/")
        response = conn.getresponse()
        body = response.read(4096).decode(errors="ignore")
        conn.close()
    except Exception:
        return None

    haystack = body.lower()
    if "zebra" not in haystack and "zpl" not in haystack:
        return None
    return {
        "printer_name": "",
        "model": "",
        "serial": "",
        "source": f"http({port})",
    }


def discover_printers(
    *,
    ip_stub: str,
    scan_wait: float,
    scan_http_port: int | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    """Perform a naive subnet scan for Zebra printers."""
    if ip_stub.endswith("."):
        raise ValueError(
            f"ip_stub must not end with a trailing dot: '{ip_stub}'. Use '{ip_stub.rstrip('.')}' instead."
        )

    results: list[dict[str, Any]] = []
    total = 254
    for offset in range(1, 255):
        ip_address = f"{ip_stub}.{offset}"
        if progress_callback is not None:
            progress_callback(
                {"kind": "checking", "checked": offset - 1, "total": total, "ip": ip_address}
            )

        source = ""
        model = ""
        serial = ""
        printer_name = ""

        device = ZebraPrinter(ip_address, port=9100)
        host_id = device.get_host_identification(timeout=scan_wait) or {}
        if host_id:
            source = "zpl"
            model = str(host_id.get("model") or "")
            serial = str(device.get_serial_number(timeout=scan_wait) or "")

        if not source and scan_http_port:
            http_probe = _http_probe(ip_address, scan_http_port, scan_wait)
            if http_probe:
                source = str(http_probe.get("source") or "")
                model = str(http_probe.get("model") or model)
                serial = str(http_probe.get("serial") or serial)
                printer_name = str(http_probe.get("printer_name") or "")

        if source:
            payload = {
                "printer_id": ip_address,
                "ip_address": ip_address,
                "printer_name": printer_name or ip_address,
                "manufacturer": "zebra",
                "model": model,
                "serial": serial,
                "notes": source,
                "state": "Unknown",
            }
            results.append(payload)
            if progress_callback is not None:
                progress_callback(
                    {
                        "kind": "found",
                        "ip": ip_address,
                        "model": model or "Unknown",
                        "serial": serial or "Unknown",
                    }
                )

    if progress_callback is not None:
        progress_callback({"kind": "done", "checked": total, "total": total})
    _log.info("Discovery scan complete for %s.*: %d printers found", ip_stub, len(results))
    return results
