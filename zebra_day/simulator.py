"""Mock Zebra printer simulator for testing network scanner and ZPL queries.

Provides two server components per simulated printer:
- **ZplServer** (TCP, default port 9100): responds to ZPL host queries
- **HttpServer** (HTTP, default port 80): serves a Zebra-like web page for scanner discovery

Usage (programmatic)::

    from zebra_day.simulator import SimulatedPrinter, PrinterProfile

    profile = PrinterProfile(model="ZD620-203dpi ZPL", serial="SIM1001")
    printer = SimulatedPrinter("127.0.0.1", zpl_port=9100, http_port=18080, profile=profile)
    printer.start()
    # ... run tests ...
    printer.stop()
"""

from __future__ import annotations

import html as html_mod
import logging
import socketserver
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Printer profile — all configurable attributes for a simulated printer
# ---------------------------------------------------------------------------


@dataclass
class PrinterProfile:
    """Configuration for a single simulated Zebra printer."""

    model: str = "ZD620-203dpi ZPL"
    serial: str = "SIM1001"
    firmware: str = "V84.20.21Z"
    dpi: str = "8"
    memory: str = "8192KB"
    label_count: int = 12345
    total_inches: int = 50000
    paused: bool = False
    paper_out: bool = False
    ribbon_out: bool = False
    head_up: bool = False

    # Friendly name shown in HTML title
    friendly_name: str = ""

    def __post_init__(self) -> None:
        if not self.friendly_name:
            short_model = self.model.split("-")[0] if "-" in self.model else self.model
            self.friendly_name = f"Zebra {short_model}"


# ---------------------------------------------------------------------------
# ZPL TCP server (port 9100)
# ---------------------------------------------------------------------------


class _ZplHandler(socketserver.StreamRequestHandler):
    """Handle a single ZPL TCP connection."""

    def handle(self) -> None:  # noqa: C901
        profile: PrinterProfile = self.server._profile  # type: ignore[attr-defined]
        try:
            data = self.request.recv(4096)
        except OSError:
            return
        if not data:
            return
        cmd = data.decode(errors="ignore").strip()
        response = _build_zpl_response(cmd, profile)
        if response is not None:
            try:
                self.request.sendall(response.encode())
            except OSError:
                pass


def _build_zpl_response(cmd: str, p: PrinterProfile) -> str | None:
    """Return the response string for a ZPL command, or None if unknown."""
    if cmd == "~HI":
        return f"\x02{p.model},{p.firmware},{p.dpi},{p.memory}\r\n\x03"
    if cmd == "~HQSN":
        return f"\x02SERIAL NUMBER\r\n{p.serial}\r\n\x03"
    if cmd == "~HQES":
        return "\x02ERROR STATUS\r\n0000 0000 0000 0000\r\n\x03"
    if cmd == "~HQOD":
        return f"\x02ODOMETER\r\nLABEL: {p.label_count}\r\nTOTAL INCHES: {p.total_inches}\r\n\x03"
    if cmd == "~HS":
        pause = "1" if p.paused else "0"
        paper = "1" if p.paper_out else "0"
        head = "1" if p.head_up else "0"
        ribbon = "1" if p.ribbon_out else "0"
        line1 = f"\x020000,0,{pause},0000,000,{paper},{head},{ribbon},000,0,0,0\r\n"
        line2 = "000,0,0,0,0,0,0,0,0000,0\r\n"
        line3 = "000,0\r\n\x03"
        return line1 + line2 + line3
    if cmd == "^XA^HH^XZ":
        return (
            f"\x02PRINTER CONFIGURATION\r\n"
            f"Model: {p.model}\r\n"
            f"Serial: {p.serial}\r\n"
            f"Firmware: {p.firmware}\r\n"
            f"DPI: {p.dpi}\r\n"
            f"Memory: {p.memory}\r\n"
            f"Label Count: {p.label_count}\r\n\x03"
        )
    # Unknown command — real printers often just ignore these
    return None


# ---------------------------------------------------------------------------
# HTTP server (port 80) — Zebra-like web page for scanner discovery
# ---------------------------------------------------------------------------


def _make_http_handler_class(profile: PrinterProfile) -> type:
    """Factory: returns a BaseHTTPRequestHandler subclass bound to *profile*."""

    class _Handler(BaseHTTPRequestHandler):
        _profile = profile

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            _log.debug("HTTP %s %s", self.address_string(), format % args)

        def do_GET(self) -> None:  # noqa: N802
            p = self._profile
            safe_model = html_mod.escape(p.model)
            safe_serial = html_mod.escape(p.serial)
            safe_name = html_mod.escape(p.friendly_name)
            body = (
                f"<html><head><title>{safe_name} - ZebraLink</title></head>"
                f"<body>"
                f"<h1>{safe_name}</h1>"
                f"<p>Model: {safe_model}</p>"
                f"<p>Serial Number: {safe_serial}</p>"
                f"<p>Firmware: {html_mod.escape(p.firmware)}</p>"
                f"<p>Powered by Link-OS</p>"
                f"</body></html>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Server", "Zebra Print Server")
            self.end_headers()
            self.wfile.write(body.encode())

    return _Handler


