"""Printer fleet management commands for zebra_day CLI."""

import json
import socket
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from zebra_day import paths as xdg

printer_app = typer.Typer(help="Printer fleet management commands")
console = Console()


def _get_local_ip() -> str:
    """Get local IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


@printer_app.command("scan")
def scan(
    ip_stub: Optional[str] = typer.Option(None, "--ip-stub", "-i", help="IP stub to scan (e.g., 192.168.1)"),
    wait: float = typer.Option(0.25, "--wait", "-w", help="Seconds to wait per IP probe"),
    lab: str = typer.Option("scan-results", "--lab", "-l", help="Lab name to assign found printers"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Scan network for Zebra printers."""
    # Determine IP stub if not provided
    if not ip_stub:
        local_ip = _get_local_ip()
        ip_stub = ".".join(local_ip.split(".")[:-1])

    if not json_output:
        console.print(f"[cyan]→[/cyan] Scanning {ip_stub}.* for Zebra printers...")
        console.print("[dim]  This may take a few minutes...[/dim]")

    try:
        import zebra_day.print_mgr as zdpm
        zp = zdpm.zpl()
        zp.probe_zebra_printers_add_to_printers_json(
            ip_stub=ip_stub,
            scan_wait=str(wait),
            lab=lab,
        )

        found = []
        if hasattr(zp, "printers") and "labs" in zp.printers and lab in zp.printers["labs"]:
            for name, info in zp.printers["labs"][lab].items():
                if isinstance(info, dict) and info.get("ip_address") not in ["dl_png"]:
                    found.append({
                        "name": name,
                        "ip": info.get("ip_address"),
                        "model": info.get("model", "unknown"),
                        "serial": info.get("serial", "unknown"),
                    })

        if json_output:
            console.print(json.dumps(found, indent=2))
        else:
            console.print(f"\n[green]✓[/green] Found {len(found)} printer(s)")
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
            console.print(json.dumps({"error": str(e)}))
        else:
            console.print(f"[red]✗[/red] Scan error: {e}")
        raise typer.Exit(1)


@printer_app.command("list")
def list_printers(
    lab: Optional[str] = typer.Option(None, "--lab", "-l", help="Filter by lab name"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """List configured printers."""
    try:
        import zebra_day.print_mgr as zdpm
        zp = zdpm.zpl()

        printers = []
        if hasattr(zp, "printers") and "labs" in zp.printers:
            for lab_name, lab_printers in zp.printers["labs"].items():
                if lab and lab_name != lab:
                    continue
                for name, info in lab_printers.items():
                    if isinstance(info, dict):
                        printers.append({
                            "lab": lab_name,
                            "name": name,
                            "ip": info.get("ip_address", "unknown"),
                            "model": info.get("model", "unknown"),
                            "styles": info.get("label_zpl_styles", []),
                        })

        if json_output:
            console.print(json.dumps(printers, indent=2))
            return

        if not printers:
            console.print("[yellow]⚠[/yellow] No printers configured")
            console.print("   Run [cyan]zday printer scan[/cyan] to discover printers")
            return

        table = Table(title="Configured Printers")
        table.add_column("Lab", style="cyan")
        table.add_column("Name")
        table.add_column("IP Address")
        table.add_column("Model")
        table.add_column("Label Styles")
        for p in printers:
            styles = ", ".join(p["styles"][:2])
            if len(p["styles"]) > 2:
                styles += f" (+{len(p['styles'])-2})"
            table.add_row(p["lab"], p["name"], p["ip"], p["model"], styles)
        console.print(table)

    except Exception as e:
        if json_output:
            console.print(json.dumps({"error": str(e)}))
        else:
            console.print(f"[red]✗[/red] Error: {e}")
        raise typer.Exit(1)


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

        console.print(f"[cyan]→[/cyan] Sending test print to {printer_name}...")
        result = zp.print_zpl(
            lab=lab,
            printer_name=printer_name,
            uid_barcode="TEST-PRINT",
            alt_a="Test Label",
            alt_b="zebra_day CLI",
            label_zpl_style=label_style,
        )
        console.print(f"[green]✓[/green] Test print sent successfully")

    except Exception as e:
        console.print(f"[red]✗[/red] Print error: {e}")
        raise typer.Exit(1)

