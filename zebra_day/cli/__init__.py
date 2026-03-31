"""zebra_day CLI using the Atlas-style activate/config contract."""

from __future__ import annotations

import os

import typer
from cli_core_yo.app import create_app
from cli_core_yo.runtime import _reset, initialize
from cli_core_yo.spec import CliSpec, ConfigSpec, EnvSpec, PluginSpec, XdgSpec

from zebra_day import paths as xdg
from zebra_day.settings import ZebraDaySettings, build_default_config_template, validate_settings_yaml


def _get_version() -> str:
    """Get zebra_day version (kept for backward compat with tests)."""
    try:
        from importlib.metadata import version

        return version("zebra_day")
    except Exception:
        return "dev"
def _zday_info_hook() -> list[tuple[str, str]]:
    """Provide zebra_day-specific info rows for the built-in info command.

    Note: cli-core-yo already provides Version, Python, Config Dir,
    Data Dir, State Dir, Cache Dir, CLI Core.  We only add domain-specific
    rows that the built-in doesn't know about.
    """
    rows: list[tuple[str, str]] = [
        ("Logs Dir", str(xdg.get_logs_dir())),
    ]

    settings = ZebraDaySettings.from_context()
    rows.append(("Deployment", settings.deployment_code))
    rows.append(("Config File", str(settings.config_path)))
    rows.append(("TapDB Config", str(settings.tapdb_config_path)))
    rows.append(("TapDB Namespace", settings.tapdb_database_name))
    rows.append(("Auth Mode", settings.auth_mode))

    # GUI server
    pid_file = xdg.get_state_dir() / "gui.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
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
    root_help="Zebra printer fleet management and ZPL print API",
    xdg=XdgSpec(
        app_dir_name=xdg.get_app_dir_name(),
        legacy_macos_config_dir="~/Library/Preferences/zebra_day",
        legacy_copy_files=["zebra-day-config.yaml", "printer_config.json"],
    ),
    config=ConfigSpec(
        primary_filename=xdg.get_config_filename(),
        template_bytes=build_default_config_template(),
        validator=validate_settings_yaml,
    ),
    env=EnvSpec(
        active_env_var="_ZEBRA_DAY_ACTIVE",
        project_root_env_var="ZEBRA_DAY_PROJECT_ROOT",
        activate_script_name="activate",
        deactivate_script_name="zebra_day_deactivate",
    ),
    plugins=PluginSpec(
        explicit=[
            "zebra_day.cli.gui.register",
            "zebra_day.cli.printer.register",
            "zebra_day.cli.template.register",
            "zebra_day.cli.man.register",
            "zebra_day.cli.cognito.register",
            "zebra_day.cli.root_commands.register",
            "zebra_day.cli.simulator.register",
        ]
    ),
    info_hooks=[_zday_info_hook],
)

app = create_app(spec)


@app.callback()
def _root_callback(
    json_flag: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Initialize RuntimeContext for the current invocation."""
    _reset()
    debug = os.environ.get("CLI_CORE_YO_DEBUG") == "1"
    xdg_paths = app._cli_core_yo_xdg_paths  # type: ignore[attr-defined]
    initialize(spec, xdg_paths, json_mode=json_flag, debug=debug)


def main():
    """Main CLI entry point."""
    app()


if __name__ == "__main__":
    raise SystemExit(main())
