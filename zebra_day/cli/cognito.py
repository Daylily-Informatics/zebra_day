"""Cognito/daycog integration commands for zebra_day."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Any

import typer
from cli_core_yo import output
from cli_core_yo.runtime import get_context

from zebra_day.settings import ZebraDaySettings
from zebra_day.web.auth import load_daycog_contract

if TYPE_CHECKING:
    from cli_core_yo.registry import CommandRegistry
    from cli_core_yo.spec import CliSpec

cognito_app = typer.Typer(help="daycog-backed Cognito contract commands")


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
    settings = ZebraDaySettings.from_context()
    payload = _status_payload(settings)
    if get_context().json_mode:
        output.emit_json(payload)
        return
    output.heading("Cognito Contract")
    output.detail(f"Mode: {payload['mode']}")
    output.detail(f"Expected client name: {payload['expected_client_name']}")
    output.detail(f"Pool: {payload['user_pool_id']}")
    output.detail(f"Region: {payload['region']}")
    output.detail(f"Client ID: {payload['app_client_id']}")
    output.detail(f"Domain: {payload['domain']}")
    output.detail(f"Configured redirect URI: {payload['redirect_uri']}")
    output.detail(f"Configured logout URL: {payload['logout_url']}")


@cognito_app.command("bind")
def bind() -> None:
    settings = ZebraDaySettings.from_context()
    payload = {
        "client_name": "zebra-day",
        "callback_url": _runtime_callback_url(settings),
        "logout_url": _runtime_logout_url(settings),
    }
    if get_context().json_mode:
        output.emit_json(payload)
        return
    output.heading("zebra_day Cognito Binding")
    output.detail(f"App client name: {payload['client_name']}")
    output.detail(f"Callback URL: {payload['callback_url']}")
    output.detail(f"Logout URL: {payload['logout_url']}")
    output.detail("Use daycog to create or update the matching app client.")


@cognito_app.command("import")
def import_context() -> None:
    payload = _status_payload(ZebraDaySettings.from_context())
    if get_context().json_mode:
        output.emit_json(payload)
        return
    output.success("Loaded Cognito runtime contract from the active daycog context")
    output.detail(f"Pool: {payload['user_pool_id']}")
    output.detail(f"Client name: {payload['app_client_name']}")


@cognito_app.command("validate")
def validate() -> None:
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
            output.emit_json({"ok": False, "issues": issues, **payload})
        else:
            output.error("Cognito contract validation failed")
            for issue in issues:
                output.bullet(issue)
        raise typer.Exit(1)
    if get_context().json_mode:
        output.emit_json({"ok": True, **payload})
        return
    output.success("Cognito contract validation passed")


@cognito_app.command(
    "daycog",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def daycog_passthrough(ctx: typer.Context) -> None:
    if not ctx.args:
        output.error("Missing daycog arguments")
        raise typer.Exit(1)
    result = _run_daycog(list(ctx.args))
    if result.stdout:
        output.print_text(result.stdout.rstrip())
    if result.returncode != 0:
        if result.stderr:
            output.error(result.stderr.strip())
        raise typer.Exit(result.returncode)


def register(registry: CommandRegistry, spec: CliSpec) -> None:
    del spec
    registry.add_typer_app(None, cognito_app, "cognito", "Cognito/daycog integration")
