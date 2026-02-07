"""DynamoDB shared configuration CLI commands for zebra_day."""

from __future__ import annotations

import json as json_mod
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from cli_core_yo import output
from cli_core_yo.runtime import get_context
from rich.console import Console
from rich.table import Table

from zebra_day.exceptions import ConfigError

if TYPE_CHECKING:
    from cli_core_yo.registry import CommandRegistry
    from cli_core_yo.spec import CliSpec

dynamo_app = typer.Typer(help="DynamoDB shared configuration management")
console = Console()  # retained for Rich Table rendering


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
        output.error("No S3 bucket name provided.")
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
            output.action(
                f"Bucket '{backend.s3_bucket}' not found — creating..."
            )
            backend.create_s3_bucket()
            output.success(
                f"S3 bucket '{backend.s3_bucket}' created "
                f"(tags: lsmc-cost-center={backend.cost_center}, "
                f"lsmc-project={backend.project})"
            )
        else:
            output.warning(
                f"S3 bucket '{backend.s3_bucket}' does not exist. "
                "Use --create-s3-if-missing to auto-create."
            )


def _get_backend_from_env(
    *,
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
        if not get_context().json_mode and _is_interactive():
            output.warning("ZEBRA_DAY_S3_BACKUP_BUCKET is not set.")
            bucket = _prompt_s3_bucket()
            backend.s3_bucket = bucket
        else:
            output.error(
                "ZEBRA_DAY_S3_BACKUP_BUCKET is required when using "
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
        output.error(f"S3 config file not found: {path}")
        raise typer.Exit(1)
    try:
        data = json_mod.loads(p.read_text())
    except Exception as exc:
        output.error(f"Failed to parse S3 config file: {exc}")
        raise typer.Exit(1)
    if not isinstance(data, dict):
        output.error("S3 config file must contain a JSON object")
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
            output.warning(
                "S3 bucket not specified via flag, config file, "
                "or ZEBRA_DAY_S3_BACKUP_BUCKET env var."
            )
            resolved_bucket = _prompt_s3_bucket()
        else:
            output.error(
                "S3 bucket required. Use --s3-bucket, --s3-config-file, "
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

    output.heading("DynamoDB Shared Config Init")

    # --- AWS permission pre-flight checks ---
    if not skip_checks:
        output.action("Checking AWS permissions...")
        perm_result = backend.check_aws_permissions()

        # Show identity
        ident = perm_result.get("identity", {})
        if ident.get("arn"):
            output.detail(f"Identity: {ident['arn']}")
            output.detail(f"Account:  {ident['account']}")
        elif ident.get("error"):
            output.error(f"Credentials failed: {ident['error']}")

        # Show each check
        for chk in perm_result.get("checks", []):
            if chk["ok"]:
                output.success(f"{chk['action']}: {chk['detail']}")
            else:
                output.error(f"{chk['action']}: {chk['detail']}")

        if not perm_result["all_ok"]:
            output.error(
                "Permission checks failed. "
                "Fix the issues above or use --skip-checks to bypass."
            )
            raise typer.Exit(1)
        output.success("All permission checks passed")

    # Create table
    output.action(f"Creating DynamoDB table '{backend.table_name}'...")
    try:
        backend.create_table()
        output.success(f"Table '{backend.table_name}' created and active")
    except Exception as exc:
        if "ResourceInUseException" in str(type(exc).__name__) or "already exists" in str(exc).lower():
            output.warning(f"Table '{backend.table_name}' already exists")
        else:
            output.error(f"Failed to create table: {exc}")
            raise typer.Exit(1)

    # Create S3 bucket (creates if not exists, applies tags)
    output.action(f"Ensuring S3 bucket '{backend.s3_bucket}' exists...")
    try:
        backend.create_s3_bucket()
        output.success(f"S3 bucket '{backend.s3_bucket}' ready")
    except Exception as exc:
        output.error(f"Failed to create/access bucket: {exc}")
        raise typer.Exit(1)

    # Write META
    output.action("Writing metadata...")
    backend.write_meta()
    output.success("META item written")

    # Print env var instructions
    output.heading("Set these environment variables")
    output.detail(f"export ZEBRA_DAY_CONFIG_BACKEND=dynamodb")
    output.detail(f"export ZEBRA_DAY_DYNAMO_TABLE={backend.table_name}")
    output.detail(f"export ZEBRA_DAY_DYNAMO_REGION={backend.region}")
    output.detail(f"export ZEBRA_DAY_S3_BACKUP_BUCKET={backend.s3_bucket}")
    output.detail(f"export ZEBRA_DAY_S3_BACKUP_PREFIX={backend.s3_prefix}")


# -----------------------------------------------------------------
# status
# -----------------------------------------------------------------

@dynamo_app.command("status")
def status_cmd(
    create_s3_if_missing: bool = typer.Option(
        False, "--create-s3-if-missing", help="Auto-create S3 bucket if it doesn't exist"
    ),
):
    """Show DynamoDB table and S3 backup status."""
    try:
        backend = _get_backend_from_env(
            create_s3_if_missing=create_s3_if_missing,
        )
    except (ConfigError, ImportError) as exc:
        output.error(str(exc))
        raise typer.Exit(1)

    try:
        status = backend.get_status()
    except Exception as exc:
        if "not found" in str(exc).lower() or "ResourceNotFoundException" in str(type(exc).__name__):
            output.error("Table not found. Run 'zday dynamo init' first.")
            raise typer.Exit(1)
        raise

    template_count = len(backend.list_templates())

    if get_context().json_mode:
        status["template_count"] = template_count
        output.emit_json(status)
        return

    output.heading("DynamoDB Shared Config Status")

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
        output.error(str(exc))
        raise typer.Exit(1)

    output.heading("DynamoDB Bootstrap")

    # Load local config
    cfg_path = Path(config_file) if config_file else xdg.get_config_file_path()
    config_items_written = 0
    if cfg_path.exists():
        import yaml

        with open(cfg_path) as f:
            config = yaml.safe_load(f) or {}
        backend.save_config(config)
        config_items_written = 1
        output.success(f"Config uploaded from {cfg_path}")
    else:
        output.warning(f"Config not found: {cfg_path}")

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

    output.success(f"{templates_written} template(s) uploaded")

    # Force backup
    prefix = backend.backup_to_s3(triggered_by="bootstrap", force=True)
    output.success(f"Backup written to s3://{backend.s3_bucket}/{prefix}")
    output.success(f"Bootstrap complete: {config_items_written} config + {templates_written} templates")



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
        output.error(str(exc))
        raise typer.Exit(1)

    out = Path(output_dir)
    tpl_dir = out / "templates"
    tpl_dir.mkdir(parents=True, exist_ok=True)

    output.heading(f"DynamoDB Export → {out}")

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

    output.success(f"Config written to {config_path}")

    # Export templates
    templates = backend.list_templates()
    for stem in templates:
        content = backend.get_template(stem)
        tpl_path = tpl_dir / f"{stem}.zpl"
        tpl_path.write_text(content)

    output.success(f"{len(templates)} template(s) written to {tpl_dir}")


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
        output.error(str(exc))
        raise typer.Exit(1)

    output.heading("DynamoDB Backup")

    try:
        prefix = backend.backup_to_s3(triggered_by="cli-manual", force=True)
        output.success(f"Backup written to s3://{backend.s3_bucket}/{prefix}")
    except Exception as exc:
        output.error(f"Backup failed: {exc}")
        raise typer.Exit(1)


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
        output.error(str(exc))
        raise typer.Exit(1)

    if list_backups:
        backups = backend.list_backups()
        if not backups:
            output.warning("No backups found.")
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
        output.error("--s3-key is required. Use --list to see available backups.")
        raise typer.Exit(1)

    if not yes:
        typer.confirm(
            f"Restore from s3://{backend.s3_bucket}/{s3_key}? This overwrites current data.",
            abort=True,
        )

    output.heading(f"Restoring from {s3_key}")
    try:
        backend.restore_from_s3(s3_key)
        output.success("Restore complete")
    except Exception as exc:
        output.error(f"Restore failed: {exc}")
        raise typer.Exit(1)


# -----------------------------------------------------------------
# destroy
# -----------------------------------------------------------------

@dynamo_app.command("destroy")
def destroy_cmd(
    yes: bool = typer.Option(False, "--yes", "-y", help="Required safety gate"),
):
    """Delete DynamoDB table (preserves S3 backups)."""
    if not yes:
        output.error("--yes flag required for safety")
        raise typer.Exit(1)

    try:
        backend = _get_backend_from_env()
    except (ConfigError, ImportError) as exc:
        output.error(str(exc))
        raise typer.Exit(1)

    output.heading("DynamoDB Table Destruction")

    # Final backup
    output.action("Creating final backup...")
    try:
        prefix = backend.backup_to_s3(triggered_by="pre-destroy", force=True)
        output.success(f"Final backup: s3://{backend.s3_bucket}/{prefix}")
    except Exception as exc:
        output.warning(f"Backup failed: {exc}")

    # Delete table
    output.action(f"Deleting table '{backend.table_name}'...")
    try:
        backend.delete_table()
        output.success("Table deleted. Backups preserved in S3.")
    except Exception as exc:
        output.error(f"Delete failed: {exc}")
        raise typer.Exit(1)


def register(registry: CommandRegistry, spec: CliSpec) -> None:
    """cli-core-yo plugin: register the dynamo command group."""
    registry.add_typer_app(None, dynamo_app, "dynamo", "DynamoDB shared configuration management")
