"""DynamoDB shared configuration CLI commands for zebra_day."""

from __future__ import annotations

import json as json_mod
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.console import Console
from rich.table import Table

from zebra_day.exceptions import ConfigError

if TYPE_CHECKING:
    from cli_core_yo.registry import CommandRegistry
    from cli_core_yo.spec import CliSpec

dynamo_app = typer.Typer(help="DynamoDB shared configuration management")
console = Console()


def _is_interactive() -> bool:
    """Return True when stdin is a TTY (interactive terminal session)."""
    try:
        return sys.stdin.isatty()
    except Exception:
        return False


def _prompt_s3_bucket() -> str:
    """Interactively prompt the user for an S3 bucket name.

    Raises ``typer.Exit(1)`` if the user provides an empty value.
    """
    bucket = typer.prompt("S3 bucket name for backups").strip()
    if not bucket:
        console.print("[red]✗[/red] No S3 bucket name provided.")
        raise typer.Exit(1)
    return bucket


def _ensure_s3_bucket(backend, *, create_if_missing: bool = False) -> None:
    """Check if the S3 bucket exists; optionally create it.

    Args:
        backend: A ``DynamoBackend`` instance with ``s3_bucket`` set.
        create_if_missing: When *True* and the bucket does not exist,
            create it and apply standard tags.
    """
    if not backend.s3_bucket:
        return
    try:
        backend._s3.head_bucket(Bucket=backend.s3_bucket)
    except Exception:
        if create_if_missing:
            console.print(
                f"[cyan]→[/cyan] Bucket '{backend.s3_bucket}' not found — creating..."
            )
            backend.create_s3_bucket()
            console.print(
                f"[green]✓[/green] S3 bucket '{backend.s3_bucket}' created "
                f"(tags: lsmc-cost-center={backend.cost_center}, "
                f"lsmc-project={backend.project})"
            )
        else:
            console.print(
                f"[yellow]⚠[/yellow] S3 bucket '{backend.s3_bucket}' does not exist. "
                "Use --create-s3-if-missing to auto-create."
            )


def _get_backend_from_env(
    *,
    json_output: bool = False,
    create_s3_if_missing: bool = False,
):
    """Create a ``DynamoBackend`` from env vars with interactive prompt fallback.

    If ``ZEBRA_DAY_S3_BACKUP_BUCKET`` is not set and the session is
    interactive (TTY, not ``--json``), the user is prompted for a bucket
    name.  Non-interactive sessions fail with a clear error.

    After backend creation, if *create_s3_if_missing* is True the bucket
    is auto-created when it does not exist in AWS.
    """
    from zebra_day.backends.dynamo import DynamoBackend

    backend = DynamoBackend.from_env(allow_missing_bucket=True)

    if not backend.s3_bucket:
        if not json_output and _is_interactive():
            console.print(
                "[yellow]⚠[/yellow] ZEBRA_DAY_S3_BACKUP_BUCKET is not set."
            )
            bucket = _prompt_s3_bucket()
            backend.s3_bucket = bucket
        else:
            console.print(
                "[red]✗[/red] ZEBRA_DAY_S3_BACKUP_BUCKET is required when using "
                "DynamoDB backend. Set it to the S3 bucket name for config backups."
            )
            raise typer.Exit(1)

    if create_s3_if_missing:
        _ensure_s3_bucket(backend, create_if_missing=True)

    return backend


def _load_s3_config_file(path: str) -> dict:
    """Load an S3 config file (JSON only, per project config rules).

    Expected keys: ``s3_bucket``, optionally ``s3_prefix``, ``region``.
    """
    p = Path(path)
    if not p.exists():
        console.print(f"[red]✗[/red] S3 config file not found: {path}")
        raise typer.Exit(1)
    try:
        data = json_mod.loads(p.read_text())
    except Exception as exc:
        console.print(f"[red]✗[/red] Failed to parse S3 config file: {exc}")
        raise typer.Exit(1)
    if not isinstance(data, dict):
        console.print("[red]✗[/red] S3 config file must contain a JSON object")
        raise typer.Exit(1)
    return data


