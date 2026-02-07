"""Environment management CLI commands."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.console import Console
from rich.panel import Panel

from zebra_day import paths as xdg

if TYPE_CHECKING:
    from cli_core_yo.registry import CommandRegistry
    from cli_core_yo.spec import CliSpec

console = Console()

env_app = typer.Typer(help="Development environment management")


def _find_project_root() -> Path | None:
    """Find the zebra_day project root by looking for pyproject.toml."""
    # Check ZDAY_PROJECT_ROOT env var first
    if env_root := os.environ.get("ZDAY_PROJECT_ROOT"):
        return Path(env_root)

    # Search upward from current directory
    current = Path.cwd()
    while current != current.parent:
        if (current / "pyproject.toml").exists() and (current / "zday_activate").exists():
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
        console.print("[red]✗[/red] Could not find zebra_day project root")
        console.print("   Make sure you're in the zebra_day directory")
        raise typer.Exit(1)

    activate_script = project_root / "zday_activate"

    if not activate_script.exists():
        console.print(f"[red]✗[/red] Activation script not found: {activate_script}")
        raise typer.Exit(1)

    console.print(
        Panel.fit(
            f"[cyan]source {activate_script}[/cyan]",
            title="Run this command to activate",
            border_style="green",
        )
    )
    console.print("\n[dim]Note: CLI commands cannot modify the parent shell.[/dim]")
    console.print("[dim]You must source the script directly.[/dim]")


@env_app.command("deactivate")
def deactivate():
    """Show command to deactivate the zebra_day development environment.

    Since CLI commands cannot modify the parent shell, this prints
    the command you need to run.
    """
    # Check if environment is active
    if not os.environ.get("_ZDAY_ACTIVE"):
        console.print("[yellow]⚠[/yellow] zebra_day environment is not active")
        return

    project_root = _find_project_root()

    if project_root is None:
        # Fallback: just tell them to run deactivate
        console.print(
            Panel.fit(
                "[cyan]source zday_deactivate[/cyan]\n[dim]or[/dim]\n[cyan]deactivate[/cyan]",
                title="Run one of these commands to deactivate",
                border_style="yellow",
            )
        )
    else:
        deactivate_script = project_root / "zday_deactivate"
        console.print(
            Panel.fit(
                f"[cyan]source {deactivate_script}[/cyan]",
                title="Run this command to deactivate",
                border_style="yellow",
            )
        )

    console.print("\n[dim]Note: CLI commands cannot modify the parent shell.[/dim]")
    console.print("[dim]You must source the script directly.[/dim]")


@env_app.command("status")
def status():
    """Show current environment status."""
    is_active = bool(os.environ.get("_ZDAY_ACTIVE"))
    project_root = os.environ.get("ZDAY_PROJECT_ROOT", "")
    virtual_env = os.environ.get("VIRTUAL_ENV", "")
    config_path = str(xdg.get_config_file_path())

    console.print("\n[bold]Environment Status[/bold]\n")

    if is_active:
        console.print("  [green]●[/green] zebra_day environment: [green]Active[/green]")
        if project_root:
            console.print(f"    Project root: [cyan]{project_root}[/cyan]")
        if virtual_env:
            console.print(f"    Virtual env:  [cyan]{virtual_env}[/cyan]")
        console.print(f"    Config file:  [cyan]{config_path}[/cyan]")
    else:
        console.print("  [dim]○[/dim] zebra_day environment: [dim]Not active[/dim]")
        console.print("    Run [cyan]zday env activate[/cyan] for instructions")
        console.print(f"    Config file:  [cyan]{config_path}[/cyan]")

    console.print()


@env_app.command("reset")
def reset():
    """Reset the environment: deactivate and re-activate cleanly.

    Since CLI commands cannot modify the parent shell, this prints
    the command you need to run.
    """
    project_root = _find_project_root()

    if project_root is None:
        console.print("[red]✗[/red] Could not find zebra_day project root")
        console.print("   Make sure you're in the zebra_day directory")
        raise typer.Exit(1)

    activate_script = project_root / "zday_activate"
    deactivate_script = project_root / "zday_deactivate"

    if not activate_script.exists():
        console.print(f"[red]✗[/red] Activation script not found: {activate_script}")
        raise typer.Exit(1)

    # Check if currently active
    is_active = bool(os.environ.get("_ZDAY_ACTIVE"))

    if is_active and deactivate_script.exists():
        # Show combined command
        console.print(
            Panel.fit(
                f"[cyan]source {deactivate_script} && source {activate_script}[/cyan]",
                title="Run this command to reset",
                border_style="cyan",
            )
        )
    else:
        # Just activate (or re-activate)
        console.print(
            Panel.fit(
                f"[cyan]source {activate_script}[/cyan]",
                title="Run this command to activate/reset",
                border_style="green",
            )
        )

    console.print("\n[dim]Note: CLI commands cannot modify the parent shell.[/dim]")
    console.print("[dim]You must source the script directly.[/dim]")


def register(registry: CommandRegistry, spec: CliSpec) -> None:
    """cli-core-yo plugin: register the env command group (custom, not built-in)."""
    registry.add_typer_app(None, env_app, "env", "Development environment management")
