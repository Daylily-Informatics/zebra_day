"""FastAPI application factory for zebra_day."""

from __future__ import annotations

import os
import subprocess
from contextlib import asynccontextmanager
from importlib.resources import files
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
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
    CognitoWebAuthError,
    clear_session_principal,
    complete_cognito_callback,
    complete_external_broker_callback,
    load_session_principal,
    setup_cognito_auth,
    setup_session_auth,
    start_cognito_login,
    start_external_broker_login,
)
from zebra_day.web.chrome import build_chrome_context, resolve_git_metadata
from zebra_day.web.middleware import RequestLoggingMiddleware, print_rate_limiter
from zebra_day.web.tapdb_surfaces import (
    mount_tapdb_surfaces,
    zebra_day_tapdb_obs_services_fragment,
)

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
    "session_expired": (
        "Session expired",
        "Your browser session is no longer valid. Start the login flow again.",
        401,
    ),
    "not_authorized": (
        "Admin access required",
        "Your account is authenticated, but it does not have the ADMIN role needed for this page.",
        403,
    ),
    "blocked_domain": (
        "Email domain not allowed",
        "This account's email domain is not allowed for Zebra Day access.",
        403,
    ),
}


def _auth_error_reason(reason: str) -> str:
    return {
        "invalid_state": "state_mismatch",
        "token_exchange_failed": "token_validation_failed",
        "missing_code": "auth_failed",
        "session_expired": "session_expired",
    }.get(reason, reason or "auth_failed")


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
    auth: Literal["none", "cognito", "external_broker"] | None = None,
    settings: ZebraDaySettings | None = None,
    client: ZebraDayClient | None = None,
) -> FastAPI:
    """Create the zebra_day FastAPI app."""
    resolved_settings = settings or ZebraDaySettings.from_context()
    if auth is not None:
        resolved_settings = ZebraDaySettings.from_context(resolved_settings.deployment_code)
        object.__setattr__(resolved_settings, "auth_mode", auth)
    chrome_context = build_chrome_context(resolved_settings)
    git_metadata = resolve_git_metadata(Path(__file__).resolve().parents[2]).model_dump()

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
    app.state.chrome_context = chrome_context
    app.state.git_metadata = git_metadata

    cognito_binding = None
    if resolved_settings.auth_mode == "cognito":
        cognito_binding = setup_cognito_auth(app, resolved_settings)

    app.add_middleware(
        CognitoAuthMiddleware,
        cognito_auth=cognito_binding,
        settings=resolved_settings,
    )
    app.add_middleware(RequestLoggingMiddleware)
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
    mount_tapdb_surfaces(app, resolved_settings)

    @app.get("/healthz")
    async def healthz(request: Request):
        return app.state.observability.public_healthz_payload(request)

    @app.get("/readyz")
    async def readyz(request: Request):
        backend_ready = getattr(app.state, "zebra_day", None) is not None
        database_check = {
            "status": "ok" if backend_ready else "error",
            "latency_ms": 0.0,
            "detail": "tapdb client ready" if backend_ready else "tapdb client unavailable",
            "details": {
                "backend": "tapdb",
                "target": "target",
                "namespace": {
                    "client_id": resolved_settings.tapdb_client_id,
                    "database_name": resolved_settings.tapdb_database_name,
                },
            },
        }
        payload = app.state.observability.public_readyz_payload(
            request,
            ready=backend_ready,
            database_check=database_check,
        )
        return JSONResponse(status_code=200 if backend_ready else 503, content=payload)

    @app.get("/health")
    async def health(request: Request):
        auth_mode = resolved_settings.auth_mode
        return app.state.observability.with_projection(
            request,
            name="health",
            status="ok",
            payload={
                "checks": {
                    "process": {
                        "status": "ok",
                        "started_at": app.state.observability.started_at,
                    },
                    "auth": {
                        "status": "ok" if auth_mode == "cognito" else "disabled",
                        "mode": auth_mode,
                        "cognito_configured": auth_mode == "cognito",
                    },
                    "database": {
                        "status": "ok",
                        "backend": "tapdb",
                        "target": "target",
                        "namespace": {
                            "client_id": resolved_settings.tapdb_client_id,
                            "database_name": resolved_settings.tapdb_database_name,
                        },
                    },
                }
            },
        )

    @app.get("/obs_services")
    async def obs_services(request: Request):
        payload = app.state.observability.obs_services_payload(
            auth_mode=resolved_settings.auth_mode
        )
        if getattr(app.state, "tapdb_universal_configured", False):
            fragment = zebra_day_tapdb_obs_services_fragment()
            payload["endpoints"] = [
                *list(payload.get("endpoints") or []),
                *list(fragment.get("endpoints") or []),
            ]
            for key in ("extensions", "capabilities", "external_ref_models"):
                existing = list(payload.get(key) or [])
                for item in fragment.get(key) or []:
                    if item not in existing:
                        existing.append(item)
                if existing:
                    payload[key] = existing
            payload["tapdb_dag_contract_version"] = str(
                fragment.get("contract_version") or ""
            )
        return app.state.observability.with_projection(
            request,
            name="obs_services",
            status="ok",
            payload=payload,
        )

    @app.get("/api_health")
    async def api_health(request: Request):
        projection, families = app.state.observability.api_health_payload()
        payload = app.state.observability.base_frame(request, status="ok")
        payload["families"] = families
        payload["projection"] = projection.model_dump()
        return payload

    @app.get("/endpoint_health")
    async def endpoint_health(request: Request, offset: int = 0, limit: int = 25):
        projection, page = app.state.observability.endpoint_health_payload(
            offset=offset, limit=limit
        )
        payload = app.state.observability.base_frame(request, status="ok")
        payload.update(page)
        payload["projection"] = projection.model_dump()
        return payload

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
                    "target": "target",
                    "namespace": {
                        "client_id": resolved_settings.tapdb_client_id,
                        "database_name": resolved_settings.tapdb_database_name,
                    },
                    "latest": None,
                    "recent": [],
                }
            },
        )

    if resolved_settings.auth_mode != "none":

        @app.get("/my_health")
        async def my_health(request: Request):
            user = getattr(request.state, "user", None)
            if not isinstance(user, dict):
                raise HTTPException(status_code=401, detail="Not authenticated")
            app.state.observability.record_auth_event(
                status="ok",
                mode=resolved_settings.auth_mode,
                detail=request.url.path,
                principal_email=str(user.get("email") or ""),
            )
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
        user = getattr(request.state, "user", None)
        principal_email = ""
        if isinstance(user, dict):
            principal_email = str(user.get("email") or "")
        app.state.observability.record_auth_event(
            status="ok",
            mode=resolved_settings.auth_mode,
            detail=request.url.path,
            principal_email=principal_email,
        )
        projection, auth_payload = app.state.observability.auth_health_payload(
            auth_mode=resolved_settings.auth_mode,
            cognito_domain=str(
                getattr(getattr(binding, "config", None), "cognito_domain", "") or ""
            ),
            user_pool_id=str(getattr(getattr(binding, "config", None), "user_pool_id", "") or ""),
            app_client_id_present=bool(
                getattr(getattr(binding, "config", None), "app_client_id", "")
            ),
            active_session_count=(
                None
                if resolved_settings.auth_mode == "none"
                else 1
                if load_session_principal(request)
                else 0
            ),
        )
        payload = app.state.observability.base_frame(
            request, status=str(auth_payload.pop("status"))
        )
        payload.update(auth_payload)
        payload["projection"] = projection.model_dump()
        return payload

    @app.get("/auth/login", name="auth_login")
    async def auth_login(request: Request, next: str = "/"):
        if resolved_settings.auth_mode == "none":
            return RedirectResponse(url=next or "/", status_code=302)
        if resolved_settings.auth_mode == "external_broker":
            try:
                return start_external_broker_login(request, resolved_settings, next or "/")
            except ValueError as exc:
                _log.warning("External broker sign-in is misconfigured: %s", exc)
                return RedirectResponse(url="/auth/error?reason=auth_error", status_code=302)
        return start_cognito_login(request, app.state.web_session_config, next or "/")

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
        if resolved_settings.auth_mode == "none":
            return RedirectResponse(url="/", status_code=302)
        try:
            return await complete_cognito_callback(
                request,
                app.state.web_session_config,
                code,
                state,
                app.state.cognito_auth.resolve_principal,
            )
        except CognitoWebAuthError as exc:
            _log.warning("Cognito callback failed: %s", exc)
            reason = _auth_error_reason(exc.reason)
            return RedirectResponse(url=f"/auth/error?reason={reason}", status_code=302)
        except ValueError as exc:
            _log.warning("Cognito callback failed: %s", exc)
            return RedirectResponse(
                url="/auth/error?reason=token_validation_failed", status_code=302
            )

    @app.get("/auth/lsmc/callback", name="external_broker_callback")
    async def external_broker_callback(
        request: Request,
        code: str | None = None,
        state: str | None = None,
    ):
        if resolved_settings.auth_mode != "external_broker":
            return RedirectResponse(url="/auth/error?reason=auth_error", status_code=302)
        try:
            return await complete_external_broker_callback(
                request,
                resolved_settings,
                code=code,
                state=state,
            )
        except CognitoWebAuthError as exc:
            _log.warning("External broker callback failed: %s", exc)
            return RedirectResponse(
                url=f"/auth/error?reason={_auth_error_reason(exc.reason)}",
                status_code=302,
            )

    @app.get("/auth/logout", name="auth_logout")
    async def auth_logout(request: Request):
        clear_session_principal(request)
        request.session.clear()
        if resolved_settings.auth_mode == "none":
            return RedirectResponse(url="/login", status_code=302)
        if resolved_settings.auth_mode == "external_broker":
            return RedirectResponse(
                url=resolved_settings.external_broker_logout_url,
                status_code=302,
            )
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
        if resolved_settings.auth_mode in {"cognito", "external_broker"}:
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
