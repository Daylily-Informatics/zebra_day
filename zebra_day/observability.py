"""In-process observability contract support for zebra_day."""

from __future__ import annotations

import os
import uuid
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import Request

from zebra_day import __version__
from zebra_day.settings import ZebraDaySettings

CONTRACT_VERSION = "v3"
SERVICE_NAME = "zebra-day"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017


@dataclass(frozen=True)
class ProjectionMetadata:
    state: str = "ready"
    stale: bool = False
    observed_at: str | None = None
    last_synced_at: str | None = None
    detail: str | None = None
    name: str | None = None

    def model_dump(self) -> dict[str, Any]:
        snapshot_at = self.observed_at or _utcnow()
        payload: dict[str, Any] = {
            "state": self.state,
            "stale": self.stale,
            "observed_at": snapshot_at,
            "last_synced_at": self.last_synced_at or snapshot_at,
            "detail": self.detail,
        }
        if self.name:
            payload["name"] = self.name
        return payload


@dataclass
class EndpointRollup:
    method: str
    route_template: str
    request_count: int = 0
    status_class_counts: Counter[str] = field(default_factory=Counter)
    durations_ms: list[float] = field(default_factory=list)
    observed_at: str | None = None

    def record(self, *, status_code: int, duration_ms: float) -> None:
        self.request_count += 1
        self.status_class_counts[f"{status_code // 100}xx"] += 1
        self.durations_ms.append(float(duration_ms))
        self.observed_at = _utcnow()

    def to_dict(self) -> dict[str, Any]:
        ordered = sorted(self.durations_ms)
        return {
            "method": self.method,
            "route_template": self.route_template,
            "request_count": self.request_count,
            "status_class_counts": dict(self.status_class_counts),
            "p50_ms": _percentile(ordered, 0.50),
            "p95_ms": _percentile(ordered, 0.95),
            "p99_ms": _percentile(ordered, 0.99),
            "fingerprint_count": 0,
            "observed_at": self.observed_at or _utcnow(),
        }


@dataclass
class FamilyRollup:
    family: str
    request_count: int = 0
    error_count: int = 0
    durations_ms: list[float] = field(default_factory=list)
    observed_at: str | None = None

    def record(self, *, status_code: int, duration_ms: float) -> None:
        self.request_count += 1
        if status_code >= 400:
            self.error_count += 1
        self.durations_ms.append(float(duration_ms))
        self.observed_at = _utcnow()

    def to_dict(self) -> dict[str, Any]:
        ordered = sorted(self.durations_ms)
        return {
            "family": self.family,
            "request_count": self.request_count,
            "error_count": self.error_count,
            "p95_ms": _percentile(ordered, 0.95),
            "observed_at": self.observed_at or _utcnow(),
        }


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    index = max(0, min(len(values) - 1, round((len(values) - 1) * percentile)))
    return round(float(values[index]), 3)


