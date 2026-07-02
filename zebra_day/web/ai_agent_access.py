"""Validation for Kahlo-issued read-only AI-agent tokens."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import Request

AI_AGENT_TOKEN_PREFIX = "kahlo_ai_"


@dataclass(frozen=True)
class EndpointSpec:
    endpoint_id: str
    method: str
    path_template: str


@dataclass(frozen=True)
class ValidatedAgentAccess:
    token_id: str
    agent_id: str
    issued_by_email: str
    endpoint_id: str
    expires_at: str


class AgentTokenError(RuntimeError):
    def __init__(self, detail: str, *, status_code: int = 401) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


ENDPOINT_CATALOG: tuple[EndpointSpec, ...] = (
    EndpointSpec("zebra.labs.list", "GET", "/api/v1/labs"),
    EndpointSpec("zebra.config.read", "GET", "/api/v1/config"),
)


def is_ai_agent_token(token: str) -> bool:
    return str(token or "").startswith(AI_AGENT_TOKEN_PREFIX)


def _truthy_env(name: str) -> bool:
    return str(os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _template_matches(template: str, path: str) -> bool:
    template_parts = [part for part in template.strip("/").split("/") if part]
    path_parts = [part for part in path.strip("/").split("/") if part]
    if len(template_parts) != len(path_parts):
        return False
    for template_part, path_part in zip(template_parts, path_parts, strict=True):
        if template_part.startswith("{") and template_part.endswith("}"):
            if not path_part:
                return False
            continue
        if template_part != path_part:
            return False
    return True


def _endpoint_id_for_request(method: str, path: str) -> str:
    resolved_method = str(method or "").upper()
    resolved_path = str(path or "").split("?", 1)[0].rstrip("/") or "/"
    for spec in ENDPOINT_CATALOG:
        if spec.method == resolved_method and _template_matches(spec.path_template, resolved_path):
            return spec.endpoint_id
    raise AgentTokenError("AI-agent token is not authorized for this endpoint", status_code=403)


def _parse_expiry(value: str) -> datetime:
    raw = str(value or "").strip()
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _load_grants(path: Path) -> list[dict[str, Any]]:
    if not path.is_absolute():
        raise AgentTokenError("AI-agent grant store path must be absolute", status_code=500)
    if not path.exists():
        raise AgentTokenError("AI-agent grant store is missing", status_code=500)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AgentTokenError("AI-agent grant store is malformed", status_code=500) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("tokens"), list):
        raise AgentTokenError("AI-agent grant store must contain a tokens list", status_code=500)
    return [record for record in payload["tokens"] if isinstance(record, dict)]


def validate_ai_agent_request(request: Request, token: str) -> ValidatedAgentAccess:
    if not is_ai_agent_token(token):
        raise AgentTokenError("Not an AI-agent token")
    if not _truthy_env("LSMC_AI_AGENT_ACCESS_ENABLED"):
        raise AgentTokenError("AI-agent token access is not enabled", status_code=503)
    raw_path = str(os.environ.get("LSMC_AI_AGENT_GRANTS_PATH") or "").strip()
    if not raw_path:
        raise AgentTokenError("LSMC_AI_AGENT_GRANTS_PATH is required", status_code=500)

    endpoint_id = _endpoint_id_for_request(request.method, request.url.path)
    token_digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    for record in _load_grants(Path(raw_path)):
        if not secrets.compare_digest(str(record.get("token_hash") or ""), token_digest):
            continue
        if record.get("revoked_at"):
            raise AgentTokenError("AI-agent token has been revoked")
        expires_at = _parse_expiry(str(record.get("expires_at") or ""))
        if datetime.now(UTC) >= expires_at:
            raise AgentTokenError("AI-agent token has expired")
        endpoint_ids = [str(item) for item in record.get("endpoint_ids") or []]
        if endpoint_id not in endpoint_ids:
            raise AgentTokenError(
                "AI-agent token is not authorized for this endpoint", status_code=403
            )
        validated = ValidatedAgentAccess(
            token_id=str(record.get("token_id") or ""),
            agent_id=str(record.get("agent_id") or ""),
            issued_by_email=str(record.get("issued_by_email") or ""),
            endpoint_id=endpoint_id,
            expires_at=str(record.get("expires_at") or ""),
        )
        request.state.auth_mode = "ai_agent_token"
        request.state.agent_id = validated.agent_id
        request.state.authorized_by_email = validated.issued_by_email
        request.state.agent_token_id = validated.token_id
        request.state.agent_endpoint_id = validated.endpoint_id
        return validated
    raise AgentTokenError("AI-agent token is unknown")
