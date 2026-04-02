"""Simple Cognito group-to-role helpers for zebra_day."""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class Role(StrEnum):
    OPERATOR = "OPERATOR"
    ADMIN = "ADMIN"


DOCS_ALLOWED_ROLES = {Role.OPERATOR.value, Role.ADMIN.value}
ADMIN_ALLOWED_ROLES = {Role.ADMIN.value}
OPERATOR_ALLOWED_ROLES = {Role.OPERATOR.value, Role.ADMIN.value}


def normalize_group_role_map(raw_map: dict[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for group_name, role_name in raw_map.items():
        group = str(group_name).strip()
        role = str(role_name).strip().upper()
        if not group or role not in {Role.OPERATOR.value, Role.ADMIN.value}:
            continue
        normalized[group] = role
    return normalized


def roles_from_groups(groups: list[str], group_role_map: dict[str, str]) -> list[str]:
    normalized_map = normalize_group_role_map(group_role_map)
    roles = {normalized_map[group] for group in groups if group in normalized_map}
    if Role.ADMIN.value in roles:
        roles.add(Role.OPERATOR.value)
    return sorted(roles)


def has_any_role(user_roles: list[str], allowed_roles: set[str]) -> bool:
    return bool(set(user_roles) & allowed_roles)


def parse_groups(raw_groups: Any) -> list[str]:
    if raw_groups is None:
        return []
    if isinstance(raw_groups, list):
        return [str(item).strip() for item in raw_groups if str(item).strip()]
    if isinstance(raw_groups, str):
        stripped = raw_groups.strip()
        return [stripped] if stripped else []
    return [str(raw_groups).strip()] if str(raw_groups).strip() else []
