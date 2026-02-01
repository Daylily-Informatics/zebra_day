"""
FastAPI application factory for zebra_day.

This module provides the main FastAPI application for the zebra_day web interface.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from importlib.resources import files

from zebra_day.logging_config import get_logger
from zebra_day import paths as xdg
from zebra_day.web.middleware import RequestLoggingMiddleware, print_rate_limiter

_log = get_logger(__name__)

# Package paths
_PKG_PATH = Path(str(files("zebra_day")))
_STATIC_PATH = _PKG_PATH / "static"
_TEMPLATES_PATH = _PKG_PATH / "templates"


def get_local_ip() -> str:
    """Get the local IP address of this machine."""
    ipcmd = r"""(ip addr show | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1' || ifconfig | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1') 2>/dev/null"""
    result = subprocess.run(ipcmd, shell=True, capture_output=True, text=True)
    lines = result.stdout.strip().split("\n")
    return lines[0] if lines and lines[0] else "127.0.0.1"


def create_app(
    *,
    debug: bool = False,
    css_theme: str = "lsmc.css",
    auth: Optional[Literal["none", "cognito"]] = None,
) -> FastAPI:
    """
    Create and configure the FastAPI application.

    Args:
        debug: Enable debug mode
        css_theme: Default CSS theme file name
        auth: Authentication mode - "none" (public) or "cognito" (AWS Cognito).
              If None, reads from ZEBRA_DAY_AUTH_MODE env var (defaults to "none").

    Returns:
        Configured FastAPI application
    """
    # Get auth mode from parameter or environment variable
    if auth is None:
        auth = os.environ.get("ZEBRA_DAY_AUTH_MODE", "none")  # type: ignore[assignment]

    # Validate auth parameter
    if auth not in ("none", "cognito"):
        raise ValueError(f"Invalid auth mode: {auth!r}. Must be 'none' or 'cognito'.")

    app = FastAPI(
        title="Zebra Day",
        description="Zebra printer fleet management and label printing",
        version="0.5.0",
        debug=debug,
    )

    # Add request logging middleware
    app.add_middleware(RequestLoggingMiddleware)

    # Configure authentication if enabled
    if auth == "cognito":
        from zebra_day.web.auth import CognitoAuthMiddleware, setup_cognito_auth

        cognito_auth = setup_cognito_auth(app)
        app.add_middleware(CognitoAuthMiddleware, cognito_auth=cognito_auth)
        app.state.cognito_auth = cognito_auth
        app.state.auth_mode = "cognito"
        _log.info("Cognito authentication middleware enabled")
    else:
        app.state.auth_mode = "none"
        _log.info("Authentication disabled (auth=none)")

    # Store rate limiter in app state for use in endpoints
    app.state.print_rate_limiter = print_rate_limiter

    # Store app state
    app.state.css_theme = css_theme
    app.state.local_ip = get_local_ip()
    app.state.pkg_path = _PKG_PATH

    # Mount static files
    app.mount("/static", StaticFiles(directory=str(_STATIC_PATH)), name="static")

    # Also mount package directories that need to be served
    files_dir = _PKG_PATH / "files"
    if files_dir.exists():
        app.mount("/files", StaticFiles(directory=str(files_dir)), name="files")

    etc_dir = _PKG_PATH / "etc"
    if etc_dir.exists():
        app.mount("/etc", StaticFiles(directory=str(etc_dir)), name="etc")

    # Setup Jinja2 templates
    templates = Jinja2Templates(directory=str(_TEMPLATES_PATH))
    app.state.templates = templates

    # Register routers
    from zebra_day.web.routers import ui, api

    app.include_router(ui.router)
    app.include_router(api.router, prefix="/api/v1", tags=["api"])

    @app.on_event("startup")
    async def startup_event():
        """Initialize application state on startup."""
        import zebra_day.print_mgr as zdpm

        app.state.zp = zdpm.zpl()
        _log.info(
            "zebra_day web server starting at %s:8118",
            app.state.local_ip,
        )

    @app.get("/healthz")
    async def healthz():
        """Health check endpoint."""
        return {"status": "healthy"}

    @app.get("/readyz")
    async def readyz():
        """Readiness check endpoint."""
        # Check if printer manager is initialized
        if hasattr(app.state, "zp") and app.state.zp is not None:
            return {"status": "ready"}
        return {"status": "not_ready"}, 503

    return app


def run_server(
    host: str = "0.0.0.0",
    port: int = 8118,
    reload: bool = False,
    auth: Literal["none", "cognito"] = "none",
):
    """
    Run the FastAPI server using uvicorn.

    Args:
        host: Host to bind to
        port: Port to listen on
        reload: Enable auto-reload for development
        auth: Authentication mode - "none" (public) or "cognito" (AWS Cognito)
    """
    import uvicorn

    # Store auth mode in environment for factory function
    os.environ["ZEBRA_DAY_AUTH_MODE"] = auth

    uvicorn.run(
        "zebra_day.web.app:create_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
    )

