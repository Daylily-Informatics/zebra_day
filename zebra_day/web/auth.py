"""Authentication integration for zebra_day web server.

Provides optional Cognito authentication support via the daylily-cognito library.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from fastapi import Depends, HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from zebra_day.logging_config import get_logger

if TYPE_CHECKING:
    from fastapi import FastAPI

_log = get_logger(__name__)

# Endpoints that should never require authentication
PUBLIC_PATHS: List[str] = [
    "/healthz",
    "/readyz",
    "/docs",
    "/openapi.json",
    "/redoc",
]

# Try to import daylily-cognito components
_COGNITO_AVAILABLE = False
_COGNITO_IMPORT_ERROR: Optional[str] = None

try:
    from daylily_cognito import CognitoAuth, CognitoConfig, create_auth_dependency

    _COGNITO_AVAILABLE = True
except ImportError as e:
    _COGNITO_IMPORT_ERROR = str(e)
    CognitoAuth = None  # type: ignore[misc, assignment]
    CognitoConfig = None  # type: ignore[misc, assignment]
    create_auth_dependency = None  # type: ignore[misc, assignment]


def is_cognito_available() -> bool:
    """Check if daylily-cognito library is installed."""
    return _COGNITO_AVAILABLE


def get_cognito_import_error() -> Optional[str]:
    """Get the import error message if daylily-cognito is not available."""
    return _COGNITO_IMPORT_ERROR


class CognitoAuthMiddleware(BaseHTTPMiddleware):
    """Middleware that enforces Cognito authentication on protected endpoints.

    Exempts health check endpoints and other public paths.
    """

    def __init__(self, app: "FastAPI", cognito_auth: Any) -> None:
        super().__init__(app)
        self.cognito_auth = cognito_auth
        self.get_current_user = create_auth_dependency(cognito_auth, optional=False)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Check authentication for protected endpoints."""
        path = request.url.path

        # Allow public endpoints without authentication
        if any(path.startswith(public) for public in PUBLIC_PATHS):
            return await call_next(request)

        # Allow static files without authentication
        if path.startswith("/static") or path.startswith("/files") or path.startswith("/etc"):
            return await call_next(request)

        # Check for Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return Response(
                content='{"detail":"Authentication required"}',
                status_code=status.HTTP_401_UNAUTHORIZED,
                media_type="application/json",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Validate Bearer token
        if not auth_header.startswith("Bearer "):
            return Response(
                content='{"detail":"Invalid authorization header format"}',
                status_code=status.HTTP_401_UNAUTHORIZED,
                media_type="application/json",
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = auth_header[7:]  # Remove "Bearer " prefix
        try:
            # Verify token and attach user to request state
            user_claims = self.cognito_auth.verify_token(token)
            request.state.user = user_claims
        except HTTPException:
            return Response(
                content='{"detail":"Invalid or expired token"}',
                status_code=status.HTTP_401_UNAUTHORIZED,
                media_type="application/json",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except Exception as e:
            _log.error("Authentication error: %s", str(e))
            return Response(
                content='{"detail":"Authentication failed"}',
                status_code=status.HTTP_401_UNAUTHORIZED,
                media_type="application/json",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return await call_next(request)


def setup_cognito_auth(app: "FastAPI") -> Any:
    """Configure Cognito authentication for the FastAPI app.

    Reads configuration from environment variables:
        - COGNITO_USER_POOL_ID: Cognito User Pool ID (required)
        - COGNITO_APP_CLIENT_ID or COGNITO_CLIENT_ID: App Client ID (required)
        - COGNITO_REGION or AWS_REGION: AWS region (defaults to us-west-2)
        - AWS_PROFILE: Optional AWS profile name

    Returns:
        CognitoAuth instance

    Raises:
        ValueError: If required environment variables are missing
        ImportError: If daylily-cognito is not installed
    """
    if not _COGNITO_AVAILABLE:
        raise ImportError(
            f"daylily-cognito library is required for Cognito authentication. "
            f"Install with: pip install -e '.[auth]'\n"
            f"Import error: {_COGNITO_IMPORT_ERROR}"
        )

    # Load config from environment
    try:
        config = CognitoConfig.from_legacy_env()
    except ValueError as e:
        raise ValueError(
            f"Missing required Cognito configuration. {e}\n"
            "Set the following environment variables:\n"
            "  COGNITO_USER_POOL_ID=your-pool-id\n"
            "  COGNITO_APP_CLIENT_ID=your-client-id\n"
            "  COGNITO_REGION=us-west-2  (optional, defaults to us-west-2)"
        ) from e

    # Create CognitoAuth instance
    cognito_auth = CognitoAuth(
        region=config.region,
        user_pool_id=config.user_pool_id,
        app_client_id=config.app_client_id,
        profile=config.aws_profile,
    )

    _log.info(
        "Cognito authentication enabled (region=%s, pool=%s)",
        config.region,
        config.user_pool_id,
    )

    return cognito_auth

