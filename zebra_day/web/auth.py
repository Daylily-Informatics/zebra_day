"""Authentication helpers for the zebra_day web app."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import secrets
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
from typing import Any
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

import httpx
import yaml
from daylily_auth_cognito.browser import session as cognito_session
from daylily_auth_cognito.browser.oauth import build_logout_url
from daylily_auth_cognito.browser.session import (
    CognitoWebAuthError,
    CognitoWebSessionConfig,
    SessionPrincipal,
    clear_session_principal,
    complete_cognito_callback,
    configure_session_middleware,
    load_session_principal,
    start_cognito_login,
)
from daylily_auth_cognito.runtime import jwks
from daylily_auth_cognito.runtime.verifier import CognitoTokenVerifier
from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse, Response

from zebra_day.logging_config import get_logger
from zebra_day.rbac import parse_groups, roles_from_groups
from zebra_day.web.ai_agent_access import (
    AgentTokenError,
    is_ai_agent_token,
    validate_ai_agent_request,
)
from zebra_day.settings import (
    DEFAULT_ALLOWED_EMAIL_DOMAINS,
    ZebraDaySettings,
    _validate_cognito_domain,
)

_log = get_logger(__name__)

__all__ = [
    "CognitoBinding",
    "CognitoWebAuthError",
    "CognitoWebSessionConfig",
    "SessionPrincipal",
    "build_logout_url",
    "build_web_session_config",
    "clear_session_principal",
    "complete_cognito_callback",
    "configure_session_middleware",
    "get_cognito_import_error",
    "get_server_instance_id",
    "is_cognito_available",
    "load_daycog_contract",
    "load_session_principal",
    "setup_cognito_auth",
    "setup_session_auth",
    "start_cognito_login",
]

PUBLIC_PATHS = ["/healthz", "/readyz", "/login"]
EXTERNAL_BROKER_CALLBACK_PATH = "/auth/lsmc/callback"
EXTERNAL_BROKER_STATE_KEY = "zebra_day_external_broker_state"
EXTERNAL_BROKER_NEXT_KEY = "zebra_day_external_broker_next"
AUTH_PATHS = [
    "/auth/login",
    "/auth/callback",
    EXTERNAL_BROKER_CALLBACK_PATH,
    "/auth/logout",
    "/auth/error",
    "/login",
]
STRUCTURED_PATHS = {
    "/health",
    "/obs_services",
    "/api_health",
    "/endpoint_health",
    "/db_health",
    "/my_health",
    "/auth_health",
    "/openapi.json",
    "/docs",
    "/api/docs",
    "/redoc",
    "/api/redoc",
}
LOCAL_DOCS_PATHS = {"/openapi.json", "/docs", "/api/docs", "/redoc", "/api/redoc"}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _validate_runtime_cognito_domain(value: Any) -> str:
    return _validate_cognito_domain(value)


def _email_domain(email: str) -> str:
    _, _, domain = str(email or "").strip().lower().partition("@")
    return domain


def _run_sync(awaitable: Any) -> Any:
    """Run an awaitable from sync code, even when a loop is already active."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)

    result: Future[Any] = Future()

    def _runner() -> None:
        try:
            result.set_result(asyncio.run(awaitable))
        except BaseException as exc:
            result.set_exception(exc)

    thread = Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()
    return result.result()


def build_user_identity(claims: dict[str, Any], settings: ZebraDaySettings) -> dict[str, Any]:
    merged_claims = dict(claims)
    email = _clean(merged_claims.get("email")).lower()
    domain = _email_domain(email)
    allowed_domains = getattr(settings, "allowed_email_domains", DEFAULT_ALLOWED_EMAIL_DOMAINS)
    if not email or domain not in {item.lower() for item in allowed_domains}:
        raise CognitoWebAuthError(
            "blocked_domain",
            "Email domain is not allowed",
            status_code=status.HTTP_403_FORBIDDEN,
            redirect_to_error=True,
        )
    groups = parse_groups(merged_claims.get("cognito:groups"))
    roles = roles_from_groups(groups, settings.cognito_group_role_map)
    merged_claims["cognito_groups"] = groups
    merged_claims["roles"] = roles
    return {
        "sub": _clean(merged_claims.get("sub") or merged_claims.get("username")),
        "email": email,
        "name": _clean(
            merged_claims.get("name")
            or merged_claims.get("cognito:username")
            or merged_claims.get("username")
        ),
        "roles": roles,
        "cognito_groups": groups,
        "auth_mode": "cognito_session",
        "service_principal": False,
    }