def _get_backend(
    table_name: str | None = None,
    region: str | None = None,
    s3_bucket: str | None = None,
    s3_prefix: str | None = None,
    profile: str | None = None,
    cost_center: str | None = None,
    project: str | None = None,
    s3_config_file: str | None = None,
    create_s3_if_missing: bool = False,
):
    """Create a DynamoBackend from explicit args merged with env var defaults.

    Priority for S3 bucket:
    ``--s3-bucket`` > ``--s3-config-file`` > env var > interactive prompt.

    If *create_s3_if_missing* is True, the bucket is auto-created when it
    does not yet exist in AWS.
    """
    from zebra_day.backends.dynamo import DynamoBackend

    # Load s3-config-file values as baseline (lowest priority for explicit flags)
    file_cfg: dict = {}
    if s3_config_file:
        file_cfg = _load_s3_config_file(s3_config_file)

    kwargs: dict = {}
    if table_name:
        kwargs["table_name"] = table_name
    if region:
        kwargs["region"] = region
    elif file_cfg.get("region"):
        kwargs["region"] = file_cfg["region"]

    # S3 bucket resolution: flag > config file > env var > interactive prompt
    resolved_bucket = (
        s3_bucket
        or file_cfg.get("s3_bucket")
        or os.environ.get("ZEBRA_DAY_S3_BACKUP_BUCKET")
    )
    if not resolved_bucket:
        if _is_interactive():
            console.print(
                "[yellow]⚠[/yellow] S3 bucket not specified via flag, config file, "
                "or ZEBRA_DAY_S3_BACKUP_BUCKET env var."
            )
            resolved_bucket = _prompt_s3_bucket()
        else:
            console.print(
                "[red]✗[/red] S3 bucket required. Use --s3-bucket, --s3-config-file, "
                "or set ZEBRA_DAY_S3_BACKUP_BUCKET."
            )
            raise typer.Exit(1)
    kwargs["s3_bucket"] = resolved_bucket

    # S3 prefix: flag > config file > default
    resolved_prefix = s3_prefix or file_cfg.get("s3_prefix")
    if resolved_prefix:
        kwargs["s3_prefix"] = resolved_prefix

    if profile:
        kwargs["profile"] = profile
    if cost_center:
        kwargs["cost_center"] = cost_center
    if project:
        kwargs["project"] = project

    backend = DynamoBackend(**kwargs)

    if create_s3_if_missing:
        _ensure_s3_bucket(backend, create_if_missing=True)

    return backend


# -----------------------------------------------------------------
# init
# -----------------------------------------------------------------

