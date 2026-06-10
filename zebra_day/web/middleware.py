"""Middleware for zebra_day request logging and observability."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections import defaultdict
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

_access_log = logging.getLogger("lsmc.access")


def _common_access_log_payload(
    *,
    request: Request,
    service_id: str,
    status_code: int,
    duration_ms: float,
    route_template: str,
) -> dict[str, object]:
    actor = (
        getattr(request.state, "authorized_by_email", None)
        or getattr(request.state, "authorizing_human", None)
        or getattr(request.state, "actor", None)
    )
    ai_agent_id = getattr(request.state, "ai_agent_id", None) or getattr(
        request.state, "agent_id", None
    )
    return {
        "event": "request_completed",
        "request_id": getattr(request.state, "request_id", ""),
        "correlation_id": getattr(request.state, "correlation_id", ""),
        "service_id": service_id,
        "actor": actor,
        "ai_agent_id": ai_agent_id,
        "authorizing_human": getattr(request.state, "authorizing_human", None)
        or getattr(request.state, "authorized_by_email", None),
        "ip": request.client.host if request.client else None,
        "method": request.method,
        "path": request.url.path,
        "route": route_template or request.url.path,
        "route_template": route_template or request.url.path,
        "status": status_code,
        "duration_ms": round(duration_ms, 2),
        "denial_reason": getattr(request.state, "denial_reason", None)
        or (f"http_{status_code}" if status_code in {401, 403} else None),
        "auth_mode": getattr(request.state, "auth_mode", None),
    }


def _emit_access_log(payload: dict[str, object], *, level: int = logging.INFO) -> None:
    _access_log.log(
        level,
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
        extra=payload,
    )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for structured request logging.

    Logs client IP, request path, method, timing, and response status.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and log structured data."""
        start_time = time.perf_counter()
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        correlation_id = request.headers.get("x-correlation-id") or request_id
        request.state.request_id = request_id
        request.state.correlation_id = correlation_id

        # Extract client info
        client_ip = request.client.host if request.client else "unknown"
        method = request.method
        path = request.url.path
        route = request.scope.get("route")
        path_template = getattr(route, "path", path)
        request.state.path_template = path_template
        str(request.query_params) if request.query_params else ""

        # Extract relevant parameters for print operations
        lab = request.query_params.get("lab", "")
        printer = request.query_params.get("printer", "")
        template = request.query_params.get("label_zpl_style", "")

        try:
            response = await call_next(request)
            status_code = response.status_code
            outcome = "success" if status_code < 400 else "error"
        except Exception as exc:
            status_code = 500
            outcome = "exception"
            payload = _common_access_log_payload(
                request=request,
                service_id="zebra-day",
                status_code=status_code,
                duration_ms=(time.perf_counter() - start_time) * 1000,
                route_template=path_template or path,
            )
            payload["outcome"] = outcome
            payload["error"] = str(exc)
            _emit_access_log(payload, level=logging.ERROR)
            raise

        route = request.scope.get("route")
        path_template = getattr(route, "path", path)
        request.state.path_template = path_template
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        log_context = _common_access_log_payload(
            request=request,
            service_id="zebra-day",
            status_code=status_code,
            duration_ms=elapsed_ms,
            route_template=path_template or path,
        )
        log_context["client_ip"] = client_ip
        log_context["status_code"] = status_code
        log_context["elapsed_ms"] = round(elapsed_ms, 2)
        log_context["outcome"] = outcome

        # Add print-specific context if relevant
        if lab:
            log_context["lab"] = lab
        if printer:
            log_context["printer"] = printer
        if template:
            log_context["template"] = template

        # Log at appropriate level
        if status_code >= 500:
            _emit_access_log(log_context, level=logging.ERROR)
        elif status_code >= 400:
            _emit_access_log(log_context, level=logging.WARNING)
        else:
            _emit_access_log(log_context, level=logging.INFO)

        observability = getattr(request.app.state, "observability", None)
        if observability is not None:
            observability.record_http_request(
                method=method,
                route_template=str(path_template or path),
                status_code=status_code,
                duration_ms=elapsed_ms,
            )
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Correlation-ID"] = correlation_id
        return response  # type: ignore[no-any-return]


class PrintRateLimiter:
    """
    Simple rate limiter for print endpoints.

    Uses a sliding window approach with configurable limits.
    """

    def __init__(
        self,
        max_requests: int = 3,
        window_seconds: float = 1.0,
        max_concurrent: int = 3,
    ):
        """
        Initialize rate limiter.

        Args:
            max_requests: Maximum requests per window per client IP
            window_seconds: Time window in seconds
            max_concurrent: Maximum concurrent print operations
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_concurrent = max_concurrent

        self._request_times: dict[str, list[float]] = defaultdict(list)
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._lock = asyncio.Lock()

    async def acquire(self, client_ip: str) -> tuple[bool, str]:
        """
        Try to acquire a print slot.

        Returns:
            Tuple of (allowed, reason)
        """
        now = time.time()

        async with self._lock:
            # Clean old entries
            cutoff = now - self.window_seconds
            self._request_times[client_ip] = [
                t for t in self._request_times[client_ip] if t > cutoff
            ]

            # Check rate limit
            if len(self._request_times[client_ip]) >= self.max_requests:
                return (
                    False,
                    f"Rate limit exceeded: {self.max_requests} requests per {self.window_seconds}s",
                )

            # Try to acquire semaphore (non-blocking check)
            if self._semaphore.locked() and self._semaphore._value == 0:
                return False, f"Too many concurrent print operations (max {self.max_concurrent})"

            # Record this request
            self._request_times[client_ip].append(now)

        # Acquire semaphore for actual operation
        await self._semaphore.acquire()
        return True, ""

    def release(self) -> None:
        """Release a print slot after operation completes."""
        self._semaphore.release()


# Global rate limiter instance
print_rate_limiter = PrintRateLimiter()
