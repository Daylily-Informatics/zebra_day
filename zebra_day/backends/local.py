"""
Local filesystem backend for zebra_day config + template storage.

Wraps the existing file I/O logic that was previously embedded in
``print_mgr.zpl()``.  Implements the ``ConfigBackend`` protocol with
zero behavioral change from the legacy code paths.
"""

from __future__ import annotations

import datetime
import json
import shutil
from importlib.resources import files
from pathlib import Path

import yaml

from zebra_day import paths as xdg
from zebra_day.logging_config import get_logger

_log = get_logger(__name__)


class LocalBackend:
    """File-based config and template backend (default)."""

    def __init__(self, config_path: str | None = None) -> None:
        self._config_path: Path | None = None
        self._explicit_path = config_path

        # Resolve config path using the same search order as the old zpl.__init__
        yaml_config = xdg.get_config_file_path()
        json_config = xdg.get_legacy_json_config_path()
        pkg_template = Path(str(files("zebra_day"))) / "etc" / "zebra-day-config-template.yaml"

        if config_path:
            cfg = Path(config_path)
            if cfg.exists():
                self._config_path = cfg
            else:
                self._create_config_from_template(cfg)
                self._config_path = cfg
        elif yaml_config.exists():
            self._config_path = yaml_config
        elif json_config.exists():
            self._migrate_json_to_yaml(json_config, yaml_config)
            self._config_path = yaml_config
        elif pkg_template.exists():
            self._create_config_from_template(yaml_config)
            self._config_path = yaml_config
        else:
            self._create_minimal_config(yaml_config)
            self._config_path = yaml_config

    @property
    def config_path_str(self) -> str:
        """Return the resolved config file path as a string."""
        return str(self._config_path) if self._config_path else ""

    # ------------------------------------------------------------------
    # ConfigBackend protocol: config operations
    # ------------------------------------------------------------------

    def load_config(self) -> dict:
        """Load configuration from the resolved file path."""
        if self._config_path is None or not self._config_path.exists():
            return {"schema_version": "2.1.0", "labs": {}}
        return self._read_config_file(self._config_path)

    def save_config(self, config: dict) -> None:
        """Save config to YAML file with backup."""
        target = self._config_path or xdg.get_config_file_path()

        # Ensure YAML extension
        if target.suffix not in (".yaml", ".yml"):
            target = target.with_suffix(".yaml")

        # Backup existing file
        if target.exists():
            backup_dir = xdg.get_config_backups_dir()
            ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            backup_path = backup_dir / f"{ts}_config_backup.yaml"
            try:
                shutil.copy2(target, backup_path)
                _log.debug("Backup created: %s", backup_path)
            except OSError as e:
                _log.warning("Failed to create backup: %s", e)

        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w") as f:
            f.write("# zebra_day Configuration File\n\n")
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        self._config_path = target
        _log.debug("Config saved to: %s", target)

    def config_exists(self) -> bool:
        """Check if the config file exists on disk."""
        return self._config_path is not None and self._config_path.exists()

    # ------------------------------------------------------------------
    # ConfigBackend protocol: template operations
    # ------------------------------------------------------------------

    def get_template(self, name: str) -> str:
        """Load template ZPL content by stem name."""
        path = self.resolve_template_path(name, include_legacy_drafts=True)
        return path.read_text()

    def list_templates(self) -> list[str]:
        """List all template stem names (sorted, deduplicated)."""
        names: set[str] = set()

        def _add_from_dir(d: Path) -> None:
            if not d.exists():
                return
            for f in d.iterdir():
                if f.is_file() and f.suffix == ".zpl":
                    names.add(f.stem)

        _add_from_dir(xdg.get_label_styles_dir())
        _add_from_dir(self._package_label_styles_dir())
        return sorted(names)

    def save_template(self, name: str, zpl_content: str) -> None:
        """Save a template to the user label_styles directory."""
        stem = self._normalize_template_stem(name)
        target = xdg.get_label_styles_dir() / f"{stem}.zpl"

        # Backup existing
        if target.exists():
            ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d_%H%M%S.%fZ")
            backup = target.parent / f"{stem}.bak.{ts}.zpl"
            shutil.copy2(target, backup)

        target.write_text(str(zpl_content))

    def delete_template(self, name: str) -> None:
        """Delete a template from the user label_styles directory."""
        stem = self._normalize_template_stem(name)
        path = xdg.get_label_styles_dir() / f"{stem}.zpl"
        if not path.exists():
            raise FileNotFoundError(f"Template not found: {stem}")
        path.unlink()

    def template_exists(self, name: str) -> bool:
        """Check if a template exists in any search location."""
        try:
            self.resolve_template_path(name, include_legacy_drafts=True)
            return True
        except FileNotFoundError:
            return False

    # ------------------------------------------------------------------
    # Path resolution (local-only helpers used by zpl() for compat)
    # ------------------------------------------------------------------

    def resolve_template_path(self, template: str, *, include_legacy_drafts: bool = False) -> Path:
        """Resolve a template name to an on-disk .zpl path.

        Resolution order:
        1) User config dir (XDG): ~/.config/zebra_day/label_styles/
        2) Package etc dir: zebra_day/etc/label_styles/
        3) Legacy drafts (if enabled)
        """
        stem = self._normalize_template_stem(template)
        filename = f"{stem}.zpl"

        user_path = xdg.get_label_styles_dir() / filename
        if user_path.exists():
            return user_path

        pkg_path = self._package_label_styles_dir() / filename
        if pkg_path.exists():
            return pkg_path

        if include_legacy_drafts:
            user_draft = xdg.get_label_drafts_dir() / filename
            if user_draft.exists():
                return user_draft
            pkg_draft = self._package_label_styles_dir() / "tmps" / filename
            if pkg_draft.exists():
                return pkg_draft

        raise FileNotFoundError(f"Template '{stem}' not found")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _package_label_styles_dir() -> Path:
        return Path(str(files("zebra_day"))) / "etc" / "label_styles"

    @staticmethod
    def _normalize_template_stem(template: str) -> str:
        raw = str(template or "").strip()
        if not raw:
            raise ValueError("Template name cannot be empty")
        if "/" in raw or "\\" in raw:
            raise ValueError("Template name must be a simple filename (no directories)")
        if raw.endswith(".zpl"):
            stem = raw[:-4]
        else:
            stem = raw
        if not stem:
            raise ValueError("Template name cannot be empty")
        return stem

    @staticmethod
    def _read_config_file(config_path: Path) -> dict:
        """Parse a YAML or JSON config file and return the dict."""
        with open(config_path) as f:
            content = f.read()

        if config_path.suffix in (".yaml", ".yml"):
            data = yaml.safe_load(content) or {}
        else:
            data = json.loads(content)

        if "schema_version" not in data:
            data["schema_version"] = "2.0.0"
        if "labs" not in data:
            data["labs"] = {}
        return data

    def _create_config_from_template(self, target_path: Path) -> None:
        template = Path(str(files("zebra_day"))) / "etc" / "zebra-day-config-template.yaml"
        _log.info("Creating config from template: %s", target_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(template, target_path)

    def _create_minimal_config(self, target_path: Path) -> None:
        _log.info("Creating minimal config: %s", target_path)
        minimal = {
            "schema_version": "2.1.0",
            "labs": {
                "default": {
                    "lab_name": "Default",
                    "lab_display_name": "Default",
                    "lab_description": "",
                    "network_stub": "",
                    "available_locations": [],
                    "printers": {},
                }
            },
        }
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w") as f:
            f.write("# zebra_day Configuration File\n\n")
            yaml.dump(minimal, f, default_flow_style=False, sort_keys=False)

    def _migrate_json_to_yaml(self, json_path: Path, yaml_path: Path) -> None:
        _log.info("Migrating config from JSON to YAML: %s -> %s", json_path, yaml_path)
        with open(json_path) as f:
            config = json.load(f)
        yaml_path.parent.mkdir(parents=True, exist_ok=True)
        with open(yaml_path, "w") as f:
            f.write("# zebra_day Configuration File\n# Migrated from JSON format\n\n")
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        backup_dir = xdg.get_config_backups_dir()
        backup_name = f"{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}_migrated_from.json"
        shutil.copy2(json_path, backup_dir / backup_name)
