"""GUI server management commands for zebra_day."""

from __future__ import annotations

import importlib
import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

import typer
from cli_core_yo import ccyo_out

from zebra_day.cli._registry_v2 import (
    REQUIRED,
    REQUIRED_MUTATING,
    REQUIRED_MUTATING_LONG_RUNNING,
    register_group_commands,
)
from zebra_day.client import ZebraDayClient
from zebra_day.settings import ZebraDaySettings
from zebra_day.web.auth import setup_cognito_auth

if TYPE_CHECKING:
    from cli_core_yo.registry import CommandRegistry
    from cli_core_yo.spec import CliSpec

gui_app = typer.Typer(help="TapDB-backed web GUI management")
SERVER_META_FILE = "server-meta.json"


class _ResolvedCerts(Protocol):
    cert_path: Path
    key_path: Path


class _ResolveHttpsCerts(Protocol):
    def __call__(
        self,
        *,
        cert_path: str | None,
        key_path: str | None,
        env: Mapping[str, str],
        shared_certs_dir: Path,
        fallback_certs_dir: Path,
    ) -> _ResolvedCerts: ...


class _SharedDayhoffCertsDir(Protocol):
    def __call__(self, deployment_code: str) -> Path: ...


def _load_tls_helpers() -> tuple[_ResolveHttpsCerts, _SharedDayhoffCertsDir]:
    try:
        certs_mod: Any = importlib.import_module("cli_core_yo.certs")
    except ImportError as exc:
        raise ImportError(
            "cli_core_yo.certs.resolve_https_certs/shared_dayhoff_certs_dir are required"
        ) from exc

    if hasattr(certs_mod, "resolve_https_certs") and hasattr(certs_mod, "shared_dayhoff_certs_dir"):
        return cast(_ResolveHttpsCerts, certs_mod.resolve_https_certs), cast(
            _SharedDayhoffCertsDir, certs_mod.shared_dayhoff_certs_dir
        )

    raise ImportError("cli_core_yo.certs.resolve_https_certs/shared_dayhoff_certs_dir are required")


resolve_https_certs, shared_dayhoff_certs_dir = _load_tls_helpers()


def _pid_file(settings: ZebraDaySettings) -> Path:
    return settings.state_dir / "gui.pid"


def _latest_log(settings: ZebraDaySettings) -> Path | None:
    logs = sorted(settings.logs_dir.glob("gui_*.log"), reverse=True)
    return logs[0] if logs else None


def _log_file(settings: ZebraDaySettings) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return settings.logs_dir / f"gui_{timestamp}.log"


def _runtime_meta_file(settings: ZebraDaySettings) -> Path:
    return settings.state_dir / SERVER_META_FILE


def _write_runtime_meta(
    *, settings: ZebraDaySettings, ssl_enabled: bool, host: str, port: int
) -> None:
    _runtime_meta_file(settings).write_text(
        json.dumps({"ssl_enabled": ssl_enabled, "host": host, "port": port}, sort_keys=True),
        encoding="utf-8",
    )


