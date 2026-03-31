from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from playwright.sync_api import Page, expect


def perform_login(page: Page, *, base_url: str, email: str, password: str) -> None:
    page.goto(f"{base_url}/auth/login", wait_until="domcontentloaded")
    user_input = page.locator(
        "input[name='username']:visible, input[type='email']:visible"
    ).first
    pass_input = page.locator(
        "input[name='password']:visible, input[type='password']:visible"
    ).first
    submit_btn = page.locator(
        "input[name='signInSubmitButton']:visible, button[type='submit']:visible"
    ).first

    expect(user_input).to_be_visible(timeout=30000)
    user_input.fill(email)
    pass_input.fill(password)
    submit_btn.click()

    try:
        page.wait_for_url(f"{base_url}/**", timeout=60000)
    except Exception as exc:
        if _is_secondary_challenge(page):
            raise AssertionError(
                "Live zebra_day E2E users must not require MFA or verification-code challenges"
            ) from exc
        raise
    assert_authenticated_page(page, base_url=base_url)


def perform_logout(page: Page, *, base_url: str) -> None:
    page.goto(f"{base_url}/auth/logout", wait_until="domcontentloaded")


def assert_authenticated_page(page: Page, *, base_url: str) -> None:
    expect(page.locator("body")).to_be_visible()
    assert page.url.startswith(base_url), f"Expected zebra_day URL, got {page.url}"
    assert "/auth/error" not in page.url


def assert_auth_error_page(page: Page, *, base_url: str, reason: str, title: str) -> None:
    expect(page.locator("[data-testid='auth-error-card']")).to_be_visible(timeout=15000)
    expect(page.locator("[data-testid='auth-error-title']")).to_have_text(title)
    assert page.url.startswith(f"{base_url}/auth/error")
    query_reason = parse_qs(urlparse(page.url).query).get("reason", [""])[0]
    assert query_reason == reason
    body = page.locator("body").inner_text()
    assert "Zebra Day Dashboard" not in body


def expect_cognito_login_page(page: Page) -> None:
    user_input = page.locator(
        "input[name='username']:visible, input[type='email']:visible"
    ).first
    expect(user_input).to_be_visible(timeout=30000)


def _is_secondary_challenge(page: Page) -> bool:
    body = page.locator("body")
    if not body.is_visible():
        return False
    text = body.inner_text().lower()
    return "verification code" in text or "enter code" in text or "mfa" in text
