"""ZPL template management commands for zebra_day CLI."""

import json
import os
import subprocess
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from zebra_day import paths as xdg

template_app = typer.Typer(help="ZPL template management commands")
console = Console()


def _get_template_dirs() -> list[Path]:
    """Get all template directories."""
    from importlib.resources import files

    dirs = []
    # XDG data directory
    xdg_styles = xdg.get_label_styles_dir()
    if xdg_styles.exists():
        dirs.append(xdg_styles)

    # Package directory
    try:
        pkg_styles = Path(str(files("zebra_day"))) / "etc" / "label_styles"
        if pkg_styles.exists():
            dirs.append(pkg_styles)
    except Exception:
        pass

    return dirs


def _find_template(name: str) -> Optional[Path]:
    """Find a template file by name."""
    for template_dir in _get_template_dirs():
        # Try exact match
        for ext in ["", ".zpl", ".txt"]:
            path = template_dir / f"{name}{ext}"
            if path.exists():
                return path
        # Try with zpl_ prefix
        for ext in ["", ".zpl", ".txt"]:
            path = template_dir / f"zpl_{name}{ext}"
            if path.exists():
                return path
    return None


@template_app.command("list")
def list_templates(
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full paths"),
):
    """List available ZPL templates."""
    templates = []

    for template_dir in _get_template_dirs():
        for f in template_dir.iterdir():
            if f.is_file() and not f.name.startswith("."):
                if f.suffix in [".zpl", ".txt", ""] or f.name.startswith("zpl_"):
                    templates.append({
                        "name": f.stem,
                        "path": str(f),
                        "size": f.stat().st_size,
                        "source": "user" if "zebra_day" not in str(template_dir) else "package",
                    })

    # Dedupe by name, prefer user templates
    seen = {}
    for t in templates:
        if t["name"] not in seen or t["source"] == "user":
            seen[t["name"]] = t
    templates = list(seen.values())

    if json_output:
        console.print(json.dumps(templates, indent=2))
        return

    if not templates:
        console.print("[yellow]⚠[/yellow] No templates found")
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
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output PNG file path"),
):
    """Generate a PNG preview of a ZPL template."""
    template_path = _find_template(template_name)
    if not template_path:
        console.print(f"[red]✗[/red] Template not found: {template_name}")
        raise typer.Exit(1)

    console.print(f"[cyan]→[/cyan] Generating preview for {template_name}...")

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

        result = zp.generate_label_png(zpl_content, str(output_path), False)
        console.print(f"[green]✓[/green] Preview generated: {output_path}")

    except Exception as e:
        console.print(f"[red]✗[/red] Preview error: {e}")
        raise typer.Exit(1)


@template_app.command("edit")
def edit(
    template_name: str = typer.Argument(..., help="Template name to edit"),
    editor: Optional[str] = typer.Option(None, "--editor", "-e", help="Editor command"),
):
    """Open a ZPL template in an editor."""
    template_path = _find_template(template_name)
    if not template_path:
        console.print(f"[red]✗[/red] Template not found: {template_name}")
        raise typer.Exit(1)

    # Determine editor
    if not editor:
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"

    console.print(f"[cyan]→[/cyan] Opening {template_path} with {editor}...")
    try:
        subprocess.run([editor, str(template_path)])
    except Exception as e:
        console.print(f"[red]✗[/red] Error opening editor: {e}")
        raise typer.Exit(1)


@template_app.command("show")
def show(
    template_name: str = typer.Argument(..., help="Template name to display"),
):
    """Display the contents of a ZPL template."""
    template_path = _find_template(template_name)
    if not template_path:
        console.print(f"[red]✗[/red] Template not found: {template_name}")
        raise typer.Exit(1)

    console.print(f"[dim]# {template_path}[/dim]\n")
    console.print(template_path.read_text())

