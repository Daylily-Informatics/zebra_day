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
from cli_core_yo import output

from zebra_day.client import ZebraDayClient
from zebra_day.settings import ZebraDaySettings
from zebra_day.web.auth import load_daycog_contract

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
        legacy_cert_env_vars: tuple[str, ...],
        legacy_key_env_vars: tuple[str, ...],
        shared_certs_dir: Path,
        fallback_certs_dir: Path,
    ) -> _ResolvedCerts: ...


class _SharedDayhoffCertsDir(Protocol):
    def __call__(self, deployment_code: str) -> Path: ...


def _load_tls_helpers() -> tuple[_ResolveHttpsCerts, _SharedDayhoffCertsDir]:
    certs_mod: Any | None
    try:
        certs_mod = importlib.import_module("cli_core_yo.certs")
    except ImportError:
        certs_mod = None

    if (
        certs_mod is not None
        and hasattr(certs_mod, "resolve_https_certs")
        and hasattr(certs_mod, "shared_dayhoff_certs_dir")
    ):
        return cast(_ResolveHttpsCerts, certs_mod.resolve_https_certs), cast(
            _SharedDayhoffCertsDir, certs_mod.shared_dayhoff_certs_dir
        )

    sibling_checkout = Path(__file__).resolve().parents[2].parent / "cli-core-yo"
    if sibling_checkout.exists():
        sys.path.insert(0, str(sibling_checkout))
        importlib.invalidate_caches()
        for module_name in ("cli_core_yo.certs", "cli_core_yo"):
            sys.modules.pop(module_name, None)
        certs_mod = importlib.import_module("cli_core_yo.certs")
        if hasattr(certs_mod, "resolve_https_certs") and hasattr(
            certs_mod, "shared_dayhoff_certs_dir"
        ):
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
        load_daycog_contract()


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
        legacy_cert_env_vars=("SSL_CERT_PATH",),
        legacy_key_env_vars=("SSL_KEY_PATH",),
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
    no_auth: bool = typer.Option(False, "--no-auth", help="Disable auth for this server process"),
    ssl: bool = typer.Option(True, "--ssl/--no-ssl", help="Serve over HTTPS"),
    no_https: bool = typer.Option(False, "--no-https", help="Deprecated alias for --no-ssl"),
    cert: str | None = typer.Option(None, "--cert", help="SSL certificate path"),
    key: str | None = typer.Option(None, "--key", help="SSL private key path"),
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
    if cert_path:
        env["SSL_CERT_FILE"] = cert_path
        env["SSL_CERT_PATH"] = cert_path
    if key_path:
        env["SSL_KEY_FILE"] = key_path
        env["SSL_KEY_PATH"] = key_path

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
    _write_runtime_meta(settings=settings, ssl_enabled=https_enabled, host=host, port=port)
    try:
        completed = subprocess.run(command, cwd=Path.cwd(), env=env)
        raise typer.Exit(completed.returncode)
    finally:
        _clear_runtime_meta(settings)


@gui_app.command("stop")
def stop() -> None:
    settings = ZebraDaySettings.from_context()
    pid = _running_pid(settings)
    if pid is None:
        output.warning("GUI is not running")
        return
    os.kill(pid, signal.SIGTERM)
    _pid_file(settings).unlink(missing_ok=True)
    _clear_runtime_meta(settings)
    output.success(f"Stopped GUI process {pid}")


@gui_app.command("restart")
def restart(
    port: int = typer.Option(8118, "--port", "-p", help="Port to bind"),
    host: str = typer.Option("localhost", "--host", help="Host to bind"),
    no_auth: bool = typer.Option(False, "--no-auth", help="Disable auth for this server process"),
    ssl: bool = typer.Option(True, "--ssl/--no-ssl", help="Serve over HTTPS"),
    no_https: bool = typer.Option(False, "--no-https", help="Disable HTTPS"),
) -> None:
    settings = ZebraDaySettings.from_context()
    if _running_pid(settings):
        stop()
        time.sleep(1)
    start(port=port, host=host, no_auth=no_auth, ssl=ssl, no_https=no_https)


@gui_app.command("status")
def status() -> None:
    settings = ZebraDaySettings.from_context()
    pid = _running_pid(settings)
    latest_log = _latest_log(settings)
    if pid is None:
        output.warning("GUI is not running")
    else:
        meta = _read_runtime_meta(settings)
        scheme = "http" if str(meta.get("ssl_enabled")).lower() in {"false", "0", "no"} else "https"
        bound_host = str(meta.get("host") or settings.host)
        raw_port = meta.get("port")
        bound_port = raw_port if isinstance(raw_port, int) else int(str(raw_port or settings.port))
        display_host = "localhost" if bound_host in {"0.0.0.0", "::", ""} else bound_host
        output.success(f"GUI running (PID {pid}) on {scheme}://{display_host}:{bound_port}")
    output.detail(f"State dir: {settings.state_dir}")
    output.detail(f"Logs dir: {settings.logs_dir}")
    if latest_log is not None:
        output.detail(f"Latest log: {latest_log}")


def register(registry: CommandRegistry, spec: CliSpec) -> None:
    del spec
    registry.add_typer_app(None, gui_app, "gui", "Web GUI management")
