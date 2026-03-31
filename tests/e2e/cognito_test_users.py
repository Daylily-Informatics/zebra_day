from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.exceptions import ClientError

DEFAULT_STANDARD_EMAIL = "zebra-day-e2e-standard@example.com"
DEFAULT_ADMIN_EMAIL = "zebra-day-e2e-admin@example.com"
DEFAULT_STANDARD_PASSWORD = "CodexPlaywright1!"
DEFAULT_ADMIN_PASSWORD = "CodexPlaywright1!"
STANDARD_GROUPS = ("zebra-day-operator",)
ADMIN_GROUPS = ("platform-admin", "zebra-day-admin")


@dataclass(frozen=True)
class E2ECredentials:
    email: str
    password: str
    user_pool_id: str
    region: str
    groups: tuple[str, ...]


def _required(name: str) -> str:
    value = str(os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required E2E setting: {name}")
    return value


def _cognito_client(region: str):
    session = boto3.Session(
        profile_name=(os.getenv("ZDAY_E2E_AWS_PROFILE") or os.getenv("AWS_PROFILE") or None),
        region_name=region,
    )
    return session.client("cognito-idp", region_name=region)


def _attributes(payload: dict[str, Any]) -> dict[str, str]:
    return {
        str(item.get("Name") or "").strip(): str(item.get("Value") or "").strip()
        for item in payload.get("UserAttributes", []) or []
        if str(item.get("Name") or "").strip()
    }


def _get_user(client, *, pool_id: str, email: str) -> dict[str, Any]:
    return client.admin_get_user(UserPoolId=pool_id, Username=email)


def _ensure_group(client, *, pool_id: str, group_name: str) -> None:
    try:
        client.get_group(UserPoolId=pool_id, GroupName=group_name)
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
        client.create_group(
            UserPoolId=pool_id,
            GroupName=group_name,
            Description=f"zebra_day E2E auto-created group {group_name}",
        )


def _ensure_membership(client, *, pool_id: str, email: str, group_name: str) -> None:
    try:
        client.admin_add_user_to_group(
            UserPoolId=pool_id,
            Username=email,
            GroupName=group_name,
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
        _ensure_group(client, pool_id=pool_id, group_name=group_name)
        client.admin_add_user_to_group(
            UserPoolId=pool_id,
            Username=email,
            GroupName=group_name,
        )


def _ensure_user(
    *,
    email_env: str,
    password_env: str,
    default_email: str,
    default_password: str,
    display_name: str,
    groups: tuple[str, ...],
) -> E2ECredentials:
    region = _required("ZDAY_E2E_COGNITO_REGION")
    pool_id = _required("ZDAY_E2E_COGNITO_USER_POOL_ID")
    email = str(os.getenv(email_env) or default_email).strip().lower()
    password = str(os.getenv(password_env) or default_password).strip() or default_password
    client = _cognito_client(region)

    try:
        user_payload = _get_user(client, pool_id=pool_id, email=email)
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "UserNotFoundException":
            raise
        client.admin_create_user(
            UserPoolId=pool_id,
            Username=email,
            TemporaryPassword=password,
            MessageAction="SUPPRESS",
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
                {"Name": "name", "Value": display_name},
            ],
        )
        user_payload = _get_user(client, pool_id=pool_id, email=email)

    client.admin_update_user_attributes(
        UserPoolId=pool_id,
        Username=email,
        UserAttributes=[
            {"Name": "email", "Value": email},
            {"Name": "email_verified", "Value": "true"},
            {"Name": "name", "Value": display_name},
        ],
    )
    client.admin_set_user_password(
        UserPoolId=pool_id,
        Username=email,
        Password=password,
        Permanent=True,
    )

    for group_name in groups:
        _ensure_membership(client, pool_id=pool_id, email=email, group_name=group_name)

    attrs = _attributes(user_payload)
    if not attrs.get("sub"):
        refreshed = _get_user(client, pool_id=pool_id, email=email)
        attrs = _attributes(refreshed)
    if not attrs.get("sub"):
        raise RuntimeError(f"E2E user {email} does not expose a Cognito sub")

    os.environ[email_env] = email
    os.environ[password_env] = password
    return E2ECredentials(
        email=email,
        password=password,
        user_pool_id=pool_id,
        region=region,
        groups=groups,
    )


def ensure_standard_user() -> E2ECredentials:
    return _ensure_user(
        email_env="ZDAY_E2E_STANDARD_EMAIL",
        password_env="ZDAY_E2E_STANDARD_PASSWORD",
        default_email=DEFAULT_STANDARD_EMAIL,
        default_password=DEFAULT_STANDARD_PASSWORD,
        display_name="Zebra Day E2E Standard",
        groups=STANDARD_GROUPS,
    )


def ensure_admin_user() -> E2ECredentials:
    return _ensure_user(
        email_env="ZDAY_E2E_ADMIN_EMAIL",
        password_env="ZDAY_E2E_ADMIN_PASSWORD",
        default_email=DEFAULT_ADMIN_EMAIL,
        default_password=DEFAULT_ADMIN_PASSWORD,
        display_name="Zebra Day E2E Admin",
        groups=ADMIN_GROUPS,
    )
