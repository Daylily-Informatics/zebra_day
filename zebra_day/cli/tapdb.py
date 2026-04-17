"""TapDB passthrough commands for zebra_day."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from cli_core_yo import ccyo_out

from zebra_day.cli._registry_v2 import REQUIRED_MUTATING, register_group_commands
from zebra_day.settings import (
    DEFAULT_TAPDB_LOCAL_DB_PORT,
    DEFAULT_TAPDB_LOCAL_UI_PORT,
    ZebraDaySettings,
)

if TYPE_CHECKING:
    from cli_core_yo.registry import CommandRegistry
    from cli_core_yo.spec import CliSpec

tapdb_app = typer.Typer(help="TapDB lifecycle wrappers")
bootstrap_app = typer.Typer(help="TapDB bootstrap wrappers")
tapdb_app.add_typer(bootstrap_app, name="bootstrap")
_PASSTHROUGH_ARGS = typer.Argument(None, metavar="ARGS...")


def _run_tapdb(settings: ZebraDaySettings, args: list[str]) -> None:
    env = os.environ.copy()
    env["MERIDIAN_DOMAIN_CODE"] = str(settings.tapdb_domain_code)
    env["TAPDB_OWNER_REPO"] = str(settings.tapdb_owner_repo_name)
    env["TAPDB_DOMAIN_CODE"] = str(settings.tapdb_domain_code)
    env["TAPDB_DOMAIN_REGISTRY_PATH"] = str(settings.tapdb_domain_registry_path)
    env["TAPDB_PREFIX_REGISTRY_PATH"] = str(settings.tapdb_prefix_registry_path)
    result = subprocess.run(
        [
            "tapdb",
            "--config",
            str(settings.tapdb_config_path),
            "--env",
            settings.tapdb_env,
            *args,
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    if result.stdout:
        ccyo_out.print_text(result.stdout.rstrip())
    if result.returncode != 0:
        if result.stderr:
            ccyo_out.error(result.stderr.strip())
        raise typer.Exit(result.returncode)


def _ensure_local_tapdb_namespace_config(settings: ZebraDaySettings) -> None:
    tapdb_config_path = Path(settings.tapdb_config_path).expanduser()
    tapdb_config_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["MERIDIAN_DOMAIN_CODE"] = str(settings.tapdb_domain_code)
    env["TAPDB_OWNER_REPO"] = str(settings.tapdb_owner_repo_name)
    env["TAPDB_DOMAIN_CODE"] = str(settings.tapdb_domain_code)
    env["TAPDB_DOMAIN_REGISTRY_PATH"] = str(settings.tapdb_domain_registry_path)
    env["TAPDB_PREFIX_REGISTRY_PATH"] = str(settings.tapdb_prefix_registry_path)
    result = subprocess.run(
        [
            "tapdb",
            "--config",
            str(tapdb_config_path),
            "config",
            "init",
            "--client-id",
            str(settings.tapdb_client_id),
            "--database-name",
            str(settings.tapdb_database_name),
            "--owner-repo-name",
            str(settings.tapdb_owner_repo_name),
            "--domain-code",
            f"{settings.tapdb_env}={settings.tapdb_domain_code}",
            "--domain-registry-path",
            str(settings.tapdb_domain_registry_path),
            "--prefix-ownership-registry-path",
            str(settings.tapdb_prefix_registry_path),
            "--env",
            str(settings.tapdb_env),
            "--db-port",
            f"{settings.tapdb_env}={DEFAULT_TAPDB_LOCAL_DB_PORT}",
            "--ui-port",
            f"{settings.tapdb_env}={DEFAULT_TAPDB_LOCAL_UI_PORT}",
        ],
        env=env,
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
    """Bootstrap a local TapDB runtime for zebra_day."""
    args = ["bootstrap", "local"]
    if no_gui:
        args.append("--no-gui")
    settings = ZebraDaySettings.from_context()
    _ensure_local_tapdb_namespace_config(settings)
    _run_tapdb(settings, args)


@tapdb_app.command("db")
def db_passthrough(
    args: list[str] = _PASSTHROUGH_ARGS,
) -> None:
    """Pass through to `tapdb db ...`."""
    resolved_args = list(args or [])
    if not resolved_args:
        ccyo_out.error("Missing tapdb db arguments")
        raise typer.Exit(1)
    _run_tapdb(ZebraDaySettings.from_context(), ["db", *resolved_args])


@tapdb_app.command("pg")
def pg_passthrough(
    args: list[str] = _PASSTHROUGH_ARGS,
) -> None:
    """Pass through to `tapdb pg ...`."""
    resolved_args = list(args or [])
    if not resolved_args:
        ccyo_out.error("Missing tapdb pg arguments")
        raise typer.Exit(1)
    _run_tapdb(ZebraDaySettings.from_context(), ["pg", *resolved_args])


@tapdb_app.command("aurora")
def aurora_passthrough(
    args: list[str] = _PASSTHROUGH_ARGS,
) -> None:
    """Pass through to `tapdb aurora ...`."""
    resolved_args = list(args or [])
    if not resolved_args:
        ccyo_out.error("Missing tapdb aurora arguments")
        raise typer.Exit(1)
    _run_tapdb(ZebraDaySettings.from_context(), ["aurora", *resolved_args])


def register(registry: CommandRegistry, spec: CliSpec) -> None:
    _ = spec
    registry.add_group("tapdb", help_text="TapDB lifecycle wrappers")
    register_group_commands(
        registry,
        "tapdb/bootstrap",
        "TapDB bootstrap wrappers",
        [
            ("local", bootstrap_local, REQUIRED_MUTATING),
        ],
    )
    registry.add_command(
        "tapdb",
        "db",
        db_passthrough,
        help_text="Pass through to `tapdb db ...`.",
        policy=REQUIRED_MUTATING,
    )
    registry.add_command(
        "tapdb",
        "pg",
        pg_passthrough,
        help_text="Pass through to `tapdb pg ...`.",
        policy=REQUIRED_MUTATING,
    )
    registry.add_command(
        "tapdb",
        "aurora",
        aurora_passthrough,
        help_text="Pass through to `tapdb aurora ...`.",
        policy=REQUIRED_MUTATING,
    )
