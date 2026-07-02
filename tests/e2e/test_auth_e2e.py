from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

import pytest

try:
    from playwright.sync_api import expect
except ModuleNotFoundError:
    expect = None

if TYPE_CHECKING:
    from playwright.sync_api import Page

from tests.e2e.auth_helpers import (
    assert_auth_error_page,
    perform_login,
    perform_logout,
)


def _playwright_available() -> bool:
    try:
        return importlib.util.find_spec("pytest_playwright.pytest_playwright") is not None
    except ModuleNotFoundError:
        return False


pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not _playwright_available(),
        reason="pytest-playwright is not installed",
    ),
]


def test_anonymous_root_redirects_into_cognito_login(anonymous_page: Page, base_url: str):
    anonymous_page.goto(f"{base_url}/", wait_until="domcontentloaded")
    expect(anonymous_page).to_have_url(f"{base_url}/login?next=/")
    expect(anonymous_page.locator("[data-testid='app-login-link']")).to_be_visible()


def test_standard_user_login_round_trip(
    anonymous_page: Page,
    base_url: str,
    standard_e2e_credentials,
):
    perform_login(
        anonymous_page,
        base_url=base_url,
        email=standard_e2e_credentials.email,
        password=standard_e2e_credentials.password,
    )
    expect(anonymous_page.locator("body")).to_contain_text("Storage:")


def test_admin_user_login_round_trip(
    anonymous_page: Page,
    base_url: str,
    admin_e2e_credentials,
):
    perform_login(
        anonymous_page,
        base_url=base_url,
        email=admin_e2e_credentials.email,
        password=admin_e2e_credentials.password,
    )
    expect(anonymous_page.locator("body")).to_contain_text("Storage:")


def test_standard_user_logout_round_trip(standard_page: Page, base_url: str):
    perform_logout(standard_page, base_url=base_url)
    current_url = standard_page.url
    assert current_url.startswith(f"{base_url}/auth/login") or "amazoncognito.com" in current_url, (
        f"Unexpected logout landing URL: {current_url}"
    )
    standard_page.goto(f"{base_url}/printers", wait_until="domcontentloaded")
    current_url = standard_page.url
    assert current_url.startswith(f"{base_url}/auth/login") or "amazoncognito.com" in current_url, (
        f"Unexpected protected-route logout URL: {current_url}"
    )


def test_admin_user_logout_round_trip(admin_page: Page, base_url: str):
    perform_logout(admin_page, base_url=base_url)
    current_url = admin_page.url
    assert current_url.startswith(f"{base_url}/auth/login") or "amazoncognito.com" in current_url, (
        f"Unexpected logout landing URL: {current_url}"
    )
    admin_page.goto(f"{base_url}/admin", wait_until="domcontentloaded")
    current_url = admin_page.url
    assert current_url.startswith(f"{base_url}/auth/login") or "amazoncognito.com" in current_url, (
        f"Unexpected protected-route logout URL: {current_url}"
    )


def test_token_validation_error_uses_dedicated_error_page(anonymous_page: Page, base_url: str):
    anonymous_page.goto(
        f"{base_url}/auth/error?reason=token_validation_failed",
        wait_until="domcontentloaded",
    )
    assert_auth_error_page(
        anonymous_page,
        base_url=base_url,
        reason="token_validation_failed",
        title="Token validation failed",
    )


def test_tampered_callback_state_renders_state_mismatch(anonymous_page: Page, base_url: str):
    anonymous_page.goto(f"{base_url}/auth/login", wait_until="domcontentloaded")
    login_state = parse_qs(urlparse(anonymous_page.url).query).get("state", [""])[0]
    assert login_state, f"Expected Cognito state in hosted UI URL, got {anonymous_page.url}"
    anonymous_page.goto(
        f"{base_url}/auth/callback?code=invalid-code&state=wrong-{login_state}",
        wait_until="domcontentloaded",
    )
    assert_auth_error_page(
        anonymous_page,
        base_url=base_url,
        reason="state_mismatch",
        title="State mismatch",
    )


def test_missing_callback_state_renders_state_mismatch(anonymous_page: Page, base_url: str):
    anonymous_page.goto(
        f"{base_url}/auth/callback?code=invalid-code",
        wait_until="domcontentloaded",
    )
    assert_auth_error_page(
        anonymous_page,
        base_url=base_url,
        reason="state_mismatch",
        title="State mismatch",
    )


def test_anonymous_local_docs_load_without_auth(anonymous_page: Page, base_url: str):
    response = anonymous_page.goto(f"{base_url}/docs", wait_until="domcontentloaded")
    assert response is not None
    assert response.status == 200
    expect(anonymous_page.locator("body")).to_contain_text("Swagger UI")
