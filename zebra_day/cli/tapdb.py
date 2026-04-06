"""TapDB passthrough commands for zebra_day."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import typer
from cli_core_yo import ccyo_out

from zebra_day.settings import ZebraDaySettings

if TYPE_CHECKING:
    from cli_core_yo.registry import CommandRegistry
    from cli_core_yo.spec import CliSpec

tapdb_app = typer.Typer(help="TapDB lifecycle wrappers")
bootstrap_app = typer.Typer(help="TapDB bootstrap wrappers")
tapdb_app.add_typer(bootstrap_app, name="bootstrap")


def _run_tapdb(settings: ZebraDaySettings, args: list[str]) -> None:
    result = subprocess.run(
        [
            "tapdb",
            "--config",
            str(settings.tapdb_config_path),
            "--env",
            settings.tapdb_env,
            *args,
        ],
        capture_output=True,
        text=True,
    )
    if result.stdout:
        ccyo_out.print_text(result.stdout.rstrip())
    if result.returncode != 0:
        if result.stderr:
            ccyo_out.error(result.stderr.strip())
        raise typer.Exit(result.returncode)


@bootstrap_app.command("local")
def bootstrap_local(
    no_gui: bool = typer.Option(True, "--no-gui/--gui", help="Skip or start the TapDB GUI"),
) -> None:
    args = ["bootstrap", "local"]
    if no_gui:
        args.append("--no-gui")
    _run_tapdb(ZebraDaySettings.from_context(), args)


@tapdb_app.command(
    "db",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def db_passthrough(ctx: typer.Context) -> None:
    if not ctx.args:
        ccyo_out.error("Missing tapdb db arguments")
        raise typer.Exit(1)
    _run_tapdb(ZebraDaySettings.from_context(), ["db", *ctx.args])


@tapdb_app.command(
    "pg",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def pg_passthrough(ctx: typer.Context) -> None:
    if not ctx.args:
        ccyo_out.error("Missing tapdb pg arguments")
        raise typer.Exit(1)
    _run_tapdb(ZebraDaySettings.from_context(), ["pg", *ctx.args])


@tapdb_app.command(
    "aurora",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def aurora_passthrough(ctx: typer.Context) -> None:
    if not ctx.args:
        ccyo_out.error("Missing tapdb aurora arguments")
        raise typer.Exit(1)
    _run_tapdb(ZebraDaySettings.from_context(), ["aurora", *ctx.args])


def register(registry: CommandRegistry, spec: CliSpec) -> None:
    del spec
    registry.add_typer_app(None, tapdb_app, "tapdb", "TapDB lifecycle wrappers")
