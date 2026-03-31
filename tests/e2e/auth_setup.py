from __future__ import annotations

import os
import ssl
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

from tests.e2e.auth_helpers import perform_login

AUTH_DIR = Path(".auth")


def _base_url() -> str:
    return os.getenv("ZDAY_E2E_BASE_URL", "https://localhost:8118").rstrip("/")


def _wait_for_server(base_url: str) -> None:
    health_url = f"{base_url}/healthz"
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    request = urllib.request.Request(health_url, method="GET")
    with urllib.request.urlopen(request, timeout=10, context=ctx) as response:
        if response.status != 200:
            raise RuntimeError(f"zebra_day health check failed for {health_url}: {response.status}")


def _save_role_state(*, role: str, email: str, password: str, base_url: str) -> None:
    output_path = AUTH_DIR / f"{role}.json"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()
        try:
            perform_login(page, base_url=base_url, email=email, password=password)
            context.storage_state(path=str(output_path))
        finally:
            context.close()
            browser.close()


def main() -> int:
    base_url = _base_url()
    standard_email = str(os.getenv("ZDAY_E2E_STANDARD_EMAIL") or "").strip()
    standard_password = str(os.getenv("ZDAY_E2E_STANDARD_PASSWORD") or "").strip()
    admin_email = str(os.getenv("ZDAY_E2E_ADMIN_EMAIL") or "").strip()
    admin_password = str(os.getenv("ZDAY_E2E_ADMIN_PASSWORD") or "").strip()
    if not all([standard_email, standard_password, admin_email, admin_password]):
        raise RuntimeError("Missing zebra_day E2E credential environment variables")

    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    _wait_for_server(base_url)
    _save_role_state(
        role="standard",
        email=standard_email,
        password=standard_password,
        base_url=base_url,
    )
    _save_role_state(
        role="admin",
        email=admin_email,
        password=admin_password,
        base_url=base_url,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
