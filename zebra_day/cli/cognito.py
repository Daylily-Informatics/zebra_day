"""Cognito authentication management commands for zebra_day CLI.

This module delegates to daylily-cognito if available, otherwise provides
basic status, bind/import, and validation commands.
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

    @app.command("bind")
    def bind():
        """Describe the expected daycog binding for zebra_day."""
        output.heading("zebra_day Cognito Binding")
        output.detail("App client name: zebra-day")
        output.detail("Callback URL: https://localhost:8118/auth/callback")
        output.detail("Logout URL: https://localhost:8118/")
        output.detail("Primary workflow: daycog setup / daycog config print --json")

    @app.command("import")
    def import_config():
        """Describe how zebra_day imports the active daycog context."""
        output.detail("zebra_day reads the active ~/.config/daycog/config.yaml context at runtime.")
        output.detail("Use daycog status to confirm the active context before starting the GUI.")

    @app.command("validate")
    def validate():
        """Validate that the active daycog context exposes the required values."""
        missing = []
        for var in ("COGNITO_USER_POOL_ID", "COGNITO_APP_CLIENT_ID", "COGNITO_DOMAIN"):
            if not os.environ.get(var):
                missing.append(var)
        if missing:
            output.error("Active auth context is incomplete")
            for var in missing:
                output.bullet(var)
            raise typer.Exit(1)
        output.success("Active auth context looks complete")

    return app


# Export the cognito app - either the full version from daylily-cognito or the fallback
cognito_app = _get_cognito_app()


def register(registry: CommandRegistry, spec: CliSpec) -> None:
    """cli-core-yo plugin: register the cognito command group."""
    registry.add_typer_app(None, cognito_app, "cognito", "Cognito authentication management")
