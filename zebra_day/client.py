"""TapDB-backed zebra_day clients."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import httpx

from zebra_day import paths as xdg
from zebra_day.logging_config import get_logger
from zebra_day.optional_deps import import_from_sibling
from zebra_day.printer_protocol import (
    build_zpl,
    discover_printers,
    render_zpl_preview,
    send_zpl_code,
)
from zebra_day.settings import ZebraDaySettings

_log = get_logger(__name__)

PRINTER_TEMPLATE_CODE = "zebra-day/fleet/printer/1.0/"
LABEL_PROFILE_TEMPLATE_CODE = "zebra-day/labels/profile/1.0/"
LABEL_TEMPLATE_TEMPLATE_CODE = "zebra-day/labels/template/1.0/"
OBSERVATION_TEMPLATE_CODE = "zebra-day/fleet/printer-observation/1.0/"
DRIFT_TEMPLATE_CODE = "zebra-day/fleet/metadata-drift/1.0/"
PRINT_JOB_TEMPLATE_CODE = "zebra-day/printing/print-job/1.0/"
PACKAGE_TEMPLATE_PACK = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "tapdb_templates"
    / "zebra_day"
    / "templates.json"
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _stable_name(lab: str, printer_id: str) -> str:
    return f"{lab}/{printer_id}"


def _timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


@dataclass
class PrinterRecord:
    printer_id: str
    lab: str
    ip_address: str
    printer_name: str = ""
    lab_location: str = ""
    manufacturer: str = "zebra"
    model: str = ""
    serial: str = ""
    label_profiles: list[str] | None = None
    default_label_profile: str = ""
    print_method: str = "socket"
    notes: str = ""
    lsmc_euid: str = ""
    state: str = "Unknown"
    status: str = "active"
    discovery_source: str = ""
    device_manifest: dict[str, Any] | None = None
    euid: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "printer_id": self.printer_id,
            "lab": self.lab,
            "ip_address": self.ip_address,
            "printer_name": self.printer_name,
            "lab_location": self.lab_location,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "serial": self.serial,
            "label_profiles": list(self.label_profiles or []),
            "default_label_profile": self.default_label_profile,
            "print_method": self.print_method,
            "notes": self.notes,
            "lsmc_euid": self.lsmc_euid,
            "state": self.state,
            "status": self.status,
            "discovery_source": self.discovery_source,
            "device_manifest": dict(self.device_manifest or {}),
            "euid": self.euid,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> PrinterRecord:
        return cls(
            printer_id=_clean(payload.get("printer_id")),
            lab=_clean(payload.get("lab")),
            ip_address=_clean(payload.get("ip_address")),
            printer_name=_clean(payload.get("printer_name")),
            lab_location=_clean(payload.get("lab_location")),
            manufacturer=_clean(payload.get("manufacturer") or "zebra"),
            model=_clean(payload.get("model")),
            serial=_clean(payload.get("serial")),
            label_profiles=list(payload.get("label_profiles") or []),
            default_label_profile=_clean(payload.get("default_label_profile")),
            print_method=_clean(payload.get("print_method") or "socket"),
            notes=_clean(payload.get("notes")),
            lsmc_euid=_clean(payload.get("lsmc_euid")),
            state=_clean(payload.get("state") or "Unknown"),
            status=_clean(payload.get("status") or "active"),
            discovery_source=_clean(payload.get("discovery_source")),
            device_manifest=dict(payload.get("device_manifest") or {}),
            euid=_clean(payload.get("euid")),
        )


class FleetRepository(Protocol):
    def list_labs(self) -> list[str]: ...
    def list_printers(self, lab: str | None = None) -> list[PrinterRecord]: ...
    def get_printer(self, lab: str, printer_id: str) -> PrinterRecord | None: ...
    def upsert_printer(self, printer: PrinterRecord) -> PrinterRecord: ...
    def list_templates(self) -> list[dict[str, Any]]: ...
    def get_template(self, template_name: str) -> dict[str, Any] | None: ...
    def upsert_template(
        self, template_name: str, zpl_content: str, source: str = "package"
    ) -> None: ...
    def list_label_profiles(self) -> list[dict[str, Any]]: ...
    def upsert_label_profile(self, profile_name: str, payload: dict[str, Any]) -> None: ...
    def get_label_profile(self, profile_name: str) -> dict[str, Any] | None: ...
    def record_observation(self, payload: dict[str, Any]) -> None: ...
    def record_drift(self, payload: dict[str, Any]) -> None: ...
    def create_print_job(self, payload: dict[str, Any]) -> None: ...


class TapDBFleetRepository:
    """TapDB-backed fleet repository."""

    def __init__(self, settings: ZebraDaySettings) -> None:
        self.settings = settings
        if not settings.tapdb_config_path.exists():
            raise FileNotFoundError(f"TapDB config not found: {settings.tapdb_config_path}")
        self._connection = self._build_connection()
        self._tapdb = import_from_sibling("daylily_tapdb", "daylily-tapdb")
        self._template_manager = self._tapdb.TemplateManager()
        self._generic_instance = import_from_sibling(
            "daylily_tapdb.models.instance",
            "daylily-tapdb",
        ).generic_instance
        self._seed_templates()
        self._seed_package_templates()

    def _build_connection(self):
        tapdb_mod = import_from_sibling("daylily_tapdb", "daylily-tapdb")
        db_config_mod = import_from_sibling("daylily_tapdb.cli.db_config", "daylily-tapdb")
        os.environ["TAPDB_CLIENT_ID"] = self.settings.tapdb_client_id
        os.environ["TAPDB_DATABASE_NAME"] = self.settings.tapdb_database_name
        os.environ["TAPDB_ENV"] = self.settings.tapdb_env
        os.environ["TAPDB_CONFIG_PATH"] = str(self.settings.tapdb_config_path)
        cfg = db_config_mod.get_db_config_for_env(self.settings.tapdb_env)
        db_hostname = f"{cfg['host']}:{cfg['port']}"
        return tapdb_mod.TAPDBConnection(
            db_hostname=db_hostname,
            db_user=cfg["user"],
            db_pass=cfg["password"],
            db_name=cfg["database"],
            engine_type=str(cfg.get("engine_type") or "local"),
        )

    def _session(self, *, commit: bool):
        return self._connection.session_scope(commit=commit)

    def _seed_templates(self) -> None:
        if not PACKAGE_TEMPLATE_PACK.exists():
            return
        loader = import_from_sibling("daylily_tapdb.templates.loader", "daylily-tapdb")
        with self._session(commit=True) as session:
            templates = (
                json.loads(PACKAGE_TEMPLATE_PACK.read_text(encoding="utf-8")).get("templates") or []
            )
            loader.seed_templates(session, templates, overwrite=False)

    def _seed_package_templates(self) -> None:
        package_dir = Path(__file__).resolve().parent / "etc" / "label_styles"
        if not package_dir.exists():
            return
        for path in sorted(package_dir.glob("*.zpl")):
            self.upsert_template(path.stem, path.read_text(encoding="utf-8"), source="package")
            self.upsert_label_profile(
                path.stem,
                {"profile_name": path.stem, "template_name": path.stem, "managed_by": "zebra-day"},
            )

    def _template_for_code(self, session, code: str):
        template = self._template_manager.get_template(session, code)
        if template is None:
            raise RuntimeError(f"TapDB template not seeded: {code}")
        return template

    def _query_instances(self, session, subtype: str):
        return (
            session.query(self._generic_instance)
            .filter(
                self._generic_instance.category == "zebra-day",
                self._generic_instance.subtype == subtype,
                self._generic_instance.is_deleted.is_(False),
            )
            .all()
        )

    def _upsert_instance(
        self,
        *,
        template_code: str,
        subtype: str,
        name: str,
        payload: dict[str, Any],
        bstatus: str = "active",
    ) -> dict[str, Any]:
        with self._session(commit=True) as session:
            existing = (
                session.query(self._generic_instance)
                .filter(
                    self._generic_instance.category == "zebra-day",
                    self._generic_instance.subtype == subtype,
                    self._generic_instance.name == name,
                    self._generic_instance.is_deleted.is_(False),
                )
                .first()
            )
            if existing is None:
                template = self._template_for_code(session, template_code)
                existing = self._generic_instance(
                    name=name,
                    polymorphic_discriminator=template.instance_polymorphic_identity
                    or template.polymorphic_discriminator.replace("_template", "_instance"),
                    category=template.category,
                    type=template.type,
                    subtype=template.subtype,
                    version=template.version,
                    template_uid=template.uid,
                    json_addl=dict(payload),
                    bstatus=bstatus,
                    is_singleton=False,
                )
                session.add(existing)
                session.flush()
            else:
                existing.json_addl = dict(payload)
                existing.bstatus = bstatus
                session.flush()

            stored = dict(existing.json_addl or {})
            stored["euid"] = _clean(getattr(existing, "euid", ""))
            return stored

    def list_labs(self) -> list[str]:
        with self._session(commit=False) as session:
            labs = {
                _clean((item.json_addl or {}).get("lab"))
                for item in self._query_instances(session, "printer")
            }
            return sorted(lab for lab in labs if lab)

    def list_printers(self, lab: str | None = None) -> list[PrinterRecord]:
        with self._session(commit=False) as session:
            items: list[PrinterRecord] = []
            for instance in self._query_instances(session, "printer"):
                payload = dict(instance.json_addl or {})
                payload["euid"] = _clean(getattr(instance, "euid", ""))
                record = PrinterRecord.from_payload(payload)
                if lab is None or record.lab == lab:
                    items.append(record)
            return sorted(items, key=lambda item: (item.lab, item.printer_id))

    def get_printer(self, lab: str, printer_id: str) -> PrinterRecord | None:
        with self._session(commit=False) as session:
            instance = (
                session.query(self._generic_instance)
                .filter(
                    self._generic_instance.category == "zebra-day",
                    self._generic_instance.subtype == "printer",
                    self._generic_instance.name == _stable_name(lab, printer_id),
                    self._generic_instance.is_deleted.is_(False),
                )
                .first()
            )
            if instance is None:
                return None
            payload = dict(instance.json_addl or {})
            payload["euid"] = _clean(getattr(instance, "euid", ""))
            return PrinterRecord.from_payload(payload)

    def upsert_printer(self, printer: PrinterRecord) -> PrinterRecord:
        payload = printer.to_payload()
        stored = self._upsert_instance(
            template_code=PRINTER_TEMPLATE_CODE,
            subtype="printer",
            name=_stable_name(printer.lab, printer.printer_id),
            payload=payload,
            bstatus=printer.status or "active",
        )
        payload["euid"] = stored.get("euid", "")
        return PrinterRecord.from_payload(payload)

    def list_templates(self) -> list[dict[str, Any]]:
        with self._session(commit=False) as session:
            rows: list[dict[str, Any]] = []
            for instance in self._query_instances(session, "template"):
                payload = dict(instance.json_addl or {})
                payload["euid"] = _clean(getattr(instance, "euid", ""))
                if _clean(payload.get("source")) == "deleted" or not _clean(
                    payload.get("zpl_content")
                ):
                    continue
                rows.append(payload)
            return sorted(rows, key=lambda item: _clean(item.get("template_name")))

    def get_template(self, template_name: str) -> dict[str, Any] | None:
        with self._session(commit=False) as session:
            instance = (
                session.query(self._generic_instance)
                .filter(
                    self._generic_instance.category == "zebra-day",
                    self._generic_instance.subtype == "template",
                    self._generic_instance.name == template_name,
                    self._generic_instance.is_deleted.is_(False),
                )
                .first()
            )
            if instance is None:
                return None
            payload = dict(instance.json_addl or {})
            payload["euid"] = _clean(getattr(instance, "euid", ""))
            if _clean(payload.get("source")) == "deleted" or not _clean(payload.get("zpl_content")):
                return None
            return payload

    def upsert_template(
        self, template_name: str, zpl_content: str, source: str = "package"
    ) -> None:
        self._upsert_instance(
            template_code=LABEL_TEMPLATE_TEMPLATE_CODE,
            subtype="template",
            name=template_name,
            payload={
                "template_name": template_name,
                "zpl_content": zpl_content,
                "source": source,
            },
        )

    def list_label_profiles(self) -> list[dict[str, Any]]:
        with self._session(commit=False) as session:
            rows: list[dict[str, Any]] = []
            for instance in self._query_instances(session, "profile"):
                payload = dict(instance.json_addl or {})
                payload["euid"] = _clean(getattr(instance, "euid", ""))
                rows.append(payload)
            return sorted(rows, key=lambda item: _clean(item.get("profile_name")))

    def upsert_label_profile(self, profile_name: str, payload: dict[str, Any]) -> None:
        full_payload = dict(payload)
        full_payload.setdefault("profile_name", profile_name)
        self._upsert_instance(
            template_code=LABEL_PROFILE_TEMPLATE_CODE,
            subtype="profile",
            name=profile_name,
            payload=full_payload,
        )

    def get_label_profile(self, profile_name: str) -> dict[str, Any] | None:
        with self._session(commit=False) as session:
            instance = (
                session.query(self._generic_instance)
                .filter(
                    self._generic_instance.category == "zebra-day",
                    self._generic_instance.subtype == "profile",
                    self._generic_instance.name == profile_name,
                    self._generic_instance.is_deleted.is_(False),
                )
                .first()
            )
            if instance is None:
                return None
            payload = dict(instance.json_addl or {})
            payload["euid"] = _clean(getattr(instance, "euid", ""))
            return payload

    def record_observation(self, payload: dict[str, Any]) -> None:
        name = (
            f"{_clean(payload.get('lab'))}/{_clean(payload.get('printer_id'))}/{_timestamp_slug()}"
        )
        self._upsert_instance(
            template_code=OBSERVATION_TEMPLATE_CODE,
            subtype="printer-observation",
            name=name,
            payload=dict(payload),
        )

    def record_drift(self, payload: dict[str, Any]) -> None:
        name = (
            f"{_clean(payload.get('lab'))}/"
            f"{_clean(payload.get('printer_id'))}/drift/{_timestamp_slug()}"
        )
        self._upsert_instance(
            template_code=DRIFT_TEMPLATE_CODE,
            subtype="metadata-drift",
            name=name,
            payload=dict(payload),
        )

    def create_print_job(self, payload: dict[str, Any]) -> None:
        job_id = _clean(payload.get("job_id")) or _timestamp_slug()
        self._upsert_instance(
            template_code=PRINT_JOB_TEMPLATE_CODE,
            subtype="print-job",
            name=job_id,
            payload=dict(payload),
            bstatus=_clean(payload.get("status") or "submitted"),
        )


class ZebraDayClient:
    """Direct TapDB client used by the zebra_day service and admin tooling."""

    def __init__(
        self,
        settings: ZebraDaySettings | None = None,
        repository: FleetRepository | None = None,
    ) -> None:
        self.settings = settings or ZebraDaySettings.from_context()
        self.repository = repository or TapDBFleetRepository(self.settings)

    @classmethod
    def from_context(
        cls,
        deployment: str | None = None,
        repository: FleetRepository | None = None,
    ) -> ZebraDayClient:
        return cls(settings=ZebraDaySettings.from_context(deployment), repository=repository)

    def list_labs(self) -> list[str]:
        return self.repository.list_labs()

    def list_printers(self, lab: str | None = None) -> list[PrinterRecord]:
        return self.repository.list_printers(lab)

    def get_printer(self, printer_id: str, lab: str | None = None) -> PrinterRecord | None:
        if lab is not None:
            return self.repository.get_printer(lab, printer_id)
        for candidate in self.repository.list_printers():
            if candidate.printer_id == printer_id:
                return candidate
        return None

    def list_template_records(self) -> list[dict[str, Any]]:
        return self.repository.list_templates()

    def list_templates(self) -> list[str]:
        return sorted(
            _clean(item.get("template_name")) for item in self.repository.list_templates()
        )

    def get_template(self, template_name: str) -> dict[str, Any] | None:
        return self.repository.get_template(template_name)

    def save_template(self, template_name: str, zpl_content: str, *, source: str = "user") -> None:
        self.repository.upsert_template(template_name, zpl_content, source=source)

    def delete_template(self, template_name: str) -> None:
        existing = self.repository.get_template(template_name)
        if existing is None:
            raise KeyError(f"Template not found: {template_name}")
        self.repository.upsert_template(template_name, "", source="deleted")

    def list_label_profiles(self) -> list[dict[str, Any]]:
        return self.repository.list_label_profiles()

    def get_label_profile(self, profile_name: str) -> dict[str, Any] | None:
        return self.repository.get_label_profile(profile_name)

    def _resolve_template_name(self, profile_or_template: str) -> tuple[str, dict[str, Any] | None]:
        profile = self.repository.get_label_profile(profile_or_template)
        if profile is None:
            return profile_or_template, None
        template_name = _clean(profile.get("template_name")) or profile_or_template
        return template_name, profile

    def build_label(
        self,
        *,
        template: str | None = None,
        zpl_content: str | None = None,
        **fields: str,
    ) -> tuple[str, str]:
        if zpl_content:
            return zpl_content, _clean(template)

        template_key = _clean(template)
        if not template_key:
            raise ValueError("A template name or raw zpl_content is required")

        template_name, _profile = self._resolve_template_name(template_key)
        template_record = self.repository.get_template(template_name)
        if template_record is None:
            raise KeyError(f"Template not found: {template_name}")
        zpl_string = build_zpl(
            _clean(template_record.get("zpl_content")),
            template_name=template_key,
            **fields,
        )
        return zpl_string, template_name

    def resolve_print_request(
        self,
        *,
        lab: str,
        printer: str,
        label_zpl_style: str | None = None,
        zpl_content: str | None = None,
        copies: int = 1,
        **fields: str,
    ) -> dict[str, Any]:
        printer_record = self.repository.get_printer(lab, printer)
        if printer_record is None:
            raise KeyError(f"Printer not found: {lab}/{printer}")

        resolved_style = _clean(label_zpl_style) or _clean(printer_record.default_label_profile)
        if not resolved_style:
            profiles = list(printer_record.label_profiles or [])
            if profiles:
                resolved_style = _clean(profiles[0])
        if not resolved_style and not zpl_content:
            raise KeyError(f"No label profile configured for printer: {lab}/{printer}")

        zpl_string, template_name = self.build_label(
            template=resolved_style or None,
            zpl_content=zpl_content,
            **fields,
        )
        return {
            "lab": lab,
            "printer_id": printer_record.printer_id,
            "printer_ip": printer_record.ip_address,
            "printer": printer_record.to_payload(),
            "template_name": template_name,
            "label_style": resolved_style,
            "zpl_content": zpl_string,
            "copies": int(copies),
        }

    def render_label(
        self,
        *,
        template: str | None = None,
        zpl_content: str | None = None,
        **fields: str,
    ) -> tuple[str, str]:
        zpl_string, template_name = self.build_label(
            template=template,
            zpl_content=zpl_content,
            **fields,
        )
        png_filename = f"zpl_render_{template_name or 'custom'}_{_timestamp_slug()}.png"
        png_path = xdg.get_generated_files_dir() / png_filename
        render_zpl_preview(zpl_string, png_path)
        return zpl_string, f"/generated/{png_filename}"

    def print_label(
        self,
        *,
        lab: str,
        printer: str,
        label_zpl_style: str | None = None,
        zpl_content: str | None = None,
        copies: int = 1,
        client_ip: str = "unknown",
        **fields: str,
    ) -> str:
        resolved = self.resolve_print_request(
            lab=lab,
            printer=printer,
            label_zpl_style=label_zpl_style,
            zpl_content=zpl_content,
            copies=copies,
            **fields,
        )
        try:
            for _ in range(int(copies)):
                send_zpl_code(resolved["zpl_content"], resolved["printer_ip"])
            status = "submitted"
        except Exception:
            status = "failed"
            raise
        finally:
            self.repository.create_print_job(
                {
                    "job_id": _timestamp_slug(),
                    "lab": lab,
                    "printer_id": printer,
                    "template": resolved.get("template_name") or "",
                    "copies": copies,
                    "client_ip": client_ip,
                    "status": status,
                    "submitted_at": _utcnow(),
                }
            )
        return str(resolved["zpl_content"])

    def submit_print_job(self, **kwargs: Any) -> str:
        return self.print_label(**kwargs)

    def discover_printers(
        self,
        *,
        ip_stub: str,
        lab: str,
        scan_http_port: int | None = None,
        progress_callback=None,
    ) -> list[PrinterRecord]:
        found: list[PrinterRecord] = []
        for payload in discover_printers(
            ip_stub=ip_stub,
            scan_wait=self.settings.default_scan_wait_seconds,
            scan_http_port=scan_http_port,
            progress_callback=progress_callback,
        ):
            existing = self.repository.get_printer(lab, payload["printer_id"])
            if existing is None:
                record = PrinterRecord(
                    printer_id=_clean(payload.get("printer_id")),
                    lab=lab,
                    ip_address=_clean(payload.get("ip_address")),
                    printer_name=_clean(payload.get("printer_name")),
                    manufacturer="zebra",
                    model=_clean(payload.get("model")),
                    serial=_clean(payload.get("serial")),
                    notes=_clean(payload.get("notes")),
                    status="draft",
                    discovery_source=_clean(payload.get("notes")),
                )
            else:
                merged = existing.to_payload()
                if not _clean(merged.get("model")):
                    merged["model"] = _clean(payload.get("model"))
                if not _clean(merged.get("serial")):
                    merged["serial"] = _clean(payload.get("serial"))
                merged["discovery_source"] = _clean(payload.get("notes"))
                record = PrinterRecord.from_payload(merged)

            stored = self.repository.upsert_printer(record)
            self.repository.record_observation(
                {
                    "lab": lab,
                    "printer_id": stored.printer_id,
                    "ip_address": stored.ip_address,
                    "model": stored.model,
                    "serial": stored.serial,
                    "source": stored.discovery_source or "zpl",
                    "observed_at": _utcnow(),
                }
            )
            found.append(stored)
        return found

    def sync_printer_metadata(self, printer_id: str, lab: str) -> PrinterRecord:
        printer = self.repository.get_printer(lab, printer_id)
        if printer is None:
            raise KeyError(f"Printer not found: {lab}/{printer_id}")

        from zebra_day.cmd_mgr import ZebraPrinter

        observed: dict[str, Any] = {
            "lab": lab,
            "printer_id": printer_id,
            "ip_address": printer.ip_address,
        }
        try:
            device = ZebraPrinter(printer.ip_address, port=9100)
            host = (
                device.get_host_identification(timeout=self.settings.default_scan_wait_seconds)
                or {}
            )
            serial = device.get_serial_number(timeout=self.settings.default_scan_wait_seconds) or ""
            observed.update(
                {
                    "model": _clean(host.get("model")),
                    "serial": _clean(serial),
                    "observed_at": _utcnow(),
                    "source": "sync",
                }
            )
            self.repository.record_observation(observed)
        except Exception as exc:
            self.repository.record_drift(
                {
                    "lab": lab,
                    "printer_id": printer_id,
                    "observed_at": _utcnow(),
                    "reason": str(exc),
                }
            )
            raise

        payload = printer.to_payload()
        if not _clean(payload.get("model")):
            payload["model"] = observed.get("model", "")
        elif observed.get("model") and payload["model"] != observed["model"]:
            self.repository.record_drift(
                {
                    "lab": lab,
                    "printer_id": printer_id,
                    "field": "model",
                    "curated_value": payload["model"],
                    "observed_value": observed["model"],
                    "observed_at": observed["observed_at"],
                }
            )
        if not _clean(payload.get("serial")):
            payload["serial"] = observed.get("serial", "")
        elif observed.get("serial") and payload["serial"] != observed["serial"]:
            self.repository.record_drift(
                {
                    "lab": lab,
                    "printer_id": printer_id,
                    "field": "serial",
                    "curated_value": payload["serial"],
                    "observed_value": observed["serial"],
                    "observed_at": observed["observed_at"],
                }
            )
        return self.repository.upsert_printer(PrinterRecord.from_payload(payload))

    def update_printer_metadata(self, lab: str, printer_id: str, **changes: Any) -> PrinterRecord:
        printer = self.repository.get_printer(lab, printer_id)
        if printer is None:
            raise KeyError(f"Printer not found: {lab}/{printer_id}")
        payload = printer.to_payload()
        payload.update({key: value for key, value in changes.items() if value is not None})
        return self.repository.upsert_printer(PrinterRecord.from_payload(payload))

    def runtime_summary(self) -> dict[str, Any]:
        return {
            "deployment_code": self.settings.deployment_code,
            "tapdb_client_id": self.settings.tapdb_client_id,
            "tapdb_database_name": self.settings.tapdb_database_name,
            "tapdb_env": self.settings.tapdb_env,
            "tapdb_config_path": str(self.settings.tapdb_config_path),
            "lab_count": len(self.list_labs()),
            "printer_count": len(self.list_printers()),
            "template_count": len(self.list_templates()),
            "label_profile_count": len(self.list_label_profiles()),
        }


class ZebraDayApiClient:
    """Remote API client for downstream consumers of shared zebra_day state."""

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        verify_ssl: bool = True,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        headers = {"accept": "application/json"}
        if api_key:
            headers["authorization"] = f"Bearer {api_key}"
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(
            base_url=self.base_url,
            verify=verify_ssl,
            headers=headers,
            follow_redirects=True,
            timeout=30.0,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ZebraDayApiClient:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _json(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self._client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    def list_labs(self) -> list[str]:
        return list(self._json("GET", "/api/v1/labs"))

    def list_printers(self, lab: str | None = None) -> list[PrinterRecord]:
        if lab is None:
            printers: list[PrinterRecord] = []
            for item in self.list_labs():
                printers.extend(self.list_printers(item))
            return printers
        rows = self._json("GET", f"/api/v1/labs/{lab}/printers")
        return [PrinterRecord.from_payload(item) for item in rows]

    def get_printer(self, printer_id: str, lab: str) -> PrinterRecord:
        payload = self._json("GET", f"/api/v1/labs/{lab}/printers/{printer_id}")
        return PrinterRecord.from_payload(payload)

    def list_templates(self) -> list[str]:
        return list(self._json("GET", "/api/v1/templates"))

    def get_template(self, template_name: str) -> dict[str, Any]:
        payload = self._json("GET", f"/api/v1/templates/{template_name}")
        return dict(payload)

    def list_label_profiles(self) -> list[dict[str, Any]]:
        payload = self._json("GET", "/api/v1/label-profiles")
        return [dict(item) for item in payload]

    def get_label_profile(self, profile_name: str) -> dict[str, Any]:
        payload = self._json("GET", f"/api/v1/label-profiles/{profile_name}")
        return dict(payload)

    def render_label(
        self,
        *,
        template: str | None = None,
        zpl_content: str | None = None,
        **fields: str,
    ) -> dict[str, Any]:
        payload = {"template": template, "zpl_content": zpl_content, **fields}
        return dict(self._json("POST", "/api/v1/render", json=payload))

    def resolve_print_request(
        self,
        *,
        lab: str,
        printer: str,
        label_zpl_style: str | None = None,
        zpl_content: str | None = None,
        copies: int = 1,
        **fields: str,
    ) -> dict[str, Any]:
        payload = {
            "lab": lab,
            "printer": printer,
            "label_zpl_style": label_zpl_style,
            "zpl_content": zpl_content,
            "copies": copies,
            **fields,
        }
        return dict(self._json("POST", "/api/v1/print/resolve", json=payload))

    def print_label(
        self,
        *,
        lab: str,
        printer: str,
        label_zpl_style: str | None = None,
        zpl_content: str | None = None,
        copies: int = 1,
        **fields: str,
    ) -> str:
        resolved = self.resolve_print_request(
            lab=lab,
            printer=printer,
            label_zpl_style=label_zpl_style,
            zpl_content=zpl_content,
            copies=copies,
            **fields,
        )
        for _ in range(int(resolved.get("copies") or copies or 1)):
            send_zpl_code(str(resolved["zpl_content"]), str(resolved["printer_ip"]))
        return str(resolved["zpl_content"])

    def submit_print_job(
        self,
        *,
        lab: str,
        printer: str,
        label_zpl_style: str | None = None,
        zpl_content: str | None = None,
        copies: int = 1,
        **fields: str,
    ) -> dict[str, Any]:
        payload = {
            "lab": lab,
            "printer": printer,
            "label_zpl_style": label_zpl_style,
            "zpl_content": zpl_content,
            "copies": copies,
            **fields,
        }
        return dict(self._json("POST", "/api/v1/print", json=payload))