@dynamo_app.command("init")
def init_cmd(
    table_name: str = typer.Option(
        "zebra-day-config", "--table-name", "-t", help="DynamoDB table name"
    ),
    region: str = typer.Option(
        None, "--region", "-r", help="AWS region [default: env or us-east-1]"
    ),
    s3_bucket: str = typer.Option(
        None, "--s3-bucket", "-b", help="S3 bucket for backups"
    ),
    s3_prefix: str = typer.Option(
        "zebra-day/", "--s3-prefix", help="S3 key prefix"
    ),
    s3_config_file: str = typer.Option(
        None, "--s3-config-file", help="JSON file with S3 bucket config (keys: s3_bucket, s3_prefix, region)"
    ),
    profile: str = typer.Option(
        None, "--profile", "-p", help="AWS profile name"
    ),
    cost_center: str = typer.Option(
        None, "--cost-center", help="lsmc-cost-center tag [default: env or 'global']"
    ),
    project: str = typer.Option(
        None, "--project", help="lsmc-project tag [default: env or 'zebra-day+{region}']"
    ),
    skip_checks: bool = typer.Option(
        False, "--skip-checks", help="Skip AWS permission pre-flight checks"
    ),
):
    """Create DynamoDB table and S3 bucket for shared configuration."""
    backend = _get_backend(
        table_name=table_name,
        region=region,
        s3_bucket=s3_bucket,
        s3_prefix=s3_prefix,
        profile=profile,
        cost_center=cost_center,
        project=project,
        s3_config_file=s3_config_file,
    )

    console.print("\n[bold cyan]DynamoDB Shared Config Init[/bold cyan]\n")

    # --- AWS permission pre-flight checks ---
    if not skip_checks:
        console.print("[cyan]→[/cyan] Checking AWS permissions...")
        perm_result = backend.check_aws_permissions()

        # Show identity
        ident = perm_result.get("identity", {})
        if ident.get("arn"):
            console.print(f"  Identity: [dim]{ident['arn']}[/dim]")
            console.print(f"  Account:  [dim]{ident['account']}[/dim]")
        elif ident.get("error"):
            console.print(f"  [red]✗ Credentials failed:[/red] {ident['error']}")

        # Show each check
        for chk in perm_result.get("checks", []):
            icon = "[green]✓[/green]" if chk["ok"] else "[red]✗[/red]"
            console.print(f"  {icon} {chk['action']}: {chk['detail']}")

        if not perm_result["all_ok"]:
            console.print(
                "\n[red]✗ Permission checks failed.[/red] "
                "Fix the issues above or use --skip-checks to bypass."
            )
            raise typer.Exit(1)
        console.print("[green]✓[/green] All permission checks passed\n")

    # Create table
    console.print(f"[cyan]→[/cyan] Creating DynamoDB table '{backend.table_name}'...")
    try:
        backend.create_table()
        console.print(f"[green]✓[/green] Table '{backend.table_name}' created and active")
    except Exception as exc:
        if "ResourceInUseException" in str(type(exc).__name__) or "already exists" in str(exc).lower():
            console.print(f"[yellow]⚠[/yellow] Table '{backend.table_name}' already exists")
        else:
            console.print(f"[red]✗[/red] Failed to create table: {exc}")
            raise typer.Exit(1)

    # Create S3 bucket (creates if not exists, applies tags)
    console.print(f"[cyan]→[/cyan] Ensuring S3 bucket '{backend.s3_bucket}' exists...")
    try:
        backend.create_s3_bucket()
        console.print(f"[green]✓[/green] S3 bucket '{backend.s3_bucket}' ready")
    except Exception as exc:
        console.print(f"[red]✗[/red] Failed to create/access bucket: {exc}")
        raise typer.Exit(1)

    # Write META
    console.print("[cyan]→[/cyan] Writing metadata...")
    backend.write_meta()
    console.print("[green]✓[/green] META item written")

    # Print env var instructions
    console.print("\n[bold]Set these environment variables:[/bold]\n")
    console.print(f"  export ZEBRA_DAY_CONFIG_BACKEND=dynamodb")
    console.print(f"  export ZEBRA_DAY_DYNAMO_TABLE={backend.table_name}")
    console.print(f"  export ZEBRA_DAY_DYNAMO_REGION={backend.region}")
    console.print(f"  export ZEBRA_DAY_S3_BACKUP_BUCKET={backend.s3_bucket}")
    console.print(f"  export ZEBRA_DAY_S3_BACKUP_PREFIX={backend.s3_prefix}")


# -----------------------------------------------------------------
# status
# -----------------------------------------------------------------

@dynamo_app.command("status")
def status_cmd(
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    create_s3_if_missing: bool = typer.Option(
        False, "--create-s3-if-missing", help="Auto-create S3 bucket if it doesn't exist"
    ),
):
    """Show DynamoDB table and S3 backup status."""
    try:
        backend = _get_backend_from_env(
            json_output=json_output,
            create_s3_if_missing=create_s3_if_missing,
        )
    except (ConfigError, ImportError) as exc:
        console.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1)

    try:
        status = backend.get_status()
    except Exception as exc:
        if "not found" in str(exc).lower() or "ResourceNotFoundException" in str(type(exc).__name__):
            console.print(
                f"[red]✗[/red] Table not found. Run 'zday dynamo init' first."
            )
            raise typer.Exit(1)
        raise

    template_count = len(backend.list_templates())

    if json_output:
        status["template_count"] = template_count
        console.print(json_mod.dumps(status, indent=2, default=str))
        return

    console.print("\n[bold cyan]DynamoDB Shared Config Status[/bold cyan]\n")

    tbl = Table(show_header=False, box=None, pad_edge=False)
    tbl.add_column("Key", style="cyan", min_width=20)
    tbl.add_column("Value")
    tbl.add_row("Table", status["table_name"])
    tbl.add_row("Region", status["region"])
    tbl.add_row("Status", f"[green]{status['table_status']}[/green]" if status["table_status"] == "ACTIVE" else status["table_status"])
    tbl.add_row("Items", str(status["item_count"]))
    tbl.add_row("Templates", str(template_count))
    tbl.add_row("Config Version", str(status["config_version"]))
    tbl.add_row("Config Updated", status["config_updated_at"] or "never")
    tbl.add_row("", "")
    tbl.add_row("S3 Bucket", status["s3_bucket"])
    tbl.add_row("S3 Prefix", status["s3_prefix"])
    tbl.add_row("Backups", str(status["backup_count"]))
    tbl.add_row("Last Backup", status["last_backup_at"] or "never")
    console.print(tbl)
    console.print()


