"""Log inspection commands for zebra_day."""

from __future__ import annotations

from typing import TYPE_CHECKING

import typer
from cli_core_yo import ccyo_out

from zebra_day.settings import ZebraDaySettings

if TYPE_CHECKING:
    from cli_core_yo.registry import CommandRegistry
    from cli_core_yo.spec import CliSpec

logs_app = typer.Typer(help="Inspect zebra_day log files")


def _latest_log(settings: ZebraDaySettings):
    logs = sorted(settings.logs_dir.glob("gui_*.log"), reverse=True)
    return logs[0] if logs else None


@logs_app.command("path")
def path() -> None:
    settings = ZebraDaySettings.from_context()
    ccyo_out.print_text(str(settings.logs_dir))


@logs_app.command("latest")
def latest() -> None:
    settings = ZebraDaySettings.from_context()
    latest_file = _latest_log(settings)
    if latest_file is None:
        ccyo_out.warning("No GUI logs found")
        raise typer.Exit(1)
    ccyo_out.print_text(str(latest_file))


@logs_app.command("show")
def show(
    lines: int = typer.Option(80, "--lines", "-n", help="Number of lines to show"),
) -> None:
    settings = ZebraDaySettings.from_context()
    latest_file = _latest_log(settings)
    if latest_file is None:
        ccyo_out.warning("No GUI logs found")
        raise typer.Exit(1)
    content = latest_file.read_text(encoding="utf-8").splitlines()
    ccyo_out.print_text("\n".join(content[-lines:]))


def register(registry: CommandRegistry, spec: CliSpec) -> None:
    del spec
    registry.add_typer_app(None, logs_app, "logs", "Inspect zebra_day logs")
