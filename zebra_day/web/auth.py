"""Authentication helpers for the zebra_day web app."""

from __future__ import annotations

import ipaddress
import os
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse, Response

from zebra_day.logging_config import get_logger
from zebra_day.optional_deps import import_from_sibling
from zebra_day.rbac import parse_groups, roles_from_groups
from zebra_day.settings import ZebraDaySettings

_web_session = import_from_sibling("daylily_cognito.web_session", "daylily-cognito")
_cognito_oauth = import_from_sibling("daylily_cognito.oauth", "daylily-cognito")

CognitoWebAuthError = _web_session.CognitoWebAuthError
CognitoWebSessionConfig = _web_session.CognitoWebSessionConfig
SessionPrincipal = _web_session.SessionPrincipal
clear_session_principal = _web_session.clear_session_principal
complete_cognito_callback = _web_session.complete_cognito_callback
configure_session_middleware = _web_session.configure_session_middleware
load_session_principal = _web_session.load_session_principal
start_cognito_login = _web_session.start_cognito_login
store_session_principal = _web_session.store_session_principal
build_logout_url = _cognito_oauth.build_logout_url

_log = get_logger(__name__)

PUBLIC_PATHS = ["/healthz", "/readyz", "/login"]
AUTH_PATHS = ["/auth/login", "/auth/callback", "/auth/logout", "/auth/error", "/login"]
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


