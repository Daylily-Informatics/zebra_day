"""Environment management CLI commands."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from cli_core_yo import output
from rich.console import Console
from rich.panel import Panel

from zebra_day import paths as xdg

if TYPE_CHECKING:
    from cli_core_yo.registry import CommandRegistry
    from cli_core_yo.spec import CliSpec

console = Console()  # retained for Rich Panel rendering

env_app = typer.Typer(help="Development environment management")


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
        output.error("Could not find zebra_day project root")
        output.detail("Make sure you're in the zebra_day directory")
        raise typer.Exit(1)

    activate_script = project_root / "activate"

    if not activate_script.exists():
        output.error(f"Activation script not found: {activate_script}")
        raise typer.Exit(1)

    console.print(
        Panel.fit(
            f"[cyan]source {activate_script} <deploy-name>[/cyan]",
            title="Run this command to activate",
            border_style="green",
        )
    )
    output.detail("Note: CLI commands cannot modify the parent shell.")
    output.detail("You must source the script directly.")


@env_app.command("deactivate")
def deactivate():
    """Show command to deactivate the zebra_day development environment.

    Since CLI commands cannot modify the parent shell, this prints
    the command you need to run.
    """
    # Check if environment is active
    if not os.environ.get("ZEBRA_DAY_ACTIVE"):
        output.warning("zebra_day environment is not active")
        return

    project_root = _find_project_root()

    if project_root is None:
        # Fallback: just tell them to run deactivate
        console.print(
            Panel.fit(
                "[cyan]source zebra_day_deactivate[/cyan]\n[dim]or[/dim]\n[cyan]deactivate[/cyan]",
                title="Run one of these commands to deactivate",
                border_style="yellow",
            )
        )
    else:
        deactivate_script = project_root / "zebra_day_deactivate"
        console.print(
            Panel.fit(
                f"[cyan]source {deactivate_script}[/cyan]",
                title="Run this command to deactivate",
                border_style="yellow",
            )
        )

    output.detail("Note: CLI commands cannot modify the parent shell.")
    output.detail("You must source the script directly.")


@env_app.command("status")
def status():
    """Show current environment status."""
    is_active = bool(os.environ.get("ZEBRA_DAY_ACTIVE"))
    project_root = os.environ.get("ZEBRA_DAY_PROJECT_ROOT") or os.environ.get("ZDAY_PROJECT_ROOT", "")
    virtual_env = os.environ.get("VIRTUAL_ENV", "")
    config_path = str(xdg.get_config_file_path())

    output.heading("Environment Status")

    if is_active:
        output.success("zebra_day environment: Active")
        if project_root:
            output.detail(f"Project root: {project_root}")
        if virtual_env:
            output.detail(f"Virtual env:  {virtual_env}")
        output.detail(f"Config file:  {config_path}")
    else:
        output.detail("zebra_day environment: Not active")
        output.detail("Run 'zday env activate' for instructions")
        output.detail(f"Config file:  {config_path}")


@env_app.command("reset")
def reset():
    """Reset the environment: deactivate and re-activate cleanly.

    Since CLI commands cannot modify the parent shell, this prints
    the command you need to run.
    """
    project_root = _find_project_root()

    if project_root is None:
        output.error("Could not find zebra_day project root")
        output.detail("Make sure you're in the zebra_day directory")
        raise typer.Exit(1)

    activate_script = project_root / "activate"
    deactivate_script = project_root / "zebra_day_deactivate"

    if not activate_script.exists():
        output.error(f"Activation script not found: {activate_script}")
        raise typer.Exit(1)

    # Check if currently active
    is_active = bool(os.environ.get("ZEBRA_DAY_ACTIVE"))

    if is_active and deactivate_script.exists():
        # Show combined command
        console.print(
            Panel.fit(
                f"[cyan]source {deactivate_script} && source {activate_script} <deploy-name>[/cyan]",
                title="Run this command to reset",
                border_style="cyan",
            )
        )
    else:
        # Just activate (or re-activate)
        console.print(
            Panel.fit(
                f"[cyan]source {activate_script} <deploy-name>[/cyan]",
                title="Run this command to activate/reset",
                border_style="green",
            )
        )

    output.detail("Note: CLI commands cannot modify the parent shell.")
    output.detail("You must source the script directly.")


def register(registry: CommandRegistry, spec: CliSpec) -> None:
    """cli-core-yo plugin: register the env command group (custom, not built-in)."""
    registry.add_typer_app(None, env_app, "env", "Development environment management")