def build_external_broker_identity(
    user: dict[str, Any],
    settings: ZebraDaySettings,
) -> dict[str, Any]:
    email = _clean(user.get("email")).lower()
    if not email:
        raise CognitoWebAuthError(
            "auth_error",
            "External broker handoff omitted email",
            status_code=status.HTTP_401_UNAUTHORIZED,
            redirect_to_error=True,
        )
    domain = _email_domain(email)
    allowed_domains = getattr(settings, "allowed_email_domains", DEFAULT_ALLOWED_EMAIL_DOMAINS)
    if domain not in {item.lower() for item in allowed_domains}:
        raise CognitoWebAuthError(
            "blocked_domain",
            "Email domain is not allowed",
            status_code=status.HTTP_403_FORBIDDEN,
            redirect_to_error=True,
        )
    groups = [str(group).strip() for group in user.get("groups") or [] if str(group).strip()]
    service_id = _clean(settings.external_broker_service_id) or "zebra-day"
    roles = {str(role).strip().upper() for role in user.get("roles") or [] if str(role).strip()}
    if "lsmc:global-admin" in groups or f"lsmc:{service_id}:admin" in groups:
        roles.add("ADMIN")
    for entitlement in user.get("service_entitlements") or []:
        if not isinstance(entitlement, dict):
            continue
        if _clean(entitlement.get("service")) != service_id:
            continue
        roles.update(
            str(role).strip().upper()
            for role in entitlement.get("roles") or []
            if str(role).strip()
        )
    if "ADMIN" in roles:
        roles.add("OPERATOR")
    if not roles:
        raise CognitoWebAuthError(
            "not_authorized",
            "External broker user has no Zebra Day role",
            status_code=status.HTTP_403_FORBIDDEN,
            redirect_to_error=True,
        )
    return {
        "sub": _clean(user.get("canonical_user_id") or user.get("sub") or email),
        "email": email,
        "name": _clean(user.get("display_name") or user.get("name") or email),
        "roles": sorted(roles),
        "cognito_groups": groups,
        "auth_mode": "external_broker",
        "service_principal": False,
    }


def is_cognito_available() -> bool:
    try:
        import daylily_auth_cognito  # noqa: F401

        return True
    except ImportError:
        return False


def get_cognito_import_error() -> str | None:
    try:
        import daylily_auth_cognito  # noqa: F401

        return None
    except ImportError as exc:
        return str(exc)


def _daycog_config_path() -> Path:
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    base_dir = Path(xdg_config_home).expanduser() if xdg_config_home else Path.home() / ".config"
    return base_dir / "daycog" / "config.yaml"