class ZebraDayObservability:
    """Small in-process rollups for the required endpoints."""

    def __init__(self, settings: ZebraDaySettings) -> None:
        self.settings = settings
        self.instance_id = str(uuid.uuid4())
        self.started_at = _utcnow()
        self.route_templates: set[str] = set()
        self._endpoint_rollups: dict[tuple[str, str], EndpointRollup] = {}
        self._family_rollups: dict[str, FamilyRollup] = {}
        self._auth_recent: deque[dict[str, Any]] = deque(maxlen=25)
        self._auth_status_counts: Counter[str] = Counter()

    def projection(
        self,
        name: str | None = None,
        *,
        observed_at: str | None = None,
        detail: str | None = None,
    ) -> ProjectionMetadata:
        snapshot_at = observed_at or self.started_at
        return ProjectionMetadata(
            name=name,
            state="ready",
            stale=False,
            observed_at=snapshot_at,
            last_synced_at=snapshot_at,
            detail=detail,
        )

    def base_frame(self, request: Request, *, status: str) -> dict[str, Any]:
        return {
            "contract_version": CONTRACT_VERSION,
            "service": SERVICE_NAME,
            "environment": self.settings.deployment_code or os.environ.get("ENVIRONMENT") or "",
            "instance_id": self.instance_id,
            "observed_at": _utcnow(),
            "status": status,
            "request_id": getattr(request.state, "request_id", ""),
            "correlation_id": getattr(request.state, "correlation_id", ""),
            "build": {
                "version": __version__,
                "sha": os.environ.get("BUILD_SHA") or os.environ.get("GIT_SHA") or "",
            },
        }

    def with_projection(
        self,
        request: Request,
        *,
        name: str,
        status: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        frame = self.base_frame(request, status=status)
        frame.update(payload)
        frame["projection"] = self.projection(name, observed_at=frame["observed_at"]).model_dump()
        return frame

    def public_healthz_payload(self, request: Request) -> dict[str, Any]:
        payload = self.base_frame(request, status="ok")
        observed_at = str(payload.get("observed_at") or _utcnow())
        payload["checks"] = {
            "process": {
                "status": "ok",
                "started_at": self.started_at,
            }
        }
        payload["projection"] = self.projection("healthz", observed_at=observed_at).model_dump()
        return payload

    def public_readyz_payload(
        self,
        request: Request,
        *,
        ready: bool,
        database_check: dict[str, Any],
        process_details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = self.base_frame(request, status="ok" if ready else "degraded")
        observed_at = str(payload.get("observed_at") or _utcnow())
        payload["ready"] = ready
        payload["checks"] = {
            "process": {
                "status": "ok",
                "started_at": self.started_at,
                "details": dict(process_details or {}),
            },
            "database": {
                "status": str(database_check.get("status") or "unknown"),
                "latency_ms": database_check.get("latency_ms"),
                "detail": database_check.get("detail"),
                "observed_at": database_check.get("observed_at") or observed_at,
                "details": dict(database_check.get("details") or {}),
            },
        }
        payload["projection"] = self.projection("readyz", observed_at=observed_at).model_dump()
        return payload

    def record_route(self, path_template: str) -> None:
        self.route_templates.add(path_template)

    def record_http_request(
        self,
        *,
        method: str,
        route_template: str,
        status_code: int,
        duration_ms: float,
    ) -> None:
        normalized_method = method.upper()
        normalized_route = str(route_template or "").strip() or "/"
        self.route_templates.add(normalized_route)

        endpoint = self._endpoint_rollups.setdefault(
            (normalized_method, normalized_route),
            EndpointRollup(method=normalized_method, route_template=normalized_route),
        )
        endpoint.record(status_code=status_code, duration_ms=duration_ms)

        family = self._family_rollups.setdefault(
            self._classify_family(normalized_route),
            FamilyRollup(family=self._classify_family(normalized_route)),
        )
        family.record(status_code=status_code, duration_ms=duration_ms)

    def api_health_payload(self) -> tuple[ProjectionMetadata, list[dict[str, Any]]]:
        families = [
            item.to_dict()
            for item in sorted(self._family_rollups.values(), key=lambda rollup: rollup.family)
        ]
        observed_at = max(
            (item["observed_at"] for item in families if item.get("observed_at")),
            default=self.started_at,
        )
        return self.projection("api_health", observed_at=observed_at), families

    def endpoint_health_payload(
        self, *, offset: int = 0, limit: int = 25
    ) -> tuple[ProjectionMetadata, dict[str, Any]]:
        items = [
            item.to_dict()
            for item in sorted(
                self._endpoint_rollups.values(),
                key=lambda rollup: (rollup.method, rollup.route_template),
            )
        ]
        observed_at = max(
            (item["observed_at"] for item in items if item.get("observed_at")),
            default=self.started_at,
        )
        page_items = items[offset : offset + limit]
        return self.projection("endpoint_health", observed_at=observed_at), {
            "page": {"total": len(items), "offset": offset, "limit": limit},
            "items": page_items,
        }

    def record_auth_event(
        self,
        *,
        status: str,
        mode: str,
        detail: str,
        principal_email: str = "",
    ) -> None:
        payload = {
            "status": status,
            "mode": str(mode or "").strip(),
            "detail": str(detail or "").strip(),
            "principal_email": str(principal_email or "").strip(),
            "observed_at": _utcnow(),
        }
        self._auth_recent.appendleft(payload)
        self._auth_status_counts[payload["status"]] += 1

    def auth_health_payload(
        self,
        *,
        auth_mode: str,
        cognito_domain: str,
        user_pool_id: str,
        app_client_id_present: bool,
        active_session_count: int | None,
    ) -> tuple[ProjectionMetadata, dict[str, Any]]:
        recent = list(self._auth_recent)
        observed_at = recent[0]["observed_at"] if recent else self.started_at
        if auth_mode == "none":
            sessions: dict[str, Any] = {
                "supported": False,
                "active_session_count": None,
                "recent_user_count": None,
                "observed_at": None,
            }
            status = "disabled"
            recent_user_count = None
        else:
            recent_user_count = len(
                {
                    item["principal_email"]
                    for item in recent
                    if str(item.get("principal_email") or "").strip()
                }
            )
            sessions = {
                "supported": True,
                "active_session_count": active_session_count,
                "recent_user_count": recent_user_count,
                "observed_at": observed_at,
            }
            status = "ok"
        payload = {
            "auth": {
                "mode": auth_mode,
                "cognito_configured": auth_mode == "cognito",
                "cognito_domain": cognito_domain,
                "user_pool_id": user_pool_id,
                "app_client_id_present": app_client_id_present,
                "recent": recent,
                "status_counts": dict(self._auth_status_counts),
                "sessions": sessions,
            }
        }
        return self.projection("auth_health", observed_at=observed_at), {
            "status": status,
            **payload,
        }

    def obs_services_payload(self, *, auth_mode: str) -> dict[str, Any]:
        rich_auth = "none" if auth_mode == "none" else "bearer_token"
        configured_dependencies = ["daylily-tapdb"]
        if auth_mode == "cognito":
            configured_dependencies.insert(0, "daylily-auth-cognito")
        endpoints = [
            {"path": "/healthz", "auth": "none", "kind": "liveness"},
            {"path": "/readyz", "auth": "none", "kind": "readiness"},
            {"path": "/health", "auth": rich_auth, "kind": "summary"},
            {"path": "/obs_services", "auth": rich_auth, "kind": "discovery"},
            {"path": "/api_health", "auth": rich_auth, "kind": "api_rollup"},
            {"path": "/endpoint_health", "auth": rich_auth, "kind": "endpoint_rollup"},
            {"path": "/db_health", "auth": rich_auth, "kind": "database"},
            {"path": "/auth_health", "auth": rich_auth, "kind": "auth"},
        ]
        if auth_mode != "none":
            endpoints.append({"path": "/my_health", "auth": "authenticated_self", "kind": "self"})
        return {
            "endpoints": endpoints,
            "extensions": ["zebra_day.observability_v1"],
            "dependencies": {
                "configured_services": configured_dependencies,
                "observed_services": configured_dependencies,
            },
        }

    @staticmethod
    def _classify_family(route_template: str) -> str:
        normalized = str(route_template or "").strip()
        if not normalized:
            return "other"
        if normalized.startswith("/api/v1/labs"):
            return "labs"
        if normalized.startswith("/api/v1/templates"):
            return "templates"
        if normalized.startswith("/api/v1/render"):
            return "render"
        if normalized.startswith("/api/v1/print"):
            return "print"
        if normalized.startswith("/api/v1/config"):
            return "config"
        if normalized in {
            "/health",
            "/healthz",
            "/readyz",
            "/obs_services",
            "/api_health",
            "/endpoint_health",
            "/db_health",
            "/auth_health",
            "/my_health",
        }:
            return "observability"
        if normalized.startswith("/api/v1"):
            return "api"
        return "ui"
