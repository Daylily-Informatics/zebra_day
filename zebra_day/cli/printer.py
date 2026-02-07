"""Printer fleet management commands for zebra_day CLI."""

from __future__ import annotations

import json
import socket
from typing import TYPE_CHECKING

import typer
from cli_core_yo import output
from rich.console import Console
from rich.table import Table

if TYPE_CHECKING:
    from cli_core_yo.registry import CommandRegistry
    from cli_core_yo.spec import CliSpec

printer_app = typer.Typer(help="Printer fleet management commands")
console = Console()  # retained for Rich Table rendering


def _get_local_ip() -> str:
    """Get local IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip: str = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


@printer_app.command("scan")
def scan(
    ip_stub: str | None = typer.Option(
        None, "--ip-stub", "-i", help="IP stub to scan (e.g., 192.168.1)"
    ),
    wait: float = typer.Option(0.5, "--wait", "-w", help="Seconds to wait per IP probe"),
    lab: str = typer.Option(
        "scan-results", "--lab", "-l", help="Lab name to assign found printers"
    ),
    display_name: str | None = typer.Option(
        None,
        "--display-name",
        help="Optional lab display name (user-friendly). Stored in config as lab_display_name.",
    ),
    description: str | None = typer.Option(
        None,
        "--description",
        help="Optional lab description. Stored in config as lab_description.",
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Scan network for Zebra printers."""
    # Determine IP stub if not provided
    if not ip_stub:
        local_ip = _get_local_ip()
        ip_stub = ".".join(local_ip.split(".")[:-1])

    if ip_stub.endswith("."):
        output.error(
            f"ip-stub must not end with a trailing dot: '{ip_stub}'. "
            f"Use '{ip_stub.rstrip('.')}' instead."
        )
        raise typer.Exit(1)

    if not json_output:
        output.action(f"Scanning {ip_stub}.* for Zebra printers...")
        output.detail("This may take a few minutes...")

    try:
        import zebra_day.print_mgr as zdpm

        zp = zdpm.zpl()
        zp.probe_zebra_printers_add_to_printers_json(
            ip_stub=ip_stub,
            scan_wait=str(wait),
            lab=lab,
            lab_description=description or "",
        )

        # Apply lab metadata updates (if explicitly provided)
        if display_name is not None or description is not None:
            try:
                zp.update_lab_metadata(
                    lab,
                    lab_display_name=display_name,
                    lab_description=description,
                    network_stub=ip_stub,
                )
            except Exception:
                # Non-fatal; scan results are still useful.
                pass

        found = []
        if hasattr(zp, "printers") and "labs" in zp.printers and lab in zp.printers["labs"]:
            lab_obj = zp.printers["labs"][lab]
            printers_obj = lab_obj.get("printers", {}) if isinstance(lab_obj, dict) else {}
            for name, info in printers_obj.items():
                if isinstance(info, dict) and info.get("ip_address") not in ["dl_png"]:
                    found.append(
                        {
                            "name": name,
                            "ip": info.get("ip_address"),
                            "model": info.get("model", "unknown"),
                            "serial": info.get("serial", "unknown"),
                        }
                    )

        if json_output:
            output.emit_json(found)
        else:
            output.success(f"Found {len(found)} printer(s)")
            if found:
                table = Table()
                table.add_column("Name", style="cyan")
                table.add_column("IP Address")
                table.add_column("Model")
                table.add_column("Serial")
                for p in found:
                    table.add_row(p["name"], p["ip"], p["model"], p["serial"])
                console.print(table)

    except Exception as e:
        if json_output:
            output.emit_json({"error": str(e)})
        else:
            output.error(f"Scan error: {e}")
        raise typer.Exit(1) from None


