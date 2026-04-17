"""TapDB passthrough commands for zebra_day."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import typer
import yaml
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


def _require_absolute_path(path_value: Path | str, *, field_name: str) -> Path:
    raw = str(path_value or "").strip()
    if not raw:
        ccyo_out.error(f"{field_name} is required and must be passed as a full path.")
        raise typer.Exit(1)
    resolved = Path(raw).expanduser()
    if not resolved.is_absolute():
        ccyo_out.error(f"{field_name} must be an absolute path, got: {raw}")
        raise typer.Exit(1)
    return resolved


def _require_existing_file(path_value: Path | str, *, field_name: str) -> Path:
    resolved = _require_absolute_path(path_value, field_name=field_name)
    if not resolved.is_file():
        ccyo_out.error(f"{field_name} must point to an existing file: {resolved}")
        raise typer.Exit(1)
    return resolved


def _run_tapdb(settings: ZebraDaySettings, args: list[str]) -> None:
    tapdb_config_path = _require_absolute_path(
        settings.tapdb_config_path,
        field_name="tapdb.config_path",
    )
    env = os.environ.copy()
    env["MERIDIAN_DOMAIN_CODE"] = str(settings.tapdb_domain_code)
    env["TAPDB_OWNER_REPO"] = str(settings.tapdb_owner_repo_name)
    env["TAPDB_DOMAIN_CODE"] = str(settings.tapdb_domain_code)
    env["TAPDB_DOMAIN_REGISTRY_PATH"] = str(settings.tapdb_domain_registry_path)
    env["TAPDB_PREFIX_REGISTRY_PATH"] = str(settings.tapdb_prefix_registry_path)
    env["TAPDB_CONFIG_PATH"] = str(tapdb_config_path)
    result = subprocess.run(
        [
            "tapdb",
            "--config",
            str(tapdb_config_path),
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
    tapdb_config_path = _require_absolute_path(
        settings.tapdb_config_path,
        field_name="tapdb.config_path",
    )
    domain_registry_path = _require_existing_file(
        settings.tapdb_domain_registry_path,
        field_name="tapdb.domain_registry_path",
    )
    prefix_registry_path = _require_existing_file(
        settings.tapdb_prefix_registry_path,
        field_name="tapdb.prefix_ownership_registry_path",
    )
    tapdb_config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {
            "config_version": 3,
            "client_id": str(settings.tapdb_client_id),
            "database_name": str(settings.tapdb_database_name),
            "owner_repo_name": str(settings.tapdb_owner_repo_name),
            "domain_code": str(settings.tapdb_domain_code),
            "domain_registry_path": str(domain_registry_path),
            "prefix_ownership_registry_path": str(prefix_registry_path),
        },
        "environments": {
            str(settings.tapdb_env): {
                "domain_code": str(settings.tapdb_domain_code),
                "engine_type": "local",
                "host": "localhost",
                "port": str(DEFAULT_TAPDB_LOCAL_DB_PORT),
                "ui_port": str(DEFAULT_TAPDB_LOCAL_UI_PORT),
                "database": "zebra_day_dev",
                "audit_log_euid_prefix": "ZGX",
                "support_email": "support@lsmc.bio",
                "cognito_user_pool_id": str(settings.cognito_user_pool_id or ""),
            }
        },
    }
    tapdb_config_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


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
