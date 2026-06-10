from __future__ import annotations

import http.client
import socket
import time

import pytest

from zebra_day import printer_protocol
from zebra_day.cmd_mgr import ZebraPrinter, clear_printer_cache, get_cached_status
from zebra_day.simulator import (
    PrinterProfile,
    SimulatedPrinter,
    SimulatorManager,
    _build_zpl_response,
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_printer_profile_and_raw_zpl_responses():
    profile = PrinterProfile(
        model="ZD620-203dpi ZPL",
        serial="SIM4242",
        firmware="V99.99",
        paused=True,
        paper_out=True,
        ribbon_out=True,
        head_up=True,
        label_count=77,
        total_inches=999,
    )

    assert profile.friendly_name == "Zebra ZD620"
    assert "ZD620-203dpi ZPL,V99.99,8,8192KB" in (_build_zpl_response("~HI", profile) or "")
    assert "SIM4242" in (_build_zpl_response("~HQSN", profile) or "")
    assert "0000 0000 0000 0000" in (_build_zpl_response("~HQES", profile) or "")
    assert "LABEL: 77" in (_build_zpl_response("~HQOD", profile) or "")
    assert "0000,0,1,0000,000,1,1,1" in (_build_zpl_response("~HS", profile) or "")
    assert "PRINTER CONFIGURATION" in (_build_zpl_response("^XA^HH^XZ", profile) or "")
    assert _build_zpl_response("~UNKNOWN", profile) is None


def test_simulated_printer_serves_zpl_http_and_status_queries():
    zpl_port = _free_port()
    http_port = _free_port()
    profile = PrinterProfile(
        model="ZD620-203dpi <ZPL>",
        serial="SIM2001",
        friendly_name="Printer <Lab>",
        paused=True,
        paper_out=True,
        ribbon_out=True,
        head_up=True,
        label_count=88,
        total_inches=1234,
    )
    printer = SimulatedPrinter("127.0.0.1", zpl_port=zpl_port, http_port=http_port, profile=profile)
    try:
        printer.start()
        time.sleep(0.05)

        assert printer.running is True
        assert printer.info()["serial"] == "SIM2001"

        device = ZebraPrinter("127.0.0.1", port=zpl_port)
        assert device.send_command("~HI")
        assert device.get_configuration()

        host_id = device.get_host_identification()
        serial = device.get_serial_number()
        error_status = device.get_error_status()
        odometer = device.get_odometer()
        host_status = device.get_host_status()
        full_status = device.get_full_status()

        assert host_id == {
            "model": "ZD620-203dpi <ZPL>",
            "firmware": "V84.20.21Z",
            "dpi": "8",
            "memory": "8192KB",
            "options": "",
        }
        assert serial == "SIM2001"
        assert error_status == {"errors": [], "warnings": [], "raw": "0000 0000 0000 0000"}
        assert odometer["label_count"] == 88
        assert odometer["total_inches"] == 1234
        assert host_status["paused"] is True
        assert host_status["paper_out"] is True
        assert host_status["head_up"] is True
        assert host_status["ribbon_out"] is True
        assert full_status["online"] is True
        assert full_status["serial"] == "SIM2001"
        assert full_status["label_count"] == 88

        printer_protocol.send_zpl_code("^XA^XZ", "127.0.0.1", printer_port=zpl_port)

        conn = http.client.HTTPConnection("127.0.0.1", port=http_port, timeout=1.0)
        conn.request("GET", "/")
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        conn.close()

        assert response.status == 200
        assert "Printer &lt;Lab&gt;" in body
        assert "ZD620-203dpi &lt;ZPL&gt;" in body

        http_probe = printer_protocol._http_probe("127.0.0.1", http_port, 1.0)
        assert http_probe == {
            "printer_name": "",
            "model": "",
            "serial": "",
            "source": f"http({http_port})",
            "http_verified": True,
            "http_status": 200,
        }
    finally:
        printer.stop()

    assert printer.running is False


def test_simulator_manager_lifecycle_and_duplicate_guard():
    mgr = SimulatorManager()
    first_zpl = _free_port()
    first_http = _free_port()
    second_zpl = _free_port()
    second_http = _free_port()
    try:
        first = mgr.start_printer(
            host="127.0.0.1",
            zpl_port=first_zpl,
            http_port=first_http,
            profile=PrinterProfile(serial="SIM-FIRST"),
        )
        assert mgr.get("127.0.0.1", first_zpl) is first
        assert mgr.list_printers()[0]["serial"] == "SIM-FIRST"

        with pytest.raises(RuntimeError):
            mgr.start_printer(
                host="127.0.0.1",
                zpl_port=first_zpl,
                http_port=first_http,
                profile=PrinterProfile(serial="SIM-DUP"),
            )

        mgr.start_printer(
            host="127.0.0.1",
            zpl_port=second_zpl,
            http_port=second_http,
            profile=PrinterProfile(serial="SIM-SECOND"),
        )
        assert mgr.stop_printer("127.0.0.1", first_zpl) is True
        assert mgr.stop_printer("127.0.0.1", first_zpl) is False
        assert mgr.stop_all() == 1
    finally:
        mgr.stop_all()


def test_get_cached_status_respects_ttl_and_force_refresh(monkeypatch):
    clear_printer_cache()
    responses = iter(
        [
            {"online": True, "serial": "A"},
            {"online": True, "serial": "B"},
            {"online": False, "serial": "C"},
        ]
    )
    now_values = iter([100.0, 105.0, 106.0, 200.0])

    monkeypatch.setattr("zebra_day.cmd_mgr.time.time", lambda: next(now_values))
    monkeypatch.setattr(
        ZebraPrinter,
        "get_full_status",
        lambda self, timeout=ZebraPrinter.DEFAULT_TIMEOUT: next(responses),
    )

    first = get_cached_status("192.168.1.10")
    cached = get_cached_status("192.168.1.10")
    forced = get_cached_status("192.168.1.10", force_refresh=True)
    expired = get_cached_status("192.168.1.10")

    assert first == {"online": True, "serial": "A"}
    assert cached is first
    assert forced == {"online": True, "serial": "B"}
    assert expired == {"online": False, "serial": "C"}


def test_build_zpl_render_preview_and_discover(monkeypatch, tmp_path):
    rendered = printer_protocol.build_zpl(
        "^XA^FD{uid_barcode}|{label_zpl_style}|{rec_date}^XZ",
        template_name="tube_2inX1in",
        uid_barcode="UID-7",
    )
    assert "UID-7" in rendered
    assert "tube_2inX1in" in rendered

    with pytest.raises(ValueError, match="missing field"):
        printer_protocol.build_zpl("^XA^FD{missing_field}^XZ")

    output_path = tmp_path / "preview.png"
    monkeypatch.setattr(
        printer_protocol,
        "render_zpl_to_png",
        lambda zpl, path: path.write_text(f"rendered:{zpl}", encoding="utf-8"),
    )
    assert printer_protocol.render_zpl_preview("^XA^XZ", output_path) == output_path
    assert output_path.read_text(encoding="utf-8") == "rendered:^XA^XZ"

    progress: list[dict[str, object]] = []

    class _FakePrinter:
        def __init__(self, ip_address: str, port: int = 9100) -> None:
            self.ip_address = ip_address
            self.port = port

        def get_host_identification(self, timeout: float = 0.0):
            if self.ip_address.endswith(".10"):
                return {"model": "ZD621"}
            return {}

        def get_serial_number(self, timeout: float = 0.0):
            if self.ip_address.endswith(".10"):
                return "SER-ZPL"
            return None

    monkeypatch.setattr(printer_protocol, "ZebraPrinter", _FakePrinter)
    monkeypatch.setattr(
        printer_protocol,
        "_http_probe",
        lambda ip_address, port, timeout: (
            {
                "printer_name": "Web Printer",
                "model": "ZT411",
                "serial": "SER-HTTP",
                "source": f"http({port})",
            }
            if ip_address.endswith(".20")
            else None
        ),
    )

    results = printer_protocol.discover_printers(
        ip_stub="192.168.50",
        scan_wait=0.001,
        scan_http_port=18080,
        progress_callback=progress.append,
    )

    assert [row["ip_address"] for row in results] == ["192.168.50.10", "192.168.50.20"]
    assert results[0]["model"] == "ZD621"
    assert results[0]["serial"] == "SER-ZPL"
    assert results[0]["notes"] == "zpl"
    assert results[1]["printer_name"] == "Web Printer"
    assert results[1]["notes"] == "http(18080)"
    assert progress[0]["kind"] == "checking"
    assert any(event["kind"] == "found" and event["ip"] == "192.168.50.10" for event in progress)
    assert any(event["kind"] == "found" and event["ip"] == "192.168.50.20" for event in progress)
    assert any(
        event["kind"] == "checked" and event["ip"] == "192.168.50.20" and event["open"]
        for event in progress
    )
    assert progress[-1] == {"kind": "done", "checked": 254, "total": 254}

    with pytest.raises(ValueError, match="must not end with a trailing dot"):
        printer_protocol.discover_printers(ip_stub="192.168.50.", scan_wait=0.01)


def test_http_probe_reports_requested_http_open_pages(monkeypatch):
    class _Response:
        status = 200

        def read(self, size: int = -1) -> bytes:
            return b"<html>ordinary printer</html>"

    class _Connection:
        def __init__(self, host, port, timeout) -> None:
            self.host = host
            self.port = port
            self.timeout = timeout

        def request(self, method, path) -> None:
            assert method == "GET"
            assert path == "/"

        def getresponse(self):
            return _Response()

        def close(self) -> None:
            return None

    monkeypatch.setattr(printer_protocol.http.client, "HTTPConnection", _Connection)
    assert printer_protocol._http_probe("192.168.1.5", 80, 0.1) == {
        "printer_name": "HTTP printer endpoint",
        "model": "HTTP endpoint",
        "serial": "",
        "source": "http(80)",
        "http_verified": False,
        "http_status": 200,
    }


def test_discover_printers_respects_minimum_wait_per_ip(monkeypatch):
    timeline = [100.0]
    sleeps: list[float] = []

    def fake_monotonic() -> float:
        return timeline[0]

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        timeline[0] += seconds

    class _FakePrinter:
        def __init__(self, ip_address: str, port: int = 9100) -> None:
            self.ip_address = ip_address
            self.port = port

        def get_host_identification(self, timeout: float = 0.0):
            return {}

        def get_serial_number(self, timeout: float = 0.0):
            return None

    monkeypatch.setattr(printer_protocol, "monotonic", fake_monotonic)
    monkeypatch.setattr(printer_protocol, "sleep", fake_sleep)
    monkeypatch.setattr(printer_protocol, "ZebraPrinter", _FakePrinter)
    monkeypatch.setattr(printer_protocol, "_http_probe", lambda ip_address, port, timeout: None)

    printer_protocol.discover_printers(ip_stub="192.168.60", scan_wait=0.2)

    assert len(sleeps) == 254
    assert sleeps[:3] == [pytest.approx(0.2), pytest.approx(0.2), pytest.approx(0.2)]
