"""FastAPI application factory for zebra_day."""

from __future__ import annotations

import os
import subprocess
from contextlib import asynccontextmanager
from importlib.resources import files
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Request
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from zebra_day import __version__
from zebra_day.client import ZebraDayClient
from zebra_day.logging_config import get_logger
from zebra_day.observability import ZebraDayObservability
from zebra_day.settings import ZebraDaySettings
from zebra_day.web.auth import (
    CognitoAuthMiddleware,
    build_user_identity,
    setup_cognito_auth,
    setup_session_auth,
)
from zebra_day.web.middleware import RequestLoggingMiddleware, print_rate_limiter

_log = get_logger(__name__)
_PKG_PATH = Path(str(files("zebra_day")))
_STATIC_PATH = _PKG_PATH / "static"
_TEMPLATES_PATH = _PKG_PATH / "templates"
_STRUCTURED_PATHS = {
    "/health",
    "/obs_services",
    "/api_health",
    "/endpoint_health",
    "/db_health",
    "/my_health",
    "/auth_health",
}
_AUTH_ERROR_REASONS: dict[str, tuple[str, str, int]] = {
    "auth_failed": (
        "Authentication failed",
        "The sign-in attempt did not complete. Start a new login flow and try again.",
        401,
    ),
    "auth_error": (
        "Authentication failed",
        "The sign-in attempt did not complete. Start a new login flow and try again.",
        403,
    ),
    "token_validation_failed": (
        "Token validation failed",
        "The Cognito callback completed, but zebra_day could not validate the returned token set.",
        401,
    ),
    "state_mismatch": (
        "State mismatch",
        "The callback state did not match the active browser session. Start the login flow again.",
        401,
    ),
    "not_authorized": (
        "Admin access required",
        "Your account is authenticated, but it does not have the ADMIN role needed for this page.",
        403,
    ),
}


def get_local_ip() -> str:
    """Get the local IP address of this machine."""
    ipcmd = r"""(ip addr show | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1' || ifconfig | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1') 2>/dev/null"""
    result = subprocess.run(ipcmd, shell=True, capture_output=True, text=True)
    lines = result.stdout.strip().split("\n")
    return lines[0] if lines and lines[0] else "127.0.0.1"


