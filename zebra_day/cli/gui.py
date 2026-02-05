"""GUI server management commands for zebra_day CLI."""

import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console

from zebra_day import paths as xdg

gui_app = typer.Typer(help="Web UI server management commands")
console = Console()

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


def _resolve_ssl_paths(cert: str | None, key: str | None) -> tuple[str | None, str | None, bool]:
    """
    Resolve SSL certificate and key paths.

    Priority:
    1. Explicit --cert/--key arguments
    2. SSL_CERT_PATH/SSL_KEY_PATH environment variables
    3. Default paths in ~/.config/zebra_day/certs/

    Returns:
        Tuple of (cert_path, key_path, use_https)
    """
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
            return cert_path, key_path, True

    return None, None, False


@gui_app.command("start")
def start(
    port: int = typer.Option(8118, "--port", "-p", help="Port to run the server on"),
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind to"),
    auth: str = typer.Option("none", "--auth", "-a", help="Authentication mode: none or cognito"),
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

    By default, HTTPS is enabled if certificates are found in:
    - Explicit --cert/--key arguments
    - SSL_CERT_PATH/SSL_KEY_PATH environment variables
    - ~/.config/zebra_day/certs/server.crt and server.key

    Use --no-https to force HTTP mode.
    """
    _ensure_dirs()

    # Validate auth option
    if auth not in ("none", "cognito"):
        console.print(f"[red]✗[/red] Invalid auth mode: {auth}. Use 'none' or 'cognito'.")
        raise typer.Exit(1)

    # Check if already running
    pid = _get_pid()
    if pid:
        console.print(f"[yellow]⚠[/yellow]  Server already running (PID {pid})")
        console.print(f"   URL: [cyan]http://{host}:{port}[/cyan]")
        return

    # Check auth dependencies if cognito mode
    if auth == "cognito":
        if not _check_auth_dependencies():
            console.print("[red]✗[/red]  Authentication requested but python-jose is not installed")
            console.print('   Install with: [cyan]pip install -e ".[auth]"[/cyan]')
            raise typer.Exit(1)

        # Check required env vars
        missing = []
        if not os.environ.get("COGNITO_USER_POOL_ID"):
            missing.append("COGNITO_USER_POOL_ID")
        if not os.environ.get("COGNITO_APP_CLIENT_ID"):
            missing.append("COGNITO_APP_CLIENT_ID")
        if missing:
            console.print("[red]✗[/red]  Cognito auth enabled but environment variables missing:")
            for var in missing:
                console.print(f"   • {var}")
            raise typer.Exit(1)
        console.print("[green]✓[/green]  Cognito authentication enabled")

    # Resolve SSL paths
    cert_path, key_path, use_https = _resolve_ssl_paths(cert, key)

    if no_https:
        use_https = False
        cert_path = None
        key_path = None

    protocol = "https" if use_https else "http"

    if use_https:
        console.print("[green]✓[/green]  HTTPS enabled")
        console.print(f"   Certificate: [dim]{cert_path}[/dim]")
        console.print(f"   Private key: [dim]{key_path}[/dim]")
    else:
        console.print("[yellow]⚠[/yellow]  Running in HTTP mode (insecure)")
        console.print("   For HTTPS, generate certificates with mkcert:")
        console.print(f"   [dim]mkdir -p {DEFAULT_CERT_DIR}[/dim]")
        console.print(
            f"   [dim]mkcert -cert-file {DEFAULT_CERT_FILE} -key-file {DEFAULT_KEY_FILE} localhost 127.0.0.1 ::1[/dim]"
        )

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
        console.print("[dim]Auto-reload enabled (foreground mode)[/dim]")

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
            console.print("[red]✗[/red]  Server failed to start. Check logs:")
            console.print(f"   [dim]{log_file}[/dim]")
            if log_file.exists():
                content = log_file.read_text().strip()
                if content:
                    console.print("\n[dim]--- Last error ---[/dim]")
                    for line in content.split("\n")[-10:]:
                        console.print(f"   {line}")
            raise typer.Exit(1)

        PID_FILE.write_text(str(proc.pid))
        console.print(f"[green]✓[/green]  Server started (PID {proc.pid})")
        console.print(f"   URL: [cyan]{protocol}://{host}:{port}[/cyan]")
        console.print(f"   Logs: [dim]{log_file}[/dim]")
    else:
        console.print(
            f"[green]✓[/green]  Starting server on [cyan]{protocol}://{host}:{port}[/cyan]"
        )
        console.print("   Press Ctrl+C to stop\n")
        try:
            result = subprocess.run(cmd, cwd=Path.cwd(), env=env)
            if result.returncode != 0:
                raise typer.Exit(result.returncode)
        except KeyboardInterrupt:
            console.print("\n[yellow]⚠[/yellow]  Server stopped")


@gui_app.command("stop")
def stop():
    """Stop the zebra_day web UI server."""
    pid = _get_pid()
    if not pid:
        console.print("[yellow]⚠[/yellow]  No server running")
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
        console.print(f"[green]✓[/green]  Server stopped (was PID {pid})")
    except ProcessLookupError:
        PID_FILE.unlink(missing_ok=True)
        console.print("[yellow]⚠[/yellow]  Server was not running")
    except PermissionError:
        console.print(f"[red]✗[/red]  Permission denied stopping PID {pid}")
        raise typer.Exit(1) from None


@gui_app.command("status")
def status():
    """Check the status of the zebra_day web UI server."""
    pid = _get_pid()
    if pid:
        log_file = _get_latest_log()
        # Check if HTTPS is likely enabled based on cert availability
        _, _, use_https = _resolve_ssl_paths(None, None)
        protocol = "https" if use_https else "http"
        console.print(f"[green]●[/green]  Server is [green]running[/green] (PID {pid})")
        console.print(f"   URL: [cyan]{protocol}://0.0.0.0:8118[/cyan]")
        if log_file:
            console.print(f"   Logs: [dim]{log_file}[/dim]")
    else:
        console.print("[dim]○[/dim]  Server is [dim]not running[/dim]")


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
            console.print("[yellow]⚠[/yellow]  No log files found.")
            return
        console.print(f"[bold]Server log files ({len(log_files)}):[/bold]")
        for lf in log_files[:20]:
            size = lf.stat().st_size
            console.print(f"  {lf.name}  [dim]({size:,} bytes)[/dim]")
        return

    log_file = _get_latest_log()
    if not log_file:
        console.print("[yellow]⚠[/yellow]  No log file found. Start the server first.")
        return

    if follow:
        console.print(f"[dim]Following {log_file.name} (Ctrl+C to stop)[/dim]\n")
        try:
            subprocess.run(["tail", "-f", "-n", str(lines), str(log_file)])
        except KeyboardInterrupt:
            console.print("\n")
    else:
        console.print(f"[dim]Showing last {lines} lines of {log_file.name}[/dim]\n")
        try:
            subprocess.run(["tail", "-n", str(lines), str(log_file)])
        except Exception as e:
            console.print(f"[red]✗[/red]  Error reading log: {e}")


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
