from __future__ import annotations

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
        if record.name == "lsmc.access" and record.getMessage() == "Request completed"
    ]
    assert records
    latest = records[-1]
    assert latest.service_id == "zebra-day"
    assert latest.status == 200
    assert latest.status_code == 200
    assert latest.route == "/ping"
    assert latest.method == "GET"
    assert latest.duration_ms >= 0
    assert latest.elapsed_ms >= 0