def create_app(
    *,
    debug: bool = False,
    css_theme: str | None = None,
    auth: Literal["none", "cognito"] | None = None,
    settings: ZebraDaySettings | None = None,
    client: ZebraDayClient | None = None,
) -> FastAPI:
    """Create the zebra_day FastAPI app."""
    resolved_settings = settings or ZebraDaySettings.from_context()
    if auth is not None:
        resolved_settings = ZebraDaySettings.from_context(resolved_settings.deployment_code)
        object.__setattr__(resolved_settings, "auth_mode", auth)

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        if not hasattr(app.state, "zebra_day") or app.state.zebra_day is None:
            app.state.zebra_day = client or ZebraDayClient(resolved_settings)
        _log.info(
            "zebra_day web server starting at %s:%s",
            app.state.local_ip,
            resolved_settings.port,
        )
        yield

    app = FastAPI(
        title="zebra_day",
        description="TapDB-backed Zebra printer fleet management and label printing",
        version=__version__,
        debug=debug,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=_lifespan,
    )
    app.state.version = __version__
    app.state.settings = resolved_settings
    app.state.css_theme = css_theme or resolved_settings.css_theme
    app.state.local_ip = get_local_ip()
    app.state.pkg_path = _PKG_PATH
    app.state.print_rate_limiter = print_rate_limiter
    app.state.observability = ZebraDayObservability(resolved_settings)

    cognito_binding = None
    if resolved_settings.auth_mode == "cognito":
        cognito_binding = setup_cognito_auth(app, resolved_settings)

    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(
        CognitoAuthMiddleware,
        cognito_auth=cognito_binding,
        settings=resolved_settings,
    )
    setup_session_auth(app, resolved_settings)
    app.state.cognito_auth = cognito_binding

    app.mount("/static", StaticFiles(directory=str(_STATIC_PATH)), name="static")
    generated_dir = resolved_settings.cache_dir / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/generated", StaticFiles(directory=str(generated_dir)), name="generated")
    etc_dir = _PKG_PATH / "etc"
    if etc_dir.exists():
        app.mount("/etc", StaticFiles(directory=str(etc_dir)), name="etc")

    templates = Jinja2Templates(directory=str(_TEMPLATES_PATH))
    app.state.templates = templates

    from zebra_day.web.routers import api, ui

    app.include_router(ui.router)
    app.include_router(api.router, prefix="/api/v1", tags=["api"])

    @app.get("/healthz")
    async def healthz():
        return {"status": "healthy"}

    @app.get("/readyz")
    async def readyz():
        return {
            "status": "ready" if getattr(app.state, "zebra_day", None) is not None else "not_ready"
        }

    @app.get("/health")
    async def health(request: Request):
        return app.state.observability.with_projection(
            request,
            name="health",
            status="ok",
            payload={
                "checks": {
                    "process": {"status": "ok"},
                    "auth": {
                        "status": "ok" if resolved_settings.auth_mode == "cognito" else "disabled",
                        "mode": resolved_settings.auth_mode,
                    },
                }
            },
        )

    @app.get("/obs_services")
    async def obs_services(request: Request):
        endpoints = [
            {"path": "/health", "auth": "operator_or_service_token", "kind": "health"},
            {"path": "/obs_services", "auth": "operator_or_service_token", "kind": "discovery"},
            {"path": "/api_health", "auth": "operator_or_service_token", "kind": "health"},
            {"path": "/endpoint_health", "auth": "operator_or_service_token", "kind": "health"},
            {"path": "/db_health", "auth": "operator_or_service_token", "kind": "database"},
            {"path": "/my_health", "auth": "operator_or_service_token", "kind": "identity"},
            {"path": "/auth_health", "auth": "operator_or_service_token", "kind": "auth"},
        ]
        return app.state.observability.with_projection(
            request,
            name="obs_services",
            status="ok",
            payload={
                "endpoints": endpoints,
                "extensions": [],
                "dependencies": {
                    "configured_services": ["daylily-cognito", "daylily-tapdb"],
                    "observed_services": ["daylily-cognito", "daylily-tapdb"],
                },
            },
        )

    @app.get("/api_health")
    async def api_health(request: Request):
        return app.state.observability.with_projection(
            request,
            name="api_health",
            status="ok",
            payload={"families": [{"name": "api", "status": "ok", "count": 1}]},
        )

    @app.get("/endpoint_health")
    async def endpoint_health(request: Request):
        items = sorted(app.state.observability.route_templates)
        return app.state.observability.with_projection(
            request,
            name="endpoint_health",
            status="ok",
            payload={
                "page": {"total": len(items), "offset": 0, "limit": len(items)},
                "items": [{"path": item, "status": "ok"} for item in items],
            },
        )

    @app.get("/db_health")
    async def db_health(request: Request):
        return app.state.observability.with_projection(
            request,
            name="db_health",
            status="ok",
            payload={
                "database": {
                    "status": "ok",
                    "backend": "tapdb",
                    "env": resolved_settings.tapdb_env,
                    "namespace": {
                        "client_id": resolved_settings.tapdb_client_id,
                        "database_name": resolved_settings.tapdb_database_name,
                    },
                }
            },
        )

    @app.get("/my_health")
    async def my_health(request: Request):
        user = getattr(request.state, "user", {}) or {}
        return app.state.observability.with_projection(
            request,
            name="my_health",
            status="ok",
            payload={
                "principal": {
                    "subject": str(user.get("sub") or ""),
                    "email": str(user.get("email") or ""),
                    "name": str(user.get("name") or ""),
                    "roles": list(user.get("roles") or []),
                    "cognito_groups": list(user.get("cognito_groups") or []),
                    "auth_mode": str(user.get("auth_mode") or resolved_settings.auth_mode),
                    "expires_at": str(user.get("expires_at") or ""),
                    "service_principal": bool(user.get("service_principal", False)),
                }
            },
        )

    @app.get("/auth_health")
    async def auth_health(request: Request):
        binding = getattr(app.state, "cognito_auth", None)
        return app.state.observability.with_projection(
            request,
            name="auth_health",
            status="ok" if resolved_settings.auth_mode == "cognito" else "disabled",
            payload={
                "auth": {
                    "mode": resolved_settings.auth_mode,
                    "cognito_configured": binding is not None,
                    "cognito_domain": str(
                        getattr(getattr(binding, "config", None), "cognito_domain", "") or ""
                    ),
                    "user_pool_id": str(
                        getattr(getattr(binding, "config", None), "user_pool_id", "") or ""
                    ),
                    "app_client_id_present": bool(
                        getattr(getattr(binding, "config", None), "app_client_id", "")
                    ),
                    "sessions": {
                        "supported": True,
                        "active_session_count": 1 if request.session.get("user_data") else 0,
                        "recent_user_count": 1 if request.session.get("user_data") else 0,
                        "observed_at": app.state.observability.base_frame(request, status="ok")[
                            "observed_at"
                        ],
                    },
                }
            },
        )

    @app.get("/auth/login", name="auth_login")
    async def auth_login(request: Request, next: str = "/"):
        if resolved_settings.auth_mode == "none":
            return RedirectResponse(url=next or "/", status_code=302)
        binding = app.state.cognito_auth
        request.session["post_login_redirect"] = next or "/"
        return RedirectResponse(url=binding.build_login_url(request), status_code=302)

    @app.get("/login", name="login_page", response_class=HTMLResponse)
    async def login_page(request: Request, next: str = "/"):
        from zebra_day.web.routers import ui

        context = ui.get_modern_context(
            request,
            active_page="",
            login_next=next or "/",
        )
        return templates.TemplateResponse(request, "modern/login.html", context, status_code=200)

    @app.get("/auth/callback", name="auth_callback")
    async def auth_callback(request: Request, code: str, state: str | None = None):
        expected = str(request.session.get("oauth_state") or "")
        if expected and state and expected != state:
            return RedirectResponse(url="/auth/error?reason=state_mismatch", status_code=302)
        try:
            result = app.state.cognito_auth.exchange_code(request, code)
        except ValueError as exc:
            _log.warning("Cognito callback failed: %s", exc)
            return RedirectResponse(
                url="/auth/error?reason=token_validation_failed", status_code=302
            )
        claims = dict(result.get("claims") or {})
        profile_claims = dict(result.get("profile_claims") or {})
        merged_claims = dict(claims)
        for key, value in profile_claims.items():
            if value not in ("", None, []):
                merged_claims[key] = value
        request.session["user_data"] = build_user_identity(merged_claims, resolved_settings)
        return RedirectResponse(
            url=str(request.session.pop("post_login_redirect", "/")), status_code=302
        )

    @app.get("/auth/logout", name="auth_logout")
    async def auth_logout(request: Request):
        request.session.clear()
        if resolved_settings.auth_mode == "none":
            return RedirectResponse(url="/login", status_code=302)
        return RedirectResponse(
            url=app.state.cognito_auth.build_logout_url(request), status_code=302
        )

    @app.post("/auth/logout", name="auth_logout_post")
    async def auth_logout_post(request: Request):
        return await auth_logout(request)

    @app.get("/auth/error", response_class=HTMLResponse)
    async def auth_error(request: Request, reason: str = "auth_failed"):
        from zebra_day.web.routers import ui

        title, message, status_code = _AUTH_ERROR_REASONS.get(
            reason, _AUTH_ERROR_REASONS["auth_failed"]
        )
        context = ui.get_modern_context(
            request,
            active_page="",
            error_reason=reason,
            error_title=title,
            error_message=message,
            error_status_code=status_code,
        )
        return templates.TemplateResponse(
            request,
            "modern/auth_error.html",
            context,
            status_code=status_code,
        )

    def _openapi_schema() -> dict[str, Any]:
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        if resolved_settings.auth_mode == "cognito":
            schema["paths"] = {
                path: value
                for path, value in schema.get("paths", {}).items()
                if path not in _STRUCTURED_PATHS
            }
        return schema

    @app.get("/openapi.json", include_in_schema=False)
    async def openapi_json():
        return JSONResponse(_openapi_schema())

    @app.get("/docs", include_in_schema=False)
    async def swagger_docs():
        return get_swagger_ui_html(openapi_url="/openapi.json", title="zebra_day Docs")

    @app.get("/api/docs", include_in_schema=False)
    async def swagger_docs_alias():
        return get_swagger_ui_html(openapi_url="/openapi.json", title="zebra_day API Docs")

    @app.get("/redoc", include_in_schema=False)
    async def redoc_docs():
        return get_redoc_html(openapi_url="/openapi.json", title="zebra_day ReDoc")

    @app.get("/api/redoc", include_in_schema=False)
    async def redoc_docs_alias():
        return get_redoc_html(openapi_url="/openapi.json", title="zebra_day API ReDoc")

    return app


