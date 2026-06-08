from __future__ import annotations

import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from zebra_day.web.middleware import RequestLoggingMiddleware


def test_request_logging_middleware_uses_common_access_logger(caplog) -> None:
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/ping")
    def ping() -> dict[str, bool]:
        return {"ok": True}

    with caplog.at_level(logging.INFO, logger="lsmc.access"):
        response = TestClient(app).get("/ping")

    assert response.status_code == 200
    records = [
        record
        for record in caplog.records
        if record.name == "lsmc.access"
    ]
    assert records
    latest = json.loads(records[-1].getMessage())
    assert latest["event"] == "request_completed"
    assert latest["service_id"] == "zebra-day"
    assert latest["request_id"]
    assert latest["correlation_id"]
    assert latest["actor"] is None
    assert latest["ai_agent_id"] is None
    assert latest["authorizing_human"] is None
    assert latest["ip"] == "testclient"
    assert latest["method"] == "GET"
    assert latest["path"] == "/ping"
    assert latest["route_template"] == "/ping"
    assert latest["status"] == 200
    assert latest["duration_ms"] >= 0
    assert latest["denial_reason"] is None
    assert latest["auth_mode"] is None
