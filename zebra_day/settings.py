"""Deployment-scoped settings for zebra_day."""

from __future__ import annotations

import colorsys
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from cli_core_yo.runtime import get_context

from zebra_day import paths as xdg
from zebra_day.rbac import normalize_group_role_map

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8118
DEFAULT_SERVICE_NAME = "zebra-day"
DEFAULT_AUTH_MODE = "cognito"
DEFAULT_TAPDB_CLIENT_ID = "zebra-day"
DEFAULT_TAPDB_OWNER_REPO = "zebra-day"
DEFAULT_MERIDIAN_DOMAIN_CODE = "Z"
DEFAULT_TAPDB_LOCAL_DB_PORT = 5544
DEFAULT_TAPDB_LOCAL_UI_PORT = 8118
DEFAULT_DEPLOYMENT_BANNER_COLOR = "#AFEEEE"
PRODUCTION_DEPLOYMENT_NAMES = {"prod", "production"}
DEFAULT_COGNITO_GROUP_ROLE_MAP = {
    "admin": "ADMIN",
    "platform-admin": "ADMIN",
    "lsmc:global-admin": "ADMIN",
    "lsmc:internal-user": "OPERATOR",
    "lsmc:zebra-day:admin": "ADMIN",
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


def _default_session_secret_key() -> str:
    return os.environ.get("ZEBRA_DAY_SESSION_SECRET", "").strip()


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
        raise ValueError(f"Zebra Day config file is required: {path}")
    content = yaml.safe_load(path.read_text())
    if not isinstance(content, dict):
        raise ValueError(f"Zebra Day config root must be a YAML mapping: {path}")
    return content


def _validate_cognito_domain(value: Any) -> str:
    domain = str(value or "").strip()
    if not domain:
        return ""
    if any(marker in domain for marker in ("://", "/", "?", "#", ":")):
        raise ValueError("authentication.cognito_domain must be a bare host without a scheme")
    return domain


def _stable_deployment_color_hex(name: str) -> str:
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    hue = int.from_bytes(digest[:8], "big") % 360
    red, green, blue = colorsys.hls_to_rgb(hue / 360.0, 0.46, 0.72)
    return f"#{round(red * 255):02x}{round(green * 255):02x}{round(blue * 255):02x}"


def _resolve_deployment_chrome(
    *,
    name: str | None,
    color: str | None,
    deployment_code: str | None = None,
) -> dict[str, object]:
    resolved_name = str(name or "").strip() or str(deployment_code or "").strip()
    if not resolved_name:
        raise ValueError("deployment.name is required")
    resolved_color = str(color or "").strip()
    if not resolved_color:
        resolved_color = _stable_deployment_color_hex(resolved_name)
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
            "session_secret_key": _default_session_secret_key(),
            "callback_path": "/auth/callback",
            "logout_path": "/auth/logout",
            "external_broker": {
                "service_id": DEFAULT_SERVICE_NAME,
                "login_url": "",
                "handoff_exchange_url": "",
                "service_token": "",
                "callback_url": "",
                "logout_url": "",
                "ca_bundle": "",
            },
            "cognito_region": "",
            "cognito_user_pool_id": "",
            "cognito_app_client_id": "",
            "cognito_domain": "",
            "group_role_map": DEFAULT_COGNITO_GROUP_ROLE_MAP,
            "allowed_email_domains": list(DEFAULT_ALLOWED_EMAIL_DOMAINS),
            "default_tenant_id": ZERO_TENANT_ID,
            "auto_provision_allowed_domains": ["lsmc.com"],
        },
        "tapdb": {
            "client_id": DEFAULT_TAPDB_CLIENT_ID,
            "owner_repo_name": DEFAULT_TAPDB_OWNER_REPO,
            "domain_code": DEFAULT_MERIDIAN_DOMAIN_CODE,
            "database_name": f"{DEFAULT_TAPDB_CLIENT_ID}-{deployment_code}",
            "schema_name": f"tapdb_zebra_day_{deployment_code.replace('-', '_')}",
            "physical_database": f"tapdb_{deployment_code.replace('-', '_')}",
            "local_db_port": DEFAULT_TAPDB_LOCAL_DB_PORT,
            "local_ui_port": DEFAULT_TAPDB_LOCAL_UI_PORT,
            "config_path": str(
                Path.home()
                / ".config"
                / "tapdb"
                / DEFAULT_TAPDB_CLIENT_ID
                / f"{DEFAULT_TAPDB_CLIENT_ID}-{deployment_code}"
                / "tapdb-config.yaml"
            ),
            "domain_registry_path": "/absolute/path/to/domain_code_registry.json",
            "prefix_ownership_registry_path": "/absolute/path/to/prefix_ownership_registry.json",
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
        "ui": {
            "show_environment_chrome": True,
        },
    }
    rendered = yaml.safe_dump(payload, sort_keys=False)
    return rendered.encode("utf-8")


