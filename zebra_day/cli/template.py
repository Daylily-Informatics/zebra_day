"""ZPL template management commands for zebra_day CLI."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

import typer
from cli_core_yo import output
from rich.console import Console
from rich.table import Table

import zebra_day.print_mgr as zdpm
from zebra_day import paths as xdg

if TYPE_CHECKING:
    from cli_core_yo.registry import CommandRegistry
    from cli_core_yo.spec import CliSpec

template_app = typer.Typer(help="ZPL template management commands")
console = Console()  # retained for Rich Table rendering


def _get_zp():
    """Get PrintMgr instance."""
    return zdpm.zpl()


def _find_template(name: str) -> Path | None:
    """Find a template file by name using PrintMgr."""
    zp = _get_zp()
    try:
        return zp.resolve_template_path(name)
    except FileNotFoundError:
        return None


@template_app.command("list")
def list_templates(
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full paths"),
):
    """List available ZPL templates."""
    zp = _get_zp()

    user_dir = xdg.get_label_styles_dir()
    pkg_dir = zp._package_label_styles_dir()

    templates: list[dict[str, Any]] = []

    # User templates
    if user_dir.exists():
        for f in sorted(user_dir.iterdir()):
            if f.is_file() and f.suffix == ".zpl":
                templates.append(
                    {
                        "name": f.stem,
                        "path": str(f),
                        "size": f.stat().st_size,
                        "source": "user",
                    }
                )

    user_names = {t["name"] for t in templates}

    # Package templates (skip if already in user)
    if pkg_dir.exists():
        for f in sorted(pkg_dir.iterdir()):
            if f.is_file() and f.suffix == ".zpl" and f.stem not in user_names:
                templates.append(
                    {
                        "name": f.stem,
                        "path": str(f),
                        "size": f.stat().st_size,
                        "source": "package",
                    }
                )

    if json_output:
        output.emit_json(templates)
        return

    if not templates:
        output.warning("No templates found")
        return

    table = Table(title="ZPL Templates")
    table.add_column("Name", style="cyan")
    table.add_column("Source")
    table.add_column("Size")
    if verbose:
        table.add_column("Path", style="dim")

    for t in sorted(templates, key=lambda x: x["name"]):
        source_style = "[green]user[/green]" if t["source"] == "user" else "[dim]package[/dim]"
        if verbose:
            table.add_row(t["name"], source_style, f"{t['size']} bytes", t["path"])
        else:
            table.add_row(t["name"], source_style, f"{t['size']} bytes")

    console.print(table)


@template_app.command("preview")
def preview(
    template_name: str = typer.Argument(..., help="Template name to preview"),
    output: str | None = typer.Option(None, "--output", "-o", help="Output PNG file path"),
):
    """Generate a PNG preview of a ZPL template."""
    template_path = _find_template(template_name)
    if not template_path:
        output.error(f"Template not found: {template_name}")
        raise typer.Exit(1)

    output.action(f"Generating preview for {template_name}...")

    try:
        import zebra_day.print_mgr as zdpm

        zp = zdpm.zpl()

        # Read template
        zpl_content = template_path.read_text()

        # Generate PNG
        if not output:
            output_path = xdg.get_generated_files_dir() / f"{template_name}_preview.png"
        else:
            output_path = Path(output)

        zp.generate_label_png(zpl_content, str(output_path), False)
        output.success(f"Preview generated: {output_path}")

    except Exception as e:
        output.error(f"Preview error: {e}")
        raise typer.Exit(1) from None


@template_app.command("edit")
def edit(
    template_name: str = typer.Argument(..., help="Template name to edit"),
    editor: str | None = typer.Option(None, "--editor", "-e", help="Editor command"),
):
    """Open a ZPL template in an editor."""
    template_path = _find_template(template_name)
    if not template_path:
        output.error(f"Template not found: {template_name}")
        raise typer.Exit(1)

    # Determine editor
    if not editor:
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"

    output.action(f"Opening {template_path} with {editor}...")
    try:
        subprocess.run([editor, str(template_path)])
    except Exception as e:
        output.error(f"Error opening editor: {e}")
        raise typer.Exit(1) from None


@template_app.command("show")
def show(
    template_name: str = typer.Argument(..., help="Template name to display"),
):
    """Display the contents of a ZPL template."""
    template_path = _find_template(template_name)
    if not template_path:
        output.error(f"Template not found: {template_name}")
        raise typer.Exit(1)

    output.detail(f"# {template_path}")
    output.print_text(template_path.read_text())


@template_app.command("save")
def save(
    filename: str = typer.Argument(..., help="Template filename (e.g., 'my_label.zpl')"),
    content_source: str = typer.Option(
        ..., "--content", "-c", help="ZPL content or path to file containing ZPL"
    ),
    location: str = typer.Option(
        "user", "--location", "-l", help="Save location: 'user' or 'package'"
    ),
    no_backup: bool = typer.Option(False, "--no-backup", help="Disable backup of existing file"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite without confirmation"),
):
    """Save a ZPL template.

    Saves to ~/.config/zebra_day/label_styles/ by default (--location=user).
    Use --location=package to save to the package directory (requires write access).
    """
    zp = _get_zp()

    # If content_source is a file path, read it
    content_path = Path(content_source)
    if content_path.exists() and content_path.is_file():
        zpl_content = content_path.read_text()
        output.detail(f"Reading ZPL from: {content_path}")
    else:
        zpl_content = content_source

    # Validate location
    if location not in ("user", "package"):
        output.error(f"Invalid location: {location} (must be 'user' or 'package')")
        raise typer.Exit(1)

    try:
        path = zp.save_template(
            filename=filename,
            zpl_content=zpl_content,
            location=location,  # type: ignore[arg-type]
            overwrite=force,
            backup=not no_backup,
        )
        output.success(f"Template saved: {path}")
    except FileExistsError as e:
        output.error(str(e))
        output.action("Use --force to overwrite")
        raise typer.Exit(1) from None
    except (ValueError, PermissionError) as e:
        output.error(str(e))
        raise typer.Exit(1) from None


@template_app.command("delete")
def delete(
    name: str = typer.Argument(..., help="Template name to delete"),
    location: str = typer.Option(
        "user", "--location", "-l", help="Delete from: 'user' or 'package'"
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Delete a ZPL template.

    By default, deletes from user config directory (~/.config/zebra_day/label_styles/).
    Use --location=package to delete from package directory (requires write access).
    """
    # Validate location
    if location not in ("user", "package"):
        output.error(f"Invalid location: {location} (must be 'user' or 'package')")
        raise typer.Exit(1)

    if not force:
        confirm = typer.confirm(f"Delete template '{name}' from {location}?")
        if not confirm:
            raise typer.Abort()

    zp = _get_zp()
    try:
        zp.delete_template(name, location=location)  # type: ignore[arg-type]
        output.success(f"Template '{name}' deleted from {location}")
    except FileNotFoundError as e:
        output.error(str(e))
        raise typer.Exit(1) from None
    except PermissionError as e:
        output.error(str(e))
        raise typer.Exit(1) from None


def register(registry: CommandRegistry, spec: CliSpec) -> None:
    """cli-core-yo plugin: register the template command group."""
    registry.add_typer_app(None, template_app, "template", "ZPL template management commands")
