"""Root-level commands (status, bootstrap) — cli-core-yo plugin."""

from __future__ import annotations

import os
import socket
from typing import TYPE_CHECKING, Any

import typer
from cli_core_yo import output
from cli_core_yo.runtime import get_context

from zebra_day import paths as xdg

if TYPE_CHECKING:
    from cli_core_yo.registry import CommandRegistry
    from cli_core_yo.spec import CliSpec


def register(registry: CommandRegistry, spec: CliSpec) -> None:
    """Register root-level status and bootstrap commands."""
    registry.add_command(
        None,
        "status",
        _status_callback,
        help_text="Show printer fleet status, network connectivity, and service health.",
    )
    registry.add_command(
        None,
        "bootstrap",
        _bootstrap_callback,
        help_text="Initialize configuration, scan for printers, and setup first-time environment.",
    )


def _status_callback() -> None:
    """Show printer fleet status, network connectivity, and service health."""
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
                total_printers = sum(
                    len(list(zp.printers["labs"][lab].keys())) for lab in labs
                )
                status_data["printers"]["configured"] = total_printers
        except Exception:
            pass

    if get_context().json_mode:
        output.emit_json(status_data)
        return

    # Human-readable output
    output.heading("Service Status")
    if status_data["gui_server"]["running"]:
        output.success(
            f"GUI Server: Running"
            f" (PID {status_data['gui_server']['pid']})"
        )
        output.detail(f"URL: {status_data['gui_server']['url']}")
    else:
        output.detail("GUI Server: Not running")

    output.heading("Printer Fleet")
    if status_data["config"]["exists"]:
        output.success("Config: Loaded")
        output.detail(f"Printers: {status_data['printers']['configured']}")
        output.detail(
            f"Labs: {', '.join(status_data['printers']['labs']) or 'none'}"
        )
    else:
        output.warning("Config: Not found")
        output.detail("Run 'zday bootstrap' to initialize")


def _bootstrap_callback(
    ip_stub: str | None = typer.Option(
        None, "--ip-stub", "-i", help="IP stub for printer scan (e.g., 192.168.1)"
    ),
    skip_scan: bool = typer.Option(
        False, "--skip-scan", "-s", help="Skip printer network scan"
    ),
    silent_scan: bool = typer.Option(
        False, "--silent-scan", help="Suppress per-IP scan output (show summary only)"
    ),
) -> None:
    """Initialize configuration, scan for printers, and setup first-time environment.

    This is the recommended first-time setup command. It will:
    1. Create XDG configuration directories
    2. Initialize printer configuration
    3. Scan the network for Zebra printers (unless --skip-scan)

    By default the scan prints each IP as it is probed and details for every
    printer discovered.  Use --silent-scan to suppress per-IP output and only
    show the final summary.
    """
    json_mode = get_context().json_mode

    config_dir = str(xdg.get_config_dir())
    data_dir = str(xdg.get_data_dir())
    printers_found = 0
    labs: list[str] = []

    # output.* primitives auto-suppress in json_mode
    output.heading("zebra_day Bootstrap")
    output.success("Config directory: " + config_dir)
    output.success("Data directory: " + data_dir)

    if skip_scan:
        output.detail("Skipping printer scan (--skip-scan)")
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

        if ip_stub.endswith("."):
            output.error(
                f"ip-stub must not end with a trailing dot: '{ip_stub}'. "
                f"Use '{ip_stub.rstrip('.')}' instead."
            )
            raise typer.Exit(1)

        output.action(f"Scanning network for Zebra printers ({ip_stub}.*)...")
        if silent_scan:
            output.detail("This may take a few minutes...")

        # Build progress callback for verbose (non-silent) scan output
        verbose_scan = not json_mode and not silent_scan

        def _scan_progress(event: dict) -> None:
            if not verbose_scan:
                return
            kind = event.get("kind")
            if kind == "checking":
                checked = event.get("checked", 0)
                total = event.get("total", 255)
                ip_addr = event.get("ip", "")
                output.print_text(
                    f"  [{checked + 1}/{total}] Probing {ip_addr}..."
                )
            elif kind == "found":
                ip_addr = event.get("ip", "")
                model = event.get("model", "Unknown")
                serial = event.get("serial", "Unknown")
                output.success(
                    f"Found printer at {ip_addr}"
                    f"  model={model}  serial={serial}"
                )
            elif kind == "done":
                checked = event.get("checked", 0)
                total = event.get("total", 255)
                output.detail(f"Scanned {checked}/{total} addresses")

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

            output.success(f"Scan complete: {printers_found} printer(s) found")
            if labs:
                output.detail(f"Labs: {', '.join(labs)}")
        except Exception as e:
            output.warning(f"Scan error: {e}")

    # Generate HTTPS certificates if mkcert is available
    certs_generated = False
    cert_path_str = None

    output.action("Checking HTTPS certificates...")

    try:
        from zebra_day import mkcert

        if not mkcert.is_mkcert_installed():
            output.warning("mkcert not installed")
            output.detail(
                "Install with: brew install mkcert (macOS) or "
                "sudo apt install mkcert (Ubuntu)"
            )
        elif not mkcert.is_ca_installed():
            output.warning("mkcert CA not installed")
            output.detail(
                "Run: mkcert -install (one-time, requires password)"
            )
        elif mkcert.certificates_exist():
            output.success(f"Certificates exist: {mkcert.CERT_FILE}")
            certs_generated = True
            cert_path_str = str(mkcert.CERT_FILE)
        else:
            output.detail("Generating certificates...")
            if mkcert.generate_certificates():
                output.success(
                    f"Certificates generated: {mkcert.CERT_FILE}"
                )
                certs_generated = True
                cert_path_str = str(mkcert.CERT_FILE)
            else:
                output.warning("Failed to generate certificates")
    except Exception as e:
        output.warning(f"Certificate check error: {e}")

    if json_mode:
        result = {
            "config_dir": config_dir,
            "data_dir": data_dir,
            "printers_found": printers_found,
            "labs": labs,
            "https_certs_generated": certs_generated,
            "cert_path": cert_path_str,
        }
        output.emit_json(result)
        return

    output.success("Bootstrap complete!")
    output.heading("Next steps")
    output.detail("zday gui start     Start the web UI")
    output.detail("zday printer list  Show configured printers")
    output.detail("zday info          Show configuration details")

