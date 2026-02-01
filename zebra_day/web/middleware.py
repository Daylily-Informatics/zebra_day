"""
Middleware for the zebra_day FastAPI application.

Provides request logging and rate limiting functionality.
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from zebra_day.logging_config import get_logger

_log = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for structured request logging.

    Logs client IP, request path, method, timing, and response status.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and log structured data."""
        start_time = time.perf_counter()

        # Extract client info
        client_ip = request.client.host if request.client else "unknown"
        method = request.method
        path = request.url.path
        query = str(request.query_params) if request.query_params else ""

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
            _log.exception(
                "Request failed",
                extra={
                    "client_ip": client_ip,
                    "method": method,
                    "path": path,
                    "error": str(exc),
                },
            )
            raise

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Build log context
        log_context = {
            "client_ip": client_ip,
            "method": method,
            "path": path,
            "status_code": status_code,
            "elapsed_ms": round(elapsed_ms, 2),
            "outcome": outcome,
        }

        # Add print-specific context if relevant
        if lab:
            log_context["lab"] = lab
        if printer:
            log_context["printer"] = printer
        if template:
            log_context["template"] = template

        # Log at appropriate level
        if status_code >= 500:
            _log.error("Request completed", extra=log_context)
        elif status_code >= 400:
            _log.warning("Request completed", extra=log_context)
        else:
            _log.info("Request completed", extra=log_context)

        return response


class PrintRateLimiter:
    """
    Simple rate limiter for print endpoints.

    Uses a sliding window approach with configurable limits.
    """

    def __init__(
        self,
        max_requests: int = 10,
        window_seconds: float = 60.0,
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
                return False, f"Rate limit exceeded: {self.max_requests} requests per {self.window_seconds}s"

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

