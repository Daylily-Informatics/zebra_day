"""zebra_day CLI - Zebra Printer Fleet Management CLI using Typer."""

from __future__ import annotations

import os
import socket
import sys
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from zebra_day import paths as xdg
from zebra_day.cli.cognito import cognito_app
from zebra_day.cli.config import config_app
from zebra_day.cli.dynamo import dynamo_app
from zebra_day.cli.env import env_app
from zebra_day.cli.gui import gui_app
from zebra_day.cli.printer import printer_app
from zebra_day.cli.template import template_app

console = Console()

app = typer.Typer(
    name="zday",
    help="zebra_day - Zebra Printer Fleet Management CLI",
    add_completion=True,
    no_args_is_help=True,
)

# Register subcommand groups
app.add_typer(gui_app, name="gui", help="Web UI server management")
app.add_typer(printer_app, name="printer", help="Printer fleet management")
app.add_typer(template_app, name="template", help="ZPL template management")
app.add_typer(config_app, name="config", help="Configuration management")
app.add_typer(env_app, name="env", help="Development environment management")
app.add_typer(cognito_app, name="cognito", help="Cognito authentication management")
app.add_typer(dynamo_app, name="dynamo", help="DynamoDB shared configuration management")


def _get_version() -> str:
    """Get zebra_day version."""
    try:
        from importlib.metadata import version

        return version("zebra_day")
    except Exception:
        return "dev"


@app.command("version")
def version():
    """Show zebra_day version."""
    console.print(f"zebra_day [cyan]{_get_version()}[/cyan]")


@app.command("info")
def info():
    """Show zebra_day configuration and status."""
    table = Table(title="zebra_day Info")
    table.add_column("Property", style="cyan")
    table.add_column("Value")

    # Version
    table.add_row("Version", _get_version())
    table.add_row("Python", sys.version.split()[0])

    # XDG Paths
    table.add_row("Config Dir", str(xdg.get_config_dir()))
    table.add_row("Data Dir", str(xdg.get_data_dir()))
    table.add_row("Logs Dir", str(xdg.get_logs_dir()))
    table.add_row("Cache Dir", str(xdg.get_cache_dir()))

    # Config file (YAML preferred, JSON fallback)
    yaml_cfg = xdg.get_config_file_path()
    json_cfg = xdg.get_legacy_json_config_path()
    if yaml_cfg.exists():
        table.add_row("Config File", f"[green]{yaml_cfg}[/green]")
    elif json_cfg.exists():
        table.add_row("Config File", f"[yellow]{json_cfg}[/yellow] [dim](legacy JSON)[/dim]")
    else:
        table.add_row("Config File", f"[yellow]not found[/yellow] [dim]({yaml_cfg})[/dim]")

    # Check if GUI server is running
    pid_file = xdg.get_state_dir() / "gui.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)
            table.add_row("GUI Server", f"[green]Running[/green] (PID {pid})")
        except (ValueError, ProcessLookupError, PermissionError):
            table.add_row("GUI Server", "[dim]Stopped[/dim]")
    else:
        table.add_row("GUI Server", "[dim]Stopped[/dim]")

    console.print(table)