# -----------------------------------------------------------------
# bootstrap
# -----------------------------------------------------------------

@dynamo_app.command("bootstrap")
def bootstrap_cmd(
    config_file: str = typer.Option(
        None, "--config-file", "-c", help="Source config file [default: XDG config path]"
    ),
    templates_dir: str = typer.Option(
        None, "--templates-dir", "-d", help="Source templates directory"
    ),
    include_package: bool = typer.Option(
        True, "--include-package/--no-include-package", help="Include package-shipped templates"
    ),
    create_s3_if_missing: bool = typer.Option(
        False, "--create-s3-if-missing", help="Auto-create S3 bucket if it doesn't exist"
    ),
):
    """Push local config and templates to DynamoDB."""
    from zebra_day import paths as xdg

    try:
        backend = _get_backend_from_env(create_s3_if_missing=create_s3_if_missing)
    except (ConfigError, ImportError) as exc:
        console.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1)

    console.print("\n[bold cyan]DynamoDB Bootstrap[/bold cyan]\n")

    # Load local config
    cfg_path = Path(config_file) if config_file else xdg.get_config_file_path()
    config_items_written = 0
    if cfg_path.exists():
        import yaml

        with open(cfg_path) as f:
            config = yaml.safe_load(f) or {}
        backend.save_config(config)
        config_items_written = 1
        console.print(f"[green]✓[/green] Config uploaded from {cfg_path}")
    else:
        console.print(f"[yellow]⚠[/yellow] Config not found: {cfg_path}")

    # Upload templates
    tpl_dirs: list[Path] = []
    if templates_dir:
        tpl_dirs.append(Path(templates_dir))
    else:
        # XDG user label_styles
        user_styles = xdg.get_config_dir() / "label_styles"
        if user_styles.is_dir():
            tpl_dirs.append(user_styles)

    if include_package:
        from importlib.resources import files

        pkg_styles = Path(str(files("zebra_day"))) / "etc" / "label_styles"
        if pkg_styles.is_dir():
            tpl_dirs.append(pkg_styles)

    templates_written = 0
    seen_stems: set[str] = set()
    for d in tpl_dirs:
        for zpl_file in sorted(d.glob("*.zpl")):
            stem = zpl_file.stem
            if stem in seen_stems:
                continue
            seen_stems.add(stem)
            content = zpl_file.read_text()
            backend.save_template(stem, content)
            templates_written += 1

    console.print(f"[green]✓[/green] {templates_written} template(s) uploaded")

    # Force backup
    prefix = backend.backup_to_s3(triggered_by="bootstrap", force=True)
    console.print(f"[green]✓[/green] Backup written to s3://{backend.s3_bucket}/{prefix}")
    console.print(f"\n[bold green]Bootstrap complete:[/bold green] {config_items_written} config + {templates_written} templates\n")
    console.print()



# -----------------------------------------------------------------
# export
# -----------------------------------------------------------------

@dynamo_app.command("export")
def export_cmd(
    output_dir: str = typer.Option(
        "./zebra-day-export", "--output-dir", "-o", help="Target directory"
    ),
    fmt: str = typer.Option(
        "json", "--format", "-f", help="Config format: json or yaml"
    ),
):
    """Pull DynamoDB config and templates to local files."""
    try:
        backend = _get_backend_from_env()
    except (ConfigError, ImportError) as exc:
        console.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1)

    out = Path(output_dir)
    tpl_dir = out / "templates"
    tpl_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"\n[bold cyan]DynamoDB Export → {out}[/bold cyan]\n")

    # Export config
    config = backend.load_config()
    if fmt == "yaml":
        import yaml

        config_path = out / "config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    else:
        config_path = out / "config.json"
        with open(config_path, "w") as f:
            json_mod.dump(config, f, indent=2, default=str)

    console.print(f"[green]✓[/green] Config written to {config_path}")

    # Export templates
    templates = backend.list_templates()
    for stem in templates:
        content = backend.get_template(stem)
        tpl_path = tpl_dir / f"{stem}.zpl"
        tpl_path.write_text(content)

    console.print(f"[green]✓[/green] {len(templates)} template(s) written to {tpl_dir}")
    console.print()


# -----------------------------------------------------------------
# backup
# -----------------------------------------------------------------