def validate_settings_yaml(content: str) -> list[str]:
    """Validate deployment-scoped zebra_day config."""
    try:
        config = yaml.safe_load(content)
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
        if mode not in {"none", "cognito", "external_broker"}:
            errors.append("authentication.mode must be 'none', 'cognito', or 'external_broker'")
        broker = auth.get("external_broker") or {}
        if mode == "external_broker":
            if not isinstance(broker, dict):
                errors.append("authentication.external_broker must be a mapping")
            else:
                for key in (
                    "service_id",
                    "login_url",
                    "handoff_exchange_url",
                    "service_token",
                    "logout_url",
                ):
                    if not str(broker.get(key) or "").strip():
                        errors.append(f"authentication.external_broker.{key} is required")
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
        cognito_domain = str(auth.get("cognito_domain") or "").strip()
        if cognito_domain:
            try:
                _validate_cognito_domain(cognito_domain)
            except ValueError as exc:
                errors.append(str(exc))

    tapdb = config.get("tapdb") or {}
    if isinstance(tapdb, dict):
        if not str(tapdb.get("client_id") or "").strip():
            errors.append("tapdb.client_id is required")
        if not str(tapdb.get("owner_repo_name") or "").strip():
            errors.append("tapdb.owner_repo_name is required")
        if not str(tapdb.get("domain_code") or "").strip():
            errors.append("tapdb.domain_code is required")
        if not str(tapdb.get("database_name") or "").strip():
            errors.append("tapdb.database_name is required")
        if not str(tapdb.get("schema_name") or "").strip():
            errors.append("tapdb.schema_name is required")
        if not str(tapdb.get("config_path") or "").strip():
            errors.append("tapdb.config_path is required")
        if not str(tapdb.get("domain_registry_path") or "").strip():
            errors.append("tapdb.domain_registry_path is required")
        if not str(tapdb.get("prefix_ownership_registry_path") or "").strip():
            errors.append("tapdb.prefix_ownership_registry_path is required")

    return errors


