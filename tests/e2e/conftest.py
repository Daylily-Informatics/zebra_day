from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from tests.e2e.cognito_test_users import ensure_admin_user, ensure_standard_user

if TYPE_CHECKING:
    from playwright.sync_api import Browser

try:
    PLAYWRIGHT_AVAILABLE = (
        importlib.util.find_spec("pytest_playwright.pytest_playwright") is not None
    )
except ModuleNotFoundError:
    PLAYWRIGHT_AVAILABLE = False


def _require_live_e2e_env() -> None:
    missing = [
        name
        for name in ("ZDAY_E2E_COGNITO_REGION", "ZDAY_E2E_COGNITO_USER_POOL_ID")
        if not str(os.getenv(name) or "").strip()
    ]
    if missing:
        pytest.skip(
            "Live zebra_day E2E tests require " + ", ".join(missing) + " to be set",
            allow_module_level=False,
        )


@pytest.fixture(scope="session")
def base_url() -> str:
    return os.getenv("ZDAY_E2E_BASE_URL", "https://localhost:8118").rstrip("/")


@pytest.fixture(scope="session")
def standard_e2e_credentials():
    _require_live_e2e_env()
    return ensure_standard_user()


@pytest.fixture(scope="session")
def admin_e2e_credentials():
    _require_live_e2e_env()
    return ensure_admin_user()


@pytest.fixture(scope="session")
def setup_auth(base_url, standard_e2e_credentials, admin_e2e_credentials):
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("pytest-playwright is not installed", allow_module_level=False)
    env = os.environ.copy()
    env["ZDAY_E2E_BASE_URL"] = base_url
    subprocess.run([sys.executable, "-m", "tests.e2e.auth_setup"], check=True, env=env)
    return {
        "standard": str(Path(".auth") / "standard.json"),
        "admin": str(Path(".auth") / "admin.json"),
    }


@pytest.fixture()
def anonymous_page(browser: Browser, standard_e2e_credentials):
    del standard_e2e_credentials
    context = browser.new_context(ignore_https_errors=True)
    try:
        page = context.new_page()
        yield page
    finally:
        context.close()


@pytest.fixture()
def standard_page(browser: Browser, setup_auth):
    context = browser.new_context(
        ignore_https_errors=True,
        storage_state=setup_auth["standard"],
    )
    try:
        page = context.new_page()
        yield page
    finally:
        context.close()


@pytest.fixture()
def admin_page(browser: Browser, setup_auth):
    context = browser.new_context(
        ignore_https_errors=True,
        storage_state=setup_auth["admin"],
    )
    try:
        page = context.new_page()
        yield page
    finally:
        context.close()