@dynamo_app.command("backup")
def backup_cmd(
    create_s3_if_missing: bool = typer.Option(
        False, "--create-s3-if-missing", help="Auto-create S3 bucket if it doesn't exist"
    ),
):
    """Trigger an immediate S3 backup snapshot."""
    try:
        backend = _get_backend_from_env(create_s3_if_missing=create_s3_if_missing)
    except (ConfigError, ImportError) as exc:
        console.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1)

    console.print("\n[bold cyan]DynamoDB Backup[/bold cyan]\n")

    try:
        prefix = backend.backup_to_s3(triggered_by="cli-manual", force=True)
        console.print(f"[green]✓[/green] Backup written to s3://{backend.s3_bucket}/{prefix}")
    except Exception as exc:
        console.print(f"[red]✗[/red] Backup failed: {exc}")
        raise typer.Exit(1)
    console.print()


# -----------------------------------------------------------------
# restore
# -----------------------------------------------------------------

@dynamo_app.command("restore")
def restore_cmd(
    s3_key: str = typer.Option(
        None, "--s3-key", "-k", help="S3 key prefix of the backup to restore"
    ),
    list_backups: bool = typer.Option(
        False, "--list", "-l", help="List available backups"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
):
    """Restore DynamoDB from an S3 backup."""
    try:
        backend = _get_backend_from_env()
    except (ConfigError, ImportError) as exc:
        console.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1)

    if list_backups:
        backups = backend.list_backups()
        if not backups:
            console.print("[yellow]No backups found.[/yellow]")
            raise typer.Exit(0)

        tbl = Table(title="Available Backups")
        tbl.add_column("#", style="dim")
        tbl.add_column("Timestamp", style="cyan")
        tbl.add_column("Templates", justify="right")
        tbl.add_column("Triggered By")
        tbl.add_column("S3 Prefix", style="dim")

        for i, b in enumerate(backups, 1):
            tbl.add_row(
                str(i),
                b.get("backup_timestamp", "?"),
                str(b.get("template_count", "?")),
                b.get("triggered_by", "?"),
                b.get("_s3_prefix", "?"),
            )
        console.print(tbl)
        return

    if not s3_key:
        console.print("[red]✗[/red] --s3-key is required. Use --list to see available backups.")
        raise typer.Exit(1)

    if not yes:
        typer.confirm(
            f"Restore from s3://{backend.s3_bucket}/{s3_key}? This overwrites current data.",
            abort=True,
        )

    console.print(f"\n[bold cyan]Restoring from {s3_key}[/bold cyan]\n")
    try:
        backend.restore_from_s3(s3_key)
        console.print("[green]✓[/green] Restore complete")
    except Exception as exc:
        console.print(f"[red]✗[/red] Restore failed: {exc}")
        raise typer.Exit(1)
    console.print()


# -----------------------------------------------------------------
# destroy
# -----------------------------------------------------------------

@dynamo_app.command("destroy")
def destroy_cmd(
    yes: bool = typer.Option(False, "--yes", "-y", help="Required safety gate"),
):
    """Delete DynamoDB table (preserves S3 backups)."""
    if not yes:
        console.print("[red]✗[/red] --yes flag required for safety")
        raise typer.Exit(1)

    try:
        backend = _get_backend_from_env()
    except (ConfigError, ImportError) as exc:
        console.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1)

    console.print("\n[bold red]DynamoDB Table Destruction[/bold red]\n")

    # Final backup
    console.print("[cyan]→[/cyan] Creating final backup...")
    try:
        prefix = backend.backup_to_s3(triggered_by="pre-destroy", force=True)
        console.print(f"[green]✓[/green] Final backup: s3://{backend.s3_bucket}/{prefix}")
    except Exception as exc:
        console.print(f"[yellow]⚠[/yellow] Backup failed: {exc}")

    # Delete table
    console.print(f"[cyan]→[/cyan] Deleting table '{backend.table_name}'...")
    try:
        backend.delete_table()
        console.print(f"[green]✓[/green] Table deleted. Backups preserved in S3.")
    except Exception as exc:
        console.print(f"[red]✗[/red] Delete failed: {exc}")
        raise typer.Exit(1)
    console.print()


def register(registry: CommandRegistry, spec: CliSpec) -> None:
    """cli-core-yo plugin: register the dynamo command group."""
    registry.add_typer_app(None, dynamo_app, "dynamo", "DynamoDB shared configuration management")