@dataclass(frozen=True)
class ZebraDaySettings:
    """Resolved runtime settings."""

    deployment_code: str
    deployment_name: str
    deployment_color: str
    deployment_is_production: bool
    ui_show_environment_chrome: bool
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
    cognito_region: str
    cognito_user_pool_id: str
    cognito_app_client_id: str
    cognito_domain: str
    external_broker_service_id: str
    external_broker_login_url: str
    external_broker_handoff_exchange_url: str
    external_broker_service_token: str
    external_broker_callback_url: str
    external_broker_logout_url: str
    external_broker_ca_bundle: str
    tapdb_client_id: str
    tapdb_owner_repo_name: str
    tapdb_domain_code: str
    tapdb_database_name: str
    tapdb_schema_name: str
    tapdb_physical_database: str
    tapdb_local_db_port: int
    tapdb_local_ui_port: int
    tapdb_config_path: Path
    tapdb_domain_registry_path: Path
    tapdb_prefix_ownership_registry_path: Path
    callback_path: str
    logout_path: str
    cognito_group_role_map: dict[str, str]
    default_scan_wait_seconds: float
    default_http_port: int | None

    def __post_init__(self) -> None:
        ca_bundle = str(self.external_broker_ca_bundle or "").strip()
        if ca_bundle and not Path(ca_bundle).is_file():
            raise ValueError("authentication.external_broker.ca_bundle does not exist")

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
        merged = _load_yaml(config_path)
        for section in ("service", "authentication", "tapdb", "discovery", "deployment", "ui"):
            if not isinstance(merged.get(section), dict):
                raise ValueError(f"Zebra Day config section {section!r} is required")

        service = merged.get("service") or {}
        auth = merged.get("authentication") or {}
        tapdb = merged.get("tapdb") or {}
        discovery = merged.get("discovery") or {}
        ui = merged.get("ui") or {}
        auth_cognito = auth.get("cognito") or {}
        auth_external_broker = auth.get("external_broker") or {}
        deployment_chrome = _resolve_deployment_chrome(
            name=(merged.get("deployment") or {}).get("name")
            if isinstance(merged.get("deployment"), dict)
            else "",
            color=(merged.get("deployment") or {}).get("color")
            if isinstance(merged.get("deployment"), dict)
            else "",
            deployment_code=deployment_code,
        )

        client_id = str(tapdb.get("client_id") or "").strip()
        if not client_id:
            raise ValueError("tapdb.client_id is required")
        owner_repo_name = str(tapdb.get("owner_repo_name") or "").strip()
        if not owner_repo_name:
            raise ValueError("tapdb.owner_repo_name is required")
        domain_code = str(tapdb.get("domain_code") or "").strip()
        if not domain_code:
            raise ValueError("tapdb.domain_code is required")
        database_name = str(tapdb.get("database_name") or "").strip()
        if not database_name:
            raise ValueError("tapdb.database_name is required")
        schema_name = str(tapdb.get("schema_name") or "").strip()
        if not schema_name:
            raise ValueError("tapdb.schema_name is required")
        physical_database = str(tapdb.get("physical_database") or "").strip()
        if not physical_database:
            raise ValueError("tapdb.physical_database is required")
        if tapdb.get("local_db_port") in (None, ""):
            raise ValueError("tapdb.local_db_port is required")
        if tapdb.get("local_ui_port") in (None, ""):
            raise ValueError("tapdb.local_ui_port is required")
        local_db_port = int(str(tapdb["local_db_port"]).strip())
        local_ui_port = int(str(tapdb["local_ui_port"]).strip())
        tapdb_config_value = str(tapdb.get("config_path") or "").strip()
        if not tapdb_config_value:
            raise ValueError("tapdb.config_path is required")
        tapdb_config_path = Path(tapdb_config_value).expanduser()
        tapdb_domain_registry_value = str(tapdb.get("domain_registry_path") or "").strip()
        if not tapdb_domain_registry_value:
            raise ValueError("tapdb.domain_registry_path is required")
        tapdb_prefix_ownership_registry_value = str(
            tapdb.get("prefix_ownership_registry_path") or ""
        ).strip()
        if not tapdb_prefix_ownership_registry_value:
            raise ValueError("tapdb.prefix_ownership_registry_path is required")
        tapdb_domain_registry_path = Path(tapdb_domain_registry_value).expanduser()
        tapdb_prefix_ownership_registry_path = Path(
            tapdb_prefix_ownership_registry_value
        ).expanduser()

        return cls(
            deployment_code=deployment_code,
            deployment_name=str(deployment_chrome["name"]),
            deployment_color=str(deployment_chrome["color"]),
            deployment_is_production=bool(deployment_chrome["is_production"]),
            ui_show_environment_chrome=bool(ui.get("show_environment_chrome", True)),
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
                _runtime_auth_mode_override()
                or os.environ.get("ZEBRA_DAY_AUTH_MODE")
                or auth.get("mode")
                or DEFAULT_AUTH_MODE
            ).strip(),
            internal_api_key=str(
                os.environ.get(str(auth.get("internal_api_key_env") or "INTERNAL_API_KEY")) or ""
            ).strip(),
            session_secret_key=str(auth.get("session_secret_key") or "").strip(),
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
            cognito_region=str(
                os.environ.get("COGNITO_REGION")
                or auth.get("cognito_region")
                or auth_cognito.get("region")
                or ""
            ).strip(),
            cognito_user_pool_id=str(
                os.environ.get("COGNITO_USER_POOL_ID")
                or auth.get("cognito_user_pool_id")
                or auth_cognito.get("user_pool_id")
                or ""
            ).strip(),
            cognito_app_client_id=str(
                os.environ.get("COGNITO_APP_CLIENT_ID")
                or auth.get("cognito_app_client_id")
                or auth_cognito.get("app_client_id")
                or ""
            ).strip(),
            cognito_domain=_validate_cognito_domain(
                os.environ.get("COGNITO_DOMAIN")
                or auth.get("cognito_domain")
                or auth_cognito.get("domain")
                or ""
            ),
            external_broker_service_id=str(
                os.environ.get("LSMC_AUTH_BROKER_SERVICE_ID")
                or os.environ.get("ZEBRA_DAY_EXTERNAL_BROKER_SERVICE_ID")
                or auth_external_broker.get("service_id")
                or DEFAULT_SERVICE_NAME
            ).strip(),
            external_broker_login_url=str(
                os.environ.get("LSMC_AUTH_BROKER_LOGIN_URL")
                or os.environ.get("ZEBRA_DAY_EXTERNAL_BROKER_LOGIN_URL")
                or auth_external_broker.get("login_url")
                or ""
            ).strip(),
            external_broker_handoff_exchange_url=str(
                os.environ.get("LSMC_AUTH_BROKER_HANDOFF_EXCHANGE_URL")
                or os.environ.get("ZEBRA_DAY_EXTERNAL_BROKER_HANDOFF_EXCHANGE_URL")
                or auth_external_broker.get("handoff_exchange_url")
                or ""
            ).strip(),
            external_broker_service_token=str(
                os.environ.get("LSMC_AUTH_BROKER_SERVICE_TOKEN")
                or os.environ.get("ZEBRA_DAY_EXTERNAL_BROKER_SERVICE_TOKEN")
                or auth_external_broker.get("service_token")
                or ""
            ).strip(),
            external_broker_callback_url=str(
                os.environ.get("LSMC_AUTH_BROKER_CALLBACK_URL")
                or os.environ.get("ZEBRA_DAY_EXTERNAL_BROKER_CALLBACK_URL")
                or auth_external_broker.get("callback_url")
                or ""
            ).strip(),
            external_broker_logout_url=str(
                os.environ.get("LSMC_AUTH_BROKER_LOGOUT_URL")
                or os.environ.get("ZEBRA_DAY_EXTERNAL_BROKER_LOGOUT_URL")
                or auth_external_broker.get("logout_url")
                or ""
            ).strip(),
            external_broker_ca_bundle=str(
                os.environ.get("LSMC_AUTH_BROKER_CA_BUNDLE")
                or os.environ.get("ZEBRA_DAY_EXTERNAL_BROKER_CA_BUNDLE")
                or auth_external_broker.get("ca_bundle")
                or ""
            ).strip(),
            tapdb_client_id=client_id,
            tapdb_owner_repo_name=owner_repo_name,
            tapdb_domain_code=domain_code,
            tapdb_database_name=database_name,
            tapdb_schema_name=schema_name,
            tapdb_physical_database=physical_database,
            tapdb_local_db_port=local_db_port,
            tapdb_local_ui_port=local_ui_port,
            tapdb_config_path=tapdb_config_path,
            tapdb_domain_registry_path=tapdb_domain_registry_path,
            tapdb_prefix_ownership_registry_path=tapdb_prefix_ownership_registry_path,
            callback_path=str(auth.get("callback_path") or "/auth/callback"),
            logout_path=str(auth.get("logout_path") or "/auth/logout"),
            cognito_group_role_map=normalize_group_role_map(
                auth.get("group_role_map") or DEFAULT_COGNITO_GROUP_ROLE_MAP
            )
            or dict(DEFAULT_COGNITO_GROUP_ROLE_MAP),
            default_scan_wait_seconds=float(discovery["default_scan_wait_seconds"]),
            default_http_port=(
                int(discovery["default_http_port"])
                if discovery.get("default_http_port") not in (None, "")
                else None
            ),
        )


def _runtime_auth_mode_override() -> str | None:
    try:
        invocation = get_context().invocation
    except Exception:
        return None
    return "none" if bool(invocation.get("no_auth")) else None
