"""zebra_day CLI - Zebra Printer Fleet Management CLI using cli-core-yo."""

from __future__ import annotations

import os

import typer
import yaml
from cli_core_yo.app import create_app
from cli_core_yo.runtime import _reset, initialize
from cli_core_yo.spec import CliSpec, ConfigSpec, PluginSpec, XdgSpec

from zebra_day import paths as xdg


def _get_version() -> str:
    """Get zebra_day version (kept for backward compat with tests)."""
    try:
        from importlib.metadata import version

        return version("zebra_day")
    except Exception:
        return "dev"


def _validate_zday_config(content: str) -> list[str]:
    """Validate zebra_day configuration YAML.

    Conforms to cli-core-yo ConfigSpec.validator signature:
    takes file content as string, returns list of error strings.
    """
    try:
        config = yaml.safe_load(content)
    except yaml.YAMLError as e:
        return [f"YAML parse error: {e}"]

    if not isinstance(config, dict):
        return ["Root YAML object must be a mapping"]

    errors: list[str] = []
    schema_version = str(config.get("schema_version", ""))

    if not schema_version:
        errors.append("Missing 'schema_version' field")
    elif schema_version not in {"2.0.0", "2.1.0"}:
        errors.append(f"Unknown schema version: {schema_version}")

    if "labs" not in config:
        errors.append("Missing 'labs' field")
    elif not isinstance(config["labs"], dict):
        errors.append("'labs' must be a dictionary")
    else:
        for lab_id, lab_data in config["labs"].items():
            if not isinstance(lab_data, dict):
                errors.append(f"Lab '{lab_id}' must be a dictionary")
                continue
            if "lab_name" not in lab_data:
                errors.append(f"Lab '{lab_id}' missing 'lab_name' field")
            if schema_version == "2.1.0":
                for req_key in ("lab_display_name", "lab_description", "network_stub"):
                    if req_key not in lab_data:
                        errors.append(f"Lab '{lab_id}' missing '{req_key}' field")
            if "printers" not in lab_data:
                errors.append(f"Lab '{lab_id}' missing 'printers' field")

    return errors


def _zday_info_hook() -> list[tuple[str, str]]:
    """Provide zebra_day-specific info rows for the built-in info command.

    Note: cli-core-yo already provides Version, Python, Config Dir,
    Data Dir, State Dir, Cache Dir, CLI Core.  We only add domain-specific
    rows that the built-in doesn't know about.
    """
    rows: list[tuple[str, str]] = [
        ("Logs Dir", str(xdg.get_logs_dir())),
    ]

    # Config file (YAML preferred, JSON fallback)
    yaml_cfg = xdg.get_config_file_path()
    json_cfg = xdg.get_legacy_json_config_path()
    if yaml_cfg.exists():
        rows.append(("Config File", str(yaml_cfg)))
    elif json_cfg.exists():
        rows.append(("Config File", f"{json_cfg} (legacy JSON)"))
    else:
        rows.append(("Config File", f"not found ({yaml_cfg})"))

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
        app_dir_name="zebra_day",
        legacy_macos_config_dir="~/Library/Preferences/zebra_day",
        legacy_copy_files=["zebra-day-config.yaml", "printer_config.json"],
    ),
    config=ConfigSpec(
        primary_filename="zebra-day-config.yaml",
        template_resource=("zebra_day", "etc/zebra-day-config-template.yaml"),
        validator=_validate_zday_config,
    ),
    env=None,  # Custom env group via plugin (Option C)
    plugins=PluginSpec(
        explicit=[
            "zebra_day.cli.gui.register",
            "zebra_day.cli.printer.register",
            "zebra_day.cli.template.register",
            "zebra_day.cli.env.register",
            "zebra_day.cli.dynamo.register",
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
