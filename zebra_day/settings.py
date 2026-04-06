"""Deployment-scoped settings for zebra_day."""

from __future__ import annotations

import colorsys
import hashlib
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from zebra_day import paths as xdg
from zebra_day.rbac import normalize_group_role_map

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8118
DEFAULT_SERVICE_NAME = "zebra-day"
DEFAULT_AUTH_MODE = "cognito"
DEFAULT_TAPDB_CLIENT_ID = "zebra-day"
DEFAULT_DEPLOYMENT_BANNER_COLOR = "#AFEEEE"
PRODUCTION_DEPLOYMENT_NAMES = {"prod", "production"}
DEFAULT_COGNITO_GROUP_ROLE_MAP = {
    "admin": "ADMIN",
    "platform-admin": "ADMIN",
    "zebra-day-admin": "ADMIN",
    "zebra-day-operator": "OPERATOR",
}
DEFAULT_ALLOWED_EMAIL_DOMAINS = [
    "lsmc.com",
    "lsmc.bio",
    "lsmc.life",
    "daylilyinformatics.com",
]
ZERO_TENANT_ID = "00000000-0000-0000-0000-000000000000"
_DEFAULT_SESSION_SECRET_KEY = os.environ.get("ZEBRA_DAY_SESSION_SECRET") or secrets.token_urlsafe(64)


def _normalize_string_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [str(value).strip()]


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    content = yaml.safe_load(path.read_text()) or {}
    return content if isinstance(content, dict) else {}


def _stable_deployment_color_hex(name: str) -> str:
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    hue = int.from_bytes(digest[:8], "big") % 360
    red, green, blue = colorsys.hls_to_rgb(hue / 360.0, 0.46, 0.72)
    return f"#{round(red * 255):02x}{round(green * 255):02x}{round(blue * 255):02x}"


def _resolve_deployment_chrome(
    *,
    name: str | None,
    color: str | None,
    fallback_name: str | None = None,
) -> dict[str, object]:
    resolved_name = str(name or "").strip() or str(fallback_name or "").strip()
    resolved_color = str(color or "").strip()
    if not resolved_color:
        resolved_color = (
            _stable_deployment_color_hex(resolved_name)
            if resolved_name
            else DEFAULT_DEPLOYMENT_BANNER_COLOR
        )
    return {
        "name": resolved_name,
        "color": resolved_color,
        "is_production": resolved_name.lower() in PRODUCTION_DEPLOYMENT_NAMES,
    }


def build_default_config_template(deployment: str | None = None) -> bytes:
    """Build the repo's canonical deployment config template."""
    deployment_code = xdg.sanitize_deployment_code(deployment or xdg.get_deployment_code())
    payload = {
        "service": {
            "deployment_code": deployment_code,
            "host": DEFAULT_HOST,
            "port": DEFAULT_PORT,
            "css_theme": "lsmc.css",
        },
        "authentication": {
            "mode": DEFAULT_AUTH_MODE,
            "internal_api_key_env": "INTERNAL_API_KEY",
            "session_cookie_name": "zebra_day_session",
            "session_secret_key": _DEFAULT_SESSION_SECRET_KEY,
            "callback_path": "/auth/callback",
            "logout_path": "/auth/logout",
            "group_role_map": DEFAULT_COGNITO_GROUP_ROLE_MAP,
            "allowed_email_domains": list(DEFAULT_ALLOWED_EMAIL_DOMAINS),
            "default_tenant_id": ZERO_TENANT_ID,
            "auto_provision_allowed_domains": ["lsmc.com"],
        },
        "tapdb": {
            "client_id": DEFAULT_TAPDB_CLIENT_ID,
            "database_name": f"{DEFAULT_TAPDB_CLIENT_ID}-{deployment_code}",
            "env": "dev",
        },
        "discovery": {
            "default_scan_wait_seconds": 0.5,
            "default_http_port": None,
        },
        "deployment": {
            "name": "",
            "color": "",
            "is_production": False,
        },
    }
    rendered = yaml.safe_dump(payload, sort_keys=False)
    return rendered.encode("utf-8")


def validate_settings_yaml(content: str) -> list[str]:
    """Validate deployment-scoped zebra_day config."""
    try:
        config = yaml.safe_load(content) or {}
    except yaml.YAMLError as exc:
        return [f"YAML parse error: {exc}"]

    if not isinstance(config, dict):
        return ["Root YAML object must be a mapping"]

    errors: list[str] = []
    for section in ("service", "authentication", "tapdb"):
        value = config.get(section)
        if not isinstance(value, dict):
            errors.append(f"Missing or invalid required section: '{section}'")

    auth = config.get("authentication") or {}
    if isinstance(auth, dict):
        mode = str(auth.get("mode") or "").strip().lower()
        if mode not in {"none", "cognito"}:
            errors.append("authentication.mode must be 'none' or 'cognito'")
        group_role_map = auth.get("group_role_map") or {}
        if not isinstance(group_role_map, dict):
            errors.append("authentication.group_role_map must be a mapping")
        elif normalize_group_role_map(group_role_map) != {
            str(key).strip(): str(value).strip().upper()
            for key, value in group_role_map.items()
            if str(key).strip()
        }:
            errors.append("authentication.group_role_map values must be OPERATOR or ADMIN")
        if not str(auth.get("session_secret_key") or "").strip():
            errors.append("authentication.session_secret_key is required")
        if not _normalize_string_list(auth.get("allowed_email_domains")):
            errors.append("authentication.allowed_email_domains must contain at least one domain")
        if not str(auth.get("default_tenant_id") or "").strip():
            errors.append("authentication.default_tenant_id is required")
        if not _normalize_string_list(auth.get("auto_provision_allowed_domains")):
            errors.append(
                "authentication.auto_provision_allowed_domains must contain at least one domain"
            )

    tapdb = config.get("tapdb") or {}
    if isinstance(tapdb, dict):
        if not str(tapdb.get("client_id") or "").strip():
            errors.append("tapdb.client_id is required")
        if not str(tapdb.get("database_name") or "").strip():
            errors.append("tapdb.database_name is required")

    return errors


