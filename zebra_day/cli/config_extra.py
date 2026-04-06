"""Extra config subcommands for zebra_day."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from cli_core_yo import ccyo_out

from zebra_day.client import ZebraDayClient
from zebra_day.settings import ZebraDaySettings
from zebra_day.web.app import create_app

if TYPE_CHECKING:
    from cli_core_yo.registry import CommandRegistry
    from cli_core_yo.spec import CliSpec


def _status() -> None:
    settings = ZebraDaySettings.from_context()
    client = ZebraDayClient(settings)
    ccyo_out.heading("Config Status")
    ccyo_out.detail(f"Deployment: {settings.deployment_code}")
    ccyo_out.detail(f"Config path: {settings.config_path}")
    ccyo_out.detail(f"TapDB config: {settings.tapdb_config_path}")
    ccyo_out.detail(f"TapDB namespace: {settings.tapdb_database_name}")
    ccyo_out.detail(f"Auth mode: {settings.auth_mode}")
    ccyo_out.detail(f"Labs: {len(client.list_labs())}")
    ccyo_out.detail(f"Printers: {len(client.list_printers())}")
    ccyo_out.detail(f"Templates: {len(client.list_templates())}")


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
    registry.add_command("config", "status", _status, "Show resolved zebra_day config status")
    registry.add_command("config", "routes", _routes, "List registered web routes")