def build_user_identity(claims: dict[str, Any], settings: ZebraDaySettings) -> dict[str, Any]:
    merged_claims = dict(claims)
    groups = parse_groups(merged_claims.get("cognito:groups"))
    roles = roles_from_groups(groups, settings.cognito_group_role_map)
    merged_claims["cognito_groups"] = groups
    merged_claims["roles"] = roles
    return {
        "sub": _clean(merged_claims.get("sub") or merged_claims.get("username")),
        "email": _clean(merged_claims.get("email")),
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


def is_cognito_available() -> bool:
    try:
        import_from_sibling("daylily_cognito", "daylily-cognito")
        return True
    except ImportError:
        return False


def get_cognito_import_error() -> str | None:
    try:
        import_from_sibling("daylily_cognito", "daylily-cognito")
        return None
    except ImportError as exc:
        return str(exc)


def load_daycog_contract() -> dict[str, str]:
    """Load the active daycog context values."""
    config_mod = import_from_sibling("daylily_cognito.config", "daylily-cognito")
    values = config_mod.get_context_values()
    if not values:
        raise ValueError("No active daycog context found in ~/.config/daycog/config.yaml")

    contract = {
        "region": _clean(values.get("COGNITO_REGION") or values.get("AWS_REGION")),
        "user_pool_id": _clean(values.get("COGNITO_USER_POOL_ID")),
        "app_client_id": _clean(values.get("COGNITO_APP_CLIENT_ID")),
        "aws_profile": _clean(values.get("AWS_PROFILE")),
        "cognito_domain": _clean(values.get("COGNITO_DOMAIN")),
        "client_name": _clean(values.get("COGNITO_CLIENT_NAME")),
        "callback_url": _clean(
            values.get("COGNITO_CALLBACK_URL")
            or values.get("COGNITO_REDIRECT_URI")
            or values.get("COGNITO_REDIRECT_URL")
        ),
        "logout_url": _clean(values.get("COGNITO_LOGOUT_URL")),
    }
    missing = [
        key
        for key in ("region", "user_pool_id", "app_client_id", "cognito_domain")
        if not contract[key]
    ]
    if missing:
        raise ValueError(f"Active daycog context is missing required values: {', '.join(missing)}")
    return contract


SERVER_INSTANCE_ID = secrets.token_urlsafe(16)
_PUBLIC_BASE_URL_ENV = "ZEBRA_DAY_PUBLIC_BASE_URL"


def get_server_instance_id() -> str:
    """Return the process-scoped server instance identifier."""
    return SERVER_INSTANCE_ID


def _session_secret(settings: ZebraDaySettings) -> str:
    return (
        os.environ.get("ZEBRA_DAY_SESSION_SECRET")
        or f"zebra-day-{settings.deployment_code}-dev-secret"
    )


def _runtime_public_base_url(settings: ZebraDaySettings) -> str:
    configured = _clean(os.environ.get(_PUBLIC_BASE_URL_ENV))
    if configured:
        return configured
    scheme = "https" if settings.auth_mode == "cognito" else "http"
    return f"{scheme}://localhost:{settings.port}"


def _origin(value: str) -> str:
    parts = urlsplit(value)
    return f"{parts.scheme}://{parts.netloc}"


def build_web_session_config(settings: ZebraDaySettings) -> CognitoWebSessionConfig:
    """Build the shared browser-session config for the current runtime."""
    contract: dict[str, str] = {}
    if settings.auth_mode == "cognito":
        try:
            contract = load_daycog_contract()
        except Exception as exc:
            _log.warning("Using fallback Cognito web-session URLs: %s", exc)

    callback_url = _clean(contract.get("callback_url"))
    logout_url = _clean(contract.get("logout_url"))
    public_base_url = (
        _origin(callback_url)
        if callback_url
        else _origin(logout_url)
        if logout_url
        else _runtime_public_base_url(settings)
    )
    if not callback_url:
        callback_url = f"{public_base_url}{settings.callback_path}"
    if not logout_url:
        logout_url = f"{public_base_url}/login"

    return CognitoWebSessionConfig(
        domain=_clean(contract.get("cognito_domain")) or "localhost",
        client_id=_clean(contract.get("app_client_id")) or settings.tapdb_client_id,
        redirect_uri=callback_url,
        logout_uri=logout_url,
        session_secret_key=_session_secret(settings),
        session_cookie_name=settings.session_cookie_name,
        public_base_url=public_base_url,
        server_instance_id=get_server_instance_id(),
        allow_insecure_http=public_base_url.startswith("http://"),
    )


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
    oauth: Any
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
            self.oauth.build_authorization_url(
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

    def _verify_id_token(self, id_token: str) -> dict[str, Any]:
        from jose import JWTError, jwt

        kid = _clean(jwt.get_unverified_header(id_token).get("kid"))
        if not kid:
            raise ValueError("Cognito id token is missing a kid header")

        cache = getattr(self.auth, "_jwks_cache", None)
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
            )
        except JWTError as exc:
            raise ValueError("Invalid Cognito id token") from exc
        return dict(claims)

    def _decode_id_token_unverified(self, id_token: str) -> dict[str, Any]:
        from jose import JWTError, jwt

        try:
            claims = jwt.decode(
                id_token,
                key="",
                options={
                    "verify_signature": False,
                    "verify_exp": False,
                    "verify_iss": False,
                    "verify_aud": False,
                    "verify_nbf": False,
                    "verify_iat": False,
                },
            )
        except JWTError as exc:
            raise ValueError("Invalid Cognito id token payload") from exc
        return dict(claims)

    def exchange_code(self, request: Request, code: str) -> dict[str, Any]:
        tokens = self.oauth.exchange_authorization_code(
            domain=self.config.cognito_domain,
            client_id=self.config.app_client_id,
            code=code,
            redirect_uri=self.redirect_uri(request),
        )
        access_token = _clean(tokens.get("access_token"))
        if not access_token:
            raise ValueError("Cognito token exchange did not return an access token")

        claims = dict(self.auth.verify_token(access_token))
        profile_claims: dict[str, Any] = {}
        id_token = _clean(tokens.get("id_token"))
        if id_token:
            try:
                profile_claims = self._verify_id_token(id_token)
            except ValueError as exc:
                _log.warning(
                    "Falling back to unverified Cognito id token decode for profile claims: %s",
                    exc,
                )
                try:
                    profile_claims = self._decode_id_token_unverified(id_token)
                except ValueError as decode_exc:
                    _log.warning(
                        "Continuing without Cognito id token profile claims: %s",
                        decode_exc,
                    )
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
            try:
                profile_claims = self._verify_id_token(id_token)
            except ValueError as exc:
                _log.warning(
                    "Falling back to unverified Cognito id token decode for profile claims: %s",
                    exc,
                )
                try:
                    profile_claims = self._decode_id_token_unverified(id_token)
                except ValueError as decode_exc:
                    _log.warning(
                        "Continuing without Cognito id token profile claims: %s",
                        decode_exc,
                    )
                    profile_claims = {}

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
    """Create a Cognito binding from the active daycog context."""
    if not is_cognito_available():
        raise ImportError(
            "daylily-cognito is required for Cognito authentication. "
            f"Import error: {get_cognito_import_error()}"
        )
    daycog = import_from_sibling("daylily_cognito", "daylily-cognito")
    oauth = import_from_sibling("daylily_cognito.oauth", "daylily-cognito")
    jwks = import_from_sibling("daylily_cognito.jwks", "daylily-cognito")
    contract = load_daycog_contract()
    config = SimpleNamespace(**contract)
    auth = daycog.CognitoAuth(
        region=config.region,
        user_pool_id=config.user_pool_id,
        app_client_id=config.app_client_id,
        profile=_clean(config.aws_profile) or None,
    )
    return CognitoBinding(
        settings=settings,
        config=config,
        auth=auth,
        oauth=oauth,
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
            return await call_next(request)  # type: ignore[no-any-return]

        auth_reason = _clean(getattr(request.state, "cognito_auth_reason", ""))
        if auth_reason == "session_expired" and not _requires_json_response(request):
            return RedirectResponse(url="/auth/error?reason=session_expired", status_code=302)

        if _has_internal_api_key(request):
            request.state.user = {"service_principal": True, "auth_mode": "service_token"}
            return await call_next(request)  # type: ignore[no-any-return]

        auth_header = _clean(request.headers.get("authorization"))
        if self.cognito_auth and auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()
            try:
                claims = self.cognito_auth.auth.verify_token(token)
                request.state.user = build_user_identity(dict(claims), self.settings)
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
        return RedirectResponse(url=f"/auth/login?next={quote(target)}", status_code=302)
