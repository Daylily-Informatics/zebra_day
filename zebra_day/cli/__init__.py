"""zebra_day CLI built on cli-core-yo with a TapDB-only runtime contract."""

from __future__ import annotations

import os
import sys
from typing import Any, cast

import typer
from cli_core_yo.app import create_app
from cli_core_yo.spec import CliSpec, ConfigSpec, EnvSpec, PluginSpec, XdgSpec

from zebra_day import paths as xdg
from zebra_day.optional_deps import import_from_sibling
from zebra_day.settings import (
    ZebraDaySettings,
    build_default_config_template,
    validate_settings_yaml,
)


def _get_version() -> str:
    try:
        from importlib.metadata import version

        return version("zebra_day")
    except Exception:
        return "dev"


def _zday_info_hook() -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = [("Logs Dir", str(xdg.get_logs_dir()))]
    settings = ZebraDaySettings.from_context()
    rows.extend(
        [
            ("Deployment", settings.deployment_code),
            ("Config File", str(settings.config_path)),
            ("TapDB Config", str(settings.tapdb_config_path)),
            ("TapDB Namespace", settings.tapdb_database_name),
            ("TapDB Env", settings.tapdb_env),
            ("Auth Mode", settings.auth_mode),
        ]
    )

    pid_file = settings.state_dir / "gui.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            os.kill(pid, 0)
            rows.append(("GUI Server", f"Running (PID {pid})"))
        except (ValueError, ProcessLookupError, PermissionError):
            rows.append(("GUI Server", "Stopped"))
    else:
        rows.append(("GUI Server", "Stopped"))
    return rows


spec = CliSpec(
    prog_name="zday",
    app_display_name="zebra_day",
    dist_name="zebra_day",
    root_help="zebra_day TapDB-backed Zebra printer fleet management and print service.",
    xdg=XdgSpec(
        app_dir_name=xdg.get_app_dir_name(),
    ),
    config=ConfigSpec(
        xdg_relative_path=xdg.get_config_filename(),
        template_bytes=build_default_config_template(),
        validator=validate_settings_yaml,
    ),
    env=EnvSpec(
        active_env_var="ZEBRA_DAY_ACTIVE",
        project_root_env_var="ZEBRA_DAY_PROJECT_ROOT",
        activate_script_name="activate <deploy-name>",
        deactivate_script_name="zebra_day_deactivate",
    ),
    plugins=PluginSpec(
        explicit=[
            "zebra_day.cli.gui.register",
            "zebra_day.cli.logs.register",
            "zebra_day.cli.printer.register",
            "zebra_day.cli.template.register",
            "zebra_day.cli.tapdb.register",
            "zebra_day.cli.cognito.register",
            "zebra_day.cli.users.register",
            "zebra_day.cli.root_commands.register",
            "zebra_day.cli.config_extra.register",
            "zebra_day.cli.simulator.register",
        ]
    ),
    info_hooks=[_zday_info_hook],
)

app = create_app(spec)

_CONDA_ENV_CHECK_EXEMPT_COMMANDS = frozenset({"version", "info", "env", "help", "config"})


def _strip_global_flags(args: list[str]) -> list[str]:
    filtered: list[str] = []
    skip_next = False
    for index, arg in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if arg in {"--json", "-j", "--no-auth"}:
            continue
        if arg in {"--help", "-h"}:
            filtered.append(arg)
            continue
        if arg == "--install-completion" and index + 1 < len(args):
            filtered.append(arg)
            skip_next = True
            continue
        filtered.append(arg)
    return filtered


def _command_requires_conda_env_check(args: list[str]) -> bool:
    filtered = _strip_global_flags(args)
    if not filtered or "--help" in filtered or "-h" in filtered:
        return False
    for arg in filtered:
        if not arg or arg.startswith("-"):
            continue
        return arg not in _CONDA_ENV_CHECK_EXEMPT_COMMANDS
    return False


def _enforce_conda_env_contract(args: list[str]) -> None:
    if not _command_requires_conda_env_check(args):
        return

    active_env = os.environ.get("CONDA_DEFAULT_ENV", "").strip()
    deployment_code = xdg.get_deployment_code()
    expected_env = f"ZEBRA_DAY-{deployment_code}"
    if not active_env:
        raise SystemExit(
            "zebra_day requires an active deployment-scoped conda environment. "
            f"Activate '{expected_env}' with 'source ./activate {deployment_code}'."
        )
    if active_env != expected_env:
        raise SystemExit(
            "zebra_day requires the deployment-scoped conda environment to match the active "
            f"deployment. Expected CONDA_DEFAULT_ENV='{expected_env}', got '{active_env}'."
        )


def _ensure_tapdb_dependency() -> None:
    try:
        import_from_sibling("daylily_tapdb", "daylily-tapdb")
    except ImportError as exc:
        raise SystemExit(
            "zebra_day CLI startup failed because daylily-tapdb is unavailable. "
            "Install the supported package before running zday."
        ) from exc


@app.callback()
def _root_callback(
    ctx: typer.Context,
    config: str | None = typer.Option(
        None,
        "--config",
        metavar="PATH",
        help="Use this config file for this invocation only.",
    ),
    json_flag: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    no_auth: bool = typer.Option(
        False,
        "--no-auth",
        help="Disable web and API auth for this invocation",
    ),
) -> None:
    del config
    del json_flag
    if no_auth:
        os.environ["ZEBRA_DAY_AUTH_MODE"] = "none"
    cli_app = cast(Any, app)
    ctx.meta["cli_core_yo_spec"] = cli_app._cli_core_yo_spec
    ctx.meta["cli_core_yo_xdg_paths"] = cli_app._cli_core_yo_xdg_paths
    ctx.meta["cli_core_yo_default_config_path"] = cli_app._cli_core_yo_config_path


def main() -> None:
    _ensure_tapdb_dependency()
    _enforce_conda_env_contract(sys.argv[1:])
    raise SystemExit(app())


if __name__ == "__main__":
    main()
