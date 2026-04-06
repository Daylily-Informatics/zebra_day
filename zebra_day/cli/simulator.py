"""CLI commands for the mock Zebra printer simulator."""

from __future__ import annotations

import signal
import time
from typing import TYPE_CHECKING

import typer
from cli_core_yo import ccyo_out

if TYPE_CHECKING:
    from cli_core_yo.registry import CommandRegistry
    from cli_core_yo.spec import CliSpec

sim_app = typer.Typer(help="Mock Zebra printer simulator for testing")

# Module-level manager keeps state while the CLI process is alive.
_manager = None


def _get_manager():
    """Lazy-init the SimulatorManager singleton."""
    global _manager
    if _manager is None:
        from zebra_day.simulator import SimulatorManager

        _manager = SimulatorManager()
    return _manager


@sim_app.command("start")
def sim_start(
    host: str = typer.Option("0.0.0.0", "--host", "-b", help="Bind address"),
    zpl_port: int = typer.Option(9100, "--zpl-port", "-z", help="ZPL TCP port (default 9100)"),
    http_port: int = typer.Option(18080, "--http-port", "-p", help="HTTP port (default 18080)"),
    model: str = typer.Option("ZD620-203dpi ZPL", "--model", "-m", help="Printer model string"),
    serial: str = typer.Option("SIM1001", "--serial", "-s", help="Serial number"),
    firmware: str = typer.Option("V84.20.21Z", "--firmware", help="Firmware version"),
    paper_out: bool = typer.Option(False, "--paper-out", help="Simulate paper-out condition"),
    ribbon_out: bool = typer.Option(False, "--ribbon-out", help="Simulate ribbon-out condition"),
    head_up: bool = typer.Option(False, "--head-up", help="Simulate head-up condition"),
    paused: bool = typer.Option(False, "--paused", help="Simulate paused state"),
    foreground: bool = typer.Option(
        False, "--foreground", "-f", help="Run in foreground (block until Ctrl+C)"
    ),
) -> None:
    """Start a simulated Zebra printer."""
    from zebra_day.simulator import PrinterProfile

    profile = PrinterProfile(
        model=model,
        serial=serial,
        firmware=firmware,
        paper_out=paper_out,
        ribbon_out=ribbon_out,
        head_up=head_up,
        paused=paused,
    )

    mgr = _get_manager()
    try:
        mgr.start_printer(host=host, zpl_port=zpl_port, http_port=http_port, profile=profile)
    except RuntimeError as exc:
        ccyo_out.error(str(exc))
        raise typer.Exit(1) from None
    except OSError as exc:
        ccyo_out.error(f"Cannot bind: {exc}")
        raise typer.Exit(1) from None

    ccyo_out.success(f"Simulator started: {model} (serial={serial})")
    ccyo_out.detail(f"ZPL: {host}:{zpl_port}  |  HTTP: http://{host}:{http_port}")

    if foreground:
        ccyo_out.action("Press Ctrl+C to stop")

        def _shutdown(signum, frame):
            ccyo_out.action("Shutting down simulator...")
            mgr.stop_all()
            raise typer.Exit(0)

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)
        try:
            while True:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            mgr.stop_all()


@sim_app.command("stop")
def sim_stop(
    host: str = typer.Option("0.0.0.0", "--host", "-b", help="Bind address"),
    zpl_port: int = typer.Option(9100, "--zpl-port", "-z", help="ZPL TCP port"),
    all_printers: bool = typer.Option(False, "--all", "-a", help="Stop all simulators"),
) -> None:
    """Stop a running simulator."""
    mgr = _get_manager()
    if all_printers:
        count = mgr.stop_all()
        ccyo_out.success(f"Stopped {count} simulator(s)")
        return
    if mgr.stop_printer(host, zpl_port):
        ccyo_out.success(f"Stopped simulator at {host}:{zpl_port}")
    else:
        ccyo_out.warning(f"No simulator found at {host}:{zpl_port}")


@sim_app.command("list")
def sim_list() -> None:
    """List all running simulators."""
    mgr = _get_manager()
    printers = mgr.list_printers()
    if not printers:
        ccyo_out.detail("No simulators running")
        return
    for p in printers:
        status = "running" if p["running"] else "stopped"
        ccyo_out.bullet(
            f"{p['model']} serial={p['serial']} "
            f"ZPL={p['host']}:{p['zpl_port']} HTTP={p['host']}:{p['http_port']} [{status}]"
        )


def register(registry: CommandRegistry, spec: CliSpec) -> None:
    """cli-core-yo plugin: register the simulator command group."""
    registry.add_typer_app(None, sim_app, "simulator", "Mock Zebra printer simulator")
