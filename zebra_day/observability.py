"""Minimal observability contract support for zebra_day."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import Request

from zebra_day import __version__
from zebra_day.settings import ZebraDaySettings

CONTRACT_VERSION = "v3"
SERVICE_NAME = "zebra-day"


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class ProjectionMetadata:
    name: str
    state: str = "ready"
    observed_at: str = ""

    def model_dump(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state,
            "observed_at": self.observed_at or _utcnow(),
        }


class ZebraDayObservability:
    """Small in-process rollups for the required endpoints."""

    def __init__(self, settings: ZebraDaySettings) -> None:
        self.settings = settings
        self.instance_id = str(uuid.uuid4())
        self.route_templates: set[str] = set()

    def record_route(self, path_template: str) -> None:
        self.route_templates.add(path_template)

    def projection(self, name: str) -> ProjectionMetadata:
        return ProjectionMetadata(name=name, observed_at=_utcnow())

    def base_frame(self, request: Request, *, status: str) -> dict[str, Any]:
        return {
            "contract_version": CONTRACT_VERSION,
            "service": SERVICE_NAME,
            "environment": self.settings.tapdb_env or os.environ.get("ENVIRONMENT") or "dev",
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
        frame["projection"] = self.projection(name).model_dump()
        return frame