def _load_daycog_file_values() -> dict[str, str]:
    path = _daycog_config_path()
    if not path.exists():
        raise RuntimeError(f"daycog config store is required: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"daycog config store must be a YAML mapping: {path}")
    return {str(key): str(value) for key, value in payload.items() if value is not None}


def load_daycog_contract() -> dict[str, str]:
    """Load the process env first, then fill gaps from the daycog config file."""
    values = {key: _clean(os.environ.get(key)) for key in os.environ}
    env_contract = {
        "region": _clean(values.get("COGNITO_REGION") or values.get("AWS_REGION")),
        "user_pool_id": _clean(values.get("COGNITO_USER_POOL_ID")),
        "app_client_id": _clean(values.get("COGNITO_APP_CLIENT_ID")),
        "aws_profile": _clean(values.get("AWS_PROFILE")),
        "cognito_domain": _validate_runtime_cognito_domain(values.get("COGNITO_DOMAIN")),
        "client_name": _clean(values.get("COGNITO_CLIENT_NAME")),
        "callback_url": _clean(
            values.get("COGNITO_CALLBACK_URL")
            or values.get("COGNITO_REDIRECT_URI")
            or values.get("COGNITO_REDIRECT_URL")
        ),
        "logout_url": _clean(values.get("COGNITO_LOGOUT_URL")),
    }
    required = ("region", "user_pool_id", "app_client_id", "cognito_domain")
    if all(env_contract[key] for key in required):
        return env_contract

    file_values = _load_daycog_file_values()
    if not file_values:
        raise ValueError(f"No daycog config file found at {_daycog_config_path()}")

    contract = {
        "region": _clean(
            values.get("COGNITO_REGION")
            or values.get("AWS_REGION")
            or file_values.get("COGNITO_REGION")
            or file_values.get("AWS_REGION")
        ),
        "user_pool_id": _clean(
            values.get("COGNITO_USER_POOL_ID") or file_values.get("COGNITO_USER_POOL_ID")
        ),
        "app_client_id": _clean(
            values.get("COGNITO_APP_CLIENT_ID") or file_values.get("COGNITO_APP_CLIENT_ID")
        ),
        "aws_profile": _clean(values.get("AWS_PROFILE") or file_values.get("AWS_PROFILE")),
        "cognito_domain": _validate_runtime_cognito_domain(
            values.get("COGNITO_DOMAIN") or file_values.get("COGNITO_DOMAIN")
        ),
        "client_name": _clean(
            values.get("COGNITO_CLIENT_NAME") or file_values.get("COGNITO_CLIENT_NAME")
        ),
        "callback_url": _clean(
            values.get("COGNITO_CALLBACK_URL")
            or values.get("COGNITO_REDIRECT_URI")
            or values.get("COGNITO_REDIRECT_URL")
            or file_values.get("COGNITO_CALLBACK_URL")
            or file_values.get("COGNITO_REDIRECT_URI")
            or file_values.get("COGNITO_REDIRECT_URL")
        ),
        "logout_url": _clean(
            values.get("COGNITO_LOGOUT_URL") or file_values.get("COGNITO_LOGOUT_URL")
        ),
    }
    missing = [key for key in required if not contract[key]]
    if missing:
        raise ValueError("daycog config file is missing required values: " + ", ".join(missing))
    return contract


SERVER_INSTANCE_ID = secrets.token_urlsafe(16)
_PUBLIC_BASE_URL_ENV = "ZEBRA_DAY_PUBLIC_BASE_URL"


def get_server_instance_id() -> str:
    """Return the process-scoped server instance identifier."""
    return SERVER_INSTANCE_ID


def _session_secret(settings: ZebraDaySettings) -> str:
    return os.environ.get("ZEBRA_DAY_SESSION_SECRET") or settings.session_secret_key


def _runtime_public_base_url(settings: ZebraDaySettings) -> str:
    configured = _clean(os.environ.get(_PUBLIC_BASE_URL_ENV))
    if configured:
        return configured
    scheme = "https" if settings.auth_mode in {"cognito", "external_broker"} else "http"
    return f"{scheme}://localhost:{settings.port}"


def _origin(value: str) -> str:
    parts = urlsplit(value)
    return f"{parts.scheme}://{parts.netloc}"


def _require_cognito_runtime_settings(settings: ZebraDaySettings) -> SimpleNamespace:
    missing = [
        name
        for name, value in (
            ("COGNITO_REGION", settings.cognito_region),
            ("COGNITO_USER_POOL_ID", settings.cognito_user_pool_id),
            ("COGNITO_APP_CLIENT_ID", settings.cognito_app_client_id),
            ("COGNITO_DOMAIN", settings.cognito_domain),
        )
        if not _clean(value)
    ]
    if missing:
        raise ValueError("Missing zebra_day Cognito runtime settings: " + ", ".join(missing))
    return SimpleNamespace(
        region=settings.cognito_region,
        user_pool_id=settings.cognito_user_pool_id,
        app_client_id=settings.cognito_app_client_id,
        cognito_domain=settings.cognito_domain,
    )


def _require_external_broker_runtime_settings(settings: ZebraDaySettings) -> None:
    missing = [
        name
        for name, value in (
            ("LSMC_AUTH_BROKER_SERVICE_ID", settings.external_broker_service_id),
            ("LSMC_AUTH_BROKER_LOGIN_URL", settings.external_broker_login_url),
            (
                "LSMC_AUTH_BROKER_HANDOFF_EXCHANGE_URL",
                settings.external_broker_handoff_exchange_url,
            ),
            ("LSMC_AUTH_BROKER_SERVICE_TOKEN", settings.external_broker_service_token),
            ("LSMC_AUTH_BROKER_LOGOUT_URL", settings.external_broker_logout_url),
        )
        if not _clean(value)
    ]
    if missing:
        raise ValueError("Missing zebra_day external broker settings: " + ", ".join(missing))


def build_web_session_config(settings: ZebraDaySettings) -> CognitoWebSessionConfig:
    """Build the shared browser-session config for the current runtime."""
    public_base_url = _runtime_public_base_url(settings)
    callback_url = (
        _clean(settings.external_broker_callback_url)
        or f"{public_base_url}{EXTERNAL_BROKER_CALLBACK_PATH}"
        if settings.auth_mode == "external_broker"
        else f"{public_base_url}{settings.callback_path}"
    )
    logout_url = f"{public_base_url}/login"
    if settings.auth_mode == "cognito":
        _require_cognito_runtime_settings(settings)
        domain = settings.cognito_domain
        client_id = settings.cognito_app_client_id
    elif settings.auth_mode == "external_broker":
        _require_external_broker_runtime_settings(settings)
        domain = _required_url_hostname(
            settings.external_broker_login_url,
            field_name="LSMC_AUTH_BROKER_LOGIN_URL",
        )
        client_id = settings.external_broker_service_id
    else:
        domain = _clean(settings.cognito_domain) or "localhost"
        client_id = _clean(settings.cognito_app_client_id) or settings.tapdb_client_id

    return CognitoWebSessionConfig(
        domain=domain,
        client_id=client_id,
        redirect_uri=callback_url,
        logout_uri=logout_url,
        session_secret_key=_session_secret(settings),
        session_cookie_name=settings.session_cookie_name,
        public_base_url=public_base_url,
        server_instance_id=get_server_instance_id(),
        allow_insecure_http=public_base_url.startswith("http://"),
        auth_mode=settings.auth_mode,
    )


def _required_url_hostname(value: str, *, field_name: str) -> str:
    parsed = urlsplit(str(value or "").strip())
    if not parsed.scheme or not parsed.netloc or not parsed.hostname:
        raise ValueError(f"{field_name} must be an absolute URL with host")
    return parsed.hostname


def start_external_broker_login(
    request: Request,
    settings: ZebraDaySettings,
    next_path: str | None,
) -> RedirectResponse:
    _require_external_broker_runtime_settings(settings)
    target = str(next_path or "/").strip() or "/"
    if not target.startswith("/"):
        target = f"/{target}"
    state = secrets.token_urlsafe(32)
    request.session[EXTERNAL_BROKER_STATE_KEY] = state
    request.session[EXTERNAL_BROKER_NEXT_KEY] = target
    callback_url = (
        _clean(settings.external_broker_callback_url)
        or f"{_runtime_public_base_url(settings)}{EXTERNAL_BROKER_CALLBACK_PATH}"
    )
    return RedirectResponse(
        url=f"{settings.external_broker_login_url.rstrip('/')}?"
        + urlencode(
            {
                "service": settings.external_broker_service_id,
                "next": target,
                "callback_url": callback_url,
                "state": state,
            }
        ),
        status_code=302,
    )


async def complete_external_broker_callback(
    request: Request,
    settings: ZebraDaySettings,
    *,
    code: str | None,
    state: str | None,
) -> RedirectResponse:
    if not code:
        raise CognitoWebAuthError("missing_code", "External broker callback omitted code")
    expected_state = _clean(request.session.get(EXTERNAL_BROKER_STATE_KEY))
    if not expected_state or state != expected_state:
        raise CognitoWebAuthError("invalid_state", "External broker state mismatch")
    ca_bundle = _clean(settings.external_broker_ca_bundle)
    verify: bool | str = ca_bundle if ca_bundle else True
    async with httpx.AsyncClient(timeout=10.0, verify=verify) as client:
        response = await client.post(
            settings.external_broker_handoff_exchange_url,
            json={"code": code},
            headers={
                "Authorization": f"Bearer {settings.external_broker_service_token}",
                "X-LSMC-Service-ID": settings.external_broker_service_id,
            },
        )
    if response.status_code >= 400:
        raise CognitoWebAuthError(
            "auth_error",
            f"External broker handoff exchange failed with status {response.status_code}",
            status_code=status.HTTP_401_UNAUTHORIZED,
            redirect_to_error=True,
        )
    payload = response.json()
    user = payload.get("user") if isinstance(payload, dict) else None
    if not isinstance(user, dict):
        raise CognitoWebAuthError("auth_error", "External broker response omitted user")
    identity = build_external_broker_identity(user, settings)
    principal = SessionPrincipal(
        user_sub=identity["sub"],
        email=identity["email"],
        name=identity["name"] or None,
        roles=list(identity["roles"]),
        cognito_groups=list(identity["cognito_groups"]),
        auth_mode="external_broker",
        authenticated_at=datetime.now(timezone.utc).isoformat(),
        server_instance_id=get_server_instance_id(),
        app_context={},
    )
    cognito_session.store_session_principal(request, build_web_session_config(settings), principal)
    request.session.pop(EXTERNAL_BROKER_STATE_KEY, None)
    redirect_to = _clean(request.session.pop(EXTERNAL_BROKER_NEXT_KEY, None)) or "/"
    if not redirect_to.startswith("/"):
        redirect_to = "/"
    return RedirectResponse(url=redirect_to, status_code=302)


def _principal_to_user_context(
    principal: SessionPrincipal, settings: ZebraDaySettings
) -> dict[str, Any]:
    expires_at = ""
    authenticated_at = _clean(principal.authenticated_at)
    if authenticated_at:
        try:
            parsed = datetime.fromisoformat(authenticated_at)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            else:
                parsed = parsed.astimezone(timezone.utc)
            expires_at = (parsed + timedelta(hours=12)).isoformat()
        except ValueError:
            expires_at = ""

    return {
        "sub": principal.user_sub,
        "email": principal.email,
        "name": principal.name or "",
        "roles": list(principal.roles),
        "cognito_groups": list(principal.cognito_groups),
        "auth_mode": principal.auth_mode,
        "expires_at": expires_at,
        "service_principal": bool(principal.app_context.get("service_principal", False)),
    }


@dataclass
class CognitoBinding:
    settings: ZebraDaySettings
    config: Any
    auth: Any
    jwks: Any
    web_session_config: CognitoWebSessionConfig | None = None

    def _canonicalize_loopback_url(self, value: str) -> str:
        parts = urlsplit(value)
        hostname = parts.hostname or ""
        if hostname not in {"127.0.0.1", "0.0.0.0", "::1"}:
            return value
        port = parts.port
        netloc = "localhost" if port is None else f"localhost:{port}"
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))

    def redirect_uri(self, request: Request) -> str:
        configured = _clean(getattr(self.config, "callback_url", ""))
        if configured:
            return self._canonicalize_loopback_url(configured)
        return self._canonicalize_loopback_url(str(request.url_for("auth_callback")))

    def logout_uri(self, request: Request) -> str:
        configured = _clean(getattr(self.config, "logout_url", ""))
        if configured:
            return self._canonicalize_loopback_url(configured)
        return self._canonicalize_loopback_url(str(request.url_for("login_page")))

    def build_login_url(self, request: Request) -> str:
        if self.web_session_config is not None:
            response = start_cognito_login(request, self.web_session_config, "/")
            return _clean(response.headers.get("location"))

        state = secrets.token_urlsafe(24)
        request.session["oauth_state"] = state
        return str(
            cognito_session.build_authorization_url(
                domain=self.config.cognito_domain,
                client_id=self.config.app_client_id,
                redirect_uri=self.redirect_uri(request),
                state=state,
            )
        )

    def build_logout_url(self, request: Request) -> str:
        return str(
            build_logout_url(
                domain=self.config.cognito_domain,
                client_id=self.config.app_client_id,
                logout_uri=self.logout_uri(request),
            )
        )

    def _verify_id_token(self, id_token: str, *, access_token: str | None = None) -> dict[str, Any]:
        from jose import JWTError, jwt

        kid = _clean(jwt.get_unverified_header(id_token).get("kid"))
        if not kid:
            raise ValueError("Cognito id token is missing a kid header")

        cache = getattr(self.auth, "cache", None)
        if cache is None:
            cache = self.jwks.JWKSCache(self.config.region, self.config.user_pool_id)
        key = cache.get_key(kid)
        issuer = (
            f"https://cognito-idp.{self.config.region}.amazonaws.com/{self.config.user_pool_id}"
        )
        try:
            claims = jwt.decode(
                id_token,
                key=key,
                algorithms=["RS256"],
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_iss": True,
                    "verify_aud": True,
                },
                issuer=issuer,
                audience=self.config.app_client_id,
                access_token=access_token,
            )
        except JWTError as exc:
            raise ValueError("Invalid Cognito id token") from exc
        return dict(claims)

    def exchange_code(self, request: Request, code: str) -> dict[str, Any]:
        tokens = _run_sync(
            cognito_session.exchange_authorization_code_async(
                domain=self.config.cognito_domain,
                client_id=self.config.app_client_id,
                code=code,
                redirect_uri=self.redirect_uri(request),
            )
        )
        access_token = _clean(tokens.get("access_token"))
        if not access_token:
            raise ValueError("Cognito token exchange did not return an access token")

        claims = dict(self.auth.verify_token(access_token))
        profile_claims: dict[str, Any] = {}
        id_token = _clean(tokens.get("id_token"))
        if id_token:
            profile_claims = self._verify_id_token(id_token, access_token=access_token)
        return {"tokens": tokens, "claims": claims, "profile_claims": profile_claims}

    def resolve_principal(
        self, token_payload: dict[str, Any], request: Request
    ) -> SessionPrincipal:
        access_token = _clean(token_payload.get("access_token"))
        if not access_token:
            raise ValueError("Cognito token exchange did not return an access token")

        claims = dict(self.auth.verify_token(access_token))
        profile_claims: dict[str, Any] = {}
        id_token = _clean(token_payload.get("id_token"))
        if id_token:
            profile_claims = self._verify_id_token(id_token, access_token=access_token)

        merged_claims = dict(claims)
        for key, value in profile_claims.items():
            if value not in ("", None, []):
                merged_claims[key] = value
        identity = build_user_identity(merged_claims, self.settings)
        return SessionPrincipal(
            user_sub=identity["sub"],
            email=identity["email"],
            name=identity["name"] or None,
            roles=list(identity["roles"]),
            cognito_groups=list(identity["cognito_groups"]),
            auth_mode=str(identity["auth_mode"] or "cognito_session"),
            authenticated_at=datetime.now(timezone.utc).isoformat(),
            server_instance_id=get_server_instance_id(),
            app_context={},
        )