def _read_runtime_meta(settings: ZebraDaySettings) -> dict[str, object]:
    meta_file = _runtime_meta_file(settings)
    if not meta_file.exists():
        return {}
    try:
        payload = json.loads(meta_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _clear_runtime_meta(settings: ZebraDaySettings) -> None:
    _runtime_meta_file(settings).unlink(missing_ok=True)


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
        setup_cognito_auth(None, settings)


def _display_url(host: str, port: int, https_enabled: bool) -> str:
    scheme = "https" if https_enabled else "http"
    display_host = "localhost" if host in {"0.0.0.0", "::", ""} else host
    return f"{scheme}://{display_host}:{port}"


def _resolve_ssl(
    settings: ZebraDaySettings,
    cert: str | None,
    key: str | None,
    ssl_enabled: bool,
) -> tuple[str | None, str | None, bool]:
    if not ssl_enabled:
        if cert or key:
            raise typer.BadParameter("--cert and --key require HTTPS; omit them with --no-ssl")
        return None, None, False

    resolved = resolve_https_certs(
        cert_path=cert,
        key_path=key,
        env=dict(os.environ),
        shared_certs_dir=shared_dayhoff_certs_dir(settings.deployment_code),
        fallback_certs_dir=settings.config_dir / "certs",
    )
    return str(resolved.cert_path), str(resolved.key_path), True


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
    ssl: bool = typer.Option(True, "--ssl/--no-ssl", help="Serve over HTTPS"),
    no_https: bool = typer.Option(
        False,
        "--no-https",
        help="Deprecated alias for --no-ssl",
        hidden=True,
    ),
    cert: str | None = typer.Option(None, "--cert", help="SSL certificate path"),
    key: str | None = typer.Option(None, "--key", help="SSL private key path"),
) -> None:
    """Start the zebra_day web GUI."""
    settings = ZebraDaySettings.from_context()
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    selected_auth = "none" if settings.auth_mode == "none" else auth
    if selected_auth not in {"none", "cognito"}:
        ccyo_out.error("auth must be 'cognito' or 'none'")
        raise typer.Exit(1)

    existing_pid = _running_pid(settings)
    if existing_pid:
        ccyo_out.warning(f"GUI already running (PID {existing_pid})")
        return

    try:
        _ensure_runtime_ready(settings, selected_auth)
    except Exception as exc:
        ccyo_out.error(str(exc))
        raise typer.Exit(1) from exc

    https_enabled = ssl and not no_https
    cert_path, key_path, https_enabled = _resolve_ssl(settings, cert, key, https_enabled)
    command = [
        sys.executable,
        "-c",
        (
            "from zebra_day.web.app import run_server; "
            f"run_server(host={host!r}, port={port}, reload={reload}, auth={selected_auth!r}, "
            f"ssl_enabled={https_enabled!r}, ssl_certfile={cert_path!r}, ssl_keyfile={key_path!r})"
        ),
    ]

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["ZEBRA_DAY_AUTH_MODE"] = selected_auth
    env["ZEBRA_DAY_DEPLOYMENT_CODE"] = settings.deployment_code
    env.pop("SSL_CERT_FILE", None)
    env.pop("SSL_KEY_FILE", None)

    if reload:
        background = False

    if background:
        log_path = _log_file(settings)
        log_handle = open(log_path, "w", encoding="utf-8", buffering=1)
        _write_runtime_meta(settings=settings, ssl_enabled=https_enabled, host=host, port=port)
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
            _clear_runtime_meta(settings)
            ccyo_out.error(f"GUI failed to start. See {log_path}")
            raise typer.Exit(1)
        _pid_file(settings).write_text(str(process.pid), encoding="utf-8")
        ccyo_out.success(f"GUI started at {_display_url(host, port, https_enabled)}")
        ccyo_out.detail(f"PID: {process.pid}")
        ccyo_out.detail(f"Log: {log_path}")
        ccyo_out.detail(f"Auth: {selected_auth}")
        return

    ccyo_out.action(f"Starting GUI at {_display_url(host, port, https_enabled)}")
    ccyo_out.detail(f"Auth: {selected_auth}")
    _write_runtime_meta(settings=settings, ssl_enabled=https_enabled, host=host, port=port)
    try:
        completed = subprocess.run(command, cwd=Path.cwd(), env=env)
        raise typer.Exit(completed.returncode)
    finally:
        _clear_runtime_meta(settings)


@gui_app.command("stop")
def stop() -> None:
    """Stop the zebra_day web GUI."""
    settings = ZebraDaySettings.from_context()
    pid = _running_pid(settings)
    if pid is None:
        ccyo_out.warning("GUI is not running")
        return
    os.kill(pid, signal.SIGTERM)
    _pid_file(settings).unlink(missing_ok=True)
    _clear_runtime_meta(settings)
    ccyo_out.success(f"Stopped GUI process {pid}")


@gui_app.command("restart")
def restart(
    port: int = typer.Option(8118, "--port", "-p", help="Port to bind"),
    host: str = typer.Option("localhost", "--host", help="Host to bind"),
    ssl: bool = typer.Option(True, "--ssl/--no-ssl", help="Serve over HTTPS"),
) -> None:
    """Restart the zebra_day web GUI."""
    settings = ZebraDaySettings.from_context()
    if _running_pid(settings):
        stop()
        time.sleep(1)
    start(port=port, host=host, ssl=ssl)


@gui_app.command("status")
def status() -> None:
    """Show zebra_day GUI process and log status."""
    settings = ZebraDaySettings.from_context()
    pid = _running_pid(settings)
    latest_log = _latest_log(settings)
    if pid is None:
        ccyo_out.warning("GUI is not running")
    else:
        meta = _read_runtime_meta(settings)
        scheme = "http" if str(meta.get("ssl_enabled")).lower() in {"false", "0", "no"} else "https"
        bound_host = str(meta.get("host") or settings.host)
        raw_port = meta.get("port")
        bound_port = raw_port if isinstance(raw_port, int) else int(str(raw_port or settings.port))
        display_host = "localhost" if bound_host in {"0.0.0.0", "::", ""} else bound_host
        ccyo_out.success(f"GUI running (PID {pid}) on {scheme}://{display_host}:{bound_port}")
    ccyo_out.detail(f"State dir: {settings.state_dir}")
    ccyo_out.detail(f"Logs dir: {settings.logs_dir}")
    if latest_log is not None:
        ccyo_out.detail(f"Latest log: {latest_log}")


def register(registry: CommandRegistry, spec: CliSpec) -> None:
    _ = spec
    register_group_commands(
        registry,
        "gui",
        "Web GUI management",
        [
            ("start", start, REQUIRED_MUTATING_LONG_RUNNING),
            ("stop", stop, REQUIRED_MUTATING),
            ("restart", restart, REQUIRED_MUTATING_LONG_RUNNING),
            ("status", status, REQUIRED),
        ],
    )
