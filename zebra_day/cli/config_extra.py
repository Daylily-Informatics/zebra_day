"""Extra config subcommands for zebra_day (status, bootstrap, routes)."""

from __future__ import annotations

import socket
from typing import TYPE_CHECKING, Any, cast

import typer
from cli_core_yo import ccyo_out
from cli_core_yo.runtime import get_context

from zebra_day.client import ZebraDayClient
from zebra_day.settings import ZebraDaySettings, build_default_config_template
from zebra_day.web.app import create_app

if TYPE_CHECKING:
    from cli_core_yo.registry import CommandRegistry
    from cli_core_yo.spec import CliSpec


def _status() -> None:
    settings = ZebraDaySettings.from_context()
    pid_file = settings.state_dir / "gui.pid"
    gui_data: dict[str, Any] = {"running": False, "pid": None}
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            gui_data = {"running": True, "pid": pid}
        except (ValueError, ProcessLookupError, PermissionError):
            pid_file.unlink(missing_ok=True)

    status_data: dict[str, Any] = {
        "deployment_code": settings.deployment_code,
        "config_path": str(settings.config_path),
        "config_exists": settings.config_path.exists(),
        "auth_mode": settings.auth_mode,
        "tapdb": {
            "config_path": str(settings.tapdb_config_path),
            "config_exists": settings.tapdb_config_path.exists(),
            "client_id": settings.tapdb_client_id,
            "database_name": settings.tapdb_database_name,
            "env": settings.tapdb_env,
        },
        "gui": gui_data,
    }

    error_text = ""
    try:
        client = ZebraDayClient(settings)
        status_data["fleet"] = {
            "labs": client.list_labs(),
            "printer_count": len(client.list_printers()),
            "template_count": len(client.list_templates()),
            "label_profile_count": len(client.list_label_profiles()),
        }
    except Exception as exc:
        error_text = str(exc)
        status_data["fleet"] = {
            "labs": [],
            "printer_count": 0,
            "template_count": 0,
            "label_profile_count": 0,
            "error": error_text,
        }

    if get_context().json_mode:
        ccyo_out.emit_json(status_data)
        if error_text:
            raise typer.Exit(1)
        return

    ccyo_out.heading("zebra_day Status")
    ccyo_out.detail(f"Deployment: {settings.deployment_code}")
    ccyo_out.detail(f"Config: {settings.config_path}")
    ccyo_out.detail(f"TapDB config: {settings.tapdb_config_path}")
    ccyo_out.detail(
        f"TapDB namespace: {settings.tapdb_client_id}/{settings.tapdb_database_name} ({settings.tapdb_env})"
    )
    ccyo_out.detail(f"Auth mode: {settings.auth_mode}")
    if status_data["gui"]["running"]:
        ccyo_out.success(f"GUI server running (PID {status_data['gui']['pid']})")
    else:
        ccyo_out.warning("GUI server is not running")

    if error_text:
        ccyo_out.error(f"TapDB unavailable: {error_text}")
        raise typer.Exit(1)

    ccyo_out.success("TapDB connection verified")
    ccyo_out.detail(f"Labs: {', '.join(status_data['fleet']['labs']) or 'none'}")
    ccyo_out.detail(f"Printers: {status_data['fleet']['printer_count']}")
    ccyo_out.detail(f"Templates: {status_data['fleet']['template_count']}")
    ccyo_out.detail(f"Label profiles: {status_data['fleet']['label_profile_count']}")


def _derive_ip_stub() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect(("8.8.8.8", 80))
        local_ip = probe.getsockname()[0]
    return ".".join(local_ip.split(".")[:-1])


def _bootstrap(
    ip_stub: str | None = typer.Option(
        None,
        "--ip-stub",
        help="IP stub to scan after config creation, e.g. 192.168.1",
    ),
    lab: str = typer.Option("default", "--lab", help="Lab name for discovered printers"),
    skip_scan: bool = typer.Option(False, "--skip-scan", help="Do not scan for printers"),
) -> None:
    settings = ZebraDaySettings.from_context()
    config_created = False
    if not settings.config_path.exists():
        settings.config_path.parent.mkdir(parents=True, exist_ok=True)
        settings.config_path.write_bytes(build_default_config_template(settings.deployment_code))
        config_created = True

    result: dict[str, Any] = {
        "deployment_code": settings.deployment_code,
        "config_path": str(settings.config_path),
        "config_created": config_created,
        "tapdb_config_path": str(settings.tapdb_config_path),
        "tapdb_config_exists": settings.tapdb_config_path.exists(),
        "lab": lab,
        "discovered_printers": [],
    }

    if not settings.tapdb_config_path.exists():
        message = (
            f"TapDB config is required. Create {settings.tapdb_config_path} before using zebra_day."
        )
        if get_context().json_mode:
            result["error"] = message
            ccyo_out.emit_json(result)
        else:
            ccyo_out.error(message)
            ccyo_out.detail(f"Deployment config: {settings.config_path}")
        raise typer.Exit(1)

    client = ZebraDayClient(settings)
    if not skip_scan:
        resolved_ip_stub = ip_stub or _derive_ip_stub()
        printers = client.discover_printers(ip_stub=resolved_ip_stub, lab=lab)
        result["discovered_printers"] = [printer.to_payload() for printer in printers]
        result["ip_stub"] = resolved_ip_stub

    if get_context().json_mode:
        ccyo_out.emit_json(result)
        return

    ccyo_out.heading("zebra_day Bootstrap")
    if config_created:
        ccyo_out.success(f"Created config: {settings.config_path}")
    else:
        ccyo_out.detail(f"Using config: {settings.config_path}")
    ccyo_out.success(f"TapDB config found: {settings.tapdb_config_path}")
    if skip_scan:
        ccyo_out.detail("Skipped printer scan")
    else:
        ccyo_out.success(f"Discovered {len(result['discovered_printers'])} printer(s)")
    ccyo_out.heading("Next steps")
    ccyo_out.detail("zday gui start")
    ccyo_out.detail("zday printer list")
    ccyo_out.detail("zday config status")


def _routes() -> None:
    class _RouteClient:
        def list_labs(self):
            return []

        def list_printers(self, lab=None):
            del lab
            return []

        def list_templates(self):
            return []

        def list_label_profiles(self):
            return []

        def runtime_summary(self):
            return {}

    app = create_app(auth="none", client=cast(ZebraDayClient, _RouteClient()))
    rows: list[tuple[str, str]] = []
    for route in app.routes:
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if not methods or not path:
            continue
        for method in sorted(methods):
            if method in {"HEAD", "OPTIONS"}:
                continue
            rows.append((method, path))
    for method, path in sorted(rows, key=lambda item: (item[1], item[0])):
        ccyo_out.print_text(f"{method:<6} {path}")


def register(registry: CommandRegistry, spec: CliSpec) -> None:
    del spec
    registry.add_command("config", "status", _status, "Show zebra_day runtime, TapDB, and GUI status")
    registry.add_command("config", "bootstrap", _bootstrap, "Create deployment config and optionally scan for printers")
    registry.add_command("config", "routes", _routes, "List registered web routes")
