"""User and role management commands for zebra_day Cognito groups."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import boto3
import typer
from cli_core_yo import ccyo_out
from cli_core_yo.runtime import get_context

from zebra_day.cli._registry_v2 import REQUIRED_JSON, REQUIRED_MUTATING, register_group_commands
from zebra_day.settings import ZebraDaySettings
from zebra_day.web.auth import load_daycog_contract

if TYPE_CHECKING:
    from cli_core_yo.registry import CommandRegistry
    from cli_core_yo.spec import CliSpec

users_app = typer.Typer(help="Manage zebra_day Cognito group membership")


def _cognito_client():
    contract = load_daycog_contract()
    profile = contract.get("aws_profile", "").strip()
    session_kwargs: dict[str, Any] = {"region_name": contract.get("region", "")}
    if profile and profile != "default":
        session_kwargs["profile_name"] = profile
    session = boto3.Session(**session_kwargs)
    return session.client("cognito-idp"), contract


@users_app.command("status")
def status() -> None:
    """Show the resolved Zebra auth mode and group-role mapping."""
    settings = ZebraDaySettings.from_context()
    payload = {
        "auth_mode": settings.auth_mode,
        "group_role_map": settings.cognito_group_role_map,
    }
    if get_context().json_mode:
        ccyo_out.emit_json(payload)
        return
    ccyo_out.heading("zebra_day User Roles")
    ccyo_out.detail(f"Auth mode: {settings.auth_mode}")
    for group_name, role_name in sorted(settings.cognito_group_role_map.items()):
        ccyo_out.bullet(f"{group_name} -> {role_name}")


@users_app.command("list-groups")
def list_groups() -> None:
    """List available Cognito groups from the bound user pool."""
    client, contract = _cognito_client()
    response = client.list_groups(UserPoolId=contract["user_pool_id"])
    groups = sorted(group["GroupName"] for group in response.get("Groups", []))
    if get_context().json_mode:
        ccyo_out.emit_json(groups)
        return
    for group in groups:
        ccyo_out.bullet(group)


def _add_user_to_group(username: str, group_name: str) -> None:
    client, contract = _cognito_client()
    client.admin_add_user_to_group(
        UserPoolId=contract["user_pool_id"],
        Username=username,
        GroupName=group_name,
    )


@users_app.command("grant-admin")
def grant_admin(username: str = typer.Argument(..., help="Cognito username or email")) -> None:
    """Grant zebra-day admin groups to one Cognito user."""
    for group_name in ("platform-admin", "zebra-day-admin"):
        _add_user_to_group(username, group_name)
    ccyo_out.success(f"Granted admin groups to {username}")


@users_app.command("grant-operator")
def grant_operator(username: str = typer.Argument(..., help="Cognito username or email")) -> None:
    """Grant the zebra-day operator group to one Cognito user."""
    _add_user_to_group(username, "zebra-day-operator")
    ccyo_out.success(f"Granted operator group to {username}")


def register(registry: CommandRegistry, spec: CliSpec) -> None:
    _ = spec
    register_group_commands(
        registry,
        "users",
        "Cognito user/group management",
        [
            ("status", status, REQUIRED_JSON),
            ("list-groups", list_groups, REQUIRED_JSON),
            ("grant-admin", grant_admin, REQUIRED_MUTATING),
            ("grant-operator", grant_operator, REQUIRED_MUTATING),
        ],
    )
