"""Shared observability helpers for zebra_day."""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from socket import gethostname
from typing import Any

from fastapi import HTTPException, Request
from pydantic import BaseModel

from zebra_day import __version__

CONTRACT_VERSION = "v3"


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


class ProjectionMetadata(BaseModel):
    state: str = "ready"
    stale: bool = False
    observed_at: str | None = None
    last_synced_at: str | None = None
    detail: str | None = None


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
            "observed_at": self.observed_at,
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
            "observed_at": self.observed_at,
        }


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    index = max(0, min(len(values) - 1, round((len(values) - 1) * percentile)))
    return round(float(values[index]), 3)


def _environment() -> str:
    return str(__import__("os").environ.get("ZEBRA_DAY_ENVIRONMENT", "local")).strip() or "local"


def _instance_id() -> str:
    return f"zebra-day-{gethostname()}"


def base_frame(request: Request, *, status: str) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "service": "zebra_printer",
        "environment": _environment(),
        "instance_id": _instance_id(),
        "observed_at": _utcnow(),
        "status": status,
        "request_id": getattr(request.state, "request_id", ""),
        "correlation_id": getattr(request.state, "correlation_id", ""),
        "build": {
            "version": __version__,
            "sha": None,
        },
    }


def _with_projection(payload: dict[str, Any], projection: ProjectionMetadata) -> dict[str, Any]:
    payload["projection"] = projection.model_dump()
    return payload


class ZebraObservabilityStore:
    def __init__(self, *, auth_mode: str) -> None:
        self._started_at = _utcnow()
        self._auth_mode = auth_mode
        self._endpoint_rollups: dict[tuple[str, str], EndpointRollup] = {}
        self._family_rollups: dict[str, FamilyRollup] = {}
        self._auth_recent: deque[dict[str, Any]] = deque(maxlen=25)
        self._auth_status_counts: Counter[str] = Counter()
        self._obs_services_snapshot = self._build_obs_services_snapshot()

    def _build_obs_services_snapshot(self) -> dict[str, Any]:
        auth_value = "none" if self._auth_mode == "none" else "bearer_token"
        endpoints: list[dict[str, str]] = [
            {"path": "/healthz", "auth": "none", "kind": "liveness"},
            {"path": "/readyz", "auth": "none", "kind": "readiness"},
            {"path": "/health", "auth": auth_value, "kind": "summary"},
            {"path": "/obs_services", "auth": auth_value, "kind": "discovery"},
            {"path": "/api_health", "auth": auth_value, "kind": "api_rollup"},
            {"path": "/endpoint_health", "auth": auth_value, "kind": "endpoint_rollup"},
            {"path": "/auth_health", "auth": auth_value, "kind": "auth"},
        ]
        if self._auth_mode != "none":
            endpoints.append({"path": "/my_health", "auth": "authenticated_self", "kind": "self"})
        return {
            "status": "ok",
            "endpoints": endpoints,
            "extensions": ["zebra_day.observability_v1"],
            "dependencies": {
                "configured_services": [],
                "observed_services": [],
            },
            "observed_at": self._started_at,
        }

    def projection(self, *, observed_at: str | None = None, detail: str | None = None) -> ProjectionMetadata:
        seen_at = observed_at or self._started_at
        return ProjectionMetadata(
            state="ready",
            stale=False,
            observed_at=seen_at,
            last_synced_at=seen_at,
            detail=detail,
        )

    def record_http_request(
        self,
        *,
        method: str,
        route_template: str,
        status_code: int,
        duration_ms: float,
    ) -> None:
        family = self._classify_family(route_template)
        key = (method.upper(), route_template)
        endpoint = self._endpoint_rollups.setdefault(
            key,
            EndpointRollup(method=method.upper(), route_template=route_template),
        )
        endpoint.record(status_code=status_code, duration_ms=duration_ms)
        family_rollup = self._family_rollups.setdefault(family, FamilyRollup(family=family))
        family_rollup.record(status_code=status_code, duration_ms=duration_ms)

    def record_auth_event(
        self,
        *,
        status: str,
        mode: str,
        detail: str,
        principal_email: str = "",
    ) -> None:
        event = {
            "status": status,
            "mode": mode,
            "detail": detail,
            "principal_email": principal_email,
            "observed_at": _utcnow(),
        }
        self._auth_recent.appendleft(event)
        self._auth_status_counts[status] += 1

    def obs_services_snapshot(self) -> tuple[ProjectionMetadata, dict[str, Any]]:
        snapshot = dict(self._obs_services_snapshot)
        snapshot["dependencies"] = dict(snapshot.get("dependencies") or {})
        return self.projection(observed_at=str(snapshot.get("observed_at") or self._started_at)), snapshot

    def health(self) -> tuple[ProjectionMetadata, dict[str, Any]]:
        payload = {
            "status": "ok",
            "checks": {
                "process": {"status": "ok", "started_at": self._started_at},
                "database": {
                    "status": "not_applicable",
                    "latency_ms": None,
                    "detail": "zebra_day does not use a database",
                    "observed_at": self._started_at,
                },
                "auth": {
                    "status": "ok" if self._auth_mode == "cognito" else "not_configured",
                    "mode": self._auth_mode,
                    "cognito_configured": self._auth_mode == "cognito",
                    "observed_at": self._started_at,
                },
            },
        }
        return self.projection(observed_at=self._started_at), payload

    def api_health(self) -> tuple[ProjectionMetadata, list[dict[str, Any]]]:
        observed_at = max((item.observed_at or self._started_at) for item in self._family_rollups.values()) if self._family_rollups else self._started_at
        families = [item.to_dict() for item in sorted(self._family_rollups.values(), key=lambda rollup: rollup.family)]
        return self.projection(observed_at=observed_at), families

    def endpoint_health(self, *, offset: int, limit: int) -> tuple[ProjectionMetadata, dict[str, Any]]:
        items = [item.to_dict() for item in sorted(self._endpoint_rollups.values(), key=lambda rollup: (rollup.method, rollup.route_template))]
        observed_at = max((item.get("observed_at") or self._started_at) for item in items) if items else self._started_at
        page = items[offset : offset + limit]
        return self.projection(observed_at=observed_at), {
            "total": len(items),
            "offset": offset,
            "limit": limit,
            "items": page,
        }

    def auth_health(self) -> tuple[ProjectionMetadata, dict[str, Any]]:
        recent = list(self._auth_recent)
        recent_user_count = len(
            {
                str(item.get("principal_email") or "").strip()
                for item in recent
                if str(item.get("principal_email") or "").strip()
            }
        )
        observed_at = recent[0]["observed_at"] if recent else self._started_at
        payload = {
            "status": "ok",
            "mode": self._auth_mode,
            "cognito_configured": self._auth_mode == "cognito",
            "cognito_domain": "",
            "user_pool_id": "",
            "app_client_id_present": self._auth_mode == "cognito",
            "recent": recent,
            "status_counts": dict(self._auth_status_counts),
            "sessions": {
                "supported": self._auth_mode == "cognito",
                "active_session_count": None,
                "recent_user_count": recent_user_count if self._auth_mode == "cognito" else None,
                "observed_at": observed_at,
            },
            "observed_at": observed_at,
        }
        return self.projection(observed_at=observed_at), payload

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
        if normalized in {"/health", "/obs_services", "/api_health", "/endpoint_health", "/auth_health", "/my_health"}:
            return "observability"
        if normalized.startswith("/api/v1"):
            return "api"
        return "ui"


