"""Embedded TapDB GUI and DAG surfaces for Zebra Day."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from daylily_tapdb.web import (
    DagV2Limits,
    TapdbHostBridge,
    TapdbHostNavLink,
    create_tapdb_gui_app,
    mount_tapdb_dag_surfaces,
)
from fastapi import FastAPI, HTTPException, Request

from zebra_day.rbac import ADMIN_ALLOWED_ROLES, has_any_role
from zebra_day.settings import ZebraDaySettings


def _request_next_path(request: Request) -> str:
    next_path = request.url.path
    if request.url.query:
        next_path = f"{next_path}?{request.url.query}"
    return next_path


def _login_href(request: Request) -> str:
    next_path = _request_next_path(request)
    return f"/login?next={next_path}"


def _host_user(request: Request) -> dict[str, Any] | None:
    settings = request.app.state.settings
    if settings.auth_mode == "none":
        return {
            "uid": "zebra-day-local-admin",
            "username": "zebra-day-local-admin@localhost",
            "email": "zebra-day-local-admin@localhost",
            "display_name": "Zebra Day Local Admin",
            "role": "admin",
            "is_active": True,
            "require_password_change": False,
        }

    user = getattr(request.state, "user", None)
    if not isinstance(user, dict) or user.get("service_principal"):
        return None
    email = str(user.get("email") or "").strip().lower()
    subject = str(user.get("sub") or email).strip() or email
    role = "admin" if has_any_role(list(user.get("roles") or []), ADMIN_ALLOWED_ROLES) else "user"
    return {
        "uid": subject,
        "username": email or subject,
        "email": email or subject,
        "display_name": str(user.get("name") or email or subject).strip(),
        "role": role,
        "is_active": True,
        "require_password_change": False,
    }


async def require_zebra_day_user(request: Request) -> dict[str, Any]:
    """Require an operator or authenticated service actor for native DAG reads."""

    settings = request.app.state.settings
    if settings.auth_mode == "none":
        return {"username": "zebra-day-local-admin"}
    user = getattr(request.state, "user", None)
    if not isinstance(user, dict):
        raise HTTPException(status_code=401, detail="Authentication required")
    if user.get("dag_read_principal"):
        return {"username": settings.dag_read_actor}
    if user.get("service_principal"):
        raise HTTPException(status_code=403, detail="Dedicated DAG read identity required")
    if request.headers.get("Authorization"):
        raise HTTPException(status_code=403, detail="Dedicated DAG read identity required")
    if not has_any_role(list(user.get("roles") or []), ADMIN_ALLOWED_ROLES):
        raise HTTPException(status_code=403, detail="Operator role required")
    actor = str(user.get("email") or user.get("sub") or "").strip()
    if not actor:
        raise HTTPException(status_code=401, detail="Authenticated actor required")
    return {"username": actor}


def resolve_tapdb_config_path(settings: ZebraDaySettings) -> str:
    raw_path = str(settings.tapdb_config_path or "").strip()
    if not raw_path:
        raise RuntimeError("Zebra Day TapDB surfaces require tapdb.config_path.")
    resolved = Path(raw_path).expanduser()
    if not resolved.is_absolute():
        raise RuntimeError("Zebra Day TapDB surfaces require an absolute tapdb.config_path.")
    return str(resolved)


def build_tapdb_host_bridge(settings: ZebraDaySettings) -> TapdbHostBridge:
    return TapdbHostBridge(
        auth_mode="host_session",
        service_name="zebra-day",
        app_name="Zebra Day",
        shell_title="Zebra Day",
        shell_subtitle="TapDB substrate",
        home_url="/",
        login_url=_login_href,
        logout_url="/auth/logout",
        change_password_url=None,
        resolve_user=_host_user,
        nav_links=(
            TapdbHostNavLink(label="Dashboard", href="/"),
            TapdbHostNavLink(label="Printers", href="/printers"),
            TapdbHostNavLink(label="Templates", href="/templates"),
            TapdbHostNavLink(label="Config", href="/config"),
        ),
        extra_stylesheets=("/static/zebra_modern.css",),
        extra_context=lambda _request: {
            "zebra_day_embedded": True,
            "deployment": settings.deployment_code,
        },
    )


def mount_tapdb_surfaces(app: FastAPI, settings: ZebraDaySettings) -> bool:
    """Mount the common TapDB GUI and root DAG API when explicit config is present."""

    config_path = resolve_tapdb_config_path(settings)
    if not Path(config_path).is_file():
        raise FileNotFoundError(f"TapDB config file is required: {config_path}")

    bridge = build_tapdb_host_bridge(settings)
    app.mount(
        "/tapdb",
        create_tapdb_gui_app(
            config_path=config_path,
            host_bridge=bridge,
        ),
    )
    dag_mount = mount_tapdb_dag_surfaces(
        app,
        config_path=config_path,
        service_id="zebra-day",
        display_name="Zebra Day",
        auth_dependency=require_zebra_day_user,
        limits=DagV2Limits(max_depth=4, max_nodes=250, max_search_page_size=50),
    )
    if not dag_mount.mounted:
        raise RuntimeError(
            f"Zebra Day TapDB DAG v2 mount failed: {dag_mount.reason}: {dag_mount.diagnostic}"
        )
    app.state.tapdb_universal_configured = True
    app.state.tapdb_universal_config_path = config_path
    app.state.tapdb_host_bridge = bridge
    return True
