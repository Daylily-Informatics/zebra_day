"""In-memory backend used by the new service layer and tests."""

from __future__ import annotations

from copy import deepcopy
from importlib.resources import files
from pathlib import Path

from zebra_day import paths as xdg
from zebra_day.backends.local import LocalBackend


class MemoryBackend:
    """Ephemeral backend implementing the legacy config/template contract."""

    def __init__(
        self,
        config: dict | None = None,
        templates: dict[str, str] | None = None,
    ) -> None:
        self._config = deepcopy(config or {"schema_version": "2.1.0", "labs": {}})
        self._templates = dict(templates or {})

    @property
    def config_path_str(self) -> str:
        return ""

    def load_config(self) -> dict:
        return deepcopy(self._config)

    def save_config(self, config: dict) -> None:
        self._config = deepcopy(config)

    def config_exists(self) -> bool:
        return True

    def get_template(self, name: str) -> str:
        stem = LocalBackend._normalize_template_stem(name)  # noqa: SLF001
        if stem in self._templates:
            return self._templates[stem]
        return self.resolve_template_path(stem, include_legacy_drafts=True).read_text()

    def list_templates(self) -> list[str]:
        names = set(self._templates)
        for directory in (
            xdg.get_label_styles_dir(),
            Path(str(files("zebra_day"))) / "etc" / "label_styles",
        ):
            if not directory.exists():
                continue
            for path in directory.iterdir():
                if path.is_file() and path.suffix == ".zpl":
                    names.add(path.stem)
        return sorted(names)

    def save_template(self, name: str, zpl_content: str) -> None:
        stem = LocalBackend._normalize_template_stem(name)  # noqa: SLF001
        self._templates[stem] = str(zpl_content)

    def delete_template(self, name: str) -> None:
        stem = LocalBackend._normalize_template_stem(name)  # noqa: SLF001
        if stem in self._templates:
            del self._templates[stem]
            return
        raise FileNotFoundError(f"Template not found: {stem}")

    def template_exists(self, name: str) -> bool:
        stem = LocalBackend._normalize_template_stem(name)  # noqa: SLF001
        if stem in self._templates:
            return True
        try:
            self.resolve_template_path(stem, include_legacy_drafts=True)
        except FileNotFoundError:
            return False
        return True

    def resolve_template_path(self, template: str, *, include_legacy_drafts: bool = False) -> Path:
        stem = LocalBackend._normalize_template_stem(template)  # noqa: SLF001
        for path in (
            xdg.get_label_styles_dir() / f"{stem}.zpl",
            Path(str(files("zebra_day"))) / "etc" / "label_styles" / f"{stem}.zpl",
        ):
            if path.exists():
                return path
        if include_legacy_drafts:
            for path in (
                xdg.get_label_drafts_dir() / f"{stem}.zpl",
                Path(str(files("zebra_day"))) / "etc" / "label_styles" / "tmps" / f"{stem}.zpl",
            ):
                if path.exists():
                    return path
        raise FileNotFoundError(f"Template not found: {stem}")
