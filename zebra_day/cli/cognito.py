"""Cognito authentication management commands for zebra_day CLI.

This module delegates to daylily-cognito if available, otherwise provides
basic status and info commands.
"""

import os
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

console = Console()


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
        return cognito_app
    else:
        # Return a minimal fallback app
        return _create_fallback_app()


def _create_fallback_app() -> typer.Typer:
    """Create a fallback cognito app with basic commands."""
    app = typer.Typer(help="Cognito authentication management (limited - daylily-cognito not installed)")

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
            console.print("\n[green]✓[/green] Cognito is configured")
            console.print("  Start server with: [cyan]zday gui start --auth cognito[/cyan]")
        else:
            console.print("\n[yellow]⚠[/yellow] Cognito is not fully configured")
            console.print("  Set environment variables or install daylily-cognito for full management")

    @app.command("info")
    def info():
        """Display information about Cognito setup requirements."""
        console.print("\n[bold]Cognito Authentication Setup[/bold]\n")
        console.print("To enable Cognito authentication for zebra_day:\n")

        console.print("[bold]1. Install auth dependencies:[/bold]")
        console.print("   [cyan]pip install -e \".[auth]\"[/cyan]\n")

        console.print("[bold]2. Set environment variables:[/bold]")
        console.print("   [cyan]export COGNITO_USER_POOL_ID=your-pool-id[/cyan]")
        console.print("   [cyan]export COGNITO_APP_CLIENT_ID=your-client-id[/cyan]")
        console.print("   [cyan]export COGNITO_REGION=us-west-2[/cyan]  # optional\n")

        console.print("[bold]3. Start server with authentication:[/bold]")
        console.print("   [cyan]zday gui start --auth cognito[/cyan]\n")

        if not _is_cognito_available():
            console.print("[dim]For full Cognito management (create, teardown), install daylily-cognito:[/dim]")
            console.print("[dim]  pip install daylily-cognito[/dim]")

    @app.command("create")
    def create():
        """Create/configure a Cognito user pool (requires daylily-cognito)."""
        console.print("[yellow]⚠[/yellow] This command requires daylily-cognito")
        console.print("  Install with: [cyan]pip install -e \".[auth]\"[/cyan]")
        raise typer.Exit(1)

    @app.command("teardown")
    def teardown():
        """Remove Cognito configuration (requires daylily-cognito)."""
        console.print("[yellow]⚠[/yellow] This command requires daylily-cognito")
        console.print("  Install with: [cyan]pip install -e \".[auth]\"[/cyan]")
        raise typer.Exit(1)

    return app


# Export the cognito app - either the full version from daylily-cognito or the fallback
cognito_app = _get_cognito_app()