@dataclass(frozen=True)
class ZebraDaySettings:
    """Resolved runtime settings."""

    deployment_code: str
    deployment_name: str
    deployment_color: str
    deployment_is_production: bool
    config_path: Path
    config_dir: Path
    data_dir: Path
    state_dir: Path
    cache_dir: Path
    logs_dir: Path
    host: str
    port: int
    css_theme: str
    auth_mode: str
    internal_api_key: str
    session_secret_key: str
    session_cookie_name: str
    allowed_email_domains: list[str]
    cognito_default_tenant_id: str
    cognito_auto_provision_allowed_domains: list[str]
    tapdb_client_id: str
    tapdb_database_name: str
    tapdb_env: str
    tapdb_config_path: Path
    callback_path: str
    logout_path: str
    cognito_group_role_map: dict[str, str]
    default_scan_wait_seconds: float
    default_http_port: int | None

    @property
    def deployment(self) -> dict[str, object]:
        return {
            "name": self.deployment_name,
            "color": self.deployment_color,
            "is_production": self.deployment_is_production,
        }

    @classmethod
    def from_context(cls, deployment: str | None = None) -> ZebraDaySettings:
        deployment_code = xdg.sanitize_deployment_code(deployment or xdg.get_deployment_code())
        config_path = Path(os.environ.get("ZEBRA_DAY_CONFIG_PATH") or xdg.get_config_file_path())
        merged = yaml.safe_load(build_default_config_template(deployment_code)) or {}
        file_payload = _load_yaml(config_path)

        for section in ("service", "authentication", "tapdb", "discovery", "deployment"):
            file_section = file_payload.get(section)
            if isinstance(file_section, dict):
                merged.setdefault(section, {})
                merged[section].update(file_section)

        service = merged.get("service") or {}
        auth = merged.get("authentication") or {}
        tapdb = merged.get("tapdb") or {}
        discovery = merged.get("discovery") or {}
        deployment_chrome = _resolve_deployment_chrome(
            name=(merged.get("deployment") or {}).get("name")
            if isinstance(merged.get("deployment"), dict)
            else "",
            color=(merged.get("deployment") or {}).get("color")
            if isinstance(merged.get("deployment"), dict)
            else "",
            fallback_name=deployment_code,
        )

        client_id = str(tapdb.get("client_id") or DEFAULT_TAPDB_CLIENT_ID).strip()
        database_name = str(
            tapdb.get("database_name") or f"{DEFAULT_TAPDB_CLIENT_ID}-{deployment_code}"
        ).strip()
        env_name = str(tapdb.get("env") or "dev").strip() or "dev"
        tapdb_config_path = Path(
            tapdb.get("config_path")
            or (Path.home() / ".config" / "tapdb" / client_id / database_name / "tapdb-config.yaml")
        )

        return cls(
            deployment_code=deployment_code,
            deployment_name=str(deployment_chrome["name"]),
            deployment_color=str(deployment_chrome["color"]),
            deployment_is_production=bool(deployment_chrome["is_production"]),
            config_path=config_path,
            config_dir=xdg.get_config_dir(),
            data_dir=xdg.get_data_dir(),
            state_dir=xdg.get_state_dir(),
            cache_dir=xdg.get_cache_dir(),
            logs_dir=xdg.get_logs_dir(),
            host=str(service.get("host") or DEFAULT_HOST),
            port=int(service.get("port") or DEFAULT_PORT),
            css_theme=str(service.get("css_theme") or "lsmc.css"),
            auth_mode=str(
                os.environ.get("ZEBRA_DAY_AUTH_MODE") or auth.get("mode") or DEFAULT_AUTH_MODE
            ).strip(),
            internal_api_key=str(
                os.environ.get(str(auth.get("internal_api_key_env") or "INTERNAL_API_KEY")) or ""
            ).strip(),
            session_secret_key=str(
                auth.get("session_secret_key") or _DEFAULT_SESSION_SECRET_KEY
            ).strip(),
            session_cookie_name=str(auth.get("session_cookie_name") or "zebra_day_session"),
            allowed_email_domains=_normalize_string_list(
                auth.get("allowed_email_domains") or DEFAULT_ALLOWED_EMAIL_DOMAINS
            )
            or list(DEFAULT_ALLOWED_EMAIL_DOMAINS),
            cognito_default_tenant_id=str(auth.get("default_tenant_id") or ZERO_TENANT_ID).strip(),
            cognito_auto_provision_allowed_domains=_normalize_string_list(
                auth.get("auto_provision_allowed_domains") or ["lsmc.com"]
            )
            or ["lsmc.com"],
            tapdb_client_id=client_id,
            tapdb_database_name=database_name,
            tapdb_env=env_name,
            tapdb_config_path=tapdb_config_path,
            callback_path=str(auth.get("callback_path") or "/auth/callback"),
            logout_path=str(auth.get("logout_path") or "/auth/logout"),
            cognito_group_role_map=normalize_group_role_map(
                auth.get("group_role_map") or DEFAULT_COGNITO_GROUP_ROLE_MAP
            )
            or dict(DEFAULT_COGNITO_GROUP_ROLE_MAP),
            default_scan_wait_seconds=float(discovery.get("default_scan_wait_seconds") or 0.5),
            default_http_port=(
                int(discovery["default_http_port"])
                if discovery.get("default_http_port") not in (None, "")
                else None
            ),
        )
