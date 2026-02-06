"""
FastAPI application factory for zebra_day.

This module provides the main FastAPI application for the zebra_day web interface.
"""

from __future__ import annotations

import os
import subprocess
from importlib.resources import files
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from zebra_day import __version__, paths as xdg
from zebra_day.logging_config import get_logger
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
    auth: Literal["none", "cognito"] | None = None,
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
        version=__version__,
        debug=debug,
    )

    # Expose version to templates via app.state
    app.state.version = __version__

    # Add request logging middleware
    app.add_middleware(RequestLoggingMiddleware)

    # Configure authentication if enabled
    if auth == "cognito":
        from zebra_day.web.auth import CognitoAuthMiddleware, setup_cognito_auth

        cognito_auth = setup_cognito_auth(app)
        app.add_middleware(CognitoAuthMiddleware, cognito_auth=cognito_auth)  # type: ignore[arg-type]
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
    # Package files directory (for templates, previews generated in-package)
    pkg_files_dir = _PKG_PATH / "files"
    pkg_files_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/files", StaticFiles(directory=str(pkg_files_dir)), name="files")

    # XDG generated files directory (for PNG downloads from dl_png printer)
    xdg_generated_dir = xdg.get_generated_files_dir()
    app.mount("/generated", StaticFiles(directory=str(xdg_generated_dir)), name="generated")

    etc_dir = _PKG_PATH / "etc"
    if etc_dir.exists():
        app.mount("/etc", StaticFiles(directory=str(etc_dir)), name="etc")

    # Setup Jinja2 templates
    templates = Jinja2Templates(directory=str(_TEMPLATES_PATH))
    app.state.templates = templates

    # Register routers
    from zebra_day.web.routers import api, ui

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


def get_default_cert_paths() -> tuple[Path | None, Path | None]:
    """
    Get default certificate paths from XDG config directory.

    Returns:
        Tuple of (cert_path, key_path) or (None, None) if not found.
    """
    config_dir = xdg.get_config_dir()
    cert_dir = config_dir / "certs"
    cert_file = cert_dir / "server.crt"
    key_file = cert_dir / "server.key"

    if cert_file.exists() and key_file.exists():
        return cert_file, key_file
    return None, None


def run_server(
    host: str = "0.0.0.0",
    port: int = 8118,
    reload: bool = False,
    auth: Literal["none", "cognito"] = "none",
    ssl_certfile: str | None = None,
    ssl_keyfile: str | None = None,
):
    """
    Run the FastAPI server using uvicorn.

    Args:
        host: Host to bind to
        port: Port to listen on
        reload: Enable auto-reload for development
        auth: Authentication mode - "none" (public) or "cognito" (AWS Cognito)
        ssl_certfile: Path to SSL certificate file (PEM format)
        ssl_keyfile: Path to SSL private key file (PEM format)

    By default, HTTPS is enabled. The server will:
    1. Check for explicit ssl_certfile/ssl_keyfile arguments
    2. Check SSL_CERT_PATH and SSL_KEY_PATH environment variables
    3. Check for certificates in ~/.config/zebra_day/certs/
    4. Attempt to auto-generate certificates with mkcert if available
    5. Fall back to HTTP with guidance if certificate setup fails
    """
    import uvicorn
    from zebra_day import mkcert

    # Store auth mode in environment for factory function
    os.environ["ZEBRA_DAY_AUTH_MODE"] = auth

    # Resolve SSL certificate paths
    cert_path = ssl_certfile
    key_path = ssl_keyfile

    # Check environment variables if not provided
    if not cert_path:
        cert_path = os.environ.get("SSL_CERT_PATH")
    if not key_path:
        key_path = os.environ.get("SSL_KEY_PATH")

    # Check default XDG paths if still not found
    if not cert_path or not key_path:
        default_cert, default_key = get_default_cert_paths()
        if default_cert and default_key:
            cert_path = str(default_cert)
            key_path = str(default_key)

    # Validate certificate files exist
    use_ssl = False
    if cert_path and key_path:
        cert_exists = Path(cert_path).exists()
        key_exists = Path(key_path).exists()
        if cert_exists and key_exists:
            use_ssl = True
            _log.info("HTTPS enabled with certificates:")
            _log.info("  Certificate: %s", cert_path)
            _log.info("  Private key: %s", key_path)
        else:
            if not cert_exists:
                _log.warning("SSL certificate not found: %s", cert_path)
            if not key_exists:
                _log.warning("SSL private key not found: %s", key_path)

    # If no valid certificates found, try auto-generation
    if not use_ssl:
        _log.info("No existing certificates found, attempting auto-generation...")
        success, message, cert_file, key_file = mkcert.try_auto_generate_certificates()

        if success and cert_file and key_file:
            cert_path = str(cert_file)
            key_path = str(key_file)
            use_ssl = True
            _log.info("Successfully auto-generated certificates:")
            _log.info("  Certificate: %s", cert_path)
            _log.info("  Private key: %s", key_path)
        else:
            _log.warning("Failed to auto-generate certificates")
            _log.warning("Falling back to HTTP (insecure)")
            for line in message.split("\n"):
                if line.strip():
                    _log.warning("  %s", line.strip())

    # Build uvicorn config
    uvicorn_kwargs: dict[str, str | int | bool | None] = {
        "host": host,
        "port": port,
        "reload": reload,
        "factory": True,
    }

    if use_ssl:
        uvicorn_kwargs["ssl_certfile"] = cert_path
        uvicorn_kwargs["ssl_keyfile"] = key_path
        protocol = "https"
    else:
        protocol = "http"

    _log.info("Starting server at %s://%s:%d", protocol, host, port)

    uvicorn.run("zebra_day.web.app:create_app", **uvicorn_kwargs)  # type: ignore[arg-type]
