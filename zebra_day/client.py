"""Modern zebra_day service facade."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from zebra_day import paths as xdg
from zebra_day.backends.memory import MemoryBackend
from zebra_day.logging_config import get_logger
from zebra_day.optional_deps import import_from_sibling
from zebra_day.settings import ZebraDaySettings

_log = get_logger(__name__)

PRINTER_TEMPLATE_CODE = "zebra-day/fleet/printer/1.0/"
LABEL_PROFILE_TEMPLATE_CODE = "zebra-day/labels/profile/1.0/"
LABEL_TEMPLATE_TEMPLATE_CODE = "zebra-day/labels/template/1.0/"
OBSERVATION_TEMPLATE_CODE = "zebra-day/fleet/printer-observation/1.0/"
DRIFT_TEMPLATE_CODE = "zebra-day/fleet/metadata-drift/1.0/"
PRINT_JOB_TEMPLATE_CODE = "zebra-day/printing/print-job/1.0/"
PACKAGE_TEMPLATE_PACK = Path(__file__).resolve().parents[1] / "config" / "tapdb_templates" / "zebra_day" / "templates.json"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _stable_name(lab: str, printer_id: str) -> str:
    return f"{lab}/{printer_id}"


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
        }

    def to_legacy_dict(self) -> dict[str, Any]:
        profiles = list(self.label_profiles or [])
        default_style = self.default_label_profile or (profiles[0] if profiles else "")
        return {
            "ip_address": self.ip_address,
            "printer_name": self.printer_name or None,
            "lab_location": self.lab_location or None,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "serial": self.serial,
            "label_zpl_styles": profiles,
            "default_label_style": default_style or None,
            "print_method": self.print_method,
            "notes": self.notes,
            "lsmc_euid": self.lsmc_euid,
            "state": self.state,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "PrinterRecord":
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
    def upsert_template(self, template_name: str, zpl_content: str, source: str = "package") -> None: ...
    def upsert_label_profile(self, profile_name: str, payload: dict[str, Any]) -> None: ...
    def get_label_profile(self, profile_name: str) -> dict[str, Any] | None: ...
    def record_observation(self, payload: dict[str, Any]) -> None: ...
    def record_drift(self, payload: dict[str, Any]) -> None: ...
    def create_print_job(self, payload: dict[str, Any]) -> None: ...


class InMemoryFleetRepository:
    """Simple repository used by tests and local injection."""

    def __init__(self) -> None:
        self._printers: dict[tuple[str, str], PrinterRecord] = {}
        self._templates: dict[str, dict[str, Any]] = {}
        self._profiles: dict[str, dict[str, Any]] = {}
        self._observations: list[dict[str, Any]] = []
        self._drifts: list[dict[str, Any]] = []
        self._print_jobs: list[dict[str, Any]] = []

    def list_labs(self) -> list[str]:
        return sorted({lab for lab, _ in self._printers})

    def list_printers(self, lab: str | None = None) -> list[PrinterRecord]:
        items = list(self._printers.values())
        if lab is not None:
            items = [item for item in items if item.lab == lab]
        return sorted(items, key=lambda item: (item.lab, item.printer_id))

    def get_printer(self, lab: str, printer_id: str) -> PrinterRecord | None:
        return self._printers.get((lab, printer_id))

    def upsert_printer(self, printer: PrinterRecord) -> PrinterRecord:
        self._printers[(printer.lab, printer.printer_id)] = printer
        return printer

    def list_templates(self) -> list[dict[str, Any]]:
        return [
            self._templates[key]
            for key in sorted(self._templates)
            if _clean(self._templates[key].get("source")) != "deleted"
            and _clean(self._templates[key].get("zpl_content"))
        ]

    def get_template(self, template_name: str) -> dict[str, Any] | None:
        template = self._templates.get(template_name)
        if not template:
            return None
        if _clean(template.get("source")) == "deleted" or not _clean(template.get("zpl_content")):
            return None
        return template

    def upsert_template(self, template_name: str, zpl_content: str, source: str = "package") -> None:
        self._templates[template_name] = {
            "template_name": template_name,
            "zpl_content": zpl_content,
            "source": source,
        }

    def upsert_label_profile(self, profile_name: str, payload: dict[str, Any]) -> None:
        self._profiles[profile_name] = dict(payload)

    def get_label_profile(self, profile_name: str) -> dict[str, Any] | None:
        return self._profiles.get(profile_name)

    def record_observation(self, payload: dict[str, Any]) -> None:
        self._observations.append(dict(payload))

    def record_drift(self, payload: dict[str, Any]) -> None:
        self._drifts.append(dict(payload))

    def create_print_job(self, payload: dict[str, Any]) -> None:
        self._print_jobs.append(dict(payload))


class TapDBFleetRepository:
    """TapDB-backed fleet repository."""

    def __init__(self, settings: ZebraDaySettings) -> None:
        self.settings = settings
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
        os.environ.setdefault("TAPDB_CLIENT_ID", self.settings.tapdb_client_id)
        os.environ.setdefault("TAPDB_DATABASE_NAME", self.settings.tapdb_database_name)
        os.environ.setdefault("TAPDB_ENV", self.settings.tapdb_env)
        if self.settings.tapdb_config_path:
            os.environ.setdefault("TAPDB_CONFIG_PATH", str(self.settings.tapdb_config_path))
        cfg = db_config_mod.get_db_config_for_env(self.settings.tapdb_env)
        db_hostname = f"{cfg['host']}:{cfg['port']}"
        engine_type = str(cfg.get("engine_type") or "local")
        return tapdb_mod.TAPDBConnection(
            db_hostname=db_hostname,
            db_user=cfg["user"],
            db_pass=cfg["password"],
            db_name=cfg["database"],
            engine_type=engine_type,
        )

    def _session(self, *, commit: bool):
        return self._connection.session_scope(commit=commit)

    def _seed_templates(self) -> None:
        if not PACKAGE_TEMPLATE_PACK.exists():
            return
        loader = import_from_sibling("daylily_tapdb.templates.loader", "daylily-tapdb")
        with self._session(commit=True) as session:
            templates = json.loads(PACKAGE_TEMPLATE_PACK.read_text()).get("templates") or []
            loader.seed_templates(session, templates, overwrite=False)

    def _seed_package_templates(self) -> None:
        package_dir = Path(__file__).resolve().parent / "etc" / "label_styles"
        if not package_dir.exists():
            return
        for path in sorted(package_dir.glob("*.zpl")):
            self.upsert_template(path.stem, path.read_text(), source="package")
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
            labs = {_clean((item.json_addl or {}).get("lab")) for item in self._query_instances(session, "printer")}
            return sorted(lab for lab in labs if lab)

    def list_printers(self, lab: str | None = None) -> list[PrinterRecord]:
        with self._session(commit=False) as session:
            items = []
            for instance in self._query_instances(session, "printer"):
                payload = dict(instance.json_addl or {})
                payload["euid"] = _clean(instance.euid)
                record = PrinterRecord.from_payload(payload)
                if lab is None or record.lab == lab:
                    items.append(record)
            return sorted(items, key=lambda item: (item.lab, item.printer_id))

    def get_printer(self, lab: str, printer_id: str) -> PrinterRecord | None:
        with self._session(commit=False) as session:
            name = _stable_name(lab, printer_id)
            instance = (
                session.query(self._generic_instance)
                .filter(
                    self._generic_instance.category == "zebra-day",
                    self._generic_instance.subtype == "printer",
                    self._generic_instance.name == name,
                    self._generic_instance.is_deleted.is_(False),
                )
                .first()
            )
            if instance is None:
                return None
            payload = dict(instance.json_addl or {})
            payload["euid"] = _clean(instance.euid)
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
            items = []
            for instance in self._query_instances(session, "template"):
                payload = dict(instance.json_addl or {})
                payload["euid"] = _clean(instance.euid)
                if _clean(payload.get("source")) == "deleted" or not _clean(payload.get("zpl_content")):
                    continue
                items.append(payload)
            return sorted(items, key=lambda item: _clean(item.get("template_name")))

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
            payload["euid"] = _clean(instance.euid)
            if _clean(payload.get("source")) == "deleted" or not _clean(payload.get("zpl_content")):
                return None
            return payload

    def upsert_template(self, template_name: str, zpl_content: str, source: str = "package") -> None:
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
            payload["euid"] = _clean(instance.euid)
            return payload

    def record_observation(self, payload: dict[str, Any]) -> None:
        name = f"{_clean(payload.get('lab'))}/{_clean(payload.get('printer_id'))}/{_utcnow()}"
        self._upsert_instance(
            template_code=OBSERVATION_TEMPLATE_CODE,
            subtype="printer-observation",
            name=name,
            payload=dict(payload),
        )

    def record_drift(self, payload: dict[str, Any]) -> None:
        name = f"{_clean(payload.get('lab'))}/{_clean(payload.get('printer_id'))}/drift/{_utcnow()}"
        self._upsert_instance(
            template_code=DRIFT_TEMPLATE_CODE,
            subtype="metadata-drift",
            name=name,
            payload=dict(payload),
        )

    def create_print_job(self, payload: dict[str, Any]) -> None:
        job_id = _clean(payload.get("job_id")) or _utcnow()
        self._upsert_instance(
            template_code=PRINT_JOB_TEMPLATE_CODE,
            subtype="print-job",
            name=job_id,
            payload=dict(payload),
            bstatus=_clean(payload.get("status") or "submitted"),
        )


class ZebraDayClient:
    """Public zebra_day facade used by CLI, API, and downstream callers."""

    def __init__(
        self,
        settings: ZebraDaySettings | None = None,
        repository: FleetRepository | None = None,
    ) -> None:
        self.settings = settings or ZebraDaySettings.from_context()
        self.repository = repository or self._build_default_repository()

    def _build_default_repository(self) -> FleetRepository:
        try:
            return TapDBFleetRepository(self.settings)
        except Exception as exc:
            _log.warning("TapDB repository unavailable, using in-memory fallback: %s", exc)
            repository = InMemoryFleetRepository()
            package_dir = Path(__file__).resolve().parent / "etc" / "label_styles"
            if package_dir.exists():
                for path in sorted(package_dir.glob("*.zpl")):
                    repository.upsert_template(path.stem, path.read_text(), source="package")
                    repository.upsert_label_profile(
                        path.stem,
                        {
                            "profile_name": path.stem,
                            "template_name": path.stem,
                            "managed_by": "zebra-day",
                        },
                    )
            return repository

    @classmethod
    def from_context(
        cls,
        deployment: str | None = None,
        repository: FleetRepository | None = None,
    ) -> "ZebraDayClient":
        return cls(settings=ZebraDaySettings.from_context(deployment), repository=repository)

    def list_labs(self) -> list[str]:
        return self.repository.list_labs()

    def list_printers(self, lab: str) -> list[PrinterRecord]:
        return self.repository.list_printers(lab)

    def get_printer(self, printer_id: str, lab: str | None = None) -> PrinterRecord | None:
        if lab is not None:
            return self.repository.get_printer(lab, printer_id)
        for candidate in self.repository.list_printers():
            if candidate.printer_id == printer_id:
                return candidate
        return None

    def _template_map(self) -> dict[str, str]:
        return {
            _clean(item.get("template_name")): _clean(item.get("zpl_content"))
            for item in self.repository.list_templates()
            if _clean(item.get("template_name"))
        }

    def _legacy_config(self) -> dict[str, Any]:
        labs: dict[str, dict[str, Any]] = {}
        for printer in self.repository.list_printers():
            labs.setdefault(
                printer.lab,
                {
                    "lab_name": printer.lab.replace("-", " ").title(),
                    "lab_display_name": printer.lab.replace("-", " ").title(),
                    "lab_description": "",
                    "network_stub": "",
                    "available_locations": [],
                    "printers": {},
                },
            )
            labs[printer.lab]["printers"][printer.printer_id] = printer.to_legacy_dict()
        return {"schema_version": "2.1.0", "labs": labs}

    def _legacy_engine(self):
        import zebra_day.print_mgr as print_mgr

        return print_mgr.zpl(
            backend=MemoryBackend(
                config=self._legacy_config(),
                templates=self._template_map(),
            )
        )

    def discover_printers(
        self,
        *,
        ip_stub: str,
        lab: str,
        scan_http_port: int | None = None,
        progress_callback=None,
    ) -> list[PrinterRecord]:
        import zebra_day.print_mgr as print_mgr

        scanner = print_mgr.zpl(backend=MemoryBackend(config={"schema_version": "2.1.0", "labs": {}}))
        scanner.probe_zebra_printers_add_to_printers_json(
            ip_stub=ip_stub,
            lab=lab,
            scan_http_port=scan_http_port,
            scan_wait=self.settings.default_scan_wait_seconds,
            progress_callback=progress_callback,
        )
        found = []
        lab_payload = ((scanner.printers.get("labs") or {}).get(lab) or {}).get("printers") or {}
        for printer_id, info in lab_payload.items():
            existing = self.repository.get_printer(lab, printer_id)
            if existing is None:
                record = PrinterRecord(
                    printer_id=printer_id,
                    lab=lab,
                    ip_address=_clean(info.get("ip_address")),
                    printer_name=_clean(info.get("printer_name")),
                    lab_location=_clean(info.get("lab_location")),
                    manufacturer=_clean(info.get("manufacturer") or "zebra"),
                    model=_clean(info.get("model")),
                    serial=_clean(info.get("serial")),
                    label_profiles=list(info.get("label_zpl_styles") or []),
                    default_label_profile=_clean(info.get("default_label_style")),
                    print_method=_clean(info.get("print_method") or "socket"),
                    notes=_clean(info.get("notes")),
                    status="draft",
                    discovery_source=_clean(info.get("notes")),
                )
            else:
                payload = existing.to_payload()
                if not payload.get("model"):
                    payload["model"] = _clean(info.get("model"))
                if not payload.get("serial"):
                    payload["serial"] = _clean(info.get("serial"))
                payload["discovery_source"] = _clean(info.get("notes"))
                record = PrinterRecord.from_payload(payload)
            stored = self.repository.upsert_printer(record)
            observation = {
                "lab": lab,
                "printer_id": printer_id,
                "ip_address": stored.ip_address,
                "model": stored.model,
                "serial": stored.serial,
                "observed_at": _utcnow(),
                "source": _clean(info.get("notes")) or "zpl",
            }
            self.repository.record_observation(observation)
            found.append(stored)
        return found

    def sync_printer_metadata(self, printer_id: str, lab: str) -> PrinterRecord:
        printer = self.repository.get_printer(lab, printer_id)
        if printer is None:
            raise KeyError(f"Printer not found: {lab}/{printer_id}")

        from zebra_day.cmd_mgr import ZebraPrinter

        observed: dict[str, Any] = {"lab": lab, "printer_id": printer_id, "ip_address": printer.ip_address}
        try:
            device = ZebraPrinter(printer.ip_address, port=9100)
            host = device.get_host_identification(timeout=self.settings.default_scan_wait_seconds) or {}
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
        if not payload.get("model"):
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
        if not payload.get("serial"):
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

    def list_templates(self) -> list[str]:
        return sorted(_clean(item.get("template_name")) for item in self.repository.list_templates())

    def render_label(
        self,
        *,
        template: str | None = None,
        zpl_content: str | None = None,
        **fields: str,
    ) -> tuple[str, str]:
        engine = self._legacy_engine()
        if zpl_content:
            zpl_string = zpl_content
        else:
            zpl_string = engine.formulate_zpl(label_zpl_style=template, **fields)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H:%M:%S.%f")
        png_filename = f"zpl_render_{template or 'custom'}_{timestamp}.png"
        png_path = xdg.get_generated_files_dir() / png_filename
        engine.generate_label_png(zpl_string, str(png_path), relative=False)
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
        engine = self._legacy_engine()
        zpl_string = engine.print_zpl(
            lab=lab,
            printer_name=printer,
            label_zpl_style=label_zpl_style,
            zpl_content=zpl_content,
            print_n=copies,
            client_ip=client_ip,
            **fields,
        )
        self.repository.create_print_job(
            {
                "job_id": _utcnow(),
                "lab": lab,
                "printer_id": printer,
                "template": label_zpl_style or "",
                "copies": copies,
                "client_ip": client_ip,
                "status": "submitted",
                "submitted_at": _utcnow(),
            }
        )
        return zpl_string