def run_server(
    host: str = "0.0.0.0",
    port: int = 8118,
    reload: bool = False,
    auth: Literal["none", "cognito"] = "cognito",
    ssl_enabled: bool = True,
    ssl_certfile: str | None = None,
    ssl_keyfile: str | None = None,
):
    """Run the FastAPI server using uvicorn."""
    import uvicorn

    os.environ["ZEBRA_DAY_AUTH_MODE"] = auth

    uvicorn_kwargs: dict[str, Any] = {
        "host": host,
        "port": port,
        "reload": reload,
        "factory": True,
    }
    if ssl_enabled:
        if not ssl_certfile or not ssl_keyfile:
            raise SystemExit(
                "HTTPS server start requires both ssl_certfile and ssl_keyfile. "
                "Use the GUI command so Zebra Day can resolve them once per deployment."
            )
        cert_path = Path(ssl_certfile)
        key_path = Path(ssl_keyfile)
        if not cert_path.exists() or not key_path.exists():
            raise SystemExit(
                f"HTTPS server start requires existing cert paths: {cert_path} and {key_path}"
            )
        uvicorn_kwargs["ssl_certfile"] = str(cert_path)
        uvicorn_kwargs["ssl_keyfile"] = str(key_path)
    uvicorn.run("zebra_day.web.app:create_app", **uvicorn_kwargs)
