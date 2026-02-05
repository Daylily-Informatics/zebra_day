"""
Tests for the zebra_day paths module (XDG Base Directory).
"""

from pathlib import Path

from zebra_day import paths as xdg


def _isolate_xdg_dirs(tmp_path: Path, monkeypatch) -> Path:
    """Force XDG dirs into a temp area so tests don't touch the real home dir."""
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg_config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg_data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg_state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg_cache"))
    return home


class TestXDGPaths:
    """Tests for XDG path functions."""

    def test_get_config_dir_returns_path(self, tmp_path, monkeypatch):
        """Test get_config_dir returns a Path object."""
        _isolate_xdg_dirs(tmp_path, monkeypatch)
        result = xdg.get_config_dir()
        assert isinstance(result, Path)

    def test_get_data_dir_returns_path(self, tmp_path, monkeypatch):
        """Test get_data_dir returns a Path object."""
        _isolate_xdg_dirs(tmp_path, monkeypatch)
        result = xdg.get_data_dir()
        assert isinstance(result, Path)

    def test_get_logs_dir_returns_path(self, tmp_path, monkeypatch):
        """Test get_logs_dir returns a Path object."""
        _isolate_xdg_dirs(tmp_path, monkeypatch)
        result = xdg.get_logs_dir()
        assert isinstance(result, Path)

    def test_get_cache_dir_returns_path(self, tmp_path, monkeypatch):
        """Test get_cache_dir returns a Path object."""
        _isolate_xdg_dirs(tmp_path, monkeypatch)
        result = xdg.get_cache_dir()
        assert isinstance(result, Path)

    def test_get_state_dir_returns_path(self, tmp_path, monkeypatch):
        """Test get_state_dir returns a Path object."""
        _isolate_xdg_dirs(tmp_path, monkeypatch)
        result = xdg.get_state_dir()
        assert isinstance(result, Path)

    def test_get_printer_config_path_returns_path(self, tmp_path, monkeypatch):
        """Test get_printer_config_path returns a Path object (now YAML)."""
        _isolate_xdg_dirs(tmp_path, monkeypatch)
        result = xdg.get_printer_config_path()
        assert isinstance(result, Path)
        # Since 2.2.0, this now returns the YAML config path
        assert result.name == "zebra-day-config.yaml"

    def test_get_config_file_path_returns_yaml_path(self, tmp_path, monkeypatch):
        """Test get_config_file_path returns YAML path."""
        _isolate_xdg_dirs(tmp_path, monkeypatch)
        result = xdg.get_config_file_path()
        assert isinstance(result, Path)
        assert result.name == "zebra-day-config.yaml"

    def test_get_legacy_json_config_path_returns_json_path(self, tmp_path, monkeypatch):
        """Test get_legacy_json_config_path returns JSON path."""
        _isolate_xdg_dirs(tmp_path, monkeypatch)
        result = xdg.get_legacy_json_config_path()
        assert isinstance(result, Path)
        assert result.name == "printer_config.json"

    def test_get_generated_files_dir_returns_path(self, tmp_path, monkeypatch):
        """Test get_generated_files_dir returns a Path object."""
        _isolate_xdg_dirs(tmp_path, monkeypatch)
        result = xdg.get_generated_files_dir()
        assert isinstance(result, Path)


class TestXDGPathConsistency:
    """Tests for XDG path consistency."""

    def test_config_dir_ends_with_zebra_day(self, tmp_path, monkeypatch):
        """Test config dir path ends with zebra_day."""
        _isolate_xdg_dirs(tmp_path, monkeypatch)
        result = xdg.get_config_dir()
        assert "zebra_day" in str(result)

    def test_data_dir_ends_with_zebra_day(self, tmp_path, monkeypatch):
        """Test data dir path ends with zebra_day."""
        _isolate_xdg_dirs(tmp_path, monkeypatch)
        result = xdg.get_data_dir()
        assert "zebra_day" in str(result)


class TestConfigPathStandardization:
    def test_config_dir_defaults_to_home_dot_config(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

        result = xdg.get_config_dir()
        assert result == home / ".config" / "zebra_day"

    def test_macos_legacy_yaml_is_copied_forward_to_xdg(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        monkeypatch.setattr(xdg.sys, "platform", "darwin")

        legacy_dir = home / "Library" / "Preferences" / "zebra_day"
        legacy_dir.mkdir(parents=True, exist_ok=True)
        legacy_yaml = legacy_dir / "zebra-day-config.yaml"
        legacy_yaml.write_text("schema_version: '2.0.0'\n")

        xdg_yaml = xdg.get_config_file_path()
        assert xdg_yaml == home / ".config" / "zebra_day" / "zebra-day-config.yaml"
        assert xdg_yaml.exists()
        assert xdg_yaml.read_text() == legacy_yaml.read_text()

    def test_macos_legacy_json_is_copied_forward_to_xdg(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        monkeypatch.setattr(xdg.sys, "platform", "darwin")

        legacy_dir = home / "Library" / "Preferences" / "zebra_day"
        legacy_dir.mkdir(parents=True, exist_ok=True)
        legacy_json = legacy_dir / "printer_config.json"
        legacy_json.write_text("{}\n")

        xdg_json = xdg.get_legacy_json_config_path()
        assert xdg_json == home / ".config" / "zebra_day" / "printer_config.json"
        assert xdg_json.exists()
        assert xdg_json.read_text() == legacy_json.read_text()
