from __future__ import annotations

from dataclasses import replace
from typing import Any

from zebra_day.client import PrinterRecord


class FakeFleetRepository:
    def __init__(self) -> None:
        self.printers: dict[tuple[str, str], PrinterRecord] = {}
        self.templates: dict[str, dict[str, Any]] = {}
        self.label_profiles: dict[str, dict[str, Any]] = {}
        self.observations: list[dict[str, Any]] = []
        self.drifts: list[dict[str, Any]] = []
        self.print_jobs: list[dict[str, Any]] = []

    def list_labs(self) -> list[str]:
        return sorted({lab for lab, _printer_id in self.printers})

    def list_printers(self, lab: str | None = None) -> list[PrinterRecord]:
        rows = list(self.printers.values())
        if lab is not None:
            rows = [row for row in rows if row.lab == lab]
        return sorted(rows, key=lambda row: (row.lab, row.printer_id))

    def get_printer(self, lab: str, printer_id: str) -> PrinterRecord | None:
        return self.printers.get((lab, printer_id))

    def get_printer_by_euid(self, printer_euid: str) -> PrinterRecord | None:
        for printer in self.printers.values():
            if printer.euid == printer_euid:
                return printer
        return None

    def upsert_printer(self, printer: PrinterRecord) -> PrinterRecord:
        if not printer.euid:
            printer = replace(printer, euid=f"{printer.lab}-printer-{len(self.printers) + 1:04d}")
        self.printers[(printer.lab, printer.printer_id)] = printer
        return printer

    def list_templates(self) -> list[dict[str, Any]]:
        return [self.templates[name] for name in sorted(self.templates)]

    def get_template(self, template_name: str) -> dict[str, Any] | None:
        return self.templates.get(template_name)

    def upsert_template(
        self, template_name: str, zpl_content: str, source: str = "package"
    ) -> None:
        self.templates[template_name] = {
            "template_name": template_name,
            "zpl_content": zpl_content,
            "source": source,
            "euid": "",
        }

    def list_label_profiles(self) -> list[dict[str, Any]]:
        return [self.label_profiles[name] for name in sorted(self.label_profiles)]

    def upsert_label_profile(self, profile_name: str, payload: dict[str, Any]) -> None:
        merged = {"profile_name": profile_name, **payload}
        self.label_profiles[profile_name] = merged

    def get_label_profile(self, profile_name: str) -> dict[str, Any] | None:
        return self.label_profiles.get(profile_name)

    def record_observation(self, payload: dict[str, Any]) -> None:
        self.observations.append(dict(payload))

    def record_drift(self, payload: dict[str, Any]) -> None:
        self.drifts.append(dict(payload))

    def create_print_job(self, payload: dict[str, Any]) -> None:
        self.print_jobs.append(dict(payload))


def sample_repository() -> FakeFleetRepository:
    repository = FakeFleetRepository()
    repository.upsert_template(
        "tube_2inX1in", "^XA^FO30,30^FD{uid_barcode}^FS^XZ", source="package"
    )
    repository.upsert_label_profile(
        "tube_2inX1in",
        {
            "profile_name": "tube_2inX1in",
            "template_name": "tube_2inX1in",
            "managed_by": "zebra-day",
            "euid": "",
        },
    )
    repository.upsert_printer(
        PrinterRecord(
            printer_id="printer-1",
            lab="default",
            ip_address="192.168.1.50",
            printer_name="Bench Printer",
            model="ZD620",
            serial="SER123",
            label_profiles=["tube_2inX1in"],
            default_label_profile="tube_2inX1in",
            euid="default-printer-0001",
        )
    )
    return repository
