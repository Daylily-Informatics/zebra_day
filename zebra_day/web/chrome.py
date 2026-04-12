"""Shared GUI chrome helpers for zebra_day."""

from __future__ import annotations

import colorsys
import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from zebra_day.settings import ZebraDaySettings


@dataclass(frozen=True)
class GitMetadata:
    branch: str
    tag: str
    commit: str

    @property
    def short_commit(self) -> str:
        return self.commit[:12] if self.commit and self.commit != "unknown" else self.commit

    def model_dump(self) -> dict[str, str]:
        return {
            "branch": self.branch,
            "tag": self.tag,
            "commit": self.commit,
            "short_commit": self.short_commit,
        }


def _stable_color_hex(name: str, *, lightness: float, saturation: float, hue_shift: int = 0) -> str:
    digest = hashlib.sha256(str(name or "").encode("utf-8")).digest()
    hue = (int.from_bytes(digest[:8], "big") + hue_shift) % 360
    red, green, blue = colorsys.hls_to_rgb(hue / 360.0, lightness, saturation)
    return "#%02x%02x%02x" % tuple(round(channel * 255) for channel in (red, green, blue))


def deployment_color(name: str) -> str:
    return _stable_color_hex(name, lightness=0.46, saturation=0.72)


def region_color(name: str) -> str:
    return _stable_color_hex(name, lightness=0.62, saturation=0.45, hue_shift=180)


def resolve_git_metadata(repo_root: Path | None = None) -> GitMetadata:
    root = repo_root or Path(__file__).resolve().parents[2]

    def _git(*args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return ""
        return result.stdout.strip()

    branch = _git("rev-parse", "--abbrev-ref", "HEAD") or "unknown"
    commit = _git("rev-parse", "HEAD") or "unknown"
    tag = _git("describe", "--tags", "--exact-match", "HEAD") or "unreleased"
    return GitMetadata(branch=branch, tag=tag, commit=commit)


def build_chrome_context(settings: ZebraDaySettings) -> dict[str, Any]:
    deployment_name = str(settings.deployment_name or settings.deployment_code or "").strip()
    region_name = str(settings.tapdb_env or settings.deployment_code or "").strip()
    return {
        "show_environment_chrome": bool(getattr(settings, "ui_show_environment_chrome", True)),
        "deployment": {
            "name": deployment_name,
            "label": deployment_name.upper(),
            "color": deployment_color(deployment_name) if deployment_name else "",
            "is_production": bool(settings.deployment_is_production),
        },
        "region": {
            "name": region_name,
            "label": region_name.upper(),
            "color": region_color(region_name) if region_name else "",
        },
    }


def build_effective_config_rows(settings: ZebraDaySettings) -> list[dict[str, str]]:
    deployment_name = str(settings.deployment_name or settings.deployment_code or "").strip()
    region_name = str(settings.tapdb_env or settings.deployment_code or "").strip()
    return [
        {"label": "Active Config Path", "value": str(settings.config_path)},
        {"label": "Deployment Code", "value": settings.deployment_code},
        {"label": "Deployment Name", "value": deployment_name},
        {"label": "Deployment Chrome Color", "value": deployment_color(deployment_name)},
        {"label": "UI Environment Chrome", "value": "enabled" if settings.ui_show_environment_chrome else "disabled"},
        {"label": "Region Label", "value": region_name},
        {"label": "Region Chrome Color", "value": region_color(region_name)},
        {"label": "TapDB Client ID", "value": settings.tapdb_client_id},
        {"label": "TapDB Database Name", "value": settings.tapdb_database_name},
        {"label": "TapDB Environment", "value": settings.tapdb_env},
        {"label": "Auth Mode", "value": settings.auth_mode},
        {"label": "Session Cookie Name", "value": settings.session_cookie_name},
        {
            "label": "Session Secret Key",
            "value": "configured" if settings.session_secret_key else "absent",
        },
        {
            "label": "Internal API Key",
            "value": "configured" if settings.internal_api_key else "absent",
        },
        {
            "label": "Allowed Email Domains",
            "value": ", ".join(settings.allowed_email_domains),
        },
        {
            "label": "Default Tenant ID",
            "value": settings.cognito_default_tenant_id,
        },
        {
            "label": "Auto Provision Domains",
            "value": ", ".join(settings.cognito_auto_provision_allowed_domains),
        },
        {"label": "Callback Path", "value": settings.callback_path},
        {"label": "Logout Path", "value": settings.logout_path},
    ]
