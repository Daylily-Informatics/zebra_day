"""zebra_day CLI built on cli-core-yo with a TapDB-only runtime contract."""

from __future__ import annotations

import os
import sys

from cli_core_yo.app import create_app, run
from cli_core_yo.spec import (
    BackendDetectSpec,
    BackendValidationSpec,
    CliSpec,
    ConfigSpec,
    ContextOptionSpec,
    EnvSpec,
    ExecutionBackendSpec,
    InvocationContextSpec,
    PluginSpec,
    PolicySpec,
    PrereqSpec,
    RuntimeSpec,
    XdgSpec,
)

from zebra_day import paths as xdg
from zebra_day.cli._registry_v2 import ZEBRA_RUNTIME_TAG
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
            ("TapDB Target", "target"),
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
    policy=PolicySpec(),
    config=ConfigSpec(
        xdg_relative_path=xdg.get_config_filename(),
        template_bytes=build_default_config_template(),
        validator=validate_settings_yaml,
    ),
    env=EnvSpec(
        active_env_var="CONDA_DEFAULT_ENV",
        project_root_env_var="ZEBRA_DAY_PROJECT_ROOT",
        activate_script_name="activate <deploy-name>",
        deactivate_script_name="zebra_day_deactivate",
        preferred_backend="zebra-day-conda",
    ),
    runtime=RuntimeSpec(
        supported_backends=[
            ExecutionBackendSpec(
                name="zebra-day-conda",
                kind="conda",
                entry_guidance="source ./activate <deploy-name>",
                detect=BackendDetectSpec(env_vars=("CONDA_PREFIX",)),
                validation=BackendValidationSpec(env_vars=("CONDA_PREFIX",)),
            )
        ],
        default_backend="zebra-day-conda",
        guard_mode="enforced",
        prereqs=[
            PrereqSpec(
                key="zebra-day-conda-active-env",
                kind="env_var",
                value="CONDA_DEFAULT_ENV",
                help="Activate zebra_day with source ./activate <deploy-name>.",
                applies_to_backends={"zebra-day-conda"},
                tags={ZEBRA_RUNTIME_TAG},
                success_message="Deployment-scoped conda environment is active.",
                failure_message=(
                    "zebra_day CLI requires an active deployment-scoped conda environment. "
                    "Run `source ./activate <deploy-name>`."
                ),
            ),
            PrereqSpec(
                key="zebra-day-conda-env-name",
                kind="command_probe",
                value=(
                    sys.executable,
                    "-c",
                    "import os, sys; "
                    "env = os.environ.get('CONDA_DEFAULT_ENV', '').strip(); "
                    "sys.exit(0 if env.startswith('ZEBRA_DAY-') and len(env) > len('ZEBRA_DAY-') else 1)",
                ),
                help="Use the deployment-scoped conda env created by source ./activate <deploy-name>.",
                applies_to_backends={"zebra-day-conda"},
                tags={ZEBRA_RUNTIME_TAG},
                success_message="Deployment-scoped conda environment name matches the deployment.",
                failure_message=(
                    "zebra_day CLI requires CONDA_DEFAULT_ENV to start with "
                    "`ZEBRA_DAY-<deploy-name>`. Run `source ./activate <deploy-name>`."
                ),
            ),
            PrereqSpec(
                key="zebra-day-daylily-tapdb",
                kind="python_import",
                value="daylily_tapdb",
                help="Install daylily-tapdb into the active zebra_day environment.",
                applies_to_backends={"zebra-day-conda"},
                tags={ZEBRA_RUNTIME_TAG},
                success_message="Dependency available: daylily-tapdb",
                failure_message=(
                    "Missing dependency: daylily-tapdb. Re-run `source ./activate <deploy-name>`."
                ),
            ),
            PrereqSpec(
                key="zebra-day-daylily-auth-cognito",
                kind="python_import",
                value="daylily_auth_cognito",
                help="Install daylily-auth-cognito into the active zebra_day environment.",
                applies_to_backends={"zebra-day-conda"},
                tags={ZEBRA_RUNTIME_TAG},
                success_message="Dependency available: daylily-auth-cognito",
                failure_message=(
                    "Missing dependency: daylily-auth-cognito. "
                    "Re-run `source ./activate <deploy-name>`."
                ),
            ),
        ],
    ),
    context=InvocationContextSpec(
        options=[
            ContextOptionSpec(
                name="no_auth",
                option_flags=("--no-auth",),
                value_type="bool",
                default=False,
                help="Disable web and API auth for this invocation.",
            )
        ]
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
            "zebra_day.cli.config_extra.register",
            "zebra_day.cli.simulator.register",
        ]
    ),
    info_hooks=[_zday_info_hook],
)

app = create_app(spec)
cli = app


def main() -> None:
    raise SystemExit(run(spec))


if __name__ == "__main__":
    main()