# ---------------------------------------------------------------------------
# SimulatedPrinter — bundles both servers for one printer instance
# ---------------------------------------------------------------------------


class SimulatedPrinter:
    """Manages a ZPL + HTTP server pair for a single simulated printer."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        zpl_port: int = 9100,
        http_port: int = 8080,
        profile: PrinterProfile | None = None,
    ) -> None:
        self.host = host
        self.zpl_port = zpl_port
        self.http_port = http_port
        self.profile = profile or PrinterProfile()
        self._zpl_server: socketserver.TCPServer | None = None
        self._http_server: HTTPServer | None = None
        self._zpl_thread: threading.Thread | None = None
        self._http_thread: threading.Thread | None = None
        self._running = False

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        """Start both servers in background threads."""
        if self._running:
            return

        # ZPL server
        socketserver.TCPServer.allow_reuse_address = True
        self._zpl_server = socketserver.TCPServer((self.host, self.zpl_port), _ZplHandler)
        self._zpl_server._profile = self.profile  # type: ignore[attr-defined]
        self._zpl_thread = threading.Thread(
            target=self._zpl_server.serve_forever,
            name=f"sim-zpl-{self.host}:{self.zpl_port}",
            daemon=True,
        )
        self._zpl_thread.start()

        # HTTP server
        handler_cls = _make_http_handler_class(self.profile)
        self._http_server = HTTPServer((self.host, self.http_port), handler_cls)
        self._http_thread = threading.Thread(
            target=self._http_server.serve_forever,
            name=f"sim-http-{self.host}:{self.http_port}",
            daemon=True,
        )
        self._http_thread.start()

        self._running = True
        _log.info(
            "Simulated printer started: %s (ZPL=%s:%d, HTTP=%s:%d)",
            self.profile.model,
            self.host,
            self.zpl_port,
            self.host,
            self.http_port,
        )

    def stop(self) -> None:
        """Shut down both servers."""
        if not self._running:
            return
        if self._zpl_server:
            self._zpl_server.shutdown()
            self._zpl_server.server_close()
        if self._http_server:
            self._http_server.shutdown()
            self._http_server.server_close()
        self._running = False
        _log.info("Simulated printer stopped: %s:%d", self.host, self.zpl_port)

    @property
    def running(self) -> bool:
        return self._running

    def info(self) -> dict[str, Any]:
        """Return a summary dict for display/serialization."""
        return {
            "host": self.host,
            "zpl_port": self.zpl_port,
            "http_port": self.http_port,
            "model": self.profile.model,
            "serial": self.profile.serial,
            "firmware": self.profile.firmware,
            "running": self._running,
        }


# ---------------------------------------------------------------------------
# SimulatorManager — manage a fleet of simulated printers
# ---------------------------------------------------------------------------


class SimulatorManager:
    """Track and manage multiple SimulatedPrinter instances."""

    def __init__(self) -> None:
        self._printers: dict[str, SimulatedPrinter] = {}  # key = "host:zpl_port"

    @staticmethod
    def _key(host: str, zpl_port: int) -> str:
        return f"{host}:{zpl_port}"

    def start_printer(
        self,
        host: str = "127.0.0.1",
        zpl_port: int = 9100,
        http_port: int = 8080,
        profile: PrinterProfile | None = None,
    ) -> SimulatedPrinter:
        """Start a new simulated printer. Raises if already running at that address."""
        key = self._key(host, zpl_port)
        if key in self._printers and self._printers[key].running:
            raise RuntimeError(f"Simulator already running at {key}")

        printer = SimulatedPrinter(
            host=host, zpl_port=zpl_port, http_port=http_port, profile=profile
        )
        printer.start()
        self._printers[key] = printer
        return printer

    def stop_printer(self, host: str, zpl_port: int = 9100) -> bool:
        """Stop a running simulator. Returns True if found and stopped."""
        key = self._key(host, zpl_port)
        printer = self._printers.pop(key, None)
        if printer is None:
            return False
        printer.stop()
        return True

    def stop_all(self) -> int:
        """Stop all simulators. Returns count stopped."""
        count = 0
        for printer in list(self._printers.values()):
            printer.stop()
            count += 1
        self._printers.clear()
        return count

    def list_printers(self) -> list[dict[str, Any]]:
        """Return info dicts for all managed printers."""
        return [p.info() for p in self._printers.values()]

    def get(self, host: str, zpl_port: int = 9100) -> SimulatedPrinter | None:
        """Get a specific printer instance."""
        return self._printers.get(self._key(host, zpl_port))
