"""TapDB-backed zebra_day clients."""

from __future__ import annotations

import importlib
import json
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx

from zebra_day import paths as xdg
from zebra_day.logging_config import get_logger
from zebra_day.printer_protocol import (
    build_zpl,
    discover_printers,
    render_zpl_preview,
    send_zpl_code,
)
from zebra_day.settings import ZebraDaySettings

_log = get_logger(__name__)

PRINTER_TEMPLATE_CODE = "generic/fleet/printer/1.0/"
LABEL_PROFILE_TEMPLATE_CODE = "generic/labels/profile/1.0/"
LABEL_TEMPLATE_TEMPLATE_CODE = "generic/labels/template/1.0/"
OBSERVATION_TEMPLATE_CODE = "generic/fleet/printer-observation/1.0/"
DRIFT_TEMPLATE_CODE = "generic/fleet/metadata-drift/1.0/"
PRINT_JOB_TEMPLATE_CODE = "generic/printing/print-job/1.0/"
PACKAGE_TEMPLATE_PACK = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "tapdb_templates"
    / "zebra_day"
    / "templates.json"
)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _stable_name(lab: str, printer_id: str) -> str:
    return f"{lab}/{printer_id}"


def _timestamp_slug() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def _pyproject_dependency_version(dependency_name: str) -> str:
    data = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    for dependency in data["project"]["dependencies"]:
        if dependency.startswith(f"{dependency_name}=="):
            return dependency.split("==", 1)[1]
    raise RuntimeError(f"Missing pinned dependency: {dependency_name}")


_DAYLILY_TAPDB_VERSION = _pyproject_dependency_version("daylily-tapdb")


def _tapdb_import(module_name: str):
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        raise ImportError(
            f"daylily-tapdb=={_DAYLILY_TAPDB_VERSION} is required for this zebra_day installation"
        ) from exc


def _ensure_prefix_ownership_registry(
    *,
    owner_repo_name: str,
    domain_code: str,
    prefixes: list[str],
    registry_path: Path,
) -> Path:
    resolved_path = Path(registry_path).expanduser().resolve()
    if not resolved_path.exists():
        raise RuntimeError(f"Prefix registry not found: {resolved_path}")

    payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Prefix registry must be a JSON object: {resolved_path}")

    ownership = payload.get("ownership")
    if not isinstance(ownership, dict):
        raise RuntimeError(f"Prefix registry must define an ownership object: {resolved_path}")

    domain_claims = ownership.get(domain_code)
    if domain_claims is None:
        domain_claims = {}
        ownership[domain_code] = domain_claims
    if not isinstance(domain_claims, dict):
        raise RuntimeError(
            f"Prefix registry claims for domain {domain_code!r} must be an object: {resolved_path}"
        )

    changed = False
    for prefix in sorted({str(prefix).strip().upper() for prefix in prefixes if str(prefix).strip()}):
        existing = domain_claims.get(prefix)
        if existing is None:
            domain_claims[prefix] = {"issuer_app_code": owner_repo_name}
            changed = True
            continue
        if not isinstance(existing, dict):
            raise RuntimeError(
                f"Prefix {prefix!r} claim for domain {domain_code!r} must be an object: "
                f"{resolved_path}"
            )
        current_owner = str(
            existing.get("issuer_app_code")
            or existing.get("owner_repo_name")
            or existing.get("repo_name")
            or ""
        ).strip()
        if current_owner and current_owner != owner_repo_name:
            raise RuntimeError(
                f"Prefix {prefix!r} for domain {domain_code!r} is claimed by "
                f"{current_owner!r}, not {owner_repo_name!r}"
            )
        if current_owner != owner_repo_name or existing.get("issuer_app_code") != owner_repo_name:
            domain_claims[prefix] = {"issuer_app_code": owner_repo_name}
            changed = True

    if changed:
        resolved_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return resolved_path


