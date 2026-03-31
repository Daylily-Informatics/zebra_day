"""Printer fleet commands for zebra_day."""

from __future__ import annotations

import socket
from typing import TYPE_CHECKING, Any

import typer
from cli_core_yo import output
from cli_core_yo.runtime import get_context

from zebra_day.client import ZebraDayClient
from zebra_day.cmd_mgr import get_cached_status

if TYPE_CHECKING:
    from cli_core_yo.registry import CommandRegistry
    from cli_core_yo.spec import CliSpec

printer_app = typer.Typer(help="TapDB-backed printer fleet commands")


def _local_ip_stub() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect(("8.8.8.8", 80))
        return ".".join(probe.getsockname()[0].split(".")[:-1])


@printer_app.command("list")
def list_printers(
    lab: str | None = typer.Option(None, "--lab", help="Filter printers by lab"),
    live: bool = typer.Option(False, "--live", help="Fetch current live printer state"),
    timeout: float = typer.Option(2.0, "--timeout", help="Live status timeout"),
) -> None:
    client = ZebraDayClient.from_context()
    rows: list[dict[str, Any]] = []
    for printer in client.list_printers(lab):
        payload = printer.to_payload()
        if live and payload["ip_address"]:
            status = get_cached_status(payload["ip_address"], timeout=timeout)
            payload["live_status"] = status
            payload["online"] = bool(status.get("online"))
        rows.append(payload)

    if get_context().json_mode:
        output.emit_json(rows)
        return

    if not rows:
        output.warning("No printers found")
        return

    for row in rows:
        header = f"{row['lab']}/{row['printer_id']}  {row['ip_address']}"
        output.bullet(header)
        output.detail(
            f"name={row['printer_name'] or '-'} model={row['model'] or '-'} serial={row['serial'] or '-'}"
        )
        output.detail(
            f"default_profile={row['default_label_profile'] or '-'} "
            f"profiles={','.join(row['label_profiles']) or '-'} "
            f"status={row['status'] or '-'} state={row['state'] or '-'}"
        )
        if live:
            live_status = row.get("live_status") or {}
            output.detail(
                f"live_online={bool(live_status.get('online'))} "
                f"paused={bool(live_status.get('paused'))} "
                f"paper_out={bool(live_status.get('paper_out'))}"
            )


@printer_app.command("scan")
def scan(
    lab: str = typer.Option("default", "--lab", help="Lab to assign discovered printers to"),
    ip_stub: str | None = typer.Option(
        None,
        "--ip-stub",
        help="IP stub to scan, e.g. 192.168.1",
    ),
    scan_http_port: int | None = typer.Option(
        None,
        "--scan-http-port",
        help="Optional HTTP port to probe alongside ZPL",
    ),
) -> None:
    client = ZebraDayClient.from_context()
    resolved_ip_stub = ip_stub or _local_ip_stub()
    found = client.discover_printers(
        ip_stub=resolved_ip_stub,
        lab=lab,
        scan_http_port=scan_http_port,
    )
    payload = [printer.to_payload() for printer in found]
    if get_context().json_mode:
        output.emit_json(payload)
        return
    output.success(f"Discovered {len(found)} printer(s) in lab '{lab}'")
    for printer in found:
        output.bullet(
            f"{printer.printer_id} {printer.ip_address} {printer.model or '-'} {printer.serial or '-'}"
        )


@printer_app.command("sync")
def sync(
    lab: str = typer.Option(..., "--lab", help="Lab containing the printer"),
    printer_id: str = typer.Argument(..., help="Printer ID to sync"),
) -> None:
    client = ZebraDayClient.from_context()
    printer = client.sync_printer_metadata(printer_id, lab)
    payload = printer.to_payload()
    if get_context().json_mode:
        output.emit_json(payload)
        return
    output.success(f"Synchronized {lab}/{printer_id}")
    output.detail(f"Model: {payload['model'] or '-'}")
    output.detail(f"Serial: {payload['serial'] or '-'}")


def register(registry: CommandRegistry, spec: CliSpec) -> None:
    del spec
    registry.add_typer_app(None, printer_app, "printer", "Printer fleet operations")
