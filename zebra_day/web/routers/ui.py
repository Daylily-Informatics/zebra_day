"""HTML UI router for the TapDB-backed zebra_day web interface."""

from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from zebra_day.rbac import ADMIN_ALLOWED_ROLES, has_any_role
from zebra_day.web.chrome import build_effective_config_rows

router = APIRouter()


def get_modern_context(request: Request, active_page: str = "", **kwargs) -> dict[str, Any]:
    """Build common context for modern templates."""
    user = getattr(request.state, "user", {}) or {}
    settings = request.app.state.settings
    chrome = getattr(request.app.state, "chrome_context", {})
    git_metadata = getattr(request.app.state, "git_metadata", {})
    return {
        "request": request,
        "active_page": active_page,
        "api_base": "/api/v1",
        "local_ip": request.app.state.local_ip,
        "version": getattr(request.app.state, "version", "unknown"),
        "git_metadata": git_metadata,
        "cache_bust": str(int(time.time())),
        "auth_mode": settings.auth_mode,
        "auth_enabled": settings.auth_mode != "none",
        "is_authenticated": bool(user),
        "user_name": str(user.get("name") or user.get("email") or user.get("sub") or ""),
        "user_roles": list(user.get("roles") or []),
        "is_admin": has_any_role(list(user.get("roles") or []), ADMIN_ALLOWED_ROLES),
        "service_principal": bool(user.get("service_principal", False)),
        "storage_mode": "tapdb",
        "tapdb_namespace": settings.tapdb_database_name,
        "deployment_code": settings.deployment_code,
        "deployment": chrome.get("deployment", settings.deployment),
        "environment_chrome": chrome.get("region", {}),
        "show_environment_chrome": bool(chrome.get("show_environment_chrome", True)),
        **kwargs,
    }


def _templates(request: Request):
    return request.app.state.templates


def _client(request: Request):
    return request.app.state.zebra_day


def _labs_dict(request: Request) -> dict[str, Any]:
    client = _client(request)
    payload: dict[str, Any] = {}
    for lab in client.list_labs():
        printers = {
            printer.printer_id: printer.to_payload() for printer in client.list_printers(lab)
        }
        payload[lab] = {
            "lab_display_name": lab.replace("-", " ").title(),
            "printers": printers,
        }
    return payload


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    client = _client(request)
    labs = client.list_labs()
    printer_count = len(client.list_printers())
    template_count = len(client.list_templates())
    stats = {
        "total_labs": len(labs),
        "total_printers": printer_count,
        "online_printers": 0,
        "total_templates": template_count,
    }
    context = get_modern_context(
        request,
        active_page="dashboard",
        labs=labs,
        labs_summary=[
            {
                "lab": lab,
                "display_name": lab.replace("-", " ").title(),
                "printer_count": len(client.list_printers(lab)),
            }
            for lab in labs
        ],
        stats=stats,
    )
    return _templates(request).TemplateResponse(request, "modern/dashboard.html", context)


@router.get("/admin", response_class=HTMLResponse)
async def admin(request: Request):
    user = getattr(request.state, "user", {}) or {}
    if not has_any_role(list(user.get("roles") or []), ADMIN_ALLOWED_ROLES):
        return RedirectResponse(url="/auth/error?reason=not_authorized", status_code=302)

    client = _client(request)
    settings = request.app.state.settings
    labs = client.list_labs()
    context = get_modern_context(
        request,
        active_page="admin",
        labs=labs,
        printer_count=len(client.list_printers()),
        template_count=len(client.list_templates()),
        config_rows=build_effective_config_rows(settings),
        auth_summary={
            "mode": settings.auth_mode,
            "enabled": settings.auth_mode != "none",
            "has_internal_api_key": bool(settings.internal_api_key),
        },
        observability_links=[
            "/health",
            "/obs_services",
            "/api_health",
            "/endpoint_health",
            "/db_health",
            "/my_health",
            "/auth_health",
        ],
    )
    return _templates(request).TemplateResponse(request, "modern/admin.html", context)


@router.get("/printers", response_class=HTMLResponse)
async def printers_index(request: Request):
    client = _client(request)
    labs = client.list_labs()
    printers = client.list_printers()
    context = get_modern_context(
        request,
        active_page="printers",
        labs=labs,
        lab="",
        printers=printers,
        scan_wait=request.app.state.settings.default_scan_wait_seconds,
        ip_root=".".join(request.app.state.local_ip.split(".")[:-1]),
    )
    return _templates(request).TemplateResponse(request, "modern/printers.html", context)


@router.get("/printers/{lab}", response_class=HTMLResponse)
async def printers_by_lab(request: Request, lab: str):
    client = _client(request)
    if lab not in client.list_labs():
        raise HTTPException(status_code=404, detail=f"Lab '{lab}' not found")
    context = get_modern_context(
        request,
        active_page="printers",
        labs=client.list_labs(),
        lab=lab,
        lab_display_name=lab.replace("-", " ").title(),
        printers=client.list_printers(lab),
        scan_wait=request.app.state.settings.default_scan_wait_seconds,
        ip_root=".".join(request.app.state.local_ip.split(".")[:-1]),
    )
    return _templates(request).TemplateResponse(request, "modern/printers.html", context)


@router.get("/templates", response_class=HTMLResponse)
async def templates_page(request: Request):
    client = _client(request)
    template_names = client.list_templates()
    context = get_modern_context(
        request,
        active_page="templates",
        template_names=template_names,
        label_profiles=client.list_label_profiles(),
    )
    return _templates(request).TemplateResponse(request, "modern/templates.html", context)


@router.get("/print", response_class=HTMLResponse)
async def print_page(
    request: Request,
    lab: str | None = None,
    printer: str | None = None,
    label_zpl_style: str | None = None,
):
    client = _client(request)
    labs = client.list_labs()
    context = get_modern_context(
        request,
        active_page="print",
        labs=labs,
        labs_dict=json.dumps(_labs_dict(request)),
        selected_lab=lab or "",
        selected_printer=printer or "",
        selected_template=label_zpl_style or "",
        template_names=client.list_templates(),
    )
    return _templates(request).TemplateResponse(request, "modern/print_request.html", context)


@router.get("/config", response_class=HTMLResponse)
async def config_page(request: Request):
    settings = request.app.state.settings
    runtime = _client(request).runtime_summary()
    context = get_modern_context(
        request,
        active_page="config",
        labs=_client(request).list_labs(),
        runtime=runtime,
        config_path=str(settings.config_path),
        tapdb_config_path=str(settings.tapdb_config_path),
        config_rows=build_effective_config_rows(settings),
    )
    return _templates(request).TemplateResponse(request, "modern/config.html", context)