def build_health_payload(request: Request, *, projection: ProjectionMetadata, health_snapshot: dict[str, Any]) -> dict[str, Any]:
    payload = base_frame(request, status=str(health_snapshot.get("status") or "unknown"))
    payload["checks"] = dict(health_snapshot.get("checks") or {})
    return _with_projection(payload, projection)


def build_obs_services_payload(request: Request, *, projection: ProjectionMetadata, snapshot: dict[str, Any]) -> dict[str, Any]:
    payload = base_frame(request, status=str(snapshot.get("status") or "ok"))
    payload["endpoints"] = list(snapshot.get("endpoints") or [])
    payload["extensions"] = list(snapshot.get("extensions") or [])
    payload["dependencies"] = dict(snapshot.get("dependencies") or {})
    return _with_projection(payload, projection)


def build_api_health_payload(request: Request, *, projection: ProjectionMetadata, families: list[dict[str, Any]]) -> dict[str, Any]:
    payload = base_frame(request, status="ok")
    payload["families"] = families
    return _with_projection(payload, projection)


def build_endpoint_health_payload(
    request: Request,
    *,
    projection: ProjectionMetadata,
    total: int,
    offset: int,
    limit: int,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    payload = base_frame(request, status="ok")
    payload["page"] = {"total": total, "offset": offset, "limit": limit}
    payload["items"] = items
    return _with_projection(payload, projection)


def build_auth_health_payload(request: Request, *, projection: ProjectionMetadata, auth_rollup: dict[str, Any]) -> dict[str, Any]:
    payload = base_frame(request, status=str(auth_rollup.get("status") or "unknown"))
    payload["auth"] = {
        "mode": str(auth_rollup.get("mode") or ""),
        "cognito_configured": bool(auth_rollup.get("cognito_configured", False)),
        "cognito_domain": str(auth_rollup.get("cognito_domain") or ""),
        "user_pool_id": str(auth_rollup.get("user_pool_id") or ""),
        "app_client_id_present": bool(auth_rollup.get("app_client_id_present", False)),
        "recent": list(auth_rollup.get("recent") or []),
        "status_counts": dict(auth_rollup.get("status_counts") or {}),
        "sessions": dict(auth_rollup.get("sessions") or {}),
    }
    return _with_projection(payload, projection)


def build_my_health_payload(request: Request) -> dict[str, Any]:
    user_claims = getattr(request.state, "user", None)
    if not isinstance(user_claims, dict):
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = base_frame(request, status="ok")
    roles = user_claims.get("cognito:groups") or []
    if isinstance(roles, str):
        roles = [roles]
    payload["principal"] = {
        "subject": str(user_claims.get("sub") or ""),
        "email": str(user_claims.get("email") or ""),
        "name": str(user_claims.get("name") or ""),
        "roles": list(roles),
        "auth_mode": "cognito",
        "expires_at": None,
        "service_principal": False,
    }
    return payload