@app.command("status")
def status(
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Show printer fleet status, network connectivity, and service health."""
    import json as json_mod

    status_data: dict[str, dict[str, Any]] = {
        "gui_server": {"running": False, "pid": None, "url": None},
        "printers": {"configured": 0, "labs": []},
        "config": {"exists": False, "path": None},
    }

    # Check GUI server
    pid_file = xdg.get_state_dir() / "gui.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)
            status_data["gui_server"]["running"] = True
            status_data["gui_server"]["pid"] = pid
            status_data["gui_server"]["url"] = "http://0.0.0.0:8118"
        except (ValueError, ProcessLookupError, PermissionError):
            pass

    # Check printer config
    printer_cfg = xdg.get_printer_config_path()
    status_data["config"]["path"] = str(printer_cfg)
    if printer_cfg.exists():
        status_data["config"]["exists"] = True
        try:
            import zebra_day.print_mgr as zdpm

            zp = zdpm.zpl()
            if hasattr(zp, "printers") and "labs" in zp.printers:
                labs = list(zp.printers["labs"].keys())
                status_data["printers"]["labs"] = labs
                total_printers = sum(len(list(zp.printers["labs"][lab].keys())) for lab in labs)
                status_data["printers"]["configured"] = total_printers
        except Exception:
            pass

    if json_output:
        console.print(json_mod.dumps(status_data, indent=2))
        return

    # Human-readable output
    console.print("\n[bold]Service Status[/bold]")
    if status_data["gui_server"]["running"]:
        console.print(
            f"  [green]●[/green] GUI Server: [green]Running[/green] (PID {status_data['gui_server']['pid']})"
        )
        console.print(f"    URL: [cyan]{status_data['gui_server']['url']}[/cyan]")
    else:
        console.print("  [dim]○[/dim] GUI Server: [dim]Not running[/dim]")

    console.print("\n[bold]Printer Fleet[/bold]")
    if status_data["config"]["exists"]:
        console.print("  [green]●[/green] Config: [green]Loaded[/green]")
        console.print(f"    Printers: {status_data['printers']['configured']}")
        console.print(f"    Labs: {', '.join(status_data['printers']['labs']) or 'none'}")
    else:
        console.print("  [yellow]○[/yellow] Config: [yellow]Not found[/yellow]")
        console.print("    Run [cyan]zday bootstrap[/cyan] to initialize")
    console.print()


@app.command("bootstrap")
def bootstrap(
    ip_stub: str | None = typer.Option(
        None, "--ip-stub", "-i", help="IP stub for printer scan (e.g., 192.168.1)"
    ),
    skip_scan: bool = typer.Option(False, "--skip-scan", "-s", help="Skip printer network scan"),
    silent_scan: bool = typer.Option(
        False, "--silent-scan", help="Suppress per-IP scan output (show summary only)"
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Initialize configuration, scan for printers, and setup first-time environment.

    This is the recommended first-time setup command. It will:
    1. Create XDG configuration directories
    2. Initialize printer configuration
    3. Scan the network for Zebra printers (unless --skip-scan)

    By default the scan prints each IP as it is probed and details for every
    printer discovered.  Use --silent-scan to suppress per-IP output and only
    show the final summary.
    """
    import json as json_mod

    config_dir = str(xdg.get_config_dir())
    data_dir = str(xdg.get_data_dir())
    printers_found = 0
    labs: list[str] = []

    if not json_output:
        console.print("\n[bold cyan]zebra_day Bootstrap[/bold cyan]\n")
        console.print("[green]✓[/green] Config directory: " + config_dir)
        console.print("[green]✓[/green] Data directory: " + data_dir)

    if skip_scan:
        if not json_output:
            console.print("[dim]Skipping printer scan (--skip-scan)[/dim]")
    else:
        # Determine IP stub
        if not ip_stub:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
                s.close()
                ip_stub = ".".join(local_ip.split(".")[:-1])
            except Exception:
                ip_stub = "192.168.1"

        if not json_output:
            console.print(f"\n[cyan]→[/cyan] Scanning network for Zebra printers ({ip_stub}.*)...")
            if silent_scan:
                console.print("[dim]  This may take a few minutes...[/dim]")

        # Build progress callback for verbose (non-silent) scan output
        verbose_scan = not json_output and not silent_scan

        def _scan_progress(event: dict) -> None:
            if not verbose_scan:
                return
            kind = event.get("kind")
            if kind == "checking":
                checked = event.get("checked", 0)
                total = event.get("total", 255)
                ip_addr = event.get("ip", "")
                console.print(
                    f"  [dim][{checked + 1}/{total}][/dim] Probing {ip_addr}...",
                    end="\r",
                )
            elif kind == "found":
                ip_addr = event.get("ip", "")
                model = event.get("model", "Unknown")
                serial = event.get("serial", "Unknown")
                console.print(
                    f"  [green]★[/green] Found printer at [bold]{ip_addr}[/bold]"
                    f"  model=[cyan]{model}[/cyan]  serial=[dim]{serial}[/dim]"
                )
            elif kind == "done":
                checked = event.get("checked", 0)
                total = event.get("total", 255)
                # Clear the last \r line
                console.print(f"  [dim]Scanned {checked}/{total} addresses[/dim]    ")

        try:
            import zebra_day.print_mgr as zdpm

            zp = zdpm.zpl()
            zp.probe_zebra_printers_add_to_printers_json(
                ip_stub=ip_stub,
                progress_callback=_scan_progress,
            )

            if hasattr(zp, "printers") and "labs" in zp.printers:
                for lab in zp.printers["labs"]:
                    printers_in_lab = len(list(zp.printers["labs"][lab].keys()))
                    printers_found += printers_in_lab
                    labs.append(lab)

            if not json_output:
                console.print(f"[green]✓[/green] Scan complete: {printers_found} printer(s) found")
                if labs:
                    console.print(f"    Labs: {', '.join(labs)}")
        except Exception as e:
            if not json_output:
                console.print(f"[yellow]⚠[/yellow] Scan error: {e}")

    # Generate HTTPS certificates if mkcert is available
    certs_generated = False
    cert_path_str = None

    if not json_output:
        console.print("\n[cyan]→[/cyan] Checking HTTPS certificates...")

    try:
        from zebra_day import mkcert

        if not mkcert.is_mkcert_installed():
            if not json_output:
                console.print("[yellow]⚠[/yellow]  mkcert not installed")
                console.print(
                    "   Install with: [dim]brew install mkcert[/dim] (macOS) or "
                    "[dim]sudo apt install mkcert[/dim] (Ubuntu)"
                )
        elif not mkcert.is_ca_installed():
            if not json_output:
                console.print("[yellow]⚠[/yellow]  mkcert CA not installed")
                console.print("   Run: [dim]mkcert -install[/dim] (one-time, requires password)")
        elif mkcert.certificates_exist():
            if not json_output:
                console.print(f"[green]✓[/green] Certificates exist: {mkcert.CERT_FILE}")
            certs_generated = True
            cert_path_str = str(mkcert.CERT_FILE)
        else:
            if not json_output:
                console.print("   Generating certificates...")
            if mkcert.generate_certificates():
                if not json_output:
                    console.print(f"[green]✓[/green] Certificates generated: {mkcert.CERT_FILE}")
                certs_generated = True
                cert_path_str = str(mkcert.CERT_FILE)
            else:
                if not json_output:
                    console.print("[yellow]⚠[/yellow]  Failed to generate certificates")
    except Exception as e:
        if not json_output:
            console.print(f"[yellow]⚠[/yellow] Certificate check error: {e}")

    if json_output:
        result = {
            "config_dir": config_dir,
            "data_dir": data_dir,
            "printers_found": printers_found,
            "labs": labs,
            "https_certs_generated": certs_generated,
            "cert_path": cert_path_str,
        }
        console.print(json_mod.dumps(result, indent=2))
    else:
        console.print("\n[bold green]✓ Bootstrap complete![/bold green]")
        console.print("\n[bold]Next steps:[/bold]")
        console.print("  zday gui start     Start the web UI")
        console.print("  zday printer list  Show configured printers")
        console.print("  zday info          Show configuration details")
        console.print()


def main():
    """Main CLI entry point."""
    app()


if __name__ == "__main__":
    raise SystemExit(main())
