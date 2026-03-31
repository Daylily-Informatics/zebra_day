"""GUI server management commands for zebra_day."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from cli_core_yo import output

from zebra_day.client import ZebraDayClient
from zebra_day.settings import ZebraDaySettings
from zebra_day.web.auth import load_daycog_contract

if TYPE_CHECKING:
    from cli_core_yo.registry import CommandRegistry
    from cli_core_yo.spec import CliSpec

gui_app = typer.Typer(help="TapDB-backed web GUI management")


def _pid_file(settings: ZebraDaySettings) -> Path:
    return settings.state_dir / "gui.pid"


def _latest_log(settings: ZebraDaySettings) -> Path | None:
    logs = sorted(settings.logs_dir.glob("gui_*.log"), reverse=True)
    return logs[0] if logs else None


def _log_file(settings: ZebraDaySettings) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return settings.logs_dir / f"gui_{timestamp}.log"


def _running_pid(settings: ZebraDaySettings) -> int | None:
    pid_file = _pid_file(settings)
    if not pid_file.exists():
        return None
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
        os.kill(pid, 0)
        return pid
    except (ValueError, ProcessLookupError, PermissionError):
        pid_file.unlink(missing_ok=True)
        return None


def _ensure_runtime_ready(settings: ZebraDaySettings, auth_mode: str) -> None:
    ZebraDayClient(settings)
    if auth_mode == "cognito":
        load_daycog_contract()


def _display_url(host: str, port: int, https_enabled: bool) -> str:
    scheme = "https" if https_enabled else "http"
    display_host = "localhost" if host in {"0.0.0.0", "::", ""} else host
    return f"{scheme}://{display_host}:{port}"


def _resolve_ssl(
    settings: ZebraDaySettings,
    cert: str | None,
    key: str | None,
    no_https: bool,
) -> tuple[str | None, str | None, bool]:
    if no_https:
        return None, None, False

    cert_path = cert or os.environ.get("SSL_CERT_PATH")
    key_path = key or os.environ.get("SSL_KEY_PATH")
    if cert_path and key_path and Path(cert_path).exists() and Path(key_path).exists():
        return cert_path, key_path, True

    cert_dir = settings.config_dir / "certs"
    default_cert = cert_dir / "server.crt"
    default_key = cert_dir / "server.key"
    if default_cert.exists() and default_key.exists():
        return str(default_cert), str(default_key), True

    from zebra_day import mkcert

    success, _message, cert_file, key_file = mkcert.try_auto_generate_certificates()
    if success and cert_file and key_file:
        return str(cert_file), str(key_file), True
    return None, None, False


@gui_app.command("start")
def start(
    port: int = typer.Option(8118, "--port", "-p", help="Port to bind"),
    host: str = typer.Option("localhost", "--host", help="Host to bind"),
    background: bool = typer.Option(
        True,
        "--background/--foreground",
        help="Run in background or foreground",
    ),
    reload: bool = typer.Option(False, "--reload", help="Enable auto reload"),
    auth: str = typer.Option("cognito", "--auth", help="Auth mode: cognito or none"),
    no_auth: bool = typer.Option(False, "--no-auth", help="Disable auth for this server process"),
    cert: str | None = typer.Option(None, "--cert", help="SSL certificate path"),
    key: str | None = typer.Option(None, "--key", help="SSL private key path"),
    no_https: bool = typer.Option(False, "--no-https", help="Disable HTTPS"),
) -> None:
    settings = ZebraDaySettings.from_context()
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    selected_auth = "none" if (no_auth or os.environ.get("ZEBRA_DAY_AUTH_MODE") == "none") else auth
    if selected_auth not in {"none", "cognito"}:
        output.error("auth must be 'cognito' or 'none'")
        raise typer.Exit(1)

    existing_pid = _running_pid(settings)
    if existing_pid:
        output.warning(f"GUI already running (PID {existing_pid})")
        return

    try:
        _ensure_runtime_ready(settings, selected_auth)
    except Exception as exc:
        output.error(str(exc))
        raise typer.Exit(1) from exc

    cert_path, key_path, https_enabled = _resolve_ssl(settings, cert, key, no_https)
    command = [
        sys.executable,
        "-c",
        (
            "from zebra_day.web.app import run_server; "
            f"run_server(host={host!r}, port={port}, reload={reload}, auth={selected_auth!r}, "
            f"ssl_certfile={cert_path!r}, ssl_keyfile={key_path!r})"
        ),
    ]

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["ZEBRA_DAY_AUTH_MODE"] = selected_auth
    env["ZEBRA_DAY_DEPLOYMENT_CODE"] = settings.deployment_code
    if cert_path:
        env["SSL_CERT_PATH"] = cert_path
    if key_path:
        env["SSL_KEY_PATH"] = key_path

    if reload:
        background = False

    if background:
        log_path = _log_file(settings)
        log_handle = open(log_path, "w", encoding="utf-8", buffering=1)
        process = subprocess.Popen(
            command,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            cwd=Path.cwd(),
            env=env,
            start_new_session=True,
        )
        time.sleep(2)
        if process.poll() is not None:
            log_handle.close()
            output.error(f"GUI failed to start. See {log_path}")
            raise typer.Exit(1)
        _pid_file(settings).write_text(str(process.pid), encoding="utf-8")
        output.success(f"GUI started at {_display_url(host, port, https_enabled)}")
        output.detail(f"PID: {process.pid}")
        output.detail(f"Log: {log_path}")
        output.detail(f"Auth: {selected_auth}")
        return

    output.action(f"Starting GUI at {_display_url(host, port, https_enabled)}")
    output.detail(f"Auth: {selected_auth}")
    completed = subprocess.run(command, cwd=Path.cwd(), env=env)
    raise typer.Exit(completed.returncode)


@gui_app.command("stop")
def stop() -> None:
    settings = ZebraDaySettings.from_context()
    pid = _running_pid(settings)
    if pid is None:
        output.warning("GUI is not running")
        return
    os.kill(pid, signal.SIGTERM)
    _pid_file(settings).unlink(missing_ok=True)
    output.success(f"Stopped GUI process {pid}")


@gui_app.command("restart")
def restart(
    port: int = typer.Option(8118, "--port", "-p", help="Port to bind"),
    host: str = typer.Option("localhost", "--host", help="Host to bind"),
    no_auth: bool = typer.Option(False, "--no-auth", help="Disable auth for this server process"),
    no_https: bool = typer.Option(False, "--no-https", help="Disable HTTPS"),
) -> None:
    settings = ZebraDaySettings.from_context()
    if _running_pid(settings):
        stop()
        time.sleep(1)
    start(port=port, host=host, no_auth=no_auth, no_https=no_https)


@gui_app.command("status")
def status() -> None:
    settings = ZebraDaySettings.from_context()
    pid = _running_pid(settings)
    latest_log = _latest_log(settings)
    if pid is None:
        output.warning("GUI is not running")
    else:
        output.success(f"GUI running (PID {pid})")
    output.detail(f"State dir: {settings.state_dir}")
    output.detail(f"Logs dir: {settings.logs_dir}")
    if latest_log is not None:
        output.detail(f"Latest log: {latest_log}")


def register(registry: CommandRegistry, spec: CliSpec) -> None:
    del spec
    registry.add_typer_app(None, gui_app, "gui", "Web GUI management")
