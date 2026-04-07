"""Cognito/daycog integration commands for zebra_day."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, cast

import typer
from cli_core_yo import ccyo_out
from cli_core_yo.runtime import get_context

from zebra_day.cli._registry_v2 import REQUIRED_JSON, REQUIRED_MUTATING, register_group_commands
from zebra_day.settings import ZebraDaySettings
from zebra_day.web.auth import load_daycog_contract

if TYPE_CHECKING:
    from cli_core_yo.registry import CommandRegistry
    from cli_core_yo.spec import CliSpec

cognito_app = typer.Typer(help="daycog-backed Cognito contract commands")
_PASSTHROUGH_ARGS = typer.Argument(None, metavar="ARGS...")


class _ArgsNamespace:
    args: Sequence[str] | None


def _runtime_callback_url(settings: ZebraDaySettings) -> str:
    return f"https://localhost:{settings.port}{settings.callback_path}"


def _runtime_logout_url(settings: ZebraDaySettings) -> str:
    return f"https://localhost:{settings.port}/"


def _run_daycog(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["daycog", *args],
        capture_output=True,
        text=True,
    )


def _passthrough_args(args: Sequence[str] | _ArgsNamespace | None) -> list[str]:
    if args is None:
        return []
    if isinstance(args, (list, tuple)):
        return list(args)
    return list(cast(_ArgsNamespace, args).args or [])


def _status_payload(settings: ZebraDaySettings) -> dict[str, Any]:
    contract = load_daycog_contract()
    return {
        "mode": settings.auth_mode,
        "deployment_code": settings.deployment_code,
        "expected_client_name": "zebra-day",
        "expected_callback_url": _runtime_callback_url(settings),
        "expected_logout_url": _runtime_logout_url(settings),
        "region": contract.get("region", ""),
        "user_pool_id": contract.get("user_pool_id", ""),
        "app_client_id": contract.get("app_client_id", ""),
        "domain": contract.get("cognito_domain", ""),
        "app_client_name": contract.get("client_name", ""),
        "redirect_uri": contract.get("callback_url", ""),
        "logout_url": contract.get("logout_url", ""),
    }


@cognito_app.command("status")
def status() -> None:
    """Show the resolved zebra_day Cognito contract."""
    settings = ZebraDaySettings.from_context()
    payload = _status_payload(settings)
    if get_context().json_mode:
        ccyo_out.emit_json(payload)
        return
    ccyo_out.heading("Cognito Contract")
    ccyo_out.detail(f"Mode: {payload['mode']}")
    ccyo_out.detail(f"Expected client name: {payload['expected_client_name']}")
    ccyo_out.detail(f"Pool: {payload['user_pool_id']}")
    ccyo_out.detail(f"Region: {payload['region']}")
    ccyo_out.detail(f"Client ID: {payload['app_client_id']}")
    ccyo_out.detail(f"Domain: {payload['domain']}")
    ccyo_out.detail(f"Configured redirect URI: {payload['redirect_uri']}")
    ccyo_out.detail(f"Configured logout URL: {payload['logout_url']}")


@cognito_app.command("bind")
def bind() -> None:
    """Print the runtime callback and logout URLs zebra_day expects."""
    settings = ZebraDaySettings.from_context()
    payload = {
        "client_name": "zebra-day",
        "callback_url": _runtime_callback_url(settings),
        "logout_url": _runtime_logout_url(settings),
    }
    if get_context().json_mode:
        ccyo_out.emit_json(payload)
        return
    ccyo_out.heading("zebra_day Cognito Binding")
    ccyo_out.detail(f"App client name: {payload['client_name']}")
    ccyo_out.detail(f"Callback URL: {payload['callback_url']}")
    ccyo_out.detail(f"Logout URL: {payload['logout_url']}")
    ccyo_out.detail("Use daycog to create or update the matching app client.")


@cognito_app.command("import")
def import_context() -> None:
    """Load the active Cognito runtime contract from daycog."""
    payload = _status_payload(ZebraDaySettings.from_context())
    if get_context().json_mode:
        ccyo_out.emit_json(payload)
        return
    ccyo_out.success("Loaded Cognito runtime contract from the daycog config file")
    ccyo_out.detail(f"Pool: {payload['user_pool_id']}")
    ccyo_out.detail(f"Client name: {payload['app_client_name']}")


@cognito_app.command("validate")
def validate() -> None:
    """Validate the bound Cognito contract against zebra_day expectations."""
    settings = ZebraDaySettings.from_context()
    payload = _status_payload(settings)
    issues: list[str] = []
    if payload["app_client_name"] and payload["app_client_name"] != "zebra-day":
        issues.append("Active app client name is not zebra-day")
    if payload["redirect_uri"] and payload["redirect_uri"] != payload["expected_callback_url"]:
        issues.append("Configured redirect URI does not match zebra_day runtime callback URL")
    if payload["logout_url"] and payload["logout_url"] != payload["expected_logout_url"]:
        issues.append("Configured logout URL does not match zebra_day runtime logout URL")
    if issues:
        if get_context().json_mode:
            ccyo_out.emit_json({"ok": False, "issues": issues, **payload})
        else:
            ccyo_out.error("Cognito contract validation failed")
            for issue in issues:
                ccyo_out.bullet(issue)
        raise typer.Exit(1)
    if get_context().json_mode:
        ccyo_out.emit_json({"ok": True, **payload})
        return
    ccyo_out.success("Cognito contract validation passed")


@cognito_app.command("daycog")
def daycog_passthrough(
    args: list[str] = _PASSTHROUGH_ARGS,
) -> None:
    """Pass through to `daycog ...`."""
    resolved_args = _passthrough_args(args)
    if not resolved_args:
        ccyo_out.error("Missing daycog arguments")
        raise typer.Exit(1)
    result = _run_daycog(resolved_args)
    if result.stdout:
        ccyo_out.print_text(result.stdout.rstrip())
    if result.returncode != 0:
        if result.stderr:
            ccyo_out.error(result.stderr.strip())
        raise typer.Exit(result.returncode)


def register(registry: CommandRegistry, spec: CliSpec) -> None:
    _ = spec
    register_group_commands(
        registry,
        "cognito",
        "Cognito/daycog integration",
        [
            ("status", status, REQUIRED_JSON),
            ("bind", bind, REQUIRED_JSON),
            ("import", import_context, REQUIRED_JSON),
            ("validate", validate, REQUIRED_JSON),
            ("daycog", daycog_passthrough, REQUIRED_MUTATING),
        ],
    )