def setup_session_auth(app, settings: ZebraDaySettings) -> CognitoWebSessionConfig:
    web_session_config = build_web_session_config(settings)
    configure_session_middleware(app, web_session_config)
    app.state.web_session_config = web_session_config
    return web_session_config


def setup_cognito_auth(_app, settings: ZebraDaySettings) -> CognitoBinding:
    """Create a Cognito binding from the configured runtime Cognito settings."""
    if not is_cognito_available():
        raise ImportError(
            "daylily-auth-cognito is required for Cognito authentication. "
            f"Import error: {get_cognito_import_error()}"
        )
    config = _require_cognito_runtime_settings(settings)
    auth = CognitoTokenVerifier(
        region=config.region,
        user_pool_id=config.user_pool_id,
        app_client_id=config.app_client_id,
    )
    return CognitoBinding(
        settings=settings,
        config=config,
        auth=auth,
        jwks=jwks,
        web_session_config=build_web_session_config(settings),
    )


def _has_internal_api_key(request: Request) -> bool:
    settings = getattr(request.app.state, "settings", None)
    expected = _clean(getattr(settings, "internal_api_key", ""))
    if not expected:
        return False
    auth_header = _clean(request.headers.get("authorization"))
    if not auth_header.lower().startswith("bearer "):
        return False
    token = auth_header.split(" ", 1)[1].strip()
    return token == expected


