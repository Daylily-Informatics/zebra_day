"""User and role management commands for zebra_day Cognito groups."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import boto3
import typer
from cli_core_yo import output
from cli_core_yo.runtime import get_context

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
    settings = ZebraDaySettings.from_context()
    payload = {
        "auth_mode": settings.auth_mode,
        "group_role_map": settings.cognito_group_role_map,
    }
    if get_context().json_mode:
        output.emit_json(payload)
        return
    output.heading("zebra_day User Roles")
    output.detail(f"Auth mode: {settings.auth_mode}")
    for group_name, role_name in sorted(settings.cognito_group_role_map.items()):
        output.bullet(f"{group_name} -> {role_name}")


@users_app.command("list-groups")
def list_groups() -> None:
    client, contract = _cognito_client()
    response = client.list_groups(UserPoolId=contract["user_pool_id"])
    groups = sorted(group["GroupName"] for group in response.get("Groups", []))
    if get_context().json_mode:
        output.emit_json(groups)
        return
    for group in groups:
        output.bullet(group)


def _add_user_to_group(username: str, group_name: str) -> None:
    client, contract = _cognito_client()
    client.admin_add_user_to_group(
        UserPoolId=contract["user_pool_id"],
        Username=username,
        GroupName=group_name,
    )


@users_app.command("grant-admin")
def grant_admin(username: str = typer.Argument(..., help="Cognito username or email")) -> None:
    for group_name in ("platform-admin", "zebra-day-admin"):
        _add_user_to_group(username, group_name)
    output.success(f"Granted admin groups to {username}")


@users_app.command("grant-operator")
def grant_operator(username: str = typer.Argument(..., help="Cognito username or email")) -> None:
    _add_user_to_group(username, "zebra-day-operator")
    output.success(f"Granted operator group to {username}")


def register(registry: CommandRegistry, spec: CliSpec) -> None:
    del spec
    registry.add_typer_app(None, users_app, "users", "Cognito user/group management")
