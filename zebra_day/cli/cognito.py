"""Cognito authentication management commands for zebra_day CLI.

This module delegates to daylily-cognito if available, otherwise provides
basic status and info commands.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import typer
from cli_core_yo import output
from rich.console import Console
from rich.table import Table

if TYPE_CHECKING:
    from cli_core_yo.registry import CommandRegistry
    from cli_core_yo.spec import CliSpec

console = Console()  # retained for Rich Table rendering


def _is_cognito_available() -> bool:
    """Check if daylily-cognito is installed."""
    try:
        from daylily_cognito.cli import cognito_app as _  # noqa: F401

        return True
    except ImportError:
        return False


def _get_cognito_app() -> typer.Typer:
    """Get the Cognito CLI app, either from daylily-cognito or a fallback."""
    if _is_cognito_available():
        # Import and return the full cognito CLI from daylily-cognito
        from daylily_cognito.cli import cognito_app

        return cognito_app  # type: ignore[no-any-return]
    else:
        # Return a minimal fallback app
        return _create_fallback_app()


def _create_fallback_app() -> typer.Typer:
    """Create a fallback cognito app with basic commands."""
    app = typer.Typer(
        help="Cognito authentication management (limited - daylily-cognito not installed)"
    )

    @app.command("status")
    def status():
        """Show current Cognito authentication configuration."""
        table = Table(title="Cognito Configuration")
        table.add_column("Variable", style="cyan")
        table.add_column("Value")
        table.add_column("Status")

        pool_id = os.environ.get("COGNITO_USER_POOL_ID")
        client_id = os.environ.get("COGNITO_APP_CLIENT_ID")
        region = os.environ.get("COGNITO_REGION", os.environ.get("AWS_DEFAULT_REGION"))

        if pool_id:
            # Truncate for display
            display = pool_id[:15] + "..." if len(pool_id) > 15 else pool_id
            table.add_row("COGNITO_USER_POOL_ID", display, "[green]Set[/green]")
        else:
            table.add_row("COGNITO_USER_POOL_ID", "-", "[yellow]Not set[/yellow]")

        if client_id:
            display = client_id[:15] + "..." if len(client_id) > 15 else client_id
            table.add_row("COGNITO_APP_CLIENT_ID", display, "[green]Set[/green]")
        else:
            table.add_row("COGNITO_APP_CLIENT_ID", "-", "[yellow]Not set[/yellow]")

        if region:
            table.add_row("COGNITO_REGION", region, "[green]Set[/green]")
        else:
            table.add_row("COGNITO_REGION", "-", "[yellow]Not set[/yellow]")

        console.print(table)

        # Summary
        if pool_id and client_id:
            output.success("Cognito is configured")
            output.detail("Start server with: zday gui start --auth cognito")
        else:
            output.warning("Cognito is not fully configured")
            output.detail(
                "Set environment variables or install daylily-cognito for full management"
            )

    @app.command("info")
    def info():
        """Display information about Cognito setup requirements."""
        output.heading("Cognito Authentication Setup")
        output.print_text("To enable Cognito authentication for zebra_day:\n")

        output.print_text("1. Install auth dependencies:")
        output.detail('pip install -e ".[auth]"')

        output.print_text("\n2. Set environment variables:")
        output.detail("export COGNITO_USER_POOL_ID=your-pool-id")
        output.detail("export COGNITO_APP_CLIENT_ID=your-client-id")
        output.detail("export COGNITO_REGION=us-west-2  # optional")

        output.print_text("\n3. Start server with authentication:")
        output.detail("zday gui start --auth cognito")

        if not _is_cognito_available():
            output.detail(
                "For full Cognito management (create, teardown), install daylily-cognito:"
            )
            output.detail("  pip install daylily-cognito")

    @app.command("create")
    def create():
        """Create/configure a Cognito user pool (requires daylily-cognito)."""
        output.warning("This command requires daylily-cognito")
        output.detail('Install with: pip install -e ".[auth]"')
        raise typer.Exit(1)

    @app.command("teardown")
    def teardown():
        """Remove Cognito configuration (requires daylily-cognito)."""
        output.warning("This command requires daylily-cognito")
        output.detail('Install with: pip install -e ".[auth]"')
        raise typer.Exit(1)

    return app


# Export the cognito app - either the full version from daylily-cognito or the fallback
cognito_app = _get_cognito_app()


def register(registry: CommandRegistry, spec: CliSpec) -> None:
    """cli-core-yo plugin: register the cognito command group."""
    registry.add_typer_app(None, cognito_app, "cognito", "Cognito authentication management")