@printer_app.command("list")
def list_printers(
    lab: str | None = typer.Option(None, "--lab", "-l", help="Filter by lab name"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    live: bool = typer.Option(False, "--live", help="Query live status from printers"),
    timeout: float = typer.Option(
        2.0, "--timeout", "-t", help="Timeout per printer query (seconds)"
    ),
):
    """List configured printers with optional live status."""
    try:
        import zebra_day.cmd_mgr as zdcm
        import zebra_day.print_mgr as zdpm

        zp = zdpm.zpl()

        printers = []
        if hasattr(zp, "printers") and "labs" in zp.printers:
            for lab_name, lab_obj in zp.printers["labs"].items():
                if lab and lab_name != lab:
                    continue
                printers_obj = lab_obj.get("printers", {}) if isinstance(lab_obj, dict) else {}
                for name, info in printers_obj.items():
                    if isinstance(info, dict):
                        printers.append(
                            {
                                "lab": lab_name,
                                "name": name,
                                "ip": info.get("ip_address", "unknown"),
                                "model": info.get("model", "unknown"),
                                "styles": info.get("label_zpl_styles", []),
                            }
                        )

        # Query live status if requested
        if live and printers:
            if not json_output:
                output.action("Querying live status from printers...")
            for p in printers:
                ip = p.get("ip", "")
                if ip and ip not in ("unknown", "dl_png"):
                    status = zdcm.get_cached_status(ip, timeout=timeout)
                    p["online"] = status.get("online", False)
                    p["firmware"] = status.get("firmware")
                    p["live_model"] = status.get("model")
                    p["serial"] = status.get("serial")
                    p["label_count"] = status.get("label_count")
                    p["paused"] = status.get("paused", False)
                    p["paper_out"] = status.get("paper_out", False)
                    p["ribbon_out"] = status.get("ribbon_out", False)
                    p["head_up"] = status.get("head_up", False)
                    # Status = network reachability only (online/offline)
                    p["status"] = "online" if status.get("online") else "offline"
                    # State = operational status (Ready/Paused/Error/Offline/Unknown)
                    if not status.get("online"):
                        p["state"] = "Offline"
                    elif status.get("paused"):
                        p["state"] = "Paused"
                    elif (
                        status.get("paper_out") or status.get("ribbon_out") or status.get("head_up")
                    ):
                        p["state"] = "Error"
                    else:
                        p["state"] = "Ready"
                else:
                    p["online"] = None
                    p["status"] = "n/a"
                    p["state"] = "Unknown"

        if json_output:
            output.emit_json(printers)
            return

        if not printers:
            output.warning("No printers configured")
            output.detail("Run 'zday printer scan' to discover printers")
            return

        # If a lab filter is specified, show lab metadata first.
        if lab:
            try:
                meta = zp.get_lab_metadata(lab)
                output.detail(
                    f"Lab: {meta.get('lab')}  "
                    f"Display: {meta.get('lab_display_name')}  "
                    f"Stub: {meta.get('network_stub')}"
                )
                if meta.get("lab_description"):
                    output.detail(f"Description: {meta.get('lab_description')}")
            except Exception:
                pass

        table = Table(title="Configured Printers")
        table.add_column("Lab", style="cyan")
        table.add_column("Name")
        table.add_column("IP Address")
        table.add_column("Model")
        if live:
            table.add_column("Status")  # Network reachability
            table.add_column("State")  # Operational state
            table.add_column("Firmware")
            table.add_column("Labels")
        else:
            table.add_column("Label Styles")

        for p in printers:
            if live:
                # Status = network reachability (online/offline)
                status = p.get("status", "unknown")
                if status == "online":
                    status_str = "[green]● online[/green]"
                elif status == "offline":
                    status_str = "[red]○ offline[/red]"
                else:
                    status_str = "[dim]—[/dim]"

                # State = operational status (Ready/Paused/Error/Offline/Unknown)
                state = p.get("state", "Unknown")
                if state == "Ready":
                    state_str = "[green]✓ Ready[/green]"
                elif state == "Paused":
                    state_str = "[yellow]⏸ Paused[/yellow]"
                elif state == "Error":
                    flags = []
                    if p.get("paper_out"):
                        flags.append("paper")
                    if p.get("ribbon_out"):
                        flags.append("ribbon")
                    if p.get("head_up"):
                        flags.append("head")
                    state_str = f"[red]⚠ Error ({','.join(flags)})[/red]"
                elif state == "Offline":
                    state_str = "[red]○ Offline[/red]"
                else:
                    state_str = "[dim]? Unknown[/dim]"

                firmware = p.get("firmware") or "—"
                labels = str(p.get("label_count")) if p.get("label_count") is not None else "—"
                model = p.get("live_model") or p["model"]
                table.add_row(
                    p["lab"], p["name"], p["ip"], model, status_str, state_str, firmware, labels
                )
            else:
                styles = ", ".join(p["styles"][:2])
                if len(p["styles"]) > 2:
                    styles += f" (+{len(p['styles']) - 2})"
                table.add_row(p["lab"], p["name"], p["ip"], p["model"], styles)
        console.print(table)

    except Exception as e:
        if json_output:
            output.emit_json({"error": str(e)})
        else:
            output.error(f"Error: {e}")
        raise typer.Exit(1) from None


@printer_app.command("test")
def test_print(
    printer_name: str = typer.Argument(..., help="Printer name or IP address"),
    lab: str = typer.Option("scan-results", "--lab", "-l", help="Lab containing the printer"),
    label_style: str = typer.Option("tube_2inX1in", "--style", "-s", help="Label style to print"),
):
    """Send a test print to a specific printer."""
    try:
        import zebra_day.print_mgr as zdpm

        zp = zdpm.zpl()

        output.action(f"Sending test print to {printer_name}...")
        zp.print_zpl(
            lab=lab,
            printer_name=printer_name,
            uid_barcode="TEST-PRINT",
            alt_a="Test Label",
            alt_b="zebra_day CLI",
            label_zpl_style=label_style,
        )
        output.success("Test print sent successfully")

    except Exception as e:
        output.error(f"Print error: {e}")
        raise typer.Exit(1) from None


def register(registry: CommandRegistry, spec: CliSpec) -> None:
    """cli-core-yo plugin: register the printer command group."""
    registry.add_typer_app(None, printer_app, "printer", "Printer fleet management commands")
