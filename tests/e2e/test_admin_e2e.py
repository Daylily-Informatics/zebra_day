from __future__ import annotations

import importlib.util

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.auth_helpers import assert_auth_error_page, assert_authenticated_page

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        importlib.util.find_spec("pytest_playwright.pytest_playwright") is None,
        reason="pytest-playwright is not installed",
    ),
]


def test_standard_user_is_denied_admin_page(standard_page: Page, base_url: str):
    standard_page.goto(f"{base_url}/admin", wait_until="domcontentloaded")
    assert_auth_error_page(
        standard_page,
        base_url=base_url,
        reason="not_authorized",
        title="Admin access required",
    )


def test_admin_user_can_access_admin_console(admin_page: Page, base_url: str):
    response = admin_page.goto(f"{base_url}/admin", wait_until="domcontentloaded")
    assert response is not None
    assert response.status == 200
    assert_authenticated_page(admin_page, base_url=base_url)
    expect(admin_page.locator("[data-testid='admin-console-title']")).to_have_text("Admin Console")
