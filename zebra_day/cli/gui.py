"""GUI server management commands for zebra_day CLI."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from cli_core_yo import output

from zebra_day import paths as xdg

if TYPE_CHECKING:
    from cli_core_yo.registry import CommandRegistry
    from cli_core_yo.spec import CliSpec

gui_app = typer.Typer(help="Web UI server management commands")

# PID and log file locations
STATE_DIR = xdg.get_state_dir()
LOG_DIR = xdg.get_logs_dir()
CONFIG_DIR = xdg.get_config_dir()
PID_FILE = STATE_DIR / "gui.pid"
DEFAULT_CERT_DIR = CONFIG_DIR / "certs"
DEFAULT_CERT_FILE = DEFAULT_CERT_DIR / "server.crt"
DEFAULT_KEY_FILE = DEFAULT_CERT_DIR / "server.key"


def _ensure_dirs():
    """Ensure state and log directories exist."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _get_log_file() -> Path:
    """Get timestamped log file path."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return LOG_DIR / f"gui_{ts}.log"


def _get_latest_log() -> Path | None:
    """Get the most recent log file."""
    logs = sorted(LOG_DIR.glob("gui_*.log"), reverse=True)
    return logs[0] if logs else None


def _get_pid() -> int | None:
    """Get the running server PID if exists."""
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            os.kill(pid, 0)
            return pid
        except (ValueError, ProcessLookupError, PermissionError):
            PID_FILE.unlink(missing_ok=True)
    return None


def _check_auth_dependencies() -> bool:
    """Check if auth dependencies are available."""
    try:
        import jose  # noqa: F401

        return True
    except ImportError:
        return False


def _resolve_ssl_paths(
    cert: str | None, key: str | None, no_https: bool = False
) -> tuple[str | None, str | None, bool, str]:
    """
    Resolve SSL certificate and key paths with automatic generation.

    Priority:
    1. Explicit --cert/--key arguments
    2. SSL_CERT_PATH/SSL_KEY_PATH environment variables
    3. Default paths in ~/.config/zebra_day/certs/
    4. Automatic generation with mkcert (if available)

    Args:
        cert: Explicit certificate path
        key: Explicit key path
        no_https: If True, skip all HTTPS setup

    Returns:
        Tuple of (cert_path, key_path, use_https, status_message)
    """
    if no_https:
        return None, None, False, "HTTP mode (--no-https flag)"

    cert_path = cert
    key_path = key

    # Check environment variables
    if not cert_path:
        cert_path = os.environ.get("SSL_CERT_PATH")
    if not key_path:
        key_path = os.environ.get("SSL_KEY_PATH")

    # Check default paths
    if not cert_path and DEFAULT_CERT_FILE.exists():
        cert_path = str(DEFAULT_CERT_FILE)
    if not key_path and DEFAULT_KEY_FILE.exists():
        key_path = str(DEFAULT_KEY_FILE)

    # Validate both exist
    if cert_path and key_path:
        if Path(cert_path).exists() and Path(key_path).exists():
            return cert_path, key_path, True, "Using existing certificates"

    # Try automatic certificate generation
    from zebra_day import mkcert

    success, message, cert_file, key_file = mkcert.try_auto_generate_certificates()

    if success and cert_file and key_file:
        return str(cert_file), str(key_file), True, message

    # Fall back to HTTP with guidance message
    return None, None, False, message


@gui_app.command("start")
def start(
    port: int = typer.Option(8118, "--port", "-p", help="Port to run the server on"),
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind to"),
    auth: str = typer.Option(
        "cognito",
        "--auth",
        "-a",
        help="Authentication mode: cognito (default) or none",
    ),
    no_auth: bool = typer.Option(
        False,
        "--no-auth",
        help="Disable authentication for backward compatibility",
    ),
    reload: bool = typer.Option(False, "--reload", "-r", help="Enable auto-reload (foreground)"),
    background: bool = typer.Option(
        True, "--background/--foreground", "-b/-f", help="Run in background"
    ),
    cert: str | None = typer.Option(None, "--cert", help="Path to SSL certificate file"),
    key: str | None = typer.Option(None, "--key", help="Path to SSL private key file"),
    no_https: bool = typer.Option(
        False, "--no-https", help="Disable HTTPS even if certificates are available"
    ),
):
    """Start the zebra_day web UI server.

    By default, HTTPS is enabled. The server will:
    1. Look for existing certificates in standard locations
    2. Attempt to auto-generate certificates with mkcert if available
    3. Fall back to HTTP with guidance if certificate setup fails

    Use --no-https to force HTTP mode.
    """
    _ensure_dirs()

    if no_auth:
        auth = "none"

    # Validate auth option
    if auth not in ("none", "cognito"):
        output.error(f"Invalid auth mode: {auth}. Use 'none' or 'cognito'.")
        raise typer.Exit(1)

    # Check if already running
    pid = _get_pid()
    if pid:
        output.warning(f"Server already running (PID {pid})")
        output.detail(f"URL: http://{host}:{port}")
        return

    # Check auth dependencies if cognito mode
    if auth == "cognito":
        if not _check_auth_dependencies():
            output.error("Authentication requested but python-jose is not installed")
            output.detail('Install with: pip install -e ".[auth]"')
            raise typer.Exit(1)

        # Check required env vars
        missing = []
        if not os.environ.get("COGNITO_USER_POOL_ID"):
            missing.append("COGNITO_USER_POOL_ID")
        if not os.environ.get("COGNITO_APP_CLIENT_ID"):
            missing.append("COGNITO_APP_CLIENT_ID")
        if missing:
            output.error("Cognito auth enabled but environment variables missing:")
            for var in missing:
                output.bullet(var)
            raise typer.Exit(1)
        output.detail("Use 'zday cognito status' to verify the active daycog context.")
        output.success("Cognito authentication enabled")

    # Resolve SSL paths with automatic generation
    cert_path, key_path, use_https, status_message = _resolve_ssl_paths(cert, key, no_https)

    protocol = "https" if use_https else "http"

    if use_https:
        output.success("HTTPS enabled")
        output.detail(f"Certificate: {cert_path}")
        output.detail(f"Private key: {key_path}")
        if "auto" in status_message.lower() or "generated" in status_message.lower():
            output.detail(status_message)
    else:
        output.warning("Running in HTTP mode (insecure)")
        # Display the status message which contains guidance
        for line in status_message.split("\n"):
            if line.strip():
                output.detail(line)

    # Build command with SSL parameters
    ssl_args = ""
    if use_https and cert_path and key_path:
        ssl_args = f", ssl_certfile='{cert_path}', ssl_keyfile='{key_path}'"

    cmd = [
        sys.executable,
        "-c",
        f"from zebra_day.web.app import run_server; run_server(host='{host}', port={port}, reload={reload}, auth='{auth}'{ssl_args})",
    ]

    # Set up environment
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["ZEBRA_DAY_AUTH_MODE"] = auth
    if cert_path:
        env["SSL_CERT_PATH"] = cert_path
    if key_path:
        env["SSL_KEY_PATH"] = key_path

    if reload:
        background = False
        output.detail("Auto-reload enabled (foreground mode)")

    if background:
        log_file = _get_log_file()
        log_f = open(log_file, "w", buffering=1)

        proc = subprocess.Popen(
            cmd,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            cwd=Path.cwd(),
            env=env,
        )

        time.sleep(2)
        if proc.poll() is not None:
            log_f.close()
            output.error("Server failed to start. Check logs:")
            output.detail(str(log_file))
            if log_file.exists():
                content = log_file.read_text().strip()
                if content:
                    output.detail("--- Last error ---")
                    for line in content.split("\n")[-10:]:
                        output.detail(line)
            raise typer.Exit(1)

        PID_FILE.write_text(str(proc.pid))
        output.success(f"Server started (PID {proc.pid})")
        output.detail(f"URL: {protocol}://{host}:{port}")
        output.detail(f"Logs: {log_file}")
    else:
        output.success(f"Starting server on {protocol}://{host}:{port}")
        output.detail("Press Ctrl+C to stop")
        try:
            result = subprocess.run(cmd, cwd=Path.cwd(), env=env)
            if result.returncode != 0:
                raise typer.Exit(result.returncode)
        except KeyboardInterrupt:
            output.warning("Server stopped")


@gui_app.command("stop")
def stop():
    """Stop the zebra_day web UI server."""
    pid = _get_pid()
    if not pid:
        output.warning("No server running")
        return

    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(10):
            time.sleep(0.5)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
        else:
            os.kill(pid, signal.SIGKILL)

        PID_FILE.unlink(missing_ok=True)
        output.success(f"Server stopped (was PID {pid})")
    except ProcessLookupError:
        PID_FILE.unlink(missing_ok=True)
        output.warning("Server was not running")
    except PermissionError:
        output.error(f"Permission denied stopping PID {pid}")
        raise typer.Exit(1) from None


@gui_app.command("status")
def status():
    """Check the status of the zebra_day web UI server."""
    pid = _get_pid()
    if pid:
        log_file = _get_latest_log()
        # Check if HTTPS is likely enabled based on cert availability
        _, _, use_https, _ = _resolve_ssl_paths(None, None)
        protocol = "https" if use_https else "http"
        output.success(f"Server is running (PID {pid})")
        output.detail(f"URL: {protocol}://0.0.0.0:8118")
        if log_file:
            output.detail(f"Logs: {log_file}")
    else:
        output.detail("Server is not running")


@gui_app.command("logs")
def logs(
    lines: int = typer.Option(50, "--tail", "-n", help="Number of lines to show"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output"),
    all_logs: bool = typer.Option(False, "--all", "-a", help="List all log files"),
):
    """View zebra_day web UI server logs."""
    if all_logs:
        log_files = sorted(LOG_DIR.glob("gui_*.log"), reverse=True)
        if not log_files:
            output.warning("No log files found.")
            return
        output.heading(f"Server log files ({len(log_files)})")
        for lf in log_files[:20]:
            size = lf.stat().st_size
            output.detail(f"{lf.name}  ({size:,} bytes)")
        return

    log_file = _get_latest_log()
    if not log_file:
        output.warning("No log file found. Start the server first.")
        return

    if follow:
        output.detail(f"Following {log_file.name} (Ctrl+C to stop)")
        try:
            subprocess.run(["tail", "-f", "-n", str(lines), str(log_file)])
        except KeyboardInterrupt:
            output.print_text("")
    else:
        output.detail(f"Showing last {lines} lines of {log_file.name}")
        try:
            subprocess.run(["tail", "-n", str(lines), str(log_file)])
        except Exception as e:
            output.error(f"Error reading log: {e}")


@gui_app.command("restart")
def restart(
    port: int = typer.Option(8118, "--port", "-p", help="Port to run the server on"),
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind to"),
    auth: str = typer.Option("none", "--auth", "-a", help="Authentication mode: none or cognito"),
    cert: str | None = typer.Option(None, "--cert", help="Path to SSL certificate file"),
    key: str | None = typer.Option(None, "--key", help="Path to SSL private key file"),
    no_https: bool = typer.Option(
        False, "--no-https", help="Disable HTTPS even if certificates are available"
    ),
):
    """Restart the zebra_day web UI server."""
    stop()
    time.sleep(1)
    start(
        port=port,
        host=host,
        auth=auth,
        reload=False,
        background=True,
        cert=cert,
        key=key,
        no_https=no_https,
    )


def register(registry: CommandRegistry, spec: CliSpec) -> None:
    """cli-core-yo plugin: register the gui command group."""
    registry.add_typer_app(None, gui_app, "gui", "Web UI server management")