def _public_printer_payload(record: PrinterRecord) -> dict[str, Any]:
    payload = record.to_payload()
    payload["printer_euid"] = _clean(payload.pop("euid", ""))
    payload.pop("printer_id", None)
    return payload


def _with_printer_euid(payload: dict[str, Any], printer_euid: str) -> dict[str, Any]:
    normalized = dict(payload)
    normalized["printer_euid"] = _clean(printer_euid)
    return normalized


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
        printer_id = _clean(payload.get("printer_id"))
        printer_euid = _clean(payload.get("printer_euid"))
        if not printer_euid:
            raise ValueError("printer_euid is required")
        return cls(
            printer_id=printer_id,
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
            euid=printer_euid,
        )


class FleetRepository(Protocol):
    def list_labs(self) -> list[str]: ...
    def list_printers(self, lab: str | None = None) -> list[PrinterRecord]: ...
    def get_printer(self, lab: str, printer_id: str) -> PrinterRecord | None: ...
    def get_printer_by_euid(self, printer_euid: str) -> PrinterRecord | None: ...
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
        self._tapdb = _tapdb_import("daylily_tapdb")
        self._template_manager = self._tapdb.TemplateManager()
        self._generic_instance = _tapdb_import("daylily_tapdb.models.instance").generic_instance
        self._seed_templates()
        self._seed_package_templates()

    def _build_connection(self):
        tapdb_mod = _tapdb_import("daylily_tapdb")
        db_config_mod = _tapdb_import("daylily_tapdb.cli.db_config")
        cfg = db_config_mod.get_db_config_for_env(
            self.settings.tapdb_env,
            config_path=str(self.settings.tapdb_config_path),
            client_id=self.settings.tapdb_client_id,
            database_name=self.settings.tapdb_database_name,
        )
        db_hostname = f"{cfg['host']}:{cfg['port']}"
        return tapdb_mod.TAPDBConnection(
            db_hostname=db_hostname,
            db_user=cfg["user"],
            db_pass=cfg["password"],
            db_name=cfg["database"],
            engine_type=str(cfg.get("engine_type") or "local"),
            domain_code=self.settings.tapdb_domain_code,
            owner_repo_name=self.settings.tapdb_owner_repo_name,
            domain_registry_path=str(self.settings.tapdb_domain_registry_path),
            prefix_registry_path=str(self.settings.tapdb_prefix_registry_path),
        )

    def _session(self, *, commit: bool):
        return self._connection.session_scope(commit=commit)

    def _seed_templates(self) -> None:
        if not PACKAGE_TEMPLATE_PACK.exists():
            raise FileNotFoundError(f"TapDB template pack not found: {PACKAGE_TEMPLATE_PACK}")
        loader = _tapdb_import("daylily_tapdb.templates.loader")
        with self._session(commit=True) as session:
            templates = (
                json.loads(PACKAGE_TEMPLATE_PACK.read_text(encoding="utf-8")).get("templates") or []
            )
            prefix_registry_path = _ensure_prefix_ownership_registry(
                owner_repo_name=self.settings.tapdb_owner_repo_name,
                domain_code=self.settings.tapdb_domain_code,
                prefixes=[str(template.get("instance_prefix") or "") for template in templates],
                registry_path=self.settings.tapdb_prefix_registry_path,
            )
            loader.seed_templates(
                session,
                templates,
                overwrite=False,
                core_config_dir=loader.find_tapdb_core_config_dir(),
                domain_code=self.settings.tapdb_domain_code,
                owner_repo_name=self.settings.tapdb_owner_repo_name,
                domain_registry_path=str(self.settings.tapdb_domain_registry_path),
                prefix_registry_path=str(prefix_registry_path),
            )

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
                self._generic_instance.category == "generic",
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
                    self._generic_instance.category == "generic",
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
                record = PrinterRecord.from_payload(
                    _with_printer_euid(payload, _clean(getattr(instance, "euid", "")))
                )
                if lab is None or record.lab == lab:
                    items.append(record)
            return sorted(items, key=lambda item: (item.lab, item.printer_id))

    def get_printer(self, lab: str, printer_id: str) -> PrinterRecord | None:
        with self._session(commit=False) as session:
            instance = (
                session.query(self._generic_instance)
                .filter(
                    self._generic_instance.category == "generic",
                    self._generic_instance.subtype == "printer",
                    self._generic_instance.name == _stable_name(lab, printer_id),
                    self._generic_instance.is_deleted.is_(False),
                )
                .first()
            )
            if instance is None:
                return None
            payload = dict(instance.json_addl or {})
            return PrinterRecord.from_payload(
                _with_printer_euid(payload, _clean(getattr(instance, "euid", "")))
            )

    def get_printer_by_euid(self, printer_euid: str) -> PrinterRecord | None:
        with self._session(commit=False) as session:
            instance = (
                session.query(self._generic_instance)
                .filter(
                    self._generic_instance.category == "generic",
                    self._generic_instance.subtype == "printer",
                    self._generic_instance.euid == printer_euid,
                    self._generic_instance.is_deleted.is_(False),
                )
                .first()
            )
            if instance is None:
                return None
            payload = dict(instance.json_addl or {})
            return PrinterRecord.from_payload(
                _with_printer_euid(payload, _clean(getattr(instance, "euid", "")))
            )

    def upsert_printer(self, printer: PrinterRecord) -> PrinterRecord:
        payload = printer.to_payload()
        stored = self._upsert_instance(
            template_code=PRINTER_TEMPLATE_CODE,
            subtype="printer",
            name=_stable_name(printer.lab, printer.printer_id),
            payload=payload,
            bstatus=printer.status or "active",
        )
        return PrinterRecord.from_payload(_with_printer_euid(payload, stored.get("euid", "")))

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
                    self._generic_instance.category == "generic",
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
                    self._generic_instance.category == "generic",
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

    def get_printer(
        self, printer_euid: str, lab: str | None = None
    ) -> PrinterRecord | None:
        candidate = self.repository.get_printer_by_euid(printer_euid)
        if candidate is None:
            return None
        if lab is not None and candidate.lab != lab:
            return None
        return candidate

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
        printer_euid: str,
        label_zpl_style: str | None = None,
        zpl_content: str | None = None,
        copies: int = 1,
        **fields: str,
    ) -> dict[str, Any]:
        printer_record = self.get_printer(printer_euid, lab=lab)
        if printer_record is None:
            raise KeyError(f"Printer not found: {lab}/{printer_euid}")

        resolved_style = _clean(label_zpl_style) or _clean(printer_record.default_label_profile)
        if not resolved_style:
            profiles = list(printer_record.label_profiles or [])
            if profiles:
                resolved_style = _clean(profiles[0])
        if not resolved_style and not zpl_content:
            raise KeyError(f"No label profile configured for printer: {lab}/{printer_record}")

        zpl_string, template_name = self.build_label(
            template=resolved_style or None,
            zpl_content=zpl_content,
            **fields,
        )
        return {
            "lab": lab,
            "printer_id": printer_record.printer_id,
            "printer_euid": printer_record.euid,
            "printer_ip": printer_record.ip_address,
            "printer": _public_printer_payload(printer_record),
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
        printer_euid: str,
        label_zpl_style: str | None = None,
        zpl_content: str | None = None,
        copies: int = 1,
        client_ip: str = "unknown",
        **fields: str,
    ) -> str:
        resolved = self.resolve_print_request(
            lab=lab,
            printer_euid=printer_euid,
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
                    "printer_euid": resolved["printer_euid"],
                    "job_id": _timestamp_slug(),
                    "lab": lab,
                    "printer_id": resolved.get("printer_id", ""),
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
                merged["printer_euid"] = _clean(merged.get("euid", ""))
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

    def sync_printer_metadata(self, printer_euid: str, lab: str) -> PrinterRecord:
        printer = self.repository.get_printer_by_euid(printer_euid)
        if printer is None:
            raise KeyError(f"Printer not found: {lab}/{printer_euid}")
        if printer.lab != lab:
            raise KeyError(f"Printer not found: {lab}/{printer_euid}")

        from zebra_day.cmd_mgr import ZebraPrinter

        observed: dict[str, Any] = {
            "lab": lab,
            "printer_id": printer.printer_id,
            "printer_euid": printer_euid,
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
                    "printer_id": printer.printer_id,
                    "printer_euid": printer_euid,
                    "observed_at": _utcnow(),
                    "reason": str(exc),
                }
            )
            raise

        payload = printer.to_payload()
        payload["printer_euid"] = _clean(payload.get("euid", ""))
        if not _clean(payload.get("model")):
            payload["model"] = observed.get("model", "")
        elif observed.get("model") and payload["model"] != observed["model"]:
            self.repository.record_drift(
                {
                    "lab": lab,
                    "printer_id": printer.printer_id,
                    "printer_euid": printer_euid,
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
                    "printer_id": printer.printer_id,
                    "printer_euid": printer_euid,
                    "field": "serial",
                    "curated_value": payload["serial"],
                    "observed_value": observed["serial"],
                    "observed_at": observed["observed_at"],
                }
            )
        return self.repository.upsert_printer(PrinterRecord.from_payload(payload))

    def update_printer_metadata(self, lab: str, printer_euid: str, **changes: Any) -> PrinterRecord:
        printer = self.repository.get_printer_by_euid(printer_euid)
        if printer is None:
            raise KeyError(f"Printer not found: {lab}/{printer_euid}")
        if printer.lab != lab:
            raise KeyError(f"Printer not found: {lab}/{printer_euid}")
        payload = printer.to_payload()
        payload.update({key: value for key, value in changes.items() if value is not None})
        payload["printer_euid"] = _clean(payload.get("euid", ""))
        return self.repository.upsert_printer(PrinterRecord.from_payload(payload))

    def runtime_summary(self) -> dict[str, Any]:
        return {
            "deployment_code": self.settings.deployment_code,
            "tapdb_client_id": self.settings.tapdb_client_id,
            "tapdb_owner_repo_name": self.settings.tapdb_owner_repo_name,
            "tapdb_domain_code": self.settings.tapdb_domain_code,
            "tapdb_database_name": self.settings.tapdb_database_name,
            "tapdb_env": self.settings.tapdb_env,
            "tapdb_config_path": str(self.settings.tapdb_config_path),
            "tapdb_domain_registry_path": str(self.settings.tapdb_domain_registry_path),
            "tapdb_prefix_registry_path": str(self.settings.tapdb_prefix_registry_path),
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

    def get_printer(self, printer_euid: str, lab: str) -> PrinterRecord:
        payload = self._json("GET", f"/api/v1/labs/{lab}/printers/{printer_euid}")
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
        printer_euid: str,
        label_zpl_style: str | None = None,
        zpl_content: str | None = None,
        copies: int = 1,
        **fields: str,
    ) -> dict[str, Any]:
        payload = {
            "lab": lab,
            "printer_euid": printer_euid,
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
        printer_euid: str,
        label_zpl_style: str | None = None,
        zpl_content: str | None = None,
        copies: int = 1,
        **fields: str,
    ) -> str:
        resolved = self.resolve_print_request(
            lab=lab,
            printer_euid=printer_euid,
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
        printer_euid: str,
        label_zpl_style: str | None = None,
        zpl_content: str | None = None,
        copies: int = 1,
        **fields: str,
    ) -> dict[str, Any]:
        payload = {
            "lab": lab,
            "printer_euid": printer_euid,
            "label_zpl_style": label_zpl_style,
            "zpl_content": zpl_content,
            "copies": copies,
            **fields,
        }
        return dict(self._json("POST", "/api/v1/print", json=payload))
