"""Environment management CLI commands."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from cli_core_yo import ccyo_out
from rich.console import Console
from rich.panel import Panel

from zebra_day import paths as xdg

if TYPE_CHECKING:
    from cli_core_yo.registry import CommandRegistry
    from cli_core_yo.spec import CliSpec

console = Console()  # retained for Rich Panel rendering

env_app = typer.Typer(help="Development environment management")


def _is_active_conda_env() -> bool:
    return os.environ.get("CONDA_DEFAULT_ENV", "").startswith("ZEBRA_DAY-")


def _find_project_root() -> Path | None:
    """Find the zebra_day project root by looking for pyproject.toml."""
    for env_var in ("ZEBRA_DAY_PROJECT_ROOT", "ZDAY_PROJECT_ROOT"):
        env_root = os.environ.get(env_var)
        if not env_root:
            continue
        return Path(env_root)

    # Search upward from current directory
    current = Path.cwd()
    while current != current.parent:
        if (current / "pyproject.toml").exists() and (current / "activate").exists():
            return current
        current = current.parent
    return None


@env_app.command("activate")
def activate():
    """Show command to activate the zebra_day development environment.

    Since CLI commands cannot modify the parent shell, this prints
    the command you need to run.
    """
    project_root = _find_project_root()

    if project_root is None:
        ccyo_out.error("Could not find zebra_day project root")
        ccyo_out.detail("Make sure you're in the zebra_day directory")
        raise typer.Exit(1)

    activate_script = project_root / "activate"

    if not activate_script.exists():
        ccyo_out.error(f"Activation script not found: {activate_script}")
        raise typer.Exit(1)

    ccyo_out.print_text(
        Panel.fit(
            f"[cyan]source {activate_script} <deploy-name>[/cyan]",
            title="Run this command to activate",
            border_style="green",
        )
    )
    ccyo_out.detail("Note: CLI commands cannot modify the parent shell.")
    ccyo_out.detail("You must source the script directly.")


@env_app.command("deactivate")
def deactivate():
    """Show command to deactivate the zebra_day development environment.

    Since CLI commands cannot modify the parent shell, this prints
    the command you need to run.
    """
    # Check if environment is active
    if not _is_active_conda_env():
        ccyo_out.warning("zebra_day environment is not active")
        return

    project_root = _find_project_root()

    if project_root is None:
        raise typer.BadParameter(
            "zebra_day project root could not be resolved; run this command from a checkout "
            "or deactivate the conda environment explicitly."
        )
    else:
        deactivate_script = project_root / "zebra_day_deactivate"
        ccyo_out.print_text(
            Panel.fit(
                f"[cyan]source {deactivate_script}[/cyan]",
                title="Run this command to deactivate",
                border_style="yellow",
            )
        )

    ccyo_out.detail("Note: CLI commands cannot modify the parent shell.")
    ccyo_out.detail("You must source the script directly.")


@env_app.command("status")
def status():
    """Show current environment status."""
    is_active = _is_active_conda_env()
    project_root = os.environ.get("ZEBRA_DAY_PROJECT_ROOT") or os.environ.get(
        "ZDAY_PROJECT_ROOT", ""
    )
    virtual_env = os.environ.get("VIRTUAL_ENV", "")
    config_path = str(xdg.get_config_file_path())

    ccyo_out.heading("Environment Status")

    if is_active:
        ccyo_out.success("zebra_day environment: Active")
        if project_root:
            ccyo_out.detail(f"Project root: {project_root}")
        if virtual_env:
            ccyo_out.detail(f"Virtual env:  {virtual_env}")
        ccyo_out.detail(f"Config file:  {config_path}")
    else:
        ccyo_out.detail("zebra_day environment: Not active")
        ccyo_out.detail("Run 'zday env activate' for instructions")
        ccyo_out.detail(f"Config file:  {config_path}")


@env_app.command("reset")
def reset():
    """Reset the environment: deactivate and re-activate cleanly.

    Since CLI commands cannot modify the parent shell, this prints
    the command you need to run.
    """
    project_root = _find_project_root()

    if project_root is None:
        ccyo_out.error("Could not find zebra_day project root")
        ccyo_out.detail("Make sure you're in the zebra_day directory")
        raise typer.Exit(1)

    activate_script = project_root / "activate"
    deactivate_script = project_root / "zebra_day_deactivate"

    if not activate_script.exists():
        ccyo_out.error(f"Activation script not found: {activate_script}")
        raise typer.Exit(1)

    # Check if currently active
    is_active = _is_active_conda_env()

    if is_active and deactivate_script.exists():
        # Show combined command
        ccyo_out.print_text(
            Panel.fit(
                f"[cyan]source {deactivate_script} && source {activate_script} <deploy-name>[/cyan]",
                title="Run this command to reset",
                border_style="cyan",
            )
        )
    else:
        # Just activate (or re-activate)
        ccyo_out.print_text(
            Panel.fit(
                f"[cyan]source {activate_script} <deploy-name>[/cyan]",
                title="Run this command to activate/reset",
                border_style="green",
            )
        )

    ccyo_out.detail("Note: CLI commands cannot modify the parent shell.")
    ccyo_out.detail("You must source the script directly.")


def register(registry: CommandRegistry, spec: CliSpec) -> None:
    """The framework-owned EnvSpec surface is the only active env CLI."""
    del registry
    del spec
