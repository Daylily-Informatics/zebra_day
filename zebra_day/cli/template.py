"""Template management commands backed by TapDB."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import typer
from cli_core_yo import ccyo_out
from cli_core_yo.runtime import get_context

from zebra_day.cli._registry_v2 import (
    REQUIRED_JSON,
    REQUIRED_MUTATING,
    REQUIRED_MUTATING_INTERACTIVE,
    register_group_commands,
)
from zebra_day.client import ZebraDayClient

if TYPE_CHECKING:
    from cli_core_yo.registry import CommandRegistry
    from cli_core_yo.spec import CliSpec

template_app = typer.Typer(help="TapDB-backed template management")


def _read_template_source(content: str) -> str:
    candidate = Path(content)
    if candidate.exists() and candidate.is_file():
        return candidate.read_text(encoding="utf-8")
    return content


@template_app.command("list")
def list_templates() -> None:
    """List available ZPL templates."""
    client = ZebraDayClient.from_context()
    names = client.list_templates()
    if get_context().json_mode:
        ccyo_out.emit_json(names)
        return
    if not names:
        ccyo_out.warning("No templates found")
        return
    for name in names:
        ccyo_out.bullet(name)


@template_app.command("show")
def show(template_name: str = typer.Argument(..., help="Template name")) -> None:
    """Print the raw ZPL for one template."""
    client = ZebraDayClient.from_context()
    template = client.get_template(template_name)
    if template is None:
        ccyo_out.error(f"Template not found: {template_name}")
        raise typer.Exit(1)
    if get_context().json_mode:
        ccyo_out.emit_json(template)
        return
    ccyo_out.print_text(str(template.get("zpl_content") or ""))


@template_app.command("save")
def save(
    filename: str = typer.Argument(..., help="Template name or filename"),
    content: str = typer.Option(..., "--content", "-c", help="Raw ZPL or path to a .zpl file"),
) -> None:
    """Create or replace a stored ZPL template."""
    client = ZebraDayClient.from_context()
    stem = filename[:-4] if filename.endswith(".zpl") else filename
    if not stem.strip():
        ccyo_out.error("filename is required")
        raise typer.Exit(1)
    client.save_template(stem, _read_template_source(content), source="user")
    ccyo_out.success(f"Saved template: {stem}")


@template_app.command("delete")
def delete(
    template_name: str = typer.Argument(..., help="Template name"),
    force: bool = typer.Option(False, "--force", help="Skip confirmation"),
) -> None:
    """Delete a stored ZPL template."""
    if not force and not typer.confirm(f"Delete template '{template_name}' from TapDB?"):
        raise typer.Abort()
    client = ZebraDayClient.from_context()
    client.delete_template(template_name)
    ccyo_out.success(f"Deleted template: {template_name}")


@template_app.command("preview")
def preview(
    template_name: str = typer.Argument(..., help="Template name"),
    uid_barcode: str = typer.Option("", "--uid-barcode", help="UID barcode value"),
) -> None:
    """Render a preview for one template."""
    client = ZebraDayClient.from_context()
    _zpl_string, png_url = client.render_label(template=template_name, uid_barcode=uid_barcode)
    if get_context().json_mode:
        ccyo_out.emit_json({"template_name": template_name, "png_url": png_url})
        return
    ccyo_out.success(f"Rendered preview: {png_url}")


def register(registry: CommandRegistry, spec: CliSpec) -> None:
    _ = spec
    register_group_commands(
        registry,
        "template",
        "Template operations",
        [
            ("list", list_templates, REQUIRED_JSON),
            ("show", show, REQUIRED_JSON),
            ("save", save, REQUIRED_MUTATING),
            ("delete", delete, REQUIRED_MUTATING_INTERACTIVE),
            ("preview", preview, REQUIRED_JSON),
        ],
    )
