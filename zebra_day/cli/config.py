"""Configuration management commands for zebra_day CLI."""

from __future__ import annotations

import os
import subprocess

import typer
import yaml
from rich.console import Console
from rich.syntax import Syntax

from zebra_day import paths as xdg

config_app = typer.Typer(help="Configuration management commands")
console = Console()


@config_app.command("init")
def init_config(
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing config"),
):
    """Initialize configuration from template.

    Creates the user config file from the template if it doesn't exist.
    """
    from importlib.resources import files
    from pathlib import Path

    config_path = xdg.get_config_file_path()
    template_path = Path(str(files("zebra_day"))) / "etc" / "zebra-day-config-template.yaml"

    if config_path.exists() and not force:
        console.print(f"[yellow]⚠[/yellow] Config already exists: {config_path}")
        console.print("   Use [cyan]--force[/cyan] to overwrite")
        raise typer.Exit(1)

    # Create config from template
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(template_path) as f:
        template_content = f.read()
    with open(config_path, "w") as f:
        f.write(template_content)

    console.print(f"[green]✓[/green] Config initialized: {config_path}")


@config_app.command("show")
def show_config():
    """Display current configuration (pretty-printed YAML)."""
    config_path = xdg.get_config_file_path()

    if not config_path.exists():
        console.print(f"[yellow]⚠[/yellow] Config not found: {config_path}")
        console.print("   Run [cyan]zday config init[/cyan] to create it")
        raise typer.Exit(1)

    with open(config_path) as f:
        content = f.read()

    syntax = Syntax(content, "yaml", theme="monokai", line_numbers=True)
    console.print(syntax)


@config_app.command("path")
def config_path():
    """Print path to the active config file."""
    yaml_path = xdg.get_config_file_path()
    json_path = xdg.get_legacy_json_config_path()

    if yaml_path.exists():
        console.print(str(yaml_path))
    elif json_path.exists():
        console.print(f"{json_path}  [dim](legacy JSON)[/dim]")
    else:
        console.print(f"{yaml_path}  [dim](not created)[/dim]")


@config_app.command("validate")
def validate_config():
    """Validate configuration against schema."""
    config_path = xdg.get_config_file_path()

    if not config_path.exists():
        console.print(f"[red]✗[/red] Config not found: {config_path}")
        raise typer.Exit(1)

    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)

        errors = []

        # Check schema version
        if "schema_version" not in config:
            errors.append("Missing 'schema_version' field")
        elif config["schema_version"] != "2.0.0":
            errors.append(f"Unknown schema version: {config['schema_version']}")

        # Check labs structure
        if "labs" not in config:
            errors.append("Missing 'labs' field")
        elif not isinstance(config["labs"], dict):
            errors.append("'labs' must be a dictionary")
        else:
            for lab_id, lab_data in config["labs"].items():
                if not isinstance(lab_data, dict):
                    errors.append(f"Lab '{lab_id}' must be a dictionary")
                    continue
                if "printers" not in lab_data:
                    errors.append(f"Lab '{lab_id}' missing 'printers' field")

        if errors:
            console.print(f"[red]✗[/red] Validation failed ({len(errors)} errors):")
            for err in errors:
                console.print(f"   • {err}")
            raise typer.Exit(1)

        console.print(f"[green]✓[/green] Config is valid: {config_path}")

    except yaml.YAMLError as e:
        console.print(f"[red]✗[/red] Invalid YAML syntax: {e}")
        raise typer.Exit(1) from None


@config_app.command("edit")
def edit_config():
    """Open configuration in $EDITOR."""
    config_path = xdg.get_config_file_path()

    if not config_path.exists():
        console.print(f"[yellow]⚠[/yellow] Config not found: {config_path}")
        console.print("   Run [cyan]zday config init[/cyan] to create it")
        raise typer.Exit(1)

    editor = os.environ.get("EDITOR", "vi")
    console.print(f"[cyan]→[/cyan] Opening {config_path} in {editor}...")
    subprocess.run([editor, str(config_path)])


@config_app.command("reset")
def reset_config(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
):
    """Reset configuration to template (with confirmation)."""
    config_path = xdg.get_config_file_path()

    if not yes:
        confirm = typer.confirm(f"Reset config at {config_path}? This cannot be undone.")
        if not confirm:
            console.print("[dim]Cancelled[/dim]")
            raise typer.Exit(0)

    # Create backup before reset
    if config_path.exists():
        import datetime
        import shutil

        backup_dir = xdg.get_config_backups_dir()
        backup_name = f"{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}_before_reset.yaml"
        shutil.copy2(config_path, backup_dir / backup_name)
        console.print(f"[dim]Backup saved: {backup_dir / backup_name}[/dim]")

    # Reset from template
    init_config(force=True)