def _is_public(request: Request) -> bool:
    path = request.url.path
    if path in PUBLIC_PATHS or path in AUTH_PATHS:
        return True
    return (
        path.startswith("/static")
        or path.startswith("/files")
        or path.startswith("/generated")
        or path.startswith("/etc")
    )


def _is_loopback_request(request: Request) -> bool:
    client = request.client
    if client is None or not client.host:
        return False
    try:
        return ipaddress.ip_address(client.host).is_loopback
    except ValueError:
        return client.host == "localhost"


def _requires_json_response(request: Request) -> bool:
    path = request.url.path
    if path.startswith("/api/") or path in STRUCTURED_PATHS:
        return True
    accept = _clean(request.headers.get("accept")).lower()
    return "application/json" in accept and "text/html" not in accept


def _session_user(request: Request) -> dict[str, Any] | None:
    principal = load_session_principal(request)
    if principal is None:
        return None
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        return None
    return _principal_to_user_context(principal, settings)


class CognitoAuthMiddleware(BaseHTTPMiddleware):
    """Session-or-token auth middleware."""

    def __init__(
        self, app, cognito_auth: CognitoBinding | None, settings: ZebraDaySettings
    ) -> None:
        super().__init__(app)
        self.cognito_auth = cognito_auth
        self.settings = settings

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if self.settings.auth_mode == "none" or _is_public(request):
            return await call_next(request)  # type: ignore[no-any-return]

        if request.url.path in LOCAL_DOCS_PATHS and _is_loopback_request(request):
            return await call_next(request)  # type: ignore[no-any-return]

        session_user = _session_user(request)
        if session_user is not None:
            request.state.user = session_user
            request.state.auth_mode = str(session_user.get("auth_mode") or "session")
            request.state.authorized_by_email = session_user.get("email") or session_user.get(
                "user_id"
            )
            return await call_next(request)  # type: ignore[no-any-return]

        auth_reason = _clean(getattr(request.state, "cognito_auth_reason", ""))
        if auth_reason == "session_expired" and not _requires_json_response(request):
            return RedirectResponse(url="/auth/error?reason=session_expired", status_code=302)

        if _has_internal_api_key(request):
            request.state.user = {"service_principal": True, "auth_mode": "service_token"}
            request.state.auth_mode = "service_token"
            return await call_next(request)  # type: ignore[no-any-return]

        auth_header = _clean(request.headers.get("authorization"))
        if auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()
            if is_ai_agent_token(token):
                try:
                    grant = validate_ai_agent_request(request, token)
                except AgentTokenError as exc:
                    return Response(
                        content=json.dumps({"detail": exc.detail}),
                        media_type="application/json",
                        status_code=exc.status_code,
                        headers={"WWW-Authenticate": "Bearer"}
                        if exc.status_code == status.HTTP_401_UNAUTHORIZED
                        else None,
                    )
                request.state.user = {
                    "service_principal": False,
                    "auth_mode": "ai_agent_token",
                    "user_id": f"ai-agent:{grant.agent_id}",
                    "email": grant.issued_by_email,
                    "roles": ["viewer"],
                    "groups": ["ai-agent"],
                    "agent_id": grant.agent_id,
                    "agent_token_id": grant.token_id,
                    "agent_endpoint_id": grant.endpoint_id,
                }
                request.state.auth_mode = "ai_agent_token"
                request.state.authorized_by_email = grant.issued_by_email
                return await call_next(request)  # type: ignore[no-any-return]
        if self.cognito_auth and auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()
            try:
                claims = self.cognito_auth.auth.verify_token(token)
                request.state.user = build_user_identity(dict(claims), self.settings)
                request.state.auth_mode = "cognito"
                request.state.authorized_by_email = request.state.user.get("email") or request.state.user.get(
                    "user_id"
                )
                return await call_next(request)  # type: ignore[no-any-return]
            except Exception as exc:
                _log.warning("Bearer token rejected: %s", exc)

        if _requires_json_response(request):
            return Response(
                content='{"detail":"Authentication required"}',
                media_type="application/json",
                status_code=status.HTTP_401_UNAUTHORIZED,
                headers={"WWW-Authenticate": "Bearer"},
            )

        target = request.url.path
        if request.url.query:
            target = f"{target}?{request.url.query}"
        return RedirectResponse(url=f"/login?next={quote(target, safe='/')}", status_code=302)
